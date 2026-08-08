from __future__ import annotations

import itertools
import unittest

from aet.risk.interventions import propose_interventions
from aet.risk.models import Coverage, EvidenceStrength, Factor, FactorFinding, SourceRef, Status


def finding(factor: Factor, status: Status = Status.FAIL) -> FactorFinding:
    return FactorFinding(
        factor=factor,
        observable="observable",
        status=status,
        strength=EvidenceStrength.DIRECT if status is Status.FAIL else EvidenceStrength.NONE,
        evidence_refs=(SourceRef(f"{factor.value}-ref"),) if status is Status.FAIL else (),
        counter_evidence_refs=(),
        coverage=Coverage(complete=True),
        limitations=("bounded",),
        does_not_prove=("automatic authority",),
        context_key="r:g:t",
    )


class RiskInterventionTests(unittest.TestCase):
    def test_all_seven_non_empty_factor_combinations_are_proposed(self) -> None:
        factors = tuple(Factor)
        seen = 0
        for size in (1, 2, 3):
            for combination in itertools.combinations(factors, size):
                with self.subTest(combination=combination):
                    proposals = propose_interventions(finding(item) for item in combination)
                    self.assertEqual(len(proposals), 1)
                    self.assertEqual(proposals[0].authority, "PROPOSED")
                    self.assertEqual(set(proposals[0].factor_combination), set(combination))
                    self.assertTrue(proposals[0].actions)
                    seen += 1
        self.assertEqual(seen, 7)

    def test_pass_and_unknown_never_propose_high_impact_action(self) -> None:
        values = (
            finding(Factor.GOAL_DIVERGENCE, Status.PASS),
            finding(Factor.HARM_REALIZATION_CAPABILITY, Status.UNKNOWN),
        )
        self.assertEqual(propose_interventions(values), ())

    def test_no_execution_callable_is_exported(self) -> None:
        import aet.risk.interventions as module

        self.assertFalse(any(name.startswith(("execute", "terminate", "revoke")) for name in module.__all__))


if __name__ == "__main__":
    unittest.main()
