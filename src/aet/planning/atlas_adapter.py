"""Bounded Planning selection over a validated Evidence Atlas."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aet.atlas import (
    AtlasStorageError,
    AtlasValidationError,
    load_evidence_atlas,
    validate_evidence_atlas,
)

from .errors import PlanningError, PlanningErrorCode
from .models import PlanningRequest
from .relevance import lexical_terms


PERSPECTIVE_PRIORITY = (
    "improvement-chain",
    "change-scope",
    "claim-chain",
    "conflicts",
    "verification-coverage",
    "regression-lineage",
    "integrations",
)


@dataclass(frozen=True)
class AtlasSelection:
    atlas_identity: str
    bundle_identity: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    omitted_nodes: int


def select_planning_nodes(
    atlas_path: Path,
    bundle_path: Path,
    request: PlanningRequest,
    *,
    max_nodes: int,
    max_depth: int,
) -> AtlasSelection:
    """Validate identities, then select nodes in deterministic priority order."""
    del max_depth  # Perspective membership already bounds graph traversal in v1.
    try:
        root = (
            Path(atlas_path).parent
            if Path(atlas_path).name == "atlas-manifest.json"
            else Path(atlas_path)
        )
        validate_evidence_atlas(root / "atlas-manifest.json", bundle_path)
        loaded = load_evidence_atlas(root)
    except (AtlasStorageError, AtlasValidationError, OSError, ValueError) as error:
        raise PlanningError(
            PlanningErrorCode.INVALID_ATLAS,
            "Evidence Atlas validation failed",
        ) from error
    graph = loaded["graph"]
    manifest = loaded["manifest"]
    bundle_identity = str(graph.get("bundle_id", ""))
    atlas_identity = str(
        manifest.get("atlas", {}).get("content_hash")
        or manifest.get("atlas", {}).get("id")
        or manifest.get("graph", {}).get("content_hash")
        or manifest.get("integrity", {}).get("file_hashes", {}).get(
            "graph/graph.json"
        )
        or ""
    )
    if not bundle_identity or not atlas_identity:
        raise PlanningError(
            PlanningErrorCode.INVALID_ATLAS,
            "Atlas identity is unavailable",
        )
    terms = lexical_terms(request.user_goal)
    perspective_tier: dict[str, int] = {}
    for perspective in graph.get("perspectives", []):
        if not isinstance(perspective, dict):
            continue
        identifier = perspective.get("id")
        if identifier not in PERSPECTIVE_PRIORITY:
            continue
        tier = PERSPECTIVE_PRIORITY.index(identifier)
        for node_id in perspective.get("node_ids", []):
            perspective_tier[str(node_id)] = min(
                tier,
                perspective_tier.get(str(node_id), len(PERSPECTIVE_PRIORITY)),
            )
    ranked = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            continue
        text = " ".join(
            str(node.get(field, ""))
            for field in ("id", "label", "title", "summary", "path", "symbol")
        ).casefold()
        lexical = 0 if any(term in text for term in terms) else 1
        ranked.append(
            (
                perspective_tier.get(node["id"], len(PERSPECTIVE_PRIORITY)),
                lexical,
                node["id"],
                dict(node),
            )
        )
    ranked.sort(key=lambda item: item[:3])
    selected = [item[3] for item in ranked[:max_nodes]]
    selected_ids = {item["id"] for item in selected}
    edges = [
        dict(item)
        for item in graph.get("edges", [])
        if isinstance(item, dict)
        and item.get("from") in selected_ids
        and item.get("to") in selected_ids
    ]
    edges.sort(key=lambda item: str(item.get("id", "")))
    return AtlasSelection(
        atlas_identity=atlas_identity,
        bundle_identity=bundle_identity,
        nodes=selected,
        edges=edges,
        diagnostics=[dict(item) for item in graph.get("diagnostics", []) if isinstance(item, dict)],
        omitted_nodes=max(0, len(ranked) - len(selected)),
    )
