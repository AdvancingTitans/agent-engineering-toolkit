"""Bounded Review Graph slices for Agent consumption."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from .errors import ReviewGraphError
from .model import GraphLimits, REVIEW_SLICE_SCHEMA, canonical_json_bytes, stable_id
from .validator import validate_review_graph, validate_review_slice


def build_root_slice(
    graph: dict[str, Any],
    *,
    limits: GraphLimits = GraphLimits(),
    current_digest: str | None = None,
) -> dict[str, Any]:
    """Return one safety-complete root slice; optional context is trimmed first."""
    validate_review_graph(graph)
    limits.validate()
    recorded = graph["snapshot"]["digest"]
    if current_digest is not None and current_digest != recorded:
        return build_stale_slice(graph, current_digest)

    nodes_by_id = {node["id"]: node for node in graph["nodes"]}
    mandatory = {node["id"] for node in graph["nodes"] if node["mandatory"]}
    changed = {
        node["id"]
        for node in graph["nodes"]
        if node["kind"] in {"file", "function", "method", "class", "test"}
        and node["attributes"].get("changed") is True
    }
    selected = set(mandatory) | changed
    selected.update(_direct_neighbors(graph, changed, {"CONTAINS", "CALLS", "MAY_CALL", "TESTS", "IMPORTS", "INHERITS"}))
    selected = _fit_nodes(graph, selected, mandatory, limits)
    return _slice(graph, selected, mode="root", limits=limits, current_digest=recorded)


def expand_slice(
    graph: dict[str, Any],
    node_id: str,
    *,
    relations: Iterable[str] = (),
    limits: GraphLimits = GraphLimits(max_nodes=12, max_edges=20, max_bytes=6_000),
    current_digest: str | None = None,
) -> dict[str, Any]:
    """Expand one node by one hop without returning the unbounded graph."""
    validate_review_graph(graph)
    limits.validate()
    recorded = graph["snapshot"]["digest"]
    if current_digest is not None and current_digest != recorded:
        return build_stale_slice(graph, current_digest)
    node_ids = {node["id"] for node in graph["nodes"]}
    if node_id not in node_ids:
        raise ReviewGraphError("unknown_node", f"unknown Review Graph node: {node_id}")
    relation_set = {item for item in relations if item}
    selected = {node_id} | _direct_neighbors(graph, {node_id}, relation_set)
    selected = _fit_nodes(graph, selected, {node_id}, limits)
    return _slice(graph, selected, mode="expand", limits=limits, current_digest=recorded)


def build_stale_slice(graph: dict[str, Any], current_digest: str | None) -> dict[str, Any]:
    recorded = graph["snapshot"]["digest"]
    stop_id = stable_id("review:stop", "stale", recorded, current_digest)
    result = {
        "schema_version": REVIEW_SLICE_SCHEMA,
        "mode": "stale",
        "status": "UNKNOWN",
        "snapshot": {
            "state": "STALE" if current_digest is not None else "UNKNOWN",
            "recorded_digest": recorded,
            "current_digest": current_digest,
        },
        "nodes": [
            {
                "id": stop_id,
                "kind": "stop_condition",
                "state": "UNKNOWN",
                "authority": "snapshot_guard",
                "text": "Stop implementation: the Review Graph snapshot does not match the current workspace. Rebuild the package.",
                "refs": ["manifest.json#snapshot"],
            }
        ],
        "edges": [],
        "cut": {
            "truncated": False,
            "omitted_nodes": len(graph["nodes"]),
            "omitted_edges": len(graph["edges"]),
            "expandable": [],
        },
    }
    return validate_review_slice(result)


def _fit_nodes(
    graph: dict[str, Any],
    selected: set[str],
    required: set[str],
    limits: GraphLimits,
) -> set[str]:
    by_id = {node["id"]: node for node in graph["nodes"]}
    if len(required) > limits.max_nodes:
        raise ReviewGraphError(
            "context_limit",
            f"mandatory safety nodes exceed max_nodes: {len(required)} > {limits.max_nodes}",
        )
    ordered_optional = sorted(
        selected - required,
        key=lambda identifier: (-by_id[identifier]["priority"], identifier),
    )
    fitted = set(required)
    fitted.update(ordered_optional[: max(0, limits.max_nodes - len(fitted))])
    return fitted


def _slice(
    graph: dict[str, Any],
    selected: set[str],
    *,
    mode: str,
    limits: GraphLimits,
    current_digest: str,
) -> dict[str, Any]:
    by_id = {node["id"]: node for node in graph["nodes"]}
    required = {identifier for identifier in selected if by_id[identifier]["mandatory"]}
    while True:
        edges = [
            edge
            for edge in graph["edges"]
            if edge["from"] in selected and edge["to"] in selected
        ]
        edges = sorted(edges, key=lambda item: (-item["priority"], item["id"]))
        mandatory_edges = [
            edge for edge in edges if edge["from"] in required and edge["to"] in required
        ]
        if len(mandatory_edges) > limits.max_edges:
            raise ReviewGraphError(
                "context_limit",
                "mandatory safety relations exceed max_edges",
            )
        kept_edges = mandatory_edges + [
            edge for edge in edges if edge not in mandatory_edges
        ][: max(0, limits.max_edges - len(mandatory_edges))]
        node_records = [_compact_node(by_id[identifier]) for identifier in sorted(selected)]
        edge_records = [[edge["from"], edge["relation"], edge["to"]] for edge in kept_edges]
        expandable = sorted(_expandable_nodes(graph, selected))
        result = {
            "schema_version": REVIEW_SLICE_SCHEMA,
            "mode": mode,
            "status": _slice_status(graph, selected),
            "snapshot": {
                "state": "EXACT_MATCH",
                "recorded_digest": graph["snapshot"]["digest"],
                "current_digest": current_digest,
            },
            "nodes": node_records,
            "edges": edge_records,
            "cut": {
                "truncated": len(selected) < len(graph["nodes"]) or len(kept_edges) < len(graph["edges"]),
                "omitted_nodes": len(graph["nodes"]) - len(selected),
                "omitted_edges": len(graph["edges"]) - len(kept_edges),
                "expandable": expandable,
            },
        }
        if len(canonical_json_bytes(result)) <= limits.max_bytes:
            return validate_review_slice(result)
        removable = sorted(
            selected - required,
            key=lambda identifier: (by_id[identifier]["priority"], identifier),
        )
        if not removable:
            raise ReviewGraphError(
                "context_limit",
                "mandatory Review Graph safety kernel exceeds max_bytes",
            )
        selected.remove(removable[0])


def _compact_node(node: dict[str, Any]) -> dict[str, Any]:
    attributes = node["attributes"]
    result: dict[str, Any] = {
        "id": node["id"],
        "kind": node["kind"],
        "state": node["state"],
        "authority": node["authority"],
        "text": node["text"],
        "refs": sorted({item["ref"] for item in node["source_refs"]}),
    }
    path = attributes.get("path")
    line = attributes.get("line")
    if isinstance(path, str):
        result["location"] = f"{path}:{line}" if isinstance(line, int) else path
    freshness = attributes.get("freshness")
    if isinstance(freshness, str):
        result["freshness"] = freshness
    limitations = attributes.get("root_limitations")
    if isinstance(limitations, list) and all(
        isinstance(item, str) and item for item in limitations
    ):
        result["limitations"] = limitations
    return result


def _direct_neighbors(
    graph: dict[str, Any],
    seeds: set[str],
    relations: set[str],
) -> set[str]:
    result: set[str] = set()
    for edge in graph["edges"]:
        if relations and edge["relation"] not in relations:
            continue
        if edge["from"] in seeds:
            result.add(edge["to"])
        if edge["to"] in seeds:
            result.add(edge["from"])
    return result


def _expandable_nodes(graph: dict[str, Any], selected: set[str]) -> set[str]:
    result: set[str] = set()
    for edge in graph["edges"]:
        if edge["from"] in selected and edge["to"] not in selected:
            result.add(edge["from"])
        if edge["to"] in selected and edge["from"] not in selected:
            result.add(edge["to"])
    return result


def _slice_status(graph: dict[str, Any], selected: set[str]) -> str:
    diagnostics = [item["status"] for item in graph["diagnostics"]]
    if "FAIL" in diagnostics:
        return "FAIL"
    if "UNKNOWN" in diagnostics:
        return "UNKNOWN"
    states = [node["state"] for node in graph["nodes"] if node["id"] in selected]
    if "FAIL" in states:
        return "FAIL"
    if "UNKNOWN" in states:
        return "UNKNOWN"
    return "PASS"
