"""Canonical Agent Run normalization, incremental merge, and atomic output."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .diagnostics import diagnostic
from .identity import build_identity, canonical_bytes, sha256
from .models import (
    ADAPTER_VERSION,
    NORMALIZATION_SCHEMA,
    NORMALIZER_VERSION,
    RUN_RECORD_SCHEMA,
)


class NormalizationError(ValueError):
    """A run could not be normalized without violating identity semantics."""


def normalize_run(
    source: str,
    input_path: Path,
    *,
    run_group_id: str | None = None,
    base_byte_offset: int = 0,
    partial: bool = False,
    generation_id: str | None = None,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize one complete or partial native run and merge optional prior state."""
    adapter = _adapter(source)
    source_name = "claude-code" if source in {"claude-code", "claude_code"} else source
    if not isinstance(base_byte_offset, int) or isinstance(base_byte_offset, bool) or base_byte_offset < 0:
        raise NormalizationError("base_byte_offset must be a non-negative integer")
    path = Path(input_path)
    if path.is_symlink() or not path.is_file():
        raise NormalizationError("input_path must be a regular, non-symbolic-link file")
    previous = _validate_prior(prior, source_name)
    previous_manifest = previous.get("manifest", {}) if previous else {}
    selected_generation = generation_id or (
        previous_manifest.get("generation_id") if previous else "generation-0"
    )
    if not isinstance(selected_generation, str) or not selected_generation:
        raise NormalizationError("generation_id must be a non-empty string")
    if previous and previous_manifest.get("generation_id") != selected_generation:
        raise NormalizationError("prior generation_id does not match this normalization")

    events, parse_diagnostics = _read_events(path, base_byte_offset)
    group_ids: set[str] = set()
    for event in events:
        group_ids.update(adapter.discover_group_ids(event["value"]))
    prior_group = previous_manifest.get("run_group_id") if previous else None
    selected_group = run_group_id or prior_group
    diagnostics = list(previous.get("diagnostics", [])) if previous else []
    diagnostics.extend(parse_diagnostics)
    if selected_group is None:
        if group_ids:
            selected_group = sorted(group_ids)[0]
        else:
            selected_group = "run-group-" + sha256(
                {"source": source_name, "path": str(path.resolve())}
            )[:16]
            diagnostics.append(
                diagnostic(
                    "missing_run_group",
                    "warning",
                    "No native run group was available; a deterministic local group was synthesized.",
                )
            )
    if not isinstance(selected_group, str) or not selected_group:
        raise NormalizationError("run_group_id must be a non-empty string")
    conflicting_groups = group_ids - {selected_group}
    if conflicting_groups or (prior_group and prior_group != selected_group):
        diagnostics.append(
            diagnostic(
                "run_group_conflict",
                "error",
                "Input records expose more than one run group; the selected group was retained.",
                count=len(conflicting_groups) + int(bool(prior_group and prior_group != selected_group)),
            )
        )

    content_fallback = partial and generation_id is None
    current_records: list[dict[str, Any]] = []
    for event in events:
        location = event["location"]
        value = event["value"]
        if _flag(value, "truncated") or _flag(value, "output_truncated"):
            diagnostics.append(
                diagnostic(
                    "truncated_tool_output",
                    "warning",
                    "A source record declares truncated output.",
                    **location,
                )
            )
        if _flag(value, "repaired"):
            diagnostics.append(
                diagnostic(
                    "repaired_record",
                    "warning",
                    "A source record declares a prior repair; no silent repair was applied.",
                    **location,
                )
            )
        drafts = adapter.extract(value)
        if not drafts:
            diagnostics.append(
                diagnostic(
                    "unsupported_record",
                    "info",
                    "The source record type is not supported by this adapter.",
                    **location,
                )
            )
            continue
        for component_index, draft in enumerate(drafts):
            record, record_diagnostics = _record_from_draft(
                draft,
                source_name=source_name,
                run_group_id=selected_group,
                generation_id=selected_generation,
                source_order_id=_source_order_id(location, component_index),
                content_fallback=content_fallback,
                location=location,
            )
            current_records.append(record)
            diagnostics.extend(record_diagnostics)

    records, merge_diagnostics = _merge_records(
        list(previous.get("records", [])) if previous else [],
        current_records,
    )
    diagnostics.extend(merge_diagnostics)
    diagnostics = [
        item
        for item in diagnostics
        if item.get("code") not in {"orphan_tool_result", "missing_tool_result"}
    ]
    records, link_diagnostics = _link_tools(records, partial=partial)
    diagnostics.extend(link_diagnostics)
    if partial:
        diagnostics.append(
            diagnostic(
                "partial_run",
                "info",
                "This normalization covers a partial run and may not contain final tool results.",
            )
        )
    diagnostics = _deduplicate_diagnostics(diagnostics)

    configuration = {
        "source_type": source_name,
        "partial": partial,
        "base_byte_offset": base_byte_offset,
        "generation_id": selected_generation,
    }
    provenance = {
        "normalizer_version": NORMALIZER_VERSION,
        "schema_version": RUN_RECORD_SCHEMA,
        "adapter_name": adapter.adapter_name,
        "adapter_version": ADAPTER_VERSION,
        "configuration_hash": sha256(configuration),
    }
    manifest = {
        "source_type": source_name,
        "run_group_id": selected_group,
        "generation_id": selected_generation,
        "partial": partial,
        "base_byte_offset": base_byte_offset,
        "provenance": provenance,
        "record_count": len(records),
        "diagnostic_count": len(diagnostics),
    }
    return {
        "schema_version": NORMALIZATION_SCHEMA,
        "manifest": manifest,
        "records": records,
        "diagnostics": diagnostics,
    }


def write_normalized_run(result: dict[str, Any], output_dir: Path) -> Path:
    """Atomically replace one normalized-run directory."""
    if set(result) != {"schema_version", "manifest", "records", "diagnostics"}:
        raise NormalizationError("normalized result has unexpected top-level fields")
    if result.get("schema_version") != NORMALIZATION_SCHEMA:
        raise NormalizationError("normalized result schema_version is unsupported")
    requested_output = Path(output_dir)
    output = requested_output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    backup: Path | None = None
    try:
        _atomic_text(
            temporary / "manifest.json",
            json.dumps(result["manifest"], ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            + "\n",
        )
        _atomic_text(
            temporary / "records.jsonl",
            "".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                + "\n"
                for item in result["records"]
            ),
        )
        _atomic_text(
            temporary / "diagnostics.jsonl",
            "".join(
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                + "\n"
                for item in result["diagnostics"]
            ),
        )
        if output.exists():
            if output.is_symlink() or not output.is_dir():
                raise NormalizationError("output_dir must be a directory and cannot be a symbolic link")
            backup = Path(tempfile.mkdtemp(prefix=f".{output.name}.backup.", dir=output.parent))
            backup.rmdir()
            os.replace(output, backup)
        os.replace(temporary, output)
        temporary = output
        if backup is not None:
            shutil.rmtree(backup)
        return requested_output
    except (OSError, TypeError, ValueError) as error:
        if backup is not None and backup.exists() and not output.exists():
            os.replace(backup, output)
        if isinstance(error, NormalizationError):
            raise
        raise NormalizationError(f"cannot write normalized run: {error}") from error
    finally:
        if temporary.exists() and temporary != output:
            shutil.rmtree(temporary, ignore_errors=True)


def load_normalized_run(path: Path) -> dict[str, Any]:
    """Load one normalized-run directory with strict JSON semantics."""
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise NormalizationError(
            "normalized run must be a non-symbolic-link directory"
        )
    manifest = _strict_json_object(root / "manifest.json", "manifest.json")

    def jsonl(name: str) -> list[dict[str, Any]]:
        target = root / name
        if target.is_symlink() or not target.is_file():
            raise NormalizationError(f"normalized run is missing {name}")
        records: list[dict[str, Any]] = []
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            raise NormalizationError(f"cannot read {name}: {error}") from error
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(
                    line,
                    parse_constant=lambda item: (_raise_nonfinite(item)),
                    object_pairs_hook=_unique_object,
                )
            except (json.JSONDecodeError, ValueError) as error:
                raise NormalizationError(
                    f"cannot read {name}:{number}: {error}"
                ) from error
            if not isinstance(value, dict):
                raise NormalizationError(
                    f"{name}:{number} must be a JSON object"
                )
            records.append(value)
        return records

    return {
        "manifest": manifest,
        "records": jsonl("records.jsonl"),
        "diagnostics": jsonl("diagnostics.jsonl"),
    }


def _strict_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=lambda item: (_raise_nonfinite(item)),
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise NormalizationError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise NormalizationError(f"{label} must be a JSON object")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _raise_nonfinite(value: str) -> Any:
    raise ValueError(f"non-finite JSON number: {value}")


def _adapter(source: str) -> Any:
    if source == "codex":
        from .adapters import codex

        return codex
    if source in {"claude-code", "claude_code"}:
        from .adapters import claude_code

        return claude_code
    raise NormalizationError(f"unsupported source adapter: {source}")


def _validate_prior(prior: dict[str, Any] | None, source: str) -> dict[str, Any]:
    if prior is None:
        return {}
    if (
        not isinstance(prior, dict)
        or set(prior) != {"schema_version", "manifest", "records", "diagnostics"}
        or prior.get("schema_version") != NORMALIZATION_SCHEMA
        or not isinstance(prior.get("manifest"), dict)
        or not isinstance(prior.get("records"), list)
        or not isinstance(prior.get("diagnostics"), list)
    ):
        raise NormalizationError("prior must be a complete agent-run-normalization/1.0 result")
    if prior["manifest"].get("source_type") != source:
        raise NormalizationError("prior source_type does not match this normalization")
    return prior


def _read_events(path: Path, base_byte_offset: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise NormalizationError(f"cannot read input run: {error}") from error
    segment = raw
    stripped = segment.lstrip()
    if base_byte_offset == 0 and stripped.startswith(b"["):
        try:
            values = json.loads(segment.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return [], [diagnostic("malformed_record", "error", "The input JSON array is malformed.")]
        if not isinstance(values, list):
            return [], [diagnostic("malformed_record", "error", "The input must contain JSON records.")]
        events = []
        diagnostics = []
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                diagnostics.append(
                    diagnostic(
                        "malformed_record",
                        "error",
                        "A source record is not a JSON object.",
                        record_index=index,
                    )
                )
                continue
            events.append({"value": value, "location": {"record_index": index}})
        return events, diagnostics

    events: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    cursor = base_byte_offset
    line_number = 1
    for raw_line in segment.splitlines(keepends=True):
        line_offset = cursor
        cursor += len(raw_line)
        if not raw_line.strip():
            line_number += 1
            continue
        try:
            value = json.loads(raw_line.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            diagnostics.append(
                diagnostic(
                    "malformed_record",
                    "error",
                    "A source JSONL record is malformed.",
                    line=line_number,
                    byte_offset=line_offset,
                )
            )
            line_number += 1
            continue
        if not isinstance(value, dict):
            diagnostics.append(
                diagnostic(
                    "malformed_record",
                    "error",
                    "A source JSONL record is not an object.",
                    line=line_number,
                    byte_offset=line_offset,
                )
            )
        else:
            events.append(
                {
                    "value": value,
                    "location": {"line": line_number, "byte_offset": line_offset},
                }
            )
        line_number += 1
    return events, diagnostics


def _record_from_draft(
    draft: dict[str, Any],
    *,
    source_name: str,
    run_group_id: str,
    generation_id: str,
    source_order_id: str,
    content_fallback: bool,
    location: dict[str, int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    record_type = draft["record_type"]
    fields = dict(draft["fields"])
    diagnostics: list[dict[str, Any]] = []
    if record_type == "tool_call":
        valid = fields.pop("arguments_valid", False)
        arguments = fields.pop("arguments", None)
        if not valid:
            diagnostics.append(
                diagnostic(
                    "invalid_tool_arguments",
                    "warning",
                    "Tool arguments were not a valid JSON object or array.",
                    **location,
                )
            )
            arguments = None
        fields["arguments_json"] = json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    elif record_type == "tool_result":
        result = fields.pop("result", None)
        if isinstance(result, str):
            fields["result_text"] = result
        elif result is not None:
            fields["result_json"] = json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        fields["linked_tool_call_record_id"] = None

    semantic_content = {"record_type": record_type, **fields}
    synthetic = record_type == "meta"
    native = draft.get("native_id")
    identity = build_identity(
        run_group_id=run_group_id,
        generation_id=generation_id,
        native_id=native if isinstance(native, str) and native else None,
        source_order_id=source_order_id,
        semantic_component_key=str(draft["component"]),
        semantic_content=semantic_content,
        synthetic=synthetic,
        content_fallback=content_fallback,
    )
    if identity["identity_kind"] == "content":
        diagnostics.append(
            diagnostic(
                "content_identity_fallback",
                "warning",
                "Stable native or generation-bound location identity was unavailable; content identity was used.",
                **location,
            )
        )
    timestamp = draft.get("timestamp")
    if not _valid_timestamp(timestamp):
        if timestamp is not None:
            diagnostics.append(
                diagnostic(
                    "invalid_timestamp",
                    "warning",
                    "A source timestamp was invalid and was not retained.",
                    **location,
                )
            )
        timestamp = _synthesized_timestamp(source_order_id)
        diagnostics.append(
            diagnostic(
                "synthesized_timestamp",
                "info",
                "A deterministic placeholder timestamp was synthesized.",
                **location,
            )
        )
    record = {
        "schema_version": RUN_RECORD_SCHEMA,
        "record_type": record_type,
        "record_id": identity["record_id"],
        "timestamp": timestamp,
        "source_identity": identity,
        **fields,
    }
    if record_type == "meta":
        record["source_type"] = fields.get("source_type", source_name)
    return record, diagnostics


def _merge_records(
    prior: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, Any]] = []
    for record in [*prior, *current]:
        identifier = record.get("record_id")
        content_hash = record.get("source_identity", {}).get("content_hash")
        if not isinstance(identifier, str) or not isinstance(content_hash, str):
            raise NormalizationError("record identity is incomplete")
        existing = by_id.get(identifier)
        if existing is None:
            copy = dict(record)
            copy["source_identity"] = dict(record["source_identity"])
            by_id[identifier] = copy
            merged.append(copy)
        elif existing["source_identity"]["content_hash"] != content_hash:
            raise NormalizationError(
                "the same stable source identity produced different semantic content"
            )
    return merged, diagnostics


def _link_tools(
    records: list[dict[str, Any]],
    *,
    partial: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    calls: dict[str, str] = {}
    for record in records:
        if record.get("record_type") == "tool_call":
            call_id = record.get("tool_call_id")
            if isinstance(call_id, str) and call_id:
                calls.setdefault(call_id, record["record_id"])
    result_ids: set[str] = set()
    diagnostics: list[dict[str, Any]] = []
    filtered: list[dict[str, Any]] = []
    for record in records:
        if record.get("record_type") == "tool_call":
            filtered.append(record)
            continue
        if record.get("record_type") != "tool_result":
            filtered.append(record)
            continue
        call_id = record.get("tool_call_id")
        if isinstance(call_id, str) and call_id in result_ids:
            diagnostics.append(
                diagnostic(
                    "duplicate_tool_result",
                    "warning",
                    "A duplicate tool result for the same call was ignored.",
                )
            )
            continue
        if isinstance(call_id, str):
            result_ids.add(call_id)
        linked = calls.get(call_id) if isinstance(call_id, str) else None
        record["linked_tool_call_record_id"] = linked
        if linked is None:
            diagnostics.append(
                diagnostic(
                    "orphan_tool_result",
                    "warning",
                    "A tool result has no matching tool call in the available run records.",
                )
            )
        filtered.append(record)
    if not partial:
        for call_id in sorted(set(calls) - result_ids):
            diagnostics.append(
                diagnostic(
                    "missing_tool_result",
                    "warning",
                    "A completed run contains a tool call without a matching result.",
                )
            )
    return filtered, diagnostics


def _source_order_id(location: dict[str, int], component_index: int) -> str:
    if "byte_offset" in location:
        return f"byte:{location['byte_offset']:020d}:component:{component_index:04d}"
    return f"record:{location.get('record_index', 0):020d}:component:{component_index:04d}"


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _synthesized_timestamp(source_order_id: str) -> str:
    microseconds = int(sha256(source_order_id)[:8], 16)
    return (datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=microseconds)).isoformat()


def _flag(value: Any, name: str) -> bool:
    if isinstance(value, dict):
        if value.get(name) is True:
            return True
        return any(_flag(child, name) for child in value.values())
    if isinstance(value, list):
        return any(_flag(child, name) for child in value)
    return False


def _reject_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")


def _deduplicate_diagnostics(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[bytes] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        encoded = canonical_bytes(value)
        if encoded not in seen:
            seen.add(encoded)
            result.append(value)
    return result


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
