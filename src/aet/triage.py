"""Transparent finding prioritization; never a release gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TriageError(ValueError):
    """Raised when an input cannot be used as a finding report."""


def triage_report(report_path: Path, output: Path) -> dict[str, Any]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TriageError(f"cannot read report: {error}") from error
    findings = report.get("findings") if isinstance(report, dict) else None
    if not isinstance(findings, list):
        raise TriageError("report must contain a findings array")
    items = [_priority(item) for item in findings if isinstance(item, dict)]
    items.sort(key=lambda item: (-item["score"], item["rule_id"]))
    data = {"report_kind": "finding_triage", "model_version": "1.0.0", "gate_policy": "Scores only order work; statuses remain authoritative.", "items": items}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def _priority(finding: dict[str, Any]) -> dict[str, Any]:
    severity = {"ERROR": 40, "WARN": 20, "INFO": 5}.get(finding.get("severity"), 0)
    evidence = finding.get("evidence") if isinstance(finding.get("evidence"), list) else []
    directness = 25 if any(isinstance(item, dict) and item.get("line") and item.get("detail") for item in evidence) else 20 if any(isinstance(item, dict) and item.get("line") for item in evidence) else 10 if evidence else 0
    radius = min(20, len({item.get("path") for item in evidence if isinstance(item, dict) and item.get("path")}) * 10)
    # ponytail: recency/ownership is intentionally zero until a source adapter provides it; do not invent precision.
    factors = {"severity": severity, "evidence_directness": directness, "impact_radius": radius, "recency_ownership": 0}
    return {"rule_id": finding.get("rule_id", "UNKNOWN"), "status": finding.get("status", "UNKNOWN"), "claim": finding.get("claim", ""), "score": sum(factors.values()), "factors": factors, "model_version": "1.0.0"}
