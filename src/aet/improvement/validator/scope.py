"""Validate Candidate targets against allowed and protected paths."""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any, Mapping

from ..models.constraint import ImprovementConstraint
from . import ValidationResult


def validate_scope(
    candidate: Mapping[str, Any],
    constraint: ImprovementConstraint,
) -> ValidationResult:
    """Reject scope expansion and protected paths."""
    target_paths = [
        target.get("path", "")
        for target in candidate.get("targets", [])
        if isinstance(target, Mapping)
    ]
    protected = sorted(
        {
            path
            for path in [*target_paths, *candidate.get("deleted_paths", [])]
            if _matches_any(path, constraint.protected_paths)
        }
    )
    if protected:
        if candidate.get("human_approval_required") is True:
            return ValidationResult(
                False,
                "NEEDS_HUMAN_REVIEW",
                "Protected paths require explicit completed human review: "
                + ", ".join(protected),
            )
        return ValidationResult(
            False,
            "REJECTED",
            "Candidate touches protected paths: " + ", ".join(protected),
        )
    outside = sorted(
        path
        for path in target_paths
        if not _matches_any(path, constraint.allowed_paths)
    )
    if outside:
        roots = {path.split("/", 1)[0] for path in outside}
        if len(roots) > 1:
            return ValidationResult(
                False,
                "NEEDS_HUMAN_REVIEW",
                "Candidate expands across multiple unapproved roots: "
                + ", ".join(outside),
            )
        return ValidationResult(
            False,
            "SCOPE_VIOLATION",
            "Candidate targets are outside allowed_paths: " + ", ".join(outside),
        )
    return ValidationResult(True, "VALID", "Candidate stays within allowed scope.")


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in patterns)
