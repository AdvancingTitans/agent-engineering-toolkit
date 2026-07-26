from __future__ import annotations

import copy
import unittest
from pathlib import Path

from aet.atlas.builder import build_evidence_graph
from aet.atlas.diff import affected_records, compare_evidence_atlases


MINIMAL = (
    Path(__file__).parent
    / "fixtures"
    / "evidence-bundles"
    / "minimal"
)


class EvidenceAtlasBuilderTests(unittest.TestCase):
    def test_minimal_bundle_build_is_deterministic_and_source_backed(self) -> None:
        first = build_evidence_graph(MINIMAL)
        second = build_evidence_graph(MINIMAL)
        self.assertEqual(first, second)
        self.assertEqual("aet-evidence-graph/1.0", first["schema_version"])
        self.assertEqual("bundle-fixture-001", first["bundle_id"])
        self.assertTrue(first["nodes"])
        self.assertTrue(first["edges"])
        self.assertTrue(
            all(node["source_refs"] for node in first["nodes"])
        )
        self.assertTrue(
            all(edge["source_refs"] for edge in first["edges"])
        )
        self.assertFalse(
            any(
                diagnostic["severity"] == "error"
                for diagnostic in first["diagnostics"]
            )
        )

    def test_claim_evidence_observation_and_freshness_boundaries_are_distinct(
        self,
    ) -> None:
        graph = build_evidence_graph(MINIMAL)
        nodes = {node["id"]: node for node in graph["nodes"]}
        by_type = {}
        for node in graph["nodes"]:
            by_type.setdefault(node["type"], []).append(node)
        self.assertEqual("supported", by_type["claim"][0]["status"])
        self.assertEqual("verified", by_type["verified_evidence"][0]["status"])
        self.assertEqual("recorded", by_type["observation"][0]["status"])
        self.assertEqual("current", by_type["freshness_result"][0]["status"])
        self.assertEqual(
            ["该结论只覆盖声明的验证命令。"],
            [
                nodes[edge["to"]]["summary"]
                for edge in graph["edges"]
                if edge["type"] == "LIMITED_BY"
                and nodes[edge["from"]]["type"] == "claim"
            ],
        )
        self.assertTrue(
            any(
                edge["type"] == "SUPPORTED_BY"
                and nodes[edge["from"]]["type"] == "claim"
                and nodes[edge["to"]]["type"] == "verified_evidence"
                for edge in graph["edges"]
            )
        )
        self.assertTrue(
            any(
                edge["type"] == "OBSERVED_IN"
                and nodes[edge["to"]]["type"] == "observation"
                for edge in graph["edges"]
            )
        )

    def test_unavailable_v1_relationships_are_diagnostics_not_guessed_nodes(
        self,
    ) -> None:
        graph = build_evidence_graph(MINIMAL)
        unavailable = {
            diagnostic["message"].split(":", 1)[0]
            for diagnostic in graph["diagnostics"]
            if diagnostic["code"] == "SOURCE_DATA_UNAVAILABLE"
        }
        self.assertEqual(
            {
                "agent",
                "symbol",
                "change_group",
                "subclaim",
                "counter_claim",
                "finding",
            },
            unavailable,
        )
        self.assertTrue(
            unavailable.isdisjoint(
                {node["type"] for node in graph["nodes"]}
            )
        )

    def test_diff_reports_status_freshness_conflict_and_unknown_without_score(
        self,
    ) -> None:
        before = build_evidence_graph(MINIMAL)
        after = copy.deepcopy(before)
        claim = next(node for node in after["nodes"] if node["type"] == "claim")
        claim["status"] = "partially_supported"
        freshness = next(
            node
            for node in after["nodes"]
            if node["type"] == "freshness_result"
        )
        freshness["freshness"] = "relevant_files_changed"
        freshness["status"] = "stale"
        result = compare_evidence_atlases(before, after)
        self.assertEqual("aet-evidence-atlas-diff/1.0", result["schema_version"])
        self.assertEqual(1, len(result["semantic_changes"]["claim_status"]))
        self.assertEqual(1, len(result["semantic_changes"]["freshness"]))
        self.assertNotIn("score", result)

    def test_incremental_dependency_report_is_bounded_to_changed_records(
        self,
    ) -> None:
        graph = build_evidence_graph(MINIMAL)
        current = dict(graph["dependency_index"]["record_hashes"])
        current["claims:claim-001"] = "0" * 64
        affected = affected_records(graph, current)
        self.assertEqual(["claims:claim-001"], affected["records"])
        self.assertIn("node:claim:claim-001", affected["nodes"])


if __name__ == "__main__":
    unittest.main()
