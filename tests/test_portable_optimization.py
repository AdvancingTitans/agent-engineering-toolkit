from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aet.bundle import BundleError
from aet.optimization import (
    OptimizationCandidateError,
    build_optimization_candidate,
)

from tests.test_evidence_bundle_protocol import (
    _copy_minimal,
    _read_json,
    _read_jsonl,
    _reseal,
    _write_json,
    _write_jsonl,
)


_FIXTURE = Path(__file__).parent / "fixtures" / "evidence-bundles" / "minimal"


def _review(
    bundle_id: str = "bundle-fixture-001",
    *,
    disposition: str = "accept",
) -> dict[str, Any]:
    return {
        "protocol": {"name": "portable-review-result", "version": "1.0"},
        "bundle_id": bundle_id,
        "conclusions": [
            {
                "id": "review-conclusion-001",
                "statement": "目标验证结论具有声明的证据边界。",
                "disposition": disposition,
                "claim_refs": ["claim-001"],
                "evidence_refs": ["ev-001"],
                "counter_evidence_refs": [],
                "reasoning_summary": "结论只引用 Bundle 中的记录。",
                "limitations": ["不扩展到未声明的验证范围。"],
            }
        ],
        "unresolved_questions": [],
    }


def _support(
    bundle_path: Path,
    review: dict[str, Any],
    *,
    review_refs: list[str] | None = None,
    run_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "bundle_path": bundle_path,
        "review": review,
        "review_refs": ["review-conclusion-001"]
        if review_refs is None
        else review_refs,
        "run_refs": [] if run_refs is None else run_refs,
    }


def _candidate(**overrides: Any) -> dict[str, Any]:
    arguments = {
        "candidate_id": "optimization-candidate-001",
        "target": "grounding_validator",
        "observed_problem": "审查结果可能越过已有证据边界。",
        "proposed_change": "在隔离 Fixture 中评估更严格的引用规则。",
        "expected_effect": "减少无依据结论。",
        "possible_regression": "可能拒绝仍可接受的有界结论。",
    }
    arguments.update(overrides)
    return arguments


def _make_second_task(root: Path) -> Path:
    bundle = _copy_minimal(root, "second-task")
    manifest = _read_json(bundle / "manifest.json")
    manifest["bundle"]["id"] = "bundle-fixture-002"
    manifest["task"]["task_id"] = "task-fixture-002"
    _write_json(bundle / "manifest.json", manifest)
    index = _read_json(bundle / "index.json")
    index["bundle_id"] = "bundle-fixture-002"
    _write_json(bundle / "index.json", index)
    evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
    evidence[0]["bindings"]["task_id"] = "task-fixture-002"
    _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)
    _reseal(bundle)
    return bundle


class PortableOptimizationTests(unittest.TestCase):
    def test_schema_has_exact_plan_fields_and_target_enum(self) -> None:
        schema = json.loads(
            (
                Path(__file__).parents[1]
                / "schemas"
                / "optimization"
                / "v1"
                / "candidate.schema.json"
            ).read_text(encoding="utf-8")
        )
        fields = {
            "id",
            "target",
            "observedProblem",
            "supportingRunRefs",
            "supportingBundleRefs",
            "supportingReviewRefs",
            "proposedChange",
            "expectedEffect",
            "possibleRegression",
            "evaluationRequired",
        }
        self.assertEqual(fields, set(schema["required"]))
        self.assertEqual(fields, set(schema["properties"]))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            {
                "source_adapter",
                "observation_extractor",
                "investigation_policy",
                "tool_selection",
                "bundle_selector",
                "consumer_guide",
                "grounding_validator",
            },
            set(schema["properties"]["target"]["enum"]),
        )
        self.assertIs(True, schema["properties"]["evaluationRequired"]["const"])

    def test_two_independent_tasks_build_exact_evaluation_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            second = _make_second_task(Path(temporary))
            result = build_optimization_candidate(
                **_candidate(),
                supporting_inputs=[
                    _support(_FIXTURE, _review()),
                    _support(second, _review("bundle-fixture-002")),
                ],
            )
        self.assertEqual(
            {
                "id",
                "target",
                "observedProblem",
                "supportingRunRefs",
                "supportingBundleRefs",
                "supportingReviewRefs",
                "proposedChange",
                "expectedEffect",
                "possibleRegression",
                "evaluationRequired",
            },
            set(result),
        )
        self.assertEqual(
            ["bundle-fixture-001", "bundle-fixture-002"],
            result["supportingBundleRefs"],
        )
        self.assertEqual(
            [
                "bundle-fixture-001#review-conclusion:review-conclusion-001",
                "bundle-fixture-002#review-conclusion:review-conclusion-001",
            ],
            result["supportingReviewRefs"],
        )
        self.assertEqual([], result["supportingRunRefs"])
        self.assertIs(True, result["evaluationRequired"])

    def test_one_task_requires_explicit_high_or_critical_failure(self) -> None:
        support = [_support(_FIXTURE, _review(disposition="request_change"))]
        with self.assertRaises(OptimizationCandidateError):
            build_optimization_candidate(
                **_candidate(),
                supporting_inputs=support,
            )
        result = build_optimization_candidate(
            **_candidate(),
            supporting_inputs=support,
            deterministic_failure={
                "severity": "high",
                "bundle_ref": "bundle-fixture-001",
                "review_ref": "review-conclusion-001",
                "claim_ref": "claim-001",
                "evidence_refs": ["ev-001"],
            },
        )
        self.assertIs(True, result["evaluationRequired"])

    def test_same_task_twice_is_not_independent_and_duplicate_bundle_fails(self) -> None:
        with self.assertRaises(OptimizationCandidateError):
            build_optimization_candidate(
                **_candidate(),
                supporting_inputs=[
                    _support(_FIXTURE, _review()),
                    _support(_FIXTURE, _review()),
                ],
            )

    def test_failure_gate_rejects_medium_and_unselected_references(self) -> None:
        support = [_support(_FIXTURE, _review(disposition="request_change"))]
        base_failure = {
            "severity": "medium",
            "bundle_ref": "bundle-fixture-001",
            "review_ref": "review-conclusion-001",
            "claim_ref": "claim-001",
            "evidence_refs": ["ev-001"],
        }
        with self.assertRaises(OptimizationCandidateError):
            build_optimization_candidate(
                **_candidate(),
                supporting_inputs=support,
                deterministic_failure=base_failure,
            )
        forged = dict(base_failure)
        forged.update({"severity": "critical", "claim_ref": "claim-missing"})
        with self.assertRaises(OptimizationCandidateError):
            build_optimization_candidate(
                **_candidate(),
                supporting_inputs=support,
                deterministic_failure=forged,
            )

    def test_support_must_be_a_valid_review_and_run_record_source(self) -> None:
        bad_review = _review()
        bad_review["conclusions"][0]["evidence_refs"] = ["ev-missing"]
        with self.assertRaises(BundleError):
            build_optimization_candidate(
                **_candidate(),
                supporting_inputs=[_support(_FIXTURE, bad_review)],
            )
        with self.assertRaises(OptimizationCandidateError):
            build_optimization_candidate(
                **_candidate(),
                supporting_inputs=[
                    _support(
                        _FIXTURE,
                        _review(disposition="request_change"),
                        run_refs=["src-001"],
                    )
                ],
                deterministic_failure={
                    "severity": "high",
                    "bundle_ref": "bundle-fixture-001",
                    "review_ref": "review-conclusion-001",
                    "claim_ref": "claim-001",
                    "evidence_refs": ["ev-001"],
                },
            )

    def test_builder_has_no_asset_write_side_effect(self) -> None:
        before = {
            path: path.read_bytes()
            for path in (
                _FIXTURE / "manifest.json",
                _FIXTURE / "core" / "claims.jsonl",
                _FIXTURE / "core" / "evidence.jsonl",
            )
        }
        build_optimization_candidate(
            **_candidate(),
            supporting_inputs=[
                _support(_FIXTURE, _review(disposition="request_change"))
            ],
            deterministic_failure={
                "severity": "critical",
                "bundle_ref": "bundle-fixture-001",
                "review_ref": "review-conclusion-001",
                "claim_ref": "claim-001",
                "evidence_refs": ["ev-001"],
            },
        )
        self.assertEqual(before, {path: path.read_bytes() for path in before})


if __name__ == "__main__":
    unittest.main()
