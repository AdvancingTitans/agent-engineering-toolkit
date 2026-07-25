"""Compile internal investigation records into a portable directory Bundle."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical import canonical_json_bytes, manifest_content_hash
from .loader import BundleError
from .markdown import render_bundle_markdown, render_consumer_guide
from .redaction import redact_bundle_material
from .selector import excluded_record_count, select_records
from .validator import validate_bundle


_CONTENT_PATHS = {
    "index": "index.json",
    "claims": "core/claims.jsonl",
    "evidence": "core/evidence.jsonl",
    "observations": "core/observations.jsonl",
    "sources": "archive/sources.jsonl",
    "diagnostics": "archive/diagnostics.jsonl",
    "conflicts": "archive/conflicts.jsonl",
    "ledger": "archive/ledger.jsonl",
    "policy": "policy.json",
    "consumer_guide": "consumer-guide.md",
    "report": "report.md",
}


def compile_bundle(
    payload: Mapping[str, Any],
    output: Path,
    *,
    claim_refs: Sequence[str] | None = None,
    max_blob_bytes: int = 64 * 1024 * 1024,
) -> dict[str, Any]:
    """Compile, validate, and atomically publish one question-bounded Bundle."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise BundleError("output_exists", f"Bundle output already exists: {output}")
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    selected = select_records(payload, claim_refs)
    excluded = excluded_record_count(payload, selected)
    policy = _object_copy(payload.get("policy"), "policy")
    raw_blobs = _selected_blobs(
        _blob_mapping(payload.get("blobs", {})),
        selected,
    )
    if policy.get("privacy_policy", {}).get("redact_secrets") is True:
        selected, blobs = redact_bundle_material(selected, raw_blobs)
    else:
        blobs = dict(raw_blobs)

    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=parent))
    try:
        _write_compiled_files(temporary, payload, selected, policy, blobs, excluded)
        validate_bundle(temporary, max_blob_bytes=max_blob_bytes)
        os.replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return validate_bundle(output, max_blob_bytes=max_blob_bytes)


def _write_compiled_files(
    root: Path,
    payload: Mapping[str, Any],
    selected: Mapping[str, list[dict[str, Any]]],
    policy: dict[str, Any],
    blobs: Mapping[str, bytes],
    excluded: int,
) -> None:
    (root / "core").mkdir()
    (root / "archive").mkdir()
    if blobs:
        (root / "blobs").mkdir()
    for name in ("claims", "evidence", "observations", "sources", "diagnostics", "conflicts", "ledger"):
        _write_jsonl(root / _CONTENT_PATHS[name], selected[name])
    _write_json(root / _CONTENT_PATHS["policy"], policy)
    for reference, raw in sorted(blobs.items()):
        _validate_blob_mapping(reference, raw)
        destination = root / reference
        destination.write_bytes(raw)

    task = _object_copy(payload.get("task"), "task")
    investigation = _object_copy(payload.get("investigation"), "investigation")
    bundle_id = _required_string(payload.get("bundle_id"), "bundle_id")
    manifest = {
        "protocol": {
            "name": "portable-evidence-bundle",
            "version": "1.0",
            "schema_uri": (
                "https://advancingtitans.github.io/agent-engineering-toolkit/"
                "schemas/evidence-bundle/v1/manifest.schema.json"
            ),
        },
        "bundle": {
            "id": bundle_id,
            "created_at": _required_string(payload.get("created_at"), "created_at"),
            "content_hash": "0" * 64,
            **(
                {"parent_bundle_id": payload["parent_bundle_id"]}
                if "parent_bundle_id" in payload
                else {}
            ),
        },
        "task": task,
        "producer": {
            "name": "agent-engineering-toolkit",
            "version": _required_string(payload.get("producer_version"), "producer_version"),
        },
        "investigation": investigation,
        "contents": dict(_CONTENT_PATHS),
        "integrity": {"algorithm": "sha256", "file_hashes": {}},
    }
    index = {
        "schema_version": "portable-evidence-bundle-index/1.0",
        "bundle_id": bundle_id,
        "question": investigation.get("question"),
        "claim_refs": [record["id"] for record in selected["claims"]],
        "evidence_refs": [record["id"] for record in selected["evidence"]],
        "observation_refs": [record["id"] for record in selected["observations"]],
        "reading_order": [
            _CONTENT_PATHS["claims"],
            _CONTENT_PATHS["evidence"],
            _CONTENT_PATHS["observations"],
        ],
        "excluded": {
            "count": excluded,
            "reason": _required_string(
                payload.get(
                    "excluded_reason",
                    "Records not relevant to the declared investigation question were omitted.",
                ),
                "excluded_reason",
            ),
        },
        "archive_available": True,
        "consumer_guidance": deepcopy(
            payload.get(
                "consumer_guidance",
                {
                    "must": [
                        "事实结论必须引用有效证据 ID。",
                        "使用历史证据前必须检查时效状态。",
                    ],
                    "must_not": [
                        "不得把执行者自述当作已复现证据。",
                        "不得把缺失证据解释为事情没有发生。",
                    ],
                },
            )
        ),
    }
    _write_json(root / _CONTENT_PATHS["index"], index)
    (root / _CONTENT_PATHS["consumer_guide"]).write_text(
        render_consumer_guide(),
        encoding="utf-8",
    )
    (root / _CONTENT_PATHS["report"]).write_text(
        render_bundle_markdown({"manifest": manifest, "claims": selected["claims"]}),
        encoding="utf-8",
    )
    paths = {
        *_CONTENT_PATHS.values(),
        *blobs,
    }
    manifest["integrity"]["file_hashes"] = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in sorted(paths)
    }
    manifest["bundle"]["content_hash"] = manifest_content_hash(manifest)
    _write_json(root / "manifest.json", manifest)


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_bytes(b"".join(canonical_json_bytes(value) + b"\n" for value in values))


def _object_copy(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleError("invalid_bundle", f"{label} must be an object")
    return deepcopy(value)


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BundleError("invalid_bundle", f"{label} must be a non-empty string")
    return value


def _blob_mapping(value: Any) -> dict[str, bytes]:
    if not isinstance(value, Mapping):
        raise BundleError("invalid_bundle", "blobs must be a mapping")
    result = dict(value)
    for reference, raw in result.items():
        _validate_blob_mapping(reference, raw)
    return result


def _validate_blob_mapping(reference: Any, raw: Any) -> None:
    if not isinstance(reference, str) or not isinstance(raw, bytes):
        raise BundleError("invalid_bundle", "Blob mapping must use string paths and byte values")
    digest = hashlib.sha256(raw).hexdigest()
    if reference != f"blobs/sha256-{digest}":
        raise BundleError("integrity_error", f"Blob key does not match content: {reference}")


def _selected_blobs(
    blobs: Mapping[str, bytes],
    records: Mapping[str, list[dict[str, Any]]],
) -> dict[str, bytes]:
    references: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            blob_ref = value.get("blob_ref")
            if isinstance(blob_ref, str):
                references.add(blob_ref)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(records)
    missing = sorted(references - set(blobs))
    if missing:
        raise BundleError(
            "integrity_error",
            "selected records reference missing Blobs: " + ", ".join(missing),
        )
    return {reference: blobs[reference] for reference in sorted(references)}
