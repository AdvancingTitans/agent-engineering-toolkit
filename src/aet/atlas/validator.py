"""Fail-closed validation for canonical Evidence Graphs and Atlas sidecars."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .model import (
    ATLAS_MANIFEST_SCHEMA,
    EDGE_TYPES,
    GRAPH_SCHEMA,
    NODE_STATUSES,
    NODE_TYPES,
    PERSPECTIVES,
    PERSPECTIVE_SCHEMA,
    merge_policy,
    record_hashes,
)
from .schema_validation import AtlasSchemaError, validate_schema


_COLLECTIONS = {
    "core/claims.jsonl": "claims",
    "core/evidence.jsonl": "evidence",
    "core/observations.jsonl": "observations",
    "archive/sources.jsonl": "sources",
    "archive/diagnostics.jsonl": "diagnostics",
    "archive/conflicts.jsonl": "conflicts",
    "archive/ledger.jsonl": "ledger",
    "manifest.json": "manifest",
    "index.json": "index",
    "policy.json": "policy",
}
_CONTROL_RECORD_IDS = {
    "manifest.json": "manifest",
    "index.json": "index",
    "policy.json": "policy",
}
_FRESHNESS = {
    "current",
    "relevant_files_changed",
    "workspace_changed",
    "environment_changed",
    "unknown",
    "not_applicable",
}
_STALE_FRESHNESS = {
    "relevant_files_changed",
    "workspace_changed",
    "environment_changed",
}
_IMPORTANCE = {"low", "normal", "high"}
_CLASSIFICATIONS = {"leaf", "expandable", "mandatory_decomposition"}
_DIAGRAM_TYPES = {"flowchart", "sequenceDiagram", "timeline", "stateDiagram"}
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FIELD_PART = re.compile(r"^([A-Za-z0-9_-]+)(?:\[([0-9]+)\])?$")
_FORBIDDEN_MERMAID = (
    (re.compile(r"(?im)^\s*click\b"), "click directives"),
    (re.compile(r"(?i)%%\s*\{"), "configuration directives"),
    (re.compile(r"(?i)<\s*/?\s*[a-z]"), "HTML labels"),
    (re.compile(r"(?i)\b(?:https?|file|javascript|data)\s*:"), "external or active URLs"),
    (re.compile(r"(?i)(?:src|href)\s*="), "HTML resource attributes"),
    (re.compile(r"(?i)\b(?:img|icon)\s*:"), "image nodes"),
)


class AtlasValidationError(ValueError):
    """An Evidence Graph or Atlas sidecar failed a fail-closed check."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def validate_evidence_graph(
    graph: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one in-memory canonical Graph against its source Bundle."""
    if not isinstance(graph, Mapping) or not isinstance(bundle, Mapping):
        _fail("invalid_argument", "graph and bundle must be mappings")
    value = dict(graph)
    _schema_validate(value, "graph.schema.json", "graph")
    _validate_graph_shape(value)
    _validate_bundle_identity(value, bundle)
    records = _record_index(bundle)
    nodes = _validate_nodes(value["nodes"], records)
    edges = _validate_edges(value["edges"], nodes, records)
    _validate_diagnostics(value["diagnostics"], records)
    _validate_authority_boundaries(value, bundle, nodes, edges)
    _validate_dependencies(value, bundle, nodes, edges)
    _validate_graph_perspective_refs(value, nodes, edges)
    return value


def validate_evidence_atlas(
    sidecar: Mapping[str, Any] | Path | str,
    bundle_path: Path | str,
) -> dict[str, Any]:
    """Validate an Atlas manifest, JSONL sidecars, hierarchy, and projections."""
    # Delayed import keeps the Atlas package independent of Bundle loader import order.
    from aet.bundle import validate_bundle

    bundle = validate_bundle(Path(bundle_path))
    if isinstance(sidecar, Mapping):
        manifest = dict(sidecar)
        root_value = manifest.pop("_root", None)
        root = Path(root_value).resolve() if isinstance(root_value, str) else None
    else:
        manifest_path = Path(sidecar)
        manifest = _read_json_object(manifest_path, "Atlas manifest")
        root = manifest_path.parent.resolve()
    _validate_manifest_shape(manifest)
    _schema_validate(manifest, "atlas-manifest.schema.json", "Atlas manifest")
    _validate_manifest_identity(manifest, bundle)
    if root is None:
        _fail(
            "sidecar_error",
            "in-memory Atlas manifest requires a string _root for file validation",
        )
    files = _validate_sidecar_hashes(root, manifest)
    for relative, raw in sorted(files.items()):
        if relative.startswith("graph/perspectives/") and relative.endswith(
            "/diagram.mmd"
        ):
            try:
                source = raw.decode("utf-8")
            except UnicodeDecodeError:
                _fail("mermaid_error", f"{relative} must be UTF-8")
            validate_mermaid(source, label=relative)
        if relative.startswith("graph/perspectives/") and relative.endswith(
            "/provenance.json"
        ):
            provenance = _decode_json(raw, relative)
            _schema_validate(
                provenance,
                "provenance.schema.json",
                relative,
            )
        if relative.startswith("graph/perspectives/") and relative.endswith(
            "/diagram-ir.json"
        ):
            diagram_ir = _decode_json(raw, relative)
            _schema_validate(
                diagram_ir,
                "diagram-ir.schema.json",
                relative,
            )
    contents = manifest["contents"]
    graph = _decode_json(files[contents["graph"]], contents["graph"])
    if not isinstance(graph, dict):
        _fail("sidecar_error", "graph sidecar must contain one JSON object")
    nodes_jsonl = _decode_jsonl(files[contents["nodes"]], contents["nodes"])
    edges_jsonl = _decode_jsonl(files[contents["edges"]], contents["edges"])
    if graph.get("nodes") != nodes_jsonl:
        _fail("sidecar_error", "graph nodes do not exactly match nodes.jsonl")
    if graph.get("edges") != edges_jsonl:
        _fail("sidecar_error", "graph edges do not exactly match edges.jsonl")
    validated = validate_evidence_graph(graph, bundle)

    diagnostics = _decode_jsonl(
        files[contents["diagnostics"]], contents["diagnostics"]
    )
    if graph.get("diagnostics") != diagnostics:
        _fail(
            "sidecar_error",
            "graph diagnostics do not exactly match diagnostics.jsonl",
        )
    hierarchy = _decode_json(files[contents["hierarchy"]], contents["hierarchy"])
    if not isinstance(hierarchy, dict):
        _fail("hierarchy_error", "hierarchy sidecar must contain one JSON object")
    _schema_validate(hierarchy, "hierarchy.schema.json", "hierarchy")
    perspective_documents = []
    for relative in contents["perspectives"]:
        document = _decode_json(files[relative], relative)
        if not isinstance(document, dict):
            _fail("perspective_error", f"{relative} must contain one JSON object")
        _schema_validate(document, "perspective.schema.json", relative)
        perspective_documents.append(document)
    _validate_perspectives(
        perspective_documents,
        hierarchy,
        validated,
        files,
        manifest["generation_policy"],
    )
    return {
        "schema_version": ATLAS_MANIFEST_SCHEMA,
        "bundle_id": validated["bundle_id"],
        "graph": validated,
        "hierarchy": hierarchy,
        "perspectives": perspective_documents,
        "manifest": manifest,
    }


def validate_mermaid(source: str, *, label: str = "diagram.mmd") -> None:
    """Reject unsafe Mermaid capabilities and unsupported diagram types."""
    if not isinstance(source, str) or not source.strip():
        _fail("mermaid_error", f"{label} must be non-empty UTF-8 text")
    if "\x00" in source:
        _fail("mermaid_error", f"{label} contains a NUL byte")
    first = next((line.strip() for line in source.splitlines() if line.strip()), "")
    accepted_header = bool(
        re.fullmatch(r"flowchart\s+(?:LR|RL|TD|TB|BT)", first)
        or first == "sequenceDiagram"
        or first == "timeline"
        or first in {"stateDiagram", "stateDiagram-v2"}
    )
    if not accepted_header:
        _fail("mermaid_error", f"{label} uses an unsupported diagram type")
    for pattern, description in _FORBIDDEN_MERMAID:
        if pattern.search(source):
            _fail("mermaid_error", f"{label} contains forbidden {description}")
    _validate_mermaid_subset_syntax(source, first, label)


def _validate_mermaid_subset_syntax(
    source: str, header: str, label: str
) -> None:
    """Validate the exact deterministic subset emitted by AET renderers."""
    identifier = r"[A-Za-z][A-Za-z0-9_]*"
    flow_node = re.compile(
        rf'^{identifier}(?:\["[^"]*"\]|\("[^"]*"\)|'
        rf'\[\["[^"]*"\]\]|\{{"[^"]*"\}}|'
        rf'\{{\{{"[^"]*"\}}\}}|\[/"[^"]*"/\])$'
    )
    flow_edge = re.compile(
        rf'^{identifier}\s+(?:-->|==>|-\.->)\|"[^"]*"\|\s+{identifier}$'
    )
    flow_class = re.compile(rf"^class\s+{identifier}\s+{identifier}$")
    flow_class_def = re.compile(rf"^classDef\s+{identifier}\s+.+$")
    sequence_participant = re.compile(
        rf"^participant\s+{identifier}\s+as\s+.+$"
    )
    sequence_edge = re.compile(
        rf"^{identifier}(?:->>|-->>){identifier}:\s+.+$"
    )
    timeline_step = re.compile(r"^.+\s+:\s+.+$")
    state_node = re.compile(
        rf'^state\s+"[^"]*"\s+as\s+{identifier}$'
    )
    state_edge = re.compile(
        rf"^{identifier}\s+-->\s+{identifier}:\s+.+$"
    )
    body = [
        line.strip()
        for line in source.splitlines()[1:]
        if line.strip()
    ]
    for line in body:
        if line.startswith("%%"):
            continue
        valid = False
        if header.startswith("flowchart "):
            valid = any(
                pattern.fullmatch(line)
                for pattern in (
                    flow_node,
                    flow_edge,
                    flow_class,
                    flow_class_def,
                )
            )
        elif header == "sequenceDiagram":
            valid = bool(
                sequence_participant.fullmatch(line)
                or sequence_edge.fullmatch(line)
            )
        elif header == "timeline":
            valid = bool(
                re.fullmatch(r"title\s+.+", line)
                or timeline_step.fullmatch(line)
            )
        else:
            valid = bool(
                re.fullmatch(r"direction\s+(?:LR|TB)", line)
                or state_node.fullmatch(line)
                or state_edge.fullmatch(line)
            )
        if not valid:
            _fail(
                "mermaid_error",
                f"{label} contains syntax outside the deterministic AET subset: {line!r}",
            )


def _schema_validate(value: Any, schema: str, label: str) -> None:
    try:
        validate_schema(value, schema)
    except AtlasSchemaError as error:
        _fail("schema_error", f"{label}: {error}")


def _validate_graph_shape(graph: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "bundle_id",
        "generated_from",
        "generation_policy",
        "nodes",
        "edges",
        "perspectives",
        "diagnostics",
        "dependency_index",
    }
    _exact_or_extension_keys(graph, required, "graph")
    if graph["schema_version"] != GRAPH_SCHEMA:
        _fail("schema_error", "unsupported Evidence Graph schema")
    _nonempty_string(graph["bundle_id"], "graph.bundle_id")
    generated = graph["generated_from"]
    _exact_keys(
        generated,
        {"bundle_content_hash", "manifest_sha256", "index_sha256"},
        "graph.generated_from",
    )
    for name, digest in generated.items():
        _sha256(digest, f"graph.generated_from.{name}")
    try:
        normalized = merge_policy(graph["generation_policy"])
    except (TypeError, ValueError) as error:
        _fail("policy_error", str(error))
    if normalized != graph["generation_policy"]:
        _fail("policy_error", "generation_policy must explicitly contain the full policy")
    _array(graph["nodes"], "graph.nodes")
    _array(graph["edges"], "graph.edges")
    _array(graph["perspectives"], "graph.perspectives")
    _array(graph["diagnostics"], "graph.diagnostics")
    _mapping(graph["dependency_index"], "graph.dependency_index")


def _validate_bundle_identity(graph: dict[str, Any], bundle: Mapping[str, Any]) -> None:
    manifest = bundle.get("manifest")
    index = bundle.get("index")
    if not isinstance(manifest, Mapping) or not isinstance(index, Mapping):
        _fail("bundle_identity_error", "source Bundle is missing manifest or index")
    bundle_document = manifest.get("bundle")
    if not isinstance(bundle_document, Mapping):
        _fail("bundle_identity_error", "source Bundle manifest.bundle is invalid")
    if graph["bundle_id"] != bundle_document.get("id"):
        _fail("bundle_identity_error", "Graph bundle_id does not match source Bundle")
    generated = graph["generated_from"]
    if generated["bundle_content_hash"] != bundle_document.get("content_hash"):
        _fail(
            "bundle_identity_error",
            "Graph bundle content hash does not match source Bundle",
        )
    manifest_raw = _bundle_file(bundle, "manifest.json", manifest)
    index_raw = _bundle_file(bundle, "index.json", index)
    if generated["manifest_sha256"] != hashlib.sha256(manifest_raw).hexdigest():
        _fail("bundle_identity_error", "Graph manifest SHA-256 is stale or incorrect")
    if generated["index_sha256"] != hashlib.sha256(index_raw).hexdigest():
        _fail("bundle_identity_error", "Graph index SHA-256 is stale or incorrect")


def _validate_nodes(
    rows: Sequence[Any],
    records: Mapping[tuple[str, str], Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        label = f"graph.nodes[{index}]"
        _mapping(raw, label)
        node = dict(raw)
        required = {
            "id",
            "type",
            "source_refs",
            "title",
            "summary",
            "status",
            "authority",
            "freshness",
            "importance",
            "complexity",
            "tags",
            "attributes",
        }
        _exact_or_extension_keys(node, required, label)
        node_id = _nonempty_string(node["id"], f"{label}.id")
        if not node_id.startswith("node:"):
            _fail("node_error", f"{label}.id must use the node: namespace")
        if node_id in result:
            _fail("node_error", f"duplicate canonical node ID: {node_id}")
        if node["type"] not in NODE_TYPES:
            _fail("node_error", f"{node_id} uses unknown node type {node['type']!r}")
        if node["status"] not in NODE_STATUSES:
            _fail("node_error", f"{node_id} uses unknown status {node['status']!r}")
        if node["freshness"] not in _FRESHNESS:
            _fail("node_error", f"{node_id} uses unknown freshness {node['freshness']!r}")
        if node["importance"] not in _IMPORTANCE:
            _fail("node_error", f"{node_id} uses unknown importance")
        for name in ("title", "summary", "authority"):
            _nonempty_string(node[name], f"{label}.{name}")
        _validate_source_refs(node["source_refs"], records, f"{label}.source_refs")
        _string_array(node["tags"], f"{label}.tags", unique=True)
        _mapping(node["attributes"], f"{label}.attributes")
        _validate_complexity(node["complexity"], node_id)
        result[node_id] = node
    if list(result) != sorted(result):
        _fail("node_error", "graph nodes must be sorted by canonical ID")
    return result


def _validate_edges(
    rows: Sequence[Any],
    nodes: Mapping[str, dict[str, Any]],
    records: Mapping[tuple[str, str], Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        label = f"graph.edges[{index}]"
        _mapping(raw, label)
        edge = dict(raw)
        required = {
            "id",
            "from",
            "to",
            "type",
            "source_refs",
            "authority",
            "freshness_effect",
            "render",
        }
        _exact_or_extension_keys(edge, required, label)
        edge_id = _nonempty_string(edge["id"], f"{label}.id")
        if not edge_id.startswith("edge:"):
            _fail("edge_error", f"{label}.id must use the edge: namespace")
        if edge_id in result:
            _fail("edge_error", f"duplicate edge ID: {edge_id}")
        if edge["type"] not in EDGE_TYPES:
            _fail("edge_error", f"{edge_id} uses unknown edge type {edge['type']!r}")
        if edge["from"] not in nodes or edge["to"] not in nodes:
            _fail("dead_link", f"{edge_id} references an unavailable graph node")
        if edge["authority"] != "deterministic_reference":
            _fail("authority_error", f"{edge_id} is not a deterministic reference")
        if edge["freshness_effect"] not in {"required", "not_applicable"}:
            _fail("freshness_error", f"{edge_id} has invalid freshness_effect")
        _validate_source_refs(edge["source_refs"], records, f"{label}.source_refs")
        _mapping(edge["render"], f"{label}.render")
        _exact_keys(edge["render"], {"label", "priority"}, f"{label}.render")
        _nonempty_string(edge["render"]["label"], f"{label}.render.label")
        priority = edge["render"]["priority"]
        if not _plain_int(priority) or not 0 <= priority <= 100:
            _fail("edge_error", f"{label}.render.priority must be from 0 through 100")
        result[edge_id] = edge
    if list(result) != sorted(result):
        _fail("edge_error", "graph edges must be sorted by edge ID")
    return result


def _validate_diagnostics(
    rows: Sequence[Any],
    records: Mapping[tuple[str, str], Any],
) -> None:
    previous: tuple[str, str, str] | None = None
    for index, raw in enumerate(rows):
        label = f"graph.diagnostics[{index}]"
        _exact_or_extension_keys(
            raw,
            {"code", "severity", "message", "source_refs"},
            label,
        )
        code = _nonempty_string(raw["code"], f"{label}.code")
        if re.fullmatch(r"[A-Z][A-Z0-9_]+", code) is None:
            _fail("diagnostic_error", f"{label}.code is invalid")
        if raw["severity"] not in {"info", "warning", "error"}:
            _fail("diagnostic_error", f"{label}.severity is invalid")
        message = _nonempty_string(raw["message"], f"{label}.message")
        _validate_source_refs(raw["source_refs"], records, f"{label}.source_refs")
        ordering = (raw["severity"], code, message)
        if previous is not None and ordering < previous:
            _fail("diagnostic_error", "graph diagnostics must be deterministically sorted")
        previous = ordering


def _validate_authority_boundaries(
    graph: Mapping[str, Any],
    bundle: Mapping[str, Any],
    nodes: Mapping[str, dict[str, Any]],
    edges: Mapping[str, dict[str, Any]],
) -> None:
    outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges.values():
        outgoing[edge["from"]].append(edge)
        source_type = nodes[edge["from"]]["type"]
        target_type = nodes[edge["to"]]["type"]
        if edge["type"] in {"SUPPORTED_BY", "PARTIALLY_SUPPORTED_BY"}:
            if source_type not in {"claim", "subclaim"} or target_type != "verified_evidence":
                _fail(
                    "authority_error",
                    f"{edge['id']} may only connect a Claim to Verified Evidence",
                )
            if edge["freshness_effect"] != "required":
                _fail("freshness_error", f"{edge['id']} must require Freshness")
            if (
                edge["type"] == "SUPPORTED_BY"
                and nodes[edge["to"]]["freshness"] != "current"
            ):
                _fail(
                    "freshness_error",
                    f"{edge['id']} cannot use stale or unknown Evidence as current support",
                )
        if edge["type"] == "CONTRADICTED_BY":
            if source_type not in {"claim", "subclaim", "conflict"} or target_type != "verified_evidence":
                _fail("counter_evidence_error", f"{edge['id']} has invalid endpoint types")
        if target_type == "observation" and edge["type"] in {
            "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY",
            "VALIDATES",
        }:
            _fail("observation_boundary_error", "Observation cannot act as Verified Evidence")
        if edge["type"] == "VALIDATES":
            proof = nodes[edge["from"]]
            if proof["type"] != "proof" or target_type not in {"claim", "subclaim"}:
                _fail("authority_error", f"{edge['id']} has invalid validation endpoints")
            if proof["freshness"] != "current" or proof["status"] != "verified":
                _fail("freshness_error", "stale or unknown Proof cannot validate a Claim")
        if edge["type"] == "FRESH_FOR":
            freshness = nodes[edge["from"]]
            target = nodes[edge["to"]]
            if (
                freshness["type"] != "freshness_result"
                or freshness["freshness"] != "current"
                or target["freshness"] != "current"
            ):
                _fail("freshness_error", f"{edge['id']} incorrectly declares current evidence")
        if edge["type"] == "STALE_FOR":
            if nodes[edge["from"]]["type"] != "freshness_result":
                _fail("freshness_error", f"{edge['id']} must start at Freshness Result")

        _validate_reference_edge_target(edge, bundle, nodes)

    _validate_required_bundle_edges(bundle, nodes, edges)

    for node in nodes.values():
        if node["type"] == "observation":
            if (
                node["authority"] != "observation"
                or node["status"] != "recorded"
                or node["freshness"] != "unknown"
            ):
                _fail(
                    "observation_boundary_error",
                    f"Observation {node['id']} exceeds recorded Observation authority",
                )
        if node["type"] in {"verified_evidence", "proof"}:
            if node["freshness"] in _STALE_FRESHNESS and node["status"] != "stale":
                _fail("freshness_error", f"{node['id']} hides stale applicability")
            if node["freshness"] == "unknown" and node["status"] == "verified":
                _fail("freshness_error", f"{node['id']} promotes unknown Freshness")

    claim_nodes = _nodes_by_record(nodes, "core/claims.jsonl")
    evidence_nodes = _nodes_by_record(nodes, "core/evidence.jsonl", "verified_evidence")
    claims = {row["id"]: row for row in bundle.get("claims", [])}
    evidence = {row["id"]: row for row in bundle.get("evidence", [])}
    for claim_id, claim in claims.items():
        graph_claim = claim_nodes.get(claim_id)
        if graph_claim is None:
            _fail("counter_evidence_error", f"Graph omits Claim {claim_id}")
        actual_counter = {
            edge["to"]
            for edge in outgoing[graph_claim["id"]]
            if edge["type"] == "CONTRADICTED_BY"
        }
        expected_counter = {
            evidence_nodes[record_id]["id"]
            for record_id in claim["counter_evidence_refs"]
            if record_id in evidence_nodes
        }
        if expected_counter != actual_counter:
            _fail(
                "counter_evidence_error",
                f"Graph does not preserve every counter-evidence reference for {claim_id}",
            )
        if claim["counter_evidence_refs"] and len(expected_counter) != len(
            claim["counter_evidence_refs"]
        ):
            _fail("counter_evidence_error", f"Graph omits counter-evidence for {claim_id}")
        if claim["status"] == "supported":
            current_support = [
                evidence[reference]
                for reference in claim["evidence_refs"]
                if reference in evidence
                and evidence[reference]["freshness"]["status"] == "current"
            ]
            if not current_support:
                _fail("freshness_error", f"supported Claim {claim_id} lacks current support")


def _validate_dependencies(
    graph: Mapping[str, Any],
    bundle: Mapping[str, Any],
    nodes: Mapping[str, dict[str, Any]],
    edges: Mapping[str, dict[str, Any]],
) -> None:
    index = graph["dependency_index"]
    required = {
        "record_hashes",
        "record_to_nodes",
        "record_to_edges",
        "node_to_edges",
        "node_to_perspectives",
        "node_to_parent_diagrams",
        "record_to_perspectives",
        "record_to_parent_diagrams",
    }
    _exact_keys(index, required, "graph.dependency_index")
    if index["record_hashes"] != record_hashes(bundle):
        _fail("dependency_error", "dependency record hashes do not match the Bundle")
    expected_node_edges: dict[str, list[str]] = defaultdict(list)
    for edge in edges.values():
        expected_node_edges[edge["from"]].append(edge["id"])
        expected_node_edges[edge["to"]].append(edge["id"])
    expected = {
        node_id: sorted(edge_ids)
        for node_id, edge_ids in sorted(expected_node_edges.items())
    }
    if index["node_to_edges"] != expected:
        _fail("dependency_error", "node_to_edges is incomplete or inconsistent")
    expected_record_nodes = _expected_record_dependencies(nodes.values())
    expected_record_edges = _expected_record_dependencies(edges.values())
    if index["record_to_nodes"] != expected_record_nodes:
        _fail("dependency_error", "record_to_nodes is incomplete or inconsistent")
    if index["record_to_edges"] != expected_record_edges:
        _fail("dependency_error", "record_to_edges is incomplete or inconsistent")
    _validate_dependency_map(
        index["node_to_perspectives"], set(PERSPECTIVES), "node_to_perspectives",
        key_ids=set(nodes),
    )
    _validate_dependency_map(
        index["node_to_parent_diagrams"], None, "node_to_parent_diagrams",
        key_ids=set(nodes),
    )
    _validate_dependency_map(
        index["record_to_perspectives"],
        set(PERSPECTIVES),
        "record_to_perspectives",
        key_ids=set(index["record_hashes"]),
    )
    _validate_dependency_map(
        index["record_to_parent_diagrams"],
        None,
        "record_to_parent_diagrams",
        key_ids=set(index["record_hashes"]),
    )


def _expected_record_dependencies(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, list[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for reference in record["source_refs"]:
            result[_dependency_key(reference)].add(record["id"])
    return {
        key: sorted(identifiers)
        for key, identifiers in sorted(result.items())
    }


def _dependency_key(reference: Mapping[str, str]) -> str:
    collection = reference["collection"]
    bundle_key = _COLLECTIONS[collection]
    if collection in _CONTROL_RECORD_IDS:
        return bundle_key
    return f"{bundle_key}:{reference['record_id']}"


def _validate_graph_perspective_refs(
    graph: Mapping[str, Any],
    nodes: Mapping[str, Any],
    edges: Mapping[str, Any],
) -> None:
    seen: set[str] = set()
    for index, item in enumerate(graph["perspectives"]):
        if isinstance(item, str):
            perspective_id = item
        elif isinstance(item, Mapping):
            perspective_id = item.get("id")
            for node_id in item.get("node_ids", []):
                if node_id not in nodes:
                    _fail("dead_link", f"graph perspective references missing node {node_id}")
            for edge_id in item.get("edge_ids", []):
                if edge_id not in edges:
                    _fail("dead_link", f"graph perspective references missing edge {edge_id}")
        else:
            _fail("perspective_error", f"graph.perspectives[{index}] is invalid")
        if perspective_id not in PERSPECTIVES or perspective_id in seen:
            _fail("perspective_error", f"invalid or duplicate Perspective {perspective_id!r}")
        seen.add(perspective_id)


def _validate_manifest_shape(manifest: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "bundle",
        "generated_from",
        "generation_policy",
        "contents",
        "integrity",
    }
    _exact_or_extension_keys(manifest, required, "Atlas manifest")
    if manifest["schema_version"] != ATLAS_MANIFEST_SCHEMA:
        _fail("schema_error", "unsupported Atlas manifest schema")
    _exact_keys(manifest["bundle"], {"id", "content_hash"}, "manifest.bundle")
    _nonempty_string(manifest["bundle"]["id"], "manifest.bundle.id")
    _sha256(manifest["bundle"]["content_hash"], "manifest.bundle.content_hash")
    _exact_keys(
        manifest["generated_from"],
        {"bundle_content_hash", "manifest_sha256", "index_sha256"},
        "manifest.generated_from",
    )
    for name, digest in manifest["generated_from"].items():
        _sha256(digest, f"manifest.generated_from.{name}")
    try:
        normalized = merge_policy(manifest["generation_policy"])
    except (TypeError, ValueError) as error:
        _fail("policy_error", str(error))
    if normalized != manifest["generation_policy"]:
        _fail("policy_error", "Atlas manifest must record the full generation policy")
    contents = manifest["contents"]
    _exact_keys(
        contents,
        {"graph", "nodes", "edges", "hierarchy", "diagnostics", "perspectives"},
        "manifest.contents",
    )
    for name in ("graph", "nodes", "edges", "hierarchy", "diagnostics"):
        _safe_relative(contents[name], f"manifest.contents.{name}")
    _string_array(contents["perspectives"], "manifest.contents.perspectives", unique=True)
    if not contents["perspectives"]:
        _fail("perspective_error", "Atlas manifest must declare at least one Perspective")
    if len(contents["perspectives"]) > len(PERSPECTIVES):
        _fail("perspective_error", "Atlas manifest declares too many Perspectives")
    for relative in contents["perspectives"]:
        _safe_relative(relative, "manifest.contents.perspectives")
    integrity = manifest["integrity"]
    _exact_keys(integrity, {"algorithm", "file_hashes"}, "manifest.integrity")
    if integrity["algorithm"] != "sha256":
        _fail("integrity_error", "Atlas sidecars must use SHA-256")
    _mapping(integrity["file_hashes"], "manifest.integrity.file_hashes")
    for relative, digest in integrity["file_hashes"].items():
        _safe_relative(relative, "manifest.integrity.file_hashes")
        _sha256(digest, f"manifest.integrity.file_hashes[{relative!r}]")


def _validate_manifest_identity(
    manifest: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> None:
    bundle_document = bundle["manifest"]["bundle"]
    if manifest["bundle"] != {
        "id": bundle_document["id"],
        "content_hash": bundle_document["content_hash"],
    }:
        _fail("bundle_identity_error", "Atlas manifest names a different Bundle")
    generated = manifest["generated_from"]
    expected = {
        "bundle_content_hash": bundle_document["content_hash"],
        "manifest_sha256": hashlib.sha256(
            _bundle_file(bundle, "manifest.json", bundle["manifest"])
        ).hexdigest(),
        "index_sha256": hashlib.sha256(
            _bundle_file(bundle, "index.json", bundle["index"])
        ).hexdigest(),
    }
    if generated != expected:
        _fail("bundle_identity_error", "Atlas manifest input identity is stale")


def _validate_sidecar_hashes(
    root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, bytes]:
    if not root.is_dir() or root.is_symlink():
        _fail("unsafe_path", "Atlas sidecar root must be a real directory")
    declared = manifest["integrity"]["file_hashes"]
    contents = manifest["contents"]
    required = {
        contents["graph"],
        contents["nodes"],
        contents["edges"],
        contents["hierarchy"],
        contents["diagnostics"],
        *contents["perspectives"],
    }
    if not required <= set(declared):
        missing = ", ".join(sorted(required - set(declared)))
        _fail("integrity_error", f"required Atlas sidecars lack hashes: {missing}")
    result: dict[str, bytes] = {}
    for relative, expected in declared.items():
        path = _safe_file(root, relative)
        try:
            raw = path.read_bytes()
        except OSError as error:
            _fail("sidecar_error", f"cannot read {relative}: {error}")
        if hashlib.sha256(raw).hexdigest() != expected:
            _fail("integrity_error", f"Atlas sidecar hash mismatch: {relative}")
        result[relative] = raw
    return result


def _validate_perspectives(
    documents: Sequence[dict[str, Any]],
    hierarchy: dict[str, Any],
    graph: Mapping[str, Any],
    files: Mapping[str, bytes],
    policy: Mapping[str, Any],
) -> None:
    nodes = {item["id"]: item for item in graph["nodes"]}
    edges = {item["id"]: item for item in graph["edges"]}
    by_id: dict[str, dict[str, Any]] = {}
    for document in documents:
        _validate_perspective_shape(document)
        perspective_id = document["id"]
        if perspective_id in by_id:
            _fail("perspective_error", f"duplicate Perspective {perspective_id}")
        by_id[perspective_id] = document
        for node_id in document["node_ids"]:
            if node_id not in nodes:
                _fail("dead_link", f"{perspective_id} references missing node {node_id}")
        for edge_id in document["edge_ids"]:
            if edge_id not in edges:
                _fail("dead_link", f"{perspective_id} references missing edge {edge_id}")
            edge = edges[edge_id]
            if edge["from"] not in document["node_ids"] or edge["to"] not in document["node_ids"]:
                _fail("dead_link", f"{perspective_id} edge endpoints are outside its node set")
        _validate_hashed_projection_files(document, files, policy)
    if not by_id:
        _fail("perspective_error", "Atlas must contain at least one fixed Perspective")
    if not set(by_id).issubset(PERSPECTIVES):
        _fail("perspective_error", "Atlas contains an unsupported Perspective")
    _validate_hierarchy(hierarchy, nodes, edges, by_id, policy)


def _validate_perspective_shape(value: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "id",
        "title",
        "root_diagram_ids",
        "node_ids",
        "edge_ids",
        "diagram",
        "documents",
    }
    _exact_or_extension_keys(value, required, "Perspective")
    if value["schema_version"] != PERSPECTIVE_SCHEMA:
        _fail("schema_error", "unsupported Perspective schema")
    if value["id"] not in PERSPECTIVES:
        _fail("perspective_error", f"unsupported Perspective {value['id']!r}")
    _nonempty_string(value["title"], "Perspective.title")
    _string_array(
        value["root_diagram_ids"],
        "Perspective.root_diagram_ids",
        unique=True,
    )
    if not value["root_diagram_ids"]:
        _fail("hierarchy_error", "Perspective requires at least one root diagram")
    _string_array(value["node_ids"], "Perspective.node_ids", unique=True)
    _string_array(value["edge_ids"], "Perspective.edge_ids", unique=True)
    diagram = value["diagram"]
    _exact_keys(diagram, {"type", "path", "sha256"}, "Perspective.diagram")
    if diagram["type"] not in _DIAGRAM_TYPES:
        _fail("perspective_error", "Perspective uses unsupported diagram type")
    _safe_relative(diagram["path"], "Perspective.diagram.path")
    _sha256(diagram["sha256"], "Perspective.diagram.sha256")
    _mapping(value["documents"], "Perspective.documents")
    required_documents = {
        "actions",
        "concerns",
        "constraints",
        "context",
        "counter_evidence",
        "description",
        "evidence",
        "freshness",
        "provenance",
        "question",
        "unknowns",
    }
    if not required_documents <= set(value["documents"]):
        _fail(
            "perspective_error",
            "Perspective must include every required documentation field",
        )
    if not value["diagram"]["path"].endswith(".mmd"):
        _fail("perspective_error", "Perspective diagram path must end in .mmd")
    for name, item in value["documents"].items():
        _nonempty_string(name, "Perspective document field")
        _exact_keys(item, {"path", "sha256"}, f"Perspective.documents.{name}")
        _safe_relative(item["path"], f"Perspective.documents.{name}.path")
        _sha256(item["sha256"], f"Perspective.documents.{name}.sha256")
    for name in required_documents - {"provenance"}:
        if not value["documents"][name]["path"].endswith(".md"):
            _fail("perspective_error", f"Perspective {name} path must end in .md")
    if not value["documents"]["provenance"]["path"].endswith(".json"):
        _fail("perspective_error", "Perspective provenance path must end in .json")


def _validate_hashed_projection_files(
    perspective: Mapping[str, Any],
    files: Mapping[str, bytes],
    policy: Mapping[str, Any],
) -> None:
    items = [perspective["diagram"], *perspective["documents"].values()]
    for item in items:
        relative = item["path"]
        raw = files.get(relative)
        if raw is None:
            _fail("dead_link", f"Perspective sidecar is unavailable or unhashed: {relative}")
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            _fail("integrity_error", f"Perspective sidecar hash mismatch: {relative}")
    try:
        diagram = files[perspective["diagram"]["path"]].decode("utf-8")
    except UnicodeDecodeError:
        _fail("mermaid_error", "diagram.mmd must be UTF-8")
    validate_mermaid(diagram, label=perspective["diagram"]["path"])
    diagram_path = PurePosixPath(perspective["diagram"]["path"])
    ir_path = str(diagram_path.with_name("diagram-ir.json"))
    ir = _decode_json(files.get(ir_path), ir_path)
    if not isinstance(ir, dict) or not isinstance(ir.get("nodes"), list):
        _fail("perspective_error", f"invalid Diagram IR: {ir_path}")
    if len(ir["nodes"]) > policy["max_nodes_per_diagram"]:
        _fail(
            "budget_error",
            f"{perspective['id']} root diagram exceeds max_nodes_per_diagram",
        )


def _validate_hierarchy(
    hierarchy: Mapping[str, Any],
    nodes: Mapping[str, Any],
    edges: Mapping[str, Any],
    perspectives: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> None:
    _exact_or_extension_keys(
        hierarchy,
        {"schema_version", "diagrams"},
        "hierarchy",
    )
    if hierarchy["schema_version"] != "aet-evidence-hierarchy/1.0":
        _fail("schema_error", "unsupported hierarchy schema")
    _array(hierarchy["diagrams"], "hierarchy.diagrams")
    diagrams: dict[str, Mapping[str, Any]] = {}
    child_count: dict[str, int] = defaultdict(int)
    for index, raw in enumerate(hierarchy["diagrams"]):
        label = f"hierarchy.diagrams[{index}]"
        _mapping(raw, label)
        required = {
            "id",
            "perspective_id",
            "root_node_id",
            "parent_diagram_id",
            "depth",
            "node_ids",
            "edge_ids",
            "child_diagram_ids",
            "reference_node_ids",
        }
        _exact_or_extension_keys(raw, required, label)
        diagram_id = _nonempty_string(raw["id"], f"{label}.id")
        if diagram_id in diagrams:
            _fail("hierarchy_error", f"duplicate diagram ID {diagram_id}")
        if raw["perspective_id"] not in perspectives:
            _fail("dead_link", f"{diagram_id} references an unknown Perspective")
        if raw["root_node_id"] not in nodes:
            _fail("dead_link", f"{diagram_id} references a missing root node")
        if not _plain_int(raw["depth"]) or raw["depth"] < 0:
            _fail("hierarchy_error", f"{diagram_id} has invalid depth")
        if raw["depth"] > policy["max_depth"]:
            _fail("budget_error", f"{diagram_id} exceeds max_depth")
        _string_array(raw["node_ids"], f"{label}.node_ids", unique=True)
        _string_array(raw["edge_ids"], f"{label}.edge_ids", unique=True)
        _string_array(
            raw["child_diagram_ids"], f"{label}.child_diagram_ids", unique=True
        )
        _string_array(
            raw["reference_node_ids"], f"{label}.reference_node_ids", unique=True
        )
        if len(raw["node_ids"]) > policy["max_nodes_per_diagram"]:
            _fail("budget_error", f"{diagram_id} exceeds max_nodes_per_diagram")
        if len(raw["child_diagram_ids"]) > policy["max_children_per_node"]:
            _fail("budget_error", f"{diagram_id} exceeds max_children_per_node")
        if raw["root_node_id"] not in raw["node_ids"]:
            _fail("hierarchy_error", f"{diagram_id} omits its root from node_ids")
        for node_id in [*raw["node_ids"], *raw["reference_node_ids"]]:
            if node_id not in nodes:
                _fail("dead_link", f"{diagram_id} references missing node {node_id}")
        for edge_id in raw["edge_ids"]:
            if edge_id not in edges:
                _fail("dead_link", f"{diagram_id} references missing edge {edge_id}")
        diagrams[diagram_id] = raw
    if len(diagrams) > policy["max_total_diagrams"]:
        _fail("budget_error", "hierarchy exceeds max_total_diagrams")
    for diagram_id, diagram in diagrams.items():
        parent = diagram["parent_diagram_id"]
        if parent is not None:
            if parent not in diagrams:
                _fail("dead_link", f"{diagram_id} references missing parent diagram")
            child_count[parent] += 1
            if diagram_id not in diagrams[parent]["child_diagram_ids"]:
                _fail("hierarchy_error", f"{diagram_id} is absent from its parent child list")
            if diagram["depth"] != diagrams[parent]["depth"] + 1:
                _fail("hierarchy_error", f"{diagram_id} depth disagrees with its parent")
            if diagram["perspective_id"] != diagrams[parent]["perspective_id"]:
                _fail("hierarchy_error", f"{diagram_id} crosses Perspective ownership")
        for child in diagram["child_diagram_ids"]:
            if child not in diagrams:
                _fail("dead_link", f"{diagram_id} references missing child diagram {child}")
            if diagrams[child]["parent_diagram_id"] != diagram_id:
                _fail("hierarchy_error", f"{diagram_id} child link is not bidirectional")
        if child_count[diagram_id] > policy["max_children_per_node"]:
            _fail("budget_error", f"{diagram_id} exceeds max_children_per_node")
    for perspective in perspectives.values():
        for root_id in perspective["root_diagram_ids"]:
            if root_id not in diagrams:
                _fail("dead_link", f"{perspective['id']} root diagram is unavailable")
            if diagrams[root_id]["parent_diagram_id"] is not None:
                _fail("hierarchy_error", f"{perspective['id']} root diagram has a parent")
            if diagrams[root_id]["perspective_id"] != perspective["id"]:
                _fail("hierarchy_error", f"{perspective['id']} root diagram belongs elsewhere")
    _detect_hierarchy_cycles(diagrams)
    reachable: set[str] = set()

    def collect(identifier: str) -> None:
        if identifier in reachable:
            return
        reachable.add(identifier)
        for child in diagrams[identifier]["child_diagram_ids"]:
            collect(child)

    for perspective in perspectives.values():
        for root_id in perspective["root_diagram_ids"]:
            collect(root_id)
    if reachable != set(diagrams):
        _fail("hierarchy_error", "hierarchy contains diagrams unreachable from a Perspective root")


def _detect_hierarchy_cycles(diagrams: Mapping[str, Mapping[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            _fail("hierarchy_error", f"recursive diagram cycle detected at {identifier}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for child in diagrams[identifier]["child_diagram_ids"]:
            visit(child)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in diagrams:
        visit(identifier)


def _validate_complexity(value: Any, node_id: str) -> None:
    _exact_keys(value, {"score", "classification", "reasons"}, f"{node_id}.complexity")
    score = value["score"]
    if not _plain_int(score) or score < 0:
        _fail("complexity_error", f"{node_id} complexity score must be non-negative")
    expected = (
        "mandatory_decomposition"
        if score >= 8
        else ("expandable" if score >= 4 else "leaf")
    )
    if value["classification"] not in _CLASSIFICATIONS or value["classification"] != expected:
        _fail("complexity_error", f"{node_id} complexity classification is inconsistent")
    _string_array(value["reasons"], f"{node_id}.complexity.reasons", unique=True)


def _validate_source_refs(
    value: Any,
    records: Mapping[tuple[str, str], Any],
    label: str,
) -> None:
    _array(value, label)
    if not value:
        _fail("source_ref_error", f"{label} must not be empty")
    seen: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(value):
        item_label = f"{label}[{index}]"
        _exact_keys(raw, {"collection", "record_id", "field"}, item_label)
        collection = _nonempty_string(raw["collection"], f"{item_label}.collection")
        record_id = _nonempty_string(raw["record_id"], f"{item_label}.record_id")
        field = _nonempty_string(raw["field"], f"{item_label}.field")
        if collection not in _COLLECTIONS:
            _fail("source_ref_error", f"{item_label} names an unsupported collection")
        key = (collection, record_id)
        if key not in records:
            _fail("source_ref_error", f"{item_label} references a missing record")
        _resolve_field(records[key], field, item_label)
        identity = (collection, record_id, field)
        if identity in seen:
            _fail("source_ref_error", f"{label} contains a duplicate field reference")
        seen.add(identity)


def _validate_reference_edge_target(
    edge: Mapping[str, Any],
    bundle: Mapping[str, Any],
    nodes: Mapping[str, dict[str, Any]],
) -> None:
    """Prove that authoritative relationship fields name the actual target."""
    contracts = {
        "SUPPORTED_BY": ("core/claims.jsonl", "evidence_refs", "verified_evidence"),
        "PARTIALLY_SUPPORTED_BY": (
            "core/claims.jsonl",
            "evidence_refs",
            "verified_evidence",
        ),
        "OBSERVED_IN": (
            "core/claims.jsonl",
            "observation_refs",
            "observation",
        ),
        "VALIDATES": ("core/evidence.jsonl", "supports", "claim"),
    }
    contract = contracts.get(edge["type"])
    if contract is None:
        if edge["type"] != "CONTRADICTED_BY":
            return
        source_type = nodes[edge["from"]]["type"]
        contract = (
            (
                "core/claims.jsonl",
                "counter_evidence_refs",
                "verified_evidence",
            )
            if source_type in {"claim", "subclaim"}
            else (
                "archive/conflicts.jsonl",
                "evidence_refs",
                "verified_evidence",
            )
        )
    collection, field, target_type = contract
    matching = [
        reference
        for reference in edge["source_refs"]
        if reference["collection"] == collection
        and reference["field"] == field
    ]
    if len(matching) != 1:
        _fail(
            "authority_error",
            f"{edge['id']} must cite exactly one {collection}:{field} field",
        )
    target = nodes[edge["to"]]
    if target["type"] != target_type:
        _fail(
            "authority_error",
            f"{edge['id']} target type does not match {collection}:{field}",
        )
    record = _bundle_record(bundle, collection, matching[0]["record_id"])
    values = _resolve_field(record, field, edge["id"])
    target_record_ids = {
        reference["record_id"]
        for reference in target["source_refs"]
        if reference["collection"]
        in {
            "core/evidence.jsonl",
            "core/claims.jsonl",
            "core/observations.jsonl",
            "archive/conflicts.jsonl",
        }
    }
    if (
        not isinstance(values, list)
        or len(target_record_ids) != 1
        or next(iter(target_record_ids)) not in values
    ):
        _fail(
            "authority_error",
            f"{edge['id']} target is not named by its cited Bundle field",
        )


def _validate_required_bundle_edges(
    bundle: Mapping[str, Any],
    nodes: Mapping[str, dict[str, Any]],
    edges: Mapping[str, dict[str, Any]],
) -> None:
    """Reject graphs that omit or alter authoritative Claim relationships."""
    node_by_record: dict[tuple[str, str, str], str] = {}
    for node in nodes.values():
        for reference in node["source_refs"]:
            node_by_record.setdefault(
                (
                    node["type"],
                    reference["collection"],
                    reference["record_id"],
                ),
                node["id"],
            )
    actual = {
        (edge["from"], edge["to"], edge["type"])
        for edge in edges.values()
    }
    evidence = {item["id"]: item for item in bundle["evidence"]}
    for claim in bundle["claims"]:
        claim_id = node_by_record.get(
            ("claim", "core/claims.jsonl", claim["id"])
        )
        if claim_id is None:
            _fail("authority_error", f"Claim node is missing for {claim['id']}")
        for evidence_id in claim["evidence_refs"]:
            target_id = node_by_record.get(
                ("verified_evidence", "core/evidence.jsonl", evidence_id)
            )
            item = evidence.get(evidence_id)
            if target_id is None or item is None:
                continue
            relation = (
                "SUPPORTED_BY"
                if claim["status"] != "partially_supported"
                and item["freshness"]["status"] == "current"
                else "PARTIALLY_SUPPORTED_BY"
            )
            if (claim_id, target_id, relation) not in actual:
                _fail(
                    "authority_error",
                    f"graph omits required {relation} edge for {claim['id']} -> {evidence_id}",
                )
        for evidence_id in claim["counter_evidence_refs"]:
            target_id = node_by_record.get(
                ("verified_evidence", "core/evidence.jsonl", evidence_id)
            )
            if target_id is not None and (
                claim_id,
                target_id,
                "CONTRADICTED_BY",
            ) not in actual:
                _fail(
                    "counter_evidence_error",
                    f"graph omits counter-evidence edge for {claim['id']} -> {evidence_id}",
                )
        for observation_id in claim["observation_refs"]:
            target_id = node_by_record.get(
                (
                    "observation",
                    "core/observations.jsonl",
                    observation_id,
                )
            )
            if target_id is not None and (
                claim_id,
                target_id,
                "OBSERVED_IN",
            ) not in actual:
                _fail(
                    "observation_boundary_error",
                    f"graph omits Observation edge for {claim['id']} -> {observation_id}",
                )


def _bundle_record(
    bundle: Mapping[str, Any], collection: str, record_id: str
) -> Mapping[str, Any]:
    bundle_key = _COLLECTIONS[collection]
    for item in bundle[bundle_key]:
        if item["id"] == record_id:
            return item
    _fail("source_ref_error", f"missing Bundle record {collection}:{record_id}")


def _record_index(bundle: Mapping[str, Any]) -> dict[tuple[str, str], Any]:
    result: dict[tuple[str, str], Any] = {}
    for collection, bundle_key in _COLLECTIONS.items():
        value = bundle.get(bundle_key)
        if collection in _CONTROL_RECORD_IDS:
            if not isinstance(value, Mapping):
                _fail("source_ref_error", f"Bundle is missing {bundle_key}")
            result[(collection, _CONTROL_RECORD_IDS[collection])] = value
            continue
        if not isinstance(value, list):
            _fail("source_ref_error", f"Bundle collection {bundle_key} is invalid")
        for item in value:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                _fail("source_ref_error", f"Bundle collection {bundle_key} has invalid record")
            key = (collection, item["id"])
            if key in result:
                _fail("source_ref_error", f"duplicate Bundle record {item['id']}")
            result[key] = item
    return result


def _resolve_field(record: Any, field: str, label: str) -> Any:
    current = record
    for raw_part in field.split("."):
        match = _FIELD_PART.fullmatch(raw_part)
        if match is None:
            _fail("source_ref_error", f"{label} has invalid field path {field!r}")
        key, index_text = match.groups()
        if not isinstance(current, Mapping) or key not in current:
            _fail("source_ref_error", f"{label} field does not exist: {field}")
        current = current[key]
        if index_text is not None:
            index = int(index_text)
            if (
                not isinstance(current, list)
                or index >= len(current)
            ):
                _fail("source_ref_error", f"{label} field index does not exist: {field}")
            current = current[index]
    return current


def _nodes_by_record(
    nodes: Mapping[str, dict[str, Any]],
    collection: str,
    node_type: str | None = None,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in nodes.values():
        if node_type is not None and node["type"] != node_type:
            continue
        for reference in node["source_refs"]:
            if reference["collection"] == collection:
                result.setdefault(reference["record_id"], node)
    return result


def _validate_dependency_map(
    value: Any,
    allowed_values: set[str] | None,
    label: str,
    *,
    key_ids: set[str] | None = None,
) -> None:
    _mapping(value, f"dependency_index.{label}")
    for key, raw_values in value.items():
        _nonempty_string(key, f"dependency_index.{label} key")
        if key_ids is not None and key not in key_ids:
            _fail("dependency_error", f"{label} names missing node {key}")
        _string_array(raw_values, f"dependency_index.{label}[{key!r}]", unique=True)
        if allowed_values is not None and not set(raw_values) <= allowed_values:
            _fail("dependency_error", f"{label} contains an unavailable reference")


def _bundle_file(bundle: Mapping[str, Any], name: str, fallback: Any) -> bytes:
    files = bundle.get("_files")
    if isinstance(files, Mapping) and isinstance(files.get(name), bytes):
        return files[name]
    root = bundle.get("root")
    if isinstance(root, str):
        try:
            return (Path(root) / name).read_bytes()
        except OSError:
            pass
    return json.dumps(
        fallback,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        _fail("sidecar_error", f"cannot read {label}: {error}")
    value = _decode_json(raw, label)
    if not isinstance(value, dict):
        _fail("sidecar_error", f"{label} must contain one JSON object")
    return value


def _decode_json(raw: bytes, label: str) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("sidecar_error", f"{label} must be UTF-8")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("sidecar_error", f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        _fail("sidecar_error", f"{label} contains non-finite number {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=unique,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as error:
        _fail("sidecar_error", f"{label} is invalid JSON: {error}")


def _decode_jsonl(raw: bytes, label: str) -> list[dict[str, Any]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("sidecar_error", f"{label} must be UTF-8")
    result: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        value = _decode_json(line.encode("utf-8"), f"{label}:{number}")
        if not isinstance(value, dict):
            _fail("sidecar_error", f"{label}:{number} must contain one object")
        result.append(value)
    return result


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        _fail("unsafe_path", f"{label} must be a normalized relative path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("unsafe_path", f"{label} must be a normalized relative path")
    return value


def _safe_file(root: Path, relative_value: str) -> Path:
    relative = PurePosixPath(_safe_relative(relative_value, "sidecar path"))
    current = root
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError:
            _fail("dead_link", f"Atlas sidecar is unavailable: {relative_value}")
        if stat.S_ISLNK(mode):
            _fail("unsafe_path", f"Atlas sidecar cannot be a symlink: {relative_value}")
    if not stat.S_ISREG(current.lstat().st_mode):
        _fail("sidecar_error", f"Atlas sidecar is not a regular file: {relative_value}")
    try:
        current.resolve(strict=True).relative_to(root)
    except (OSError, ValueError):
        _fail("unsafe_path", f"Atlas sidecar escapes its root: {relative_value}")
    return current


def _exact_keys(value: Any, expected: set[str], label: str) -> None:
    _mapping(value, label)
    if set(value) != expected:
        _fail(
            "schema_error",
            f"{label} must contain exactly: {', '.join(sorted(expected))}",
        )


def _exact_or_extension_keys(value: Any, required: set[str], label: str) -> None:
    _mapping(value, label)
    allowed = required | {"extensions"}
    if not required <= set(value) or not set(value) <= allowed:
        _fail(
            "schema_error",
            f"{label} has missing or unsupported fields",
        )
    if "extensions" in value:
        _mapping(value["extensions"], f"{label}.extensions")


def _mapping(value: Any, label: str) -> None:
    if not isinstance(value, Mapping):
        _fail("schema_error", f"{label} must be an object")


def _array(value: Any, label: str) -> None:
    if not isinstance(value, list):
        _fail("schema_error", f"{label} must be an array")


def _string_array(value: Any, label: str, *, unique: bool) -> None:
    _array(value, label)
    if not all(isinstance(item, str) and item for item in value):
        _fail("schema_error", f"{label} must contain non-empty strings")
    if unique and len(value) != len(set(value)):
        _fail("schema_error", f"{label} must contain unique strings")


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("schema_error", f"{label} must be a non-empty string")
    return value


def _sha256(value: Any, label: str) -> None:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        _fail("integrity_error", f"{label} must be a lowercase SHA-256 digest")


def _plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _fail(code: str, message: str) -> None:
    raise AtlasValidationError(code, message)
