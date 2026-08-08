"""Fail-closed semantic validation for Review Graph v1."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .errors import ReviewGraphError
from .model import (
    CODE_GRAPH_SCHEMA,
    MANDATORY_ROOT_KINDS,
    REVIEW_GRAPH_SCHEMA,
    REVIEW_MANIFEST_SCHEMA,
    REVIEW_SLICE_SCHEMA,
    STATES,
    canonical_json_bytes,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_code_graph(value: Mapping[str, Any]) -> dict[str, Any]:
    graph = _object(value, "code graph")
    _exact_keys(
        graph,
        {"schema_version", "snapshot", "index", "nodes", "edges", "diagnostics"},
        "code graph",
    )
    _const(graph["schema_version"], CODE_GRAPH_SCHEMA, "code graph schema_version")
    _snapshot(graph["snapshot"])
    index = _object(graph["index"], "code graph index")
    _require_keys(
        index,
        {"language", "base_ref", "coverage_status", "file_count", "symbol_count"},
        "code graph index",
    )
    _state(index["coverage_status"], "code graph coverage_status")
    _graph_records(graph["nodes"], graph["edges"], "code graph")
    _diagnostics(graph["diagnostics"])
    return dict(graph)


def validate_review_graph(value: Mapping[str, Any]) -> dict[str, Any]:
    graph = _object(value, "review graph")
    _exact_keys(
        graph,
        {
            "schema_version",
            "snapshot",
            "task",
            "code_index",
            "evidence_binding",
            "nodes",
            "edges",
            "diagnostics",
        },
        "review graph",
    )
    _const(graph["schema_version"], REVIEW_GRAPH_SCHEMA, "review graph schema_version")
    _snapshot(graph["snapshot"])
    task = _object(graph["task"], "review graph task")
    _require_keys(task, {"id", "request", "authority"}, "review graph task")
    _nonempty(task["id"], "review graph task id")
    _nonempty(task["request"], "review graph task request")
    _nonempty(task["authority"], "review graph task authority")
    for label in ("code_index", "evidence_binding"):
        binding = _object(graph[label], f"review graph {label}")
        _require_keys(binding, {"status", "sha256"}, f"review graph {label}")
        _state(binding["status"], f"review graph {label} status")
        _sha(binding["sha256"], f"review graph {label} sha256")
    _graph_records(graph["nodes"], graph["edges"], "review graph")
    _diagnostics(graph["diagnostics"])
    return dict(graph)


def validate_review_slice(value: Mapping[str, Any]) -> dict[str, Any]:
    review_slice = _object(value, "review slice")
    _exact_keys(
        review_slice,
        {"schema_version", "mode", "status", "snapshot", "nodes", "edges", "cut"},
        "review slice",
    )
    _const(review_slice["schema_version"], REVIEW_SLICE_SCHEMA, "review slice schema_version")
    if review_slice["mode"] not in {"root", "expand", "stale"}:
        raise ReviewGraphError("invalid_schema", "review slice mode is unsupported")
    _state(review_slice["status"], "review slice status")
    snapshot = _object(review_slice["snapshot"], "review slice snapshot")
    _require_keys(snapshot, {"state", "recorded_digest", "current_digest"}, "review slice snapshot")
    if snapshot["state"] not in {"EXACT_MATCH", "STALE", "UNKNOWN"}:
        raise ReviewGraphError("invalid_schema", "review slice snapshot state is unsupported")
    for field in ("recorded_digest", "current_digest"):
        value_or_none = snapshot[field]
        if value_or_none is not None:
            _sha(value_or_none, f"review slice snapshot {field}")

    nodes = _array(review_slice["nodes"], "review slice nodes")
    node_ids: set[str] = set()
    kinds: set[str] = set()
    for item in nodes:
        node = _object(item, "review slice node")
        _require_keys(node, {"id", "kind", "state", "authority", "text", "refs"}, "review slice node")
        identifier = _nonempty(node["id"], "review slice node id")
        if identifier in node_ids:
            raise ReviewGraphError("duplicate_id", f"duplicate review slice node: {identifier}")
        node_ids.add(identifier)
        kinds.add(_nonempty(node["kind"], "review slice node kind"))
        _state(node["state"], "review slice node state")
        _nonempty(node["authority"], "review slice node authority")
        _nonempty(node["text"], "review slice node text")
        refs = _array(node["refs"], "review slice node refs")
        if not all(isinstance(ref, str) and ref for ref in refs):
            raise ReviewGraphError("invalid_schema", "review slice refs must be non-empty strings")
        if "limitations" in node:
            limitations = _array(node["limitations"], "review slice node limitations")
            if not all(isinstance(item, str) and item for item in limitations):
                raise ReviewGraphError(
                    "invalid_schema",
                    "review slice limitations must be non-empty strings",
                )

    edges = _array(review_slice["edges"], "review slice edges")
    for item in edges:
        if not isinstance(item, list) or len(item) != 3 or not all(
            isinstance(part, str) and part for part in item
        ):
            raise ReviewGraphError("invalid_schema", "review slice edges must be string triples")
        if item[0] not in node_ids or item[2] not in node_ids:
            raise ReviewGraphError("dangling_reference", "review slice edge references an omitted node")

    cut = _object(review_slice["cut"], "review slice cut")
    _exact_keys(cut, {"truncated", "omitted_nodes", "omitted_edges", "expandable"}, "review slice cut")
    if not isinstance(cut["truncated"], bool):
        raise ReviewGraphError("invalid_schema", "review slice cut.truncated must be boolean")
    for field in ("omitted_nodes", "omitted_edges"):
        if not isinstance(cut[field], int) or isinstance(cut[field], bool) or cut[field] < 0:
            raise ReviewGraphError("invalid_schema", f"review slice cut.{field} must be non-negative")
    expandable = _array(cut["expandable"], "review slice cut.expandable")
    if not all(isinstance(item, str) and item in node_ids for item in expandable):
        raise ReviewGraphError("dangling_reference", "expandable nodes must be present in the slice")

    if review_slice["mode"] == "root":
        missing = sorted(MANDATORY_ROOT_KINDS - kinds)
        if missing:
            raise ReviewGraphError(
                "incomplete_review_contract",
                "root slice is missing mandatory kinds: " + ", ".join(missing),
            )
    if review_slice["mode"] == "stale":
        if review_slice["status"] != "UNKNOWN" or "stop_condition" not in kinds:
            raise ReviewGraphError(
                "stale_snapshot",
                "stale slices must remain UNKNOWN and include a stop condition",
            )
    canonical_json_bytes(review_slice)
    return dict(review_slice)


def validate_review_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _object(value, "review manifest")
    _exact_keys(
        manifest,
        {"schema_version", "package_id", "snapshot", "inputs", "contents", "integrity"},
        "review manifest",
    )
    _const(manifest["schema_version"], REVIEW_MANIFEST_SCHEMA, "review manifest schema_version")
    _nonempty(manifest["package_id"], "review manifest package_id")
    _snapshot(manifest["snapshot"])
    inputs = _object(manifest["inputs"], "review manifest inputs")
    _require_keys(inputs, {"bundle", "improvements", "base_ref"}, "review manifest inputs")
    for key in ("bundle", "improvements"):
        item = _object(inputs[key], f"review manifest input {key}")
        _require_keys(item, {"sha256"}, f"review manifest input {key}")
        _sha(item["sha256"], f"review manifest input {key} sha256")
    _nonempty(inputs["base_ref"], "review manifest base_ref")
    contents = _object(manifest["contents"], "review manifest contents")
    if not contents:
        raise ReviewGraphError("invalid_schema", "review manifest contents cannot be empty")
    integrity = _object(manifest["integrity"], "review manifest integrity")
    _exact_keys(integrity, {"algorithm", "file_hashes"}, "review manifest integrity")
    _const(integrity["algorithm"], "sha256", "review manifest integrity algorithm")
    hashes = _object(integrity["file_hashes"], "review manifest file hashes")
    if set(hashes) != set(contents.values()):
        raise ReviewGraphError("integrity_error", "manifest hashes must cover every declared content file")
    for path, digest in hashes.items():
        _safe_relative(path)
        _sha(digest, f"review manifest hash for {path}")
    return dict(manifest)


def _graph_records(raw_nodes: Any, raw_edges: Any, label: str) -> None:
    nodes = _array(raw_nodes, f"{label} nodes")
    edges = _array(raw_edges, f"{label} edges")
    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    for raw in nodes:
        node = _object(raw, f"{label} node")
        _exact_keys(
            node,
            {"id", "kind", "state", "authority", "text", "source_refs", "attributes", "mandatory", "priority"},
            f"{label} node",
        )
        identifier = _nonempty(node["id"], f"{label} node id")
        if identifier in node_ids:
            raise ReviewGraphError("duplicate_id", f"duplicate node: {identifier}")
        node_ids.add(identifier)
        _nonempty(node["kind"], f"{label} node kind")
        _state(node["state"], f"{label} node state")
        _nonempty(node["authority"], f"{label} node authority")
        _nonempty(node["text"], f"{label} node text")
        _source_refs(node["source_refs"], f"{label} node source_refs")
        _object(node["attributes"], f"{label} node attributes")
        if not isinstance(node["mandatory"], bool):
            raise ReviewGraphError("invalid_schema", f"{label} node mandatory must be boolean")
        _priority(node["priority"], f"{label} node priority")
    for raw in edges:
        edge = _object(raw, f"{label} edge")
        _exact_keys(
            edge,
            {"id", "from", "to", "relation", "state", "authority", "source_refs", "attributes", "priority"},
            f"{label} edge",
        )
        identifier = _nonempty(edge["id"], f"{label} edge id")
        if identifier in edge_ids:
            raise ReviewGraphError("duplicate_id", f"duplicate edge: {identifier}")
        edge_ids.add(identifier)
        source = _nonempty(edge["from"], f"{label} edge from")
        target = _nonempty(edge["to"], f"{label} edge to")
        if source not in node_ids or target not in node_ids:
            raise ReviewGraphError("dangling_reference", f"edge {identifier} references an unknown node")
        _nonempty(edge["relation"], f"{label} edge relation")
        _state(edge["state"], f"{label} edge state")
        _nonempty(edge["authority"], f"{label} edge authority")
        _source_refs(edge["source_refs"], f"{label} edge source_refs")
        _object(edge["attributes"], f"{label} edge attributes")
        _priority(edge["priority"], f"{label} edge priority")


def _snapshot(raw: Any) -> None:
    value = _object(raw, "snapshot")
    _require_keys(value, {"status", "head_sha", "worktree_digest", "digest"}, "snapshot")
    _state(value["status"], "snapshot status")
    head = value["head_sha"]
    if not isinstance(head, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head) is None:
        raise ReviewGraphError("invalid_schema", "snapshot head_sha must be a Git object ID")
    for field in ("worktree_digest", "digest"):
        _sha(value[field], f"snapshot {field}")


def _source_refs(raw: Any, label: str) -> None:
    refs = _array(raw, label)
    if not refs:
        raise ReviewGraphError("missing_source", f"{label} cannot be empty")
    for raw_ref in refs:
        ref = _object(raw_ref, label)
        _require_keys(ref, {"kind", "ref"}, label)
        _nonempty(ref["kind"], f"{label} kind")
        _nonempty(ref["ref"], f"{label} ref")


def _diagnostics(raw: Any) -> None:
    diagnostics = _array(raw, "diagnostics")
    for raw_item in diagnostics:
        item = _object(raw_item, "diagnostic")
        _require_keys(item, {"code", "status", "message", "refs"}, "diagnostic")
        _nonempty(item["code"], "diagnostic code")
        _state(item["status"], "diagnostic status")
        _nonempty(item["message"], "diagnostic message")
        refs = _array(item["refs"], "diagnostic refs")
        if not all(isinstance(ref, str) and ref for ref in refs):
            raise ReviewGraphError("invalid_schema", "diagnostic refs must be strings")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewGraphError("invalid_schema", f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReviewGraphError("invalid_schema", f"{label} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ReviewGraphError(
            "invalid_schema",
            f"{label} keys differ; missing={missing}, extra={extra}",
        )


def _require_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - set(value))
    if missing:
        raise ReviewGraphError("invalid_schema", f"{label} is missing: {', '.join(missing)}")


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReviewGraphError("invalid_schema", f"{label} must be a non-empty string")
    return value


def _const(value: Any, expected: str, label: str) -> None:
    if value != expected:
        raise ReviewGraphError("invalid_schema", f"{label} must equal {expected}")


def _state(value: Any, label: str) -> None:
    if value not in STATES:
        raise ReviewGraphError("invalid_schema", f"{label} is unsupported")


def _priority(value: Any, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
        raise ReviewGraphError("invalid_schema", f"{label} must be between 0 and 100")


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ReviewGraphError("invalid_schema", f"{label} must be lowercase SHA-256")


def _safe_relative(value: Any) -> None:
    path = _nonempty(value, "content path")
    if path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ReviewGraphError("unsafe_path", f"unsafe review package path: {path}")
