from __future__ import annotations

import unittest
from pathlib import Path

from aet.risk.adapters import load_context
from aet.risk.coverage import assess_coverage
from aet.risk.policy import load_policy


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"


class RiskCoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(FIXTURES / "risk-policy.json")

    def test_complete_linked_run_allows_negative_coverage(self) -> None:
        context = load_context(FIXTURES / "codex-clean.jsonl", FIXTURES / "intent-v2.json", self.policy)
        coverage = assess_coverage(context)
        self.assertTrue(coverage.complete)
        self.assertFalse(coverage.observability_gap)

    def test_truncated_missing_result_is_unknown_coverage(self) -> None:
        context = load_context(FIXTURES / "codex-unknown.jsonl", FIXTURES / "intent-v2.json", self.policy)
        coverage = assess_coverage(context)
        self.assertFalse(coverage.complete)
        self.assertIn("truncated_tool_output", coverage.gaps)
        self.assertIn("missing_tool_result", coverage.gaps)
        self.assertTrue(coverage.observability_gap)


if __name__ == "__main__":
    unittest.main()
