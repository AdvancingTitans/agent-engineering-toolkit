"""Read-only external-diff mapping for post-implementation verification."""

from __future__ import annotations

import hashlib
import shlex
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import PlanningError, PlanningErrorCode
from .helper import _jsonl, load_plan
from .models import canonical_json_bytes, canonical_relative_path
from .package_builder import PLAN_FILES, validate_plan_package


MAX_DIFF_BYTES = 2_000_000


def build_verification_handoff(
    plan: Mapping[str, Any],
    diff: str | bytes,
    *,
    references: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Map one external unified diff to a frozen Plan without executing it."""
    _require_plan(plan)
    text = _diff_text(diff)
    changes = _parse_unified_diff(text)
    changed_paths = sorted(
        {
            path
            for change in changes
            for path in (change["old_path"], change["new_path"])
            if path is not None
        }
    )
    planned_items = [
        item
        for item in plan["edit_items"]
        if item.get("disposition") != "DO_NOT_EDIT"
    ]
    planned_paths = sorted(
        {
            path
            for item in planned_items
            for path in [
                str(item["path"]),
                *[
                    value
                    for value in item.get("tests", [])
                    if isinstance(value, str)
                ],
            ]
        }
    )
    do_not_edit_paths = sorted(
        {
            str(item["path"])
            for item in plan["edit_items"]
            if item.get("disposition") == "DO_NOT_EDIT"
        }
    )
    planned_set = set(planned_paths)
    changed_set = set(changed_paths)
    touched_items = []
    for item in planned_items:
        matched_paths = sorted(
            changed_set
            & {
                str(item["path"]),
                *[
                    value
                    for value in item.get("tests", [])
                    if isinstance(value, str)
                ],
            }
        )
        if matched_paths:
            touched_items.append(
                {
                    "edit_id": item["edit_id"],
                    "path": item["path"],
                    "disposition": item["disposition"],
                    "matched_paths": matched_paths,
                }
            )
    reference_values = [dict(item) for item in references]
    stale = [
        {
            "reference_id": item.get("reference_id"),
            "kind": item.get("kind"),
            "path": item.get("path"),
            "status": item.get("status"),
            "strength": item.get("strength"),
        }
        for item in reference_values
        if item.get("status") == "STALE"
        or item.get("strength") in {"NEEDS_EVIDENCE", "UNKNOWN"}
    ]
    proof_candidates = _proof_candidates(
        plan,
        touched_items,
        changed_paths,
    )
    lineage = [
        {
            "path": path,
            "status": "UNKNOWN",
            "reason": (
                "The external diff does not establish regression lineage; "
                "a separate Evidence Atlas or Proof update must resolve it."
            ),
        }
        for path in changed_paths
    ]
    unplanned = sorted(changed_set - planned_set)
    do_not_edit_changed = sorted(changed_set & set(do_not_edit_paths))
    status = (
        "NEEDS_REVIEW"
        if unplanned or do_not_edit_changed or stale or lineage
        else "PENDING"
    )
    return {
        "schema_version": "verification-handoff/1.0",
        "handoff_id": _handoff_id(plan["plan_id"], text),
        "plan_id": plan["plan_id"],
        "plan_status": plan["status"],
        "authority": "PROPOSED",
        "status": status,
        "planned_paths": planned_paths,
        "changed_paths": changed_paths,
        "planned_changed_paths": sorted(planned_set & changed_set),
        "untouched_planned_paths": sorted(planned_set - changed_set),
        "unplanned_paths": unplanned,
        "do_not_edit_changed_paths": do_not_edit_changed,
        "changes": changes,
        "touched_edit_items": touched_items,
        "pending_proof": proof_candidates,
        "stale_evidence": stale,
        "unresolved_regression_lineage": lineage,
        "verification_status": "UNKNOWN",
        "execution": {
            "allowed": False,
            "commands_executed": 0,
            "proofs_executed": 0,
        },
        "limitations": [
            "A diff records changed paths but does not prove intended behavior.",
            "Proof candidates are argv data and were not executed.",
            "The original Plan package was read and not modified.",
        ],
    }


def build_verification_handoff_from_package(
    plan_package: Path,
    diff: str | bytes,
) -> dict[str, Any]:
    """Validate a Plan package, read its references, and build one handoff."""
    root = Path(plan_package)
    if root.is_file():
        root = root.parent
    validate_plan_package(root)
    plan = load_plan(root)
    references = _jsonl(root / PLAN_FILES["references"])
    return build_verification_handoff(
        plan,
        diff,
        references=references,
    )


def _parse_unified_diff(text: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if line.startswith(("diff --cc ", "diff --combined ")):
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "combined diffs are unsupported",
            )
        if line.startswith("diff --git "):
            if current is not None:
                changes.append(_finish_change(current))
            fields = shlex.split(line)
            if len(fields) != 4:
                raise PlanningError(
                    PlanningErrorCode.INVALID_REQUEST,
                    "diff --git header is invalid",
                )
            current = {
                "old_path": _diff_path(fields[2], "a/"),
                "new_path": _diff_path(fields[3], "b/"),
                "change_type": "MODIFIED",
            }
            continue
        if current is None:
            if line.startswith(("--- ", "+++ ")):
                raise PlanningError(
                    PlanningErrorCode.INVALID_REQUEST,
                    "unified diff file headers require a preceding diff --git header",
                )
            continue
        if line.startswith("new file mode "):
            current["change_type"] = "ADDED"
        elif line.startswith("deleted file mode "):
            current["change_type"] = "DELETED"
        elif line.startswith("rename from "):
            current["old_path"] = _diff_path(
                line.removeprefix("rename from "),
                None,
            )
            current["change_type"] = "RENAMED"
        elif line.startswith("rename to "):
            current["new_path"] = _diff_path(
                line.removeprefix("rename to "),
                None,
            )
            current["change_type"] = "RENAMED"
        elif line.startswith("--- "):
            current["old_path"] = _file_header_path(line[4:], "a/")
        elif line.startswith("+++ "):
            current["new_path"] = _file_header_path(line[4:], "b/")
    if current is not None:
        changes.append(_finish_change(current))
    return sorted(
        changes,
        key=lambda item: (
            item["new_path"] or "",
            item["old_path"] or "",
            item["change_type"],
        ),
    )


def _finish_change(value: dict[str, Any]) -> dict[str, Any]:
    old_path = value.get("old_path")
    new_path = value.get("new_path")
    if old_path is None and new_path is None:
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "diff change has no repository path",
        )
    change_type = value["change_type"]
    if old_path is None:
        change_type = "ADDED"
    elif new_path is None:
        change_type = "DELETED"
    elif old_path != new_path and change_type == "MODIFIED":
        change_type = "RENAMED"
    return {
        "old_path": old_path,
        "new_path": new_path,
        "change_type": change_type,
    }


def _file_header_path(value: str, prefix: str) -> str | None:
    raw = value.split("\t", 1)[0]
    if raw == "/dev/null":
        return None
    fields = shlex.split(raw)
    if len(fields) != 1:
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "diff file header path is invalid",
        )
    return _diff_path(fields[0], prefix)


def _diff_path(value: str, prefix: str | None) -> str:
    raw = value
    if prefix is not None:
        if not raw.startswith(prefix):
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "diff path is missing its repository prefix",
            )
        raw = raw[len(prefix) :]
    return canonical_relative_path(raw)


def _proof_candidates(
    plan: Mapping[str, Any],
    touched_items: list[dict[str, Any]],
    changed_paths: list[str],
) -> list[dict[str, Any]]:
    touched_ids = {item["edit_id"] for item in touched_items}
    if not touched_ids:
        return []
    steps = plan.get("verification_plan", {}).get("steps", [])
    if not isinstance(steps, list):
        return []
    candidates = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        edit_refs = [
            value
            for value in step.get("edit_refs", [])
            if isinstance(value, str)
        ]
        if touched_ids and not touched_ids.intersection(edit_refs):
            continue
        verification_id = str(step.get("verification_id", ""))
        if not verification_id:
            continue
        candidates.append(
            {
                "proof_candidate_id": f"PROOF-CANDIDATE-{verification_id}",
                "verification_id": verification_id,
                "plan_id": plan["plan_id"],
                "edit_refs": edit_refs,
                "changed_paths": list(changed_paths),
                "description": step.get("description"),
                "command": step.get("command"),
                "expected_result": step.get("expected_result"),
                "status": "UNKNOWN",
                "execution_status": "PENDING",
            }
        )
    return sorted(candidates, key=lambda item: item["proof_candidate_id"])


def _diff_text(value: str | bytes) -> str:
    if isinstance(value, str):
        raw = value.encode("utf-8")
    elif isinstance(value, bytes):
        raw = value
    else:
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "diff must be UTF-8 text",
        )
    if len(raw) > MAX_DIFF_BYTES:
        raise PlanningError(
            PlanningErrorCode.BUDGET_EXHAUSTED,
            "external diff exceeds the byte budget",
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "external diff must be UTF-8",
        ) from error


def _handoff_id(plan_id: str, diff: str) -> str:
    value = {
        "plan_id": plan_id,
        "diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
    }
    return "HANDOFF-" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()[:16].upper()


def _require_plan(plan: Mapping[str, Any]) -> None:
    if (
        not isinstance(plan, Mapping)
        or plan.get("schema_version") != "evidence-linked-plan/1.0"
        or plan.get("authority") != "PROPOSED"
        or not isinstance(plan.get("plan_id"), str)
        or not isinstance(plan.get("edit_items"), list)
    ):
        raise PlanningError(
            PlanningErrorCode.INVALID_CANDIDATE,
            "Evidence-Linked Plan is invalid",
        )
