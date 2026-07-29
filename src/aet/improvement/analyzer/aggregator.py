"""Aggregate normalized Findings without weakening their evidence boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, Mapping

from ..models.issue import ImprovementIssue
from .finding_normalizer import normalize_finding


def aggregate_findings(
    findings: Iterable[Mapping[str, Any] | ImprovementIssue],
) -> list[ImprovementIssue]:
    """Merge same behavior + component + evidence pattern and assign stable IDs."""
    grouped: dict[tuple[str, str, str], ImprovementIssue] = {}
    for finding in findings:
        issue = (
            finding
            if isinstance(finding, ImprovementIssue)
            else normalize_finding(finding)
        )
        if issue is None:
            continue
        key = (
            str(issue.impact.get("behavior", issue.category)),
            str(issue.impact.get("component", "unknown")),
            str(issue.impact.get("evidence_pattern", "none")),
        )
        current = grouped.get(key)
        if current is None:
            grouped[key] = issue
            continue
        grouped[key] = replace(
            current,
            finding_refs=sorted(set(current.finding_refs + issue.finding_refs)),
            evidence_refs=sorted(set(current.evidence_refs + issue.evidence_refs)),
        )
    priority_order = {
        "P0_BLOCKING": 0,
        "P1_HIGH": 1,
        "P2_NORMAL": 2,
        "P3_OPPORTUNITY": 3,
    }
    ordered = sorted(
        grouped.values(),
        key=lambda item: (
            priority_order[item.priority],
            item.category,
            item.finding_refs,
        ),
    )[:5]
    return [
        replace(issue, id=f"IMP-{number:03d}")
        for number, issue in enumerate(ordered, start=1)
    ]
