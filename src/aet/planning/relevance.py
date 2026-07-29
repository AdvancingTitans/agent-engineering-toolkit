"""Deterministic reference ranking for Planning Context construction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .bundle_loader import PlanningBundleView
from .models import PlanningRequest


_WORD = re.compile(r"[A-Za-z0-9_.:/-]+|[\u3400-\u9fff]")


@dataclass(frozen=True)
class RankedReference:
    reference_id: str
    kind: str
    priority_tier: int
    reasons: list[str]
    record: dict[str, Any]


def lexical_terms(value: str) -> list[str]:
    return sorted(
        {
            token.casefold()
            for token in _WORD.findall(value)
            if len(token) > 1 or "\u3400" <= token <= "\u9fff"
        }
    )


def rank_references(
    request: PlanningRequest,
    bundle: PlanningBundleView,
    atlas_nodes: Iterable[dict[str, Any]] = (),
) -> list[RankedReference]:
    terms = lexical_terms(request.user_goal)
    explicit_paths = {
        path
        for path in request.allowed_paths
        if not any(character in path for character in "*?[")
    }
    atlas_record_refs = {
        str(reference)
        for node in atlas_nodes
        for reference in node.get("record_refs", node.get("source_record_refs", []))
        if isinstance(reference, str)
    }
    records = [
        *[(item, "claim") for item in bundle.claims],
        *[(item, "evidence") for item in bundle.evidence],
        *[(item, "source") for item in bundle.sources],
        *[(item, "conflict") for item in bundle.conflicts],
    ]
    ranked: list[RankedReference] = []
    for record, kind in records:
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            continue
        reasons: list[str] = []
        paths = _paths(record)
        if explicit_paths.intersection(paths):
            reasons.append("EXPLICIT_REFERENCE")
        if any(_within(path, allowed) for path in paths for allowed in bundle.allowed_paths):
            reasons.append("ALLOWED_SCOPE_PATH")
        if identifier in atlas_record_refs:
            reasons.append("GRAPH_ADJACENCY")
        if kind in {"claim", "evidence"} and _direct_links(record):
            reasons.append("CLAIM_EVIDENCE_DIRECT_LINK")
        text = _record_text(record)
        if any(term in text for term in terms):
            reasons.append("TEXT_LEXICAL_MATCH")
        if any(term in path.casefold() for term in terms for path in paths):
            reasons.append("SYMBOL_PATH_LEXICAL_MATCH")
        priority = _priority(reasons)
        ranked.append(
            RankedReference(
                reference_id=identifier,
                kind=kind,
                priority_tier=priority,
                reasons=sorted(set(reasons)),
                record=dict(record),
            )
        )
    ranked.sort(
        key=lambda item: (
            item.priority_tier,
            item.kind,
            item.reference_id,
        )
    )
    return ranked


def _priority(reasons: list[str]) -> int:
    ordered = (
        "EXPLICIT_REFERENCE",
        "ALLOWED_SCOPE_PATH",
        "IMPROVEMENT_CHAIN_LINK",
        "CHANGE_SCOPE_LINK",
        "CLAIM_EVIDENCE_DIRECT_LINK",
        "GRAPH_ADJACENCY",
        "SYMBOL_PATH_LEXICAL_MATCH",
        "TEXT_LEXICAL_MATCH",
    )
    for number, reason in enumerate(ordered):
        if reason in reasons:
            return number
    return len(ordered)


def _paths(record: dict[str, Any]) -> set[str]:
    paths = {
        item
        for item in record.get("bindings", {}).get("paths", [])
        if isinstance(item, str)
    }
    locator = record.get("locator")
    if isinstance(locator, dict) and isinstance(locator.get("path"), str):
        paths.add(locator["path"])
    return paths


def _direct_links(record: dict[str, Any]) -> bool:
    return any(
        isinstance(record.get(field), list) and bool(record[field])
        for field in (
            "evidence_refs",
            "counter_evidence_refs",
            "supports",
            "contradicts",
            "source_refs",
        )
    )


def _record_text(record: dict[str, Any]) -> str:
    values = []
    for field in (
        "id",
        "statement",
        "proposition",
        "question",
        "summary",
        "message",
    ):
        if isinstance(record.get(field), str):
            values.append(record[field])
    values.extend(_paths(record))
    return " ".join(values).casefold()


def _within(path: str, pattern: str) -> bool:
    prefix = pattern.removesuffix("/**").rstrip("/")
    return path == prefix or path.startswith(prefix + "/")
