"""Stable constants for Agent Run Normalization v1."""

from __future__ import annotations

NORMALIZATION_SCHEMA = "agent-run-normalization/1.0"
RUN_RECORD_SCHEMA = "canonical-run-record/1.0"
NORMALIZER_VERSION = "1.0.0"
ADAPTER_VERSION = "1.0.0"

RECORD_TYPES = {
    "meta",
    "user",
    "assistant",
    "reasoning",
    "tool_call",
    "tool_result",
}
IDENTITY_KINDS = {"native", "location", "content", "synthetic"}
