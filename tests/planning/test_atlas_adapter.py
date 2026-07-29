from __future__ import annotations

import runpy
import tempfile
import unittest
from pathlib import Path

from aet.atlas import build_evidence_atlas
from aet.bundle import compile_bundle
from aet.planning.atlas_adapter import select_planning_nodes
from aet.planning.request_normalizer import RequestOverrides, normalize_request


ROOT = Path(__file__).resolve().parents[2]


class AtlasAdapterTests(unittest.TestCase):
    def test_real_self_review_atlas_is_identity_bound_and_bounded(self) -> None:
        namespace = runpy.run_path(str(ROOT / "examples/evidence-atlas/build_example.py"))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bundle = root / "bundle"
            compile_bundle(namespace["payload"](), bundle)
            atlas = build_evidence_atlas(
                bundle,
                generation_policy={
                    "llm_enabled": False,
                    "max_depth": 2,
                    "max_nodes_per_diagram": 10,
                    "max_children_per_node": 6,
                    "max_total_diagrams": 20,
                },
            )
            request = normalize_request(
                "Locate the Graph Builder and conflict behavior.",
                workspace=ROOT,
                explicit=RequestOverrides(
                    bundle_identity="bundle-aet-atlas-self-review-v1",
                ),
            )
            selection = select_planning_nodes(
                Path(atlas["output"]),
                bundle,
                request,
                max_nodes=8,
                max_depth=2,
            )
            self.assertEqual(
                selection.bundle_identity,
                "bundle-aet-atlas-self-review-v1",
            )
            self.assertEqual(len(selection.nodes), 8)
            self.assertGreater(selection.omitted_nodes, 0)
            self.assertTrue(selection.atlas_identity)


if __name__ == "__main__":
    unittest.main()
