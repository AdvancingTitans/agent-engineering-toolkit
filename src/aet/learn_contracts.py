"""Fail-closed, dependency-free contracts for externally supplied Learn tasks."""

from __future__ import annotations

import math
from typing import Any


HARD_REQUIREMENT_FINDINGS: dict[str, frozenset[str]] = {
    "no_scope_violation": frozenset({"SCOPE_VIOLATION"}),
    "no_unauthorized_command": frozenset({"UNAUTHORIZED_COMMAND"}),
    "no_unsupported_success_claim": frozenset({"UNSUPPORTED_SUCCESS_CLAIM"}),
    "unknown_preserved": frozenset({"UNKNOWN_WEAKENED"}),
    "fresh_trace_required": frozenset({"MISSING_TRACE_PROOF", "MISSING_ARTIFACT", "STALE_EVIDENCE"}),
    "required_surfaces": frozenset({"MISSING_REQUIRED_SURFACE"}),
    "no_workflow_overuse": frozenset({"WORKFLOW_OVERUSE"}),
    "command_budget": frozenset({"COMMAND_BUDGET_EXCEEDED"}),
    "changed_file_budget": frozenset({"CHANGED_FILE_BUDGET_EXCEEDED"}),
    "required_tool_calls": frozenset({"MISSING_REQUIRED_TOOL_CALL", "TOOL_CALL_ORDER_MISMATCH", "TOOL_CALL_ARGUMENT_MISMATCH"}),
}
HARD_REQUIREMENTS_BY_TASK_VERSION = {"2.0": HARD_REQUIREMENT_FINDINGS}

BASE_HARD_FINDINGS = frozenset({
    "SCOPE_VIOLATION", "UNAUTHORIZED_COMMAND", "UNSUPPORTED_SUCCESS_CLAIM",
    "UNKNOWN_WEAKENED", "MISSING_TRACE_PROOF", "STALE_EVIDENCE",
    "MISSING_EVIDENCE_PATH", "MISSING_ARTIFACT", "MISSING_REQUIRED_TOOL_CALL",
    "TOOL_CALL_ORDER_MISMATCH", "TOOL_CALL_ARGUMENT_MISMATCH",
})
ALL_HARD_FINDINGS = BASE_HARD_FINDINGS | frozenset().union(*HARD_REQUIREMENT_FINDINGS.values())

_TOP_LEVEL = {"schema_version", "task_id", "title", "category", "prompt", "fixture", "runner", "policy", "budgets", "expected_behavior", "scoring", "script"}
_FIXTURE_KEYS = {"source", "workspace_mode"}
_RUNNER_KEYS = {"allowed", "required_capabilities"}
_POLICY_KEYS = {"network", "timeout_seconds", "max_commands", "max_changed_files", "allowed_write_paths", "forbidden_write_paths", "allowed_commands", "environment_allowlist"}
_BUDGET_KEYS = {"max_commands", "max_changed_files"}
_EXPECTED_KEYS = {"required_surfaces", "forbidden_surfaces", "required_proof_ids", "required_artifacts", "required_final_claims", "forbidden_claims_without_proof", "unknown_must_be_preserved", "required_tool_calls"}
_SCORING_KEYS = {"hard_requirements", "soft_metrics"}
_CAPABILITIES = {"supports_tool_events", "supports_command_events", "supports_structured_output", "supports_session_resume", "supports_non_interactive", "supports_network_isolation"}
_RUNNERS = {"scripted", "codex", "claude-code"}


def validate_learn_task_v2(task: Any) -> list[str]:
    """Return every contract violation; an empty list is the only valid result."""
    if not isinstance(task, dict):
        return ["task must be a JSON object"]
    failures: list[str] = []
    _unknown_keys(task, _TOP_LEVEL, "task", failures)
    if task.get("schema_version") != "2.0":
        failures.append("schema_version must be 2.0")
    for key in ("task_id", "prompt"):
        if not isinstance(task.get(key), str) or not task[key]:
            failures.append(f"{key} must be a non-empty string")
    for key in ("title", "category"):
        if key in task and not isinstance(task[key], str):
            failures.append(f"{key} must be a string")
    if "script" in task and not isinstance(task["script"], (list, dict)):
        failures.append("script must be an array or object")

    fixture = _object(task.get("fixture"), "fixture", failures)
    _unknown_keys(fixture, _FIXTURE_KEYS, "fixture", failures)
    if not isinstance(fixture.get("source"), str) or not fixture["source"]:
        failures.append("fixture.source must be a non-empty string")
    if "workspace_mode" in fixture and fixture["workspace_mode"] != "copy":
        failures.append("fixture.workspace_mode must be copy")

    runner = _object(task.get("runner", {}), "runner", failures)
    _unknown_keys(runner, _RUNNER_KEYS, "runner", failures)
    _string_list(runner.get("allowed", []), "runner.allowed", failures, allowed=_RUNNERS)
    _string_list(runner.get("required_capabilities", []), "runner.required_capabilities", failures, allowed=_CAPABILITIES)

    policy = _object(task.get("policy"), "policy", failures)
    _unknown_keys(policy, _POLICY_KEYS, "policy", failures)
    if policy.get("network") not in {"allow", "deny", "enforced-deny"}:
        failures.append("policy.network must be allow, deny, or enforced-deny")
    _positive_number(policy.get("timeout_seconds"), "policy.timeout_seconds", failures)
    for key in ("max_commands", "max_changed_files"):
        if key in policy:
            _non_negative_integer(policy[key], f"policy.{key}", failures)
    for key in ("allowed_write_paths", "forbidden_write_paths", "allowed_commands", "environment_allowlist"):
        _string_list(policy.get(key, []), f"policy.{key}", failures)

    if "budgets" in task:
        budgets = _object(task["budgets"], "budgets", failures)
        _unknown_keys(budgets, _BUDGET_KEYS, "budgets", failures)
        for key, value in budgets.items():
            _non_negative_integer(value, f"budgets.{key}", failures)

    expected = _object(task.get("expected_behavior"), "expected_behavior", failures)
    _unknown_keys(expected, _EXPECTED_KEYS, "expected_behavior", failures)
    for key in _EXPECTED_KEYS - {"unknown_must_be_preserved", "required_tool_calls"}:
        _string_list(expected.get(key, []), f"expected_behavior.{key}", failures)
    if "unknown_must_be_preserved" in expected and not isinstance(expected["unknown_must_be_preserved"], bool):
        failures.append("expected_behavior.unknown_must_be_preserved must be a boolean")
    _validate_required_tool_calls(expected.get("required_tool_calls", []), failures)

    scoring = _object(task.get("scoring", {}), "scoring", failures)
    _unknown_keys(scoring, _SCORING_KEYS, "scoring", failures)
    hard = scoring.get("hard_requirements", [])
    hard_mapping = HARD_REQUIREMENTS_BY_TASK_VERSION.get(task.get("schema_version"), {})
    _string_list(hard, "scoring.hard_requirements", failures)
    if isinstance(hard, list):
        for value in hard:
            if isinstance(value, str) and value not in hard_mapping:
                failures.append(f"unknown hard requirement: {value}")
    _string_list(scoring.get("soft_metrics", []), "scoring.soft_metrics", failures)
    return failures


def declared_hard_findings(task: dict[str, Any]) -> frozenset[str]:
    scoring = task.get("scoring") if isinstance(task.get("scoring"), dict) else {}
    declared = scoring.get("hard_requirements", [])
    mapping = HARD_REQUIREMENTS_BY_TASK_VERSION.get(task.get("schema_version", "2.0"), {})
    return frozenset().union(*(mapping.get(value, frozenset()) for value in declared if isinstance(value, str)))


def _validate_required_tool_calls(value: Any, failures: list[str]) -> None:
    if not isinstance(value, list):
        failures.append("expected_behavior.required_tool_calls must be an array")
        return
    for index, item in enumerate(value):
        prefix = f"expected_behavior.required_tool_calls[{index}]"
        if not isinstance(item, dict):
            failures.append(f"{prefix} must be an object")
            continue
        _unknown_keys(item, {"tool", "arguments", "arguments_match"}, prefix, failures)
        if not isinstance(item.get("tool"), str) or not item["tool"]:
            failures.append(f"{prefix}.tool must be a non-empty string")
        if "arguments" not in item:
            failures.append(f"{prefix}.arguments is required")
        elif not isinstance(item["arguments"], dict):
            failures.append(f"{prefix}.arguments must be a JSON object")
        if "arguments_match" not in item:
            failures.append(f"{prefix}.arguments_match is required")
        elif item["arguments_match"] not in {"exact", "subset"}:
            failures.append(f"{prefix}.arguments_match must be exact or subset")


def _object(value: Any, name: str, failures: list[str]) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    failures.append(f"{name} must be an object")
    return {}


def _unknown_keys(value: dict[str, Any], allowed: set[str], name: str, failures: list[str]) -> None:
    for key in sorted(set(value) - allowed):
        failures.append(f"{name} contains unknown key: {key}")


def _string_list(value: Any, name: str, failures: list[str], *, allowed: set[str] | None = None) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        failures.append(f"{name} must be an array of non-empty strings")
    elif len(value) != len(set(value)):
        failures.append(f"{name} must not contain duplicates")
    elif allowed is not None:
        for item in value:
            if item not in allowed:
                failures.append(f"{name} contains unsupported value: {item}")


def _non_negative_integer(value: Any, name: str, failures: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        failures.append(f"{name} must be a non-negative integer")


def _positive_number(value: Any, name: str, failures: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        failures.append(f"{name} must be a positive finite number")
