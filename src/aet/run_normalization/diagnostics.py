"""Privacy-safe normalization diagnostics."""

from __future__ import annotations

from typing import Any


def diagnostic(
    code: str,
    severity: str,
    message: str,
    *,
    line: int | None = None,
    byte_offset: int | None = None,
    record_index: int | None = None,
    count: int | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    location = {
        key: item
        for key, item in (
            ("line", line),
            ("byte_offset", byte_offset),
            ("record_index", record_index),
        )
        if item is not None
    }
    if location:
        value["input_location"] = location
    if count is not None:
        value["count"] = count
    return value
