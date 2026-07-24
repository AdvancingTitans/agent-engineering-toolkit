"""Intent and diff preflight for the /aet-scope Skill."""

from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any

from ..evidence import workspace_snapshot
from ..review import ReviewError, _changed_paths


SCOPE_BUDGET = {
    "wall_time_seconds": 45,
    "llm_calls": 2,
    "tool_calls": 8,
    "remote_calls": 2,
    "expensive_calls": 1,
    "findings": 5,
    "investigation_rounds": 4,
    "max_low_cost_tests": 1,
}


def quick_scope(root: Path, *, base: str, intent_path: Path | None) -> dict[str, Any]:
    """Collect scope facts; path mismatches remain questions until investigated."""
    root = root.resolve()
    try:
        changed_paths = _changed_paths(root, base)
    except ReviewError:
        raise
    snapshot = workspace_snapshot(root)
    if intent_path is None:
        return {
            "schema": "aet-quick-scope/v1",
            "report_kind": "quick_scope_preflight",
            "authoritative_status": "UNKNOWN",
            "disposition": "INSUFFICIENT_INTENT",
            "base": base,
            "changed_paths": changed_paths,
            "workspace_snapshot": snapshot,
            "budget": SCOPE_BUDGET,
            "observations": _path_observations(changed_paths),
            "required_investigation": _required_investigation(),
            "stop_after": "report_emitted",
        }
    path = intent_path if intent_path.is_absolute() else root / intent_path
    intent = _load_intent(path.resolve(), root)
    allowed = intent.get("allowed_surfaces") or intent.get("allowed_paths") or []
    outside = [item for item in changed_paths if not _matches_any(item, allowed)]
    disposition = "POSSIBLE_SCOPE_EXPANSION" if outside else "IN_SCOPE"
    observations = _path_observations(changed_paths)
    if outside:
        observations.append({
            "observation_id": "obs_outside_declared_surface",
            "type": "path_outside_declared_surface",
            "paths": outside,
            "authoritative_status": "FAIL",
            "semantic_effect": "investigate_necessity_before_scope_conclusion",
        })
    return {
        "schema": "aet-quick-scope/v1",
        "report_kind": "quick_scope_preflight",
        "authoritative_status": "PASS" if not outside else "FAIL",
        "disposition": disposition,
        "base": base,
        "intent": intent,
        "intent_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "changed_paths": changed_paths,
        "workspace_snapshot": snapshot,
        "budget": SCOPE_BUDGET,
        "observations": observations,
        "required_investigation": _required_investigation(),
        "guardrail": "A path mismatch alone cannot establish OUT_OF_SCOPE.",
        "stop_after": "report_emitted",
    }


def _load_intent(path: Path, root: Path) -> dict[str, Any]:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ReviewError("intent contract must be inside the review root") from error
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewError(f"cannot read intent contract: {error}") from error
    if not isinstance(value, dict):
        raise ReviewError("intent contract must be a JSON object")
    if value.get("schema_version", value.get("schema")) == "aet-intent/v2":
        goal = value.get("goal")
        sources = value.get("source_refs")
        if not isinstance(goal, dict) or not isinstance(goal.get("text"), str) or not goal["text"].strip():
            raise ReviewError("aet-intent/v2 requires goal.text")
        if not isinstance(sources, list) or not sources:
            raise ReviewError("aet-intent/v2 requires source_refs")
        for source in sources:
            if not isinstance(source, dict) or source.get("source_type") not in {
                "explicit_user",
                "explicit_project",
                "inferred",
                "unknown",
            }:
                raise ReviewError("each intent source needs a valid source_type")
        return value
    if not isinstance(value.get("intent"), str) or not value["intent"].strip():
        raise ReviewError("legacy intent requires a non-empty intent")
    value = dict(value)
    value["schema"] = "aet-intent/legacy"
    value["source_refs"] = [{"source_type": "explicit_project", "ref": path.name}]
    return value


def _matches_any(path: str, patterns: list[Any]) -> bool:
    for item in patterns:
        pattern = item if isinstance(item, str) else item.get("text") if isinstance(item, dict) else None
        if not isinstance(pattern, str):
            continue
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def _path_observations(paths: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "observation_id": f"obs_changed_path_{index}",
            "type": "changed_path",
            "value": path,
            "source": {"tool": "git.diff", "invocation_id": "preflight"},
        }
        for index, path in enumerate(paths, 1)
    ]


def _required_investigation() -> list[str]:
    return [
        "recover_intent",
        "identify_changed_purpose",
        "inspect_direct_dependency",
        "inspect_test_or_interface_relation",
        "search_additional_authorization",
        "evaluate_counter_hypothesis",
    ]
