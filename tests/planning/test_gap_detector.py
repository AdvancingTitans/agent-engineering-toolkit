from __future__ import annotations

import unittest

from aet.planning.gap_detector import detect_planning_gaps
from aet.planning.models import OmissionSummary


class GapDetectorTests(unittest.TestCase):
    def test_source_only_and_budget_exhaustion_are_explicit(self) -> None:
        gaps = detect_planning_gaps(
            has_bundle=False,
            allowed_scope_resolved=False,
            relevant_claims=[],
            relevant_evidence=[],
            conflicts=[],
            source_sites=[],
            verification_requirements=[],
            omitted=OmissionSummary(nodes=1),
        )
        codes = {item.code for item in gaps}
        self.assertIn("EVIDENCE_REQUIRED", codes)
        self.assertIn("BUDGET_EXHAUSTED", codes)
        self.assertTrue(any(item.critical for item in gaps))


if __name__ == "__main__":
    unittest.main()
