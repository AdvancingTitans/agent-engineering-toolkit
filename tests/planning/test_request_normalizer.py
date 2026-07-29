from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aet.planning.errors import PlanningError
from aet.planning.models import PlanningBudgets
from aet.planning.request_normalizer import RequestOverrides, normalize_request


class RequestNormalizerTests(unittest.TestCase):
    def test_empty_request_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(PlanningError):
                normalize_request("  ", workspace=Path(raw))

    def test_paths_risk_terms_and_overrides_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            request = normalize_request(
                "修改所有失败路径。\nAllowed paths: `src/a.py`, tests/\n保护路径：vendor/",
                workspace=Path(raw),
                explicit=RequestOverrides(
                    acceptance_criteria=["Failure remains explicit."],
                    required_verification=["python -m unittest"],
                    bundle_identity="bundle-1",
                    budgets=PlanningBudgets(max_nodes=20),
                ),
            )
            self.assertEqual(request.allowed_paths, ["src/a.py", "tests/**"])
            self.assertEqual(request.protected_paths, ["vendor/**"])
            self.assertIn("所有", request.high_risk_claims)
            self.assertEqual(request.allowed_scope_status, "RESOLVED")
            self.assertEqual(request.budgets.max_nodes, 20)

    def test_no_allowed_scope_remains_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            request = normalize_request("Change one behavior.", workspace=Path(raw))
            self.assertEqual(request.allowed_paths, [])
            self.assertEqual(request.allowed_scope_status, "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
