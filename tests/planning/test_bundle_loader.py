from __future__ import annotations

import unittest
from pathlib import Path

from aet.planning.bundle_loader import load_planning_bundle
from aet.planning.errors import PlanningError, PlanningErrorCode


ROOT = Path(__file__).resolve().parents[2]
MINIMAL = ROOT / "tests/fixtures/evidence-bundles/minimal"


class PlanningBundleLoaderTests(unittest.TestCase):
    def test_validated_bundle_retains_status_scope_and_verification(self) -> None:
        view = load_planning_bundle(MINIMAL)
        self.assertEqual(view.bundle_id, "bundle-fixture-001")
        self.assertEqual(view.claims[0]["status"], "supported")
        self.assertEqual(view.evidence[0]["freshness"]["status"], "current")
        self.assertIn("tests/**", view.allowed_paths)
        self.assertIn("python -m unittest tests.test_example", view.verification_requirements)

    def test_invalid_bundle_fails_closed(self) -> None:
        with self.assertRaises(PlanningError) as raised:
            load_planning_bundle(ROOT / "tests/fixtures/broken_project")
        self.assertEqual(raised.exception.code, PlanningErrorCode.INVALID_BUNDLE)


if __name__ == "__main__":
    unittest.main()
