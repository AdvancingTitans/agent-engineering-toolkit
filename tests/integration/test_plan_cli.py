from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from aet.cli import main
from aet.planning.models import canonical_json_bytes

from tests.planning.test_models import candidate_value
from tests.planning.test_validator import context_value


ROOT = Path(__file__).resolve().parents[2]


class PlanCliTests(unittest.TestCase):
    def call(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_context_command_runs_without_a_model(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "context.json"
            code, stdout, stderr = self.call(
                [
                    "plan",
                    "context",
                    "--workspace",
                    str(ROOT),
                    "--request-text",
                    "Inspect src/aet/cli.py without editing.",
                    "--allowed-path",
                    "src/aet/cli.py",
                    "--verification",
                    "python -m unittest",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual((code, stderr), (0, ""))
            self.assertTrue(output.is_file())
            context = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(context["schema_version"], "planning-context/1.0")
            self.assertTrue(any(item["critical"] for item in context["gaps"]))
            self.assertEqual(json.loads(stdout)["status"], "PASS")

    def test_candidate_package_and_helper_commands_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            context_path = root / "context.json"
            candidate_path = root / "candidate.json"
            package = root / "plan"
            context_path.write_bytes(canonical_json_bytes(context_value()))
            candidate_path.write_text(
                json.dumps(candidate_value(), ensure_ascii=False),
                encoding="utf-8",
            )
            code, stdout, stderr = self.call(
                [
                    "plan",
                    "validate-candidate",
                    "--context",
                    str(context_path),
                    "--candidate",
                    str(candidate_path),
                    "--output",
                    str(package),
                ]
            )
            self.assertEqual((code, stderr), (0, ""))
            self.assertEqual(json.loads(stdout)["status"], "READY_FOR_HUMAN_REVIEW")
            for argv in (
                ["plan", "validate", str(package)],
                ["plan", "show", str(package)],
                ["plan", "explain", str(package), "--edit", "EDIT-001"],
                ["plan", "trace", str(package), "--path", "src/aet/example.py"],
                ["plan", "gaps", str(package)],
            ):
                with self.subTest(argv=argv):
                    code, stdout, stderr = self.call(argv)
                    self.assertEqual((code, stderr), (0, ""))
                    self.assertTrue(stdout)
            exported = root / "exported-skill"
            code, stdout, stderr = self.call(
                [
                    "plan",
                    "export-skill",
                    str(package),
                    "--target",
                    "codex",
                    "--output",
                    str(exported),
                ]
            )
            self.assertEqual((code, stderr), (0, ""))
            self.assertEqual("PASS", json.loads(stdout)["status"])
            self.assertTrue((exported / "SKILL.md").is_file())
            diff = root / "agent.diff"
            diff.write_text(
                "diff --git a/src/aet/example.py b/src/aet/example.py\n"
                "--- a/src/aet/example.py\n"
                "+++ b/src/aet/example.py\n"
                "@@ -1 +1 @@\n-old\n+new\n",
                encoding="utf-8",
            )
            handoff = root / "verification-request.json"
            code, stdout, stderr = self.call(
                [
                    "plan",
                    "verification-handoff",
                    str(package),
                    "--diff",
                    str(diff),
                    "--output",
                    str(handoff),
                ]
            )
            self.assertEqual((code, stderr), (0, ""))
            self.assertEqual("UNKNOWN", json.loads(stdout)["verification_status"])
            self.assertEqual(
                "verification-handoff/1.0",
                json.loads(handoff.read_text(encoding="utf-8"))["schema_version"],
            )


if __name__ == "__main__":
    unittest.main()
