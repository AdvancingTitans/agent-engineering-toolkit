"""Dependency-free MCP convenience layer for portable AET artifacts."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any, Mapping, TextIO

from . import __version__
from .bundle import (
    BundleError,
    compile_bundle,
    validate_bundle,
    validate_review_result,
)
from .investigation import (
    investigate_run,
    validate_investigation_result,
    write_investigation_result,
)
from .run_normalization import (
    load_normalized_run,
    normalize_run,
    write_normalized_run,
)
from .atlas.queries import (
    get_children,
    get_node,
    list_perspectives,
    trace_claim_support,
    trace_conflict,
    trace_freshness_impact,
)
from .atlas.render import render_projection
from .atlas.storage import load_evidence_atlas
from .atlas.validator import validate_evidence_atlas


MCP_PROTOCOL_VERSION = "2025-06-18"


def _path_schema(*required: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(required),
        "properties": {
            name: {"type": "string", "minLength": 1} for name in required
        },
    }


def _graph_trace_schema(identifier: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["atlas", "bundle", identifier],
        "properties": {
            "atlas": {"type": "string", "minLength": 1},
            "bundle": {"type": "string", "minLength": 1},
            identifier: {"type": "string", "minLength": 1},
            "depth": {"type": "integer", "minimum": 1, "maximum": 8},
            "max_nodes": {"type": "integer", "minimum": 1, "maximum": 200},
            "max_bytes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
            },
        },
    }


_TOOLS = [
    {
        "name": "aet_run_normalize",
        "description": "Normalize one supported local Agent run without executing it.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["source", "input", "output"],
            "properties": {
                "source": {"enum": ["codex", "claude-code"]},
                "input": {"type": "string", "minLength": 1},
                "output": {"type": "string", "minLength": 1},
                "run_group_id": {"type": "string", "minLength": 1},
            },
        },
    },
    {
        "name": "aet_investigation_create",
        "description": "Create one read-only investigation with optional explicit deterministic Proof receipts.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["request", "run", "output"],
            "properties": {
                "request": {"type": "string", "minLength": 1},
                "run": {"type": "string", "minLength": 1},
                "output": {"type": "string", "minLength": 1},
                "workspace": {"type": "string", "minLength": 1},
                "proofs": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
            },
        },
    },
    {
        "name": "aet_investigation_get",
        "description": "Read one local portable investigation result.",
        "inputSchema": _path_schema("investigation"),
    },
    {
        "name": "aet_bundle_create",
        "description": "Compile one complete local Bundle payload into a non-overwriting directory.",
        "inputSchema": _path_schema("payload", "output"),
    },
    {
        "name": "aet_bundle_get_index",
        "description": "Validate a Bundle and return its portable Index.",
        "inputSchema": _path_schema("bundle"),
    },
    {
        "name": "aet_bundle_get_claim",
        "description": "Validate a Bundle and resolve one Claim ID.",
        "inputSchema": _path_schema("bundle", "claim_id"),
    },
    {
        "name": "aet_bundle_get_evidence",
        "description": "Validate a Bundle and resolve one Evidence ID.",
        "inputSchema": _path_schema("bundle", "evidence_id"),
    },
    {
        "name": "aet_bundle_get_blob",
        "description": "Validate a Bundle and return one Blob as base64.",
        "inputSchema": _path_schema("bundle", "blob_ref"),
    },
    {
        "name": "aet_bundle_validate_review",
        "description": "Validate one structured Review Result against a Bundle.",
        "inputSchema": _path_schema("bundle", "review"),
    },
    {
        "name": "aet_graph_list_perspectives",
        "description": "List the eight deterministic Perspectives in a validated local Evidence Atlas.",
        "inputSchema": _path_schema("atlas", "bundle"),
    },
    {
        "name": "aet_graph_get_root",
        "description": "Return the root nodes for one validated Evidence Atlas Perspective.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["atlas", "bundle", "perspective"],
            "properties": {
                "atlas": {"type": "string", "minLength": 1},
                "bundle": {"type": "string", "minLength": 1},
                "perspective": {"type": "string", "minLength": 1},
            },
        },
    },
    {
        "name": "aet_graph_get_node",
        "description": "Resolve one canonical node in a validated local Evidence Atlas.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["atlas", "bundle", "node_id"],
            "properties": {
                "atlas": {"type": "string", "minLength": 1},
                "bundle": {"type": "string", "minLength": 1},
                "node_id": {"type": "string", "minLength": 1},
            },
        },
    },
    {
        "name": "aet_graph_get_children",
        "description": "Return bounded direct children for one Atlas node and Perspective.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["atlas", "bundle", "node_id", "perspective"],
            "properties": {
                "atlas": {"type": "string", "minLength": 1},
                "bundle": {"type": "string", "minLength": 1},
                "node_id": {"type": "string", "minLength": 1},
                "perspective": {"type": "string", "minLength": 1},
                "max_nodes": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
    {
        "name": "aet_graph_trace_claim",
        "description": "Trace bounded support and counter-evidence paths for one Claim.",
        "inputSchema": _graph_trace_schema("claim_id"),
    },
    {
        "name": "aet_graph_trace_conflict",
        "description": "Trace one bounded Conflict and its unresolved paths.",
        "inputSchema": _graph_trace_schema("conflict_id"),
    },
    {
        "name": "aet_graph_trace_freshness",
        "description": "Trace bounded Freshness impact from Evidence or Proof to Claims.",
        "inputSchema": _graph_trace_schema("node_id"),
    },
    {
        "name": "aet_graph_render_mermaid",
        "description": "Render one validated Perspective as strict, offline-safe Mermaid.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["atlas", "bundle", "perspective"],
            "properties": {
                "atlas": {"type": "string", "minLength": 1},
                "bundle": {"type": "string", "minLength": 1},
                "perspective": {"type": "string", "minLength": 1},
                "max_nodes": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    },
]


def handle_request(request: Mapping[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC request without changing reviewer judgment."""
    if not isinstance(request, Mapping):
        return _rpc_error(None, -32600, "request must be an object")
    identifier = request.get("id")
    method = request.get("method")
    if method == "notifications/initialized":
        return None
    if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return _rpc_error(identifier, -32600, "invalid JSON-RPC request")
    if method == "initialize":
        return _rpc_result(
            identifier,
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "agent-engineering-toolkit",
                    "version": __version__,
                },
            },
        )
    if method == "ping":
        return _rpc_result(identifier, {})
    if method == "tools/list":
        return _rpc_result(identifier, {"tools": _TOOLS})
    if method != "tools/call":
        return _rpc_error(identifier, -32601, f"unsupported method: {method}")
    params = request.get("params")
    if not isinstance(params, dict):
        return _rpc_error(identifier, -32602, "tools/call params must be an object")
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return _rpc_error(identifier, -32602, "tool name and arguments are required")
    try:
        result = call_tool(name, arguments)
    except (BundleError, OSError, TypeError, ValueError) as error:
        return _rpc_result(
            identifier,
            {
                "content": [{"type": "text", "text": str(error)}],
                "isError": True,
            },
        )
    return _rpc_result(
        identifier,
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        result,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ),
                }
            ],
            "structuredContent": result,
            "isError": False,
        },
    )


def call_tool(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Call one bounded MCP tool."""
    if name == "aet_run_normalize":
        _exact_arguments(arguments, {"source", "input", "output"}, {"run_group_id"})
        output = Path(_string(arguments, "output"))
        _require_new_output(output)
        result = normalize_run(
            _string(arguments, "source"),
            Path(_string(arguments, "input")),
            run_group_id=_optional_string(arguments, "run_group_id"),
        )
        write_normalized_run(result, output)
        return {"manifest": result["manifest"], "output": str(output)}
    if name == "aet_investigation_create":
        _exact_arguments(
            arguments,
            {"request", "run", "output"},
            {"workspace", "proofs"},
        )
        output = Path(_string(arguments, "output"))
        _require_new_output(output)
        request = _strict_json_object(
            Path(_string(arguments, "request")),
            "investigation request",
        )
        normalized = load_normalized_run(Path(_string(arguments, "run")))
        proofs = arguments.get("proofs", [])
        if not isinstance(proofs, list) or any(
            not isinstance(item, str) or not item for item in proofs
        ):
            raise ValueError("proofs must be an array of non-empty paths")
        workspace_value = arguments.get("workspace")
        if workspace_value is not None and (
            not isinstance(workspace_value, str) or not workspace_value
        ):
            raise ValueError("workspace must be a non-empty path")
        result = investigate_run(
            request,
            normalized["records"],
            workspace=Path(workspace_value) if workspace_value is not None else None,
            proof_paths=tuple(Path(item) for item in proofs),
        )
        write_investigation_result(result, output)
        return result
    if name == "aet_investigation_get":
        _exact_arguments(arguments, {"investigation"})
        return validate_investigation_result(
            _strict_json_object(
                Path(_string(arguments, "investigation")),
                "investigation result",
            )
        )
    if name == "aet_bundle_create":
        _exact_arguments(arguments, {"payload", "output"})
        output = Path(_string(arguments, "output"))
        _require_new_output(output)
        payload = _strict_json_object(
            Path(_string(arguments, "payload")),
            "Bundle compilation payload",
        )
        bundle = compile_bundle(payload, output)
        return {
            "bundle_id": bundle["manifest"]["bundle"]["id"],
            "output": str(output),
        }
    if name == "aet_bundle_get_index":
        _exact_arguments(arguments, {"bundle"})
        return validate_bundle(Path(_string(arguments, "bundle")))["index"]
    if name == "aet_bundle_get_claim":
        _exact_arguments(arguments, {"bundle", "claim_id"})
        bundle = validate_bundle(Path(_string(arguments, "bundle")))
        return _resolve(bundle["claims"], _string(arguments, "claim_id"), "Claim")
    if name == "aet_bundle_get_evidence":
        _exact_arguments(arguments, {"bundle", "evidence_id"})
        bundle = validate_bundle(Path(_string(arguments, "bundle")))
        return _resolve(
            bundle["evidence"],
            _string(arguments, "evidence_id"),
            "Evidence",
        )
    if name == "aet_bundle_get_blob":
        _exact_arguments(arguments, {"bundle", "blob_ref"})
        bundle = validate_bundle(Path(_string(arguments, "bundle")))
        blob_ref = _string(arguments, "blob_ref")
        blob = bundle["blobs"].get(blob_ref)
        if not isinstance(blob, bytes):
            raise BundleError("reference_error", f"unknown Blob reference: {blob_ref}")
        return {
            "blob_ref": blob_ref,
            "bytes": len(blob),
            "content_base64": base64.b64encode(blob).decode("ascii"),
        }
    if name == "aet_bundle_validate_review":
        _exact_arguments(arguments, {"bundle", "review"})
        return validate_review_result(
            Path(_string(arguments, "bundle")),
            Path(_string(arguments, "review")),
        )
    if name == "aet_graph_list_perspectives":
        _exact_arguments(arguments, {"atlas", "bundle"})
        graph = _validated_graph(arguments)
        return {"perspectives": list_perspectives(graph)}
    if name == "aet_graph_get_root":
        _exact_arguments(arguments, {"atlas", "bundle", "perspective"})
        graph = _validated_graph(arguments)
        perspective_id = _string(arguments, "perspective")
        perspective = _perspective(graph, perspective_id)
        return {
            "perspective": perspective_id,
            "roots": [
                get_node(graph, identifier)
                for identifier in perspective["root_node_ids"]
            ],
        }
    if name == "aet_graph_get_node":
        _exact_arguments(arguments, {"atlas", "bundle", "node_id"})
        return get_node(
            _validated_graph(arguments),
            _string(arguments, "node_id"),
        )
    if name == "aet_graph_get_children":
        _exact_arguments(
            arguments,
            {"atlas", "bundle", "node_id", "perspective"},
            {"max_nodes"},
        )
        return {
            "children": get_children(
                _validated_graph(arguments),
                _string(arguments, "node_id"),
                perspective=_string(arguments, "perspective"),
                max_nodes=_bounded_int(arguments, "max_nodes", 25, 200),
            )
        }
    if name == "aet_graph_trace_claim":
        _exact_arguments(
            arguments,
            {"atlas", "bundle", "claim_id"},
            {"depth", "max_nodes", "max_bytes"},
        )
        return trace_claim_support(
            _validated_graph(arguments),
            _string(arguments, "claim_id"),
            depth=_bounded_int(arguments, "depth", 4, 8),
            max_nodes=_bounded_int(arguments, "max_nodes", 100, 200),
            max_bytes=_bounded_int(arguments, "max_bytes", 524_288, 1_000_000),
        )
    if name == "aet_graph_trace_conflict":
        _exact_arguments(
            arguments,
            {"atlas", "bundle", "conflict_id"},
            {"depth", "max_nodes", "max_bytes"},
        )
        return trace_conflict(
            _validated_graph(arguments),
            _string(arguments, "conflict_id"),
            depth=_bounded_int(arguments, "depth", 3, 8),
            max_nodes=_bounded_int(arguments, "max_nodes", 75, 200),
            max_bytes=_bounded_int(arguments, "max_bytes", 393_216, 1_000_000),
        )
    if name == "aet_graph_trace_freshness":
        _exact_arguments(
            arguments,
            {"atlas", "bundle", "node_id"},
            {"depth", "max_nodes", "max_bytes"},
        )
        return trace_freshness_impact(
            _validated_graph(arguments),
            _string(arguments, "node_id"),
            depth=_bounded_int(arguments, "depth", 4, 8),
            max_nodes=_bounded_int(arguments, "max_nodes", 100, 200),
            max_bytes=_bounded_int(arguments, "max_bytes", 524_288, 1_000_000),
        )
    if name == "aet_graph_render_mermaid":
        _exact_arguments(
            arguments,
            {"atlas", "bundle", "perspective"},
            {"max_nodes"},
        )
        graph = _validated_graph(arguments)
        perspective = _perspective(graph, _string(arguments, "perspective"))
        projection = render_projection(
            graph,
            node_ids=perspective["node_ids"],
            edge_ids=perspective["edge_ids"],
            diagram_type=perspective["diagram_type"],
            direction=perspective["direction"],
            max_nodes=_bounded_int(arguments, "max_nodes", 25, 200),
            root_ids=perspective["root_node_ids"],
        )
        return {
            "perspective": perspective["id"],
            "mermaid": projection.get("diagram") or "",
            "diagnostics": projection["diagnostics"],
        }
    raise ValueError(f"unsupported MCP tool: {name}")


def serve_stdio(
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    """Serve newline-delimited MCP JSON-RPC over stdio."""
    source = input_stream or sys.stdin
    destination = output_stream or sys.stdout
    for line in source:
        if not line.strip():
            continue
        try:
            request = json.loads(
                line,
                parse_constant=lambda item: (_raise_nonfinite(item)),
                object_pairs_hook=_unique_object,
            )
            response = handle_request(request)
        except (json.JSONDecodeError, ValueError) as error:
            response = _rpc_error(None, -32700, f"invalid JSON: {error}")
        if response is not None:
            destination.write(
                json.dumps(
                    response,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                + "\n"
            )
            destination.flush()


def _resolve(records: list[dict[str, Any]], identifier: str, label: str) -> dict[str, Any]:
    for record in records:
        if record.get("id") == identifier:
            return record
    raise BundleError("reference_error", f"unknown {label} ID: {identifier}")


def _exact_arguments(
    arguments: Mapping[str, Any],
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    if not required <= set(arguments) or not set(arguments) <= allowed:
        raise ValueError("MCP tool arguments do not match the declared schema")


def _string(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _optional_string(arguments: Mapping[str, Any], name: str) -> str | None:
    if name not in arguments:
        return None
    return _string(arguments, name)


def _bounded_int(
    arguments: Mapping[str, Any],
    name: str,
    default: int,
    maximum: int,
) -> int:
    value = arguments.get(name, default)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
        or value > maximum
    ):
        raise ValueError(f"{name} must be between 1 and {maximum}")
    return value


def _validated_graph(arguments: Mapping[str, Any]) -> dict[str, Any]:
    atlas = Path(_string(arguments, "atlas"))
    manifest = atlas if atlas.name == "atlas-manifest.json" else atlas / "atlas-manifest.json"
    validate_evidence_atlas(manifest, Path(_string(arguments, "bundle")))
    return load_evidence_atlas(manifest.parent)["graph"]


def _perspective(
    graph: Mapping[str, Any],
    perspective_id: str,
) -> dict[str, Any]:
    for perspective in graph.get("perspectives", []):
        if isinstance(perspective, dict) and perspective.get("id") == perspective_id:
            return perspective
    raise ValueError(f"unknown Perspective: {perspective_id}")


def _require_new_output(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"output already exists: {path}")


def _strict_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda item: (_raise_nonfinite(item)),
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _raise_nonfinite(value: str) -> Any:
    raise ValueError(f"non-finite JSON number: {value}")


def _rpc_result(identifier: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": identifier, "result": result}


def _rpc_error(
    identifier: Any,
    code: int,
    message: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "error": {"code": code, "message": message},
    }
