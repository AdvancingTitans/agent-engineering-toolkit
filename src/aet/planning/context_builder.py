"""Build bounded Planning Context from Bundle, Atlas, and current source."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from aet.improvement.constraint.rules import PROTECTED_PATHS

from .atlas_adapter import AtlasSelection, select_planning_nodes
from .bundle_loader import PlanningBundleView, load_planning_bundle
from .errors import PlanningError, PlanningErrorCode
from .gap_detector import detect_planning_gaps
from .models import (
    OmissionSummary,
    PlanningBudgets,
    PlanningConstraints,
    PlanningContext,
    PlanningRequest,
)
from .policy import path_matches
from .relevance import RankedReference, rank_references
from .source_navigator import SourceNavigator


def build_planning_context(
    request: PlanningRequest,
    *,
    workspace: Path,
    bundle_path: Path | None = None,
    atlas_path: Path | None = None,
    budgets: PlanningBudgets | None = None,
) -> PlanningContext:
    """Create one deterministic, read-only Context for a Host Planner."""
    root = Path(workspace).resolve(strict=True)
    selected_budgets = budgets or request.budgets
    bundle = load_planning_bundle(bundle_path) if bundle_path is not None else None
    atlas: AtlasSelection | None = None
    diagnostics: list[dict[str, Any]] = []
    if atlas_path is not None:
        if bundle_path is None or bundle is None:
            raise PlanningError(
                PlanningErrorCode.INVALID_ATLAS,
                "Atlas validation requires its source Bundle",
            )
        atlas = select_planning_nodes(
            atlas_path,
            bundle_path,
            request,
            max_nodes=selected_budgets.max_nodes,
            max_depth=selected_budgets.max_depth,
        )
        if atlas.bundle_identity != bundle.bundle_id:
            raise PlanningError(
                PlanningErrorCode.IDENTITY_MISMATCH,
                "Atlas and Bundle identities differ",
            )
        if request.atlas_identity and request.atlas_identity != atlas.atlas_identity:
            raise PlanningError(
                PlanningErrorCode.IDENTITY_MISMATCH,
                "requested Atlas identity differs from the validated Atlas",
            )
    elif request.atlas_identity:
        diagnostics.append(
            {
                "code": PlanningErrorCode.INVALID_ATLAS.value,
                "severity": "WARNING",
                "message": "Request names an Atlas identity but no Atlas was supplied.",
            }
        )
    if bundle is not None and request.bundle_identity and request.bundle_identity not in {
        bundle.bundle_id,
        bundle.content_hash,
    }:
        raise PlanningError(
            PlanningErrorCode.IDENTITY_MISMATCH,
            "requested Bundle identity differs from the validated Bundle",
        )
    effective_request = replace(
        request,
        bundle_identity=(bundle.content_hash if bundle is not None else None),
        atlas_identity=(atlas.atlas_identity if atlas is not None else None),
    )

    constraints = _resolve_constraints(effective_request, bundle)
    ranked = (
        rank_references(
            effective_request,
            bundle,
            atlas.nodes if atlas is not None else (),
        )
        if bundle is not None
        else []
    )
    selected = ranked[: selected_budgets.max_nodes]
    omitted_nodes = max(0, len(ranked) - len(selected))
    if atlas is not None:
        omitted_nodes += atlas.omitted_nodes
    selected_ids = {item.reference_id for item in selected}
    claims = _selected_records(selected, "claim")
    evidence = _selected_records(selected, "evidence")
    conflicts = _selected_records(selected, "conflict")
    sources = _selected_records(selected, "source")
    if bundle is not None:
        evidence_ids = {
            reference
            for claim in claims
            for reference in [
                *claim.get("evidence_refs", []),
                *claim.get("counter_evidence_refs", []),
            ]
            if isinstance(reference, str)
        }
        evidence.extend(
            dict(item)
            for item in bundle.evidence
            if item["id"] in evidence_ids and item["id"] not in selected_ids
        )
        evidence.sort(key=lambda item: str(item.get("id", "")))
    counter_ids = {
        reference
        for claim in claims
        for reference in claim.get("counter_evidence_refs", [])
        if isinstance(reference, str)
    }
    counter = [item for item in evidence if item.get("id") in counter_ids]
    relevant_evidence = [item for item in evidence if item.get("id") not in counter_ids]
    unknowns = [
        *[item for item in claims if item.get("status") == "unknown"],
        *[
            item
            for item in evidence
            if item.get("freshness", {}).get("status") == "unknown"
        ],
    ]

    seeds = _source_seeds(
        effective_request,
        bundle,
        sources,
        [*relevant_evidence, *counter],
    )
    navigator = SourceNavigator(
        root,
        constraints,
        max_file_bytes=selected_budgets.max_source_bytes,
    )
    source_sites = []
    source_bytes = 0
    omitted_ranges = 0
    for seed in seeds:
        if len(source_sites) >= selected_budgets.max_source_files:
            omitted_ranges += 1
            continue
        if source_bytes >= selected_budgets.max_source_bytes:
            omitted_ranges += 1
            continue
        try:
            snapshot = navigator.inspect_path(
                seed["path"],
                source_id=seed.get("source_id"),
                expected_hash=seed.get("content_hash"),
                reference_ids=seed.get("reference_ids", []),
                symbol=seed.get("symbol"),
            )
        except PlanningError as error:
            diagnostics.append(
                {
                    "code": error.code.value,
                    "severity": "ERROR",
                    "message": error.message,
                    "path": seed["path"],
                }
            )
            continue
        if source_bytes + snapshot.size > selected_budgets.max_source_bytes:
            omitted_ranges += 1
            continue
        source_sites.append(snapshot.site)
        source_bytes += snapshot.size
    omitted = OmissionSummary(
        nodes=omitted_nodes,
        source_ranges=omitted_ranges,
        source_bytes=0,
    )
    verification = sorted(
        {
            *effective_request.required_verification,
            *(bundle.verification_requirements if bundle else []),
        }
    )
    gaps = detect_planning_gaps(
        has_bundle=bundle is not None,
        allowed_scope_resolved=constraints.scope_status == "RESOLVED",
        relevant_claims=claims,
        relevant_evidence=[*relevant_evidence, *counter],
        conflicts=conflicts,
        source_sites=source_sites,
        verification_requirements=verification,
        omitted=omitted,
    )
    if atlas is None and bundle is not None:
        diagnostics.append(
            {
                "code": "ATLAS_NOT_SUPPLIED",
                "severity": "INFO",
                "message": "Context uses validated Bundle plus current Source without Atlas navigation.",
            }
        )
    return PlanningContext(
        schema_version="planning-context/1.0",
        request=effective_request,
        workspace=effective_request.workspace_identity,
        relevant_claims=claims,
        relevant_evidence=relevant_evidence,
        counter_evidence=counter,
        conflicts=conflicts,
        unknowns=unknowns,
        atlas_nodes=atlas.nodes if atlas is not None else [],
        source_sites=source_sites,
        candidate_relations=atlas.edges if atlas is not None else [],
        constraints=constraints,
        gaps=gaps,
        omitted=omitted,
        diagnostics=[
            *diagnostics,
            *(atlas.diagnostics if atlas is not None else []),
            *[
                {
                    "reference_id": item.reference_id,
                    "kind": item.kind,
                    "priority_tier": item.priority_tier,
                    "reasons": item.reasons,
                }
                for item in selected
            ],
        ],
    )


def _resolve_constraints(
    request: PlanningRequest,
    bundle: PlanningBundleView | None,
) -> PlanningConstraints:
    protected = {
        *PROTECTED_PATHS,
        *request.protected_paths,
        *(bundle.protected_paths if bundle else []),
    }
    bundle_allowed = bundle.allowed_paths if bundle else []
    if request.allowed_paths:
        if bundle_allowed:
            allowed = [
                path
                for path in request.allowed_paths
                if any(
                    _patterns_overlap(path, policy)
                    for policy in bundle_allowed
                )
            ]
        else:
            allowed = list(request.allowed_paths)
    else:
        allowed = list(bundle_allowed)
    return PlanningConstraints(
        allowed_paths=sorted(set(allowed)),
        protected_paths=sorted(set(protected)),
        scope_status="RESOLVED" if allowed else "UNRESOLVED",
    )


def _patterns_overlap(left: str, right: str) -> bool:
    left_root = left.removesuffix("/**").rstrip("/")
    right_root = right.removesuffix("/**").rstrip("/")
    return (
        left_root == right_root
        or left_root.startswith(right_root + "/")
        or right_root.startswith(left_root + "/")
    )


def _selected_records(
    ranked: list[RankedReference],
    kind: str,
) -> list[dict[str, Any]]:
    return [
        dict(item.record)
        for item in ranked
        if item.kind == kind
    ]


def _source_seeds(
    request: PlanningRequest,
    bundle: PlanningBundleView | None,
    selected_sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seeds: dict[str, dict[str, Any]] = {}
    source_records = {
        item["id"]: item
        for item in (bundle.sources if bundle else [])
        if isinstance(item.get("id"), str)
    }
    relevant_source_ids = {
        reference
        for item in evidence
        for reference in item.get("source_refs", [])
        if isinstance(reference, str)
    }
    relevant_source_ids.update(
        item["id"] for item in selected_sources if isinstance(item.get("id"), str)
    )
    for source_id in sorted(relevant_source_ids):
        source = source_records.get(source_id)
        if source is None:
            continue
        locator = source.get("locator", {})
        path = locator.get("path") if isinstance(locator, dict) else None
        if not isinstance(path, str):
            continue
        seeds[path] = {
            "path": path,
            "source_id": source_id,
            "content_hash": source.get("integrity", {}).get("content_hash"),
            "reference_ids": sorted(
                item["id"]
                for item in evidence
                if source_id in item.get("source_refs", [])
            ),
        }
    for item in evidence:
        for path in item.get("bindings", {}).get("paths", []):
            if isinstance(path, str):
                seeds.setdefault(
                    path,
                    {
                        "path": path,
                        "reference_ids": [str(item.get("id", ""))],
                    },
                )
    for pattern in request.allowed_paths:
        if not any(character in pattern for character in "*?["):
            seeds.setdefault(pattern, {"path": pattern, "reference_ids": []})
    return [seeds[key] for key in sorted(seeds)]
