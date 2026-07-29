"""Detect bounded cross-Finding failure patterns."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..models.issue import ImprovementIssue
from .finding_normalizer import normalize_finding


def detect_patterns(findings: Iterable[Mapping[str, Any]]) -> list[ImprovementIssue]:
    """Recognize only the explicitly planned tool-failure handling pattern."""
    records = list(findings)
    text = " ".join(
        str(item.get("statement") or item.get("message") or "").lower()
        for item in records
    )
    if not all(token in text for token in ("empty", "timeout", "missing source")):
        return []
    issue = normalize_finding(
        {
            "id": "pattern-tool-failure",
            "type": "error_handling_gap",
            "statement": "Empty result, timeout, and missing source share a tool failure handling gap.",
            "component": "tool",
            "behavior": "tool failure handling gap",
            "evidence_refs": sorted(
                {
                    ref
                    for item in records
                    for ref in item.get("evidence_refs", [])
                    if isinstance(ref, str)
                }
            ),
        }
    )
    return [issue] if issue is not None else []
