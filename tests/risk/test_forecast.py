from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from aet.risk.diagnose import diagnose_risk
from aet.risk.forecast import (
    ForecastStatus,
    calibration_gate,
    forecast_diagnosis,
    forecast_pathway,
    wilson_interval,
)
from aet.risk.renderer import write_outputs


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"
SIGNATURE = "+".join(
    sorted(
        (
            "goal_divergence_indicator",
            "harm_realization_capability",
            "oversight_resistance_indicator",
        )
    )
)


def calibration() -> dict:
    return {
        "schema_version": "aet-risk-calibration/1.0",
        "dataset_sha256": "a" * 64,
        "episode_count": 240,
        "positive_count": 60,
        "repository_count": 3,
        "host_count": 2,
        "min_support": 20,
        "split_manifest": {
            "dataset_sha256": "a" * 64,
            "temporal_holdout": True,
            "repository_holdout": True,
            "host_holdout": True,
            "leakage_detected": False,
        },
        "holdout_metrics": {
            "false_positive_rate": 0.005,
            "ece": 0.08,
            "brier_skill_ci_low": -0.01,
        },
        "domain": {
            "hosts": ["codex", "claude-code"],
            "repositories": ["repo-a", "repo-b", "repo-c"],
        },
        "baseline": {"positives": 10, "support": 200},
        "buckets": {SIGNATURE: {"positives": 90, "support": 100}},
    }


class RiskForecastTests(unittest.TestCase):
    def test_wilson_interval_handles_known_and_boundary_counts(self) -> None:
        middle = wilson_interval(5, 10)
        self.assertAlmostEqual(middle.low, 0.2366, places=3)
        self.assertAlmostEqual(middle.high, 0.7634, places=3)
        for positives in (0, 10):
            interval = wilson_interval(positives, 10)
            self.assertFalse(math.isnan(interval.low))
            self.assertFalse(math.isnan(interval.high))

    def test_calibration_gate_is_research_only_and_still_reports_data_gaps(self) -> None:
        valid = calibration()
        self.assertEqual(calibration_gate(valid), (False, ("forecast_research_only",)))
        valid["episode_count"] = 199
        valid["split_manifest"]["leakage_detected"] = True
        passed, gaps = calibration_gate(valid)
        self.assertFalse(passed)
        self.assertIn("forecast_research_only", gaps)
        self.assertIn("episode_count_below_200", gaps)
        self.assertIn("split_leakage_not_excluded", gaps)

    def test_plausible_calibration_cannot_promote_a_research_forecast(self) -> None:
        result = forecast_pathway(
            {"key": SIGNATURE, "host": "codex", "repository": "repo-a"},
            calibration(),
        )
        self.assertEqual(result.status, ForecastStatus.UNKNOWN)
        self.assertEqual(result.reason, "forecast_research_only")

    def test_all_research_inputs_fail_conservatively_before_domain_or_support_claims(self) -> None:
        value = calibration()
        value["buckets"][SIGNATURE] = {"positives": 6, "support": 100}
        overlap = forecast_pathway(
            {"key": SIGNATURE, "host": "codex", "repository": "repo-a"},
            value,
        )
        self.assertEqual(overlap.status, ForecastStatus.UNKNOWN)
        value["buckets"][SIGNATURE] = {"positives": 10, "support": 19}
        insufficient = forecast_pathway(
            {"key": SIGNATURE, "host": "codex", "repository": "repo-a"},
            value,
        )
        self.assertEqual(insufficient.status, ForecastStatus.UNKNOWN)
        out_of_domain = forecast_pathway(
            {"key": SIGNATURE, "host": "new-host", "repository": "repo-a"},
            calibration(),
        )
        self.assertEqual(out_of_domain.status, ForecastStatus.UNKNOWN)

    def test_forecast_report_is_hash_bound_and_has_no_holistic_score(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = diagnose_risk(
                run_path=FIXTURES / "codex-compound.jsonl",
                intent_path=FIXTURES / "intent-v2.json",
                policy_path=FIXTURES / "risk-policy.json",
                now="2026-08-01T00:00:00Z",
            )
            diagnosis_path = root / "diagnosis.json"
            write_outputs(diagnosis, diagnosis_path)
            calibration_path = root / "calibration.json"
            calibration_path.write_text(json.dumps(calibration()), encoding="utf-8")
            report = forecast_diagnosis(
                diagnosis_path,
                calibration_path,
                host="codex",
                repository="repo-a",
                now="2026-08-01T00:00:00Z",
            )
            self.assertEqual(report["gate_status"], "FAIL")
            self.assertEqual(report["forecasts"][0]["status"], "UNKNOWN")
            self.assertIn("forecast_research_only", report["limitations"])
            self.assertNotIn("overall_score", report)
            self.assertFalse(report["provenance"]["model_parameter_changes"])


if __name__ == "__main__":
    unittest.main()
