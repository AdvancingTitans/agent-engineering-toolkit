from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from aet.planning.candidate_parser import parse_candidate
from aet.planning.errors import PlanningError
from aet.planning.helper import explain_edit, list_gaps, load_plan, trace_path
from aet.planning.package_builder import build_plan_package, validate_plan_package
from aet.planning.validator import validate_plan_candidate

from tests.planning.test_models import candidate_value
from tests.planning.test_validator import context_value


class PlanPackageBuilderTests(unittest.TestCase):
    def _result(self):
        context = context_value()
        result = validate_plan_candidate(
            context,
            parse_candidate(json.dumps(candidate_value())),
        )
        return context, result

    def test_package_is_deterministic_copyable_and_queryable(self) -> None:
        context, result = self._result()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = build_plan_package(context, result, root / "first")
            second = build_plan_package(context, result, root / "second")
            first_files = {
                path.relative_to(first).as_posix(): path.read_bytes()
                for path in first.rglob("*")
                if path.is_file()
            }
            second_files = {
                path.relative_to(second).as_posix(): path.read_bytes()
                for path in second.rglob("*")
                if path.is_file()
            }
            self.assertEqual(first_files, second_files)
            copied = root / "copied"
            shutil.copytree(first, copied)
            self.assertEqual(validate_plan_package(copied)["status"], "PASS")
            self.assertEqual(load_plan(copied)["authority"], "PROPOSED")
            self.assertEqual(explain_edit(copied, "EDIT-001")["edit"]["path"], "src/aet/example.py")
            self.assertEqual(trace_path(copied, "src/aet/example.py")["status"], "PASS")
            self.assertEqual(list_gaps(copied)["gaps"], [])

    def test_atomic_replacement_and_tamper_detection(self) -> None:
        context, result = self._result()
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "plan"
            build_plan_package(context, result, output)
            (output / "plan.md").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(PlanningError):
                validate_plan_package(output)
            build_plan_package(context, result, output)
            self.assertEqual(validate_plan_package(output)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
