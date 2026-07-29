"""Remove no authority from a Candidate while normalizing ordering."""

from __future__ import annotations

from typing import Any, Mapping

from .schema import CandidateSchema


def sanitize_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Return a stable copy after strict validation."""
    CandidateSchema.validate(candidate)
    result = dict(candidate)
    for name in (
        "assumptions",
        "risks",
        "verification_plan",
        "finding_refs",
        "evidence_refs",
        "claim_refs",
        "deleted_paths",
    ):
        if name in result:
            result[name] = sorted(result[name])
    result["targets"] = sorted(
        (dict(target) for target in result["targets"]),
        key=lambda item: (item["path"], item["symbol"]),
    )
    return result
