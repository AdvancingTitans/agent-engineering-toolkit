#!/usr/bin/env python3
"""Score AET Quick investigation benchmark runs without an LLM judge."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any


HERE = Path(__file__).resolve().parent


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("aet_quick_benchmark_runner", HERE / "runner.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load benchmark runner contract")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = _load_runner()
GROUPS = RUNNER.GROUPS


def _known(value: Any) -> dict[str, Any]:
    return {"status": "EVIDENCED", "value": value}


def _unknown() -> dict[str, Any]:
    return {"status": "UNKNOWN", "value": None}


def _read_annotations(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    document = RUNNER.read_json(path)
    if document.get("schema_version") != "quick-investigation-annotations/v1":
        raise ValueError("unsupported annotations schema")
    rows = document.get("annotations")
    if not isinstance(rows, list):
        raise ValueError("annotations must be an array")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("run_id"), str):
            raise ValueError("each annotation requires run_id")
        if row["run_id"] in result:
            raise ValueError(f"duplicate annotation: {row['run_id']}")
        review = row.get("manual_review_seconds")
        understanding = row.get("user_understanding")
        if review is not None and (
            not isinstance(review, (int, float))
            or isinstance(review, bool)
            or not math.isfinite(review)
            or review < 0
        ):
            raise ValueError(f"invalid manual review time: {row['run_id']}")
        if understanding is not None and understanding not in {"CORRECT", "PARTIAL", "INCORRECT"}:
            raise ValueError(f"invalid user understanding annotation: {row['run_id']}")
        if review is None and understanding is None:
            raise ValueError(f"annotation has no human value: {row['run_id']}")
        result[row["run_id"]] = row
    return result


def _mean(values: list[float | int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _metric(values: list[float | int]) -> dict[str, Any]:
    return {"total": sum(values), "mean": _mean(values)}


def _usage_metric(group_runs: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [
        run["usage"][key]
        for run in group_runs
        if run["usage"].get("status") == "EVIDENCED"
    ]
    if not values:
        return {"status": "UNKNOWN", "observed_runs": 0, "total": None, "mean": None}
    return {
        "status": "EVIDENCED" if len(values) == len(group_runs) else "PARTIAL",
        "observed_runs": len(values),
        "total": sum(values),
        "mean": _mean(values),
    }


def score_run(
    run: dict[str, Any],
    scenario: dict[str, Any],
    annotation: dict[str, Any] | None,
) -> dict[str, Any]:
    expected = set(scenario["expected_claim_ids"])
    claims = run.get("output", {}).get("claims", [])
    emitted = {
        claim["claim_id"]
        for claim in claims
        if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)
    }
    true_positives = expected & emitted
    false_positives = emitted - expected
    evidence_ids = {
        item["id"]
        for item in scenario["evidence"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    ungrounded: list[str] = []
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("claim_id"), str):
            continue
        refs = claim.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(ref not in evidence_ids for ref in refs):
            ungrounded.append(claim["claim_id"])
    review_value = (
        _known(annotation["manual_review_seconds"])
        if annotation is not None and "manual_review_seconds" in annotation
        else _unknown()
    )
    understanding_value = (
        _known(annotation["user_understanding"])
        if annotation is not None and "user_understanding" in annotation
        else _unknown()
    )
    return {
        "run_id": run["run_id"],
        "group": run["group"],
        "scenario_id": run["scenario_id"],
        "expected_claim_ids": sorted(expected),
        "emitted_claim_ids": sorted(emitted),
        "true_positive_claim_ids": sorted(true_positives),
        "false_positive_claim_ids": sorted(false_positives),
        "ungrounded_claim_ids": sorted(set(ungrounded)),
        "manual_review_seconds": review_value,
        "user_understanding": understanding_value,
    }


def _human_summary(
    run_scores: list[dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    values = [
        item[field]["value"]
        for item in run_scores
        if item[field]["status"] == "EVIDENCED"
    ]
    if not values:
        return {"status": "UNKNOWN", "annotated_runs": 0, "value": None}
    if field == "manual_review_seconds":
        return {
            "status": "EVIDENCED",
            "annotated_runs": len(values),
            "value": {"total": sum(values), "mean": _mean(values)},
        }
    return {
        "status": "EVIDENCED",
        "annotated_runs": len(values),
        "value": {
            state: sum(value == state for value in values)
            for state in ("CORRECT", "PARTIAL", "INCORRECT")
        },
    }


def score(
    suite_path: Path,
    runs_root: Path,
    annotations_path: Path | None = None,
) -> dict[str, Any]:
    suite = RUNNER.load_suite(suite_path)
    scenarios = {item["scenario_id"]: item for item in suite["scenarios"]}
    annotations = _read_annotations(annotations_path)
    runs: list[dict[str, Any]] = []
    if runs_root.is_file():
        bundle = RUNNER.read_json(runs_root)
        if bundle.get("schema_version") != "quick-investigation-normalized-runs/v1":
            raise ValueError("unsupported normalized Runs bundle")
        bundle_runs = bundle.get("runs")
        if not isinstance(bundle_runs, list):
            raise ValueError("normalized Runs bundle requires a runs array")
        sources = [(runs_root, run) for run in bundle_runs]
    else:
        sources = [
            (path, RUNNER.read_json(path))
            for path in sorted(runs_root.rglob("run.json"))
        ]
    for path, run in sources:
        if not isinstance(run, dict):
            raise ValueError(f"Run must be an object: {path}")
        if run.get("schema_version") != "quick-investigation-run/v1":
            raise ValueError(f"unsupported run schema: {path}")
        if run.get("suite_id") != suite["suite_id"]:
            raise ValueError(f"run belongs to another suite: {path}")
        if run.get("scenario_id") not in scenarios or run.get("group") not in GROUPS:
            raise ValueError(f"run has an unknown scenario or group: {path}")
        runs.append(run)
    if not runs:
        raise ValueError("no run.json files found")
    run_ids = [run["run_id"] for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("run IDs must be unique")
    unknown_annotations = sorted(set(annotations) - set(run_ids))
    if unknown_annotations:
        raise ValueError(f"annotations reference unknown runs: {', '.join(unknown_annotations)}")

    scores = [
        score_run(run, scenarios[run["scenario_id"]], annotations.get(run["run_id"]))
        for run in runs
    ]
    by_group: dict[str, Any] = {}
    for group in GROUPS:
        group_runs = [run for run in runs if run["group"] == group]
        group_scores = [item for item in scores if item["group"] == group]
        if not group_runs:
            continue
        expected_count = sum(len(item["expected_claim_ids"]) for item in group_scores)
        true_positive_count = sum(len(item["true_positive_claim_ids"]) for item in group_scores)
        emitted_count = sum(len(item["emitted_claim_ids"]) for item in group_scores)
        false_positive_count = sum(len(item["false_positive_claim_ids"]) for item in group_scores)
        ungrounded_count = sum(len(item["ungrounded_claim_ids"]) for item in group_scores)
        usage = {
            key: _usage_metric(group_runs, key)
            for key in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")
        }
        by_group[group] = {
            "run_count": len(group_runs),
            "effective_recall": {
                "true_positive_claims": true_positive_count,
                "expected_claims": expected_count,
                "rate": true_positive_count / expected_count if expected_count else 1.0,
            },
            "false_discovery_proportion": {
                "count": false_positive_count,
                "emitted_claims": emitted_count,
                "rate": false_positive_count / emitted_count if emitted_count else 0.0,
            },
            "ungrounded_conclusions": {
                "count": ungrounded_count,
                "emitted_claims": emitted_count,
                "rate": ungrounded_count / emitted_count if emitted_count else 0.0,
            },
            "grounding_rejections": {
                "count": sum(
                    len(run.get("grounding", {}).get("rejected_claims", []))
                    for run in group_runs
                ),
                "runs_rejected": sum(
                    run.get("grounding", {}).get("status") == "REJECTED"
                    for run in group_runs
                ),
            },
            "tool_calls": _metric([run["tool_calls"] for run in group_runs]),
            "wall_time_seconds": _metric([run["wall_time_seconds"] for run in group_runs]),
            "tokens": usage,
            "manual_review_seconds": _human_summary(group_scores, "manual_review_seconds"),
            "user_understanding": _human_summary(group_scores, "user_understanding"),
        }
    return {
        "schema_version": "quick-investigation-report/v1",
        "report_kind": "quick_investigation_benchmark",
        "suite_id": suite["suite_id"],
        "groups": by_group,
        "runs": scores,
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=HERE / "fixtures" / "scope-scenarios.json")
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = score(args.suite, args.runs, args.annotations)
        _atomic_json(args.output, report)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"quick investigation scoring failed: {exc}") from exc
    print(json.dumps({"output": str(args.output), "groups": sorted(report["groups"])}, sort_keys=True))


if __name__ == "__main__":
    main()
