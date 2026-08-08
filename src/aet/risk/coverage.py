"""Coverage gates that prevent absence of evidence from becoming PASS."""

from __future__ import annotations

from .models import Coverage, RiskContext

_INCOMPLETE_CODES = {
    "malformed_record",
    "missing_tool_result",
    "orphan_tool_result",
    "partial_run",
    "repaired_record",
    "run_group_conflict",
    "truncated_tool_output",
}


def assess_coverage(context: RiskContext) -> Coverage:
    gaps = {item.code for item in context.diagnostics if item.code in _INCOMPLETE_CODES}
    calls = {
        str(item.get("record_id"))
        for item in context.records
        if item.get("record_type") == "tool_call"
    }
    linked = {
        str(item.get("linked_tool_call_record_id"))
        for item in context.records
        if item.get("record_type") == "tool_result" and item.get("linked_tool_call_record_id")
    }
    if calls - linked:
        gaps.add("missing_tool_result")
    if not context.records:
        gaps.add("empty_run")
    explicit_intent = context.intent.get("goal", {}).get("source_type") in {
        "explicit_user",
        "explicit_project",
    }
    if not explicit_intent:
        gaps.add("intent_not_explicit")
    checked = tuple(
        sorted(
            {str(item["id"]) for item in context.policy.assets}
            | {str(item["id"]) for item in context.policy.monitoring_surfaces}
        )
    )
    return Coverage(
        complete=not gaps,
        checked_surfaces=checked,
        gaps=tuple(sorted(gaps)),
        observability_gap=bool(gaps),
    )


__all__ = ["assess_coverage"]
