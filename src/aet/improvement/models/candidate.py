"""Improvement Candidate model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CodeTarget:
    path: str
    symbol: str


@dataclass(frozen=True)
class ImprovementCandidate:
    id: str
    constraint_id: str
    strategy: str
    targets: list[CodeTarget]
    assumptions: list[str]
    risks: list[str]
    verification_plan: list[str]

    @property
    def status(self) -> str:
        """Candidates are proposals, never verified facts."""
        return "PROPOSED"
