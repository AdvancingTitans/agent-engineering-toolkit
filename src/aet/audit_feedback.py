"""Reproducible, Evidence Only feedback for audit findings."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .discovery import discover_assets
from .rules import run_rules


class AuditFeedbackError(ValueError):
    """Raised when subjective feedback lacks a reproducible local fixture."""


OUTCOMES = {
    "false-positive": "FALSE_POSITIVE",
    "false-negative": "FALSE_NEGATIVE",
    "wrong-status": "WRONG_STATUS",
    "wrong-severity": "WRONG_SEVERITY",
    "wrong-evidence-location": "WRONG_EVIDENCE_LOCATION",
    "incomplete-remediation": "INCOMPLETE_REMEDIATION",
    "duplicate-finding": "DUPLICATE_FINDING",
    "non-deterministic": "NON_DETERMINISTIC",
    "performance-regression": "PERFORMANCE_REGRESSION",
    "policy-exception-required": "POLICY_EXCEPTION_REQUIRED",
}


def record_audit_feedback(*, report: Path, finding: str, outcome: str, reason_code: str, fixture: Path, output: Path) -> dict[str, Any]:
    if outcome not in OUTCOMES:
        raise AuditFeedbackError(f"unsupported audit feedback outcome: {outcome}")
    if not reason_code or not reason_code.replace("-", "_").isupper():
        raise AuditFeedbackError("reason code must be a non-empty uppercase code")
    source = _json(report)
    if source.get("report_kind") != "audit" or not isinstance(source.get("findings"), list):
        raise AuditFeedbackError("feedback source must be an AET audit report")
    expected_path = fixture / "expected.json"
    expected = _json(expected_path)
    must_emit = expected.get("must_emit")
    must_not_emit = expected.get("must_not_emit", [])
    if not isinstance(must_emit, list) or not isinstance(must_not_emit, list):
        raise AuditFeedbackError("fixture expected.json must declare must_emit and optional must_not_emit arrays")
    expected_ids = {row.get("rule_id") for row in must_emit if isinstance(row, dict)}
    if finding not in expected_ids and outcome != "false-positive":
        raise AuditFeedbackError("fixture expected result does not bind the feedback finding")
    reported_ids = {row.get("rule_id") for row in source["findings"] if isinstance(row, dict)}
    started = time.perf_counter()
    observed = run_rules(fixture, discover_assets(fixture))
    elapsed_ms = (time.perf_counter() - started) * 1000
    observed_ids = {row.rule_id for row in observed}
    expected_row = next((row for row in must_emit if isinstance(row, dict) and row.get("rule_id") == finding), None)
    forbidden_row = next((row for row in must_not_emit if isinstance(row, dict) and row.get("rule_id") == finding), None)
    observed_row = next((row for row in observed if row.rule_id == finding), None)
    if outcome == "false-negative":
        reproduced = finding not in reported_ids and finding not in observed_ids
    elif outcome == "false-positive":
        reproduced = forbidden_row is not None and finding in reported_ids and observed_row is not None
    elif outcome == "wrong-status":
        reproduced = expected_row is not None and observed_row is not None and expected_row.get("status") != observed_row.status.value
    elif outcome == "wrong-severity":
        reproduced = expected_row is not None and observed_row is not None and expected_row.get("severity") != observed_row.severity.value
    elif outcome == "wrong-evidence-location":
        reproduced = expected_row is not None and observed_row is not None and expected_row.get("evidence_path") != observed_row.evidence[0].path
    elif outcome == "incomplete-remediation":
        reproduced = expected_row is not None and expected_row.get("remediation_required") is True and observed_row is not None and not observed_row.remediation.strip()
    elif outcome == "duplicate-finding":
        reproduced = sum(row.rule_id == finding for row in observed) > 1
    elif outcome == "non-deterministic":
        repeated = run_rules(fixture, discover_assets(fixture))
        reproduced = [row.to_dict() for row in observed] != [row.to_dict() for row in repeated]
    elif outcome == "performance-regression":
        maximum = expected.get("max_runtime_ms")
        if not isinstance(maximum, (int, float)) or isinstance(maximum, bool) or maximum < 0:
            raise AuditFeedbackError("performance feedback requires expected.max_runtime_ms")
        reproduced = elapsed_ms > float(maximum)
    elif outcome == "policy-exception-required":
        reproduced = forbidden_row is not None and observed_row is not None and bool(forbidden_row.get("policy_exception"))
    else:
        reproduced = False
    if not reproduced:
        raise AuditFeedbackError("the supplied fixture does not reproduce the reported audit deviation")
    fixture_hash = _tree_hash(fixture)
    primary = OUTCOMES[outcome]
    record = {
        "schema_version": "audit-feedback/v1",
        "report_kind": "audit_feedback",
        "feedback_id": f"AFB-{fixture_hash[:12].upper()}",
        "recorded_at": datetime.now(UTC).isoformat(),
        "finding": finding,
        "outcome": outcome,
        "reason_codes": [primary, reason_code],
        "deviations": [primary, reason_code],
        "source_report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "fixture_sha256": fixture_hash,
        "fixture": str(fixture.resolve()),
        "expected_sha256": hashlib.sha256(expected_path.read_bytes()).hexdigest(),
        "reproduced": True,
        "adoption_grade": True,
        "privacy": {"profile": "evidence-only", "raw_transcript_retained": False, "human_text_retained": False},
    }
    _write(output, record)
    return record


def _tree_hash(root: Path) -> str:
    if not root.is_dir():
        raise AuditFeedbackError(f"fixture does not exist: {root}")
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditFeedbackError(f"invalid local JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise AuditFeedbackError(f"JSON must contain an object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)
