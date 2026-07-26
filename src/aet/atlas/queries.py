"""Bounded read-only queries over a validated canonical Evidence Graph."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from typing import Any


MAX_QUERY_DEPTH = 8
MAX_QUERY_NODES = 200
MAX_QUERY_BYTES = 1_000_000


class AtlasQueryError(ValueError):
    """A graph query is invalid or exceeds a deterministic budget."""


def list_perspectives(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return compact, stable Perspective metadata."""
    values = graph.get("perspectives")
    if not isinstance(values, list):
        raise AtlasQueryError("graph.perspectives must be an array")
    result = []
    for item in values:
        if not isinstance(item, Mapping):
            raise AtlasQueryError("graph.perspectives must contain objects")
        result.append(
            {
                key: item[key]
                for key in (
                    "id",
                    "title",
                    "question",
                    "root_node_ids",
                    "node_count",
                    "edge_count",
                )
                if key in item
            }
        )
    return result


def get_node(graph: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    """Resolve one canonical node ID."""
    if not isinstance(node_id, str) or not node_id:
        raise AtlasQueryError("node_id must be a non-empty string")
    for node in _records(graph, "nodes"):
        if node.get("id") == node_id:
            return dict(node)
    raise AtlasQueryError(f"unknown Atlas node: {node_id}")


def get_children(
    graph: Mapping[str, Any],
    node_id: str,
    *,
    perspective: str | None = None,
    max_nodes: int = 25,
) -> list[dict[str, Any]]:
    """Return deterministic outgoing neighbors under one Perspective."""
    _budgets(1, max_nodes, MAX_QUERY_BYTES)
    node_ids = _perspective_node_ids(graph, perspective)
    edges = [
        edge
        for edge in _records(graph, "edges")
        if edge.get("from") == node_id
        and edge.get("to") in node_ids
        and edge.get("from") in node_ids
    ]
    edges.sort(key=lambda item: (-_priority(item), str(item.get("id", ""))))
    result = []
    for edge in edges[:max_nodes]:
        child = get_node(graph, str(edge["to"]))
        result.append({"edge": dict(edge), "node": child})
    return result


def get_node_subgraph(
    graph: Mapping[str, Any],
    root_id: str,
    *,
    perspective: str | None = None,
    depth: int = 2,
    max_nodes: int = 50,
    max_bytes: int = 262_144,
    edge_types: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Traverse a bounded graph without changing evidence semantics."""
    _budgets(depth, max_nodes, max_bytes)
    allowed_nodes = _perspective_node_ids(graph, perspective)
    if root_id not in allowed_nodes:
        raise AtlasQueryError(
            f"root node {root_id} is not present in Perspective {perspective}"
        )
    allowed_edges = set(edge_types or ())
    edge_index: dict[str, list[dict[str, Any]]] = {}
    for edge in _records(graph, "edges"):
        if edge.get("from") not in allowed_nodes or edge.get("to") not in allowed_nodes:
            continue
        if allowed_edges and edge.get("type") not in allowed_edges:
            continue
        edge_index.setdefault(str(edge["from"]), []).append(dict(edge))
    for values in edge_index.values():
        values.sort(key=lambda item: (-_priority(item), str(item.get("id", ""))))

    selected_nodes: list[dict[str, Any]] = []
    selected_edges: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    queue: deque[tuple[str, int]] = deque([(root_id, 0)])
    truncated = False
    while queue:
        node_id, level = queue.popleft()
        if node_id in seen:
            continue
        if len(seen) >= max_nodes:
            truncated = True
            break
        seen.add(node_id)
        selected_nodes.append(get_node(graph, node_id))
        if level >= depth:
            continue
        for edge in edge_index.get(node_id, []):
            selected_edges[str(edge["id"])] = edge
            if str(edge["to"]) not in seen:
                queue.append((str(edge["to"]), level + 1))
    selected_edges = {
        identifier: edge
        for identifier, edge in selected_edges.items()
        if edge["from"] in seen and edge["to"] in seen
    }
    result = {
        "root_id": root_id,
        "perspective": perspective,
        "depth": depth,
        "truncated": truncated,
        "nodes": selected_nodes,
        "edges": [
            selected_edges[key] for key in sorted(selected_edges)
        ],
    }
    if len(_json_bytes(result)) > max_bytes:
        raise AtlasQueryError("query result exceeds max_bytes")
    return result


def trace_claim_support(
    graph: Mapping[str, Any],
    claim_id: str,
    *,
    depth: int = 4,
    max_nodes: int = 100,
    max_bytes: int = 524_288,
) -> dict[str, Any]:
    """Trace support, counter-evidence, limits, proof, and Freshness paths."""
    canonical = _resolve_record_or_node(graph, "claim", claim_id)
    return get_node_subgraph(
        graph,
        canonical,
        perspective="claim-chain",
        depth=depth,
        max_nodes=max_nodes,
        max_bytes=max_bytes,
        edge_types={
            "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY",
            "CONTRADICTED_BY",
            "LIMITED_BY",
            "DERIVED_FROM",
            "PRODUCED_BY",
            "VALIDATES",
            "FRESH_FOR",
            "STALE_FOR",
            "INVALIDATED_BY",
            "LEAVES_UNKNOWN",
            "RECOMMENDS",
        },
    )


def trace_conflict(
    graph: Mapping[str, Any],
    conflict_id: str,
    *,
    depth: int = 3,
    max_nodes: int = 75,
    max_bytes: int = 393_216,
) -> dict[str, Any]:
    """Trace one conflict and its unresolved/unknown paths."""
    canonical = _resolve_record_or_node(graph, "conflict", conflict_id)
    return get_node_subgraph(
        graph,
        canonical,
        perspective="conflicts",
        depth=depth,
        max_nodes=max_nodes,
        max_bytes=max_bytes,
    )


def trace_freshness_impact(
    graph: Mapping[str, Any],
    node_id: str,
    *,
    depth: int = 4,
    max_nodes: int = 100,
    max_bytes: int = 524_288,
) -> dict[str, Any]:
    """Trace current/stale/unknown applicability and downstream Claims."""
    canonical = (
        node_id
        if node_id.startswith("node:")
        else _resolve_any_identifier(
            graph, {"verified_evidence", "proof", "freshness_result"}, node_id
        )
    )
    return get_node_subgraph(
        graph,
        canonical,
        perspective="freshness",
        depth=depth,
        max_nodes=max_nodes,
        max_bytes=max_bytes,
    )


def explain_node(graph: Mapping[str, Any], node_id: str) -> dict[str, Any]:
    """Return one node with direct incoming and outgoing authority edges."""
    node = get_node(graph, node_id)
    incoming = []
    outgoing = []
    for edge in _records(graph, "edges"):
        if edge.get("to") == node_id:
            incoming.append(dict(edge))
        if edge.get("from") == node_id:
            outgoing.append(dict(edge))
    incoming.sort(key=lambda item: str(item["id"]))
    outgoing.sort(key=lambda item: str(item["id"]))
    return {"node": node, "incoming": incoming, "outgoing": outgoing}


def _perspective_node_ids(
    graph: Mapping[str, Any], perspective: str | None
) -> set[str]:
    all_nodes = {str(node["id"]) for node in _records(graph, "nodes")}
    if perspective is None:
        return all_nodes
    for item in _records(graph, "perspectives"):
        if item.get("id") == perspective:
            values = item.get("node_ids")
            if not isinstance(values, list) or any(
                not isinstance(value, str) for value in values
            ):
                raise AtlasQueryError("Perspective node_ids must contain strings")
            return set(values)
    raise AtlasQueryError(f"unknown Perspective: {perspective}")


def _resolve_record_or_node(
    graph: Mapping[str, Any], node_type: str, identifier: str
) -> str:
    if identifier.startswith("node:"):
        node = get_node(graph, identifier)
        if node.get("type") != node_type:
            raise AtlasQueryError(
                f"node {identifier} is not of type {node_type}"
            )
        return identifier
    return _resolve_any_identifier(graph, {node_type}, identifier)


def _resolve_any_identifier(
    graph: Mapping[str, Any], node_types: set[str], identifier: str
) -> str:
    suffix = f":{identifier}"
    matches = [
        str(node["id"])
        for node in _records(graph, "nodes")
        if node.get("type") in node_types
        and (
            str(node.get("id", "")).endswith(suffix)
            or node.get("attributes", {}).get("record_id") == identifier
        )
    ]
    if len(matches) != 1:
        raise AtlasQueryError(
            f"identifier {identifier!r} resolved to {len(matches)} Atlas nodes"
        )
    return matches[0]


def _budgets(depth: int, max_nodes: int, max_bytes: int) -> None:
    for name, value, maximum in (
        ("depth", depth, MAX_QUERY_DEPTH),
        ("max_nodes", max_nodes, MAX_QUERY_NODES),
        ("max_bytes", max_bytes, MAX_QUERY_BYTES),
    ):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
            or value > maximum
        ):
            raise AtlasQueryError(f"{name} must be between 1 and {maximum}")


def _records(graph: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    values = graph.get(field)
    if not isinstance(values, list) or any(
        not isinstance(value, Mapping) for value in values
    ):
        raise AtlasQueryError(f"graph.{field} must contain objects")
    return values


def _priority(edge: Mapping[str, Any]) -> int:
    render = edge.get("render")
    value = render.get("priority") if isinstance(render, Mapping) else 0
    return value if isinstance(value, int) else 0


def _json_bytes(value: Any) -> bytes:
    import json

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
