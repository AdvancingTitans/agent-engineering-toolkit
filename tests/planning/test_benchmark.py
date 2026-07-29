from __future__ import annotations

import json
import runpy
import unittest
from pathlib import Path

from aet.planning.models import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/planning/localization-gold.json"
RUNNER = ROOT / "eval/evidence-guided-planner/run_benchmark.py"
RESULT = (
    ROOT
    / "eval/evidence-guided-planner/results/v1.17.0.json"
)


class PlannerBenchmarkTests(unittest.TestCase):
    def test_frozen_twenty_case_benchmark_meets_planner_thresholds(self) -> None:
        namespace = runpy.run_path(str(RUNNER))
        fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
        first = namespace["evaluate"](fixtures)
        second = namespace["evaluate"](fixtures)
        self.assertEqual(20, first["fixture_count"])
        self.assertEqual("PASS", first["status"])
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        planner = first["groups"]["planner_protocol"]
        self.assertGreaterEqual(planner["required_path_recall"], 0.90)
        self.assertGreaterEqual(planner["recommended_path_precision"], 0.80)
        self.assertGreaterEqual(planner["required_test_recall"], 0.85)
        self.assertEqual(0.0, planner["protected_path_rate"])
        self.assertEqual(1.0, planner["reference_resolution_rate"])
        checked_in = json.loads(RESULT.read_text(encoding="utf-8"))
        self.assertEqual("PASS", checked_in["status"])
        for metric in (
            "required_path_recall",
            "recommended_path_precision",
            "required_test_recall",
            "protected_path_rate",
            "reference_resolution_rate",
        ):
            self.assertEqual(
                planner[metric],
                checked_in["groups"]["planner_protocol"][metric],
            )


if __name__ == "__main__":
    unittest.main()
