from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from aet.risk.diagnose import diagnose_risk
from aet.risk.models import Coverage, EvidenceStrength, Factor, FactorFinding, SourceRef, Status
from aet.risk.pathways import link_pathways


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"


def finding(factor: Factor, *, context: str = "r:g:t", asset: str = "shared", monitor: str = "") -> FactorFinding:
    return FactorFinding(
        factor=factor,
        observable="observable",
        status=Status.FAIL,
        strength=EvidenceStrength.DIRECT,
        evidence_refs=(SourceRef(f"{factor.value}-ref", source_order_id=f"{factor.value}-order"),),
        counter_evidence_refs=(),
        coverage=Coverage(complete=True),
        limitations=("bounded",),
        does_not_prove=("internal motive",),
        context_key=context,
        asset_ids=(asset,) if asset else (),
        monitoring_surface_ids=(monitor,) if monitor else (),
        order_keys=(f"{factor.value}-order",),
    )


class RiskPathwayTests(unittest.TestCase):
    def test_compound_fixture_links_three_factor_same_context_path(self) -> None:
        diagnosis = diagnose_risk(
            run_path=FIXTURES / "codex-compound.jsonl",
            intent_path=FIXTURES / "intent-v2.json",
            policy_path=FIXTURES / "risk-policy.json",
            now="2026-08-01T00:00:00Z",
        )
        self.assertEqual(len(diagnosis.pathways), 1)
        pathway = diagnosis.pathways[0]
        self.assertEqual({item.factor for item in pathway.factors}, set(Factor))
        self.assertEqual(pathway.status, Status.FAIL)
        self.assertGreaterEqual(len(pathway.ordered_refs), 4)

    def test_monitor_only_event_does_not_manufacture_three_factor_path(self) -> None:
        diagnosis = diagnose_risk(
            run_path=FIXTURES / "codex-evasion.jsonl",
            intent_path=FIXTURES / "intent-v2.json",
            policy_path=FIXTURES / "risk-policy.json",
            now="2026-08-01T00:00:00Z",
        )
        self.assertEqual(diagnosis.pathways, ())

    def test_cross_context_and_unrelated_assets_are_not_linked(self) -> None:
        first = finding(Factor.GOAL_DIVERGENCE, context="a:g:t", asset="a")
        second = finding(Factor.HARM_REALIZATION_CAPABILITY, context="b:g:t", asset="a")
        self.assertEqual(link_pathways((first, second)), ())
        unrelated = replace(second, context_key="a:g:t", asset_ids=("b",))
        self.assertEqual(link_pathways((first, unrelated)), ())

    def test_removing_coverage_cannot_increase_path_certainty(self) -> None:
        first = finding(Factor.GOAL_DIVERGENCE)
        second = finding(Factor.HARM_REALIZATION_CAPABILITY)
        self.assertEqual(len(link_pathways((first, second))), 1)
        incomplete = replace(second, coverage=Coverage(complete=False, gaps=("missing_tool_result",)))
        self.assertEqual(link_pathways((first, incomplete)), ())


if __name__ == "__main__":
    unittest.main()
