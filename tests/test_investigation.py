from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from aet.investigation import (
    GroundingError,
    InvestigationLedger,
    StopDecision,
    evaluate_stop,
    validate_investigated_finding,
)
from aet.investigation.ledger import LedgerError
from aet.narrative import render_investigated_finding


def _ledger(*, exit_code: int = 0, tool: str = "ripgrep") -> InvestigationLedger:
    result = {"exit_code": exit_code, "matches": ["src/app.py:1"]}
    result_sha256 = hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return InvestigationLedger({
        "schema_version": "aet-investigation-ledger/v1",
        "investigation_id": "inv_test",
        "command": "aet-scope",
        "hypotheses": [
            {"id": "H1", "statement": "The change is required.", "state": "OPEN"},
            {"id": "H2", "statement": "The change is unrelated.", "state": "OPEN"},
        ],
        "completed_investigations": [
            "recover_intent",
            "inspect_direct_dependency",
            "evaluate_counter_hypothesis",
        ],
        "material_conflicting_evidence_refs": [],
        "budget": {
            "wall_time_seconds": 45,
            "llm_calls": 2,
            "tool_calls": 8,
            "remote_calls": 2,
            "expensive_calls": 1,
            "findings": 5,
        },
        "usage": {
            "wall_time_seconds": 1,
            "llm_calls": 1,
            "tool_calls": 1,
            "remote_calls": 0,
            "expensive_calls": 0,
            "findings": 1,
        },
        "steps": [{
            "step_id": "step_01",
            "question": "Does the changed symbol support the task?",
            "tool": tool,
            "evidence_class": (
                "llm_similarity" if tool == "llm.similarity" else "deterministic_tool"
            ),
            "input": {"pattern": "changed_symbol"},
            "result": result,
            "result_ref": "evidence://search/1",
            "result_sha256": result_sha256,
            "observation": {"summary": "one reference"},
            "hypothesis_effect": {"supports": ["H1"], "weakens": ["H2"]},
            "decision_value": "high",
            "cost": "low",
        }],
        "stop": {"reason": "DOMINANT_EXPLANATION", "bounded_result": False},
    })


def _finding(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "finding_type": "possible_scope_expansion",
        "origin": "INVESTIGATED_FINDING",
        "authoritative_status": "UNKNOWN",
        "assessment_state": "SUPPORTED_WITH_LIMITS",
        "blocking": False,
        "evidence_refs": ["evidence://search/1"],
        "counter_explanation": {
            "statement": "A shared dependency may justify the change.",
            "investigation_result": "UNRESOLVED",
            "evidence_refs": [],
        },
        "confirmed_facts": [],
        "engineering_judgment": "The available facts support a limited judgment.",
        "remaining_uncertainty": ["The counter explanation is unresolved."],
    }
    value.update(overrides)
    return value


def _contract(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "aet-investigation-contract/v1",
        "finding_type": "possible_scope_expansion",
        "required_investigation": [
            "recover_intent",
            "inspect_direct_dependency",
            "evaluate_counter_hypothesis",
        ],
        "factual_grounding": {
            "tool_claims_require_result_ref": True,
            "user_constraints_require_source_ref": True,
            "negative_claims_require_search_scope": True,
        },
        "semantic_judgment": {
            "must_distinguish_fact_and_inference": True,
            "must_present_counter_explanation": True,
            "must_disclose_unresolved_assumptions": True,
        },
        "prohibited": [
            "llm_similarity_as_sole_evidence",
            "unexecuted_test_as_passed",
            "unread_file_citation",
            "hidden_conflicting_evidence",
            "unsupported_authorization_inference",
            "invented_tool_result",
        ],
        "stop_conditions": [
            "dominant_explanation_established",
            "remaining_uncertainty_does_not_change_action",
            "evidence_value_exhausted",
            "investigation_budget_exhausted",
            "user_authority_required",
            "user_information_required",
            "tool_unavailable",
        ],
    }
    value.update(overrides)
    return value


class InvestigationContractTests(unittest.TestCase):
    def test_ledger_requires_complete_hash_bound_steps(self) -> None:
        ledger = _ledger()
        ledger.validate()
        self.assertEqual(ledger.result_refs, {"evidence://search/1"})
        broken = _ledger()
        del broken.data["steps"][0]["result_sha256"]
        with self.assertRaises(LedgerError):
            broken.validate()
        tampered = _ledger()
        tampered.data["steps"][0]["result"]["exit_code"] = 9
        with self.assertRaises(LedgerError):
            tampered.validate()

    def test_ledger_rejects_budget_overrun_and_unknown_hypothesis(self) -> None:
        overrun = _ledger()
        overrun.data["usage"]["tool_calls"] = 9
        with self.assertRaises(LedgerError):
            overrun.validate()
        unknown = _ledger()
        unknown.data["steps"][0]["hypothesis_effect"]["supports"] = ["H_missing"]
        with self.assertRaises(LedgerError):
            unknown.validate()

    def test_grounding_rejects_unknown_evidence_and_hypothesis_blocking(self) -> None:
        ledger = _ledger()
        ledger.validate()
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(evidence_refs=["evidence://missing"]),
                ledger,
            )
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(
                    origin="HYPOTHESIS",
                    assessment_state="UNKNOWN",
                    blocking=True,
                ),
                ledger,
            )

    def test_supported_finding_requires_counter_investigation(self) -> None:
        ledger = _ledger()
        ledger.validate()
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(assessment_state="SUPPORTED"),
                ledger,
            )
        validate_investigated_finding(
            _finding(
                assessment_state="SUPPORTED",
                counter_explanation={
                    "statement": "The shared interface may require this change.",
                    "investigation_result": "WEAKENED",
                    "evidence_refs": ["evidence://search/1"],
                },
            ),
            ledger,
        )

    def test_contract_limits_strong_findings_until_required_directions_complete(self) -> None:
        contract = _contract(required_investigation=[
            "recover_intent",
            "inspect_direct_dependency",
            "search_additional_authorization",
        ])
        supported = _finding(
            assessment_state="SUPPORTED",
            counter_explanation={
                "statement": "A shared interface may require the change.",
                "investigation_result": "WEAKENED",
                "evidence_refs": ["evidence://search/1"],
            },
        )
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                supported,
                _ledger(),
                investigation_contract=contract,
            )
        validate_investigated_finding(
            _finding(
                assessment_state="SUPPORTED_WITH_LIMITS",
                remaining_uncertainty=["Additional authorization was not searched."],
            ),
            _ledger(),
            investigation_contract=contract,
        )

    def test_contract_shape_and_finding_type_are_executed(self) -> None:
        ledger = _ledger()
        for field in _contract():
            invalid = _contract()
            del invalid[field]
            with self.subTest(field=field), self.assertRaises(GroundingError):
                validate_investigated_finding(
                    _finding(),
                    ledger,
                    investigation_contract=invalid,
                )
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(),
                ledger,
                investigation_contract=_contract(extra=True),
            )
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(finding_type="different"),
                ledger,
                investigation_contract=_contract(),
            )

    def test_contract_rejects_similarity_only_unread_location_and_hidden_conflict(self) -> None:
        similarity = _ledger(tool="llm.similarity")
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(),
                similarity,
                investigation_contract=_contract(),
            )
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(locations=[{"path": "src/unread.py", "line": 1}]),
                _ledger(),
                investigation_contract=_contract(),
            )
        conflicted = _ledger()
        conflicted.data["material_conflicting_evidence_refs"] = ["evidence://search/1"]
        with self.assertRaises(GroundingError):
            validate_investigated_finding(_finding(), conflicted)

    def test_contract_rejects_report_complete_untyped_fact_and_missing_evidence_class(self) -> None:
        report_complete = _ledger()
        report_complete.data["stop"] = {
            "reason": "REPORT_COMPLETE",
            "bounded_result": False,
        }
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(),
                report_complete,
                investigation_contract=_contract(),
            )
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(confirmed_facts=[{
                    "statement": "The test passed.",
                    "evidence_refs": ["evidence://search/1"],
                }]),
                _ledger(),
            )
        missing_class = _ledger()
        del missing_class.data["steps"][0]["evidence_class"]
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(),
                missing_class,
                investigation_contract=_contract(),
            )

    def test_user_source_negative_scope_and_stop_reason_are_verified(self) -> None:
        ledger = _ledger()
        ledger.data["steps"][0]["result"] = {
            "source_type": "explicit_user",
            "searched_scope": ["src/"],
            "matches": [],
        }
        ledger.data["steps"][0]["result_sha256"] = hashlib.sha256(
            json.dumps(
                ledger.data["steps"][0]["result"],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        validate_investigated_finding(
            _finding(confirmed_facts=[
                {
                    "kind": "explicit_user_constraint",
                    "statement": "Do not change payments.",
                    "source_type": "explicit_user",
                    "source_ref": "evidence://search/1",
                    "evidence_refs": ["evidence://search/1"],
                },
                {
                    "kind": "negative_search",
                    "statement": "No payment references were found.",
                    "search_scope": ["src/"],
                    "evidence_refs": ["evidence://search/1"],
                },
            ]),
            ledger,
        )
        ledger.data["stop"] = {"reason": "BUDGET_EXHAUSTED", "bounded_result": False}
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(),
                ledger,
                investigation_contract=_contract(),
            )

    def test_test_pass_and_negative_claims_require_specific_grounding(self) -> None:
        failing = _ledger(exit_code=1)
        failing.validate()
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(confirmed_facts=[{
                    "kind": "test_passed",
                    "statement": "The test passed.",
                    "evidence_refs": ["evidence://search/1"],
                }]),
                failing,
            )
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(confirmed_facts=[{
                    "kind": "negative_search",
                    "statement": "No references were found.",
                    "evidence_refs": ["evidence://search/1"],
                }]),
                _ledger(),
            )

    def test_permissions_are_checked_without_changing_evidence_status(self) -> None:
        ledger = _ledger(tool="remote.github.read")
        ledger.data["steps"][0]["writes"] = True
        ledger.validate()
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(),
                ledger,
                allowed_tools={"ripgrep"},
            )
        with self.assertRaises(GroundingError):
            validate_investigated_finding(
                _finding(),
                ledger,
                allowed_tools={"remote.github.read"},
                allow_writes=False,
            )

    def test_stop_policy_is_bounded_and_requires_counter_check(self) -> None:
        self.assertEqual(
            evaluate_stop(dominant_explanation=True, counter_hypothesis_checked=False),
            StopDecision.CONTINUE,
        )
        self.assertEqual(
            evaluate_stop(dominant_explanation=True, counter_hypothesis_checked=True),
            StopDecision.DOMINANT_EXPLANATION,
        )
        self.assertEqual(
            evaluate_stop(consecutive_no_value_calls=2),
            StopDecision.NO_NEW_DECISION_VALUE,
        )
        self.assertEqual(
            evaluate_stop(budget_exhausted=True),
            StopDecision.BUDGET_EXHAUSTED,
        )

    def test_canonical_finding_flows_through_grounding_and_bilingual_renderer(self) -> None:
        finding = {
            "schema_version": "aet-investigated-finding/v1",
            "finding_id": "finding_1",
            "finding_type": "possible_scope_expansion",
            "origin": "INVESTIGATED_FINDING",
            "authoritative_status": "UNKNOWN",
            "assessment_state": "SUPPORTED",
            "blocking": False,
            "conclusion": "The change may expand scope.",
            "confirmed_facts": [{
                "statement": "The path changed.",
                "kind": "tool_fact",
                "evidence_refs": ["evidence://search/1"],
            }],
            "engineering_judgment": "The change lacks a demonstrated dependency.",
            "counter_explanation": {
                "statement": "A shared interface may require the change.",
                "investigation_result": "WEAKENED",
                "evidence_refs": ["evidence://search/1"],
            },
            "remaining_uncertainty": ["A later authorization may exist."],
            "locations": [{"path": "src/payment.py", "line": 1}],
            "recommended_action": "Split the change or provide its dependency.",
            "evidence_refs": ["evidence://search/1"],
        }
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "schemas" / "investigated-finding-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        self.assertTrue(set(schema["required"]).issubset(finding))
        self.assertTrue(set(finding).issubset(schema["properties"]))
        ledger = _ledger()
        ledger.validate()
        validate_investigated_finding(finding, ledger)
        self.assertIn("Evidence references", render_investigated_finding(finding, "en"))
        self.assertIn("原始证据", render_investigated_finding(finding, "zh-CN"))


if __name__ == "__main__":
    unittest.main()
