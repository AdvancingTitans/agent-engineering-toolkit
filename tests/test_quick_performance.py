from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "eval" / "quick-performance" / "runner.py"
SPEC = importlib.util.spec_from_file_location("aet_quick_performance", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class QuickPerformanceEvidenceTests(unittest.TestCase):
    def test_nearest_rank_p95_and_tracked_report(self) -> None:
        self.assertEqual(19, RUNNER._p95(list(range(1, 21))))
        report = json.loads(
            (ROOT / "eval" / "quick-performance" / "results" / "v1.13.0.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual("aet-quick-performance/v1", report["schema_version"])
        self.assertGreaterEqual(report["method"]["tracked_files"], 100)
        for name, metric in report["commands"].items():
            with self.subTest(name=name):
                self.assertEqual(
                    report["method"]["repetitions_per_command"],
                    len(metric["samples_seconds"]),
                )
                self.assertEqual(RUNNER._p95(metric["samples_seconds"]), metric["p95_seconds"])
                self.assertLess(metric["p95_seconds"], metric["budget_seconds"])


if __name__ == "__main__":
    unittest.main()
