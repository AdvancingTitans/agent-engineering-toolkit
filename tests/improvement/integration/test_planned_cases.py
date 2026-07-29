from __future__ import annotations

import json
import unittest
from pathlib import Path

from aet.improvement.analyzer import normalize_finding
from aet.improvement.constraint import build_constraint
from aet.improvement.models.constraint import ImprovementConstraint
from aet.improvement.validator import detect_gaming, validate_scope


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests/improvement/fixtures"


def _load(relative: str) -> dict:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def _constraint() -> ImprovementConstraint:
    return ImprovementConstraint(
        id="IC-001",
        issue_id="IMP-001",
        objective="Fix login timeout.",
        required_behavior=[],
        forbidden_behavior=[],
        allowed_paths=["auth/**"],
        protected_paths=[
            "tests/evals/**",
            "eval/**",
            "grader/**",
            "fixtures/**",
            ".aet/**",
        ],
        verification_requirements=["python -m unittest"],
    )


class PlannedIntegrationCases(unittest.TestCase):
    def test_empty_tool_result_hallucination(self) -> None:
        issue = normalize_finding(
            _load("empty-tool-result/finding.json")
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue.category, "unsupported_claim")
        constraint = build_constraint(
            issue,
            allowed_paths=["src/tool/**"],
        )
        self.assertIn(
            "empty",
            " ".join(
                [
                    constraint.objective,
                    *constraint.required_behavior,
                    *constraint.forbidden_behavior,
                ]
            ).lower(),
        )

    def test_scope_expansion_needs_human_review(self) -> None:
        candidate = {
            **_load("scope-overreach/candidate.json"),
            "targets": [
                {"path": "auth/session.py", "symbol": "login"},
                {"path": "database/pool.py", "symbol": "connect"},
                {"path": "payment/card.py", "symbol": "charge"},
            ],
        }

        result = validate_scope(candidate, _constraint())

        self.assertEqual(result.code, "NEEDS_HUMAN_REVIEW")

    def test_grader_tampering_is_anti_gaming_failure(self) -> None:
        result = detect_gaming(
            _load("grader-tampering/candidate.json")
        )

        self.assertEqual(result.code, "ANTI_GAMING_FAILURE")

    def test_deleted_test_attempt_is_rejected(self) -> None:
        candidate = {
            **_load("scope-overreach/candidate.json"),
            "deleted_paths": ["tests/regression/test_case.py"],
        }

        result = detect_gaming(candidate)

        self.assertEqual(result.code, "ANTI_GAMING_FAILURE")

    def test_eval_design_defect_still_requires_human_review(self) -> None:
        candidate = _load("eval-design-defect/candidate.json")

        result = validate_scope(
            candidate,
            ImprovementConstraint(
                **{
                    **_constraint().__dict__,
                    "allowed_paths": ["eval/**"],
                }
            ),
        )

        self.assertEqual(result.code, "NEEDS_HUMAN_REVIEW")


if __name__ == "__main__":
    unittest.main()
