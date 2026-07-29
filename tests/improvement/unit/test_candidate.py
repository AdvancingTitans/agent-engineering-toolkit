from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aet.improvement.candidate import parse_candidate
from aet.improvement.cli.improve import (
    generate_agent_prompt,
    validate_candidate_file,
)
from aet.improvement.models.constraint import ImprovementConstraint
from aet.improvement.validator import (
    detect_gaming,
    validate_grounding,
    validate_reference,
    validate_scope,
    validate_strength,
)


def _candidate(**overrides):
    value = {
        "id": "CAND-001",
        "constraint_id": "IC-001",
        "strategy": "Introduce a structured empty-result state.",
        "targets": [{"path": "src/aet/cli.py", "symbol": "main"}],
        "assumptions": [],
        "risks": [],
        "verification_plan": ["python -m unittest"],
        "finding_refs": ["FND-001"],
        "evidence_refs": ["EV-001"],
        "claim_refs": ["CLM-001"],
        "deleted_paths": [],
        "human_approval_required": False,
        "root_cause_status": "evidenced",
    }
    value.update(overrides)
    return value


def _constraint(**overrides):
    value = {
        "id": "IC-001",
        "issue_id": "IMP-001",
        "objective": "Keep the change bounded.",
        "required_behavior": [],
        "forbidden_behavior": [],
        "allowed_paths": ["src/aet/**"],
        "protected_paths": [
            "tests/evals/**",
            "eval/**",
            "grader/**",
            "fixtures/**",
            ".aet/**",
        ],
        "verification_requirements": ["python -m unittest"],
    }
    value.update(overrides)
    return ImprovementConstraint(**value)


class CandidateLayerTests(unittest.TestCase):
    def test_candidate_is_always_proposed(self) -> None:
        candidate = parse_candidate(_candidate())

        self.assertEqual(candidate.status, "PROPOSED")

    def test_invalid_evidence_reference(self) -> None:
        result = validate_grounding(
            _candidate(evidence_refs=["NOT_EXIST"]),
            {
                "evidence": [{"id": "EV-001"}],
                "findings": [{"id": "FND-001"}],
                "claims": [{"id": "CLM-001"}],
            },
        )

        self.assertTrue(result.invalid)
        self.assertEqual(result.code, "INVALID_REFERENCE")

    def test_scope_violation(self) -> None:
        result = validate_scope(
            _candidate(
                targets=[{"path": "src/payment/card.py", "symbol": "charge"}]
            ),
            _constraint(allowed_paths=["src/auth/**"]),
        )

        self.assertEqual(result.code, "SCOPE_VIOLATION")

    def test_protected_path_is_rejected(self) -> None:
        result = validate_scope(
            _candidate(
                targets=[{"path": "eval/grader.py", "symbol": "grade"}]
            ),
            _constraint(allowed_paths=["**"]),
        )

        self.assertEqual(result.code, "REJECTED")

    def test_missing_file_and_symbol_are_invalid_references(self) -> None:
        missing_file = validate_reference(
            {"path": "src/not_exist.py", "symbol": "missing"}
        )
        missing_symbol = validate_reference(
            {"path": "src/aet/cli.py", "symbol": "fake_function"}
        )

        self.assertEqual(missing_file.code, "INVALID_REFERENCE")
        self.assertEqual(missing_symbol.code, "INVALID_REFERENCE")

    def test_real_file_and_symbol_are_valid(self) -> None:
        result = validate_reference(
            {"path": "src/aet/cli.py", "symbol": "main"}
        )

        self.assertTrue(result.valid)

    def test_unknown_root_cause_cannot_target_code(self) -> None:
        result = validate_strength(
            _candidate(root_cause_status="unknown")
        )

        self.assertEqual(result.code, "INVESTIGATION_REQUIRED")

    def test_grader_tampering_and_test_deletion_fail(self) -> None:
        grader = detect_gaming(
            _candidate(
                targets=[{"path": "grader/main.py", "symbol": "grade"}]
            )
        )
        deletion = detect_gaming(
            _candidate(deleted_paths=["tests/regression/test_case.py"])
        )

        self.assertEqual(grader.code, "ANTI_GAMING_FAILURE")
        self.assertEqual(deletion.code, "ANTI_GAMING_FAILURE")

    def test_prompt_and_valid_candidate_cli_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / ".aet/improvements"
            output.mkdir(parents=True)
            (output / "issues.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "IMP-001",
                            "title": "Unsupported claim",
                            "category": "unsupported_claim",
                            "priority": "P1_HIGH",
                            "finding_refs": ["FND-001"],
                            "evidence_refs": ["EV-001"],
                            "confidence": "high",
                            "impact": {
                                "statement": "Unsupported claim",
                                "limitations": [],
                                "root_cause_status": "evidenced",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (output / "constraints.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "IC-001",
                            "issue_id": "IMP-001",
                            "objective": "Keep facts grounded.",
                            "required_behavior": [],
                            "forbidden_behavior": [],
                            "allowed_paths": ["src/aet/**"],
                            "protected_paths": [
                                "tests/evals/**",
                                "eval/**",
                                "grader/**",
                                "fixtures/**",
                                ".aet/**",
                            ],
                            "verification_requirements": [
                                "python -m unittest"
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            candidate_path = Path(raw) / "candidate.json"
            candidate_path.write_text(
                json.dumps(_candidate(claim_refs=["FND-001"])),
                encoding="utf-8",
            )

            prompt = generate_agent_prompt("IMP-001", output=output)
            validation = validate_candidate_file(
                candidate_path,
                output=output,
                root=Path.cwd(),
            )

            self.assertEqual(prompt["status"], "PROPOSED")
            task = (output / "agent-task.md").read_text(encoding="utf-8")
            for section in (
                "Problem",
                "Evidence",
                "Allowed Scope",
                "Forbidden Scope",
                "Verification",
                "Stop Conditions",
            ):
                self.assertIn(f"## {section}", task)
            self.assertTrue(validation["valid"])
            self.assertEqual(validation["status"], "PROPOSED")


if __name__ == "__main__":
    unittest.main()
