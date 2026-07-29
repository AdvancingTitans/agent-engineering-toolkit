"""Deterministic Helper queries over a validated Plan package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .candidate_parser import strict_json_loads
from .errors import PlanningError, PlanningErrorCode
from .package_builder import PLAN_FILES, validate_plan_package
from .renderer import render_plan_markdown


def load_plan(path: Path) -> dict[str, Any]:
    root = Path(path)
    if root.is_file() and root.name == "plan.json":
        root = root.parent
    validate_plan_package(root)
    value = strict_json_loads((root / PLAN_FILES["plan"]).read_bytes(), label="plan.json")
    if not isinstance(value, dict):
        raise PlanningError(
            PlanningErrorCode.INVALID_CANDIDATE,
            "plan.json must contain one object",
        )
    return value


def show_plan(path: Path) -> str:
    return render_plan_markdown(load_plan(path))


def explain_edit(path: Path, edit_id: str) -> dict[str, Any]:
    plan = load_plan(path)
    item = next(
        (value for value in plan["edit_items"] if value.get("edit_id") == edit_id),
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


def trace_path(path: Path, source_path: str) -> dict[str, Any]:
    plan = load_plan(path)
    root = Path(path)
    if root.is_file():
        root = root.parent
    references = _jsonl(root / PLAN_FILES["references"])
    matching_edits = [
        item for item in plan["edit_items"] if item.get("path") == source_path
    ]
    wanted = {
        reference
        for item in matching_edits
        for reference in [
            *item.get("evidence_refs", []),
            *item.get("atlas_refs", []),
            *item.get("source_refs", []),
        ]
    }
    return {
        "schema_version": "plan-reference-trace/1.0",
        "plan_id": plan["plan_id"],
        "path": source_path,
        "edit_items": matching_edits,
        "references": [
            item for item in references if item.get("reference_id") in wanted
        ],
        "status": "PASS" if matching_edits else "UNKNOWN",
    }


def trace_reference(path: Path, reference_id: str) -> dict[str, Any]:
    plan = load_plan(path)
    root = Path(path)
    if root.is_file():
        root = root.parent
    references = _jsonl(root / PLAN_FILES["references"])
    reference = next(
        (
            item
            for item in references
            if item.get("reference_id") == reference_id
        ),
        None,
    )
    if reference is None:
        raise PlanningError(
            PlanningErrorCode.REFERENCE_NOT_FOUND,
            "Plan reference does not exist",
        )
    matching_edits = [
        item
        for item in plan["edit_items"]
        if reference_id
        in {
            *item.get("evidence_refs", []),
            *item.get("atlas_refs", []),
            *item.get("source_refs", []),
        }
    ]
    return {
        "schema_version": "plan-reference-trace/1.0",
        "plan_id": plan["plan_id"],
        "reference_id": reference_id,
        "reference": reference,
        "edit_items": matching_edits,
        "status": "PASS",
    }


def list_gaps(path: Path) -> dict[str, Any]:
    plan = load_plan(path)
    gaps = [
        item
        for item in plan["diagnostics"]
        if item.get("severity") in {"ERROR", "BLOCKER"}
    ]
    return {
        "schema_version": "plan-gaps/1.0",
        "plan_id": plan["plan_id"],
        "plan_status": plan["status"],
        "gaps": gaps,
        "conflicts": plan["conflicts"],
        "unknowns": plan["unknowns"],
    }


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_bytes().splitlines(), start=1):
        if not line.strip():
            continue
        value = strict_json_loads(line, label=f"{path.name}:{number}")
        if not isinstance(value, dict):
            raise PlanningError(
                PlanningErrorCode.INVALID_CANDIDATE,
                f"{path.name}:{number} must contain one object",
            )
        rows.append(value)
    return rows
