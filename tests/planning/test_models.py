from __future__ import annotations

import json
import unittest

from aet.planning.candidate_parser import parse_candidate
from aet.planning.errors import PlanningError, PlanningErrorCode
from aet.planning.models import (
    PlanningBudgets,
    PlanningRequest,
    WorkspaceIdentity,
    canonical_json_bytes,
    canonical_relative_path,
    stable_plan_id,
    stable_request_id,
)
from aet.planning.schemas import SchemaKind, load_schema


def candidate_value() -> dict:
    return {
        "schema_version": "plan-candidate/1.0",
        "request_id": "REQ-EXAMPLE",
        "summary": "Propose one bounded edit.",
        "coverage_claim": "BEST_EFFORT",
        "edit_items": [
            {
                "edit_id": "EDIT-001",
                "disposition": "REQUIRED",
                "path": "src/aet/example.py",
                "symbol": "run",
                "source_range": {"start_line": 1, "end_line": 4},
                "intent": "Preserve one failure state.",
                "expected_change": "Add a proposed branch for the failure state.",
                "rationale": "The current source site drops the state.",
                "behavior_links": ["behavior:failure"],
                "evidence_refs": ["ev-1"],
                "atlas_refs": [],
                "source_refs": ["SRC-001"],
                "dependencies": [],
                "tests": ["tests/test_example.py"],
                "risks": [],
                "limitations": ["This does not establish runtime success."],
            }
        ],
        "investigation_items": [],
        "verification_steps": [
            {
                "verification_id": "VERIFY-001",
                "description": "Run the focused regression after implementation.",
                "command": ["python", "-m", "unittest", "tests.test_example"],
                "edit_refs": ["EDIT-001"],
                "expected_result": "exit_code=0",
                "status": "PENDING",
            }
        ],
        "assumptions": [],
        "unresolved": [],
    }


class PlanningModelTests(unittest.TestCase):
    def test_schema_files_are_valid_json_with_explicit_ids(self) -> None:
        for kind in SchemaKind:
            schema = load_schema(kind)
            self.assertEqual(schema["type"], "object")
            self.assertTrue(schema["$id"].startswith("https://"))

    def test_request_and_plan_ids_are_stable(self) -> None:
        workspace = WorkspaceIdentity("PASS", "workspace-1", "a" * 40, "b" * 64)
        request_id = stable_request_id("Change one behavior.", workspace)
        request = PlanningRequest(
            schema_version="planning-request/1.0",
            request_id=request_id,
            user_goal="Change one behavior.",
            acceptance_criteria=[],
            non_goals=[],
            allowed_paths=["src/**"],
            protected_paths=["tests/fixtures/**"],
            required_verification=["python -m unittest"],
            bundle_identity="bundle-1",
            atlas_identity=None,
            workspace_identity=workspace,
            budgets=PlanningBudgets(),
            allowed_scope_status="RESOLVED",
        )
        first = stable_plan_id(request, workspace, "bundle-1")
        second = stable_plan_id(request, workspace, "bundle-1")
        self.assertEqual(first, second)
        self.assertEqual(canonical_json_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}\n')

    def test_canonical_path_rejects_every_escape_form(self) -> None:
        invalid = [
            "/etc/passwd",
            "../secret",
            "src/../secret",
            "./src/a.py",
            "src\\a.py",
            "",
            "src//a.py",
            "src/\x00a.py",
        ]
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(PlanningError) as raised:
                    canonical_relative_path(value)
                self.assertEqual(raised.exception.code, PlanningErrorCode.PATH_ESCAPE)
        self.assertEqual(canonical_relative_path("src/aet/a.py"), "src/aet/a.py")

    def test_candidate_parser_rejects_free_text_duplicate_keys_and_unknown_fields(self) -> None:
        with self.assertRaises(PlanningError):
            parse_candidate("```json\n{}\n```")
        with self.assertRaises(PlanningError):
            parse_candidate('{"schema_version":"plan-candidate/1.0","schema_version":"x"}')
        value = candidate_value()
        value["unexpected"] = True
        with self.assertRaises(PlanningError):
            parse_candidate(json.dumps(value))

    def test_candidate_parser_builds_typed_candidate(self) -> None:
        parsed = parse_candidate(json.dumps(candidate_value()))
        self.assertEqual(parsed.edit_items[0].edit_id, "EDIT-001")
        self.assertEqual(parsed.edit_items[0].source_range.start_line, 1)
        self.assertEqual(parsed.verification_steps[0].status, "PENDING")


if __name__ == "__main__":
    unittest.main()
