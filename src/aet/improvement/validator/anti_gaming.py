"""Detect planned anti-gaming violations."""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any, Mapping

from . import ValidationResult


def detect_gaming(candidate: Mapping[str, Any]) -> ValidationResult:
    """Reject test deletion, grader changes, threshold lowering, and hiding."""
    deleted = candidate.get("deleted_paths", [])
    if any(fnmatchcase(path, "tests/**") for path in deleted):
        return ValidationResult(
            False,
            "ANTI_GAMING_FAILURE",
            "Candidate deletes tests.",
        )
    targets = [
        target.get("path", "")
        for target in candidate.get("targets", [])
        if isinstance(target, Mapping)
    ]
    if any(
        fnmatchcase(path, pattern)
        for path in targets
        for pattern in ("grader/**", "eval/**", "fixtures/**", "tests/evals/**")
    ):
        return ValidationResult(
            False,
            "ANTI_GAMING_FAILURE",
            "Candidate modifies grader, evaluation, or fixture truth.",
        )
    text = " ".join(
        [
            str(candidate.get("strategy", "")),
            *candidate.get("assumptions", []),
            *candidate.get("risks", []),
        ]
    ).lower()
    for phrase in (
        "lower threshold",
        "hide failure",
        "modify grader",
        "delete test",
        "change fixture truth",
    ):
        if phrase in text:
            return ValidationResult(
                False,
                "ANTI_GAMING_FAILURE",
                f"Candidate contains forbidden strategy: {phrase}",
            )
    return ValidationResult(True, "VALID", "No anti-gaming violation detected.")
