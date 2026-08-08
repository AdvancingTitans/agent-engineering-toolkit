from __future__ import annotations

import copy
import hashlib
import io
import json
import runpy
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import aet.atlas.storage as atlas_storage
from aet.atlas.builder import build_evidence_graph
from aet.atlas.hierarchy import build_hierarchy
from aet.atlas.model import PERSPECTIVES
from aet.atlas.perspectives import build_perspectives
from aet.atlas.queries import AtlasQueryError, get_node_subgraph
from aet.atlas.render import render_document_fields, render_projection
from aet.atlas.storage import (
    build_evidence_atlas,
    load_evidence_atlas,
)
from aet.atlas.validator import (
    AtlasValidationError,
    validate_evidence_atlas,
    validate_evidence_graph,
    validate_mermaid,
)
from aet.atlas.viewer import single_html, viewer_files
from aet.bundle import validate_bundle
from aet.bundle.compiler import compile_bundle
from aet.cli import main


MINIMAL = (
    Path(__file__).parent
    / "fixtures"
    / "evidence-bundles"
    / "minimal"
)


class EvidenceAtlasProtocolTests(unittest.TestCase):
    def test_complete_sidecar_is_deterministic_valid_and_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first.atlas"
            second = Path(temporary) / "second.atlas"
            built = build_evidence_atlas(MINIMAL, output=first)
            build_evidence_atlas(MINIMAL, output=second)
            report = validate_evidence_atlas(
                first / "atlas-manifest.json",
                MINIMAL,
            )
            self.assertEqual("aet-evidence-atlas-manifest/1.0", report["schema_version"])
            self.assertEqual(list(PERSPECTIVES), [
                item["id"] for item in built["perspectives"]
            ])
            self.assertEqual(
                (first / "atlas-manifest.json").read_bytes(),
                (second / "atlas-manifest.json").read_bytes(),
            )
            self.assertTrue((first / "atlas" / "index.html").is_file())
            self.assertTrue((first / "atlas" / "assets" / "mermaid.min.js").is_file())
            self.assertTrue((first / "atlas" / "assets" / "atlas-data.js").is_file())
            index = (first / "atlas" / "index.html").read_text(encoding="utf-8")
            self.assertIn("connect-src 'none'", index)
            self.assertNotIn("<script src=\"http", index)
            self.assertNotIn("<script id=\"atlas-data\"", index)
            self.assertIn('script src="assets/atlas-data.js"', index)
            viewer_js = (
                first / "atlas" / "assets" / "atlas.js"
            ).read_text(encoding="utf-8")
            self.assertIn("applyVisibilityToDiagram", viewer_js)
            self.assertIn("referenceDiagram", viewer_js)
            self.assertIn('setAttribute("aria-level"', viewer_js)
            self.assertIn("Open subgraph ↗", viewer_js)
            self.assertIn("SEE SUBGRAPH", viewer_js)
            self.assertIn("MAX DEPTH", viewer_js)
            self.assertIn('"CYCLE"', viewer_js)
            self.assertTrue(
                any(
                    projection["references"]
                    for projection in built["projections"].values()
                )
            )
            self.assertFalse(built["graph"]["generation_policy"]["llm_enabled"])
            with patch(
                "aet.atlas.storage.render_projection",
                side_effect=AssertionError("unchanged Perspectives were rebuilt"),
            ):
                incremental = build_evidence_atlas(MINIMAL, output=first)
            self.assertEqual([], incremental["incremental"]["records"])
            self.assertEqual([], incremental["incremental"]["perspectives"])

    def test_every_node_is_evaluated_and_only_complex_nodes_expand(self) -> None:
        graph = build_evidence_graph(MINIMAL)
        perspectives = build_perspectives(graph)
        hierarchy = build_hierarchy(graph, perspectives[0])
        nodes_by_id = {node["id"]: node for node in graph["nodes"]}
        self.assertTrue(
            all(
                node["complexity"]["classification"]
                in {"leaf", "expandable", "mandatory_decomposition"}
                for node in graph["nodes"]
            )
        )
        expanded = {
            diagram["root_node_id"] for diagram in hierarchy["diagrams"]
        }
        typed = {
            diagram["root_node_id"]: diagram["extensions"]["decomposer"]
            for diagram in hierarchy["diagrams"]
            if diagram["root_node_id"] in nodes_by_id
            and nodes_by_id[diagram["root_node_id"]]["type"]
            in {"claim", "proof", "source"}
        }
        self.assertTrue(any(value.startswith("typed:") for value in typed.values()))
        leaf_ids = {
            node["id"]
            for node in graph["nodes"]
            if node["complexity"]["classification"] == "leaf"
        }
        self.assertTrue(expanded.isdisjoint(leaf_ids))
        self.assertLessEqual(
            max(diagram["depth"] for diagram in hierarchy["diagrams"]),
            graph["generation_policy"]["max_depth"],
        )
        proof = next(node for node in graph["nodes"] if node["type"] == "proof")
        fields = render_document_fields(proof, graph)
        self.assertIn("## Does not prove", fields["evidence.md"])
        self.assertIn(
            "Does not prove: 只覆盖声明的测试路径。",
            fields["concerns.md"],
        )

    def test_global_diagram_budget_reserves_all_eleven_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atlas = Path(temporary) / "bounded.atlas"
            result = build_evidence_atlas(
                MINIMAL,
                output=atlas,
                generation_policy={"max_total_diagrams": 11},
            )
            self.assertEqual(
                11,
                sum(
                    len(item["diagrams"])
                    for item in result["hierarchies"].values()
                ),
            )
            validate_evidence_atlas(atlas / "atlas-manifest.json", MINIMAL)

    def test_recursive_references_cover_cycle_deduplication_and_max_depth(
        self,
    ) -> None:
        graph = build_evidence_graph(MINIMAL)
        graph["generation_policy"]["max_depth"] = 1
        perspectives = build_perspectives(graph)
        reasons = {
            reference["reason"]
            for perspective in perspectives
            for reference in build_hierarchy(graph, perspective)["references"]
        }
        self.assertTrue(
            {"cycle", "deduplicated", "max_depth"}.issubset(reasons)
        )

    def test_multiple_claims_share_one_canonical_proof_node(self) -> None:
        bundle = copy.deepcopy(validate_bundle(MINIMAL))
        second = copy.deepcopy(bundle["claims"][0])
        second["id"] = "claim-002"
        second["statement"] = "同一验证结果也支持第二条有边界命题。"
        bundle["claims"].append(second)
        bundle["evidence"][0]["supports"].append("claim-002")
        graph = build_evidence_graph(bundle)
        proofs = [
            node for node in graph["nodes"] if node["type"] == "proof"
        ]
        self.assertEqual(["node:proof:ev-001"], [node["id"] for node in proofs])
        self.assertEqual(
            {
                "node:claim:claim-001",
                "node:claim:claim-002",
            },
            {
                edge["to"]
                for edge in graph["edges"]
                if edge["type"] == "VALIDATES"
                and edge["from"] == "node:proof:ev-001"
            },
        )

    def test_bundle_v1_missing_change_groups_remains_explicit_unknown(
        self,
    ) -> None:
        graph = build_evidence_graph(MINIMAL)
        perspectives = {
            item["id"]: item for item in build_perspectives(graph)
        }
        scope = perspectives["change-scope"]
        self.assertEqual("UNKNOWN", scope["coverage_status"])
        self.assertTrue(
            any("Change Group" in item for item in scope["unknowns"])
        )
        self.assertFalse(
            any(node["type"] == "change_group" for node in graph["nodes"])
        )
        self.assertTrue(
            any(
                diagnostic["code"] == "SOURCE_DATA_UNAVAILABLE"
                and diagnostic["message"].startswith("change_group:")
                for diagnostic in graph["diagnostics"]
            )
        )

    def test_build_can_select_a_valid_perspective_subset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atlas = Path(temporary) / "selected.atlas"
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(
                    [
                        "atlas",
                        "build",
                        str(MINIMAL),
                        "--output",
                        str(atlas),
                        "--perspectives",
                        "claim-chain,verification-coverage",
                    ]
                )
            self.assertEqual(0, result)
            report = json.loads(output.getvalue())
            self.assertEqual(
                ["claim-chain", "verification-coverage"],
                report["perspectives"],
            )
            validation = validate_evidence_atlas(
                atlas / "atlas-manifest.json",
                MINIMAL,
            )
            self.assertEqual(
                2,
                len(validation["perspectives"]),
            )
            manifest = json.loads(
                (atlas / "atlas-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(2, len(manifest["contents"]["perspectives"]))

    def test_stale_proof_cannot_validate_current_claim(self) -> None:
        bundle = copy.deepcopy(validate_bundle(MINIMAL))
        evidence = bundle["evidence"][0]
        evidence["freshness"] = {
            "status": "relevant_files_changed",
            "checked_at": "2026-01-03T03:04:05Z",
            "explanation": "Relevant file changed.",
            "effect": "Historical result no longer applies.",
        }
        graph = build_evidence_graph(bundle)
        freshness = next(
            item
            for item in build_perspectives(graph)
            if item["id"] == "freshness"
        )
        rendered = render_projection(
            graph,
            node_ids=freshness["node_ids"],
            edge_ids=freshness["edge_ids"],
            diagram_type=freshness["diagram_type"],
            direction=freshness["direction"],
            max_nodes=25,
            root_ids=freshness["root_node_ids"],
        )
        self.assertIn(
            "2026-01-03T03-04-05Z",
            rendered["diagram"],
        )
        nodes = {node["id"]: node for node in graph["nodes"]}
        proof_ids = {
            node["id"]
            for node in graph["nodes"]
            if node["type"] == "proof"
        }
        self.assertTrue(
            all(nodes[identifier]["status"] == "stale" for identifier in proof_ids)
        )
        self.assertFalse(
            any(
                edge["type"] == "VALIDATES"
                and edge["from"] in proof_ids
                for edge in graph["edges"]
            )
        )
        support = next(
            edge
            for edge in graph["edges"]
            if edge["from"] == "node:claim:claim-001"
            and edge["to"] == "node:verified_evidence:ev-001"
        )
        self.assertEqual("PARTIALLY_SUPPORTED_BY", support["type"])
        self.assertIn("stale", support["render"]["label"])

    def test_authoritative_edge_target_must_match_its_cited_field(self) -> None:
        bundle = copy.deepcopy(validate_bundle(MINIMAL))
        second = copy.deepcopy(bundle["evidence"][0])
        second["id"] = "ev-002"
        second["supports"] = []
        bundle["evidence"].append(second)
        graph = build_evidence_graph(bundle)
        forged = copy.deepcopy(graph)
        support = next(
            edge
            for edge in forged["edges"]
            if edge["type"] == "SUPPORTED_BY"
        )
        support["to"] = "node:verified_evidence:ev-002"
        with self.assertRaisesRegex(
            AtlasValidationError,
            "target is not named|omits required",
        ):
            validate_evidence_graph(forged, bundle)

    def test_mermaid_projection_escapes_untrusted_labels_and_rejects_active_content(
        self,
    ) -> None:
        graph = build_evidence_graph(MINIMAL)
        perspective = build_perspectives(graph)[0]
        graph["nodes"][0]["title"] = '<script>alert("x")</script> https://evil.invalid'
        rendered = render_projection(
            graph,
            node_ids=perspective["node_ids"],
            edge_ids=perspective["edge_ids"],
            diagram_type=perspective["diagram_type"],
            direction=perspective["direction"],
            max_nodes=25,
            root_ids=perspective["root_node_ids"],
        )
        mermaid = rendered["diagram"]
        validate_mermaid(mermaid)
        self.assertNotIn("<script", mermaid)
        self.assertNotIn("https:", mermaid)
        for unsafe in (
            "flowchart BOGUS\n",
            "flowchart LR\nclick A \"https://evil.invalid\"",
            "flowchart LR\nA[<img src=x>]",
            "%%{init: {}}%%\nflowchart LR",
            'flowchart LR\n A["unterminated',
            "sequenceDiagram\n participant",
            "timeline\n Step :",
        ):
            with self.assertRaises(AtlasValidationError):
                validate_mermaid(unsafe)

    def test_unsupported_claim_has_a_distinct_mermaid_class(self) -> None:
        bundle = copy.deepcopy(validate_bundle(MINIMAL))
        bundle["claims"][0]["status"] = "unsupported"
        bundle["claims"][0]["evidence_refs"] = []
        graph = build_evidence_graph(bundle)
        perspective = build_perspectives(graph)[0]
        rendered = render_projection(
            graph,
            node_ids=perspective["node_ids"],
            edge_ids=perspective["edge_ids"],
            diagram_type=perspective["diagram_type"],
            direction=perspective["direction"],
            max_nodes=25,
            root_ids=perspective["root_node_ids"],
        )
        self.assertIn("classDef unsupported", rendered["diagram"])
        claim_id = next(
            node["id"]
            for node in rendered["diagram_ir"]["nodes"]
            if node["canonical_id"] == "node:claim:claim-001"
        )
        self.assertIn(
            f"class {claim_id} unsupported",
            rendered["diagram"],
        )

    def test_oversized_diagram_is_bounded_and_reports_omissions(self) -> None:
        graph = build_evidence_graph(MINIMAL)
        perspective = build_perspectives(graph)[0]
        rendered = render_projection(
            graph,
            node_ids=perspective["node_ids"],
            edge_ids=perspective["edge_ids"],
            diagram_type=perspective["diagram_type"],
            direction=perspective["direction"],
            max_nodes=3,
            root_ids=perspective["root_node_ids"],
        )
        self.assertLessEqual(len(rendered["diagram_ir"]["nodes"]), 3)
        self.assertTrue(
            any(
                diagnostic["code"] == "DIAGRAM_TRUNCATED"
                for diagnostic in rendered["diagnostics"]
            )
        )

    def test_unavailable_source_and_record_refs_are_diagnostic_only(self) -> None:
        bundle = copy.deepcopy(validate_bundle(MINIMAL))
        bundle["observations"][0]["source_refs"].append("src-unavailable")
        bundle["claims"][0]["observation_refs"].append("obs-unavailable")
        graph = build_evidence_graph(bundle)
        messages = {
            diagnostic["message"]
            for diagnostic in graph["diagnostics"]
            if diagnostic["code"] == "MISSING_REFERENCE"
        }
        self.assertTrue(
            any("Source src-unavailable" in message for message in messages)
        )
        self.assertTrue(
            any("Observation obs-unavailable" in message for message in messages)
        )
        self.assertNotIn(
            "node:source:src-unavailable",
            {node["id"] for node in graph["nodes"]},
        )

    def test_viewer_payload_cannot_break_out_of_data_transport(self) -> None:
        graph = build_evidence_graph(MINIMAL)
        graph["nodes"][0]["summary"] = "</script><script>alert('x')</script>"
        files = viewer_files(graph, {})
        index = files["index.html"].decode("utf-8")
        data = files["assets/atlas-data.js"].decode("utf-8")
        self.assertNotIn("alert('x')", index)
        self.assertNotIn("</script><script>", data)
        self.assertIn("<\\/script>", data)
        self.assertNotIn(
            "</script><script>alert('x')</script>",
            single_html(graph, {}).decode("utf-8"),
        )

    def test_query_budget_and_graph_authority_fail_closed(self) -> None:
        bundle = validate_bundle(MINIMAL)
        graph = build_evidence_graph(bundle)
        build_perspectives(graph)
        validate_evidence_graph(graph, bundle)
        with self.assertRaises(AtlasQueryError):
            get_node_subgraph(
                graph,
                "node:claim:claim-001",
                perspective="claim-chain",
                max_nodes=201,
            )
        forged = copy.deepcopy(graph)
        forged["edges"][0]["source_refs"] = []
        with self.assertRaises(AtlasValidationError):
            validate_evidence_graph(forged, bundle)
        invalid_schema = copy.deepcopy(graph)
        invalid_schema["extensions"] = "not-an-object"
        with self.assertRaisesRegex(AtlasValidationError, "schema_error"):
            validate_evidence_graph(invalid_schema, bundle)

    def test_recursive_provenance_is_schema_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atlas = Path(temporary) / "provenance.atlas"
            build_evidence_atlas(MINIMAL, output=atlas)
            provenance = next(
                (atlas / "graph" / "perspectives").glob(
                    "*/children/**/provenance.json"
                )
            )
            value = json.loads(provenance.read_text(encoding="utf-8"))
            value["generator"]["mode"] = "invented"
            raw = (
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            provenance.write_bytes(raw)
            manifest_path = atlas / "atlas-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            relative = provenance.relative_to(atlas).as_posix()
            manifest["integrity"]["file_hashes"][relative] = hashlib.sha256(
                raw
            ).hexdigest()
            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AtlasValidationError, "schema_error"):
                validate_evidence_atlas(
                    manifest_path,
                    MINIMAL,
                )

    def test_cli_build_validate_query_export_diff_and_non_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atlas = root / "minimal.atlas"
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    0,
                    main(
                        [
                            "atlas",
                            "build",
                            str(MINIMAL),
                            "--output",
                            str(atlas),
                            "--no-llm",
                        ]
                    ),
                )
            report = json.loads(output.getvalue())
            self.assertEqual("PASS", report["status"])

            for argv in (
                [
                    "atlas",
                    "validate",
                    str(atlas),
                    "--bundle",
                    str(MINIMAL),
                ],
                [
                    "atlas",
                    "query",
                    str(atlas),
                    "--bundle",
                    str(MINIMAL),
                    "--perspective",
                    "claim-chain",
                    "--root",
                    "node:claim:claim-001",
                ],
                [
                    "atlas",
                    "diff",
                    str(atlas),
                    str(atlas),
                    "--before-bundle",
                    str(MINIMAL),
                    "--after-bundle",
                    str(MINIMAL),
                ],
            ):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(0, main(argv))

            exported = root / "atlas.html"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    main(
                        [
                            "atlas",
                            "export",
                            str(atlas),
                            "--bundle",
                            str(MINIMAL),
                            "--format",
                            "single-html",
                            "--output",
                            str(exported),
                        ]
                    ),
                )
            self.assertTrue(exported.read_bytes().startswith(b"<!doctype html>"))
            loaded = load_evidence_atlas(atlas)
            self.assertEqual("bundle-fixture-001", loaded["graph"]["bundle_id"])
            recursive = next(
                item
                for item in loaded["hierarchy"]["diagrams"]
                if item["parent_diagram_id"] is not None
            )
            self.assertIn(
                recursive["id"],
                exported.read_text(encoding="utf-8"),
            )
            with self.assertRaises(SystemExit):
                main(
                    [
                        "atlas",
                        "build",
                        str(MINIMAL),
                        "--output",
                        str(atlas),
                        "--no-replace",
                    ]
                )

    def test_readme_self_review_example_builds_the_tracked_mermaid(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        example = repository / "examples" / "evidence-atlas"
        namespace = runpy.run_path(str(example / "build_example.py"))
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            atlas = Path(temporary) / "bundle.atlas"
            compile_bundle(namespace["payload"](), bundle)
            build_evidence_atlas(
                bundle,
                output=atlas,
                generation_policy={"max_depth": 4, "max_nodes_per_diagram": 14},
            )
            validate_evidence_atlas(atlas / "atlas-manifest.json", bundle)
            generated = (
                atlas
                / "graph"
                / "perspectives"
                / "claim-chain"
                / "diagram.mmd"
            ).read_text(encoding="utf-8")
            tracked = (
                example / "aet-self-review-claim-chain.mmd"
            ).read_text(encoding="utf-8")
            self.assertEqual(generated, tracked)

    def test_full_overview_embeds_the_exact_generated_example(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        expected = (
            repository
            / "examples"
            / "evidence-atlas"
            / "aet-self-review-claim-chain.mmd"
        ).read_text(encoding="utf-8").rstrip()
        for relative in ("docs/reference/full-product-overview.md",):
            content = (repository / relative).read_text(encoding="utf-8")
            section = content.split(
                "<!-- atlas-self-review-mermaid:start -->", 1
            )[1].split("<!-- atlas-self-review-mermaid:end -->", 1)[0]
            embedded = section.split("```mermaid\n", 1)[1].rsplit(
                "\n```", 1
            )[0]
            self.assertEqual(expected, embedded, relative)

    def test_incremental_rebuild_reuses_unaffected_recursive_subgraphs(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[1]
        namespace = runpy.run_path(
            str(
                repository
                / "examples"
                / "evidence-atlas"
                / "build_example.py"
            )
        )
        before = namespace["payload"]()
        after = copy.deepcopy(before)
        after["claims"][0]["smallest_next_action"] = (
            "Review this exact Claim again."
        )
        policy = {"max_depth": 4, "max_nodes_per_diagram": 14}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_bundle = root / "before"
            second_bundle = root / "after"
            atlas = root / "review.atlas"
            compile_bundle(before, first_bundle)
            compile_bundle(after, second_bundle)
            build_evidence_atlas(
                first_bundle,
                output=atlas,
                generation_policy=policy,
            )
            with patch(
                "aet.atlas.storage.render_projection",
                wraps=atlas_storage.render_projection,
            ) as render:
                result = build_evidence_atlas(
                    second_bundle,
                    output=atlas,
                    generation_policy=policy,
                )
            possible_full_render_count = len(result["perspectives"]) + sum(
                len(hierarchy["diagrams"])
                for hierarchy in result["hierarchies"].values()
            )
            self.assertTrue(result["incremental"]["parent_diagrams"])
            self.assertLess(render.call_count, possible_full_render_count)
            validate_evidence_atlas(
                atlas / "atlas-manifest.json",
                second_bundle,
            )

    def test_mermaid_render_failure_keeps_a_valid_list_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atlas = Path(temporary) / "fallback.atlas"
            with patch(
                "aet.atlas.render.render_mermaid",
                side_effect=ValueError("synthetic parser failure"),
            ):
                built = build_evidence_atlas(MINIMAL, output=atlas)
            validate_evidence_atlas(atlas / "atlas-manifest.json", MINIMAL)
            self.assertTrue(
                any(
                    item["code"] == "MERMAID_RENDER_FAILED"
                    for item in built["graph"]["diagnostics"]
                )
            )
            errors = list(
                (atlas / "graph" / "perspectives").glob(
                    "*/**/diagram-error.json"
                )
            )
            self.assertTrue(errors)
            self.assertTrue(
                all(
                    (path.parent / "diagram.mmd").is_file()
                    for path in errors
                )
            )


if __name__ == "__main__":
    unittest.main()
