"""Deliberately flawed adapter used by the README case study."""

from __future__ import annotations

from typing import Any


def normalize_findings(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Normalize a tool result for a coding Agent."""
    if not rows:
        return {
            "status": "ok",
            "facts": ["No security issues were found."],
        }
    return {"status": "ok", "facts": rows}
