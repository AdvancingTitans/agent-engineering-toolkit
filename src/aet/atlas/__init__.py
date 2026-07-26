"""Deterministic Evidence Atlas projections for Portable Evidence Bundles."""

from .model import (
    ATLAS_MANIFEST_SCHEMA,
    DIFF_SCHEMA,
    EDGE_TYPES,
    GRAPH_SCHEMA,
    NODE_STATUSES,
    NODE_TYPES,
    PERSPECTIVES,
    PERSPECTIVE_SCHEMA,
)
from .builder import build_evidence_graph
from .diff import affected_records, compare_evidence_atlases
from .perspectives import build_perspectives
from .hierarchy import build_hierarchy
from .queries import (
    AtlasQueryError,
    explain_node,
    get_children,
    get_node,
    get_node_subgraph,
    list_perspectives,
    trace_claim_support,
    trace_conflict,
    trace_freshness_impact,
)
from .render import (
    build_diagram_ir,
    render_document_fields,
    render_markdown_fields,
    render_mermaid,
    render_projection,
    try_render_mermaid,
    validate_mermaid,
)
from .storage import (
    AtlasStorageError,
    atlas_is_stale,
    build_evidence_atlas,
    default_atlas_path,
    load_evidence_atlas,
)
from .validator import (
    AtlasValidationError,
    validate_evidence_atlas,
    validate_evidence_graph,
)
from .viewer import serve_atlas, single_html, viewer_files

__all__ = [
    "ATLAS_MANIFEST_SCHEMA",
    "DIFF_SCHEMA",
    "EDGE_TYPES",
    "GRAPH_SCHEMA",
    "NODE_STATUSES",
    "NODE_TYPES",
    "PERSPECTIVES",
    "PERSPECTIVE_SCHEMA",
    "AtlasQueryError",
    "AtlasStorageError",
    "AtlasValidationError",
    "affected_records",
    "atlas_is_stale",
    "build_diagram_ir",
    "build_evidence_graph",
    "build_evidence_atlas",
    "build_hierarchy",
    "build_perspectives",
    "compare_evidence_atlases",
    "default_atlas_path",
    "explain_node",
    "get_children",
    "get_node",
    "get_node_subgraph",
    "list_perspectives",
    "load_evidence_atlas",
    "render_document_fields",
    "render_markdown_fields",
    "render_mermaid",
    "render_projection",
    "serve_atlas",
    "single_html",
    "trace_claim_support",
    "trace_conflict",
    "trace_freshness_impact",
    "try_render_mermaid",
    "validate_evidence_atlas",
    "validate_evidence_graph",
    "validate_mermaid",
    "viewer_files",
]
