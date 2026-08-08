from __future__ import annotations

import unittest
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from aet.risk.diagnose import diagnose_risk
from aet.risk.models import Factor, Status, to_primitive


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"
NOW = "2026-08-01T00:00:00Z"


def diagnose(name: str):
    return diagnose_risk(
        run_path=FIXTURES / name,
        intent_path=FIXTURES / "intent-v2.json",
        policy_path=FIXTURES / "risk-policy.json",
        now=NOW,
    )


class RiskDiagnoseTests(unittest.TestCase):
    def test_clean_run_passes_all_three_axes_with_declared_coverage(self) -> None:
        result = diagnose("codex-clean.jsonl")
        self.assertEqual({item.status for item in result.findings}, {Status.PASS})
        self.assertTrue(all(item.coverage.complete for item in result.findings))

    def test_compound_run_fails_each_axis_without_holistic_score(self) -> None:
        result = diagnose("codex-compound.jsonl")
        self.assertEqual({item.status for item in result.findings}, {Status.FAIL})
        primitive = to_primitive(result)
        self.assertNotIn("overall_score", primitive)
        self.assertNotIn("trust_score", primitive)

    def test_missing_evidence_preserves_unknown(self) -> None:
        result = diagnose("codex-unknown.jsonl")
        self.assertEqual({item.status for item in result.findings}, {Status.UNKNOWN})

    def test_codex_and_claude_equivalent_runs_have_same_factor_vector(self) -> None:
        codex = diagnose("codex-compound.jsonl")
        claude = diagnose("claude-equivalent.jsonl")
        self.assertEqual(
            [(item.factor, item.status, item.signal_codes) for item in codex.findings],
            [(item.factor, item.status, item.signal_codes) for item in claude.findings],
        )

    def test_fixed_time_is_byte_semantically_deterministic(self) -> None:
        first = to_primitive(diagnose("codex-capability.jsonl"))
        second = to_primitive(diagnose("codex-capability.jsonl"))
        self.assertEqual(first, second)
        self.assertFalse(first["provenance"]["network_used"])
        self.assertFalse(first["provenance"]["model_parameter_changes"])

    def test_ten_megabyte_low_relevance_run_meets_local_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "large.jsonl"
            events = [
                {
                    "type": "session_meta",
                    "session_id": "risk-large",
                    "payload": {"id": "risk-large", "cwd": "/repo"},
                },
                {
                    "type": "assistant",
                    "session_id": "risk-large",
                    "content": "x" * 10_000_000,
                },
            ]
            run.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
            tracemalloc.start()
            started = time.perf_counter()
            result = diagnose_risk(
                run_path=run,
                intent_path=FIXTURES / "intent-v2.json",
                policy_path=FIXTURES / "risk-policy.json",
                now=NOW,
            )
            elapsed = time.perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            self.assertEqual({item.status for item in result.findings}, {Status.PASS})
            self.assertLessEqual(elapsed, 2.0)
            self.assertLessEqual(peak, 256 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
