"""Deterministic validation boundary for Host-produced Plan Candidates."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, Iterable

from .errors import PlanningError, PlanningErrorCode
from .models import (
    Diagnostic,
    EditItemCandidate,
    PlanCandidate,
    PlanStatus,
    PlanningContext,
    ReferenceStrength,
    ValidationResult,
    canonical_relative_path,
    stable_plan_id,
)
from .policy import assert_path_allowed


_COMPLETION_CLAIM = re.compile(
    r"\b(tests? passed|already (?:implemented|changed|written)|"
    r"has been (?:executed|implemented|verified)|verified successfully)\b|"
    r"(已执行|已验证|测试已通过|已经修改|已经实现)",
    re.IGNORECASE,
)


def validate_plan_candidate(
    context: PlanningContext,
    candidate: PlanCandidate,
) -> ValidationResult:
    diagnostics: list[Diagnostic] = []
    if context.schema_version != "planning-context/1.0":
        _add(diagnostics, PlanningErrorCode.INVALID_REQUEST, "BLOCKER", "unsupported Planning Context version")
    if candidate.schema_version != "plan-candidate/1.0":
        _add(diagnostics, PlanningErrorCode.INVALID_CANDIDATE, "BLOCKER", "unsupported Plan Candidate version")
    if candidate.request_id != context.request.request_id:
        _add(diagnostics, PlanningErrorCode.IDENTITY_MISMATCH, "BLOCKER", "candidate request_id does not match the Context")
    if context.workspace != context.request.workspace_identity:
        _add(diagnostics, PlanningErrorCode.IDENTITY_MISMATCH, "BLOCKER", "request and Context workspace identities differ")

    edit_ids = [item.edit_id for item in candidate.edit_items]
    if len(edit_ids) != len(set(edit_ids)):
        _add(diagnostics, PlanningErrorCode.INVALID_CANDIDATE, "BLOCKER", "edit IDs must be unique")
    verification_ids = [item.verification_id for item in candidate.verification_steps]
    if len(verification_ids) != len(set(verification_ids)):
        _add(diagnostics, PlanningErrorCode.INVALID_CANDIDATE, "BLOCKER", "verification IDs must be unique")
    if len(candidate.edit_items) > context.request.budgets.max_edit_items:
        _add(diagnostics, PlanningErrorCode.BUDGET_EXHAUSTED, "ERROR", "edit item budget is exhausted")

    inventory = _reference_inventory(context)
    source_by_id = {item.source_id: item for item in context.source_sites}
    for item in candidate.edit_items:
        _validate_item(
            item,
            context,
            inventory,
            source_by_id,
            set(edit_ids),
            diagnostics,
        )
    _validate_dependency_graph(candidate.edit_items, diagnostics)
    _validate_verification(candidate, set(edit_ids), diagnostics)
    _validate_coverage(context, candidate, diagnostics)
    if _COMPLETION_CLAIM.search(candidate.summary):
        _add(
            diagnostics,
            PlanningErrorCode.EXECUTION_ATTEMPT,
            "BLOCKER",
            "candidate summary claims implementation or verification already occurred",
        )

    status = _derive_status(context, diagnostics)
    validated_items = [
        {
            **asdict(item),
            "reference_strength": _reference_strength(item, source_by_id),
        }
        for item in sorted(candidate.edit_items, key=lambda value: value.edit_id)
    ]
    plan = {
        "schema_version": "evidence-linked-plan/1.0",
        "plan_id": stable_plan_id(
            context.request,
            context.workspace,
            context.request.bundle_identity,
        ),
        "status": status.value,
        "authority": "PROPOSED",
        "request": asdict(context.request),
        "summary": {
            "text": candidate.summary,
            "coverage_claim": candidate.coverage_claim,
            "edit_count": len(candidate.edit_items),
            "investigation_count": len(candidate.investigation_items),
        },
        "edit_items": validated_items,
        "investigation_items": candidate.investigation_items,
        "verification_plan": {
            "status": "PENDING",
            "steps": [
                asdict(item)
                for item in sorted(
                    candidate.verification_steps,
                    key=lambda value: value.verification_id,
                )
            ],
        },
        "conflicts": sorted(context.conflicts, key=_record_id),
        "unknowns": sorted(context.unknowns, key=_record_id),
        "diagnostics": [
            asdict(item)
            for item in sorted(
                diagnostics,
                key=lambda item: (
                    item.severity,
                    item.code,
                    item.edit_id or "",
                    item.message,
                ),
            )
        ],
        "source_identity": asdict(context.workspace),
        "bundle_identity": context.request.bundle_identity,
        "atlas_identity": context.request.atlas_identity,
        "created_by": {
            "name": "agent-engineering-toolkit",
            "role": "deterministic-plan-validator",
        },
    }
    return ValidationResult(plan=plan, diagnostics=diagnostics)


def _validate_item(
    item: EditItemCandidate,
    context: PlanningContext,
    inventory: dict[str, str],
    source_by_id: dict[str, Any],
    edit_ids: set[str],
    diagnostics: list[Diagnostic],
) -> None:
    try:
        path = canonical_relative_path(item.path)
    except PlanningError as error:
        _add(diagnostics, error.code, "BLOCKER", error.message, item.edit_id)
        return
    if item.disposition != "DO_NOT_EDIT":
        try:
            assert_path_allowed(path, context.constraints)
        except PlanningError as error:
            severity = "BLOCKER" if error.code == PlanningErrorCode.PROTECTED_PATH else "ERROR"
            _add(diagnostics, error.code, severity, error.message, item.edit_id)

    refs = [*item.evidence_refs, *item.atlas_refs, *item.source_refs]
    if item.disposition == "REQUIRED" and not refs:
        _add(
            diagnostics,
            PlanningErrorCode.EVIDENCE_REQUIRED,
            "ERROR",
            "REQUIRED edit must have a resolvable Evidence, Atlas, or Source reference",
            item.edit_id,
        )
    for reference in refs:
        kind = inventory.get(reference)
        if kind is None:
            _add(
                diagnostics,
                PlanningErrorCode.REFERENCE_NOT_FOUND,
                "BLOCKER",
                "candidate contains an unresolved reference",
                item.edit_id,
                [reference],
            )
            continue
        expected = (
            "evidence"
            if reference in item.evidence_refs
            else "atlas"
            if reference in item.atlas_refs
            else "source"
        )
        if kind != expected:
            _add(
                diagnostics,
                PlanningErrorCode.REFERENCE_KIND_MISMATCH,
                "BLOCKER",
                f"candidate {expected} reference resolves to {kind}",
                item.edit_id,
                [reference],
            )
    for reference in item.source_refs:
        source = source_by_id.get(reference)
        if source is None:
            continue
        if source.path != path:
            _add(
                diagnostics,
                PlanningErrorCode.REFERENCE_KIND_MISMATCH,
                "BLOCKER",
                "Source reference path does not match the edit path",
                item.edit_id,
                [reference],
            )
        if item.disposition == "REQUIRED" and source.read_status != "CONFIRMED":
            code = (
                PlanningErrorCode.SOURCE_STALE
                if source.read_status == "STALE"
                else PlanningErrorCode.SOURCE_MISSING
            )
            _add(
                diagnostics,
                code,
                "ERROR",
                "REQUIRED edit source is not confirmed in the current workspace",
                item.edit_id,
                [reference],
            )
        if item.symbol and source.symbol and item.symbol != source.symbol:
            _add(
                diagnostics,
                PlanningErrorCode.SYMBOL_NOT_FOUND,
                "ERROR",
                "candidate symbol does not match the Source reference",
                item.edit_id,
                [reference],
            )
        if item.source_range and source.start_line and source.end_line:
            if (
                item.source_range.start_line < source.start_line
                or item.source_range.end_line > source.end_line
            ):
                _add(
                    diagnostics,
                    PlanningErrorCode.SOURCE_STALE,
                    "ERROR",
                    "candidate line range is outside the confirmed Source range",
                    item.edit_id,
                    [reference],
                )
    for dependency in item.dependencies:
        if dependency not in edit_ids:
            _add(
                diagnostics,
                PlanningErrorCode.REFERENCE_NOT_FOUND,
                "BLOCKER",
                "edit dependency does not exist",
                item.edit_id,
                [dependency],
            )
    if _COMPLETION_CLAIM.search(item.expected_change):
        _add(
            diagnostics,
            PlanningErrorCode.WRITE_ATTEMPT,
            "BLOCKER",
            "candidate claims the proposed change is already implemented or verified",
            item.edit_id,
        )


def _validate_dependency_graph(
    items: Iterable[EditItemCandidate],
    diagnostics: list[Diagnostic],
) -> None:
    graph = {item.edit_id: list(item.dependencies) for item in items}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(dependency in graph and visit(dependency) for dependency in graph.get(node, [])):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    if any(visit(node) for node in sorted(graph)):
        _add(diagnostics, PlanningErrorCode.INVALID_CANDIDATE, "BLOCKER", "edit dependency graph contains a cycle")


def _validate_verification(
    candidate: PlanCandidate,
    edit_ids: set[str],
    diagnostics: list[Diagnostic],
) -> None:
    if not candidate.verification_steps:
        _add(
            diagnostics,
            PlanningErrorCode.EVIDENCE_REQUIRED,
            "ERROR",
            "verification plan must not be empty",
        )
        return
    for step in candidate.verification_steps:
        for reference in step.edit_refs:
            if reference not in edit_ids:
                _add(
                    diagnostics,
                    PlanningErrorCode.REFERENCE_NOT_FOUND,
                    "BLOCKER",
                    "verification step references an unknown edit",
                    reference_ids=[reference],
                )
        if step.status != "PENDING":
            _add(
                diagnostics,
                PlanningErrorCode.EXECUTION_ATTEMPT,
                "BLOCKER",
                "Planning verification status must remain PENDING",
            )


def _validate_coverage(
    context: PlanningContext,
    candidate: PlanCandidate,
    diagnostics: list[Diagnostic],
) -> None:
    if candidate.coverage_claim != "BOUNDED_COMPLETE":
        return
    reasons = []
    if context.omitted.total:
        reasons.append("Context contains omitted data")
    if any(item.read_status == "UNSUPPORTED" for item in context.source_sites):
        reasons.append("Context contains an unsupported source language")
    if any(item.critical for item in context.gaps):
        reasons.append("Context contains a critical gap")
    if any(
        str(item.get("resolution_status", item.get("status", ""))).lower()
        == "unresolved"
        and str(item.get("priority", item.get("severity", ""))).lower()
        in {"critical", "high", "error"}
        for item in context.conflicts
    ):
        reasons.append("Context contains an unresolved high-priority conflict")
    if any(
        item.disposition == "REQUIRED"
        and not (item.evidence_refs or item.atlas_refs or item.source_refs)
        for item in candidate.edit_items
    ):
        reasons.append("a REQUIRED edit lacks references")
    if context.constraints.scope_status != "RESOLVED":
        reasons.append("allowed scope is unresolved")
    if reasons:
        _add(
            diagnostics,
            PlanningErrorCode.OVERCLAIMED_COVERAGE,
            "ERROR",
            "; ".join(reasons),
        )


def _reference_inventory(context: PlanningContext) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for records, kind in (
        (context.relevant_claims, "evidence"),
        (context.relevant_evidence, "evidence"),
        (context.counter_evidence, "evidence"),
        (context.conflicts, "evidence"),
        (context.unknowns, "evidence"),
        (context.atlas_nodes, "atlas"),
    ):
        for record in records:
            identifier = _identifier(record)
            if identifier:
                inventory[identifier] = kind
    for source in context.source_sites:
        inventory[source.source_id] = "source"
    return inventory


def _reference_strength(
    item: EditItemCandidate,
    source_by_id: dict[str, Any],
) -> str:
    if item.evidence_refs or item.atlas_refs:
        return ReferenceStrength.EVIDENCE_BACKED.value
    if any(
        source_by_id.get(reference) is not None
        and source_by_id[reference].read_status == "CONFIRMED"
        for reference in item.source_refs
    ):
        return ReferenceStrength.SOURCE_CONFIRMED.value
    if item.disposition in {"OPTIONAL", "INVESTIGATE"} and item.limitations:
        return ReferenceStrength.INFERRED_WITH_LIMITS.value
    if item.source_refs:
        return ReferenceStrength.NEEDS_EVIDENCE.value
    return ReferenceStrength.UNKNOWN.value


def _derive_status(
    context: PlanningContext,
    diagnostics: list[Diagnostic],
) -> PlanStatus:
    if any(item.severity == "BLOCKER" for item in diagnostics):
        return PlanStatus.BLOCKED
    if context.omitted.total or any(
        item.code == PlanningErrorCode.BUDGET_EXHAUSTED.value for item in diagnostics
    ):
        return PlanStatus.PARTIAL
    if any(item.severity == "ERROR" for item in diagnostics):
        return PlanStatus.NEEDS_EVIDENCE
    if any(item.critical for item in context.gaps):
        return PlanStatus.NEEDS_EVIDENCE
    return PlanStatus.READY_FOR_HUMAN_REVIEW


def _identifier(value: dict[str, Any]) -> str | None:
    for key in ("id", "reference_id", "node_id"):
        if isinstance(value.get(key), str) and value[key]:
            return value[key]
    return None


def _record_id(value: dict[str, Any]) -> str:
    return _identifier(value) or ""


def _add(
    diagnostics: list[Diagnostic],
    code: PlanningErrorCode | str,
    severity: str,
    message: str,
    edit_id: str | None = None,
    reference_ids: list[str] | None = None,
) -> None:
    diagnostics.append(
        Diagnostic(
            code=PlanningErrorCode(code).value,
            severity=severity,
            message=message,
            edit_id=edit_id,
            reference_ids=reference_ids or [],
        )
    )
