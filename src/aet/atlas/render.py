"""Safe, deterministic Mermaid and Markdown projections for Evidence Atlas."""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .model import DEFAULT_GENERATION_POLICY, canonical_bytes


DIAGRAM_IR_SCHEMA = "aet-evidence-diagram-ir/1.0"

_DIAGRAM_TYPES = {
    "flowchart": "flowchart",
    "sequence": "sequenceDiagram",
    "sequencediagram": "sequenceDiagram",
    "timeline": "timeline",
    "state": "stateDiagram",
    "statediagram": "stateDiagram",
    "statediagramv2": "stateDiagram",
}
_DIRECTIONS = frozenset({"LR", "RL", "TD", "TB", "BT"})
_UNSAFE_OUTPUT = (
    (re.compile(r"(?im)^\s*click(?:\s|$)"), "click directives"),
    (re.compile(r"%%\s*\{"), "Mermaid init directives"),
    (re.compile(r"(?i)\b(?:https?|data|javascript|file):\s*(?://)?"), "URLs"),
    (re.compile(r"!\s*\["), "Markdown images"),
    (re.compile(r"(?is)<\s*/?\s*[a-z][^>]*>"), "HTML"),
)
_URL = re.compile(r"(?i)\b(?:https?|data|javascript|file):\s*(?://)?\S*")
_HTML_TAG = re.compile(r"(?is)<\s*/?\s*[a-z][^>]*>")
_INIT_DIRECTIVE = re.compile(r"%%\s*\{.*?\}%%", re.DOTALL)
_MARKDOWN_IMAGE = re.compile(r"!\s*\[[^\]]*\]\s*\([^)]*\)")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
_SPACE = re.compile(r"\s+")

_STATUS_LABELS = {
    "verified": "VERIFIED",
    "supported": "SUPPORTED",
    "partially_supported": "PARTIAL",
    "conflicted": "CONFLICT",
    "unsupported": "UNSUPPORTED",
    "unknown": "UNKNOWN",
    "stale": "STALE",
    "current": "CURRENT",
    "resolved": "RESOLVED",
    "not_applicable": "N/A",
    "recorded": "RECORDED",
}

_NODE_CLASS_DEFINITIONS = (
    "classDef verified fill:#dcfce7,stroke:#166534,color:#052e16,stroke-width:2px",
    "classDef observation fill:#e0f2fe,stroke:#0369a1,color:#082f49",
    "classDef candidate fill:#fef3c7,stroke:#92400e,color:#451a03,stroke-dasharray:5 3",
    "classDef supported fill:#ede9fe,stroke:#6d28d9,color:#2e1065,stroke-width:2px",
    "classDef conflict fill:#fee2e2,stroke:#b91c1c,color:#450a0a,stroke-width:2px",
    "classDef unknown fill:#f3f4f6,stroke:#4b5563,color:#111827,stroke-dasharray:5 3",
    "classDef stale fill:#ffedd5,stroke:#c2410c,color:#431407,stroke-dasharray:3 3",
    "classDef authorization fill:#ecfccb,stroke:#3f6212,color:#1a2e05",
    "classDef omitted fill:#f3f4f6,stroke:#6b7280,color:#111827,stroke-dasharray:2 3",
    "classDef evidenceDefault fill:#ffffff,stroke:#475569,color:#0f172a",
)

_EDGE_LABELS = {
    "ANSWERS": "answers",
    "DECOMPOSES_INTO": "decomposes into",
    "SUPPORTED_BY": "supported by",
    "PARTIALLY_SUPPORTED_BY": "partially supported by",
    "CONTRADICTED_BY": "contradicted by",
    "LIMITED_BY": "limited by",
    "DERIVED_FROM": "derived from",
    "OBSERVED_IN": "observed in",
    "PRODUCED_BY": "produced by",
    "EXECUTED_BY": "executed by",
    "CALLED": "called",
    "RETURNED": "returned",
    "APPLIES_TO": "applies to",
    "CHANGED": "changed",
    "DEPENDS_ON": "depends on",
    "VALIDATES": "validates",
    "INVALIDATED_BY": "invalidated by",
    "FRESH_FOR": "fresh for",
    "STALE_FOR": "stale for",
    "AUTHORIZED_BY": "authorized by",
    "VIOLATES": "violates",
    "CONSTRAINED_BY": "constrained by",
    "GROUPED_IN": "grouped in",
    "RESOLVES": "resolves",
    "LEAVES_UNKNOWN": "leaves unknown",
    "RECOMMENDS": "recommends",
    "PRECEDES": "precedes",
    "DUPLICATES": "duplicates",
}


class MermaidRenderError(ValueError):
    """Raised when a Diagram IR cannot be rendered without unsafe Mermaid."""


def safe_mermaid_id(canonical_id: str) -> str:
    """Return a stable renderer-owned ID that contains no source text."""
    digest = hashlib.sha256(str(canonical_id).encode("utf-8")).hexdigest()[:16]
    return f"N_{digest}"


def safe_label(value: Any, *, limit: int = 120) -> str:
    """Reduce untrusted Bundle text to one plain Mermaid label."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _INIT_DIRECTIVE.sub("[blocked directive]", text)
    text = _MARKDOWN_IMAGE.sub("[blocked image]", text)
    text = _HTML_TAG.sub("", text)
    text = _URL.sub("[blocked URL]", text)
    text = _CONTROL.sub(" ", text)
    text = text.replace("\\", "/").replace('"', "'")
    text = text.replace("<", "‹").replace(">", "›")
    text = text.replace(";", "；").replace("|", "｜").replace("%", "％")
    text = _SPACE.sub(" ", text).strip()
    if not text:
        text = "Untitled"
    if len(text) > limit:
        text = text[: max(1, limit - 1)].rstrip() + "…"
    return text


def build_diagram_ir(
    graph: Mapping[str, Any],
    *,
    node_ids: Iterable[str] | None = None,
    edge_ids: Iterable[str] | None = None,
    root_ids: Iterable[str] | None = None,
    diagram_type: str = "flowchart",
    direction: str = "LR",
    title: str | None = None,
    max_nodes: int | None = None,
) -> dict[str, Any]:
    """Build a bounded Diagram IR without changing the canonical graph."""
    normalized_type = _normalize_diagram_type(diagram_type)
    normalized_direction = str(direction).upper()
    if normalized_direction not in _DIRECTIONS:
        raise ValueError(f"unsupported Mermaid direction: {direction}")

    graph_nodes = {
        str(node["id"]): dict(node)
        for node in graph.get("nodes", [])
        if isinstance(node, Mapping) and isinstance(node.get("id"), str)
    }
    requested_nodes = set(node_ids) if node_ids is not None else set(graph_nodes)
    selected_source_nodes = {
        identifier: graph_nodes[identifier]
        for identifier in requested_nodes
        if identifier in graph_nodes
    }
    missing_nodes = sorted(requested_nodes - set(graph_nodes))

    graph_edges = [
        dict(edge)
        for edge in graph.get("edges", [])
        if isinstance(edge, Mapping)
        and isinstance(edge.get("id"), str)
        and isinstance(edge.get("from"), str)
        and isinstance(edge.get("to"), str)
    ]
    requested_edges = set(edge_ids) if edge_ids is not None else None
    candidate_edges = [
        edge
        for edge in graph_edges
        if (requested_edges is None or edge["id"] in requested_edges)
        and edge["from"] in selected_source_nodes
        and edge["to"] in selected_source_nodes
    ]
    missing_edges = (
        sorted(requested_edges - {edge["id"] for edge in graph_edges})
        if requested_edges is not None
        else []
    )

    policy = graph.get("generation_policy")
    policy_max = (
        policy.get("max_nodes_per_diagram")
        if isinstance(policy, Mapping)
        else DEFAULT_GENERATION_POLICY["max_nodes_per_diagram"]
    )
    effective_max = policy_max if max_nodes is None else max_nodes
    if not isinstance(effective_max, int) or isinstance(effective_max, bool):
        raise ValueError("max_nodes must be an integer")
    if effective_max < 1:
        raise ValueError("max_nodes must be positive")

    explicit_roots = set(root_ids or ())
    inferred_roots = _inferred_roots(selected_source_nodes, candidate_edges)
    all_roots = explicit_roots | inferred_roots
    ranked = sorted(
        selected_source_nodes.values(),
        key=lambda node: (-_retention_priority(node, all_roots), str(node["id"])),
    )
    diagnostics: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    aggregate_omitted = len(ranked) > effective_max and effective_max > 1
    source_limit = effective_max - 1 if aggregate_omitted else effective_max
    kept = ranked[:source_limit]
    if len(ranked) > source_limit:
        omitted = ranked[source_limit:]
        diagnostics.append(
            {
                "code": "DIAGRAM_TRUNCATED",
                "severity": "warning",
                "message": (
                    f"diagram retained {len(kept)} of {len(ranked)} canonical "
                    "nodes using root, Claim, conflict/UNKNOWN, and Verified "
                    "Evidence priority"
                ),
                "omitted_node_ids": [str(node["id"]) for node in omitted],
            }
        )
    if missing_nodes:
        diagnostics.append(
            {
                "code": "MISSING_DIAGRAM_NODE",
                "severity": "warning",
                "message": "requested canonical nodes were unavailable",
                "node_ids": missing_nodes,
            }
        )
    if missing_edges:
        diagnostics.append(
            {
                "code": "MISSING_DIAGRAM_EDGE",
                "severity": "warning",
                "message": "requested canonical edges were unavailable",
                "edge_ids": missing_edges,
            }
        )

    ir_nodes = [_node_ir(node) for node in kept]
    kept_ids = {str(node["id"]) for node in kept}
    if aggregate_omitted:
        omitted_id = f"node:diagram:omitted-{len(omitted)}"
        ir_nodes.append(
            {
                "id": safe_mermaid_id(omitted_id),
                "canonical_id": omitted_id,
                "type": "unknown",
                "status": "unknown",
                "label": f"[OMITTED] {len(omitted)} lower-priority nodes",
                "shape": "rectangle",
                "class": "omitted",
                "priority": -1,
                "synthetic": True,
                "timestamp": "UNKNOWN",
            }
        )

    ir_edges = [
        _edge_ir(edge)
        for edge in candidate_edges
        if edge["from"] in kept_ids and edge["to"] in kept_ids
    ]
    ir_edges.sort(
        key=lambda edge: (
            -int(edge["priority"]),
            str(edge["from"]),
            str(edge["to"]),
            str(edge["canonical_id"]),
        )
    )
    ir_nodes.sort(key=lambda node: (-int(node["priority"]), str(node["canonical_id"])))
    return {
        "schema_version": DIAGRAM_IR_SCHEMA,
        "diagram_type": normalized_type,
        "direction": normalized_direction,
        "title": safe_label(title or "Evidence Atlas", limit=100),
        "nodes": ir_nodes,
        "edges": ir_edges,
        "diagnostics": diagnostics,
        "projection": {
            "source_node_count": len(selected_source_nodes),
            "source_edge_count": len(candidate_edges),
            "rendered_node_count": len(ir_nodes),
            "rendered_edge_count": len(ir_edges),
            "max_nodes": effective_max,
            "omitted_node_count": len(omitted),
        },
    }


def render_mermaid(diagram_ir: Mapping[str, Any]) -> str:
    """Render a validated Diagram IR to deterministic Mermaid text."""
    diagram_type = _normalize_diagram_type(str(diagram_ir.get("diagram_type", "")))
    direction = str(diagram_ir.get("direction", "LR")).upper()
    if direction not in _DIRECTIONS:
        raise MermaidRenderError(f"unsupported Mermaid direction: {direction}")
    nodes = _validated_ir_nodes(diagram_ir.get("nodes"))
    edges = _validated_ir_edges(diagram_ir.get("edges"), nodes)
    title = safe_label(diagram_ir.get("title", "Evidence Atlas"), limit=100)

    if diagram_type == "flowchart":
        lines = _render_flowchart(nodes, edges, direction, title)
    elif diagram_type == "sequenceDiagram":
        lines = _render_sequence(nodes, edges, title)
    elif diagram_type == "timeline":
        lines = _render_timeline(nodes, title)
    else:
        lines = _render_state(nodes, edges, direction, title)
    content = "\n".join(lines).rstrip() + "\n"
    validate_mermaid(content)
    return content


def try_render_mermaid(diagram_ir: Mapping[str, Any]) -> dict[str, Any]:
    """Render Mermaid while preserving a serializable failure diagnostic."""
    try:
        return {"content": render_mermaid(diagram_ir), "diagnostics": []}
    except (MermaidRenderError, TypeError, ValueError) as exc:
        diagnostic = {
            "code": "MERMAID_RENDER_FAILED",
            "severity": "warning",
            "message": safe_label(str(exc), limit=240),
        }
        try:
            ir_bytes = canonical_bytes(diagram_ir)
        except (TypeError, ValueError):
            ir_bytes = repr(diagram_ir).encode("utf-8", errors="replace")
        return {
            "content": None,
            "diagnostics": [diagnostic],
            "diagram_error": {
                "schema_version": "aet-mermaid-render-error/1.0",
                "diagnostic": diagnostic,
                "diagram_ir_sha256": hashlib.sha256(ir_bytes).hexdigest(),
            },
        }


def validate_mermaid(content: str) -> None:
    """Reject capabilities outside AET's strict, local Mermaid subset."""
    if not isinstance(content, str) or not content.strip():
        raise MermaidRenderError("Mermaid output is empty")
    first = content.splitlines()[0].strip()
    if not (
        re.fullmatch(r"flowchart\s+(?:LR|RL|TD|TB|BT)", first)
        or first == "sequenceDiagram"
        or first == "timeline"
        or first == "stateDiagram-v2"
    ):
        raise MermaidRenderError("Mermaid output has an unsupported declaration")
    for pattern, capability in _UNSAFE_OUTPUT:
        if pattern.search(content):
            raise MermaidRenderError(f"unsafe Mermaid output contains {capability}")


def render_document_fields(
    node: Mapping[str, Any],
    graph: Mapping[str, Any],
) -> dict[str, str]:
    """Render deterministic node documentation without creating new evidence."""
    node_id = str(node.get("id", ""))
    nodes = {
        str(item["id"]): item
        for item in graph.get("nodes", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    edges = [
        edge
        for edge in graph.get("edges", [])
        if isinstance(edge, Mapping)
        and (edge.get("from") == node_id or edge.get("to") == node_id)
    ]
    related: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = (
        defaultdict(list)
    )
    for edge in edges:
        other_id = edge.get("to") if edge.get("from") == node_id else edge.get("from")
        other = nodes.get(str(other_id))
        if other is not None:
            related[str(edge.get("type", ""))].append((edge, other))

    title = _markdown_text(node.get("title", node_id or "Untitled"))
    summary = _markdown_text(node.get("summary", "No summary is available."))
    status = _markdown_text(node.get("status", "unknown"))
    freshness = _markdown_text(node.get("freshness", "unknown"))
    authority = _markdown_text(node.get("authority", "unknown"))
    question = _question_for(node)
    fields = {
        "description.md": f"# {title}\n\n{summary}\n",
        "question.md": f"# Question\n\n{_markdown_text(question)}\n",
        "context.md": (
            "# Context\n\n"
            f"- Type: `{_markdown_code(node.get('type', 'unknown'))}`\n"
            f"- Status: `{_markdown_code(status)}`\n"
            f"- Authority: `{_markdown_code(authority)}`\n"
            f"- Importance: `{_markdown_code(node.get('importance', 'normal'))}`\n"
        ),
        "evidence.md": _evidence_document(node, related),
        "counter-evidence.md": _relation_document(
            "Counter-evidence",
            related,
            {"CONTRADICTED_BY", "VIOLATES", "INVALIDATED_BY"},
            "No counter-evidence relation is recorded for this node.",
        ),
        "freshness.md": _freshness_document(node, related, freshness),
        "constraints.md": _relation_document(
            "Constraints",
            related,
            {"CONSTRAINED_BY", "AUTHORIZED_BY", "APPLIES_TO"},
            "No additional constraint relation is recorded for this node.",
        ),
        "concerns.md": _concerns_document(node, related),
        "unknowns.md": _relation_document(
            "Unknowns",
            related,
            {"LEAVES_UNKNOWN", "LIMITED_BY"},
            (
                "This node is explicitly UNKNOWN."
                if node.get("status") == "unknown" or node.get("type") == "unknown"
                else "No explicit UNKNOWN relation is recorded for this node."
            ),
        ),
        "actions.md": _relation_document(
            "Actions",
            related,
            {"RECOMMENDS", "RESOLVES"},
            "No action is authorized or recommended by this projection.",
        ),
    }
    source_refs = node.get("source_refs")
    provenance = {
        "node_id": node_id,
        "source_refs": list(source_refs) if isinstance(source_refs, list) else [],
        "edge_refs": sorted(
            str(edge["id"]) for edge in edges if isinstance(edge.get("id"), str)
        ),
        "generator": {
            "name": "aet-atlas",
            "mode": "deterministic",
            "authoritative_narrative": False,
        },
    }
    fields["provenance.json"] = (
        json.dumps(provenance, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    fields["node.json"] = (
        json.dumps(dict(node), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return fields


def render_projection(
    graph: Mapping[str, Any],
    **diagram_options: Any,
) -> dict[str, Any]:
    """Build IR, Mermaid, Markdown fields, and non-fatal diagnostics together."""
    diagram_ir = build_diagram_ir(graph, **diagram_options)
    rendered = try_render_mermaid(diagram_ir)
    nodes_by_id = {
        str(node["id"]): node
        for node in graph.get("nodes", [])
        if isinstance(node, Mapping) and isinstance(node.get("id"), str)
    }
    documents = {
        str(item["canonical_id"]): render_document_fields(
            nodes_by_id[str(item["canonical_id"])], graph
        )
        for item in diagram_ir["nodes"]
        if not item.get("synthetic") and str(item["canonical_id"]) in nodes_by_id
    }
    diagnostics = [
        *diagram_ir.get("diagnostics", []),
        *rendered.get("diagnostics", []),
    ]
    files = {
        "diagram-ir.json": (
            json.dumps(
                diagram_ir,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ),
        "diagnostics.json": (
            json.dumps(
                diagnostics,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ),
    }
    if rendered.get("content") is not None:
        files["diagram.mmd"] = str(rendered["content"])
    else:
        files["diagram.mmd"] = (
            "flowchart LR\n"
            '    N_RENDER_ERROR["[UNKNOWN] Mermaid projection unavailable; '
            'use Diagram IR and list view."]\n'
            "    classDef unknown fill:#f3f4f6,stroke:#4b5563,"
            "color:#111827,stroke-dasharray:5 3\n"
            "    class N_RENDER_ERROR unknown\n"
        )
    for item in diagram_ir["nodes"]:
        canonical_id = str(item["canonical_id"])
        if item.get("synthetic") or canonical_id not in documents:
            continue
        node_directory = str(item["id"]).lower()
        for filename, content in documents[canonical_id].items():
            files[f"children/{node_directory}/{filename}"] = content
    result = {
        "diagram_ir": diagram_ir,
        "diagram": rendered.get("content"),
        "documents": documents,
        "diagnostics": diagnostics,
        "files": files,
    }
    if "diagram_error" in rendered:
        result["diagram_error"] = rendered["diagram_error"]
        result["files"]["diagram-error.json"] = (
            json.dumps(
                rendered["diagram_error"],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    return result


def render_markdown_fields(
    node: Mapping[str, Any],
    graph: Mapping[str, Any],
) -> dict[str, str]:
    """Compatibility alias for callers using the design document terminology."""
    return render_document_fields(node, graph)


def _normalize_diagram_type(value: str) -> str:
    key = value.replace("-", "").replace("_", "").lower()
    try:
        return _DIAGRAM_TYPES[key]
    except KeyError as exc:
        raise ValueError(f"unsupported Mermaid diagram type: {value}") from exc


def _inferred_roots(
    nodes: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> set[str]:
    incoming = {str(edge["to"]) for edge in edges}
    return {
        identifier
        for identifier, node in nodes.items()
        if identifier not in incoming
        and (
            node.get("type") in {"intent", "run", "finding", "claim"}
            or (
                isinstance(node.get("attributes"), Mapping)
                and node["attributes"].get("root") is True
            )
        )
    }


def _retention_priority(node: Mapping[str, Any], root_ids: set[str]) -> int:
    identifier = str(node.get("id", ""))
    node_type = str(node.get("type", ""))
    status = str(node.get("status", ""))
    if identifier in root_ids:
        category = 5
    elif node_type in {"claim", "subclaim", "finding"}:
        category = 4
    elif node_type in {"conflict", "unknown"} or status in {"conflicted", "unknown"}:
        category = 3
    elif node_type in {"verified_evidence", "proof"} or status == "verified":
        category = 2
    else:
        category = 1
    importance = {"high": 30, "normal": 20, "low": 10}.get(
        str(node.get("importance", "normal")), 0
    )
    complexity = node.get("complexity")
    score = (
        int(complexity.get("score", 0))
        if isinstance(complexity, Mapping)
        and isinstance(complexity.get("score", 0), int)
        else 0
    )
    return category * 10000 + importance * 10 + min(max(score, 0), 99)


def _node_ir(node: Mapping[str, Any]) -> dict[str, Any]:
    status = str(node.get("status", "recorded"))
    node_type = str(node.get("type", "artifact"))
    prefix = _semantic_prefix(node_type, status)
    label = safe_label(node.get("title") or node.get("summary") or node.get("id"))
    if prefix:
        label = safe_label(f"[{prefix}] {label}")
    node_class, shape = _node_presentation(node_type, status)
    attributes = node.get("attributes")
    checked_at = (
        attributes.get("checked_at")
        if isinstance(attributes, Mapping)
        else None
    )
    return {
        "id": safe_mermaid_id(str(node["id"])),
        "canonical_id": str(node["id"]),
        "type": node_type,
        "status": status,
        "label": label,
        "shape": shape,
        "class": node_class,
        "priority": _retention_priority(node, set()),
        "synthetic": False,
        "timestamp": (
            safe_label(checked_at).replace(":", "-")
            if isinstance(checked_at, str) and checked_at.strip()
            else "UNKNOWN"
        ),
    }


def _semantic_prefix(node_type: str, status: str) -> str:
    if node_type == "observation":
        return "OBSERVATION"
    if node_type == "evidence_candidate":
        return "CANDIDATE"
    if node_type == "verified_evidence":
        return "VERIFIED"
    if node_type == "authorization":
        return "AUTH"
    if node_type == "conflict":
        return "CONFLICT"
    if node_type == "unknown":
        return "UNKNOWN"
    return _STATUS_LABELS.get(status, status.upper().replace("_", " "))


def _node_presentation(node_type: str, status: str) -> tuple[str, str]:
    if node_type == "observation":
        return ("observation", "rounded")
    if node_type == "evidence_candidate":
        return ("candidate", "subroutine")
    if node_type == "authorization":
        return ("authorization", "parallelogram")
    if node_type == "conflict" or status == "conflicted":
        return ("conflict", "diamond")
    if node_type == "unknown" or status == "unknown":
        return ("unknown", "rectangle")
    if status == "stale":
        return ("stale", "rectangle")
    if node_type == "verified_evidence" or status == "verified":
        return ("verified", "rectangle")
    if node_type in {"claim", "subclaim", "finding"}:
        return ("supported", "hexagon")
    return ("evidenceDefault", "rectangle")


def _edge_ir(edge: Mapping[str, Any]) -> dict[str, Any]:
    render = edge.get("render")
    edge_type = str(edge.get("type", "RELATED"))
    label = (
        render.get("label")
        if isinstance(render, Mapping) and render.get("label")
        else _EDGE_LABELS.get(edge_type, edge_type.lower().replace("_", " "))
    )
    priority = (
        render.get("priority", 50)
        if isinstance(render, Mapping)
        else 50
    )
    if not isinstance(priority, int) or isinstance(priority, bool):
        priority = 50
    if edge_type in {"CONTRADICTED_BY", "INVALIDATED_BY", "VIOLATES", "STALE_FOR"}:
        line = "dotted"
    elif edge_type in {"SUPPORTED_BY", "VALIDATES", "FRESH_FOR", "AUTHORIZED_BY"}:
        line = "strong"
    else:
        line = "solid"
    return {
        "id": safe_mermaid_id(str(edge["id"])),
        "canonical_id": str(edge["id"]),
        "from": safe_mermaid_id(str(edge["from"])),
        "to": safe_mermaid_id(str(edge["to"])),
        "type": edge_type,
        "label": safe_label(label, limit=80),
        "line": line,
        "priority": priority,
    }


def _validated_ir_nodes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise MermaidRenderError("Diagram IR nodes must be a sequence")
    result: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise MermaidRenderError("Diagram IR contains an invalid node")
        identifier = str(item.get("id", ""))
        if not re.fullmatch(r"N_[0-9a-f]{16}", identifier):
            raise MermaidRenderError("Diagram IR contains an unsafe node ID")
        if identifier in identifiers:
            raise MermaidRenderError("Diagram IR contains a duplicate node ID")
        identifiers.add(identifier)
        result.append(
            {
                **dict(item),
                "id": identifier,
                "label": safe_label(item.get("label")),
                "shape": str(item.get("shape", "rectangle")),
                "class": str(item.get("class", "evidenceDefault")),
            }
        )
    return result


def _validated_ir_edges(
    value: Any,
    nodes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise MermaidRenderError("Diagram IR edges must be a sequence")
    node_ids = {str(node["id"]) for node in nodes}
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise MermaidRenderError("Diagram IR contains an invalid edge")
        from_id = str(item.get("from", ""))
        to_id = str(item.get("to", ""))
        if from_id not in node_ids or to_id not in node_ids:
            raise MermaidRenderError("Diagram IR edge references an unavailable node")
        line = str(item.get("line", "solid"))
        if line not in {"solid", "dotted", "strong"}:
            raise MermaidRenderError("Diagram IR contains an unsupported edge line")
        result.append(
            {
                **dict(item),
                "from": from_id,
                "to": to_id,
                "label": safe_label(item.get("label"), limit=80),
                "line": line,
            }
        )
    return result


def _render_flowchart(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    direction: str,
    title: str,
) -> list[str]:
    lines = [f"flowchart {direction}", f"    %% {title}"]
    allowed_classes = {
        definition.split()[1]
        for definition in _NODE_CLASS_DEFINITIONS
    }
    for node in nodes:
        identifier = str(node["id"])
        label = str(node["label"])
        lines.append(f"    {_flowchart_node(identifier, label, str(node['shape']))}")
    for edge in edges:
        arrow = {"solid": "-->", "dotted": "-.->", "strong": "==>"}[str(edge["line"])]
        lines.append(
            f'    {edge["from"]} {arrow}|"{edge["label"]}"| {edge["to"]}'
        )
    lines.extend(f"    {definition}" for definition in _NODE_CLASS_DEFINITIONS)
    for node in nodes:
        node_class = str(node["class"])
        if node_class not in allowed_classes:
            raise MermaidRenderError("Diagram IR contains an unsupported node class")
        lines.append(f'    class {node["id"]} {node_class}')
    return lines


def _flowchart_node(identifier: str, label: str, shape: str) -> str:
    if shape == "rounded":
        return f'{identifier}("{label}")'
    if shape == "subroutine":
        return f'{identifier}[["{label}"]]'
    if shape == "diamond":
        return f'{identifier}{{"{label}"}}'
    if shape == "hexagon":
        return f'{identifier}{{{{"{label}"}}}}'
    if shape == "parallelogram":
        return f'{identifier}[/"{label}"/]'
    if shape == "rectangle":
        return f'{identifier}["{label}"]'
    raise MermaidRenderError(f"unsupported flowchart node shape: {shape}")


def _render_sequence(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    title: str,
) -> list[str]:
    lines = ["sequenceDiagram", f"    %% {title}"]
    for node in nodes:
        lines.append(f'    participant {node["id"]} as {node["label"]}')
    for edge in edges:
        arrow = "-->>" if edge["line"] == "dotted" else "->>"
        lines.append(
            f'    {edge["from"]}{arrow}{edge["to"]}: {edge["label"]}'
        )
    return lines


def _render_timeline(
    nodes: Sequence[Mapping[str, Any]],
    title: str,
) -> list[str]:
    lines = ["timeline", f"    title {title}"]
    for node in nodes:
        lines.append(
            f'    {node.get("timestamp") or "UNKNOWN"} : {node["label"]}'
        )
    return lines


def _render_state(
    nodes: Sequence[Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    direction: str,
    title: str,
) -> list[str]:
    state_direction = "LR" if direction in {"LR", "RL"} else "TB"
    lines = [
        "stateDiagram-v2",
        f"    %% {title}",
        f"    direction {state_direction}",
    ]
    for node in nodes:
        lines.append(f'    state "{node["label"]}" as {node["id"]}')
    for edge in edges:
        lines.append(f'    {edge["from"]} --> {edge["to"]}: {edge["label"]}')
    return lines


def _markdown_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _INIT_DIRECTIVE.sub("[blocked directive]", text)
    text = _MARKDOWN_IMAGE.sub("[blocked image]", text)
    text = _URL.sub("[blocked URL]", text)
    text = html.escape(_CONTROL.sub(" ", text), quote=False)
    return _SPACE.sub(" ", text).strip() or "Unknown"


def _markdown_code(value: Any) -> str:
    return _markdown_text(value).replace("`", "'")


def _question_for(node: Mapping[str, Any]) -> str:
    attributes = node.get("attributes")
    if isinstance(attributes, Mapping):
        for key in ("question", "question_answered"):
            value = attributes.get(key)
            if isinstance(value, str) and value.strip():
                return value
    node_type = str(node.get("type", "node")).replace("_", " ")
    return f"What does this {node_type} establish, and what limits its applicability?"


def _relation_document(
    heading: str,
    related: Mapping[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]],
    relation_types: set[str],
    empty_message: str,
) -> str:
    rows: list[tuple[str, str, str]] = []
    for relation_type in sorted(relation_types):
        for edge, other in related.get(relation_type, []):
            rows.append(
                (
                    relation_type,
                    str(other.get("title") or other.get("id") or "Unknown"),
                    str(edge.get("id", "")),
                )
            )
    lines = [f"# {heading}", ""]
    if not rows:
        lines.append(_markdown_text(empty_message))
    else:
        for relation_type, title, edge_id in sorted(rows):
            lines.append(
                f"- `{_markdown_code(relation_type)}` "
                f"{_markdown_text(title)} "
                f"(`{_markdown_code(edge_id)}`)"
            )
    return "\n".join(lines).rstrip() + "\n"


def _freshness_document(
    node: Mapping[str, Any],
    related: Mapping[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]],
    freshness: str,
) -> str:
    lines = ["# Freshness", "", f"- Current applicability: `{_markdown_code(freshness)}`"]
    rows: list[tuple[str, str]] = []
    for relation_type in ("FRESH_FOR", "STALE_FOR", "INVALIDATED_BY"):
        for _edge, other in related.get(relation_type, []):
            rows.append(
                (relation_type, str(other.get("title") or other.get("id") or "Unknown"))
            )
    for relation_type, title in sorted(rows):
        lines.append(f"- `{relation_type}` {_markdown_text(title)}")
    if not rows:
        lines.append("- No freshness transition relation is recorded.")
    return "\n".join(lines).rstrip() + "\n"


def _evidence_document(
    node: Mapping[str, Any],
    related: Mapping[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]],
) -> str:
    content = _relation_document(
        "Evidence",
        related,
        {
            "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY",
            "VALIDATES",
            "DERIVED_FROM",
            "PRODUCED_BY",
            "OBSERVED_IN",
        },
        "No supporting relation is recorded for this node.",
    ).rstrip()
    attributes = node.get("attributes")
    does_not_prove = (
        attributes.get("does_not_prove", [])
        if isinstance(attributes, Mapping)
        else []
    )
    if node.get("type") == "proof":
        lines = [content, "", "## Does not prove", ""]
        if does_not_prove:
            lines.extend(
                f"- {_markdown_text(item)}" for item in does_not_prove
            )
        else:
            lines.append("- No explicit limitation is recorded.")
        return "\n".join(lines).rstrip() + "\n"
    return content + "\n"


def _concerns_document(
    node: Mapping[str, Any],
    related: Mapping[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]],
) -> str:
    concerns: list[str] = []
    status = str(node.get("status", ""))
    freshness = str(node.get("freshness", ""))
    if status in {"conflicted", "unsupported", "unknown"}:
        concerns.append(f"Node status is `{_markdown_code(status)}`.")
    if freshness == "stale" or status == "stale":
        concerns.append("Current applicability is `stale`.")
    attributes = node.get("attributes")
    does_not_prove = (
        attributes.get("does_not_prove", [])
        if isinstance(attributes, Mapping)
        else []
    )
    concerns.extend(
        f"Does not prove: {_markdown_text(item)}"
        for item in does_not_prove
    )
    for relation_type in ("CONTRADICTED_BY", "INVALIDATED_BY", "LIMITED_BY", "VIOLATES"):
        for _edge, other in related.get(relation_type, []):
            title = other.get("title") or other.get("id") or "Unknown"
            concerns.append(f"`{relation_type}` {_markdown_text(title)}")
    lines = ["# Concerns", ""]
    lines.extend(f"- {item}" for item in concerns)
    if not concerns:
        lines.append("No explicit concern is recorded for this node.")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "DIAGRAM_IR_SCHEMA",
    "MermaidRenderError",
    "build_diagram_ir",
    "render_document_fields",
    "render_markdown_fields",
    "render_mermaid",
    "render_projection",
    "safe_label",
    "safe_mermaid_id",
    "try_render_mermaid",
    "validate_mermaid",
]
