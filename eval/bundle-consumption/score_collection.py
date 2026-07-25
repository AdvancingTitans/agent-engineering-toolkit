#!/usr/bin/env python3
"""Score one measured multi-scenario consumer response without aggregation."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from scorer import evaluate, read_json


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


def score_collection(
    catalog_path: Path,
    bundle_root: Path,
    response: dict[str, Any] | None,
    *,
    consumer_id: str,
    consumer_available: bool,
    elapsed_seconds: float | None,
) -> dict[str, Any]:
    catalog = read_json(catalog_path)
    scenarios = catalog["scenarios"]
    reviews: dict[str, dict[str, Any]] = {}
    if consumer_available:
        if response is None or not isinstance(response.get("reviews"), list):
            raise ValueError("available consumer response must contain reviews")
        for item in response["reviews"]:
            if not isinstance(item, dict):
                raise ValueError("consumer review entries must be objects")
            scenario_id = item.get("scenario_id")
            review = item.get("review")
            if (
                not isinstance(scenario_id, str)
                or not isinstance(review, dict)
                or scenario_id in reviews
            ):
                raise ValueError("consumer review entries require unique scenario IDs")
            reviews[scenario_id] = review
        expected_ids = {item["scenario_id"] for item in scenarios}
        if set(reviews) != expected_ids:
            raise ValueError("consumer response must cover every catalog scenario exactly once")

    reports: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_id = scenario["scenario_id"]
        review = reviews.get(scenario_id)
        if review is not None and elapsed_seconds is not None:
            conclusion_ids = [
                item.get("id")
                for item in review.get("conclusions", [])
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
            review = dict(review)
            review["extensions"] = {
                "evaluation": {
                    "conclusion_elapsed_seconds": {
                        identifier: elapsed_seconds for identifier in conclusion_ids
                    }
                }
            }
        report = evaluate(
            bundle_root / scenario_id if consumer_available else None,
            review,
            scenario_id=scenario_id,
            consumer_id=consumer_id,
            expected_relevant_evidence_refs=scenario[
                "expected_relevant_evidence_refs"
            ],
            consumer_available=consumer_available,
        )
        report["method"]["external_agent_calls"] = 1 if consumer_available else 0
        reports.append(report)

    return {
        "schema_version": "bundle-consumption-measured-collection/v1",
        "report_kind": "bundle_consumption_measured_collection",
        "consumer_id": consumer_id,
        "consumer_status": "AVAILABLE" if consumer_available else "NOT_APPLICABLE",
        "scenario_count": len(reports),
        "scenarios": reports,
        "aggregate_score": None,
        "elapsed_seconds_to_complete_response": elapsed_seconds,
        "limitations": [
            "Synthetic fixtures do not establish general Agent accuracy.",
            "Metrics remain independent; no trust score is calculated.",
            (
                "Per-conclusion timing uses complete-response elapsed time as a "
                "measured upper bound, not token-level first-conclusion latency."
            ),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--response", type=Path)
    parser.add_argument("--consumer-id", required=True)
    parser.add_argument("--consumer-unavailable", action="store_true")
    parser.add_argument("--elapsed-seconds", type=float)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        response = read_json(args.response) if args.response is not None else None
        report = score_collection(
            args.catalog,
            args.bundle_root,
            response,
            consumer_id=args.consumer_id,
            consumer_available=not args.consumer_unavailable,
            elapsed_seconds=args.elapsed_seconds,
        )
        _atomic_json(args.output, report)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"collection scoring failed: {error}") from error


if __name__ == "__main__":
    main()
