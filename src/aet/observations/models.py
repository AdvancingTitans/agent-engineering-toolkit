"""Observation v1 constants and validation errors."""

from __future__ import annotations


class ObservationError(ValueError):
    """A normalized Run Record cannot be represented as a valid Observation."""


OBSERVATION_TYPES = {
    "agent_statement",
    "agent_tool_call",
    "agent_tool_result",
    "agent_reasoning",
    "run_sequence",
    "run_metadata",
}

RELIABILITY_LEVELS = {
    "self_report",
    "recorded_behavior",
    "recorded_tool_output",
}

OBSERVATION_FIELDS = {
    "id",
    "investigation_id",
    "type",
    "statement",
    "source_refs",
    "proves",
    "does_not_prove",
    "reliability",
    "limitations",
}
