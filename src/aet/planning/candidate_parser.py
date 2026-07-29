"""Strict JSON-only Plan Candidate parsing."""

from __future__ import annotations

import json
from typing import Any

from .errors import PlanningError, PlanningErrorCode
from .models import EditItemCandidate, LineRange, PlanCandidate, VerificationStep


MAX_CANDIDATE_BYTES = 5_000_000
MAX_CANDIDATE_ITEMS = 1_000


def strict_json_loads(raw: bytes | str, *, label: str = "Plan Candidate") -> Any:
    if isinstance(raw, bytes):
        if len(raw) > MAX_CANDIDATE_BYTES:
            raise PlanningError(
                PlanningErrorCode.INVALID_CANDIDATE,
                f"{label} exceeds the byte budget",
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise PlanningError(
                PlanningErrorCode.INVALID_CANDIDATE,
                f"{label} must be UTF-8",
            ) from error
    elif isinstance(raw, str):
        text = raw
        if len(text.encode("utf-8")) > MAX_CANDIDATE_BYTES:
            raise PlanningError(
                PlanningErrorCode.INVALID_CANDIDATE,
                f"{label} exceeds the byte budget",
            )
    else:
        raise PlanningError(
            PlanningErrorCode.INVALID_CANDIDATE,
            f"{label} must be JSON bytes or text",
        )

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise PlanningError(
                    PlanningErrorCode.INVALID_CANDIDATE,
                    f"{label} contains duplicate key {key!r}",
                )
            value[key] = item
        return value

    def reject_constant(value: str) -> Any:
        raise PlanningError(
            PlanningErrorCode.INVALID_CANDIDATE,
            f"{label} contains non-finite number {value}",
        )

    try:
        return json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except PlanningError:
        raise
    except (json.JSONDecodeError, UnicodeError) as error:
        raise PlanningError(
            PlanningErrorCode.INVALID_CANDIDATE,
            f"{label} must contain exactly one JSON document",
        ) from error


def parse_candidate(raw: bytes | str) -> PlanCandidate:
    value = strict_json_loads(raw)
    if not isinstance(value, dict):
        _fail("Plan Candidate must contain one object")
    _exact(
        value,
        {
            "schema_version",
            "request_id",
            "summary",
            "coverage_claim",
            "edit_items",
            "investigation_items",
            "verification_steps",
            "assumptions",
            "unresolved",
        },
        "Plan Candidate",
    )
    if value["schema_version"] != "plan-candidate/1.0":
        _fail("unsupported Plan Candidate schema version")
    _nonempty(value["request_id"], "request_id")
    _nonempty(value["summary"], "summary")
    _enum(
        value["coverage_claim"],
        {"BOUNDED_COMPLETE", "BEST_EFFORT", "PARTIAL", "UNKNOWN"},
        "coverage_claim",
    )
    for field in (
        "edit_items",
        "investigation_items",
        "verification_steps",
        "assumptions",
        "unresolved",
    ):
        if not isinstance(value[field], list):
            _fail(f"{field} must be an array")
        if len(value[field]) > MAX_CANDIDATE_ITEMS:
            _fail(f"{field} exceeds the item budget")

    edit_items = [_parse_edit(item, number) for number, item in enumerate(value["edit_items"])]
    verification = [
        _parse_verification(item, number)
        for number, item in enumerate(value["verification_steps"])
    ]
    for field in ("investigation_items", "assumptions", "unresolved"):
        if any(not isinstance(item, dict) for item in value[field]):
            _fail(f"{field} must contain objects")
    return PlanCandidate(
        schema_version=value["schema_version"],
        request_id=value["request_id"],
        summary=value["summary"],
        coverage_claim=value["coverage_claim"],
        edit_items=edit_items,
        investigation_items=[dict(item) for item in value["investigation_items"]],
        verification_steps=verification,
        assumptions=[dict(item) for item in value["assumptions"]],
        unresolved=[dict(item) for item in value["unresolved"]],
    )


def _parse_edit(value: Any, number: int) -> EditItemCandidate:
    label = f"edit_items[{number}]"
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    _exact(
        value,
        {
            "edit_id",
            "disposition",
            "path",
            "symbol",
            "source_range",
            "intent",
            "expected_change",
            "rationale",
            "behavior_links",
            "evidence_refs",
            "atlas_refs",
            "source_refs",
            "dependencies",
            "tests",
            "risks",
            "limitations",
        },
        label,
    )
    for field in ("edit_id", "path", "intent", "expected_change", "rationale"):
        _nonempty(value[field], f"{label}.{field}")
    _enum(
        value["disposition"],
        {"REQUIRED", "OPTIONAL", "INVESTIGATE", "DO_NOT_EDIT"},
        f"{label}.disposition",
    )
    if value["symbol"] is not None and not isinstance(value["symbol"], str):
        _fail(f"{label}.symbol must be a string or null")
    line_range = None
    if value["source_range"] is not None:
        if not isinstance(value["source_range"], dict):
            _fail(f"{label}.source_range must be an object or null")
        _exact(value["source_range"], {"start_line", "end_line"}, f"{label}.source_range")
        try:
            line_range = LineRange(**value["source_range"])
        except (TypeError, PlanningError) as error:
            _fail(f"{label}.source_range is invalid", cause=error)
    list_fields = (
        "behavior_links",
        "evidence_refs",
        "atlas_refs",
        "source_refs",
        "dependencies",
        "tests",
        "risks",
        "limitations",
    )
    for field in list_fields:
        _string_list(value[field], f"{label}.{field}")
    return EditItemCandidate(
        edit_id=value["edit_id"],
        disposition=value["disposition"],
        path=value["path"],
        symbol=value["symbol"],
        source_range=line_range,
        intent=value["intent"],
        expected_change=value["expected_change"],
        rationale=value["rationale"],
        behavior_links=list(value["behavior_links"]),
        evidence_refs=list(value["evidence_refs"]),
        atlas_refs=list(value["atlas_refs"]),
        source_refs=list(value["source_refs"]),
        dependencies=list(value["dependencies"]),
        tests=list(value["tests"]),
        risks=list(value["risks"]),
        limitations=list(value["limitations"]),
    )


def _parse_verification(value: Any, number: int) -> VerificationStep:
    label = f"verification_steps[{number}]"
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    _exact(
        value,
        {
            "verification_id",
            "description",
            "command",
            "edit_refs",
            "expected_result",
            "status",
        },
        label,
    )
    for field in ("verification_id", "description", "expected_result"):
        _nonempty(value[field], f"{label}.{field}")
    if value["status"] != "PENDING":
        _fail(f"{label}.status must be PENDING")
    command = value["command"]
    if command is not None:
        _string_list(command, f"{label}.command", nonempty=True)
    _string_list(value["edit_refs"], f"{label}.edit_refs")
    return VerificationStep(
        verification_id=value["verification_id"],
        description=value["description"],
        command=list(command) if command is not None else None,
        edit_refs=list(value["edit_refs"]),
        expected_result=value["expected_result"],
        status="PENDING",
    )


def _exact(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        unknown = sorted(set(value) - expected)
        _fail(f"{label} fields mismatch; missing={missing}, unknown={unknown}")


def _nonempty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be a non-empty string")


def _string_list(value: Any, label: str, *, nonempty: bool = False) -> None:
    if (
        not isinstance(value, list)
        or (nonempty and not value)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        _fail(f"{label} must contain unique strings")


def _enum(value: Any, allowed: set[str], label: str) -> None:
    if value not in allowed:
        _fail(f"{label} is unsupported")


def _fail(message: str, *, cause: Exception | None = None) -> None:
    error = PlanningError(PlanningErrorCode.INVALID_CANDIDATE, message)
    if cause is None:
        raise error
    raise error from cause
