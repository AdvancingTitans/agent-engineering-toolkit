"""Compose code structure, evidence, and review-control records."""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from aet.atlas.builder import build_evidence_graph
from aet.bundle import validate_bundle
from aet.improvement.models.constraint import ImprovementConstraint
from aet.improvement.models.issue import ImprovementIssue

from .errors import ReviewGraphError
from .indexer import build_code_graph
from .model import REVIEW_GRAPH_SCHEMA, canonical_json_bytes, sha256_bytes, stable_id
from .validator import validate_review_graph


_STALE = {"stale", "relevant_files_changed", "workspace_changed", "environment_changed"}


def build_review_graph(
    workspace: Path,
    base_ref: str,
    bundle_path: Path,
    improvements_path: Path,
    *,
    issue_id: str | None = None,
    exclude_paths: tuple[str, ...] = (),
    max_files: int = 2_000,
    max_bytes: int = 8 * 1024 * 1024,
) -> dict[str, Any]:
    """Build one canonical Review Graph without executing project code."""
    bundle = validate_bundle(bundle_path)
    issue, constraint, improvements_sha = load_improvement_contract(improvements_path, issue_id)
    code_graph = build_code_graph(
        workspace,
        base_ref,
        exclude_paths=exclude_paths,
        max_files=max_files,
        max_bytes=max_bytes,
    )
    evidence_graph = build_evidence_graph(bundle)
    task = bundle["manifest"]["task"]
    task_id = str(task["task_id"])

    evidence_graph_nodes = {item["id"]: item for item in evidence_graph["nodes"]}
    limitations_by_source: dict[str, list[dict[str, Any]]] = {}
    for raw_edge in evidence_graph["edges"]:
        if raw_edge["type"] != "LIMITED_BY":
            continue
        limitation = evidence_graph_nodes.get(raw_edge["to"])
        if limitation is not None and limitation["type"] == "limitation":
            limitations_by_source.setdefault(raw_edge["from"], []).append(limitation)

    nodes = [dict(item) for item in code_graph["nodes"]]
    edges = [dict(item) for item in code_graph["edges"]]
    diagnostics = [dict(item) for item in code_graph["diagnostics"]]

    evidence_ids_by_record_kind: dict[tuple[str, str], set[str]] = {}
    evidence_nodes: dict[str, dict[str, Any]] = {}
    relevant_records = set(issue.evidence_refs) | set(issue.finding_refs)
    for raw in evidence_graph["nodes"]:
        node = _evidence_node(raw, relevant_records)
        related_limitations = sorted(
            limitations_by_source.get(raw["id"], []),
            key=lambda item: item["id"],
        )
        if related_limitations:
            node["attributes"]["root_limitations"] = [
                str(item["summary"]) for item in related_limitations
            ]
            for limitation in related_limitations:
                node["source_refs"].extend(_bundle_refs(limitation["source_refs"]))
        nodes.append(node)
        evidence_nodes[node["id"]] = node
        for ref in raw["source_refs"]:
            record_id = ref.get("record_id")
            if isinstance(record_id, str):
                evidence_ids_by_record_kind.setdefault((record_id, node["kind"]), set()).add(
                    node["id"]
                )
    for raw in evidence_graph["edges"]:
        edges.append(_evidence_edge(raw))

    task_node = _control_node(
        stable_id("review:intent", task_id),
        "intent",
        str(task["request"]),
        "human_intent",
        f"manifest.json#task.{task_id}",
        state="PASS",
        mandatory=True,
        priority=100,
        attributes={"task_id": task_id},
    )
    issue_node = _control_node(
        stable_id("review:issue", issue.id),
        "review_issue",
        _review_issue_text(issue, constraint),
        "deterministic_improvement_record",
        f"issues.json#{issue.id}",
        state="PASS",
        mandatory=True,
        priority=100,
        attributes=asdict(issue),
    )
    issue_node["source_refs"].append(
        {"kind": "review_control", "ref": f"constraints.json#{constraint.id}.required_behavior"}
    )
    nodes.extend([task_node, issue_node])
    edges.append(_control_edge(task_node["id"], issue_node["id"], "TARGETS", f"issues.json#{issue.id}", priority=100))

    allowed = _scope_node(
        constraint.allowed_paths,
        "allowed_scope",
        constraint.id,
        "Allowed paths",
    )
    protected_values = [*constraint.protected_paths, *constraint.forbidden_behavior]
    protected = _scope_node(
        protected_values,
        "protected_scope",
        constraint.id,
        "Protected paths and forbidden behavior",
    )
    verification = _scope_node(
        constraint.verification_requirements,
        "verification_requirement",
        constraint.id,
        "Required verification",
    )
    nodes.extend([allowed, protected, verification])
    edges.extend(
        [
            _control_edge(issue_node["id"], allowed["id"], "AUTHORIZED_BY", f"constraints.json#{constraint.id}.allowed_paths", priority=100),
            _control_edge(issue_node["id"], protected["id"], "CONSTRAINED_BY", f"constraints.json#{constraint.id}.protected_paths", priority=100),
            _control_edge(issue_node["id"], verification["id"], "REQUIRES_VERIFICATION", f"constraints.json#{constraint.id}.verification_requirements", priority=100),
        ]
    )

    stop_texts = [
        "Stop if any referenced Evidence or Finding is missing.",
        "Stop before changing a protected path or performing forbidden behavior.",
        "Stop if verification cannot produce valid current Proof.",
    ]
    if constraint.action == "investigate":
        stop_texts.insert(0, "INVESTIGATION_REQUIRED: do not propose direct code modifications.")
    stop_node = _scope_node(stop_texts, "stop_condition", constraint.id, "Stop conditions")
    nodes.append(stop_node)
    edges.append(_control_edge(issue_node["id"], stop_node["id"], "STOP_IF", f"constraints.json#{constraint.id}", priority=100))

    missing_records: list[str] = []
    required_records = [
        *((record_id, "claim") for record_id in sorted(issue.finding_refs)),
        *((record_id, "verified_evidence") for record_id in sorted(issue.evidence_refs)),
    ]
    for record_id, canonical_kind in required_records:
        targets = sorted(evidence_ids_by_record_kind.get((record_id, canonical_kind), set()))
        if not targets:
            missing_records.append(record_id)
            continue
        for target in targets:
            evidence_nodes[target]["mandatory"] = True
            evidence_nodes[target]["priority"] = 100
            edges.append(
                _control_edge(issue_node["id"], target, "JUSTIFIED_BY", f"issues.json#{issue.id}.{record_id}", priority=100)
            )
    if missing_records:
        raise ReviewGraphError(
            "missing_evidence_reference",
            "improvement records reference absent Bundle records: " + ", ".join(missing_records),
        )

    file_nodes = {
        node["attributes"].get("path"): node
        for node in nodes
        if node["kind"] == "file"
        and node["id"].startswith("code:")
        and isinstance(node["attributes"].get("path"), str)
    }
    for node in list(evidence_nodes.values()):
        bindings = node["attributes"].get("bindings")
        paths = bindings.get("paths", []) if isinstance(bindings, dict) else []
        for path in paths if isinstance(paths, list) else []:
            if path in file_nodes:
                edges.append(
                    _control_edge(node["id"], file_nodes[path]["id"], "BINDS_TO_CODE", node["source_refs"][0]["ref"], priority=85)
                )

    target_files: set[str] = set()
    for path, file_node in file_nodes.items():
        if any(_matches(path, pattern) for pattern in constraint.allowed_paths):
            target_files.add(file_node["id"])
            if file_node["attributes"].get("changed"):
                file_node["mandatory"] = True
                file_node["priority"] = 100
                edges.append(
                    _control_edge(issue_node["id"], file_node["id"], "TARGETS", f"constraints.json#{constraint.id}.allowed_paths", priority=100)
                )

    changed_files = [
        node
        for node in nodes
        if node["kind"] == "file" and node["attributes"].get("changed") is True
    ]
    for file_node in changed_files:
        path = str(file_node["attributes"]["path"])
        if file_node["id"] not in target_files:
            diagnostics.append(
                _diagnostic(
                    "CHANGED_OUTSIDE_ALLOWED_SCOPE",
                    "FAIL",
                    f"Changed file is outside the Improvement allowed paths: {path}",
                    [path, f"constraints.json#{constraint.id}.allowed_paths"],
                )
            )
            file_node["mandatory"] = True
            file_node["priority"] = 100
        if any(_matches(path, pattern) for pattern in constraint.protected_paths):
            diagnostics.append(
                _diagnostic(
                    "PROTECTED_PATH_CHANGED",
                    "FAIL",
                    f"Protected path is changed: {path}",
                    [path, f"constraints.json#{constraint.id}.protected_paths"],
                )
            )

    for record, label in (
        (allowed, "allowed scope"),
        (protected, "protected scope"),
        (verification, "verification requirements"),
    ):
        if record["state"] == "UNKNOWN":
            diagnostics.append(
                _diagnostic(
                    "INCOMPLETE_REVIEW_CONTRACT",
                    "UNKNOWN",
                    f"The {label} is empty; implementation is not authorized.",
                    record["source_refs"],
                )
            )

    graph = {
        "schema_version": REVIEW_GRAPH_SCHEMA,
        "snapshot": dict(code_graph["snapshot"]),
        "task": {"id": task_id, "request": str(task["request"]), "authority": "human_intent"},
        "code_index": {
            "status": code_graph["index"]["coverage_status"],
            "sha256": sha256_bytes(canonical_json_bytes(code_graph)),
        },
        "evidence_binding": {
            "status": "PASS",
            "sha256": str(bundle["manifest"]["bundle"]["content_hash"]),
        },
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "edges": _deduplicate_edges(edges),
        "diagnostics": sorted(diagnostics, key=lambda item: (item["status"], item["code"], item["message"])),
    }
    graph["task"]["improvements_sha256"] = improvements_sha
    # The public schema keeps task compact. The hash remains attached to the
    # package manifest, not the canonical graph task object.
    graph["task"].pop("improvements_sha256")
    return validate_review_graph(graph)


def load_improvement_contract(
    path: Path,
    issue_id: str | None = None,
) -> tuple[ImprovementIssue, ImprovementConstraint, str]:
    root = path.resolve()
    if not root.is_dir() or root.is_symlink():
        raise ReviewGraphError("invalid_improvements", "improvements path must be a real directory")
    issues_path = root / "issues.json"
    constraints_path = root / "constraints.json"
    try:
        issues_raw = json.loads(issues_path.read_text(encoding="utf-8"))
        constraints_raw = json.loads(constraints_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReviewGraphError("invalid_improvements", f"cannot load Improvement records: {error}") from error
    if not isinstance(issues_raw, list) or not isinstance(constraints_raw, list):
        raise ReviewGraphError("invalid_improvements", "issues and constraints must be arrays")
    try:
        issues = [ImprovementIssue(**item) for item in issues_raw if isinstance(item, dict)]
        constraints = [ImprovementConstraint(**item) for item in constraints_raw if isinstance(item, dict)]
    except TypeError as error:
        raise ReviewGraphError("invalid_improvements", f"invalid Improvement record: {error}") from error
    if len(issues) != len(issues_raw) or len(constraints) != len(constraints_raw):
        raise ReviewGraphError("invalid_improvements", "every Improvement record must be an object")
    if issue_id is None:
        if len(issues) != 1:
            raise ReviewGraphError("ambiguous_issue", "--issue is required when improvements contain multiple issues")
        issue = issues[0]
    else:
        matches = [item for item in issues if item.id == issue_id]
        if len(matches) != 1:
            raise ReviewGraphError("unknown_issue", f"unknown Improvement Issue: {issue_id}")
        issue = matches[0]
    matches = [item for item in constraints if item.issue_id == issue.id]
    if len(matches) != 1:
        raise ReviewGraphError("invalid_improvements", f"issue {issue.id} must have exactly one constraint")
    if not issue.evidence_refs or not issue.finding_refs:
        raise ReviewGraphError("missing_evidence_reference", f"issue {issue.id} lacks Evidence or Finding references")
    digest = hashlib.sha256(issues_path.read_bytes() + b"\0" + constraints_path.read_bytes()).hexdigest()
    return issue, matches[0], digest


def _evidence_node(raw: dict[str, Any], relevant_records: set[str]) -> dict[str, Any]:
    refs = _bundle_refs(raw["source_refs"])
    records = {item["record_id"] for item in raw["source_refs"]}
    original = str(raw["status"])
    state = _evidence_state(original, str(raw.get("freshness", "unknown")))
    priority = 90 if state in {"FAIL", "UNKNOWN"} else 65
    if raw.get("importance") == "high":
        priority = max(priority, 85)
    return {
        "id": raw["id"],
        "kind": raw["type"],
        "state": state,
        "authority": str(raw["authority"]),
        "text": str(raw["summary"]),
        "source_refs": refs,
        "attributes": {
            **dict(raw.get("attributes", {})),
            "evidence_status": original,
            "freshness": raw.get("freshness"),
            "canonical_title": raw.get("title"),
        },
        # Only the canonical Claim/Evidence records named by an Improvement
        # become part of the mandatory safety kernel. Derived limitations,
        # freshness details, Sources, and recommendations remain available by
        # bounded expansion instead of bloating every Agent root slice.
        "mandatory": False,
        "priority": 90 if records.intersection(relevant_records) else priority,
    }


def _bundle_refs(raw_refs: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "kind": "bundle",
            "ref": f"{item['collection']}#{item['record_id']}.{item['field']}",
        }
        for item in raw_refs
    ]


def _evidence_edge(raw: dict[str, Any]) -> dict[str, Any]:
    refs = [
        {
            "kind": "bundle",
            "ref": f"{item['collection']}#{item['record_id']}.{item['field']}",
        }
        for item in raw["source_refs"]
    ]
    return {
        "id": "review:" + raw["id"],
        "from": raw["from"],
        "to": raw["to"],
        "relation": raw["type"],
        "state": "PASS",
        "authority": str(raw["authority"]),
        "source_refs": refs,
        "attributes": {"freshness_effect": raw.get("freshness_effect")},
        "priority": int(raw.get("render", {}).get("priority", 50)),
    }


def _evidence_state(status: str, freshness: str) -> str:
    if freshness in _STALE or status == "stale":
        return "UNKNOWN"
    if status in {"verified", "supported", "current", "resolved", "recorded"}:
        return "PASS"
    if status in {"unsupported", "conflicted"}:
        return "FAIL"
    if status == "not_applicable":
        return "NOT_APPLICABLE"
    return "UNKNOWN"


def _scope_node(values: list[str], kind: str, constraint_id: str, label: str) -> dict[str, Any]:
    cleaned = [str(item) for item in values if str(item)]
    state = "PASS" if cleaned else "UNKNOWN"
    text = f"{label}: " + ("; ".join(cleaned) if cleaned else "UNKNOWN: nothing recorded")
    return _control_node(
        stable_id(f"review:{kind}", constraint_id, *cleaned),
        kind,
        text,
        "improvement_constraint",
        f"constraints.json#{constraint_id}.{kind}",
        state=state,
        mandatory=True,
        priority=100,
        attributes={"values": cleaned, "constraint_id": constraint_id},
    )


def _review_issue_text(
    issue: ImprovementIssue,
    constraint: ImprovementConstraint,
) -> str:
    required = "; ".join(constraint.required_behavior) or "UNKNOWN: nothing recorded"
    finding_refs = ", ".join(issue.finding_refs) or "UNKNOWN"
    evidence_refs = ", ".join(issue.evidence_refs) or "UNKNOWN"
    return (
        f"{issue.title}. Objective: {constraint.objective.rstrip('.')}. "
        f"Required: {required}. Findings: {finding_refs}. Evidence: {evidence_refs}"
    )


def _control_node(
    identifier: str,
    kind: str,
    text: str,
    authority: str,
    ref: str,
    *,
    state: str,
    mandatory: bool,
    priority: int,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": kind,
        "state": state,
        "authority": authority,
        "text": text,
        "source_refs": [{"kind": "review_control", "ref": ref}],
        "attributes": attributes,
        "mandatory": mandatory,
        "priority": priority,
    }


def _control_edge(source: str, target: str, relation: str, ref: str, *, priority: int) -> dict[str, Any]:
    return {
        "id": stable_id("review:edge", source, target, relation, ref),
        "from": source,
        "to": target,
        "relation": relation,
        "state": "PASS",
        "authority": "deterministic_reference",
        "source_refs": [{"kind": "review_control", "ref": ref}],
        "attributes": {},
        "priority": priority,
    }


def _diagnostic(code: str, status: str, message: str, refs: list[Any]) -> dict[str, Any]:
    normalized = [
        item["ref"] if isinstance(item, dict) and isinstance(item.get("ref"), str) else str(item)
        for item in refs
    ]
    return {"code": code, "status": status, "message": message, "refs": normalized}


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)


def _deduplicate_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {edge["id"]: edge for edge in edges}
    return [by_id[identifier] for identifier in sorted(by_id)]
