from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from aet.evidence import workspace_snapshot
from aet.review_graph import build_code_graph


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


class PythonCodeGraphTests(unittest.TestCase):
    def _repository(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "review-graph@example.invalid")
        _git(root, "config", "user.name", "Review Graph")
        (root / "app.py").write_text(
            "def helper():\n    return 1\n\ndef changed():\n    return helper()\n",
            encoding="utf-8",
        )
        (root / "test_app.py").write_text(
            "from app import changed\n\ndef test_changed():\n    assert changed() == 1\n",
            encoding="utf-8",
        )
        _git(root, "add", ".")
        _git(root, "commit", "-qm", "baseline")
        return temporary, root

    def test_indexes_changed_symbols_calls_imports_and_tests(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        (root / "app.py").write_text(
            "def helper():\n    return 1\n\ndef changed():\n    value = helper()\n    return value\n",
            encoding="utf-8",
        )

        graph = build_code_graph(root, "HEAD")
        symbols = {
            node["attributes"].get("qualified_name"): node
            for node in graph["nodes"]
            if node["kind"] != "file"
        }
        self.assertTrue(symbols["changed"]["attributes"]["changed"])
        self.assertFalse(symbols["helper"]["attributes"]["changed"])
        relations = {
            (edge["from"], edge["relation"], edge["to"], edge["state"])
            for edge in graph["edges"]
        }
        self.assertIn(
            (symbols["changed"]["id"], "CALLS", symbols["helper"]["id"], "PASS"),
            relations,
        )
        self.assertIn(
            (symbols["test_changed"]["id"], "TESTS", symbols["changed"]["id"], "PASS"),
            relations,
        )
        self.assertIn("IMPORTS", {edge["relation"] for edge in graph["edges"]})
        self.assertEqual(graph["index"]["coverage_status"], "PASS")

    def test_dynamic_call_on_changed_line_remains_unknown(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        (root / "app.py").write_text(
            "class Service:\n    def run(self):\n        return 1\n\ndef changed(service):\n    return service.run()\n",
            encoding="utf-8",
        )
        graph = build_code_graph(root, "HEAD")
        may_call = [edge for edge in graph["edges"] if edge["relation"] == "MAY_CALL"]
        self.assertEqual(len(may_call), 1)
        self.assertEqual(may_call[0]["state"], "UNKNOWN")
        self.assertEqual(may_call[0]["authority"], "name_heuristic")
        self.assertEqual(graph["index"]["coverage_status"], "UNKNOWN")
        self.assertIn("DYNAMIC_CALL_TARGET", {item["code"] for item in graph["diagnostics"]})

    def test_parse_failure_and_file_limit_are_explicit_unknowns(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        (root / "app.py").write_text("def broken(:\n", encoding="utf-8")
        graph = build_code_graph(root, "HEAD")
        self.assertEqual(graph["index"]["coverage_status"], "UNKNOWN")
        self.assertIn("PYTHON_PARSE_ERROR", {item["code"] for item in graph["diagnostics"]})

        limited = build_code_graph(root, "HEAD", max_files=1)
        self.assertEqual(limited["index"]["coverage_status"], "UNKNOWN")
        self.assertIn("FILE_LIMIT", {item["code"] for item in limited["diagnostics"]})

    def test_snapshot_excludes_the_generated_package_subtree(self) -> None:
        temporary, root = self._repository()
        self.addCleanup(temporary.cleanup)
        before = workspace_snapshot(root, ("review-output",))
        output = root / "review-output" / "review"
        output.mkdir(parents=True)
        (output / "graph.json").write_text("{}\n", encoding="utf-8")
        after = workspace_snapshot(root, ("review-output",))
        self.assertEqual(before["digest"], after["digest"])


if __name__ == "__main__":
    unittest.main()
