#!/usr/bin/env python3
"""Run deterministic Portable Bundle consumption evaluation without external Agents."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from scorer import evaluate, read_json


HERE = Path(__file__).resolve().parent


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _expectations(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    value = read_json(path).get("expected_relevant_evidence_refs")
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError("expected_relevant_evidence_refs must contain strings")
    return value


def run_suite(path: Path) -> dict[str, Any]:
    suite = read_json(path)
    if suite.get("schema_version") != "bundle-consumption-scenarios/v1":
        raise ValueError("unsupported scenario suite")
    scenarios = suite.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 10:
        raise ValueError("scenario suite must contain exactly ten scenarios")
    reports: list[dict[str, Any]] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("scenario entries must be objects")
        available = scenario.get("availability") == "available"
        bundle = (
            (path.parent / scenario["bundle"]).resolve()
            if available
            else None
        )
        review = (
            read_json((path.parent / scenario["review"]).resolve())
            if available
            else None
        )
        reports.append(
            evaluate(
                bundle,
                review,
                scenario_id=scenario["scenario_id"],
                consumer_id=scenario["consumer_id"],
                expected_relevant_evidence_refs=scenario.get(
                    "expected_relevant_evidence_refs"
                ),
                consumer_available=available,
            )
        )
    return {
        "schema_version": "bundle-consumption-suite-report/v1",
        "report_kind": "bundle_consumption_suite_report",
        "suite_id": suite["suite_id"],
        "scenario_count": len(reports),
        "scenarios": reports,
        "aggregate_score": None,
        "limitations": [
            "Scenario metrics remain independent; no trust score is calculated."
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--expectations", type=Path)
    parser.add_argument("--suite", type=Path)
    parser.add_argument("--scenario-id", default="local-evaluation")
    parser.add_argument("--consumer-id", default="structured-review-consumer")
    parser.add_argument("--consumer-unavailable", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.suite is not None:
            if args.bundle is not None or args.review is not None:
                raise ValueError("--suite cannot be combined with --bundle or --review")
            report = run_suite(args.suite)
        else:
            review = read_json(args.review) if args.review is not None else None
            report = evaluate(
                args.bundle,
                review,
                scenario_id=args.scenario_id,
                consumer_id=args.consumer_id,
                expected_relevant_evidence_refs=_expectations(args.expectations),
                consumer_available=not args.consumer_unavailable,
            )
        _atomic_json(args.output, report)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"bundle consumption evaluation failed: {error}") from error


if __name__ == "__main__":
    main()
