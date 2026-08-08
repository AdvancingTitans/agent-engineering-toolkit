from __future__ import annotations

import unittest
from pathlib import Path

from aet.risk.adapters import load_context
from aet.risk.models import Factor
from aet.risk.policy import load_policy
from aet.risk.signals import extract_signals


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"


class RiskSignalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy(FIXTURES / "risk-policy.json")

    def signals(self, name: str):
        context = load_context(FIXTURES / name, FIXTURES / "intent-v2.json", self.policy)
        return extract_signals(context)

    def test_clean_read_has_no_direct_risk_signal(self) -> None:
        self.assertEqual(self.signals("codex-clean.jsonl"), ())

    def test_failed_out_of_scope_attempt_proves_divergence_not_capability(self) -> None:
        signals = self.signals("codex-goal-divergence.jsonl")
        self.assertEqual({item.factor for item in signals}, {Factor.GOAL_DIVERGENCE})
        self.assertEqual(signals[0].code, "INTENT_BOUNDARY_CROSSED")

    def test_authorized_write_proves_deployment_bound_capability_only(self) -> None:
        signals = self.signals("codex-capability.jsonl")
        self.assertEqual({item.factor for item in signals}, {Factor.HARM_REALIZATION_CAPABILITY})
        self.assertIn("general capability outside this deployment", signals[0].does_not_prove)

    def test_monitor_suppression_requires_call_and_effect_refs(self) -> None:
        signals = self.signals("codex-evasion.jsonl")
        evasion = next(item for item in signals if item.factor is Factor.OVERSIGHT_RESISTANCE)
        self.assertEqual(evasion.code, "EVIDENCE_SUPPRESSION_SUCCEEDED")
        self.assertEqual(len(evasion.refs), 2)
        self.assertEqual(evasion.monitoring_surface_ids, ("aet-evidence",))

    def test_missing_result_does_not_prove_capability_or_evasion(self) -> None:
        signals = self.signals("codex-unknown.jsonl")
        self.assertFalse(any(item.factor is Factor.HARM_REALIZATION_CAPABILITY for item in signals))
        self.assertFalse(any(item.factor is Factor.OVERSIGHT_RESISTANCE for item in signals))


if __name__ == "__main__":
    unittest.main()
