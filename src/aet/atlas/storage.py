"""Atomic sidecar storage for deterministic Evidence Atlas projections."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from aet.bundle import BundleError, validate_bundle
from aet.risk.errors import RiskInputError
from aet.risk.schemas import SchemaKind as RiskSchemaKind, validate_version as validate_risk_version

from .builder import build_evidence_graph
from .diff import affected_records
from .hierarchy import build_hierarchy
from .model import ATLAS_MANIFEST_SCHEMA, PERSPECTIVES, canonical_bytes, record_hashes
from .perspectives import build_perspectives
from .render import render_document_fields, render_projection, safe_mermaid_id
from .viewer import MERMAID_VERSION, viewer_files


class AtlasStorageError(ValueError):
    """An Atlas sidecar could not be safely loaded or published."""


def default_atlas_path(bundle_path: Path) -> Path:
    """Return the v1-compatible sibling sidecar location."""
    bundle = Path(bundle_path)
    return bundle.with_name(bundle.name + ".atlas")


def build_evidence_atlas(
    bundle_path: Path,
    *,
    output: Path | None = None,
    generation_policy: Mapping[str, Any] | None = None,
    perspective_ids: Iterable[str] | None = None,
    risk_diagnosis: Path | None = None,
    replace: bool = True,
) -> dict[str, Any]:
    """Build and atomically publish a complete v1-compatible Atlas sidecar."""
    bundle_path = Path(bundle_path).resolve(strict=True)
    bundle = validate_bundle(bundle_path)
    diagnosis = _load_risk_diagnosis(risk_diagnosis) if risk_diagnosis is not None else None
    destination = (
        default_atlas_path(bundle_path)
        if output is None
        else Path(output).expanduser().resolve(strict=False)
    )
    _outside_bundle(bundle_path, destination)
    previous_atlas = None
    previous_graph = None
    if destination.exists() or destination.is_symlink():
        if not replace:
            raise AtlasStorageError(f"Atlas output already exists: {destination}")
        previous_atlas = _load_previous_atlas(destination)
        if previous_atlas is not None:
            previous_graph = previous_atlas["graph"]
    if diagnosis is not None:
        previous_atlas = None
        previous_graph = None

    graph = build_evidence_graph(
        bundle,
        generation_policy=generation_policy,
        risk_diagnosis=diagnosis,
    )
    all_perspectives = build_perspectives(graph)
    perspectives = _select_perspectives(all_perspectives, perspective_ids)
    hierarchies = _build_all_hierarchies(graph, perspectives)
    graph.pop("hierarchies", None)
    incremental = (
        affected_records(
            previous_graph,
            graph["dependency_index"]["record_hashes"],
        )
        if previous_graph is not None
        else {
            "records": sorted(graph["dependency_index"]["record_hashes"]),
            "nodes": [node["id"] for node in graph["nodes"]],
            "edges": [edge["id"] for edge in graph["edges"]],
            "perspectives": [item["id"] for item in perspectives],
            "parent_diagrams": sorted(
                {
                    diagram["id"]
                    for hierarchy in hierarchies.values()
                    for diagram in hierarchy["diagrams"]
                }
            ),
        }
    )
    if previous_graph is not None:
        _merge_current_impact(incremental, graph)
    selected_ids = {item["id"] for item in perspectives}
    incremental["perspectives"] = sorted(
        selected_ids.intersection(incremental["perspectives"])
    )
    if previous_atlas is not None:
        previous_root = Path(previous_atlas["root"])
        incremental["perspectives"] = sorted(
            set(incremental["perspectives"])
            | {
                perspective_id
                for perspective_id in selected_ids
                if not _previous_projection_exists(
                    previous_root,
                    perspective_id,
                )
            }
        )

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent)
    )
    try:
        projections = _write_graph(
            temporary,
            graph,
            perspectives,
            hierarchies,
            previous_root=(
                Path(previous_atlas["root"])
                if previous_atlas is not None
                else None
            ),
            rebuild_perspectives=set(incremental["perspectives"]),
            rebuild_diagrams=set(incremental["parent_diagrams"]),
        )
        _write_viewer(temporary, graph, projections)
        manifest = _seal_sidecar(
            temporary,
            bundle,
            graph,
            perspectives,
        )
        _write_json(temporary / "atlas-manifest.json", manifest)
        if destination.exists():
            _reuse_unchanged_files(destination, temporary)
        _publish_directory(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "manifest": manifest,
        "graph": graph,
        "perspectives": perspectives,
        "hierarchies": hierarchies,
        "projections": projections,
        "incremental": incremental,
        "output": str(destination),
    }


def _load_risk_diagnosis(path: Path) -> dict[str, Any]:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        raise AtlasStorageError("risk diagnosis must be a regular non-symbolic-link file")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AtlasStorageError(f"cannot read risk diagnosis: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != "aet-risk-diagnosis/1.0":
        raise AtlasStorageError("risk diagnosis must use aet-risk-diagnosis/1.0")
    if any(key in value for key in ("overall_score", "trust_score", "model_motive")):
        raise AtlasStorageError("risk diagnosis contains a forbidden authority field")
    try:
        validate_risk_version(RiskSchemaKind.RISK_DIAGNOSIS, value)
    except RiskInputError as error:
        raise AtlasStorageError(f"invalid risk diagnosis: {error}") from error
    return value


def load_evidence_atlas(path: Path) -> dict[str, Any]:
    """Load a sidecar with path and file-hash checks but no Bundle inference."""
    root = _safe_root(Path(path))
    manifest = _read_json_object(_safe_file(root, "atlas-manifest.json"))
    integrity = manifest.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        raise AtlasStorageError("Atlas integrity algorithm must be sha256")
    hashes = integrity.get("file_hashes")
    if not isinstance(hashes, dict):
        raise AtlasStorageError("Atlas integrity.file_hashes must be an object")
    actual = _regular_files(root)
    actual.discard("atlas-manifest.json")
    if actual != set(hashes):
        raise AtlasStorageError(
            "Atlas manifest must hash every non-manifest regular file"
        )
    files: dict[str, bytes] = {}
    for relative, expected in sorted(hashes.items()):
        if not isinstance(relative, str) or not _is_sha256(expected):
            raise AtlasStorageError("Atlas file hashes must use safe paths and SHA-256")
        raw = _safe_file(root, relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise AtlasStorageError(f"Atlas file hash mismatch: {relative}")
        files[relative] = raw
    graph = _decode_json_object(files.get("graph/graph.json"), "graph/graph.json")
    nodes = _decode_jsonl(files.get("graph/nodes.jsonl"), "graph/nodes.jsonl")
    edges = _decode_jsonl(files.get("graph/edges.jsonl"), "graph/edges.jsonl")
    hierarchy = _decode_json_object(
        files.get("graph/hierarchy.json"),
        "graph/hierarchy.json",
    )
    diagnostics = _decode_jsonl(
        files.get("graph/diagnostics.jsonl"),
        "graph/diagnostics.jsonl",
    )
    dependencies = _decode_json_object(
        files.get("graph/dependencies.json"),
        "graph/dependencies.json",
    )
    return {
        "root": str(root),
        "manifest": manifest,
        "graph": graph,
        "nodes": nodes,
        "edges": edges,
        "hierarchy": hierarchy,
        "diagnostics": diagnostics,
        "dependencies": dependencies,
        "_files": files,
    }


def atlas_is_stale(atlas: Mapping[str, Any], bundle_path: Path) -> bool:
    """Return whether the sidecar no longer binds the current Bundle identity."""
    bundle = validate_bundle(Path(bundle_path))
    generated = atlas.get("manifest", {}).get("generated_from", {})
    return (
        generated.get("bundle_content_hash")
        != bundle["manifest"]["bundle"]["content_hash"]
        or generated.get("manifest_sha256")
        != hashlib.sha256(
            (Path(bundle["root"]) / "manifest.json").read_bytes()
        ).hexdigest()
        or generated.get("index_sha256")
        != hashlib.sha256(bundle["_files"]["index.json"]).hexdigest()
    )


def _write_graph(
    root: Path,
    graph: dict[str, Any],
    perspectives: list[dict[str, Any]],
    hierarchies: dict[str, dict[str, Any]],
    *,
    previous_root: Path | None = None,
    rebuild_perspectives: set[str] | None = None,
    rebuild_diagrams: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    graph_root = root / "graph"
    graph_root.mkdir()
    projections: dict[str, dict[str, Any]] = {}
    rendered: dict[str, dict[str, Any]] = {}
    for perspective in perspectives:
        reusable = (
            previous_root is not None
            and rebuild_perspectives is not None
            and perspective["id"] not in rebuild_perspectives
            and _previous_projection_exists(
                previous_root,
                perspective["id"],
            )
        )
        projection = (
            _load_previous_projection(previous_root, perspective["id"])
            if reusable
            else render_projection(
                graph,
                node_ids=perspective["node_ids"],
                edge_ids=perspective["edge_ids"],
                diagram_type=perspective["diagram_type"],
                direction=perspective["direction"],
                max_nodes=graph["generation_policy"]["max_nodes_per_diagram"],
                root_ids=perspective["root_node_ids"],
            )
        )
        rendered[perspective["id"]] = projection
        projections[perspective["id"]] = {
            "perspective": perspective,
            "ir": projection["diagram_ir"],
            "mermaid": projection.get("diagram") or "",
            "diagnostics": projection["diagnostics"],
            "diagrams": {},
            "node_to_diagram": {},
            "references": [
                dict(reference)
                for reference in hierarchies[perspective["id"]]["references"]
            ],
        }
    graph["diagnostics"] = _normalize_diagnostics(
        [
            *graph.get("diagnostics", []),
            *[
                diagnostic
                for hierarchy in hierarchies.values()
                for diagnostic in hierarchy.get("diagnostics", [])
            ],
            *[
                diagnostic
                for projection in rendered.values()
                for diagnostic in projection.get("diagnostics", [])
            ],
        ],
        graph,
    )
    _write_json(graph_root / "graph.json", graph)
    _write_jsonl(graph_root / "nodes.jsonl", graph["nodes"])
    _write_jsonl(graph_root / "edges.jsonl", graph["edges"])
    _write_json(
        graph_root / "hierarchy.json",
        _flatten_hierarchies(hierarchies),
    )
    _write_jsonl(graph_root / "diagnostics.jsonl", graph["diagnostics"])
    _write_json(
        graph_root / "dependencies.json",
        graph["dependency_index"],
    )
    candidates_root = graph_root / "candidates"
    candidates_root.mkdir()
    _write_jsonl(candidates_root / "edges.jsonl", [])
    perspective_root = graph_root / "perspectives"
    perspective_root.mkdir()
    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    for perspective in perspectives:
        destination = perspective_root / perspective["id"]
        reusable = (
            previous_root is not None
            and rebuild_perspectives is not None
            and perspective["id"] not in rebuild_perspectives
            and _previous_projection_exists(
                previous_root,
                perspective["id"],
            )
        )
        if reusable:
            source = (
                previous_root
                / "graph"
                / "perspectives"
                / perspective["id"]
            )
            shutil.copytree(source, destination)
            _load_previous_recursive_projections(
                source,
                projections[perspective["id"]],
                nodes_by_id,
            )
            continue
        destination.mkdir()
        projection = rendered[perspective["id"]]
        _write_text(
            destination / "description.md",
            f"# {perspective['title']}\n\n{perspective['question']}\n",
        )
        _write_text(
            destination / "question.md",
            f"# Question\n\n{perspective['question']}\n",
        )
        _write_text(
            destination / "context.md",
            (
                "# Context\n\n"
                f"{perspective['description']}\n\n"
                f"Nodes: {perspective['node_count']}; "
                f"edges: {perspective['edge_count']}.\n"
            ),
        )
        _write_text(
            destination / "evidence.md",
            (
                "# Evidence\n\n"
                "The authoritative evidence is referenced by the canonical "
                "node and edge IDs in `perspective.json`.\n"
            ),
        )
        _write_text(
            destination / "counter-evidence.md",
            (
                "# Counter-evidence\n\n"
                "Counter-evidence and conflicts are retained through "
                "`CONTRADICTED_BY` edges and conflict nodes when present.\n"
            ),
        )
        _write_text(
            destination / "freshness.md",
            (
                "# Freshness\n\n"
                "Freshness remains a per-node and per-edge property; this "
                "projection does not upgrade historical applicability.\n"
            ),
        )
        _write_text(
            destination / "constraints.md",
            _list_markdown("Constraints", perspective["constraints"]),
        )
        _write_text(
            destination / "concerns.md",
            _list_markdown("Concerns", perspective["concerns"]),
        )
        _write_text(
            destination / "unknowns.md",
            _unknowns_markdown(perspective),
        )
        _write_text(
            destination / "actions.md",
            _list_markdown(
                "Actions",
                perspective["actions"],
                empty="No action is authorized by this projection.",
            ),
        )
        _write_json(
            destination / "provenance.json",
            {
                "perspective_id": perspective["id"],
                "bundle_id": graph["bundle_id"],
                "node_refs": perspective["node_ids"],
                "edge_refs": perspective["edge_ids"],
                "generator": {
                    "name": "aet-atlas",
                    "mode": "deterministic",
                    "authoritative_narrative": False,
                },
            },
        )
        _write_projection_files(destination, projection, include_children=False)
        _write_recursive_diagrams(
            destination,
            graph,
            perspective,
            hierarchies[perspective["id"]],
            nodes_by_id,
            projections[perspective["id"]],
            previous_perspective_root=(
                previous_root
                / "graph"
                / "perspectives"
                / perspective["id"]
                if previous_root is not None
                else None
            ),
            rebuild_diagrams=rebuild_diagrams,
        )
        sidecar_prefix = f"graph/perspectives/{perspective['id']}"
        diagram_path = f"{sidecar_prefix}/diagram.mmd"
        document_paths = {
            "actions": f"{sidecar_prefix}/actions.md",
            "concerns": f"{sidecar_prefix}/concerns.md",
            "constraints": f"{sidecar_prefix}/constraints.md",
            "context": f"{sidecar_prefix}/context.md",
            "counter_evidence": f"{sidecar_prefix}/counter-evidence.md",
            "description": f"{sidecar_prefix}/description.md",
            "evidence": f"{sidecar_prefix}/evidence.md",
            "freshness": f"{sidecar_prefix}/freshness.md",
            "question": f"{sidecar_prefix}/question.md",
            "unknowns": f"{sidecar_prefix}/unknowns.md",
            "provenance": f"{sidecar_prefix}/provenance.json",
        }
        descriptor = {
            "schema_version": perspective["schema_version"],
            "id": perspective["id"],
            "title": perspective["title"],
            "root_diagram_ids": [
                item["id"]
                for item in hierarchies[perspective["id"]]["diagrams"]
                if item.get("parent_diagram_id") is None
            ],
            "node_ids": perspective["node_ids"],
            "edge_ids": perspective["edge_ids"],
            "diagram": {
                "type": perspective["diagram_type"],
                "path": diagram_path,
                "sha256": _file_sha256(root / diagram_path),
            },
            "documents": {
                name: {
                    "path": relative,
                    "sha256": _file_sha256(root / relative),
                }
                for name, relative in sorted(document_paths.items())
            },
            "extensions": {
                key: perspective[key]
                for key in (
                    "question",
                    "description",
                    "coverage_status",
                    "direction",
                    "root_node_ids",
                    "node_count",
                    "edge_count",
                    "unknowns",
                    "constraints",
                    "concerns",
                    "actions",
                    "provenance",
                )
            },
        }
        _write_json(destination / "perspective.json", descriptor)
    return projections


def _write_recursive_diagrams(
    perspective_root: Path,
    graph: dict[str, Any],
    perspective: dict[str, Any],
    hierarchy: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    viewer_projection: dict[str, Any],
    *,
    previous_perspective_root: Path | None = None,
    rebuild_diagrams: set[str] | None = None,
) -> None:
    paths: dict[str, Path] = {}
    previous_paths = (
        _previous_diagram_directories(previous_perspective_root)
        if previous_perspective_root is not None
        else {}
    )
    diagrams = sorted(
        hierarchy["diagrams"],
        key=lambda item: (item["depth"], item["id"]),
    )
    for diagram in diagrams:
        parent_id = diagram["parent_diagram_id"]
        base = (
            perspective_root
            if parent_id is None
            else paths.get(parent_id, perspective_root)
        )
        node_directory = safe_mermaid_id(diagram["root_node_id"]).lower()
        destination = base / "children" / node_directory
        destination.mkdir(parents=True, exist_ok=True)
        paths[diagram["id"]] = destination
        previous = previous_paths.get(diagram["id"])
        reusable = (
            previous is not None
            and rebuild_diagrams is not None
            and diagram["id"] not in rebuild_diagrams
        )
        if reusable:
            for source in sorted(previous.iterdir()):
                if source.is_file():
                    shutil.copy2(source, destination / source.name)
            projection = _projection_from_directory(destination)
        else:
            projection = render_projection(
                graph,
                node_ids=diagram["node_ids"],
                edge_ids=diagram["edge_ids"],
                diagram_type=perspective["diagram_type"],
                direction=perspective["direction"],
                max_nodes=graph["generation_policy"]["max_nodes_per_diagram"],
                root_ids=[diagram["root_node_id"]],
            )
        viewer_projection["diagrams"][diagram["id"]] = {
            "id": diagram["id"],
            "root_node_id": diagram["root_node_id"],
            "parent_diagram_id": diagram["parent_diagram_id"],
            "child_diagram_ids": diagram["child_diagram_ids"],
            "ir": projection["diagram_ir"],
            "mermaid": projection.get("diagram") or "",
            "diagnostics": projection["diagnostics"],
            "title": nodes_by_id[diagram["root_node_id"]]["title"],
        }
        viewer_projection["node_to_diagram"].setdefault(
            diagram["root_node_id"],
            diagram["id"],
        )
        if not reusable:
            _write_projection_files(destination, projection, include_children=False)
            root_node = nodes_by_id[diagram["root_node_id"]]
            for filename, content in render_document_fields(root_node, graph).items():
                _write_text(destination / filename, content)
        _write_json(
            destination / "hierarchy.json",
            diagram,
        )
    for reference in hierarchy["references"]:
        parent = reference.get("parent_diagram_id")
        base = paths.get(parent, perspective_root)
        reference_root = base / "references"
        reference_root.mkdir(parents=True, exist_ok=True)
        name = (
            safe_mermaid_id(reference["node_id"]).lower()
            + "-"
            + reference["reason"]
            + ".json"
        )
        _write_json(reference_root / name, reference)


def _previous_diagram_directories(
    perspective_root: Path,
) -> dict[str, Path]:
    result: dict[str, Path] = {}
    if not perspective_root.is_dir():
        return result
    for hierarchy_path in sorted(
        perspective_root.glob("children/**/hierarchy.json")
    ):
        diagram = _read_json_object(hierarchy_path)
        identifier = diagram.get("id")
        if isinstance(identifier, str):
            result[identifier] = hierarchy_path.parent
    return result


def _projection_from_directory(directory: Path) -> dict[str, Any]:
    try:
        diagnostics = json.loads(
            (directory / "diagnostics.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AtlasStorageError(
            f"invalid prior recursive projection: {directory}"
        ) from error
    if not isinstance(diagnostics, list):
        raise AtlasStorageError(
            f"invalid prior recursive projection: {directory}"
        )
    return {
        "diagram_ir": _read_json_object(directory / "diagram-ir.json"),
        "diagram": (directory / "diagram.mmd").read_text(encoding="utf-8"),
        "diagnostics": diagnostics,
    }


def _build_all_hierarchies(
    graph: dict[str, Any],
    perspectives: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    maximum = graph["generation_policy"]["max_total_diagrams"]
    remaining = maximum
    result: dict[str, dict[str, Any]] = {}
    for index, perspective in enumerate(perspectives):
        remaining_perspectives = len(perspectives) - index - 1
        current_budget = remaining - remaining_perspectives
        original = graph["generation_policy"]["max_total_diagrams"]
        graph["generation_policy"]["max_total_diagrams"] = current_budget
        try:
            hierarchy = build_hierarchy(graph, perspective)
        finally:
            graph["generation_policy"]["max_total_diagrams"] = original
        hierarchy["generation_policy"]["max_total_diagrams"] = maximum
        result[perspective["id"]] = hierarchy
        remaining -= len(hierarchy["diagrams"])
    if sum(len(value["diagrams"]) for value in result.values()) > maximum:
        raise AtlasStorageError("Atlas hierarchy exceeded max_total_diagrams")
    return result


def _write_projection_files(
    root: Path,
    projection: Mapping[str, Any],
    *,
    include_children: bool = True,
) -> None:
    for relative, content in sorted(projection["files"].items()):
        if not include_children and relative.startswith("children/"):
            continue
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(path, content)


def _write_viewer(
    root: Path,
    graph: dict[str, Any],
    projections: dict[str, dict[str, Any]],
) -> None:
    viewer_root = root / "atlas"
    viewer_root.mkdir()
    for relative, raw in viewer_files(graph, projections).items():
        path = viewer_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    _write_json(
        viewer_root / "atlas-manifest.json",
        {
            "schema_version": "aet-evidence-atlas-viewer/1.0",
            "bundle_id": graph["bundle_id"],
            "bundle_content_hash": graph["generated_from"]["bundle_content_hash"],
            "graph": "../graph/graph.json",
            "mermaid_version": MERMAID_VERSION,
            "security_level": "strict",
            "network_required": False,
        },
    )


def _seal_sidecar(
    root: Path,
    bundle: Mapping[str, Any],
    graph: Mapping[str, Any],
    perspectives: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    hashes = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in sorted(_regular_files(root))
    }
    return {
        "schema_version": ATLAS_MANIFEST_SCHEMA,
        "bundle": {
            "id": bundle["manifest"]["bundle"]["id"],
            "content_hash": bundle["manifest"]["bundle"]["content_hash"],
        },
        "generated_from": dict(graph["generated_from"]),
        "contents": {
            "graph": "graph/graph.json",
            "nodes": "graph/nodes.jsonl",
            "edges": "graph/edges.jsonl",
            "hierarchy": "graph/hierarchy.json",
            "diagnostics": "graph/diagnostics.jsonl",
            "perspectives": [
                f"graph/perspectives/{perspective['id']}/perspective.json"
                for perspective in perspectives
            ],
        },
        "generation_policy": dict(graph["generation_policy"]),
        "extensions": {
            "viewer": {
                "mermaid_version": MERMAID_VERSION,
                "security_level": "strict",
                "network_required": False,
            },
            "dependencies": "graph/dependencies.json",
            "candidate_edges": "graph/candidates/edges.jsonl",
            "viewer_entrypoint": "atlas/index.html",
        },
        "integrity": {
            "algorithm": "sha256",
            "file_hashes": hashes,
        },
    }


def _load_previous_atlas(path: Path) -> dict[str, Any] | None:
    try:
        return load_evidence_atlas(path)
    except (AtlasStorageError, OSError, ValueError):
        return None


def _previous_projection_exists(
    previous_root: Path,
    perspective_id: str,
) -> bool:
    root = previous_root / "graph" / "perspectives" / perspective_id
    return all(
        (root / name).is_file()
        for name in (
            "perspective.json",
            "diagram-ir.json",
            "diagram.mmd",
            "diagnostics.json",
        )
    )


def _select_perspectives(
    perspectives: list[dict[str, Any]],
    requested: Iterable[str] | None,
) -> list[dict[str, Any]]:
    if requested is None:
        return perspectives
    identifiers = list(requested)
    if not identifiers:
        raise AtlasStorageError("at least one Perspective must be selected")
    if len(set(identifiers)) != len(identifiers):
        raise AtlasStorageError("Perspective selection contains duplicates")
    unsupported = sorted(set(identifiers) - set(PERSPECTIVES))
    if unsupported:
        raise AtlasStorageError(
            f"unsupported Perspective selection: {', '.join(unsupported)}"
        )
    selected = set(identifiers)
    return [
        perspective
        for perspective in perspectives
        if perspective["id"] in selected
    ]


def _load_previous_projection(
    previous_root: Path,
    perspective_id: str,
) -> dict[str, Any]:
    root = previous_root / "graph" / "perspectives" / perspective_id
    diagram_ir = _read_json_object(root / "diagram-ir.json")
    try:
        diagnostics = json.loads(
            (root / "diagnostics.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AtlasStorageError(
            f"invalid prior projection diagnostics: {perspective_id}"
        ) from error
    if not isinstance(diagnostics, list):
        raise AtlasStorageError(
            f"invalid prior projection diagnostics: {perspective_id}"
        )
    return {
        "diagram_ir": diagram_ir,
        "diagram": (root / "diagram.mmd").read_text(encoding="utf-8"),
        "diagnostics": diagnostics,
    }


def _load_previous_recursive_projections(
    perspective_root: Path,
    viewer_projection: dict[str, Any],
    nodes_by_id: Mapping[str, Mapping[str, Any]],
) -> None:
    for hierarchy_path in sorted(
        perspective_root.glob("children/**/hierarchy.json")
    ):
        directory = hierarchy_path.parent
        diagram = _read_json_object(hierarchy_path)
        diagram_id = diagram.get("id")
        root_node_id = diagram.get("root_node_id")
        if (
            not isinstance(diagram_id, str)
            or not isinstance(root_node_id, str)
            or root_node_id not in nodes_by_id
        ):
            raise AtlasStorageError("invalid prior recursive projection")
        try:
            diagnostics = json.loads(
                (directory / "diagnostics.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AtlasStorageError(
                f"invalid prior recursive diagnostics: {diagram_id}"
            ) from error
        if not isinstance(diagnostics, list):
            raise AtlasStorageError(
                f"invalid prior recursive diagnostics: {diagram_id}"
            )
        viewer_projection["diagrams"][diagram_id] = {
            "id": diagram_id,
            "root_node_id": root_node_id,
            "parent_diagram_id": diagram.get("parent_diagram_id"),
            "child_diagram_ids": diagram.get("child_diagram_ids", []),
            "ir": _read_json_object(directory / "diagram-ir.json"),
            "mermaid": (directory / "diagram.mmd").read_text(encoding="utf-8"),
            "diagnostics": diagnostics,
            "title": nodes_by_id[root_node_id]["title"],
        }
        viewer_projection["node_to_diagram"].setdefault(
            root_node_id,
            diagram_id,
        )


def _merge_current_impact(
    incremental: dict[str, list[str]],
    graph: Mapping[str, Any],
) -> None:
    dependency = graph["dependency_index"]
    changed = incremental["records"]
    nodes = set(incremental["nodes"])
    edges = set(incremental["edges"])
    perspectives = set(incremental["perspectives"])
    parents = set(incremental["parent_diagrams"])
    for record in changed:
        nodes.update(dependency["record_to_nodes"].get(record, []))
        edges.update(dependency["record_to_edges"].get(record, []))
        perspectives.update(
            dependency["record_to_perspectives"].get(record, [])
        )
        parents.update(
            dependency["record_to_parent_diagrams"].get(record, [])
        )
    for node in nodes:
        perspectives.update(
            dependency["node_to_perspectives"].get(node, [])
        )
        parents.update(
            dependency["node_to_parent_diagrams"].get(node, [])
        )
    if changed and not perspectives:
        perspectives.update(PERSPECTIVES)
    incremental.update(
        {
            "nodes": sorted(nodes),
            "edges": sorted(edges),
            "perspectives": sorted(perspectives),
            "parent_diagrams": sorted(parents),
        }
    )


def _reuse_unchanged_files(previous: Path, staged: Path) -> None:
    previous = _safe_root(previous)
    for relative in sorted(_regular_files(staged)):
        old = previous / relative
        new = staged / relative
        if not old.is_file() or old.is_symlink():
            continue
        if old.read_bytes() != new.read_bytes():
            continue
        new.unlink()
        try:
            os.link(old, new)
        except OSError:
            shutil.copy2(old, new)


def _publish_directory(staged: Path, destination: Path) -> None:
    backup = destination.with_name(
        f".{destination.name}.backup-{uuid.uuid4().hex}"
    )
    moved_old = False
    try:
        if destination.exists():
            if destination.is_symlink() or not destination.is_dir():
                raise AtlasStorageError(
                    f"Atlas output must be a regular directory: {destination}"
                )
            os.replace(destination, backup)
            moved_old = True
        os.replace(staged, destination)
    except Exception:
        if moved_old and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup)


def _outside_bundle(bundle: Path, destination: Path) -> None:
    if destination == bundle:
        raise AtlasStorageError("Atlas sidecar cannot overwrite its source Bundle")
    try:
        destination.relative_to(bundle)
    except ValueError:
        return
    raise AtlasStorageError(
        "Atlas sidecar must remain outside the v1 Bundle root to preserve compatibility"
    )


def _safe_root(path: Path) -> Path:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise AtlasStorageError(f"Atlas sidecar is unavailable: {error}") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise AtlasStorageError("Atlas sidecar root must be a regular directory")
    resolved = path.resolve(strict=True)
    for candidate in resolved.rglob("*"):
        mode = candidate.lstat().st_mode
        if stat.S_ISLNK(mode) or not (
            stat.S_ISDIR(mode) or stat.S_ISREG(mode)
        ):
            raise AtlasStorageError(
                f"Atlas sidecar contains an unsafe path: {candidate}"
            )
    return resolved


def _safe_file(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or path.is_absolute()
        or path.as_posix() != relative
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise AtlasStorageError(f"unsafe Atlas path: {relative!r}")
    candidate = root.joinpath(*path.parts)
    if not candidate.is_file() or candidate.is_symlink():
        raise AtlasStorageError(f"Atlas file is unavailable: {relative}")
    try:
        candidate.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        raise AtlasStorageError(f"Atlas path escapes its root: {relative}") from error
    return candidate


def _regular_files(root: Path) -> set[str]:
    return {
        candidate.relative_to(root).as_posix()
        for candidate in root.rglob("*")
        if candidate.is_file() and not candidate.is_symlink()
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_bytes(value) + b"\n")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.write_bytes(
        b"".join(canonical_bytes(value) + b"\n" for value in values)
    )


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _read_json_object(path: Path) -> dict[str, Any]:
    return _decode_json_object(path.read_bytes(), path.name)


def _decode_json_object(raw: bytes | None, label: str) -> dict[str, Any]:
    if not isinstance(raw, bytes):
        raise AtlasStorageError(f"Atlas file was not loaded: {label}")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AtlasStorageError(f"invalid Atlas JSON: {label}") from error
    if not isinstance(value, dict):
        raise AtlasStorageError(f"Atlas JSON must contain an object: {label}")
    return value


def _decode_jsonl(raw: bytes | None, label: str) -> list[dict[str, Any]]:
    if not isinstance(raw, bytes):
        raise AtlasStorageError(f"Atlas file was not loaded: {label}")
    values = []
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise AtlasStorageError(f"Atlas JSONL must be UTF-8: {label}") from error
    for number, line in enumerate(lines, start=1):
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise AtlasStorageError(
                f"invalid Atlas JSONL: {label}:{number}"
            ) from error
        if not isinstance(value, dict):
            raise AtlasStorageError(
                f"Atlas JSONL row must be an object: {label}:{number}"
            )
        values.append(value)
    return values


def _unknowns_markdown(perspective: Mapping[str, Any]) -> str:
    unknowns = perspective.get("unknowns", [])
    if not isinstance(unknowns, list) or not unknowns:
        return "# Unknowns\n\nNo explicit UNKNOWN is recorded for this Perspective.\n"
    return "# Unknowns\n\n" + "".join(f"- {value}\n" for value in unknowns)


def _list_markdown(
    title: str,
    values: Any,
    *,
    empty: str = "None recorded.",
) -> str:
    if not isinstance(values, list) or not values:
        return f"# {title}\n\n{empty}\n"
    return f"# {title}\n\n" + "".join(f"- {value}\n" for value in values)


def _unique_diagnostics(
    values: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[bytes] = set()
    result = []
    for value in values:
        encoded = canonical_bytes(value)
        if encoded in seen:
            continue
        seen.add(encoded)
        result.append(value)
    return sorted(
        result,
        key=lambda item: (
            str(item.get("severity", "")),
            str(item.get("code", "")),
            str(item.get("perspective_id", "")),
            str(item.get("node_id", "")),
            str(item.get("message", "")),
        ),
    )


def _normalize_diagnostics(
    values: list[dict[str, Any]],
    graph: Mapping[str, Any],
) -> list[dict[str, Any]]:
    nodes = {
        node["id"]: node
        for node in graph.get("nodes", [])
        if isinstance(node, Mapping) and isinstance(node.get("id"), str)
    }
    perspectives = {
        item["id"]: item
        for item in graph.get("perspectives", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    fallback_refs = next(
        (
            list(node["source_refs"])
            for node in nodes.values()
            if node.get("type") == "intent"
        ),
        [],
    )
    normalized = []
    for value in values:
        node_id = value.get("node_id")
        perspective_id = value.get("perspective_id")
        refs = value.get("source_refs")
        if not isinstance(refs, list) or not refs:
            if isinstance(node_id, str) and node_id in nodes:
                refs = list(nodes[node_id]["source_refs"])
            elif (
                isinstance(perspective_id, str)
                and perspective_id in perspectives
            ):
                root_ids = perspectives[perspective_id].get(
                    "root_node_ids", []
                )
                refs = [
                    ref
                    for root_id in root_ids
                    if root_id in nodes
                    for ref in nodes[root_id]["source_refs"]
                ]
            else:
                refs = list(fallback_refs)
        extras = {
            key: value[key]
            for key in value
            if key not in {"code", "severity", "message", "source_refs"}
        }
        normalized.append(
            {
                "code": str(value.get("code", "ATLAS_DIAGNOSTIC")),
                "severity": str(value.get("severity", "warning")),
                "message": str(value.get("message", "Atlas diagnostic")),
                "source_refs": refs,
                **({"extensions": extras} if extras else {}),
            }
        )
    return _unique_diagnostics(normalized)


def _flatten_hierarchies(
    hierarchies: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    diagrams = []
    for perspective_id, hierarchy in sorted(hierarchies.items()):
        for diagram in hierarchy["diagrams"]:
            required = {
                key: diagram[key]
                for key in (
                    "id",
                    "perspective_id",
                    "root_node_id",
                    "parent_diagram_id",
                    "depth",
                    "node_ids",
                    "edge_ids",
                    "child_diagram_ids",
                    "reference_node_ids",
                )
            }
            extras = {
                key: value
                for key, value in diagram.items()
                if key not in required
            }
            diagrams.append(
                {
                    **required,
                    **({"extensions": extras} if extras else {}),
                }
            )
    return {
        "schema_version": "aet-evidence-hierarchy/1.0",
        "diagrams": sorted(diagrams, key=lambda item: item["id"]),
    }


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
