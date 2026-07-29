"""Canonical Evidence Atlas vocabulary and deterministic helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any


GRAPH_SCHEMA = "aet-evidence-graph/1.0"
PERSPECTIVE_SCHEMA = "aet-evidence-perspective/1.0"
ATLAS_MANIFEST_SCHEMA = "aet-evidence-atlas-manifest/1.0"
DIFF_SCHEMA = "aet-evidence-atlas-diff/1.0"

NODE_TYPES = frozenset(
    {
        "intent",
        "constraint",
        "authorization",
        "run",
        "agent",
        "tool_call",
        "tool_result",
        "observation",
        "evidence_candidate",
        "verified_evidence",
        "source",
        "artifact",
        "file",
        "symbol",
        "change_group",
        "command",
        "proof",
        "freshness_result",
        "claim",
        "subclaim",
        "counter_claim",
        "finding",
        "conflict",
        "unknown",
        "limitation",
        "recommendation",
        "policy_rule",
        "budget",
    }
)

EDGE_TYPES = frozenset(
    {
        "ANSWERS",
        "DECOMPOSES_INTO",
        "SUPPORTED_BY",
        "PARTIALLY_SUPPORTED_BY",
        "CONTRADICTED_BY",
        "LIMITED_BY",
        "DERIVED_FROM",
        "OBSERVED_IN",
        "PRODUCED_BY",
        "EXECUTED_BY",
        "CALLED",
        "RETURNED",
        "APPLIES_TO",
        "CHANGED",
        "DEPENDS_ON",
        "VALIDATES",
        "INVALIDATED_BY",
        "FRESH_FOR",
        "STALE_FOR",
        "AUTHORIZED_BY",
        "VIOLATES",
        "CONSTRAINED_BY",
        "GROUPED_IN",
        "RESOLVES",
        "LEAVES_UNKNOWN",
        "RECOMMENDS",
        "PRECEDES",
        "DUPLICATES",
    }
)

NODE_STATUSES = frozenset(
    {
        "verified",
        "supported",
        "partially_supported",
        "conflicted",
        "unsupported",
        "unknown",
        "stale",
        "current",
        "resolved",
        "not_applicable",
        "recorded",
    }
)

PERSPECTIVES = (
    "claim-chain",
    "investigation-flow",
    "change-scope",
    "verification-coverage",
    "evidence-data-flow",
    "integrations",
    "conflicts",
    "freshness",
    "improvement-chain",
    "regression-lineage",
)

DEFAULT_GENERATION_POLICY = {
    "max_depth": 4,
    "max_nodes_per_diagram": 25,
    "max_children_per_node": 12,
    "max_total_diagrams": 100,
    "deduplicate_by_canonical_node_id": True,
    "llm_enabled": False,
    "mermaid_security_level": "strict",
    "allow_html_labels": False,
    "allow_external_urls": False,
    "allow_external_images": False,
}

_SAFE_IDENTIFIER = re.compile(r"[^A-Za-z0-9_-]+")


def canonical_bytes(value: Any) -> bytes:
    """Return the stable UTF-8 JSON representation used by Atlas hashes."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    """Hash a JSON value canonically."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def stable_id(kind: str, identifier: str) -> str:
    """Build a stable canonical node ID without embedding arbitrary text."""
    safe_kind = _SAFE_IDENTIFIER.sub("-", kind).strip("-").lower()
    safe_identifier = _SAFE_IDENTIFIER.sub("-", identifier).strip("-")
    if not safe_kind or not safe_identifier:
        digest = hashlib.sha256(f"{kind}\0{identifier}".encode("utf-8")).hexdigest()[:16]
        return f"node:derived:{digest}"
    return f"node:{safe_kind}:{safe_identifier}"


def derived_id(kind: str, *parts: str) -> str:
    """Build a stable ID for a node derived from one or more source fields."""
    digest = hashlib.sha256("\0".join((kind, *parts)).encode("utf-8")).hexdigest()[:20]
    return f"node:{kind}:{digest}"


def edge_id(from_id: str, edge_type: str, to_id: str, ordinal: int = 0) -> str:
    """Build a stable edge ID."""
    digest = hashlib.sha256(
        f"{from_id}\0{edge_type}\0{to_id}\0{ordinal}".encode("utf-8")
    ).hexdigest()[:24]
    return f"edge:{digest}"


def source_ref(collection: str, record_id: str, field: str) -> dict[str, str]:
    """Return one machine-verifiable source reference."""
    return {
        "collection": collection,
        "record_id": record_id,
        "field": field,
    }


def merge_policy(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a validated generation policy with bounded overrides."""
    policy = dict(DEFAULT_GENERATION_POLICY)
    if overrides:
        unknown = set(overrides) - set(policy)
        if unknown:
            raise ValueError(
                "unsupported Atlas generation policy fields: "
                + ", ".join(sorted(unknown))
            )
        policy.update(overrides)
    for name in (
        "max_depth",
        "max_nodes_per_diagram",
        "max_children_per_node",
        "max_total_diagrams",
    ):
        value = policy[name]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if policy["max_total_diagrams"] < len(PERSPECTIVES):
        raise ValueError(
            "max_total_diagrams must reserve at least one root diagram for "
            f"each of the {len(PERSPECTIVES)} built-in Perspectives"
        )
    for name in (
        "deduplicate_by_canonical_node_id",
        "llm_enabled",
        "allow_html_labels",
        "allow_external_urls",
        "allow_external_images",
    ):
        if not isinstance(policy[name], bool):
            raise ValueError(f"{name} must be a boolean")
    if policy["llm_enabled"]:
        raise ValueError(
            "AET v1.16 Atlas is deterministic; host LLM narratives are optional "
            "consumer extensions and cannot be enabled by the core builder"
        )
    if policy["mermaid_security_level"] != "strict":
        raise ValueError("mermaid_security_level must remain strict")
    if (
        policy["allow_html_labels"]
        or policy["allow_external_urls"]
        or policy["allow_external_images"]
    ):
        raise ValueError("unsafe Mermaid capabilities cannot be enabled")
    return policy


def record_hashes(bundle: Mapping[str, Any]) -> dict[str, str]:
    """Index every Bundle record and control document for incremental rebuilds."""
    result: dict[str, str] = {}
    for collection in (
        "claims",
        "evidence",
        "observations",
        "sources",
        "diagnostics",
        "conflicts",
        "ledger",
    ):
        for record in bundle.get(collection, []):
            if isinstance(record, Mapping) and isinstance(record.get("id"), str):
                result[f"{collection}:{record['id']}"] = sha256_value(record)
    for name in ("manifest", "index", "policy"):
        value = bundle.get(name)
        if isinstance(value, Mapping):
            result[name] = sha256_value(value)
    return dict(sorted(result.items()))
