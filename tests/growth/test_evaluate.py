import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/growth"))

from evaluate import evaluate


def snapshot() -> dict:
    value = json.loads(
        (ROOT / "ops/growth/metrics/baseline.example.json").read_text()
    )
    value["repository"] = "owner/repo"
    value["stars"] = {
        "status": "KNOWN",
        "value": 10,
        "source": "repo",
        "observed_at": value["observed_at"],
        "diagnostic": None,
    }
    value["traffic_unique_visitors"] = {
        "status": "KNOWN",
        "value": 100,
        "source": "traffic",
        "observed_at": value["observed_at"],
        "diagnostic": None,
    }
    return value


class GrowthEvaluateTests(unittest.TestCase):
    def test_known_deltas_and_conversion(self) -> None:
        baseline = snapshot()
        current = copy.deepcopy(baseline)
        current["observed_at"] = "2026-01-08T00:00:00Z"
        current["stars"]["value"] = 15
        current["traffic_unique_visitors"]["value"] = 200
        result = evaluate(baseline, current)
        self.assertEqual(result["deltas"]["stars"]["value"], 5)
        self.assertEqual(result["stars_per_unique_visitor"]["value"], 0.05)
        self.assertIn("does not attribute", result["causality_statement"])

    def test_zero_denominator_and_unknown_are_explicit(self) -> None:
        baseline = snapshot()
        current = copy.deepcopy(baseline)
        result = evaluate(baseline, current)
        self.assertEqual(result["deltas"]["stars"]["value"], 0)
        self.assertEqual(result["stars_per_unique_visitor"]["status"], "UNKNOWN")
        current["stars"]["status"] = "UNAVAILABLE"
        current["stars"]["value"] = None
        result = evaluate(baseline, current)
        self.assertEqual(result["deltas"]["stars"]["status"], "UNKNOWN")

    def test_rejects_mismatched_repository_and_schema(self) -> None:
        baseline = snapshot()
        current = copy.deepcopy(baseline)
        current["repository"] = "other/repo"
        with self.assertRaisesRegex(ValueError, "repository differ"):
            evaluate(baseline, current)
        current = copy.deepcopy(baseline)
        current["schema_version"] = "future"
        with self.assertRaisesRegex(ValueError, "schema_version"):
            evaluate(baseline, current)
