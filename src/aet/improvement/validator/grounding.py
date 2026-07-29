"""Validate Candidate references against existing authoritative records."""

from __future__ import annotations

from typing import Any, Mapping

from . import ValidationResult


def validate_grounding(
    candidate: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> ValidationResult:
    """Reject missing Evidence, Finding, or Claim references."""
    inventories = {
        "evidence_refs": _ids(bundle.get("evidence", [])),
        "finding_refs": _ids(bundle.get("findings", bundle.get("claims", []))),
        "claim_refs": _ids(bundle.get("claims", [])),
    }
    for field, available in inventories.items():
        missing = sorted(set(candidate.get(field, [])) - available)
        if missing:
            return ValidationResult(
                False,
                "INVALID_REFERENCE",
                f"{field} do not exist: {', '.join(missing)}",
            )
    return ValidationResult(True, "VALID", "All Candidate references exist.")


def _ids(records: Any) -> set[str]:
    if not isinstance(records, list):
        return set()
    return {
        item["id"]
        for item in records
        if isinstance(item, Mapping)
        and isinstance(item.get("id"), str)
        and item["id"]
    }
