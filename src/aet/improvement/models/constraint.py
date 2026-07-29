"""Improvement Constraint model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImprovementConstraint:
    id: str
    issue_id: str
    objective: str
    required_behavior: list[str]
    forbidden_behavior: list[str]
    allowed_paths: list[str]
    protected_paths: list[str]
    verification_requirements: list[str]

    @property
    def action(self) -> str:
        """Expose the planned UNKNOWN behavior without changing the schema."""
        if "INVESTIGATION_REQUIRED" in self.required_behavior:
            return "investigate"
        if "NEEDS_HUMAN_REVIEW" in self.required_behavior:
            return "human_review"
        return "change"
