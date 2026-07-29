#!/usr/bin/env python3
"""Compare two aggregate snapshots without implying channel causality."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


METRICS = (
    "stars",
    "forks",
    "watchers",
    "open_issues",
    "contributors",
    "pull_requests",
    "traffic_views",
    "traffic_unique_visitors",
    "clones",
    "release_downloads",
    "skills_installs",
)


def evaluate(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    if baseline.get("schema_version") != "aet-growth-snapshot/v1":
        raise ValueError("baseline schema_version must be aet-growth-snapshot/v1")
    if current.get("schema_version") != "aet-growth-snapshot/v1":
        raise ValueError("current schema_version must be aet-growth-snapshot/v1")
    if baseline.get("repository") != current.get("repository"):
        raise ValueError("baseline and current repository differ")
    deltas: dict[str, Any] = {}
    diagnostics: list[str] = []
    for name in METRICS:
        before = baseline.get(name, {})
        after = current.get(name, {})
        if before.get("status") == after.get("status") == "KNOWN":
            before_value = before.get("value")
            after_value = after.get("value")
            if isinstance(before_value, (int, float)) and isinstance(
                after_value, (int, float)
            ):
                deltas[name] = {"status": "KNOWN", "value": after_value - before_value}
                continue
        deltas[name] = {
            "status": "UNKNOWN",
            "value": None,
            "diagnostic": "one or both observations are not KNOWN numeric values",
        }

    star_delta = deltas["stars"]
    unique_delta = deltas["traffic_unique_visitors"]
    if (
        star_delta["status"] == "KNOWN"
        and unique_delta["status"] == "KNOWN"
        and unique_delta["value"] > 0
    ):
        conversion = {
            "status": "KNOWN",
            "value": star_delta["value"] / unique_delta["value"],
        }
    else:
        conversion = {
            "status": "UNKNOWN",
            "value": None,
            "diagnostic": "requires KNOWN deltas and unique visitors > 0",
        }
    if baseline.get("observed_at") == current.get("observed_at"):
        diagnostics.append("baseline and current are the same observation; all known deltas are zero")
    return {
        "schema_version": "aet-growth-evaluation/v1",
        "repository": baseline["repository"],
        "baseline_observed_at": baseline.get("observed_at"),
        "current_observed_at": current.get("observed_at"),
        "deltas": deltas,
        "stars_per_unique_visitor": conversion,
        "diagnostics": diagnostics,
        "causality_statement": "This comparison is descriptive and does not attribute Stars to a channel.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        current = json.loads(args.current.read_text(encoding="utf-8"))
        print(json.dumps(evaluate(baseline, current), indent=2, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"growth evaluation failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
