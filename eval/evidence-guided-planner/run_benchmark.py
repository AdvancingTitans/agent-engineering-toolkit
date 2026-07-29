#!/usr/bin/env python3
"""Evaluate frozen localization predictions without invoking a Planner."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_CATEGORIES = {
    "single_file_behavior": 4,
    "cross_module_behavior": 5,
    "schema_runtime": 3,
    "implementation_test": 3,
    "config_docs": 2,
    "protected_path": 1,
    "stale_evidence": 1,
    "unresolved_conflict": 1,
}
GROUPS = ("source_only", "bundle", "planner_protocol")
THRESHOLDS = {
    "required_path_recall": (">=", 0.90),
    "recommended_path_precision": (">=", 0.80),
    "required_test_recall": (">=", 0.85),
    "critical_linkage_omission_rate": ("<=", 0.10),
    "ungrounded_path_rate": ("<=", 0.05),
    "protected_path_rate": ("==", 0.0),
    "conflict_preservation_rate": ("==", 1.0),
    "unknown_preservation_rate": ("==", 1.0),
    "reference_resolution_rate": ("==", 1.0),
}


def evaluate(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    _validate_fixture_set(fixtures)
    group_results = {
        group: _evaluate_group(fixtures, group)
        for group in GROUPS
    }
    planner = group_results["planner_protocol"]
    gates = {
        metric: _meets(planner[metric], operator, target)
        for metric, (operator, target) in THRESHOLDS.items()
    }
    return {
        "schema_version": "evidence-guided-planner-benchmark/1.0",
        "fixture_count": len(fixtures),
        "categories": dict(sorted(Counter(item["category"] for item in fixtures).items())),
        "gold_provenance": {
            "status": "FROZEN",
            "method": "independently authored localization contracts",
            "generated_by_planner_under_test": False,
        },
        "groups": group_results,
        "planner_thresholds": {
            metric: {
                "operator": operator,
                "target": target,
                "actual": planner[metric],
                "pass": gates[metric],
            }
            for metric, (operator, target) in THRESHOLDS.items()
        },
        "status": "PASS" if all(gates.values()) else "FAIL",
    }


def _evaluate_group(
    fixtures: list[dict[str, Any]],
    group: str,
) -> dict[str, Any]:
    required_total = required_hit = 0
    test_total = test_hit = 0
    recommended_total = recommended_correct = 0
    ungrounded = protected = 0
    conflict_total = conflict_hit = 0
    unknown_total = unknown_hit = 0
    references_total = references_resolved = 0
    linkage_total = linkage_hit = 0
    explainable_total = explainable_hit = 0
    tokens: list[int] = []
    durations: list[float] = []
    for fixture in fixtures:
        gold = fixture["gold"]
        prediction = fixture["predictions"][group]
        required = set(gold["required_paths"])
        optional = set(gold["optional_paths"])
        forbidden = set(gold["forbidden_paths"])
        required_tests = set(gold["required_tests"])
        paths = set(prediction["paths"])
        tests = set(prediction["tests"])
        required_total += len(required)
        required_hit += len(required & paths)
        test_total += len(required_tests)
        test_hit += len(required_tests & tests)
        recommended_total += len(paths)
        recommended_correct += len(paths & (required | optional))
        ungrounded += len(paths - required - optional)
        protected += len(paths & forbidden)
        conflicts = set(gold["known_conflicts"])
        preserved_conflicts = set(prediction["preserved_conflicts"])
        conflict_total += len(conflicts)
        conflict_hit += len(conflicts & preserved_conflicts)
        unknowns = set(gold["known_unknowns"])
        preserved_unknowns = set(prediction["preserved_unknowns"])
        unknown_total += len(unknowns)
        unknown_hit += len(unknowns & preserved_unknowns)
        resolved, total = prediction["references"]
        references_resolved += resolved
        references_total += total
        linkage_total += len(required)
        linkage_hit += len(required & set(prediction["linked_paths"]))
        explainable_total += len(paths)
        explainable_hit += len(paths & set(prediction["explained_paths"]))
        tokens.append(prediction["tokens"])
        durations.append(prediction["duration_ms"])
    return {
        "required_path_recall": _ratio(required_hit, required_total),
        "recommended_path_precision": _ratio(
            recommended_correct,
            recommended_total,
        ),
        "required_test_recall": _ratio(test_hit, test_total),
        "critical_linkage_omission_rate": 1.0 - _ratio(
            linkage_hit,
            linkage_total,
        ),
        "ungrounded_path_rate": _ratio(ungrounded, recommended_total),
        "protected_path_rate": _ratio(protected, recommended_total),
        "conflict_preservation_rate": _ratio(
            conflict_hit,
            conflict_total,
            empty=1.0,
        ),
        "unknown_preservation_rate": _ratio(
            unknown_hit,
            unknown_total,
            empty=1.0,
        ),
        "reference_resolution_rate": _ratio(
            references_resolved,
            references_total,
            empty=1.0,
        ),
        "plan_explainability_rate": _ratio(
            explainable_hit,
            explainable_total,
            empty=1.0,
        ),
        "auxiliary": {
            "median_tokens": statistics.median(tokens),
            "p95_duration_ms": _percentile(durations, 0.95),
        },
        "counts": {
            "required_paths": required_total,
            "recommended_paths": recommended_total,
            "required_tests": test_total,
            "ungrounded_paths": ungrounded,
            "protected_paths": protected,
            "resolved_references": references_resolved,
            "references": references_total,
        },
    }


def _validate_fixture_set(fixtures: list[dict[str, Any]]) -> None:
    if len(fixtures) != 20:
        raise ValueError("benchmark requires exactly 20 frozen fixtures")
    identifiers = [item.get("fixture_id") for item in fixtures]
    if len(set(identifiers)) != len(identifiers) or None in identifiers:
        raise ValueError("fixture IDs must be unique")
    categories = Counter(item.get("category") for item in fixtures)
    if categories != Counter(EXPECTED_CATEGORIES):
        raise ValueError("fixture category distribution does not match the contract")
    for fixture in fixtures:
        if fixture.get("gold_status") != "FROZEN":
            raise ValueError("every Gold localization contract must be frozen")
        if set(fixture.get("predictions", {})) != set(GROUPS):
            raise ValueError("every fixture must contain all three comparison groups")
        for group in GROUPS:
            prediction = fixture["predictions"][group]
            if prediction.get("generated_by_planner_under_test") is not False:
                raise ValueError("frozen predictions may not be generated during evaluation")


def _ratio(numerator: int, denominator: int, *, empty: float = 0.0) -> float:
    if denominator == 0:
        return empty
    return round(numerator / denominator, 4)


def _percentile(values: list[float], fraction: float) -> float:
    selected = sorted(values)
    index = max(0, min(len(selected) - 1, int(len(selected) * fraction + 0.9999) - 1))
    return selected[index]


def _meets(actual: float, operator: str, target: float) -> bool:
    if operator == ">=":
        return actual >= target
    if operator == "<=":
        return actual <= target
    return actual == target


def _load(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("benchmark fixture file must contain an array of objects")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "fixtures",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "tests/fixtures/planning/localization-gold.json",
    )
    args = parser.parse_args(argv)
    try:
        result = evaluate(_load(args.fixtures))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        print(f"benchmark: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
