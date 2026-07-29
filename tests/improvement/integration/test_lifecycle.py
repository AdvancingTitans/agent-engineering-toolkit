from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aet.improvement.cli.improve import verify_issue
from aet.improvement.lifecycle import compare_before_after, validate_proof, verify_improvement
from aet.improvement.models.verification import VerificationContract


def _contract() -> VerificationContract:
    return VerificationContract(
        id="VC-001",
        commands=["python -m unittest tests.test_tool"],
        expected_results=["exit_code=0"],
        proof_required=True,
        relevant_paths=["src/tool/result.py"],
    )


def _proof(**overrides):
    value = {
        "id": "PROOF-001",
        "contract_id": "VC-001",
        "candidate_id": "CAND-001",
        "status": "PASS",
        "freshness": "current",
        "command_results": [
            {
                "command": "python -m unittest tests.test_tool",
                "exit_code": 0,
            }
        ],
        "changed_paths": ["src/tool/result.py"],
    }
    value.update(overrides)
    return value


class VerificationLifecycleTests(unittest.TestCase):
    def test_stale_proof_cannot_pass(self) -> None:
        result = validate_proof(
            _contract(),
            _proof(freshness="relevant_files_changed"),
            candidate_id="CAND-001",
        )

        self.assertEqual(result.code, "STALE_PROOF")

    def test_valid_lifecycle_promotes_verified_improvement(self) -> None:
        outcome = verify_improvement(
            _contract(),
            issue_id="IMP-001",
            candidate_id="CAND-001",
            proof=_proof(),
            before_metrics={"status": "FAIL"},
            after_metrics={"status": "PASS"},
        )

        self.assertEqual(outcome.status, "verified_improvement")
        self.assertEqual(outcome.proof_refs, ["PROOF-001"])

    def test_missing_code_change_remains_unverified(self) -> None:
        outcome = verify_improvement(
            _contract(),
            issue_id="IMP-001",
            candidate_id="CAND-001",
            proof=_proof(changed_paths=[]),
        )

        self.assertEqual(outcome.status, "implemented_unverified")
        self.assertEqual(outcome.proof_refs, [])

    def test_before_after_preserves_evidence_statuses(self) -> None:
        result = compare_before_after(
            {"test": "FAIL", "coverage": 1},
            {"test": "PASS", "coverage": 2},
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["improved"], ["coverage", "test"])

    def test_regression_fails_comparison(self) -> None:
        result = compare_before_after(
            {"test": "PASS"},
            {"test": "FAIL"},
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["regressed"], ["test"])

    def test_verify_cli_helper_writes_verified_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            fixtures = {
                "issues.json": [
                    {
                        "id": "IMP-001",
                        "title": "Failure handling gap",
                        "category": "error_handling_gap",
                        "priority": "P2_NORMAL",
                        "finding_refs": ["FND-001"],
                        "evidence_refs": ["EV-001"],
                        "confidence": "high",
                        "impact": {},
                    }
                ],
                "constraints.json": [
                    {
                        "id": "IC-001",
                        "issue_id": "IMP-001",
                        "objective": "Handle failures.",
                        "required_behavior": [],
                        "forbidden_behavior": [],
                        "allowed_paths": ["src/tool/result.py"],
                        "protected_paths": ["eval/**"],
                        "verification_requirements": [
                            "python -m unittest tests.test_tool"
                        ],
                    }
                ],
                "candidate.json": {
                    "id": "CAND-001",
                    "constraint_id": "IC-001",
                },
                "verification-contract.json": {
                    "id": "VC-001",
                    "commands": ["python -m unittest tests.test_tool"],
                    "expected_results": ["exit_code=0"],
                    "proof_required": True,
                    "relevant_paths": ["src/tool/result.py"],
                },
                "proof.json": _proof(),
                "before.json": {"test": "FAIL"},
                "after.json": {"test": "PASS"},
            }
            for name, value in fixtures.items():
                (output / name).write_text(
                    json.dumps(value),
                    encoding="utf-8",
                )

            report = verify_issue("IMP-001", output=output)

            self.assertTrue(report["valid"])
            self.assertEqual(report["status"], "verified_improvement")
            outcome = json.loads(
                (output / "outcome.json").read_text(encoding="utf-8")
            )
            self.assertEqual(outcome["status"], "verified_improvement")


if __name__ == "__main__":
    unittest.main()
