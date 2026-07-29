"""Normalize existing Findings into deterministic Improvement Issues."""

from __future__ import annotations

from typing import Any, Mapping

from ..models.issue import ImprovementIssue


SUPPORTED_CATEGORIES = frozenset(
    {
        "scope_violation",
        "unsupported_claim",
        "missing_verification",
        "stale_verification",
        "missing_test",
        "error_handling_gap",
        "unknown_root_cause",
    }
)

_TITLES = {
    "scope_violation": "Change exceeds the evidenced scope",
    "unsupported_claim": "Claim is not supported by evidence",
    "missing_verification": "Required verification is missing",
    "stale_verification": "Verification is stale for the current state",
    "missing_test": "Regression coverage is missing",
    "error_handling_gap": "Failure handling is incomplete",
    "unknown_root_cause": "Root cause remains unknown",
}

_PRIORITIES = {
    "scope_violation": "P1_HIGH",
    "unsupported_claim": "P1_HIGH",
    "missing_verification": "P2_NORMAL",
    "stale_verification": "P1_HIGH",
    "missing_test": "P2_NORMAL",
    "error_handling_gap": "P2_NORMAL",
    "unknown_root_cause": "P1_HIGH",
}


def normalize_finding(finding: Mapping[str, Any]) -> ImprovementIssue | None:
    """Convert one Finding-compatible record without creating new evidence."""
    category = _category(finding)
    if category is None:
        return None
    finding_id = _text(finding.get("id"), "finding-unknown")
    evidence_refs = _string_list(finding.get("evidence_refs"))
    limitations = _string_list(finding.get("limitations"))
    root_cause = _text(finding.get("root_cause_status"), "")
    if category == "unknown_root_cause":
        root_cause = "unknown"
    impact = {
        "statement": _text(
            finding.get("statement") or finding.get("claim") or finding.get("message"),
            _TITLES[category],
        ),
        "limitations": limitations,
        "root_cause_status": root_cause or "not_recorded",
        "component": _text(finding.get("component"), "unknown"),
        "behavior": _text(finding.get("behavior"), category),
        "evidence_pattern": ",".join(sorted(evidence_refs)) or "none",
    }
    confidence = "low" if category == "unknown_root_cause" else "high"
    return ImprovementIssue(
        id="IMP-000",
        title=_TITLES[category],
        category=category,
        priority=_PRIORITIES[category],
        finding_refs=[finding_id],
        evidence_refs=evidence_refs,
        confidence=confidence,
        impact=impact,
    )


def _category(finding: Mapping[str, Any]) -> str | None:
    explicit = finding.get("type") or finding.get("category")
    if isinstance(explicit, str) and explicit in SUPPORTED_CATEGORIES:
        return explicit
    status = finding.get("status")
    freshness = finding.get("freshness_status")
    if freshness in {
        "relevant_files_changed",
        "workspace_changed",
        "environment_changed",
        "stale",
    }:
        return "stale_verification"
    if status == "unsupported":
        return "unsupported_claim"
    if status == "unknown" or finding.get("root_cause_status") == "unknown":
        return "unknown_root_cause"
    if status == "conflicted":
        return "missing_verification"
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({item for item in value if isinstance(item, str) and item})


def _text(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value.strip() else default
