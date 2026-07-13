"""Load a small, non-executable DSL for versioned audit rule packs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import Severity, Status


class RulePackError(ValueError):
    """Raised when a rule pack crosses the safe declarative boundary."""


DETECTOR_TYPES = {
    "local_targets",
    "instruction_size",
    "skill_contract",
    "duplicate_normalized_line",
    "json_script_target_exists",
}


def load_rulepack(path: Path | None = None) -> dict[str, Any]:
    source = path or Path(__file__).with_name("rulepacks_builtin.json")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RulePackError(f"cannot load rule pack: {error}") from error
    _validate(data)
    return data


def rulepack_metadata(rulepack: dict[str, Any]) -> dict[str, Any]:
    _validate(rulepack)
    payload = json.dumps(rulepack, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {
        "version": "aet-safe-dsl/v1",
        "rulepack_id": rulepack["rulepack_id"],
        "rulepack_revision": rulepack["revision"],
        "rulepack_sha256": hashlib.sha256(payload).hexdigest(),
        "detector_runtime": "aet-safe-dsl/v1",
    }


def shadow_diff(official: list[Any], candidate: list[Any], *, official_engine: dict[str, Any], candidate_engine: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compare normalized findings without changing the official audit authority."""
    def key(row: Any) -> tuple[str, str, int | None]:
        evidence = row.evidence[0]
        return row.rule_id, evidence.path, evidence.line

    baseline = {key(row): row.to_dict() for row in official}
    proposed = {key(row): row.to_dict() for row in candidate}
    def state(rows: list[Any]) -> str:
        if any(row.status is Status.FAIL for row in rows):
            return "FAIL"
        if any(row.status is Status.UNKNOWN for row in rows):
            return "UNKNOWN"
        return "PASS"
    added = [proposed[item] for item in sorted(proposed.keys() - baseline.keys())]
    removed = [baseline[item] for item in sorted(baseline.keys() - proposed.keys())]
    changed = []
    for item in sorted(baseline.keys() & proposed.keys()):
        before, after = baseline[item], proposed[item]
        if (before["status"], before["severity"], before["evidence"]) != (after["status"], after["severity"], after["evidence"]):
            changed.append({"before": before, "after": after})
    return {
        "schema_version": "audit-shadow/v1",
        "report_kind": "audit_shadow",
        "generated_at": datetime.now(UTC).isoformat(),
        "official_status": state(official),
        "shadow_status": state(candidate),
        "official_engine": official_engine,
        "candidate_engine": candidate_engine,
        "workspace_snapshot": snapshot,
        "affects_official_output": False,
        "affects_official_exit_code": False,
        "diff": {"added_findings": added, "removed_findings": removed, "changed_findings": changed},
    }


def _validate(data: Any) -> None:
    if not isinstance(data, dict) or data.get("schema_version") != "audit-rulepack/v1":
        raise RulePackError("rule pack must use audit-rulepack/v1")
    if not isinstance(data.get("rulepack_id"), str) or not data["rulepack_id"]:
        raise RulePackError("rulepack_id must be non-empty")
    if not isinstance(data.get("revision"), int) or data["revision"] < 1:
        raise RulePackError("revision must be a positive integer")
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise RulePackError("rules must be a non-empty array")
    identifiers: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise RulePackError("each rule must be an object")
        identifier = rule.get("rule_id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise RulePackError("rule_id values must be unique and non-empty")
        identifiers.add(identifier)
        detector = rule.get("detector")
        if not isinstance(detector, dict) or detector.get("type") not in DETECTOR_TYPES:
            raise RulePackError(f"rule {identifier} uses a detector outside the safe DSL")
        if set(detector) & {"module", "python", "shell", "command", "exec", "network"}:
            raise RulePackError(f"rule {identifier} contains executable detector fields")
        files = detector.get("files", [])
        if not isinstance(files, list) or any(not isinstance(item, str) or not item or Path(item).is_absolute() or ".." in Path(item).parts for item in files):
            raise RulePackError(f"rule {identifier} contains a file selector outside the audit root")
        match_rule_id = detector.get("match_rule_id")
        if match_rule_id is not None and (not isinstance(match_rule_id, str) or not match_rule_id):
            raise RulePackError(f"rule {identifier} has an invalid detector match_rule_id")
        target_kinds = rule.get("target_kinds")
        if not isinstance(target_kinds, list) or not target_kinds or any(item not in {"instruction", "skill", "repository"} for item in target_kinds):
            raise RulePackError(f"rule {identifier} has invalid target_kinds")
        result = rule.get("result", {})
        if not isinstance(result, dict) or not isinstance(result.get("claim"), str) or not isinstance(result.get("remediation"), str):
            raise RulePackError(f"rule {identifier} must declare claim and remediation")
        try:
            Status(result.get("status"))
            Severity(result.get("severity"))
        except ValueError as error:
            raise RulePackError(f"rule {identifier} has invalid result semantics") from error
