from __future__ import annotations

import runpy
import tempfile
import unittest
from pathlib import Path

from aet.planning.package_builder import validate_plan_package
from aet.planning.skill_exporter import validate_exported_skill


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/evidence-guided-planner/build_example.py"


class PlannerEndToEndTests(unittest.TestCase):
    def test_three_real_examples_build_complete_portable_outputs(self) -> None:
        namespace = runpy.run_path(str(EXAMPLE))
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "examples"
            summary = namespace["build_examples"](output)
            statuses = {
                item["name"]: item["plan_status"]
                for item in summary["scenarios"]
            }
            self.assertEqual(
                "READY_FOR_HUMAN_REVIEW",
                statuses["single-file"],
            )
            self.assertEqual(
                "READY_FOR_HUMAN_REVIEW",
                statuses["cross-module"],
            )
            self.assertEqual(
                "NEEDS_EVIDENCE",
                statuses["needs-evidence"],
            )
            for name in statuses:
                with self.subTest(name=name):
                    scenario = output / name
                    self.assertEqual(
                        "PASS",
                        validate_plan_package(scenario / "plan")["status"],
                    )
                    self.assertEqual(
                        "PASS",
                        validate_exported_skill(
                            scenario / "exported-skill"
                        )["status"],
                    )
                    handoff = (
                        scenario / "verification-request.json"
                    ).read_text(encoding="utf-8")
                    self.assertIn('"verification_status":"UNKNOWN"', handoff)


if __name__ == "__main__":
    unittest.main()
