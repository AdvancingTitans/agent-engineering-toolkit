"""Build Improvement Constraints from normalized Issues."""

from __future__ import annotations

from ..models.constraint import ImprovementConstraint
from ..models.issue import ImprovementIssue
from .rules import PROTECTED_PATHS, RULES


def build_constraint(
    issue: ImprovementIssue,
    *,
    allowed_paths: list[str] | None = None,
    verification_requirements: list[str] | None = None,
) -> ImprovementConstraint:
    """Generate one bounded deterministic Constraint."""
    rule = RULES[issue.category]
    paths = sorted(set(allowed_paths or []))
    required = list(rule.required_behavior)
    if not paths and issue.category != "unknown_root_cause":
        required.append("NEEDS_HUMAN_REVIEW")
    verification = sorted(set(verification_requirements or []))
    if not verification:
        verification = (
            ["NOT_ACTIONABLE: verification requirement is missing."]
            if issue.category == "missing_verification"
            else ["Provide a reproducible verification command and valid Proof."]
        )
    number = issue.id.removeprefix("IMP-")
    return ImprovementConstraint(
        id=f"IC-{number}",
        issue_id=issue.id,
        objective=rule.objective,
        required_behavior=required,
        forbidden_behavior=list(rule.forbidden_behavior),
        allowed_paths=paths,
        protected_paths=list(PROTECTED_PATHS),
        verification_requirements=verification,
    )
