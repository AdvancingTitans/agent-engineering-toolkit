"""Extract bounded Observations from canonical Agent Run Records."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .models import ObservationError

_FAILURE_STATUS = {"fail", "failed", "failure", "error"}
_ZERO_FAILURES = re.compile(r"\b0\s+(?:failed|failures|errors?)\b", re.IGNORECASE)
_FAILURE_TEXT = re.compile(r"\b(?:failed|failure|error)\b|失败|错误", re.IGNORECASE)


def extract_observations(
    records: list[dict[str, Any]],
    *,
    investigation_id: str,
    question: str = "",
) -> list[dict[str, Any]]:
    """Extract deterministic Observations without promoting them to verified facts."""
    # 方案第 4 节边界：Run Record 只生成 Observation，不在此处晋级为强证据。
    if not isinstance(investigation_id, str) or not investigation_id:
        raise ObservationError("investigation_id must be a non-empty string")
    if not isinstance(question, str):
        raise ObservationError("question must be a string")
    if not isinstance(records, list):
        raise ObservationError("records must be a list")

    observations: list[dict[str, Any]] = []
    source_refs: list[str] = []
    seen_record_ids: set[str] = set()
    for record in records:
        record_id, record_type = _validate_record(record)
        if record_id in seen_record_ids:
            raise ObservationError("record_id must be unique within one extraction")
        seen_record_ids.add(record_id)
        source_refs.append(record_id)
        observation = _extract_record(record, investigation_id)
        if observation is not None:
            observations.append(observation)

    if source_refs:
        ordered_source_refs = sorted(source_refs)
        observations.append(
            _observation(
                investigation_id=investigation_id,
                observation_type="run_sequence",
                statement=(
                    "The normalized run contains "
                    f"{len(source_refs)} records with declared source-order metadata."
                ),
                source_refs=ordered_source_refs,
                proves=[
                    "The normalized records declare source-order metadata for this run."
                ],
                does_not_prove=[
                    "The declared source order establishes wall-clock execution order.",
                    "Every native run event is present.",
                ],
                reliability="recorded_behavior",
                limitations=["sequence_is_limited_to_normalized_records"],
            )
        )
    if question.strip():
        from .relevance import filter_relevant_observations

        return filter_relevant_observations(observations, question)
    return observations


def _extract_record(
    record: dict[str, Any],
    investigation_id: str,
) -> dict[str, Any] | None:
    record_type = record["record_type"]
    record_id = record["record_id"]
    if record_type == "user":
        return None
    if record_type == "assistant":
        content = _required_string(record, "content")
        return _observation(
            investigation_id=investigation_id,
            observation_type="agent_statement",
            statement=f"The normalized run contains this agent statement: {content}",
            source_refs=[record_id],
            proves=["The normalized run contains the quoted agent statement."],
            does_not_prove=[
                "The agent statement is factually correct.",
                "The statement applies to the current workspace.",
                "The described action was authorized.",
            ],
            reliability="self_report",
            limitations=["agent_self_report"],
        )
    if record_type == "reasoning":
        content = _required_string(record, "content")
        return _observation(
            investigation_id=investigation_id,
            observation_type="agent_reasoning",
            statement=f"The normalized run contains this agent reasoning record: {content}",
            source_refs=[record_id],
            proves=["The normalized run contains the quoted reasoning record."],
            does_not_prove=[
                "Any factual proposition in the reasoning is true.",
                "Any contemplated action was executed.",
            ],
            reliability="self_report",
            limitations=["reasoning_is_not_fact_evidence"],
        )
    if record_type == "tool_call":
        tool_call_id = _required_string(record, "tool_call_id")
        tool_name = _required_string(record, "tool_name")
        arguments_json = _required_string(record, "arguments_json")
        return _observation(
            investigation_id=investigation_id,
            observation_type="agent_tool_call",
            statement=(
                f"The normalized run contains tool call {tool_call_id} "
                f"to {tool_name} with arguments {arguments_json}."
            ),
            source_refs=[record_id],
            proves=["The normalized run records this tool call and its arguments."],
            does_not_prove=[
                "The tool completed successfully.",
                "The call ran in the current workspace.",
                "A recorded result remains current.",
            ],
            reliability="recorded_behavior",
            limitations=["recorded_call_is_not_execution_proof"],
        )
    if record_type == "tool_result":
        tool_call_id = _required_string(record, "tool_call_id")
        result = _tool_result_content(record)
        failure = _indicates_failure(record, result)
        linked_record_id = record.get("linked_tool_call_record_id")
        result_source_refs = [record_id]
        if isinstance(linked_record_id, str) and linked_record_id:
            result_source_refs.append(linked_record_id)
        limitations = ["recorded_output_may_be_incomplete"]
        if failure:
            limitations.append("recorded_result_indicates_failure")
        if record.get("linked_tool_call_record_id") is None:
            limitations.append("tool_call_link_missing")
        return _observation(
            investigation_id=investigation_id,
            observation_type="agent_tool_result",
            statement=(
                f"The normalized run contains a result for tool call "
                f"{tool_call_id}: {result}"
            ),
            source_refs=result_source_refs,
            proves=["The normalized run contains this recorded tool result."],
            does_not_prove=[
                "The recorded output is complete or authentic.",
                "The tool ran in the current workspace.",
                "The result applies after the final code change.",
            ],
            reliability="recorded_tool_output",
            limitations=limitations,
        )
    if record_type == "meta":
        fields = [
            f"source_type={record.get('source_type', '')}",
            f"working_directory={record.get('working_directory', '')}",
            f"git_branch={record.get('git_branch', '')}",
            f"model={record.get('model', '')}",
        ]
        return _observation(
            investigation_id=investigation_id,
            observation_type="run_metadata",
            statement="The normalized run declares metadata: " + ", ".join(fields) + ".",
            source_refs=[record_id],
            proves=["The normalized run declares the listed metadata values."],
            does_not_prove=[
                "The declared metadata matches the current workspace.",
                "The metadata remained unchanged throughout the run.",
            ],
            reliability="recorded_behavior",
            limitations=["metadata_is_historical_run_context"],
        )
    raise ObservationError(f"unsupported record_type: {record_type}")


def _observation(
    *,
    investigation_id: str,
    observation_type: str,
    statement: str,
    source_refs: list[str],
    proves: list[str],
    does_not_prove: list[str],
    reliability: str,
    limitations: list[str],
) -> dict[str, Any]:
    if not does_not_prove:
        raise ObservationError("does_not_prove must not be empty")
    semantic = {
        "investigation_id": investigation_id,
        "type": observation_type,
        "statement": statement,
        "source_refs": source_refs,
    }
    observation_id = hashlib.sha256(_canonical_bytes(semantic)).hexdigest()
    return {
        "id": observation_id,
        "investigation_id": investigation_id,
        "type": observation_type,
        "statement": statement,
        "source_refs": list(source_refs),
        "proves": list(proves),
        "does_not_prove": list(does_not_prove),
        "reliability": reliability,
        "limitations": list(limitations),
    }


def _validate_record(record: Any) -> tuple[str, str]:
    if not isinstance(record, dict):
        raise ObservationError("each record must be an object")
    record_id = record.get("record_id")
    record_type = record.get("record_type")
    if not isinstance(record_id, str) or not record_id:
        raise ObservationError("record_id must be a non-empty string")
    if record_type not in {
        "meta",
        "user",
        "assistant",
        "reasoning",
        "tool_call",
        "tool_result",
    }:
        raise ObservationError("record_type is unsupported")
    return record_id, record_type


def _required_string(record: dict[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ObservationError(f"{field} must be a non-empty string")
    return value


def _tool_result_content(record: dict[str, Any]) -> str:
    result_text = record.get("result_text")
    if isinstance(result_text, str) and result_text:
        return result_text
    result_json = record.get("result_json")
    if isinstance(result_json, str) and result_json:
        return result_json
    raise ObservationError("tool_result must contain result_text or result_json")


def _indicates_failure(record: dict[str, Any], content: str) -> bool:
    parsed = _parse_json(record.get("result_json"))
    if isinstance(parsed, dict):
        exit_code = parsed.get("exit_code", parsed.get("exitCode"))
        if isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0:
            return True
        if parsed.get("is_error") is True or parsed.get("isError") is True:
            return True
        if parsed.get("success") is False:
            return True
        status = parsed.get("status")
        if isinstance(status, str) and status.lower() in _FAILURE_STATUS:
            return True
    searchable = _ZERO_FAILURES.sub("", content)
    return bool(_FAILURE_TEXT.search(searchable))


def _parse_json(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
