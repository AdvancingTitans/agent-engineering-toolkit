"""Bounded recursive decomposition for Evidence Atlas perspectives."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any


HIERARCHY_SCHEMA = "aet-evidence-hierarchy/1.0"
_STALE = {
    "stale",
    "relevant_files_changed",
    "workspace_changed",
    "environment_changed",
}
_TYPED_DECOMPOSERS: dict[str, tuple[tuple[str, ...], ...]] = {
    "finding": (
        ("claim", "subclaim"),
        ("verified_evidence", "proof", "observation"),
        ("conflict", "counter_claim"),
        ("limitation", "unknown"),
        ("recommendation",),
    ),
    "claim": (
        ("subclaim",),
        ("verified_evidence", "proof", "evidence_candidate", "observation"),
        ("conflict", "counter_claim"),
        ("freshness_result",),
        ("limitation", "unknown"),
        ("recommendation",),
    ),
    "change_group": (
        ("file", "symbol"),
        ("change_group",),
        ("authorization", "constraint", "policy_rule"),
        ("proof", "command"),
        ("limitation", "unknown"),
    ),
    "proof": (
        ("command",),
        ("file", "artifact"),
        ("claim", "subclaim"),
        ("freshness_result",),
        ("limitation", "unknown"),
    ),
    "source": (
        ("tool_call", "tool_result", "run"),
        ("verified_evidence", "evidence_candidate", "observation"),
        ("conflict", "unknown"),
        ("authorization", "constraint", "policy_rule"),
        ("limitation",),
    ),
}


def build_hierarchy(
    graph: dict[str, Any], perspective: Mapping[str, Any]
) -> dict[str, Any]:
    """Build one perspective's bounded, cycle-safe recursive hierarchy."""
    policy = graph["generation_policy"]
    nodes = {
        node["id"]: node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    edges = {
        edge["id"]: edge
        for edge in graph.get("edges", [])
        if isinstance(edge, dict) and isinstance(edge.get("id"), str)
    }
    _evaluate_complexity(nodes, edges.values(), policy)

    diagrams: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    node_to_parent: dict[str, set[str]] = defaultdict(set)
    expanded: dict[tuple[str, str], str] = {}
    perspective_id = perspective.get("id")
    if not isinstance(perspective_id, str) or not perspective_id:
        raise ValueError("perspective.id must be a non-empty string")
    selected_edge_ids = perspective.get("edge_ids")
    if not isinstance(selected_edge_ids, list):
        raise ValueError("perspective.edge_ids must be an array")

    def decompose(
        perspective_id: str,
        root_id: str,
        depth: int,
        path: tuple[str, ...],
        parent_diagram_id: str | None,
    ) -> str | None:
        key = (perspective_id, root_id)
        if policy["deduplicate_by_canonical_node_id"] and key in expanded:
            references.append(
                {
                    "perspective_id": perspective_id,
                    "node_id": root_id,
                    "target_diagram_id": expanded[key],
                    "parent_diagram_id": parent_diagram_id,
                    "reason": "deduplicated",
                }
            )
            return None
        if root_id in path:
            references.append(
                {
                    "perspective_id": perspective_id,
                    "node_id": root_id,
                    "target_diagram_id": None,
                    "parent_diagram_id": parent_diagram_id,
                    "reason": "cycle",
                }
            )
            diagnostics.append(
                {
                    "code": "CYCLE_DETECTED",
                    "severity": "warning",
                    "perspective_id": perspective_id,
                    "node_id": root_id,
                    "message": "Recursive expansion stopped at a canonical-node cycle.",
                }
            )
            return None
        if len(diagrams) >= policy["max_total_diagrams"]:
            diagnostics.append(
                {
                    "code": "DIAGRAM_BUDGET_EXHAUSTED",
                    "severity": "warning",
                    "perspective_id": perspective_id,
                    "node_id": root_id,
                    "message": "max_total_diagrams prevented further decomposition.",
                }
            )
            return None

        selected_edges = {
            edge_id: edges[edge_id]
            for edge_id in selected_edge_ids
            if edge_id in edges
        }
        root_type = nodes[root_id]["type"]
        neighbors = _decomposition_neighbors(
            root_id,
            root_type,
            nodes,
            selected_edges.values(),
        )
        maximum_children = min(
            policy["max_children_per_node"],
            max(0, policy["max_nodes_per_diagram"] - 1),
        )
        included_children = neighbors[:maximum_children]
        omitted_children = neighbors[maximum_children:]
        included_ids = {root_id, *included_children}
        diagram_edges = [
            edge
            for edge in selected_edges.values()
            if edge["from"] in included_ids and edge["to"] in included_ids
        ]
        diagram_id = _diagram_id(perspective_id, root_id, depth)
        diagram = {
            "id": diagram_id,
            "perspective_id": perspective_id,
            "root_node_id": root_id,
            "parent_diagram_id": parent_diagram_id,
            "depth": depth,
            "node_ids": sorted(included_ids),
            "edge_ids": sorted(edge["id"] for edge in diagram_edges),
            "child_diagram_ids": [],
            "reference_node_ids": [],
            "omitted_node_ids": omitted_children,
            "truncated": bool(omitted_children),
            "extensions": {
                "decomposer": (
                    f"typed:{root_type}"
                    if root_type in _TYPED_DECOMPOSERS
                    else "generic:relations"
                )
            },
        }
        diagrams.append(diagram)
        expanded[key] = diagram_id
        for node_id in included_ids:
            node_to_parent[node_id].add(diagram_id)

        if omitted_children:
            diagnostics.append(
                {
                    "code": "CHILD_BUDGET_APPLIED",
                    "severity": "info",
                    "perspective_id": perspective_id,
                    "node_id": root_id,
                    "message": (
                        f"{len(omitted_children)} child nodes were omitted by "
                        "max_children_per_node/max_nodes_per_diagram."
                    ),
                }
            )

        next_path = (*path, root_id)
        for child_id in included_children:
            child = nodes[child_id]
            classification = child["complexity"]["classification"]
            if classification == "leaf":
                continue
            if child_id in next_path:
                references.append(
                    {
                        "perspective_id": perspective_id,
                        "node_id": child_id,
                        "target_diagram_id": expanded.get(
                            (perspective_id, child_id)
                        ),
                        "parent_diagram_id": diagram_id,
                        "reason": "cycle",
                    }
                )
                diagram["reference_node_ids"].append(child_id)
                diagnostics.append(
                    {
                        "code": "CYCLE_DETECTED",
                        "severity": "warning",
                        "perspective_id": perspective_id,
                        "node_id": child_id,
                        "message": "Recursive expansion stopped at a canonical-node cycle.",
                    }
                )
                continue
            existing = expanded.get((perspective_id, child_id))
            if policy["deduplicate_by_canonical_node_id"] and existing:
                references.append(
                    {
                        "perspective_id": perspective_id,
                        "node_id": child_id,
                        "target_diagram_id": existing,
                        "parent_diagram_id": diagram_id,
                        "reason": "deduplicated",
                    }
                )
                diagram["reference_node_ids"].append(child_id)
                continue
            if depth >= policy["max_depth"]:
                references.append(
                    {
                        "perspective_id": perspective_id,
                        "node_id": child_id,
                        "target_diagram_id": None,
                        "parent_diagram_id": diagram_id,
                        "reason": "max_depth",
                    }
                )
                diagram["reference_node_ids"].append(child_id)
                diagnostics.append(
                    {
                        "code": "MAX_DEPTH_REACHED",
                        "severity": "info",
                        "perspective_id": perspective_id,
                        "node_id": child_id,
                        "message": "max_depth prevented further decomposition.",
                    }
                )
                continue
            child_diagram = decompose(
                perspective_id,
                child_id,
                depth + 1,
                next_path,
                diagram_id,
            )
            if child_diagram:
                diagram["child_diagram_ids"].append(child_diagram)
            else:
                diagram["reference_node_ids"].append(child_id)

        diagram["child_diagram_ids"].sort()
        diagram["reference_node_ids"] = sorted(set(diagram["reference_node_ids"]))
        return diagram_id

    roots = [
        node_id
        for node_id in perspective.get("root_node_ids", [])
        if node_id in nodes
    ]
    root_entries: list[dict[str, Any]] = []
    for root_id in roots:
        if len(diagrams) >= policy["max_total_diagrams"]:
            root_entries.append(
                {
                    "node_id": root_id,
                    "diagram_id": None,
                    "status": "budget_exhausted",
                }
            )
            continue
        diagram_id = decompose(perspective_id, root_id, 0, (), None)
        root_entries.append(
            {
                "node_id": root_id,
                "diagram_id": diagram_id
                or expanded.get((perspective_id, root_id)),
                "status": "expanded" if diagram_id else "reference",
            }
        )

    hierarchy = {
        "schema_version": HIERARCHY_SCHEMA,
        "bundle_id": graph.get("bundle_id"),
        "perspective_id": perspective_id,
        "generation_policy": dict(policy),
        "roots": root_entries,
        "nodes": {
            node_id: {
                "complexity": dict(node["complexity"]),
                "diagram_ids": sorted(node_to_parent.get(node_id, set())),
            }
            for node_id, node in sorted(nodes.items())
        },
        "diagrams": sorted(diagrams, key=lambda item: item["id"]),
        "references": sorted(
            references,
            key=lambda item: (
                item["perspective_id"],
                item["node_id"],
                item["parent_diagram_id"] or "",
                item["reason"],
            ),
        ),
        "diagnostics": _unique_diagnostics(diagnostics),
    }
    graph.setdefault("hierarchies", {})[perspective_id] = hierarchy
    dependency = graph.setdefault("dependency_index", {})
    existing_parent = {
        node_id: set(diagram_ids)
        for node_id, diagram_ids in dependency.get(
            "node_to_parent_diagrams", {}
        ).items()
    }
    for node_id, values in node_to_parent.items():
        existing_parent.setdefault(node_id, set()).update(values)
    dependency["node_to_parent_diagrams"] = {
        node_id: sorted(values)
        for node_id, values in sorted(existing_parent.items())
    }
    _update_record_parent_diagrams(graph, nodes)
    return hierarchy


def _evaluate_complexity(
    nodes: Mapping[str, dict[str, Any]],
    edges: Any,
    policy: Mapping[str, Any],
) -> None:
    edge_values = list(edges)
    incoming: Counter[str] = Counter()
    outgoing: Counter[str] = Counter()
    relation_types: dict[str, set[str]] = defaultdict(set)
    neighbor_types: dict[str, set[str]] = defaultdict(set)
    neighbor_ids: dict[str, set[str]] = defaultdict(set)
    claim_neighbors: dict[str, set[str]] = defaultdict(set)
    has_support: set[str] = set()
    has_counter: set[str] = set()
    for edge in edge_values:
        source = edge["from"]
        target = edge["to"]
        outgoing[source] += 1
        incoming[target] += 1
        relation_types[source].add(edge["type"])
        relation_types[target].add(edge["type"])
        if source in nodes and target in nodes:
            neighbor_types[source].add(nodes[target]["type"])
            neighbor_types[target].add(nodes[source]["type"])
            neighbor_ids[source].add(target)
            neighbor_ids[target].add(source)
            if nodes[source]["type"] == "claim":
                claim_neighbors[target].add(source)
            if nodes[target]["type"] == "claim":
                claim_neighbors[source].add(target)
        if edge["type"] in {"SUPPORTED_BY", "PARTIALLY_SUPPORTED_BY"}:
            has_support.add(source)
        if edge["type"] == "CONTRADICTED_BY":
            has_counter.add(source)

    for node_id, node in nodes.items():
        score = outgoing[node_id] + min(incoming[node_id], 3)
        reasons: list[str] = []
        relation_count = len(relation_types[node_id])
        if relation_count > 1:
            score += relation_count - 1
            reasons.append("multiple relation types")
        if node["type"] == "conflict" or node.get("status") == "conflicted":
            score += 3
            reasons.append("conflict")
        if node["type"] == "unknown" or node.get("status") == "unknown":
            score += 2
            reasons.append("unknown")
        if node.get("freshness") in _STALE or node.get("status") == "stale":
            score += 2
            reasons.append("freshness transition")
        if outgoing[node_id] >= 3:
            reasons.append("multiple child entities")
        if len(neighbor_types[node_id]) >= 3:
            score += 2
            reasons.append("cross-domain relations")

        mandatory: list[str] = []
        if len(claim_neighbors[node_id]) >= 2:
            mandatory.append("linked to multiple claims")
        if node_id in has_support and node_id in has_counter:
            mandatory.append("support and counter-evidence coexist")
        if node["type"] == "conflict" or node.get("status") == "conflicted":
            mandatory.append("conflict requires decomposition")
        if (
            node.get("status") in {"partially_supported", "stale"}
            or node.get("freshness") in _STALE
        ):
            mandatory.append("partial or stale applicability")
        if node["type"] == "proof" and len(claim_neighbors[node_id]) >= 2:
            mandatory.append("proof validates multiple claims")
        change_groups = {
            neighbor_id
            for neighbor_id in neighbor_ids[node_id]
            if nodes[neighbor_id]["type"] == "change_group"
        }
        if len(change_groups) >= 3:
            mandatory.append("three or more change groups")
        file_modules = {
            _path_module(nodes[neighbor_id])
            for neighbor_id in neighbor_ids[node_id]
            if nodes[neighbor_id]["type"] == "file"
        }
        file_modules.discard("")
        if len(file_modules) >= 2:
            mandatory.append("cross-module scope")
        if (
            node["type"] == "finding"
            and sum(
                nodes[neighbor_id]["type"] in {"claim", "subclaim"}
                for neighbor_id in neighbor_ids[node_id]
            )
            >= 2
        ):
            mandatory.append("finding contains multiple questions")
        if len(neighbor_ids[node_id]) + 1 > policy["max_nodes_per_diagram"]:
            mandatory.append("node exceeds per-diagram node budget")
        if mandatory:
            score = max(score, 8)
            reasons.extend(mandatory)
        classification = (
            "mandatory_decomposition"
            if score >= 8
            else ("expandable" if score >= 4 else "leaf")
        )
        node["complexity"] = {
            "score": score,
            "classification": classification,
            "reasons": sorted(set(reasons)),
        }


def _decomposition_neighbors(
    root_id: str,
    root_type: str,
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Any,
) -> list[str]:
    groups = _TYPED_DECOMPOSERS.get(root_type, ())
    type_priority = {
        node_type: group_index
        for group_index, group in enumerate(groups)
        for node_type in group
    }
    candidates: dict[str, tuple[int, int, str]] = {}
    for edge in edges:
        neighbor: str | None = None
        if edge["from"] == root_id:
            neighbor = edge["to"]
        elif edge["to"] == root_id:
            neighbor = edge["from"]
        if neighbor is None:
            continue
        priority = int(edge.get("render", {}).get("priority", 50))
        neighbor_type = str(nodes.get(neighbor, {}).get("type", ""))
        group_index = type_priority.get(neighbor_type, len(groups))
        current = candidates.get(neighbor)
        candidate = (group_index, -priority, edge["id"])
        if current is None or candidate < current:
            candidates[neighbor] = candidate
    return [
        node_id
        for node_id, _ in sorted(
            candidates.items(),
            key=lambda item: (item[1][0], item[1][1], item[0], item[1][2]),
        )
    ]


def _diagram_id(perspective_id: str, root_id: str, depth: int) -> str:
    digest = hashlib.sha256(
        f"{perspective_id}\0{root_id}\0{depth}".encode("utf-8")
    ).hexdigest()[:20]
    return f"diagram:{digest}"


def _path_module(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes")
    path = attributes.get("path") if isinstance(attributes, Mapping) else None
    if not isinstance(path, str):
        return ""
    normalized = path.strip("/")
    return normalized.split("/", 1)[0] if normalized else ""


def _unique_diagnostics(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for value in values:
        key = (
            value["code"],
            value["perspective_id"],
            value["node_id"],
            value["message"],
        )
        unique[key] = value
    return [unique[key] for key in sorted(unique)]


def _update_record_parent_diagrams(
    graph: dict[str, Any], nodes: Mapping[str, Mapping[str, Any]]
) -> None:
    dependency = graph.setdefault("dependency_index", {})
    node_to_parent = dependency.get("node_to_parent_diagrams", {})
    record_to_parent: dict[str, set[str]] = defaultdict(set)
    for node_id, diagram_ids in node_to_parent.items():
        node = nodes.get(node_id)
        if not node:
            continue
        for ref in node.get("source_refs", []):
            record_to_parent[_dependency_key(ref)].update(diagram_ids)
    dependency["record_to_parent_diagrams"] = {
        key: sorted(values)
        for key, values in sorted(record_to_parent.items())
    }


def _dependency_key(ref: Mapping[str, str]) -> str:
    collection = ref.get("collection", "")
    record_id = ref.get("record_id", "")
    names = {
        "manifest.json": "manifest",
        "index.json": "index",
        "policy.json": "policy",
        "core/claims.jsonl": "claims",
        "core/evidence.jsonl": "evidence",
        "core/observations.jsonl": "observations",
        "archive/sources.jsonl": "sources",
        "archive/diagnostics.jsonl": "diagnostics",
        "archive/conflicts.jsonl": "conflicts",
        "archive/ledger.jsonl": "ledger",
    }
    name = names.get(collection, collection)
    return name if name in {"manifest", "index", "policy"} else f"{name}:{record_id}"


__all__ = ["HIERARCHY_SCHEMA", "build_hierarchy"]
