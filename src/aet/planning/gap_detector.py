"""Deterministic Planning gap and conflict detection."""

from __future__ import annotations

from typing import Any

from .errors import PlanningErrorCode
from .models import OmissionSummary, PlanningGap, SourceSite


def detect_planning_gaps(
    *,
    has_bundle: bool,
    allowed_scope_resolved: bool,
    relevant_claims: list[dict[str, Any]],
    relevant_evidence: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    source_sites: list[SourceSite],
    verification_requirements: list[str],
    omitted: OmissionSummary,
) -> list[PlanningGap]:
    gaps: list[PlanningGap] = []

    def add(code: str, message: str, *, critical: bool, refs: list[str] | None = None) -> None:
        gaps.append(
            PlanningGap(
                gap_id=f"GAP-{len(gaps) + 1:03d}",
                code=code,
                severity="ERROR" if critical else "WARNING",
                message=message,
                critical=critical,
                reference_ids=refs or [],
            )
        )

    if not has_bundle:
        add(
            PlanningErrorCode.EVIDENCE_REQUIRED.value,
            "No validated Portable Evidence Bundle was supplied; Source-only localization cannot establish a READY plan.",
            critical=True,
        )
    if not allowed_scope_resolved:
        add(
            PlanningErrorCode.EVIDENCE_REQUIRED.value,
            "Allowed change scope is unresolved.",
            critical=True,
        )
    if has_bundle and not relevant_claims and not relevant_evidence:
        add(
            PlanningErrorCode.EVIDENCE_REQUIRED.value,
            "The supplied Bundle does not contain evidence relevant to the request.",
            critical=True,
        )
    for site in source_sites:
        if site.read_status == "STALE":
            add(
                PlanningErrorCode.SOURCE_STALE.value,
                f"Source reference is stale: {site.path}",
                critical=True,
                refs=[site.source_id],
            )
        elif site.read_status == "MISSING":
            add(
                PlanningErrorCode.SOURCE_MISSING.value,
                f"Source reference is missing: {site.path}",
                critical=True,
                refs=[site.source_id],
            )
        elif site.read_status == "UNSUPPORTED":
            add(
                PlanningErrorCode.UNSUPPORTED_LANGUAGE.value,
                f"Source reference is unsupported: {site.path}",
                critical=False,
                refs=[site.source_id],
            )
    for conflict in conflicts:
        if str(conflict.get("resolution_status", "unresolved")).lower() == "unresolved":
            add(
                PlanningErrorCode.CONFLICT_UNRESOLVED.value,
                "Planning Context retains an unresolved conflict.",
                critical=str(conflict.get("severity", conflict.get("priority", ""))).lower()
                in {"critical", "high", "error"},
                refs=[str(conflict.get("id", ""))],
            )
    if not verification_requirements:
        add(
            PlanningErrorCode.EVIDENCE_REQUIRED.value,
            "No reproducible verification requirement is available.",
            critical=True,
        )
    if omitted.total:
        add(
            PlanningErrorCode.BUDGET_EXHAUSTED.value,
            "Planning Context was truncated by an explicit budget.",
            critical=False,
        )
    return gaps


def blocks_ready_status(gap: PlanningGap) -> bool:
    return gap.critical
