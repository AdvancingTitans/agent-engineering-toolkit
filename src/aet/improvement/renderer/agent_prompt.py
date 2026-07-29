"""Render a bounded coding-Agent task."""

from __future__ import annotations

from ..models.constraint import ImprovementConstraint
from ..models.issue import ImprovementIssue


def render_agent_prompt(
    constraint: ImprovementConstraint,
    issue: ImprovementIssue | None = None,
) -> str:
    """Render the fixed Problem/Evidence/Scope/Verification/Stop structure."""
    problem = issue.title if issue is not None else constraint.objective
    evidence = (
        ", ".join(issue.evidence_refs)
        if issue is not None and issue.evidence_refs
        else "No Evidence reference; stop with INVALID_IMPROVEMENT_INPUT."
    )
    finding_refs = (
        ", ".join(issue.finding_refs)
        if issue is not None
        else "Not supplied"
    )
    stop_conditions = [
        "Stop if any Evidence or Finding reference is missing.",
        "Stop before changing a protected path.",
        "Stop if verification cannot produce valid Proof.",
    ]
    if constraint.action == "investigate":
        stop_conditions.insert(
            0,
            "INVESTIGATION_REQUIRED: do not propose direct code modifications.",
        )
    return "\n".join(
        [
            "# Agent Task",
            "",
            "Candidate status: `PROPOSED`",
            "",
            "## Problem",
            problem,
            "",
            "## Evidence",
            evidence,
            f"Finding refs: {finding_refs}",
            "",
            "## Allowed Scope",
            *[f"- `{path}`" for path in constraint.allowed_paths],
            "",
            "## Forbidden Scope",
            *[f"- `{path}`" for path in constraint.protected_paths],
            *[f"- {item}" for item in constraint.forbidden_behavior],
            "",
            "## Verification",
            *[f"- `{item}`" for item in constraint.verification_requirements],
            "",
            "## Stop Conditions",
            *[f"- {item}" for item in stop_conditions],
            "",
        ]
    )
