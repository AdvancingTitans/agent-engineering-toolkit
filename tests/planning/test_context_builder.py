from __future__ import annotations

import runpy
import tempfile
import unittest
from pathlib import Path

from aet.atlas import build_evidence_atlas
from aet.bundle import compile_bundle
from aet.planning.context_builder import build_planning_context
from aet.planning.errors import PlanningError, PlanningErrorCode
from aet.planning.request_normalizer import RequestOverrides, normalize_request


ROOT = Path(__file__).resolve().parents[2]


class PlanningContextBuilderTests(unittest.TestCase):
    def test_real_improvement_bundle_preserves_counter_evidence_scope_and_source(self) -> None:
        namespace = runpy.run_path(
            str(ROOT / "examples/evidence-grounded-improvement/build_example.py")
        )
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw) / "bundle"
            compile_bundle(namespace["payload"](), bundle)
            request = normalize_request(
                "Change the empty tool result handling without weakening evidence.",
                workspace=ROOT,
                explicit=RequestOverrides(
                    bundle_identity="bundle-empty-tool-result-review-v1",
                ),
            )
            context = build_planning_context(
                request,
                workspace=ROOT,
                bundle_path=bundle,
            )
            self.assertIn(
                "examples/evidence-grounded-improvement/sample_project/tool_result.py",
                context.constraints.allowed_paths,
            )
            self.assertEqual(
                {item["id"] for item in context.counter_evidence},
                {"ev-empty-result-regression"},
            )
            self.assertTrue(
                any(
                    item.path.endswith("tool_result.py")
                    and item.read_status == "CONFIRMED"
                    for item in context.source_sites
                )
            )
            self.assertTrue(
                any("python examples/evidence-grounded-improvement" in item for item in {
                    requirement
                    for gap in context.gaps
                    for requirement in [gap.message]
                })
                is False
            )

    def test_real_atlas_context_retains_conflict_unknown_and_current_sources(self) -> None:
        namespace = runpy.run_path(str(ROOT / "examples/evidence-atlas/build_example.py"))
        with tempfile.TemporaryDirectory() as raw:
            bundle = Path(raw) / "bundle"
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
                "Update the deterministic Evidence Graph and preserve conflicts.",
                workspace=ROOT,
                explicit=RequestOverrides(
                    bundle_identity="bundle-aet-atlas-self-review-v1",
                ),
            )
            context = build_planning_context(
                request,
                workspace=ROOT,
                bundle_path=bundle,
                atlas_path=Path(atlas["output"]),
            )
            self.assertTrue(context.atlas_nodes)
            self.assertTrue(context.conflicts)
            self.assertTrue(
                any(item.path == "src/aet/atlas/builder.py" for item in context.source_sites)
            )
            self.assertTrue(
                any(gap.code == "CONFLICT_UNRESOLVED" for gap in context.gaps)
            )

    def test_source_only_context_never_loses_needs_evidence_gap(self) -> None:
        request = normalize_request(
            "Inspect src/aet/cli.py.",
            workspace=ROOT,
            explicit=RequestOverrides(
                allowed_paths=["src/aet/cli.py"],
                required_verification=["python -m unittest"],
            ),
        )
        context = build_planning_context(request, workspace=ROOT)
        self.assertTrue(any(gap.critical for gap in context.gaps))
        self.assertTrue(
            any(
                gap.code == PlanningErrorCode.EVIDENCE_REQUIRED.value
                for gap in context.gaps
            )
        )

    def test_bundle_identity_mismatch_fails_closed(self) -> None:
        request = normalize_request(
            "Inspect one verification.",
            workspace=ROOT,
            explicit=RequestOverrides(bundle_identity="wrong-bundle"),
        )
        with self.assertRaises(PlanningError) as raised:
            build_planning_context(
                request,
                workspace=ROOT,
                bundle_path=ROOT / "tests/fixtures/evidence-bundles/minimal",
            )
        self.assertEqual(raised.exception.code, PlanningErrorCode.IDENTITY_MISMATCH)


if __name__ == "__main__":
    unittest.main()
