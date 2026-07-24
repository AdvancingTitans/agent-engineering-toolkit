"""Budget and stopping rules for bounded Quick investigations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


@dataclass(frozen=True)
class CommandBudget:
    wall_time_seconds: float
    llm_calls: int
    tool_calls: int
    remote_calls: int
    expensive_calls: int
    findings: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CommandBudget":
        limits = value.get("limits")
        if not isinstance(limits, dict):
            raise ValueError("command budget requires limits")
        fields = (
            "wall_time_seconds",
            "llm_calls",
            "tool_calls",
            "remote_calls",
            "expensive_calls",
            "findings",
        )
        parsed: dict[str, int | float] = {}
        for field in fields:
            item = limits.get(field)
            if not isinstance(item, (int, float)) or isinstance(item, bool) or item < 0:
                raise ValueError(f"command budget {field} must be non-negative")
            parsed[field] = item
        return cls(**parsed)


class StopDecision(StrEnum):
    CONTINUE = "CONTINUE"
    DOMINANT_EXPLANATION = "DOMINANT_EXPLANATION"
    ACTION_UNCHANGED = "ACTION_UNCHANGED"
    NO_NEW_DECISION_VALUE = "NO_NEW_DECISION_VALUE"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    USER_INPUT_REQUIRED = "USER_INPUT_REQUIRED"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"


def evaluate_stop(
    *,
    dominant_explanation: bool = False,
    counter_hypothesis_checked: bool = False,
    action_would_change: bool = True,
    consecutive_no_value_calls: int = 0,
    budget_exhausted: bool = False,
    authorization_required: bool = False,
    user_input_required: bool = False,
    tool_unavailable: bool = False,
) -> StopDecision:
    if budget_exhausted:
        return StopDecision.BUDGET_EXHAUSTED
    if authorization_required:
        return StopDecision.AUTHORIZATION_REQUIRED
    if user_input_required:
        return StopDecision.USER_INPUT_REQUIRED
    if tool_unavailable:
        return StopDecision.TOOL_UNAVAILABLE
    if dominant_explanation and counter_hypothesis_checked:
        return StopDecision.DOMINANT_EXPLANATION
    if not action_would_change:
        return StopDecision.ACTION_UNCHANGED
    if consecutive_no_value_calls >= 2:
        return StopDecision.NO_NEW_DECISION_VALUE
    return StopDecision.CONTINUE
