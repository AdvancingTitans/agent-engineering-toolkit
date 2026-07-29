from __future__ import annotations

import json
import unittest

from aet.planning.candidate_parser import parse_candidate
from aet.planning.models import (
    OmissionSummary,
    PlanningBudgets,
    PlanningConstraints,
    PlanningContext,
    PlanningGap,
    PlanningRequest,
    SourceSite,
    WorkspaceIdentity,
    canonical_json_bytes,
)
from aet.planning.validator import validate_plan_candidate

from .test_models import candidate_value


def context_value(
    *,
    allowed_paths: list[str] | None = None,
    protected_paths: list[str] | None = None,
    omitted: OmissionSummary | None = None,
    conflicts: list[dict] | None = None,
    source_status: str = "CONFIRMED",
) -> PlanningContext:
    workspace = WorkspaceIdentity("PASS", "workspace-1", "a" * 40, "b" * 64)
    request = PlanningRequest(
        schema_version="planning-request/1.0",
        request_id="REQ-EXAMPLE",
        user_goal="Change one behavior.",
        acceptance_criteria=["Preserve the failure state."],
        non_goals=["Do not execute commands while planning."],
        allowed_paths=allowed_paths or ["src/**", "tests/**"],
        protected_paths=protected_paths or ["tests/fixtures/**", ".aet/**"],
        required_verification=["python -m unittest"],
        bundle_identity="bundle-1",
        atlas_identity="atlas-1",
        workspace_identity=workspace,
        budgets=PlanningBudgets(max_edit_items=100),
        allowed_scope_status="RESOLVED",
    )
    return PlanningContext(
        schema_version="planning-context/1.0",
        request=request,
        workspace=workspace,
        relevant_claims=[{"id": "claim-1"}],
        relevant_evidence=[{"id": "ev-1", "status": "FAIL"}],
        counter_evidence=[],
        conflicts=conflicts or [],
        unknowns=[],
        atlas_nodes=[{"id": "node:claim:claim-1"}],
        source_sites=[
            SourceSite(
                source_id="SRC-001",
                path="src/aet/example.py",
                symbol="run",
                start_line=1,
                end_line=10,
                content_hash="c" * 64,
                language="python",
                role="IMPLEMENTATION",
                read_status=source_status,
                reference_ids=["ev-1"],
            )
        ],
        candidate_relations=[],
        constraints=PlanningConstraints(
            allowed_paths=allowed_paths or ["src/**", "tests/**"],
            protected_paths=protected_paths or ["tests/fixtures/**", ".aet/**"],
            scope_status="RESOLVED",
        ),
        gaps=[],
        omitted=omitted or OmissionSummary(),
    )


def validate(value: dict, context: PlanningContext | None = None):
    return validate_plan_candidate(
        context or context_value(),
        parse_candidate(json.dumps(value)),
    )


class PlanningValidatorTests(unittest.TestCase):
    def test_valid_candidate_is_ready_and_deterministic(self) -> None:
        first = validate(candidate_value())
        second = validate(candidate_value())
        self.assertEqual(first.status, "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(first.plan["authority"], "PROPOSED")
        self.assertEqual(canonical_json_bytes(first.plan), canonical_json_bytes(second.plan))

    def test_required_reference_is_mandatory_and_forged_reference_blocks(self) -> None:
        missing = candidate_value()
        missing["edit_items"][0]["evidence_refs"] = []
        missing["edit_items"][0]["source_refs"] = []
        result = validate(missing)
        self.assertEqual(result.status, "NEEDS_EVIDENCE")
        self.assertIn("EVIDENCE_REQUIRED", {item.code for item in result.diagnostics})

        forged = candidate_value()
        forged["edit_items"][0]["evidence_refs"] = ["ev-forged"]
        result = validate(forged)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("REFERENCE_NOT_FOUND", {item.code for item in result.diagnostics})

    def test_protected_path_is_always_blocked(self) -> None:
        value = candidate_value()
        value["edit_items"][0]["path"] = "tests/fixtures/private.py"
        value["edit_items"][0]["source_refs"] = []
        result = validate(value)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("PROTECTED_PATH", {item.code for item in result.diagnostics})

    def test_all_path_escape_forms_are_blocked(self) -> None:
        for path in ("/tmp/a.py", "../a.py", "src/../a.py", "src\\a.py"):
            value = candidate_value()
            value["edit_items"][0]["path"] = path
            value["edit_items"][0]["source_refs"] = []
            with self.subTest(path=path):
                result = validate(value)
                self.assertEqual(result.status, "BLOCKED")
                self.assertIn("PATH_ESCAPE", {item.code for item in result.diagnostics})

    def test_source_path_mismatch_and_stale_source_fail_closed(self) -> None:
        value = candidate_value()
        value["edit_items"][0]["path"] = "src/aet/other.py"
        result = validate(value)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("REFERENCE_KIND_MISMATCH", {item.code for item in result.diagnostics})

        result = validate(candidate_value(), context_value(source_status="STALE"))
        self.assertEqual(result.status, "NEEDS_EVIDENCE")
        self.assertIn("SOURCE_STALE", {item.code for item in result.diagnostics})

    def test_bounded_complete_rejects_omission_conflict_and_critical_gap(self) -> None:
        value = candidate_value()
        value["coverage_claim"] = "BOUNDED_COMPLETE"
        conflict = {
            "id": "conflict-1",
            "resolution_status": "unresolved",
            "priority": "high",
        }
        context = context_value(
            omitted=OmissionSummary(nodes=1),
            conflicts=[conflict],
        )
        context = PlanningContext(
            **{
                **context.__dict__,
                "gaps": [
                    PlanningGap(
                        "GAP-1",
                        "EVIDENCE_REQUIRED",
                        "ERROR",
                        "Current evidence is incomplete.",
                        True,
                    )
                ],
            }
        )
        result = validate(value, context)
        self.assertEqual(result.status, "PARTIAL")
        self.assertIn("OVERCLAIMED_COVERAGE", {item.code for item in result.diagnostics})

    def test_empty_verification_dependency_cycle_and_completion_claim_are_rejected(self) -> None:
        value = candidate_value()
        value["verification_steps"] = []
        result = validate(value)
        self.assertEqual(result.status, "NEEDS_EVIDENCE")

        value = candidate_value()
        second = dict(value["edit_items"][0])
        second["edit_id"] = "EDIT-002"
        second["source_refs"] = []
        second["evidence_refs"] = ["ev-1"]
        second["dependencies"] = ["EDIT-001"]
        value["edit_items"][0]["dependencies"] = ["EDIT-002"]
        value["edit_items"].append(second)
        result = validate(value)
        self.assertEqual(result.status, "BLOCKED")

        value = candidate_value()
        value["edit_items"][0]["expected_change"] = "Tests passed and the change has been implemented."
        result = validate(value)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("WRITE_ATTEMPT", {item.code for item in result.diagnostics})


if __name__ == "__main__":
    unittest.main()
