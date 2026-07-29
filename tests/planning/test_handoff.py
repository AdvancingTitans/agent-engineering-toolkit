from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from aet.planning.candidate_parser import parse_candidate
from aet.planning.handoff import build_verification_handoff_from_package
from aet.planning.package_builder import build_plan_package
from aet.planning.validator import validate_plan_candidate

from tests.planning.test_models import candidate_value
from tests.planning.test_validator import context_value


def diff_for(path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        "index 1111111..2222222 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )


class VerificationHandoffTests(unittest.TestCase):
    def _package(self, root: Path, *, stale: bool = False) -> Path:
        context = context_value()
        if stale:
            context = replace(
                context,
                relevant_evidence=[
                    {
                        "id": "ev-1",
                        "kind": "proof",
                        "freshness": {"status": "stale"},
                    }
                ],
                source_sites=[
                    replace(context.source_sites[0], read_status="STALE")
                ],
            )
        result = validate_plan_candidate(
            context,
            parse_candidate(json.dumps(candidate_value())),
        )
        return build_plan_package(context, result, root / "plan")

    def test_maps_planned_unplanned_and_test_only_changes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            package = self._package(Path(raw))
            planned = build_verification_handoff_from_package(
                package,
                diff_for("src/aet/example.py"),
            )
            self.assertEqual([], planned["unplanned_paths"])
            self.assertEqual(
                ["src/aet/example.py"],
                planned["planned_changed_paths"],
            )
            self.assertEqual("UNKNOWN", planned["verification_status"])
            self.assertEqual("PENDING", planned["pending_proof"][0]["execution_status"])

            mixed = build_verification_handoff_from_package(
                package,
                diff_for("src/aet/example.py") + diff_for("README.md"),
            )
            self.assertEqual(["README.md"], mixed["unplanned_paths"])

            test_only = build_verification_handoff_from_package(
                package,
                diff_for("tests/test_example.py"),
            )
            self.assertEqual([], test_only["unplanned_paths"])
            self.assertEqual(
                ["EDIT-001"],
                [item["edit_id"] for item in test_only["touched_edit_items"]],
            )
            self.assertTrue(test_only["pending_proof"])

    def test_rename_empty_stale_and_original_plan_immutability(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = self._package(root, stale=True)
            before = {
                item.relative_to(package).as_posix(): item.read_bytes()
                for item in package.rglob("*")
                if item.is_file()
            }
            renamed = build_verification_handoff_from_package(
                package,
                "diff --git a/src/aet/example.py b/src/aet/renamed.py\n"
                "similarity index 100%\n"
                "rename from src/aet/example.py\n"
                "rename to src/aet/renamed.py\n",
            )
            self.assertEqual(
                ["src/aet/renamed.py"],
                renamed["unplanned_paths"],
            )
            self.assertEqual("RENAMED", renamed["changes"][0]["change_type"])
            self.assertEqual(
                ["SRC-001", "ev-1"],
                [
                    item["reference_id"]
                    for item in renamed["stale_evidence"]
                ],
            )
            empty = build_verification_handoff_from_package(package, "")
            self.assertEqual([], empty["changed_paths"])
            self.assertEqual([], empty["pending_proof"])
            self.assertEqual("UNKNOWN", empty["verification_status"])
            self.assertEqual(
                ["src/aet/example.py", "src/aet/renamed.py"],
                [
                    item["path"]
                    for item in renamed["unresolved_regression_lineage"]
                ],
            )
            after = {
                item.relative_to(package).as_posix(): item.read_bytes()
                for item in package.rglob("*")
                if item.is_file()
            }
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
