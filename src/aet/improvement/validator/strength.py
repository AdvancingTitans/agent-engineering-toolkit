"""Prevent Candidate language from overstating plausible causes."""

from __future__ import annotations

from typing import Any, Mapping

from . import ValidationResult


def validate_strength(candidate: Mapping[str, Any]) -> ValidationResult:
    """Reject definitive root-cause language when the cause is not evidenced."""
    status = candidate.get("root_cause_status")
    strategy = str(candidate.get("strategy", "")).lower()
    if status in {"unknown", "plausible"} and "root cause is" in strategy:
        return ValidationResult(
            False,
            "FALSE_CERTAINTY",
            "Use 'Possible cause:' until the root cause is evidenced.",
        )
    if status == "unknown" and candidate.get("targets"):
        return ValidationResult(
            False,
            "INVESTIGATION_REQUIRED",
            "UNKNOWN root cause cannot produce direct modification targets.",
        )
    return ValidationResult(True, "VALID", "Candidate strength matches recorded certainty.")
