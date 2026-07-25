"""Map native and streamed Claude Code events to neutral record drafts."""

from __future__ import annotations

import json
from typing import Any

adapter_name = "claude_code"


def discover_group_ids(event: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    for owner in (event, message):
        for key in ("session_id", "conversation_id", "run_id"):
            if isinstance(owner.get(key), str) and owner[key]:
                values.add(owner[key])
    return values


def extract(event: dict[str, Any]) -> list[dict[str, Any]]:
    event_type = event.get("type")
    message = event.get("message") if isinstance(event.get("message"), dict) else {}
    timestamp = _timestamp(event, message)
    native = _native(event, message)
    if event_type == "system":
        return [
            _draft(
                "meta",
                native,
                timestamp,
                {
                    "source_type": "claude-code",
                    **_optional(
                        working_directory=event.get("cwd"),
                        git_branch=event.get("git_branch"),
                        model=event.get("model"),
                    ),
                },
                "meta",
            )
        ]
    if event_type not in {"user", "assistant"}:
        if event_type == "result" and isinstance(event.get("result"), str):
            return [_draft("assistant", native, timestamp, {"content": event["result"]}, "result")]
        return []

    blocks = message.get("content", event.get("content", []))
    if isinstance(blocks, str):
        return [_draft(event_type, native, timestamp, {"content": blocks}, "message")]
    if not isinstance(blocks, list):
        return []
    drafts: list[dict[str, Any]] = []
    text_parts: list[str] = []
    for position, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        block_native = block.get("id") if isinstance(block.get("id"), str) else native
        if kind == "text":
            text_parts.append(str(block.get("text", "")))
        elif kind == "thinking":
            drafts.append(
                _draft(
                    "reasoning",
                    block_native,
                    timestamp,
                    {
                        "content": str(block.get("thinking", block.get("text", ""))),
                        "public_export_allowed": False,
                    },
                    f"reasoning:{position}",
                )
            )
        elif kind == "tool_use":
            call_id = str(block.get("id") or "")
            arguments = block.get("input")
            drafts.append(
                _tool_call(
                    block_native or call_id,
                    timestamp,
                    call_id,
                    str(block.get("name") or "unknown"),
                    arguments,
                )
            )
        elif kind == "tool_result":
            call_id = str(block.get("tool_use_id") or "")
            drafts.append(
                _tool_result(
                    block_native or call_id,
                    timestamp,
                    call_id,
                    block.get("content"),
                )
            )
    if text_parts:
        drafts.insert(
            0,
            _draft(event_type, native, timestamp, {"content": "".join(text_parts)}, "message"),
        )
    return drafts


def _tool_call(
    native: str | None,
    timestamp: str | None,
    call_id: str,
    name: str,
    arguments: Any,
) -> dict[str, Any]:
    valid = isinstance(arguments, (dict, list))
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            valid = isinstance(parsed, (dict, list))
            arguments = parsed if valid else arguments
        except json.JSONDecodeError:
            valid = False
    return _draft(
        "tool_call",
        native,
        timestamp,
        {
            "tool_call_id": call_id,
            "tool_name": name,
            "arguments": arguments,
            "arguments_valid": valid,
        },
        f"tool-call:{call_id}",
    )


def _tool_result(
    native: str | None,
    timestamp: str | None,
    call_id: str,
    result: Any,
) -> dict[str, Any]:
    return _draft(
        "tool_result",
        native,
        timestamp,
        {"tool_call_id": call_id, "result": result},
        f"tool-result:{call_id}",
    )


def _draft(
    record_type: str,
    native_id: str | None,
    timestamp: str | None,
    fields: dict[str, Any],
    component: str,
) -> dict[str, Any]:
    return {
        "record_type": record_type,
        "native_id": native_id,
        "timestamp": timestamp,
        "fields": fields,
        "component": component,
    }


def _native(event: dict[str, Any], message: dict[str, Any]) -> str | None:
    for owner in (message, event):
        for key in ("id", "uuid", "message_id"):
            if isinstance(owner.get(key), str) and owner[key]:
                return owner[key]
    return None


def _timestamp(*owners: dict[str, Any]) -> str | None:
    for owner in owners:
        for key in ("timestamp", "created_at", "time"):
            if isinstance(owner.get(key), str) and owner[key]:
                return owner[key]
    return None


def _optional(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if isinstance(value, str)}
