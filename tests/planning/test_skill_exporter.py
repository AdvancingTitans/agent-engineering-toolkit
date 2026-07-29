from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from aet.planning.candidate_parser import parse_candidate
from aet.planning.errors import PlanningError
from aet.planning.package_builder import build_plan_package
from aet.planning.skill_exporter import (
    export_plan_skill,
    validate_exported_skill,
)
from aet.planning.validator import validate_plan_candidate

from tests.planning.test_models import candidate_value
from tests.planning.test_validator import context_value


class PlanSkillExporterTests(unittest.TestCase):
    def _package(self, root: Path, candidate: dict | None = None) -> Path:
        context = context_value()
        result = validate_plan_candidate(
            context,
            parse_candidate(json.dumps(candidate or candidate_value())),
        )
        return build_plan_package(context, result, root / "plan")

    def test_exports_minimal_deterministic_target_skills(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = self._package(root)
            first = export_plan_skill(
                package,
                root / "codex",
                target="codex",
            )
            second = export_plan_skill(
                package,
                root / "generic",
                target="generic",
            )
            self.assertEqual(validate_exported_skill(first)["status"], "PASS")
            self.assertEqual(validate_exported_skill(second)["status"], "PASS")
            first_map = json.loads(
                (first / "references/source-map.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                ["SRC-001", "ev-1"],
                [
                    item["reference_id"]
                    for item in first_map["references"]
                ],
            )
            first_files = {
                item.relative_to(first).as_posix(): item.read_bytes()
                for item in first.rglob("*")
                if item.is_file()
            }
            third = export_plan_skill(
                package,
                root / "codex-copy",
                target="codex",
            )
            third_files = {
                item.relative_to(third).as_posix(): item.read_bytes()
                for item in third.rglob("*")
                if item.is_file()
            }
            self.assertEqual(first_files, third_files)

    def test_rejects_secret_like_content_overwrite_and_unknown_target(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            candidate = deepcopy(candidate_value())
            candidate["edit_items"][0]["intent"] = "Use token=supersecretvalue"
            package = self._package(root, candidate)
            with self.assertRaises(PlanningError):
                export_plan_skill(package, root / "secret", target="codex")
            safe_package = self._package(root / "safe")
            output = export_plan_skill(
                safe_package,
                root / "once",
                target="claude-code",
            )
            with self.assertRaises(PlanningError):
                export_plan_skill(
                    safe_package,
                    output,
                    target="claude-code",
                )
            with self.assertRaises(PlanningError):
                export_plan_skill(
                    safe_package,
                    root / "unknown",
                    target="unknown",
                )


if __name__ == "__main__":
    unittest.main()
