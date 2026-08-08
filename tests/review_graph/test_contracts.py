from __future__ import annotations

import json
import unittest
from pathlib import Path

from aet.review_graph import (
    ReviewGraphError,
    validate_code_graph,
    validate_review_graph,
    validate_review_manifest,
    validate_review_slice,
)


SHA = "a" * 64


def _node(identifier: str, kind: str, *, state: str = "PASS", mandatory: bool = False) -> dict:
    return {
        "id": identifier,
        "kind": kind,
        "state": state,
        "authority": "test",
        "text": identifier,
        "source_refs": [{"kind": "fixture", "ref": "fixture.json:1"}],
        "attributes": {},
        "mandatory": mandatory,
        "priority": 100 if mandatory else 50,
    }


def _edge(identifier: str, source: str, target: str) -> dict:
    return {
        "id": identifier,
        "from": source,
        "to": target,
        "relation": "TARGETS",
        "state": "PASS",
        "authority": "test",
        "source_refs": [{"kind": "fixture", "ref": "fixture.json:1"}],
        "attributes": {},
        "priority": 50,
    }


def _snapshot() -> dict:
    return {
        "status": "PASS",
        "head_sha": SHA,
        "worktree_digest": SHA,
        "digest": SHA,
    }


class ReviewGraphContractTests(unittest.TestCase):
    def test_code_and_review_graph_accept_strict_grounded_records(self) -> None:
        code = {
            "schema_version": "aet-code-graph/1.0",
            "snapshot": _snapshot(),
            "index": {
                "language": "python",
                "base_ref": "HEAD~1",
                "coverage_status": "PASS",
                "file_count": 1,
                "symbol_count": 1,
            },
            "nodes": [_node("code:file:a", "file"), _node("code:symbol:a", "function")],
            "edges": [_edge("code-edge:a", "code:file:a", "code:symbol:a")],
            "diagnostics": [],
        }
        self.assertEqual(validate_code_graph(code)["schema_version"], "aet-code-graph/1.0")

        review = {
            "schema_version": "aet-review-graph/1.0",
            "snapshot": _snapshot(),
            "task": {"id": "task-1", "request": "review", "authority": "human_intent"},
            "code_index": {"status": "PASS", "sha256": SHA},
            "evidence_binding": {"status": "PASS", "sha256": SHA},
            "nodes": code["nodes"],
            "edges": code["edges"],
            "diagnostics": [],
        }
        self.assertEqual(validate_review_graph(review)["task"]["id"], "task-1")

    def test_dangling_edge_and_duplicate_node_fail_closed(self) -> None:
        graph = {
            "schema_version": "aet-code-graph/1.0",
            "snapshot": _snapshot(),
            "index": {
                "language": "python",
                "base_ref": "HEAD~1",
                "coverage_status": "PASS",
                "file_count": 1,
                "symbol_count": 0,
            },
            "nodes": [_node("code:file:a", "file")],
            "edges": [_edge("edge:a", "code:file:a", "code:symbol:missing")],
            "diagnostics": [],
        }
        with self.assertRaisesRegex(ReviewGraphError, "dangling_reference"):
            validate_code_graph(graph)
        graph["edges"] = []
        graph["nodes"].append(dict(graph["nodes"][0]))
        with self.assertRaisesRegex(ReviewGraphError, "duplicate_id"):
            validate_code_graph(graph)

    def test_root_slice_requires_the_complete_safety_kernel(self) -> None:
        nodes = [
            {
                "id": f"review:{kind}",
                "kind": kind,
                "state": "PASS",
                "authority": "human_intent",
                "text": kind,
                "refs": ["fixture.json:1"],
            }
            for kind in (
                "intent",
                "allowed_scope",
                "protected_scope",
                "verification_requirement",
                "stop_condition",
            )
        ]
        value = {
            "schema_version": "aet-review-slice/1.0",
            "mode": "root",
            "status": "PASS",
            "snapshot": {
                "state": "EXACT_MATCH",
                "recorded_digest": SHA,
                "current_digest": SHA,
            },
            "nodes": nodes,
            "edges": [],
            "cut": {
                "truncated": False,
                "omitted_nodes": 0,
                "omitted_edges": 0,
                "expandable": [],
            },
        }
        validate_review_slice(value)
        value["nodes"] = value["nodes"][:-1]
        with self.assertRaisesRegex(ReviewGraphError, "incomplete_review_contract"):
            validate_review_slice(value)

    def test_stale_slice_must_be_unknown_and_stop(self) -> None:
        value = {
            "schema_version": "aet-review-slice/1.0",
            "mode": "stale",
            "status": "UNKNOWN",
            "snapshot": {
                "state": "STALE",
                "recorded_digest": SHA,
                "current_digest": "b" * 64,
            },
            "nodes": [
                {
                    "id": "review:stop",
                    "kind": "stop_condition",
                    "state": "UNKNOWN",
                    "authority": "snapshot_guard",
                    "text": "Stop because the package is stale.",
                    "refs": ["manifest.json:snapshot"],
                }
            ],
            "edges": [],
            "cut": {
                "truncated": False,
                "omitted_nodes": 0,
                "omitted_edges": 0,
                "expandable": [],
            },
        }
        validate_review_slice(value)
        value["status"] = "PASS"
        with self.assertRaisesRegex(ReviewGraphError, "stale_snapshot"):
            validate_review_slice(value)

    def test_manifest_hashes_cover_declared_files(self) -> None:
        manifest = {
            "schema_version": "aet-review-manifest/1.0",
            "package_id": "review-package:test",
            "snapshot": _snapshot(),
            "inputs": {
                "bundle": {"sha256": SHA},
                "improvements": {"sha256": SHA},
                "base_ref": "HEAD~1",
            },
            "contents": {"review_graph": "review/graph.json"},
            "integrity": {
                "algorithm": "sha256",
                "file_hashes": {"review/graph.json": SHA},
            },
        }
        validate_review_manifest(manifest)
        manifest["integrity"]["file_hashes"] = {}
        with self.assertRaisesRegex(ReviewGraphError, "integrity_error"):
            validate_review_manifest(manifest)

    def test_all_review_graph_schemas_are_valid_json(self) -> None:
        root = Path(__file__).resolve().parents[2]
        schema_dir = root / "schemas" / "review-graph" / "v1"
        names = {path.name for path in schema_dir.glob("*.json")}
        self.assertEqual(
            names,
            {
                "code-graph.schema.json",
                "review-graph.schema.json",
                "review-manifest.schema.json",
                "review-slice.schema.json",
            },
        )
        for path in schema_dir.glob("*.json"):
            self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)


if __name__ == "__main__":
    unittest.main()
