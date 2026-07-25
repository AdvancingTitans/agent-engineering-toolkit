"""Deterministic, minimal lexical relevance filtering for Observations."""

from __future__ import annotations

import re
from typing import Any

from .models import OBSERVATION_FIELDS, OBSERVATION_TYPES, ObservationError

_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+|[\u3400-\u9fff]+", re.IGNORECASE)
_STOP_TERMS = {
    "a",
    "an",
    "and",
    "are",
    "did",
    "do",
    "does",
    "for",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "was",
    "were",
}
_TEST_TERMS = {
    "test",
    "tests",
    "pytest",
    "unittest",
    "verification",
    "verify",
    "verified",
    "pass",
    "passed",
    "fail",
    "failed",
    "result",
    "command",
    "tool",
    "测试",
    "验证",
    "通过",
    "失败",
}


def filter_relevant_observations(
    observations: list[dict[str, Any]],
    question: str,
) -> list[dict[str, Any]]:
    """Return observations sharing deterministic lexical terms with a question."""
    if not isinstance(observations, list):
        raise ObservationError("observations must be a list")
    for observation in observations:
        _validate_observation(observation)
    if not isinstance(question, str):
        raise ObservationError("question must be a string")
    if not question.strip():
        return list(observations)

    question_terms = _terms(question)
    if question_terms & _TEST_TERMS:
        question_terms.update(_TEST_TERMS)
    if not question_terms:
        return list(observations)

    relevant: list[dict[str, Any]] = []
    for observation in observations:
        searchable = " ".join(
            [
                observation["type"],
                observation["statement"],
                *observation["proves"],
                *observation["limitations"],
            ]
        )
        if question_terms & _terms(searchable):
            relevant.append(observation)
    linked_source_refs = {
        reference
        for observation in relevant
        if observation["type"] in {"agent_tool_call", "agent_tool_result"}
        for reference in observation["source_refs"]
    }
    if linked_source_refs:
        for observation in observations:
            if observation in relevant or observation["type"] == "run_sequence":
                continue
            if (
                observation["type"] in {"agent_tool_call", "agent_tool_result"}
                and set(observation["source_refs"]) & linked_source_refs
            ):
                relevant.append(observation)
    return relevant


def _terms(value: str) -> set[str]:
    terms: set[str] = set()
    for match in _TOKEN_PATTERN.findall(value.lower()):
        if _is_cjk(match):
            terms.add(match)
            terms.update(match)
            terms.update(match[index : index + 2] for index in range(len(match) - 1))
        else:
            terms.add(match)
    return terms - _STOP_TERMS


def _is_cjk(value: str) -> bool:
    return bool(value) and all("\u3400" <= character <= "\u9fff" for character in value)


def _validate_observation(observation: Any) -> None:
    if not isinstance(observation, dict) or set(observation) != OBSERVATION_FIELDS:
        raise ObservationError("observation has unexpected fields")
    if observation.get("type") not in OBSERVATION_TYPES:
        raise ObservationError("observation type is unsupported")
    for field in ("id", "investigation_id", "statement"):
        if not isinstance(observation.get(field), str) or not observation[field]:
            raise ObservationError(f"observation {field} must be a non-empty string")
    for field in ("source_refs", "proves", "does_not_prove", "limitations"):
        value = observation.get(field)
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise ObservationError(f"observation {field} must be a string list")
    if not observation["source_refs"]:
        raise ObservationError("observation source_refs must not be empty")
    if not observation["proves"]:
        raise ObservationError("observation proves must not be empty")
    if not observation["does_not_prove"]:
        raise ObservationError("observation does_not_prove must not be empty")
