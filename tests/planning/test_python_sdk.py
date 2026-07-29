from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from aet.planning.candidate_parser import parse_candidate
from aet.planning.errors import PlanningError
from aet.planning.models import canonical_json_bytes
from aet.planning.package_builder import build_plan_package
from aet.planning.validator import validate_plan_candidate
from aet_bundle import (
    explain_edit,
    load_plan,
    query_plan_edits,
    render_planner_context,
    validate_plan,
)

from tests.planning.test_models import candidate_value
from tests.planning.test_validator import context_value


class PlanningPythonSdkTests(unittest.TestCase):
    def test_load_query_explain_validate_and_render_are_read_only(self) -> None:
        context = context_value()
        result = validate_plan_candidate(
            context,
            parse_candidate(json.dumps(candidate_value())),
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = build_plan_package(context, result, root / "plan")
            context_path = root / "context.json"
            context_path.write_bytes(canonical_json_bytes(asdict(context)))
            plan = load_plan(package)
            self.assertEqual(validate_plan(package)["status"], "PASS")
            self.assertEqual(
                ["EDIT-001"],
                [
                    item["edit_id"]
                    for item in query_plan_edits(
                        plan,
                        "src/aet/example.py",
                    )
                ],
            )
            self.assertEqual(
                "EDIT-001",
                explain_edit(plan, "EDIT-001")["edit"]["edit_id"],
            )
            rendered = render_planner_context(
                context_path,
                max_chars=100_000,
            )
            self.assertIn('"planning-context/1.0"', rendered)
            with self.assertRaises(PlanningError):
                render_planner_context(context_path, max_chars=1)


if __name__ == "__main__":
    unittest.main()
