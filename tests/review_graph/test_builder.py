from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from aet.review_graph import (
    GraphLimits,
    ReviewGraphError,
    build_review_graph,
    build_root_slice,
    expand_slice,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


class ReviewGraphBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "review-graph@example.invalid")
        _git(self.root, "config", "user.name", "Review Graph")
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
                        "title": "Keep the recorded proof bounded",
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
                        "objective": "Keep the verification evidence current.",
                        "required_behavior": ["Preserve the evidence boundary."],
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

    def _graph(self) -> dict:
        return build_review_graph(
            self.root,
            "HEAD",
            self.bundle,
            self.improvements,
            exclude_paths=("improvements",),
        )

    def test_bridges_changed_code_evidence_and_safety_controls(self) -> None:
        graph = self._graph()
        kinds = {node["kind"] for node in graph["nodes"] if node["mandatory"]}
        self.assertTrue(
            {
                "intent",
                "review_issue",
                "claim",
                "verified_evidence",
                "allowed_scope",
                "protected_scope",
                "verification_requirement",
                "stop_condition",
            }.issubset(kinds)
        )
        self.assertFalse(
            any(
                node["mandatory"]
                for node in graph["nodes"]
                if node["kind"] in {"limitation", "recommendation", "freshness_result"}
            )
        )
        relations = {edge["relation"] for edge in graph["edges"]}
        self.assertIn("JUSTIFIED_BY", relations)
        self.assertIn("BINDS_TO_CODE", relations)
        self.assertIn("TARGETS", relations)
        self.assertNotIn("overall_score", json.dumps(graph))

    def test_root_slice_is_bounded_and_safety_complete(self) -> None:
        graph = self._graph()
        review_slice = build_root_slice(graph, limits=GraphLimits(max_nodes=24, max_edges=32, max_bytes=8_000))
        kinds = {node["kind"] for node in review_slice["nodes"]}
        self.assertTrue(
            {
                "intent",
                "allowed_scope",
                "protected_scope",
                "verification_requirement",
                "stop_condition",
            }.issubset(kinds)
        )
        self.assertLessEqual(len(json.dumps(review_slice, ensure_ascii=False).encode("utf-8")), 8_000)
        self.assertTrue(review_slice["cut"]["truncated"])
        self.assertTrue(review_slice["cut"]["expandable"])
        evidence = next(
            node for node in review_slice["nodes"] if node["kind"] == "verified_evidence"
        )
        self.assertTrue(evidence["limitations"])

    def test_expand_is_one_hop_and_relation_filtered(self) -> None:
        graph = self._graph()
        changed = next(
            node for node in graph["nodes"] if node["kind"] == "test" and node["attributes"].get("changed")
        )
        expanded = expand_slice(
            graph,
            changed["id"],
            relations=("TESTS", "CONTAINS"),
        )
        self.assertEqual(expanded["mode"], "expand")
        self.assertIn(changed["id"], {node["id"] for node in expanded["nodes"]})
        self.assertTrue(all(edge[1] in {"TESTS", "CONTAINS"} for edge in expanded["edges"]))

    def test_stale_snapshot_returns_only_an_unknown_stop(self) -> None:
        graph = self._graph()
        stale = build_root_slice(graph, current_digest="b" * 64)
        self.assertEqual(stale["mode"], "stale")
        self.assertEqual(stale["status"], "UNKNOWN")
        self.assertEqual([node["kind"] for node in stale["nodes"]], ["stop_condition"])

    def test_safety_kernel_cannot_be_truncated(self) -> None:
        graph = self._graph()
        with self.assertRaisesRegex(ReviewGraphError, "context_limit"):
            build_root_slice(graph, limits=GraphLimits(max_nodes=2, max_edges=2, max_bytes=500))

    def test_changed_file_outside_allowed_scope_is_fail(self) -> None:
        (self.root / "extra.py").write_text("VALUE = 1\n", encoding="utf-8")
        graph = self._graph()
        failures = [item for item in graph["diagnostics"] if item["status"] == "FAIL"]
        self.assertIn("CHANGED_OUTSIDE_ALLOWED_SCOPE", {item["code"] for item in failures})
        self.assertEqual(build_root_slice(graph)["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
