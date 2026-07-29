"""Improvement Issue model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImprovementIssue:
    id: str
    title: str
    category: str
    priority: str
    finding_refs: list[str]
    evidence_refs: list[str]
    confidence: str
    impact: dict
