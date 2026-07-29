from __future__ import annotations

import unittest
from pathlib import Path

from aet.planning.bundle_loader import load_planning_bundle
from aet.planning.models import PlanningBudgets, PlanningRequest, WorkspaceIdentity
from aet.planning.relevance import rank_references


ROOT = Path(__file__).resolve().parents[2]


class RelevanceTests(unittest.TestCase):
    def test_allowed_scope_and_direct_links_precede_lexical_fallback(self) -> None:
        bundle = load_planning_bundle(ROOT / "tests/fixtures/evidence-bundles/minimal")
        workspace = WorkspaceIdentity("PASS", "workspace", "a" * 40, "b" * 64)
        request = PlanningRequest(
            "planning-request/1.0",
            "REQ-RANK",
            "Change tests/test_example.py verification.",
            [],
            [],
            ["tests/test_example.py"],
            [],
            [],
            bundle.bundle_id,
            None,
            workspace,
            PlanningBudgets(),
            allowed_scope_status="RESOLVED",
        )
        ranked = rank_references(request, bundle)
        self.assertEqual(ranked[0].priority_tier, 0)
        self.assertIn("EXPLICIT_REFERENCE", ranked[0].reasons)
        self.assertEqual(
            [(item.priority_tier, item.kind, item.reference_id) for item in ranked],
            sorted(
                (item.priority_tier, item.kind, item.reference_id)
                for item in ranked
            ),
        )


if __name__ == "__main__":
    unittest.main()
