"""Adapters from existing AET evidence contracts into one bounded RiskContext."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from aet.bundle import BundleError, validate_bundle
from aet.run_normalization import NormalizationError, load_normalized_run, normalize_run

from .errors import RiskInputError
from .models import Diagnostic, RiskContext
from .policy import RiskPolicy
from .schemas import canonical_json


def load_context(
    run_path: str | Path,
    intent_path: str | Path,
    policy: RiskPolicy,
    *,
    bundle_path: str | Path | None = None,
) -> RiskContext:
    normalized = _load_run(Path(run_path))
    intent = _load_object(Path(intent_path), "intent")
    _validate_intent(intent)
    evidence = _load_evidence(Path(bundle_path)) if bundle_path is not None else ()
    return build_context(normalized, intent, policy, evidence=evidence)


def build_context(
    normalized: Mapping[str, Any],
    intent: Mapping[str, Any],
    policy: RiskPolicy,
    *,
    evidence: tuple[Mapping[str, Any], ...] = (),
) -> RiskContext:
    manifest = normalized.get("manifest")
    records = normalized.get("records")
    raw_diagnostics = normalized.get("diagnostics")
    if not isinstance(manifest, Mapping) or not isinstance(records, list) or not isinstance(raw_diagnostics, list):
        raise RiskInputError("normalized run must contain manifest, records, and diagnostics")
    run_group_id = manifest.get("run_group_id")
    generation_id = manifest.get("generation_id")
    if not isinstance(run_group_id, str) or not run_group_id:
        raise RiskInputError("normalized run_group_id is required")
    if not isinstance(generation_id, str) or not generation_id:
        raise RiskInputError("normalized generation_id is required")
    groups = {
        item.get("source_identity", {}).get("run_group_id")
        for item in records
        if isinstance(item, Mapping) and isinstance(item.get("source_identity"), Mapping)
    }
    groups.discard(None)
    if groups != {run_group_id}:
        raise RiskInputError("records and manifest expose conflicting run groups")
    diagnostics = tuple(_diagnostic(item) for item in raw_diagnostics if isinstance(item, Mapping))
    task_digest = hashlib.sha256(canonical_json(intent).encode("utf-8")).hexdigest()[:16]
    return RiskContext(
        run_group_id=run_group_id,
        generation_id=generation_id,
        task_id=f"task-{task_digest}",
        records=tuple(item for item in records if isinstance(item, Mapping)),
        intent=intent,
        policy=policy,
        evidence=evidence,
        diagnostics=diagnostics,
    )


def _load_run(path: Path) -> dict[str, Any]:
    try:
        if path.is_dir():
            return load_normalized_run(path)
        if path.is_symlink() or not path.is_file():
            raise RiskInputError("run must be a regular JSONL file or normalized-run directory")
        first = next((line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()), "")
        if not first:
            raise RiskInputError("run input is empty")
        first_value = json.loads(first)
        if not isinstance(first_value, dict):
            raise RiskInputError("run JSONL records must be objects")
        if first_value.get("schema_version") == "canonical-run-record/1.0":
            records = _load_jsonl(path)
            groups = {
                item.get("source_identity", {}).get("run_group_id")
                for item in records
                if isinstance(item.get("source_identity"), dict)
            }
            groups.discard(None)
            if len(groups) != 1:
                raise RiskInputError("canonical JSONL must contain exactly one run group")
            return {
                "manifest": {
                    "source_type": "canonical-jsonl",
                    "run_group_id": next(iter(groups)),
                    "generation_id": "generation-0",
                    "partial": False,
                },
                "records": records,
                "diagnostics": [],
            }
        source = "claude-code" if first_value.get("type") == "system" else "codex"
        return normalize_run(source, path, generation_id="generation-0")
    except (OSError, UnicodeError, json.JSONDecodeError, NormalizationError) as error:
        if isinstance(error, RiskInputError):
            raise
        raise RiskInputError(f"cannot load run: {error}") from error


def _load_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RiskInputError(f"{label} must be a regular non-symbolic-link file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RiskInputError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise RiskInputError(f"{label} must contain one object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RiskInputError(f"run record {number} must be an object")
        values.append(value)
    return values


def _validate_intent(intent: Mapping[str, Any]) -> None:
    if intent.get("schema_version") != "aet-intent/v2":
        raise RiskInputError("intent must use aet-intent/v2")
    required = {"goal", "constraints", "allowed_surfaces", "uncertain_terms", "source_refs"}
    if not required.issubset(intent):
        raise RiskInputError("intent v2 is incomplete")
    goal = intent.get("goal")
    if not isinstance(goal, Mapping) or goal.get("source_type") not in {"explicit_user", "explicit_project"}:
        raise RiskInputError("intent goal must have explicit authority")


def _load_evidence(path: Path) -> tuple[Mapping[str, Any], ...]:
    try:
        value = validate_bundle(path) if path.is_dir() else _load_object(path, "bundle")
    except BundleError as error:
        raise RiskInputError(f"cannot validate bundle: {error}") from error
    records: list[Mapping[str, Any]] = []
    for key in ("evidence", "claims", "sources", "proofs"):
        items = value.get(key, ())
        if isinstance(items, list):
            records.extend(item for item in items if isinstance(item, Mapping))
    return tuple(records)


def _diagnostic(value: Mapping[str, Any]) -> Diagnostic:
    severity = str(value.get("severity", "warning"))
    if severity not in {"info", "warning", "error"}:
        severity = "warning"
    return Diagnostic(
        code=str(value.get("code", "unknown_normalizer_diagnostic")),
        message=str(value.get("message", "Normalizer diagnostic.")),
        severity=severity,
    )


__all__ = ["build_context", "load_context"]
