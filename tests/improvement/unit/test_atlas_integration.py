from __future__ import annotations

import unittest
from pathlib import Path

from aet.atlas.builder import build_evidence_graph
from aet.atlas.model import PERSPECTIVES
from aet.atlas.perspectives import build_perspectives


ROOT = Path(__file__).resolve().parents[3]
MINIMAL = ROOT / "tests/fixtures/evidence-bundles/minimal"


class ImprovementAtlasIntegrationTests(unittest.TestCase):
    def test_improvement_perspectives_are_fixed_and_fail_visible(self) -> None:
        graph = build_evidence_graph(MINIMAL)
        perspectives = {
            item["id"]: item for item in build_perspectives(graph)
        }

        self.assertEqual(PERSPECTIVES[-2:], (
            "improvement-chain",
            "regression-lineage",
        ))
        for identifier in PERSPECTIVES[-2:]:
            perspective = perspectives[identifier]
            self.assertEqual(perspective["coverage_status"], "UNKNOWN")
            self.assertTrue(perspective["unknowns"])
            self.assertEqual(
                graph["nodes"][
                    next(
                        index
                        for index, node in enumerate(graph["nodes"])
                        if node["id"] == perspective["root_node_ids"][-1]
                    )
                ]["status"],
                "unknown",
            )


if __name__ == "__main__":
    unittest.main()
