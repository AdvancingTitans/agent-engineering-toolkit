"""Improvement Outcome model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImprovementOutcome:
    issue_id: str
    candidate_id: str
    status: str
    before_metrics: dict
    after_metrics: dict
    proof_refs: list[str]
