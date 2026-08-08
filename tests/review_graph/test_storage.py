from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from aet.cli import main
from aet.mcp_server import call_tool
from aet.review_graph import ReviewGraphError
from aet.review_graph.storage import (
    build_review_package,
    export_compatibility,
    open_review_package,
    validate_review_package,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


class ReviewPackageStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "review-package@example.invalid")
        _git(self.root, "config", "user.name", "Review Package")
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_example.py").write_text(
            "def helper():\n    return 1\n\ndef test_example():\n    assert helper() == 1\n",
            encoding="utf-8",
        )
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-qm", "baseline")
        (self.root / "tests" / "test_example.py").write_text(
            "def helper():\n    return 1\n\ndef test_example():\n    value = helper()\n    assert value == 1\n",
            encoding="utf-8",
        )
        self.improvements = self.root / "improvements"
        self.improvements.mkdir()
        (self.improvements / "issues.json").write_text(
            json.dumps(
                [
                    {
                        "id": "IMP-001",
                        "title": "Keep proof bounded",
                        "category": "verification_gap",
                        "priority": "P1_HIGH",
                        "finding_refs": ["claim-001"],
                        "evidence_refs": ["ev-001"],
                        "confidence": "high",
                        "impact": {"statement": "Review the changed test.", "limitations": []},
                    }
                ]
            ),
            encoding="utf-8",
        )
        (self.improvements / "constraints.json").write_text(
            json.dumps(
                [
                    {
                        "id": "IC-001",
                        "issue_id": "IMP-001",
                        "objective": "Keep the verification current.",
                        "required_behavior": ["Preserve boundaries."],
                        "forbidden_behavior": ["Do not weaken the test."],
                        "allowed_paths": ["tests/test_example.py"],
                        "protected_paths": ["fixtures/**", ".aet/**"],
                        "verification_requirements": ["python -m unittest tests.test_example"],
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.bundle = (
            Path(__file__).resolve().parents[2]
            / "tests"
            / "fixtures"
            / "evidence-bundles"
            / "minimal"
        )
        self.package = self.root / "review-output"

    def _build(self) -> None:
        report = build_review_package(
            self.root,
            "HEAD",
            self.bundle,
            self.improvements,
            self.package,
        )
        self.assertIn(report["status"], {"PASS", "UNKNOWN"})

    def test_package_is_hash_bound_graph_first_and_non_overwriting(self) -> None:
        self._build()
        loaded = validate_review_package(self.package)
        self.assertEqual(loaded["root_slice"]["mode"], "root")
        root_bytes = (self.package / "review" / "root.slice.json").read_bytes()
        self.assertNotIn(b"\n  ", root_bytes)
        self.assertFalse((self.package / "compatibility").exists())
        self.assertFalse((self.package / "agent-context.json").exists())
        human_report = (
            self.package / "projections" / "human-improvements.md"
        ).read_text(encoding="utf-8")
        self.assertIn("可直接交给 Coding Agent 的改进提示词", human_report)
        self.assertIn("Objective: Keep the verification current.", human_report)
        self.assertTrue((self.package / "projections" / "diagrams" / "review-overview.mmd").is_file())
        self.assertEqual(open_review_package(self.package, self.root)["snapshot"]["state"], "EXACT_MATCH")
        with self.assertRaisesRegex(ReviewGraphError, "output_exists"):
            self._build()

    def test_stale_workspace_returns_unknown_stop(self) -> None:
        self._build()
        (self.root / "tests" / "test_example.py").write_text("def changed_again():\n    return 2\n", encoding="utf-8")
        opened = open_review_package(self.package, self.root)
        self.assertEqual(opened["mode"], "stale")
        self.assertEqual(opened["status"], "UNKNOWN")

    def test_tamper_is_rejected_and_legacy_export_is_explicit(self) -> None:
        self._build()
        compatibility = self.root / "legacy"
        report = export_compatibility(self.package, self.root, compatibility)
        self.assertFalse(report["default_agent_input"])
        self.assertTrue((compatibility / "agent-context.json").is_file())
        self.assertTrue((compatibility / "agent-task.md").is_file())

        target = self.package / "review" / "root.slice.json"
        target.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ReviewGraphError, "integrity_error"):
            validate_review_package(self.package)

    def test_package_symlink_is_rejected(self) -> None:
        self._build()
        (self.package / "unexpected-link").symlink_to("manifest.json")
        with self.assertRaisesRegex(ReviewGraphError, "integrity_error"):
            validate_review_package(self.package)

    def test_cli_and_two_mcp_tools_return_bounded_slices(self) -> None:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(
                [
                    "review-graph",
                    "build",
                    "--workspace",
                    str(self.root),
                    "--base",
                    "HEAD",
                    "--bundle",
                    str(self.bundle),
                    "--improvements",
                    str(self.improvements),
                    "--issue",
                    "IMP-001",
                    "--output",
                    str(self.package),
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.getvalue())["report_kind"], "aet_review_graph_package")

        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(["review-graph", "validate", str(self.package)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.getvalue())["status"], "PASS")

        opened = call_tool(
            "aet_review_open",
            {"package": str(self.package), "workspace": str(self.root)},
        )
        self.assertEqual(opened["mode"], "root")
        expandable = opened["cut"]["expandable"]
        self.assertTrue(expandable)
        expanded = call_tool(
            "aet_review_expand",
            {
                "package": str(self.package),
                "workspace": str(self.root),
                "node_id": expandable[0],
                "max_nodes": 8,
                "max_edges": 12,
                "max_bytes": 5000,
            },
        )
        self.assertEqual(expanded["mode"], "expand")


if __name__ == "__main__":
    unittest.main()
