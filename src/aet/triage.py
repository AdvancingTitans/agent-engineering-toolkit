"""Transparent finding prioritization; never a release gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TriageError(ValueError):
    """Raised when an input cannot be used as a finding report."""


def triage_report(report_path: Path, output: Path, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TriageError(f"cannot read report: {error}") from error
    findings = report.get("findings") if isinstance(report, dict) else None
    if not isinstance(findings, list):
        raise TriageError("report must contain a findings array")
    items = [_priority(item, policy) for item in findings if isinstance(item, dict)]
    items.sort(key=lambda item: (-item["score"], item["rule_id"]))
    data = {"report_kind": "finding_triage", "model_version": "1.0.0", "gate_policy": "Scores only order work; statuses remain authoritative.", "items": items}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def _priority(finding: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    weights = (policy or {}).get("weights", {})
    severity_weight = float(weights.get("severity", 1))
    severity = {"ERROR": 40, "WARN": 20, "INFO": 5}.get(finding.get("severity"), 0) * severity_weight
    evidence = finding.get("evidence") if isinstance(finding.get("evidence"), list) else []
    directness = 25 if any(isinstance(item, dict) and item.get("line") and item.get("detail") for item in evidence) else 20 if any(isinstance(item, dict) and item.get("line") for item in evidence) else 10 if evidence else 0
    radius = min(20, len({item.get("path") for item in evidence if isinstance(item, dict) and item.get("path")}) * 10)
    # ponytail: recency/ownership is intentionally zero until a source adapter provides it; do not invent precision.
    critical_paths = (policy or {}).get("critical_paths", [])
    paths = [str(item.get("path", "")) for item in evidence if isinstance(item, dict)]
    critical = float(weights.get("critical_path", 0)) if any(any(path == pattern.rstrip("/**") or (pattern.endswith("/**") and path.startswith(pattern[:-3].rstrip("/") + "/")) for pattern in critical_paths) for path in paths) else 0
    factors = {"severity": severity, "evidence_directness": directness, "impact_radius": radius, "critical_path": critical, "recency_ownership": 0}
    return {"rule_id": finding.get("rule_id", "UNKNOWN"), "status": finding.get("status", "UNKNOWN"), "claim": finding.get("claim", ""), "score": sum(factors.values()), "factors": factors, "model_version": "1.0.0"}
