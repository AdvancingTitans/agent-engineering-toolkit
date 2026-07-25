"""Build unverified Evidence Candidates from bounded Observations."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from aet.observations import filter_relevant_observations
from aet.observations.models import OBSERVATION_FIELDS


class CandidateError(ValueError):
    """Observations cannot be represented as valid Evidence Candidates."""


_COMMAND_TOOL = re.compile(
    r"\b(?:bash|shell|command|terminal|exec|exec_command|run_command)\b",
    re.IGNORECASE,
)
_TEST_RESULT = re.compile(
    r"\b(?:test|tests|pytest|unittest|passed|failed)\b|测试|验证|通过|失败",
    re.IGNORECASE,
)


def build_evidence_candidates(
    observations: list[dict[str, Any]],
    *,
    investigation_id: str,
    question: str = "",
) -> list[dict[str, Any]]:
    """Build deterministic, unverified candidates without evidence promotion."""
    # 方案第 4 节边界：Reasoning 不得成为事实证据，运行记录最多生成 observed 候选。
    if not isinstance(investigation_id, str) or not investigation_id:
        raise CandidateError("investigation_id must be a non-empty string")
    if not isinstance(question, str):
        raise CandidateError("question must be a string")
    _validate_observations(observations, investigation_id)
    try:
        selected = filter_relevant_observations(observations, question)
    except ValueError as error:
        raise CandidateError(str(error)) from error

    candidates: list[dict[str, Any]] = []
    for observation in selected:
        observation_type = observation["type"]
        if observation_type in {"agent_reasoning", "run_metadata", "run_sequence"}:
            continue
        candidate = _candidate_for_observation(observation, investigation_id)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _candidate_for_observation(
    observation: dict[str, Any],
    investigation_id: str,
) -> dict[str, Any] | None:
    observation_type = observation["type"]
    if observation_type == "agent_statement":
        return _candidate(
            investigation_id=investigation_id,
            proposition=observation["statement"],
            candidate_type="agent_claim",
            observation=observation,
            proposed_evidence_kind="run_observation",
            proposed_strength="context_only",
            verification_plan=[
                {
                    "action": "verify_against_workspace",
                    "purpose": (
                        "Corroborate the agent statement with deterministic workspace evidence."
                    ),
                }
            ],
        )
    if observation_type == "agent_tool_call":
        candidate_type = (
            "command_observation"
            if _COMMAND_TOOL.search(observation["statement"])
            else "tool_observation"
        )
        return _candidate(
            investigation_id=investigation_id,
            proposition=observation["statement"],
            candidate_type=candidate_type,
            observation=observation,
            proposed_evidence_kind="command_receipt",
            proposed_strength="observed",
            verification_plan=[
                {
                    "action": "inspect_or_reproduce_tool_call",
                    "purpose": "Confirm execution, workspace binding, and result.",
                }
            ],
        )
    if observation_type == "agent_tool_result":
        failure = "recorded_result_indicates_failure" in observation["limitations"]
        candidate_type = "counter_evidence" if failure else "tool_observation"
        evidence_kind = (
            "test_result"
            if _TEST_RESULT.search(observation["statement"])
            else "command_receipt"
        )
        plan = (
            [
                {
                    "action": "investigate_counter_evidence",
                    "purpose": (
                        "Determine whether the recorded failure changes the target claim."
                    ),
                }
            ]
            if failure
            else [
                {
                    "action": "corroborate_or_reproduce_result",
                    "purpose": (
                        "Confirm completeness, workspace binding, and freshness."
                    ),
                }
            ]
        )
        return _candidate(
            investigation_id=investigation_id,
            proposition=observation["statement"],
            candidate_type=candidate_type,
            observation=observation,
            proposed_evidence_kind=evidence_kind,
            proposed_strength="observed",
            verification_plan=plan,
        )
    return None


def _candidate(
    *,
    investigation_id: str,
    proposition: str,
    candidate_type: str,
    observation: dict[str, Any],
    proposed_evidence_kind: str,
    proposed_strength: str,
    verification_plan: list[dict[str, str]],
) -> dict[str, Any]:
    semantic = {
        "investigation_id": investigation_id,
        "candidate_type": candidate_type,
        "observation_refs": [observation["id"]],
        "proposition": proposition,
    }
    candidate_id = hashlib.sha256(_canonical_bytes(semantic)).hexdigest()
    return {
        "id": candidate_id,
        "investigation_id": investigation_id,
        "proposition": proposition,
        "candidate_type": candidate_type,
        "observation_refs": [observation["id"]],
        "source_refs": list(dict.fromkeys(observation["source_refs"])),
        "verification_required": True,
        "proposed_evidence_kind": proposed_evidence_kind,
        "proposed_strength": proposed_strength,
        "status": "unverified",
        "verification_plan": verification_plan,
    }


def _validate_observations(
    observations: Any,
    investigation_id: str,
) -> None:
    if not isinstance(observations, list):
        raise CandidateError("observations must be a list")
    seen_ids: set[str] = set()
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) != OBSERVATION_FIELDS:
            raise CandidateError("observation has unexpected fields")
        if observation.get("investigation_id") != investigation_id:
            raise CandidateError("observation investigation_id does not match")
        observation_id = observation.get("id")
        if not isinstance(observation_id, str) or not observation_id:
            raise CandidateError("observation id must be a non-empty string")
        if observation_id in seen_ids:
            raise CandidateError("observation id must be unique")
        seen_ids.add(observation_id)
        for field in ("source_refs", "proves", "does_not_prove", "limitations"):
            value = observation.get(field)
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item for item in value
            ):
                raise CandidateError(f"observation {field} must be a string list")
        if not observation["does_not_prove"]:
            raise CandidateError("observation does_not_prove must not be empty")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
