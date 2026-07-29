"""Read-only Python SDK helpers for portable Evidence-Linked Plans."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from aet.planning.candidate_parser import strict_json_loads
from aet.planning.errors import PlanningError, PlanningErrorCode
from aet.planning.handoff import (
    build_verification_handoff_from_package as _build_handoff,
)
from aet.planning.helper import load_plan as _load_plan_package
from aet.planning.models import canonical_json_bytes
from aet.planning.package_builder import validate_plan_package


def load_plan(path: str | Path) -> dict[str, Any]:
    """Load one integrity-checked portable Plan package."""
    return _load_plan_package(Path(path))


def query_plan_edits(
    plan: Mapping[str, Any],
    path: str | None = None,
) -> list[dict[str, Any]]:
    """Return validated Edit Items, optionally for one exact path."""
    _require_plan(plan)
    edits = plan.get("edit_items")
    if not isinstance(edits, list) or any(not isinstance(item, dict) for item in edits):
        raise PlanningError(
            PlanningErrorCode.INVALID_CANDIDATE,
            "Plan edit_items must contain objects",
        )
    if path is None:
        return [dict(item) for item in edits]
    return [dict(item) for item in edits if item.get("path") == path]


def explain_edit(
    plan: Mapping[str, Any],
    edit_id: str,
) -> dict[str, Any]:
    """Explain one recorded Edit Item without adding facts."""
    if not isinstance(edit_id, str) or not edit_id:
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "edit_id must be a non-empty string",
        )
    item = next(
        (
            value
            for value in query_plan_edits(plan)
            if value.get("edit_id") == edit_id
        ),
        None,
    )
    if item is None:
        raise PlanningError(
            PlanningErrorCode.REFERENCE_NOT_FOUND,
            "Plan edit does not exist",
        )
    return {
        "schema_version": "plan-edit-explanation/1.0",
        "plan_id": plan["plan_id"],
        "status": plan["status"],
        "authority": "PROPOSED",
        "edit": item,
        "what_this_does_not_prove": [
            "The edit has not been implemented.",
            "The verification steps have not run.",
        ],
    }


def validate_plan(path: str | Path) -> dict[str, Any]:
    """Validate one portable Plan package and every declared file hash."""
    return validate_plan_package(Path(path))


def build_verification_handoff(
    path: str | Path,
    diff: str | bytes,
) -> dict[str, Any]:
    """Map an external diff to pending Proof requests without execution."""
    return _build_handoff(Path(path), diff)


def render_planner_context(
    path: str | Path,
    *,
    max_chars: int,
) -> str:
    """Render canonical Planning Context JSON within one explicit character budget."""
    if (
        not isinstance(max_chars, int)
        or isinstance(max_chars, bool)
        or max_chars < 1
    ):
        raise ValueError("max_chars must be a positive integer")
    value = strict_json_loads(
        Path(path).read_bytes(),
        label="Planning Context",
    )
    if not isinstance(value, dict) or value.get("schema_version") != "planning-context/1.0":
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "Planning Context is invalid",
        )
    rendered = canonical_json_bytes(value).decode("utf-8").rstrip("\n")
    if len(rendered) > max_chars:
        raise PlanningError(
            PlanningErrorCode.BUDGET_EXHAUSTED,
            "Planning Context exceeds max_chars; reduce context budgets instead of truncating",
        )
    return rendered


def _require_plan(plan: Mapping[str, Any]) -> None:
    if (
        not isinstance(plan, Mapping)
        or plan.get("schema_version") != "evidence-linked-plan/1.0"
        or plan.get("authority") != "PROPOSED"
        or not isinstance(plan.get("plan_id"), str)
    ):
        raise PlanningError(
            PlanningErrorCode.INVALID_CANDIDATE,
            "Evidence-Linked Plan is invalid",
        )


__all__ = [
    "build_verification_handoff",
    "explain_edit",
    "load_plan",
    "query_plan_edits",
    "render_planner_context",
    "validate_plan",
]
