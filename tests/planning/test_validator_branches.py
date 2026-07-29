from __future__ import annotations

import json
import unittest
from dataclasses import replace

from aet.planning.candidate_parser import parse_candidate
from aet.planning.models import (
    LineRange,
    OmissionSummary,
    PlanningConstraints,
    PlanningGap,
    WorkspaceIdentity,
)
from aet.planning.validator import validate_plan_candidate

from tests.planning.test_models import candidate_value
from tests.planning.test_validator import context_value


def candidate():
    return parse_candidate(json.dumps(candidate_value()))


def codes(result) -> set[str]:
    return {item.code for item in result.diagnostics}


class PlanningValidatorBranchTests(unittest.TestCase):
    def test_identity_schema_duplicates_and_budget_fail_closed(self) -> None:
        context = context_value()
        invalid_context = context_value()
        object.__setattr__(invalid_context, "schema_version", "planning-context/9")
        invalid_candidate = replace(
            candidate(),
            schema_version="plan-candidate/9",
            request_id="REQ-OTHER",
        )
        result = validate_plan_candidate(invalid_context, invalid_candidate)
        self.assertEqual("BLOCKED", result.status)
        self.assertIn("INVALID_REQUEST", codes(result))
        self.assertIn("INVALID_CANDIDATE", codes(result))
        self.assertIn("IDENTITY_MISMATCH", codes(result))

        mismatched_workspace = replace(
            context,
            workspace=WorkspaceIdentity(
                "PASS",
                "other-workspace",
                "d" * 40,
                "e" * 64,
            ),
        )
        result = validate_plan_candidate(mismatched_workspace, candidate())
        self.assertIn("IDENTITY_MISMATCH", codes(result))

        original = candidate()
        duplicate_edits = replace(
            original,
            edit_items=[original.edit_items[0], original.edit_items[0]],
        )
        self.assertIn(
            "INVALID_CANDIDATE",
            codes(validate_plan_candidate(context, duplicate_edits)),
        )
        duplicate_verification = replace(
            original,
            verification_steps=[
                original.verification_steps[0],
                original.verification_steps[0],
            ],
        )
        self.assertIn(
            "INVALID_CANDIDATE",
            codes(validate_plan_candidate(context, duplicate_verification)),
        )
        tiny_request = replace(
            context.request,
            budgets=replace(context.request.budgets, max_edit_items=0),
        )
        tiny_context = replace(context, request=tiny_request)
        result = validate_plan_candidate(tiny_context, original)
        self.assertEqual("PARTIAL", result.status)
        self.assertIn("BUDGET_EXHAUSTED", codes(result))

    def test_reference_source_symbol_range_dependency_and_completion_branches(self) -> None:
        context = context_value()
        original = candidate()
        item = original.edit_items[0]

        wrong_kind = replace(
            original,
            edit_items=[
                replace(
                    item,
                    evidence_refs=["SRC-001"],
                    source_refs=[],
                )
            ],
        )
        self.assertIn(
            "REFERENCE_KIND_MISMATCH",
            codes(validate_plan_candidate(context, wrong_kind)),
        )

        atlas_as_source = replace(
            original,
            edit_items=[
                replace(
                    item,
                    evidence_refs=[],
                    source_refs=["node:claim:claim-1"],
                )
            ],
        )
        self.assertIn(
            "REFERENCE_KIND_MISMATCH",
            codes(validate_plan_candidate(context, atlas_as_source)),
        )

        for source_status, expected in (
            ("STALE", "SOURCE_STALE"),
            ("MISSING", "SOURCE_MISSING"),
        ):
            with self.subTest(source_status=source_status):
                result = validate_plan_candidate(
                    context_value(source_status=source_status),
                    replace(
                        original,
                        edit_items=[
                            replace(item, evidence_refs=[])
                        ],
                    ),
                )
                self.assertIn(expected, codes(result))

        symbol = replace(
            original,
            edit_items=[replace(item, symbol="other_symbol")],
        )
        self.assertIn(
            "SYMBOL_NOT_FOUND",
            codes(validate_plan_candidate(context, symbol)),
        )
        out_of_range = replace(
            original,
            edit_items=[
                replace(item, source_range=LineRange(1, 20))
            ],
        )
        self.assertIn(
            "SOURCE_STALE",
            codes(validate_plan_candidate(context, out_of_range)),
        )
        missing_dependency = replace(
            original,
            edit_items=[replace(item, dependencies=["EDIT-MISSING"])],
        )
        self.assertIn(
            "REFERENCE_NOT_FOUND",
            codes(validate_plan_candidate(context, missing_dependency)),
        )
        completion = replace(
            original,
            summary="Tests passed and the change has been implemented.",
            edit_items=[
                replace(item, expected_change="Already implemented and verified successfully.")
            ],
        )
        result = validate_plan_candidate(context, completion)
        self.assertIn("EXECUTION_ATTEMPT", codes(result))
        self.assertIn("WRITE_ATTEMPT", codes(result))

    def test_verification_and_bounded_complete_rejection_branches(self) -> None:
        context = context_value()
        original = candidate()
        no_verification = replace(original, verification_steps=[])
        result = validate_plan_candidate(context, no_verification)
        self.assertEqual("NEEDS_EVIDENCE", result.status)
        self.assertIn("EVIDENCE_REQUIRED", codes(result))

        bad_reference = replace(
            original,
            verification_steps=[
                replace(
                    original.verification_steps[0],
                    edit_refs=["EDIT-MISSING"],
                )
            ],
        )
        self.assertIn(
            "REFERENCE_NOT_FOUND",
            codes(validate_plan_candidate(context, bad_reference)),
        )
        executed = replace(
            original,
            verification_steps=[
                replace(original.verification_steps[0], status="PASS")
            ],
        )
        self.assertIn(
            "EXECUTION_ATTEMPT",
            codes(validate_plan_candidate(context, executed)),
        )

        source = replace(
            context.source_sites[0],
            read_status="UNSUPPORTED",
        )
        bounded_context = replace(
            context,
            source_sites=[source],
            conflicts=[
                {
                    "id": "conflict-high",
                    "resolution_status": "unresolved",
                    "priority": "high",
                }
            ],
            gaps=[
                PlanningGap(
                    "GAP-CRITICAL",
                    "EVIDENCE_REQUIRED",
                    "ERROR",
                    "Critical evidence is missing.",
                    True,
                )
            ],
            omitted=OmissionSummary(nodes=1),
            constraints=PlanningConstraints(
                allowed_paths=["src/**"],
                protected_paths=[],
                scope_status="UNRESOLVED",
            ),
        )
        ungrounded_item = replace(
            original.edit_items[0],
            evidence_refs=[],
            atlas_refs=[],
            source_refs=[],
        )
        bounded = replace(
            original,
            coverage_claim="BOUNDED_COMPLETE",
            edit_items=[ungrounded_item],
        )
        result = validate_plan_candidate(bounded_context, bounded)
        self.assertEqual("PARTIAL", result.status)
        self.assertIn("OVERCLAIMED_COVERAGE", codes(result))
        message = next(
            item.message
            for item in result.diagnostics
            if item.code == "OVERCLAIMED_COVERAGE"
        )
        for marker in (
            "omitted data",
            "unsupported source language",
            "critical gap",
            "unresolved high-priority conflict",
            "lacks references",
            "scope is unresolved",
        ):
            self.assertIn(marker, message)

    def test_reference_strength_variants_and_record_identifier_fallbacks(self) -> None:
        context = context_value()
        original = candidate()
        item = original.edit_items[0]
        variants = [
            (
                replace(
                    item,
                    evidence_refs=[],
                    source_refs=["SRC-001"],
                ),
                context,
                "SOURCE_CONFIRMED",
            ),
            (
                replace(
                    item,
                    disposition="OPTIONAL",
                    evidence_refs=[],
                    source_refs=[],
                    limitations=["Needs a caller review."],
                ),
                context,
                "INFERRED_WITH_LIMITS",
            ),
            (
                replace(
                    item,
                    evidence_refs=[],
                    source_refs=["SRC-001"],
                ),
                context_value(source_status="STALE"),
                "NEEDS_EVIDENCE",
            ),
            (
                replace(
                    item,
                    disposition="OPTIONAL",
                    evidence_refs=[],
                    source_refs=[],
                    limitations=[],
                ),
                context,
                "UNKNOWN",
            ),
        ]
        for selected, selected_context, expected in variants:
            with self.subTest(expected=expected):
                result = validate_plan_candidate(
                    selected_context,
                    replace(original, edit_items=[selected]),
                )
                self.assertEqual(
                    expected,
                    result.plan["edit_items"][0]["reference_strength"],
                )

        fallback_context = replace(
            context,
            relevant_claims=[
                {"reference_id": "REF-FALLBACK"},
                {"node_id": "NODE-FALLBACK"},
                {},
            ],
        )
        fallback = replace(
            original,
            edit_items=[
                replace(
                    item,
                    evidence_refs=["REF-FALLBACK", "NODE-FALLBACK"],
                    source_refs=[],
                )
            ],
        )
        result = validate_plan_candidate(fallback_context, fallback)
        self.assertNotIn("REFERENCE_NOT_FOUND", codes(result))


if __name__ == "__main__":
    unittest.main()
