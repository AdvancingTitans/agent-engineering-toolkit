"""Deterministic Before/After comparison."""

from __future__ import annotations

from typing import Any, Mapping


def compare_before_after(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare like-for-like metrics without creating a composite score."""
    if set(before) != set(after):
        return {
            "status": "UNKNOWN",
            "improved": [],
            "regressed": [],
            "unchanged": [],
            "unknown": sorted(set(before) ^ set(after)),
        }
    improved: list[str] = []
    regressed: list[str] = []
    unchanged: list[str] = []
    unknown: list[str] = []
    for key in sorted(before):
        left = before[key]
        right = after[key]
        if left == right:
            unchanged.append(key)
        elif _status_rank(left) is not None and _status_rank(right) is not None:
            if _status_rank(right) > _status_rank(left):
                improved.append(key)
            else:
                regressed.append(key)
        elif _number(left) and _number(right):
            if right > left:
                improved.append(key)
            else:
                regressed.append(key)
        else:
            unknown.append(key)
    status = "FAIL" if regressed else "PASS" if improved and not unknown else "UNKNOWN"
    return {
        "status": status,
        "improved": improved,
        "regressed": regressed,
        "unchanged": unchanged,
        "unknown": unknown,
    }


def _status_rank(value: Any) -> int | None:
    return {
        "FAIL": 0,
        "UNKNOWN": 1,
        "NOT_APPLICABLE": 1,
        "PASS": 2,
    }.get(value)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
