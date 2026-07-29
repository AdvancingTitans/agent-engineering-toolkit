import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aet.demo.errors import DemoInvariantError
from aet.demo.models import DemoOptions, MutationSpec
from aet.demo.runner import _apply_mutation, run_demo


class DemoRunnerTests(unittest.TestCase):
    def test_real_demo_uses_quick_core_and_detects_stale_proof(self) -> None:
        result = run_demo("stale-proof", DemoOptions())
        self.assertEqual(result.overall_status, "PASS")
        self.assertEqual(result.execution_status, "PASS")
        self.assertEqual(result.before_state, "EXACT_MATCH")
        self.assertEqual(result.after_state, "RELEVANT_FILES_CHANGED")
        self.assertEqual((result.network_calls, result.llm_calls), (0, 0))
        self.assertIsNone(result.workspace_path)

    def test_keep_reports_real_workspace_and_proof(self) -> None:
        result = run_demo("stale-proof", DemoOptions(keep=True))
        self.assertEqual(result.overall_status, "PASS")
        self.assertTrue(Path(result.workspace_path).is_dir())
        self.assertTrue(Path(result.proof_path).is_file())
        import shutil

        shutil.rmtree(Path(result.workspace_path).parent)

    def test_child_failure_and_timeout_never_pass(self) -> None:
        proof = {
            "authoritative_status": "FAIL",
            "command": {"timed_out": False},
        }
        with mock.patch("aet.demo.runner.quick_proof", return_value=(proof, 7)):
            failed = run_demo("stale-proof", DemoOptions())
        self.assertEqual(failed.overall_status, "FAIL")
        self.assertIn("status 7", failed.diagnostics[0])

        proof["command"]["timed_out"] = True
        with mock.patch("aet.demo.runner.quick_proof", return_value=(proof, 124)):
            timed_out = run_demo("stale-proof", DemoOptions(timeout_seconds=1))
        self.assertEqual(timed_out.overall_status, "FAIL")
        self.assertIn("timed out", timed_out.diagnostics[0])

    def test_before_state_mismatch_is_a_regression(self) -> None:
        proof = {
            "authoritative_status": "PASS",
            "command": {"timed_out": False},
        }
        with mock.patch("aet.demo.runner.quick_proof", return_value=(proof, 0)):
            with mock.patch(
                "aet.demo.runner.quick_fresh",
                return_value={"freshness_state": "UNKNOWN"},
            ):
                result = run_demo("stale-proof", DemoOptions())
        self.assertEqual(result.overall_status, "FAIL")
        self.assertIn("before_state", result.diagnostics[0])

    def test_mutation_requires_exact_sha_and_unique_old_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "file.py"
            target.write_text("old\n", encoding="utf-8")
            mutation = MutationSpec(
                path="file.py",
                operation="replace_text",
                expected_old_sha256="0" * 64,
                old="old",
                new="new",
            )
            with self.assertRaisesRegex(DemoInvariantError, "SHA mismatch"):
                _apply_mutation(root, mutation)
