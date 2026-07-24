"""Bounded deterministic preflight for the /aet-check Skill."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_audit_config
from ..discovery import discover_assets
from ..evidence import workspace_snapshot
from ..reporters import report_data
from ..rulepacks import load_rulepack, rulepack_metadata
from ..rules import run_rules


CHECK_BUDGET = {
    "wall_time_seconds": 30,
    "llm_calls": 2,
    "tool_calls": 6,
    "remote_calls": 0,
    "expensive_calls": 1,
    "findings": 5,
    "investigation_rounds": 3,
}


def quick_check(root: Path, *, max_findings: int = 5) -> dict[str, Any]:
    """Return facts for host investigation without executing project code."""
    root = root.resolve()
    config = load_audit_config(root, None)
    assets = discover_assets(root, config)
    rulepack = load_rulepack(None)
    findings = run_rules(root, assets, rulepack=rulepack)
    truncated = len(findings) > max_findings
    selected = findings[:max_findings]
    report = report_data(
        root,
        assets,
        selected,
        scope={"root": str(root), "config": config.to_dict()},
        workspace_snapshot=workspace_snapshot(root),
        audit_engine=rulepack_metadata(rulepack),
    )
    report.update({
        "schema": "aet-quick-check/v1",
        "report_kind": "quick_check_preflight",
        "authoritative_status_set": ["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"],
        "budget": CHECK_BUDGET,
        "bounded_result": {
            "status": "BOUNDED_RESULT" if truncated else "COMPLETE_WITHIN_BOUNDARY",
            "eligible_findings": len(findings),
            "reported_findings": len(selected),
            "uninspected_surfaces": [
                "complete Git history",
                "project code execution",
                "remote project systems",
                "unrelated source files",
            ],
        },
        "host_investigation": {
            "max_hypotheses": 3,
            "must_check_counter_explanation": True,
            "may_create_investigated_findings": True,
            "may_change_authoritative_findings": False,
            "stop_after": "report_emitted",
        },
    })
    return report
