"""Deterministic relevant-file freshness for Quick proof receipts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..evidence import evidence_receipt, workspace_snapshot
from .common import sha256_file
from .proof import _environment_binding


FRESH_STATES = (
    "EXACT_MATCH",
    "RELEVANT_FILES_MATCH",
    "HEAD_CHANGED_RELEVANT_FILES_MATCH",
    "RELEVANT_FILES_CHANGED",
    "ARTIFACT_CHANGED",
    "ENVIRONMENT_CHANGED",
    "UNKNOWN",
)


def quick_fresh(proof_path: Path) -> dict[str, Any]:
    """Compare a Quick proof or legacy canonical report with the live workspace."""
    try:
        raw = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return _result("UNKNOWN", [f"cannot read proof: {error}"])
    if raw.get("schema_version", raw.get("schema")) != "aet-proof-receipt/v2":
        legacy = raw if raw.get("report_kind") == "evidence_receipt" else evidence_receipt(proof_path)
        freshness = legacy.get("freshness", {})
        state = "EXACT_MATCH" if freshness.get("status") == "PASS" else "UNKNOWN"
        return _result(state, [freshness.get("state") or freshness.get("reason") or "legacy proof freshness is unavailable"], legacy=legacy)

    binding = raw.get("binding")
    if not isinstance(binding, dict):
        return _result("UNKNOWN", ["proof binding is missing"])
    if binding.get("status") == "UNKNOWN":
        return _result("UNKNOWN", ["proof contains an unavailable required binding"])
    recorded_snapshot = binding.get("workspace_snapshot")
    if not isinstance(recorded_snapshot, dict):
        return _result("UNKNOWN", ["workspace snapshot is missing"])
    root_value = recorded_snapshot.get("root") or raw.get("command", {}).get("cwd")
    if not isinstance(root_value, str):
        return _result("UNKNOWN", ["workspace root is missing"])
    root = Path(root_value)
    if not root.is_dir():
        return _result("UNKNOWN", ["recorded workspace is unavailable"])

    reasons: list[str] = []
    artifact_changes, artifact_unknown = _changed_artifacts(root, raw.get("artifacts", []))
    if artifact_changes:
        return _result("ARTIFACT_CHANGED", artifact_changes)
    if artifact_unknown:
        return _result("UNKNOWN", artifact_unknown)
    recorded_environment = binding.get("environment")
    if (
        not isinstance(recorded_environment, dict)
        or recorded_environment.get("selected_executable") is None
        or any(
            not isinstance(item, dict) or item.get("status") != "PASS"
            for item in recorded_environment.get("explicit_environment", [])
        )
    ):
        return _result("UNKNOWN", ["recorded runtime or environment binding is unavailable"])
    environment_names = [
        item.get("name")
        for item in recorded_environment.get("explicit_environment", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ] if isinstance(recorded_environment, dict) else []
    if recorded_environment != _environment_binding(
        root,
        argv=raw.get("command", {}).get("argv", []),
        environment_names=environment_names,
    ):
        return _result("ENVIRONMENT_CHANGED", ["recorded runtime or dependency lockfiles changed"])
    relevant_changes, relevant_unknown = _changed_relevant(root, binding.get("relevant_paths", []))
    if relevant_changes:
        return _result("RELEVANT_FILES_CHANGED", relevant_changes)
    if relevant_unknown:
        return _result("UNKNOWN", relevant_unknown)

    current = workspace_snapshot(root)
    recorded_head = recorded_snapshot.get("head_sha")
    current_head = current.get("head_sha")
    if recorded_snapshot.get("digest") == current.get("digest"):
        return _result("EXACT_MATCH", ["workspace snapshot is an exact match"])
    if recorded_head != current_head:
        return _result("HEAD_CHANGED_RELEVANT_FILES_MATCH", ["Git HEAD changed, but all declared relevant files still match"])
    if binding.get("relevant_paths"):
        return _result("RELEVANT_FILES_MATCH", ["unrelated workspace state changed; declared relevant files still match"])
    reasons.append("workspace changed and the proof declares no relevant files")
    return _result("UNKNOWN", reasons)


def _changed_relevant(root: Path, records: Any) -> tuple[list[str], list[str]]:
    if not isinstance(records, list):
        return [], ["relevant path binding is invalid"]
    changed: list[str] = []
    unknown: list[str] = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            unknown.append("relevant path binding is invalid")
            continue
        path = (root / record["path"]).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            unknown.append(f"relevant path escaped the workspace: {record['path']}")
            continue
        if record.get("status") != "PASS" or not path.is_file() or path.is_symlink():
            unknown.append(f"relevant file is unavailable: {record['path']}")
        elif sha256_file(path) != record.get("sha256"):
            changed.append(f"relevant file changed: {record['path']}")
    return changed, unknown


def _changed_artifacts(root: Path, records: Any) -> tuple[list[str], list[str]]:
    if not isinstance(records, list):
        return [], ["artifact binding is invalid"]
    changed: list[str] = []
    unknown: list[str] = []
    for record in records:
        if not isinstance(record, dict) or not record.get("requested_path"):
            unknown.append("artifact binding is invalid")
            continue
        if record.get("status") != "PASS" or not record.get("sha256"):
            unknown.append(f"artifact binding is unavailable: {record['requested_path']}")
            continue
        path = (root / record["requested_path"]).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            unknown.append(f"artifact escaped the workspace: {record['requested_path']}")
            continue
        if not path.is_file() or path.is_symlink():
            changed.append(f"artifact changed: {record['requested_path']}")
        elif sha256_file(path) != record["sha256"]:
            changed.append(f"artifact changed: {record['requested_path']}")
    return changed, unknown


def _result(state: str, reasons: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "schema": "aet-quick-fresh/v1",
        "report_kind": "quick_fresh",
        "authoritative_status": "PASS" if state in {"EXACT_MATCH", "RELEVANT_FILES_MATCH", "HEAD_CHANGED_RELEVANT_FILES_MATCH"} else "FAIL" if state in {"RELEVANT_FILES_CHANGED", "ARTIFACT_CHANGED", "ENVIRONMENT_CHANGED"} else "UNKNOWN",
        "freshness_state": state,
        "reasons": reasons,
        "network_calls": 0,
        "llm_calls": 0,
        "writes": 0,
        "stop_after": "report_emitted",
        **extra,
    }
