"""Deterministic comparison of two Evidence Atlas graphs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import DIFF_SCHEMA
from .schema_validation import validate_schema


def compare_evidence_atlases(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe factual graph changes without creating a trust score."""
    before_nodes = _by_id(before, "nodes")
    after_nodes = _by_id(after, "nodes")
    before_edges = _by_id(before, "edges")
    after_edges = _by_id(after, "edges")

    added_node_ids = sorted(set(after_nodes) - set(before_nodes))
    removed_node_ids = sorted(set(before_nodes) - set(after_nodes))
    common_node_ids = sorted(set(before_nodes) & set(after_nodes))
    changed_nodes = []
    for identifier in common_node_ids:
        left = before_nodes[identifier]
        right = after_nodes[identifier]
        changes = {}
        for field in (
            "status",
            "freshness",
            "authority",
            "summary",
            "source_refs",
            "attributes",
        ):
            if left.get(field) != right.get(field):
                changes[field] = {
                    "before": left.get(field),
                    "after": right.get(field),
                }
        if changes:
            changed_nodes.append(
                {
                    "id": identifier,
                    "type": right.get("type"),
                    "changes": changes,
                }
            )

    added_edges = [
        after_edges[identifier]
        for identifier in sorted(set(after_edges) - set(before_edges))
    ]
    removed_edges = [
        before_edges[identifier]
        for identifier in sorted(set(before_edges) - set(after_edges))
    ]
    changed_edges = []
    for identifier in sorted(set(before_edges) & set(after_edges)):
        if before_edges[identifier] != after_edges[identifier]:
            changed_edges.append(
                {
                    "id": identifier,
                    "before": before_edges[identifier],
                    "after": after_edges[identifier],
                }
            )

    result = {
        "schema_version": DIFF_SCHEMA,
        "before": {
            "bundle_id": before.get("bundle_id"),
            "bundle_content_hash": before.get("generated_from", {}).get(
                "bundle_content_hash"
            ),
        },
        "after": {
            "bundle_id": after.get("bundle_id"),
            "bundle_content_hash": after.get("generated_from", {}).get(
                "bundle_content_hash"
            ),
        },
        "nodes": {
            "added": [after_nodes[identifier] for identifier in added_node_ids],
            "removed": [
                before_nodes[identifier] for identifier in removed_node_ids
            ],
            "changed": changed_nodes,
        },
        "edges": {
            "added": added_edges,
            "removed": removed_edges,
            "changed": changed_edges,
        },
        "semantic_changes": {
            "claim_status": _field_changes(changed_nodes, "claim", "status"),
            "freshness": _freshness_changes(changed_nodes),
            "conflicts": _typed_membership(
                before_nodes,
                after_nodes,
                "conflict",
            ),
            "unknowns": _typed_membership(
                before_nodes,
                after_nodes,
                "unknown",
            ),
        },
    }
    validate_schema(result, "comparison.schema.json")
    return result


def affected_records(
    previous_graph: Mapping[str, Any],
    current_record_hashes: Mapping[str, str],
) -> dict[str, list[str]]:
    """Return the dependency closure used by incremental rebuild reporting."""
    index = previous_graph.get("dependency_index", {})
    old_hashes = index.get("record_hashes", {})
    if not isinstance(old_hashes, Mapping):
        old_hashes = {}
    changed_records = sorted(
        key
        for key in set(old_hashes) | set(current_record_hashes)
        if old_hashes.get(key) != current_record_hashes.get(key)
    )
    record_to_nodes = index.get("record_to_nodes", {})
    record_to_edges = index.get("record_to_edges", {})
    node_to_perspectives = index.get("node_to_perspectives", {})
    node_to_parents = index.get("node_to_parent_diagrams", {})
    nodes = sorted(
        {
            node
            for record in changed_records
            for node in _list_value(record_to_nodes, record)
        }
    )
    edges = sorted(
        {
            edge
            for record in changed_records
            for edge in _list_value(record_to_edges, record)
        }
    )
    perspectives = sorted(
        {
            perspective
            for node in nodes
            for perspective in _list_value(node_to_perspectives, node)
        }
    )
    parents = sorted(
        {
            parent
            for node in nodes
            for parent in _list_value(node_to_parents, node)
        }
    )
    return {
        "records": changed_records,
        "nodes": nodes,
        "edges": edges,
        "perspectives": perspectives,
        "parent_diagrams": parents,
    }


def _by_id(graph: Mapping[str, Any], field: str) -> dict[str, dict[str, Any]]:
    values = graph.get(field)
    if not isinstance(values, list):
        raise ValueError(f"graph.{field} must be an array")
    result = {}
    for value in values:
        if not isinstance(value, Mapping) or not isinstance(value.get("id"), str):
            raise ValueError(f"graph.{field} records require string IDs")
        identifier = value["id"]
        if identifier in result:
            raise ValueError(f"duplicate graph.{field} ID: {identifier}")
        result[identifier] = dict(value)
    return result


def _field_changes(
    changed_nodes: list[dict[str, Any]],
    node_type: str,
    field: str,
) -> list[dict[str, Any]]:
    return [
        {"id": item["id"], **item["changes"][field]}
        for item in changed_nodes
        if item["type"] == node_type and field in item["changes"]
    ]


def _freshness_changes(
    changed_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {"id": item["id"], **item["changes"]["freshness"]}
        for item in changed_nodes
        if "freshness" in item["changes"]
    ]


def _typed_membership(
    before: Mapping[str, dict[str, Any]],
    after: Mapping[str, dict[str, Any]],
    node_type: str,
) -> dict[str, list[str]]:
    left = {
        identifier
        for identifier, node in before.items()
        if node.get("type") == node_type
    }
    right = {
        identifier
        for identifier, node in after.items()
        if node.get("type") == node_type
    }
    return {
        "added": sorted(right - left),
        "removed": sorted(left - right),
    }


def _list_value(mapping: Any, key: str) -> list[str]:
    if not isinstance(mapping, Mapping):
        return []
    value = mapping.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
