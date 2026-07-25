"""Map native and streamed Codex events to neutral record drafts."""

from __future__ import annotations

import json
from typing import Any

adapter_name = "codex"


def discover_group_ids(event: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    for owner in (event, payload):
        for key in ("thread_id", "session_id", "run_id"):
            if isinstance(owner.get(key), str) and owner[key]:
                values.add(owner[key])
    if event.get("type") == "session_meta" and isinstance(payload.get("id"), str):
        values.add(payload["id"])
    return values


def extract(event: dict[str, Any]) -> list[dict[str, Any]]:
    event_type = event.get("type")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    timestamp = _timestamp(event, payload)
    native = _native(event, payload)
    drafts: list[dict[str, Any]] = []

    if event_type in {"session_meta", "turn_context"}:
        drafts.append(
            _draft(
                "meta",
                native,
                timestamp,
                {
                    "source_type": "codex",
                    **_optional(
                        working_directory=payload.get("cwd"),
                        git_branch=payload.get("git_branch") or _nested(payload, "git", "branch"),
                        model=payload.get("model"),
                    ),
                },
                "meta",
            )
        )
        return drafts

    if event_type in {"response_item", "event_msg"}:
        return _payload_records(payload, native, timestamp)

    item = event.get("item") if isinstance(event.get("item"), dict) else {}
    if item and event_type in {"item.completed", "item.started", "item.updated"}:
        if event_type != "item.completed":
            return []
        item_native = item.get("id") if isinstance(item.get("id"), str) else native
        item_type = item.get("type")
        if item_type == "command_execution":
            call_id = str(item.get("id") or f"command:{item.get('command', '')}")
            arguments = {"command": item.get("command", "")}
            drafts.append(_tool_call(item_native, timestamp, call_id, "shell", arguments))
            result = {
                "exit_code": item.get("exit_code"),
                "output": item.get("aggregated_output", ""),
            }
            drafts.append(_tool_result(item_native, timestamp, call_id, result))
        elif item_type in {"mcp_tool_call", "tool_call"}:
            call_id = str(item.get("call_id") or item.get("id") or "")
            drafts.append(
                _tool_call(
                    item_native,
                    timestamp,
                    call_id,
                    str(item.get("tool") or item.get("name") or "unknown"),
                    item.get("arguments"),
                )
            )
            if "result" in item or "output" in item:
                drafts.append(
                    _tool_result(
                        item_native,
                        timestamp,
                        call_id,
                        item.get("result", item.get("output")),
                    )
                )
        elif item_type == "agent_message":
            drafts.append(_draft("assistant", item_native, timestamp, {"content": str(item.get("text", ""))}, "message"))
        return drafts

    if event_type in {"user", "assistant"}:
        content = event.get("content")
        if isinstance(content, str):
            drafts.append(_draft(event_type, native, timestamp, {"content": content}, "message"))
            return drafts
    return drafts


def _payload_records(
    payload: dict[str, Any],
    native: str | None,
    timestamp: str | None,
) -> list[dict[str, Any]]:
    kind = payload.get("type")
    if kind == "message":
        role = payload.get("role")
        record_type = "user" if role == "user" else "assistant" if role == "assistant" else None
        if record_type is None:
            return []
        text = _content_text(payload.get("content"))
        return [_draft(record_type, native, timestamp, {"content": text}, "message")]
    if kind in {"user_message", "agent_message"}:
        record_type = "user" if kind == "user_message" else "assistant"
        content = payload.get("message", payload.get("text", ""))
        return [_draft(record_type, native, timestamp, {"content": _content_text(content)}, "message")]
    if kind in {"reasoning", "agent_reasoning"}:
        content = payload.get("text", payload.get("content", payload.get("summary", "")))
        return [
            _draft(
                "reasoning",
                native,
                timestamp,
                {"content": _content_text(content), "public_export_allowed": False},
                "reasoning",
            )
        ]
    if kind in {"function_call", "custom_tool_call"}:
        call_id = str(payload.get("call_id") or payload.get("id") or "")
        name = str(payload.get("name") or payload.get("tool") or "unknown")
        arguments = payload.get("arguments", payload.get("input"))
        return [_tool_call(native or call_id, timestamp, call_id, name, arguments)]
    if kind in {"function_call_output", "custom_tool_call_output"}:
        call_id = str(payload.get("call_id") or payload.get("tool_call_id") or "")
        return [_tool_result(native or call_id, timestamp, call_id, payload.get("output", payload.get("result")))]
    return []


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
        native or call_id or None,
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
        native or call_id or None,
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


def _native(event: dict[str, Any], payload: dict[str, Any]) -> str | None:
    for owner in (payload, event):
        for key in ("id", "uuid", "call_id", "item_id"):
            if isinstance(owner.get(key), str) and owner[key]:
                return owner[key]
    return None


def _timestamp(*owners: dict[str, Any]) -> str | None:
    for owner in owners:
        for key in ("timestamp", "created_at", "time"):
            if isinstance(owner.get(key), str) and owner[key]:
                return owner[key]
    return None


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            str(item.get("text", ""))
            for item in value
            if isinstance(item, dict) and item.get("type") in {"input_text", "output_text", "text"}
        )
    if isinstance(value, dict):
        return str(value.get("text", ""))
    return ""


def _optional(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if isinstance(value, str)}


def _nested(value: dict[str, Any], first: str, second: str) -> Any:
    child = value.get(first)
    return child.get(second) if isinstance(child, dict) else None
