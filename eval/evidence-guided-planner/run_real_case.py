#!/usr/bin/env python3
"""Score the tracked real Codex scope-localization observation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _ratio(hit: int, total: int) -> float:
    return round(hit / total, 4) if total else 1.0


def score(gold: dict[str, Any], observations: dict[str, Any]) -> dict[str, Any]:
    decisions = gold["decisions"]
    required = {
        path
        for path, contract in decisions.items()
        if contract["disposition"] == "REQUIRED"
    }
    required_tests = set(gold["required_tests"])
    groups: dict[str, Any] = {}
    for name, observation in observations["groups"].items():
        response = observation["response"]
        predicted = {
            item["path"]: item
            for item in response["paths"]
            if not item["path"].startswith("tests/")
        }
        predicted_paths = set(predicted)
        gold_paths = set(decisions)
        disposition_hits = sum(
            predicted.get(path, {}).get("disposition") == contract["disposition"]
            for path, contract in decisions.items()
        )
        reference_hits = sum(
            bool(
                set(predicted.get(path, {}).get("evidence_refs", []))
                & set(contract["evidence_refs"])
            )
            for path, contract in decisions.items()
        )
        source_location_hits = sum(
            bool(predicted.get(path, {}).get("source_location"))
            for path in decisions
        )
        linkage_hits = 0
        for left, right in gold["required_linkages"]:
            left_links = set(predicted.get(left, {}).get("linked_with", []))
            right_links = set(predicted.get(right, {}).get("linked_with", []))
            linkage_hits += right in left_links or left in right_links
        unknown_text = "\n".join(response["unknowns"]).casefold()
        preserved_unknowns = [
            item["id"]
            for item in gold["required_unknowns"]
            if all(
                any(term.casefold() in unknown_text for term in alternatives)
                for alternatives in item["term_groups"]
            )
        ]
        tests = set(response["tests"])
        groups[name] = {
            "required_production_path_recall": _ratio(
                len(required & predicted_paths),
                len(required),
            ),
            "production_decision_precision": _ratio(
                len(gold_paths & predicted_paths),
                len(predicted_paths),
            ),
            "disposition_accuracy": _ratio(
                disposition_hits,
                len(decisions),
            ),
            "required_test_recall": _ratio(
                len(required_tests & tests),
                len(required_tests),
            ),
            "evidence_reference_coverage": _ratio(
                reference_hits,
                len(decisions),
            ),
            "source_location_coverage": _ratio(
                source_location_hits,
                len(decisions),
            ),
            "linkage_coverage": _ratio(
                linkage_hits,
                len(gold["required_linkages"]),
            ),
            "unknown_preservation_rate": _ratio(
                len(preserved_unknowns),
                len(gold["required_unknowns"]),
            ),
            "counts": {
                "production_decisions": len(predicted_paths),
                "required_tests_found": len(required_tests & tests),
                "preserved_unknowns": preserved_unknowns,
            },
            "usage": observation["usage"],
        }
    source = groups["source_only"]
    evidence = groups["v1_16_evidence_only"]
    planned = groups["v1_17_evidence_guided_plan"]
    metrics = (
        "required_production_path_recall",
        "production_decision_precision",
        "disposition_accuracy",
        "required_test_recall",
        "evidence_reference_coverage",
        "source_location_coverage",
        "linkage_coverage",
        "unknown_preservation_rate",
    )
    return {
        "schema_version": "evidence-guided-planner-real-result/1.0",
        "case_id": gold["case_id"],
        "sample": {
            "model": observations["runner"]["model"],
            "repetitions": observations["runner"]["repetitions"],
            "scope": "one real AET self-review case; not a general model-quality claim",
        },
        "groups": groups,
        "deltas_percentage_points": {
            "v1_17_plan_vs_source_only": {
                metric: round((planned[metric] - source[metric]) * 100, 2)
                for metric in metrics
            },
            "v1_17_plan_vs_v1_16_evidence_only": {
                metric: round((planned[metric] - evidence[metric]) * 100, 2)
                for metric in metrics
            },
        },
        "excluded_observations": observations["excluded_observations"],
        "status": "PASS",
    }


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=here / "real-case/gold.json")
    parser.add_argument(
        "--observations",
        type=Path,
        default=here / "real-case/observations.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = score(_load(args.gold), _load(args.observations))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
