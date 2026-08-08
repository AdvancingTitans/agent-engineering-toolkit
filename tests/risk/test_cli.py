from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from aet.cli import main


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"


class RiskCliTests(unittest.TestCase):
    def test_diagnose_writes_both_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stdout = StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        "risk", "diagnose",
                        "--run", str(FIXTURES / "codex-capability.jsonl"),
                        "--intent", str(FIXTURES / "intent-v2.json"),
                        "--policy", str(FIXTURES / "risk-policy.json"),
                        "--json-out", str(root / "risk.json"),
                        "--md-out", str(root / "risk.md"),
                        "--created-at", "2026-08-01T00:00:00Z",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["authority"], "DIAGNOSIS")
            self.assertTrue((root / "risk.json").is_file())
            self.assertTrue((root / "risk.md").is_file())

    def test_invalid_policy_returns_two_and_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "risk.json"
            output.write_text("keep", encoding="utf-8")
            invalid = root / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            stderr = StringIO()
            with redirect_stderr(stderr):
                code = main(
                    [
                        "risk", "diagnose",
                        "--run", str(FIXTURES / "codex-clean.jsonl"),
                        "--intent", str(FIXTURES / "intent-v2.json"),
                        "--policy", str(invalid),
                        "--json-out", str(output),
                    ]
                )
            self.assertEqual(code, 2)
            self.assertEqual(output.read_text(), "keep")
            self.assertIn("risk diagnose failed", stderr.getvalue())

    def test_forecast_gate_failure_is_explicit_exit_three(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis_out = root / "diagnosis.json"
            self.assertEqual(
                main(
                    [
                        "risk", "diagnose",
                        "--run", str(FIXTURES / "codex-compound.jsonl"),
                        "--intent", str(FIXTURES / "intent-v2.json"),
                        "--policy", str(FIXTURES / "risk-policy.json"),
                        "--json-out", str(diagnosis_out),
                        "--created-at", "2026-08-01T00:00:00Z",
                    ]
                ),
                0,
            )
            calibration = {
                "dataset_sha256": "a" * 64,
                "episode_count": 1,
                "positive_count": 0,
                "repository_count": 1,
                "host_count": 1,
                "split_manifest": {"dataset_sha256": "a" * 64},
                "holdout_metrics": {},
                "domain": {"hosts": ["codex"], "repositories": ["repo-a"]},
                "baseline": {"positives": 0, "support": 1},
                "buckets": {},
            }
            calibration_path = root / "calibration.json"
            calibration_path.write_text(json.dumps(calibration), encoding="utf-8")
            forecast_out = root / "forecast.json"
            with redirect_stdout(StringIO()):
                code = main(
                    [
                        "risk", "forecast",
                        "--diagnosis", str(diagnosis_out),
                        "--calibration", str(calibration_path),
                        "--host", "codex",
                        "--repository", "repo-a",
                        "--json-out", str(forecast_out),
                        "--created-at", "2026-08-01T00:00:00Z",
                    ]
                )
            self.assertEqual(code, 3)
            self.assertEqual(json.loads(forecast_out.read_text())["gate_status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
