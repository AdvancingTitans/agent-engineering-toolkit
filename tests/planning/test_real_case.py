from __future__ import annotations

import json
import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(
    str(ROOT / "eval/evidence-guided-planner/run_real_case.py")
)


class RealPlannerCaseTests(unittest.TestCase):
    def test_tracked_real_case_preserves_dimension_level_results(self) -> None:
        load = MODULE["_load"]
        score = MODULE["score"]
        result = score(
            load(ROOT / "eval/evidence-guided-planner/real-case/gold.json"),
            load(
                ROOT
                / "eval/evidence-guided-planner/real-case/observations.json"
            ),
        )
        source = result["groups"]["source_only"]
        evidence = result["groups"]["v1_16_evidence_only"]
        planned = result["groups"]["v1_17_evidence_guided_plan"]
        self.assertEqual(1.0, source["required_production_path_recall"])
        self.assertEqual(0.4444, source["production_decision_precision"])
        self.assertEqual(1.0, evidence["production_decision_precision"])
        self.assertEqual(0.0, evidence["required_test_recall"])
        for metric in (
            "required_production_path_recall",
            "production_decision_precision",
            "disposition_accuracy",
            "required_test_recall",
            "evidence_reference_coverage",
            "source_location_coverage",
            "linkage_coverage",
            "unknown_preservation_rate",
        ):
            self.assertEqual(1.0, planned[metric], metric)

    def test_cli_result_matches_tracked_json(self) -> None:
        expected = json.loads(
            (
                ROOT
                / "eval/evidence-guided-planner/results/v1.17.0-real-codex.json"
            ).read_text(encoding="utf-8")
        )
        actual = MODULE["score"](
            MODULE["_load"](
                ROOT / "eval/evidence-guided-planner/real-case/gold.json"
            ),
            MODULE["_load"](
                ROOT
                / "eval/evidence-guided-planner/real-case/observations.json"
            ),
        )
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
