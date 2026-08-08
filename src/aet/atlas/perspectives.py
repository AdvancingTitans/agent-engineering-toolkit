"""Deterministic, bounded projections over the canonical Evidence Graph."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import PERSPECTIVES, PERSPECTIVE_SCHEMA, derived_id


_MANIFEST_REF = {
    "collection": "manifest.json",
    "record_id": "manifest",
    "field": "investigation",
}

_SPECS: dict[str, dict[str, Any]] = {
    "claim-chain": {
        "title": "Claim Chain",
        "question": "这个结论由哪些证据支持、反驳或限制？",
        "description": "从 Claim 追踪 Verified Evidence、Proof、反证、限制、Freshness 与 UNKNOWN。",
        "diagram_type": "flowchart",
        "direction": "LR",
        "node_types": {
            "intent", "claim", "verified_evidence", "proof", "command",
            "observation", "conflict", "freshness_result", "unknown",
            "limitation", "recommendation",
        },
        "edge_types": {
            "ANSWERS", "SUPPORTED_BY", "PARTIALLY_SUPPORTED_BY",
            "CONTRADICTED_BY", "OBSERVED_IN", "VALIDATES", "PRODUCED_BY",
            "EXECUTED_BY", "LIMITED_BY", "INVALIDATED_BY", "FRESH_FOR",
            "STALE_FOR", "LEAVES_UNKNOWN", "RECOMMENDS", "DERIVED_FROM",
        },
        "root_types": ("claim",),
        "required": (("claim",),),
        "missing": "Bundle 中没有可投影的 Claim。",
    },
    "investigation-flow": {
        "title": "Investigation Flow",
        "question": "AET 怎样从任务意图走到当前判断？",
        "description": "展示 Intent、Ledger Tool Call、Observation、Candidate、Evidence 与 Claim 的调查顺序。",
        "diagram_type": "flowchart",
        "direction": "LR",
        "node_types": {
            "intent", "run", "tool_call", "tool_result", "observation",
            "evidence_candidate", "verified_evidence", "claim", "conflict",
            "unknown", "limitation", "recommendation", "budget",
        },
        "edge_types": {
            "ANSWERS", "PRECEDES", "CALLED", "RETURNED", "PRODUCED_BY",
            "DERIVED_FROM", "SUPPORTED_BY", "PARTIALLY_SUPPORTED_BY",
            "CONTRADICTED_BY", "LIMITED_BY", "LEAVES_UNKNOWN",
            "RECOMMENDS", "CONSTRAINED_BY",
        },
        "root_types": ("run", "intent"),
        "required": (("run",),),
        "missing": "Bundle 中没有标准化调查 Run。",
    },
    "change-scope": {
        "title": "Change Scope",
        "question": "哪些声明范围、路径与授权边界和任务相关？",
        "description": "仅展示声明 Scope 与 path binding；没有显式 Change Group 时不得推断真实修改范围。",
        "diagram_type": "flowchart",
        "direction": "TD",
        "node_types": {
            "intent", "run", "file", "symbol", "change_group", "authorization",
            "constraint", "verified_evidence", "proof", "claim", "unknown",
            "limitation", "recommendation", "policy_rule",
        },
        "edge_types": {
            "ANSWERS", "APPLIES_TO", "CHANGED", "GROUPED_IN",
            "AUTHORIZED_BY", "CONSTRAINED_BY", "VALIDATES", "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY", "LIMITED_BY", "LEAVES_UNKNOWN",
            "RECOMMENDS",
        },
        "root_types": ("change_group", "run", "intent"),
        "required": (("file",), ("change_group",)),
        "missing": (
            "Bundle v1 只有声明 Scope/path binding，没有显式 Change Group；"
            "该视角不能证明真实 diff。"
        ),
    },
    "verification-coverage": {
        "title": "Verification Coverage",
        "question": "验证证明了什么，又明确没有证明什么？",
        "description": "连接 Claim、Proof、Command、相关路径、Freshness、限制与 does_not_prove。",
        "diagram_type": "flowchart",
        "direction": "LR",
        "node_types": {
            "claim", "verified_evidence", "proof", "command", "file",
            "observation", "freshness_result", "limitation", "unknown",
            "recommendation", "source", "artifact",
        },
        "edge_types": {
            "SUPPORTED_BY", "PARTIALLY_SUPPORTED_BY", "CONTRADICTED_BY",
            "VALIDATES", "PRODUCED_BY", "EXECUTED_BY", "APPLIES_TO",
            "DERIVED_FROM", "FRESH_FOR", "STALE_FOR", "INVALIDATED_BY",
            "LIMITED_BY", "LEAVES_UNKNOWN", "RECOMMENDS", "OBSERVED_IN",
        },
        "root_types": ("proof", "claim"),
        "required": (("proof", "verified_evidence"),),
        "missing": "Bundle 中没有 Proof 或 Verified Evidence，验证覆盖保持 UNKNOWN。",
    },
    "evidence-data-flow": {
        "title": "Evidence Data Flow",
        "question": "证据如何从运行记录流向观察、候选、验证和结论？",
        "description": "实例化 Evidence 生命周期；缺失阶段保持 UNKNOWN，不补造记录。",
        "diagram_type": "flowchart",
        "direction": "LR",
        "node_types": {
            "intent", "run", "source", "tool_call", "tool_result",
            "observation", "evidence_candidate", "verified_evidence", "claim",
            "conflict", "artifact", "unknown", "limitation",
        },
        "edge_types": {
            "ANSWERS", "PRECEDES", "RETURNED", "PRODUCED_BY",
            "DERIVED_FROM", "OBSERVED_IN", "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY", "CONTRADICTED_BY", "LIMITED_BY",
            "LEAVES_UNKNOWN",
        },
        "root_types": ("run", "intent"),
        "required": (("run",), ("observation", "verified_evidence")),
        "missing": "Bundle 没有足够记录来实例化 Evidence 生命周期。",
    },
    "integrations": {
        "title": "Integration and Sources",
        "question": "调查依赖哪些工具、来源、Artifact 与权限边界？",
        "description": "展示本地来源与工具边界；source_type 不会被升级为 Agent 身份。",
        "diagram_type": "sequenceDiagram",
        "direction": "LR",
        "node_types": {
            "run", "agent", "tool_call", "tool_result", "source", "artifact",
            "command", "proof", "authorization", "constraint", "policy_rule",
            "budget", "unknown",
        },
        "edge_types": {
            "CALLED", "RETURNED", "PRODUCED_BY", "DERIVED_FROM",
            "EXECUTED_BY", "AUTHORIZED_BY", "CONSTRAINED_BY",
            "APPLIES_TO", "PRECEDES", "LEAVES_UNKNOWN",
        },
        "root_types": ("run", "source", "tool_call"),
        "required": (("source", "tool_call"),),
        "missing": "Bundle 中没有可识别的 Source 或 Tool Call。",
    },
    "conflicts": {
        "title": "Conflict and Unknown",
        "question": "哪些证据冲突，哪些问题仍未解决？",
        "description": "优先展示 Conflict、UNKNOWN、反证、限制与下一步行动。",
        "diagram_type": "stateDiagram",
        "direction": "TD",
        "node_types": {
            "claim", "verified_evidence", "conflict", "unknown",
            "freshness_result", "limitation", "recommendation", "run",
        },
        "edge_types": {
            "CONTRADICTED_BY", "LEAVES_UNKNOWN", "INVALIDATED_BY",
            "STALE_FOR", "LIMITED_BY", "RECOMMENDS", "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY",
        },
        "root_types": ("conflict", "unknown", "run"),
        "required": (),
        "missing": "",
    },
    "freshness": {
        "title": "Freshness",
        "question": "证据何时仍适用，何时以及为何失效？",
        "description": "展示 Evidence、Proof、绑定路径、Freshness Result 与重跑建议。",
        "diagram_type": "timeline",
        "direction": "LR",
        "node_types": {
            "verified_evidence", "proof", "freshness_result", "file",
            "claim", "unknown", "recommendation", "limitation",
        },
        "edge_types": {
            "FRESH_FOR", "STALE_FOR", "INVALIDATED_BY", "APPLIES_TO",
            "SUPPORTED_BY", "PARTIALLY_SUPPORTED_BY", "VALIDATES",
            "LEAVES_UNKNOWN", "RECOMMENDS", "LIMITED_BY",
        },
        "root_types": ("freshness_result", "verified_evidence"),
        "required": (("freshness_result",),),
        "missing": "Bundle 中没有 Evidence Freshness Result。",
    },
    "improvement-chain": {
        "title": "Improvement Chain",
        "question": "Finding 如何约束 Candidate，并由 Verification 与 Outcome 闭环？",
        "description": (
            "展示有来源依据的 Finding、Constraint、Candidate、Verification 与 Outcome；"
            "Bundle 未携带独立 Improvement 记录时保持 UNKNOWN。"
        ),
        "diagram_type": "flowchart",
        "direction": "LR",
        "node_types": {
            "finding", "constraint", "recommendation", "proof", "claim",
            "verified_evidence", "unknown", "limitation", "conflict",
        },
        "edge_types": {
            "CONSTRAINED_BY", "RECOMMENDS", "VALIDATES", "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY", "DERIVED_FROM", "LEAVES_UNKNOWN",
            "LIMITED_BY", "INVALIDATED_BY",
        },
        "root_types": ("finding", "claim"),
        "required": (
            ("finding",),
            ("constraint",),
            ("recommendation",),
            ("proof",),
        ),
        "missing": (
            "Bundle 中缺少独立 Improvement Finding、Constraint、Candidate、"
            "Verification 或 Outcome 记录；不得从建议推断已验证改进。"
        ),
    },
    "regression-lineage": {
        "title": "Regression Lineage",
        "question": "已验证改进如何绑定到后续 Regression Fixture 与 CI 检查？",
        "description": (
            "追踪 Proof、Freshness、Finding 与回归建议；"
            "缺少 Improvement Outcome 或 Regression Fixture 时保持 UNKNOWN。"
        ),
        "diagram_type": "flowchart",
        "direction": "LR",
        "node_types": {
            "finding", "proof", "freshness_result", "verified_evidence",
            "claim", "recommendation", "artifact", "unknown", "limitation",
            "conflict",
        },
        "edge_types": {
            "FRESH_FOR", "STALE_FOR", "INVALIDATED_BY", "VALIDATES",
            "SUPPORTED_BY", "PARTIALLY_SUPPORTED_BY", "DERIVED_FROM",
            "RECOMMENDS", "LIMITED_BY", "LEAVES_UNKNOWN",
            "CONTRADICTED_BY", "PRODUCED_BY",
        },
        "root_types": ("proof", "verified_evidence"),
        "required": (
            ("proof", "verified_evidence"),
            ("freshness_result",),
            ("finding",),
        ),
        "missing": (
            "Bundle 中缺少可绑定的 Improvement Outcome、Regression Fixture "
            "或 Finding；不得推断回归已沉淀。"
        ),
    },
    "behavioural-risk": {
        "title": "Behavioural Risk Diagnosis",
        "question": "哪些证据绑定的行为风险条件、路径与 PROPOSED 干预和当前任务相关？",
        "description": (
            "只投影显式提供且能够解析回 Bundle 记录的 Risk Diagnosis；"
            "不生成整体分数、不推断内部动机、不执行干预。"
        ),
        "diagram_type": "flowchart",
        "direction": "LR",
        "node_types": {
            "finding", "recommendation", "verified_evidence", "observation",
            "claim", "unknown", "limitation", "conflict",
        },
        "edge_types": {
            "DERIVED_FROM", "SUPPORTED_BY", "PARTIALLY_SUPPORTED_BY",
            "CONTRADICTED_BY", "LIMITED_BY", "LEAVES_UNKNOWN", "RECOMMENDS",
        },
        "root_types": ("finding",),
        "required": (("finding",),),
        "required_tag": "behavioural-risk",
        "missing": (
            "没有提供可解析回 Bundle 记录的 Behavioural Risk Diagnosis；"
            "不得从普通 Finding 推断行为风险。"
        ),
    },
}


def apply_perspectives(graph: dict[str, Any]) -> dict[str, Any]:
    """Attach all fixed perspectives and update their dependency index."""
    nodes = _nodes_by_id(graph)
    perspectives: list[dict[str, Any]] = []
    for perspective_id in PERSPECTIVES:
        spec = _SPECS[perspective_id]
        required_tag = spec.get("required_tag")
        eligible_nodes = [
            node
            for node in nodes.values()
            if required_tag is None or required_tag in node.get("tags", [])
        ]
        missing = _missing_requirements(eligible_nodes, spec["required"])
        unknowns = [spec["missing"]] if missing and spec["missing"] else []
        if unknowns:
            unknown_id = _ensure_unknown_node(graph, nodes, perspective_id, unknowns[0])
        else:
            unknown_id = None

        selected_node_ids = {
            node_id
            for node_id, node in nodes.items()
            if node.get("type") in spec["node_types"]
            and (required_tag is None or required_tag in node.get("tags", []))
        }
        if unknown_id is not None:
            selected_node_ids.add(unknown_id)
        selected_edges = [
            edge
            for edge in graph.get("edges", [])
            if edge.get("type") in spec["edge_types"]
            and edge.get("from") in selected_node_ids
            and edge.get("to") in selected_node_ids
        ]
        selected_node_ids = _retain_connected_nodes(
            selected_node_ids,
            selected_edges,
            nodes,
            set(spec["root_types"]),
            unknown_id,
        )
        selected_edges = [
            edge
            for edge in selected_edges
            if edge["from"] in selected_node_ids and edge["to"] in selected_node_ids
        ]
        roots = _roots(
            selected_node_ids,
            nodes,
            spec["root_types"],
            unknown_id,
        )
        perspective = {
            "schema_version": PERSPECTIVE_SCHEMA,
            "id": perspective_id,
            "title": spec["title"],
            "question": spec["question"],
            "description": spec["description"],
            "coverage_status": "UNKNOWN" if unknowns else "PASS",
            "diagram_type": spec["diagram_type"],
            "direction": spec["direction"],
            "root_node_ids": roots,
            "node_ids": sorted(selected_node_ids),
            "edge_ids": sorted(edge["id"] for edge in selected_edges),
            "node_count": len(selected_node_ids),
            "edge_count": len(selected_edges),
            "unknowns": unknowns,
            "constraints": _perspective_constraints(perspective_id),
            "concerns": _perspective_concerns(perspective_id),
            "actions": (
                ["补充结构化 Bundle 数据后重建该视角。"] if unknowns else []
            ),
            "provenance": {
                "bundle_id": graph.get("bundle_id"),
                "generated_from": graph.get("generated_from"),
                "mode": "deterministic",
            },
        }
        perspectives.append(perspective)

    graph["perspectives"] = perspectives
    dependency_index = graph.setdefault("dependency_index", {})
    node_to_perspectives: dict[str, list[str]] = {}
    for perspective in perspectives:
        for node_id in perspective["node_ids"]:
            node_to_perspectives.setdefault(node_id, []).append(perspective["id"])
    dependency_index["node_to_perspectives"] = {
        node_id: sorted(values)
        for node_id, values in sorted(node_to_perspectives.items())
    }
    _update_record_perspectives(graph, nodes)
    return graph


def build_perspectives(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Compatibility helper returning the attached perspective records."""
    return apply_perspectives(graph)["perspectives"]


def _nodes_by_id(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        node["id"]: node
        for node in graph.get("nodes", [])
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }


def _missing_requirements(
    nodes: Any, requirements: tuple[tuple[str, ...], ...]
) -> bool:
    present = {node.get("type") for node in nodes}
    return any(not present.intersection(alternatives) for alternatives in requirements)


def _ensure_unknown_node(
    graph: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    perspective_id: str,
    reason: str,
) -> str:
    node_id = derived_id("unknown", "perspective", perspective_id)
    if node_id not in nodes:
        node = {
            "id": node_id,
            "type": "unknown",
            "source_refs": [dict(_MANIFEST_REF)],
            "title": f"UNKNOWN: {perspective_id}",
            "summary": reason,
            "status": "unknown",
            "authority": "deterministic_projection",
            "freshness": "not_applicable",
            "importance": "high",
            "complexity": {
                "score": 2,
                "classification": "leaf",
                "reasons": ["missing structured source data"],
            },
            "tags": ["perspective", perspective_id, "unknown"],
            "attributes": {"perspective_id": perspective_id},
        }
        graph.setdefault("nodes", []).append(node)
        graph["nodes"].sort(key=lambda item: item["id"])
        nodes[node_id] = node
        dependency = graph.setdefault("dependency_index", {})
        dependency.setdefault("record_to_nodes", {}).setdefault(
            "manifest", []
        ).append(node_id)
        dependency["record_to_nodes"]["manifest"] = sorted(
            set(dependency["record_to_nodes"]["manifest"])
        )
    return node_id


def _retain_connected_nodes(
    node_ids: set[str],
    edges: list[dict[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
    root_types: set[str],
    unknown_id: str | None,
) -> set[str]:
    connected = {
        identifier
        for edge in edges
        for identifier in (edge["from"], edge["to"])
    }
    connected.update(
        node_id
        for node_id in node_ids
        if nodes[node_id].get("type") in root_types
    )
    if unknown_id is not None:
        connected.add(unknown_id)
    return connected


def _roots(
    node_ids: set[str],
    nodes: Mapping[str, Mapping[str, Any]],
    root_types: tuple[str, ...],
    unknown_id: str | None,
) -> list[str]:
    roots: list[str] = []
    for node_type in root_types:
        roots.extend(
            sorted(
                node_id
                for node_id in node_ids
                if nodes[node_id].get("type") == node_type
            )
        )
        if roots:
            break
    if unknown_id is not None and unknown_id not in roots:
        roots.append(unknown_id)
    if not roots and node_ids:
        roots.append(sorted(node_ids)[0])
    return roots


def _perspective_constraints(perspective_id: str) -> list[str]:
    common = ["只使用 Canonical Evidence Graph 中有来源依据的节点和边。"]
    if perspective_id == "change-scope":
        common.append("声明 Scope/path binding 不等于真实 Git diff 或 Change Group。")
    if perspective_id == "verification-coverage":
        common.append("Proof 只覆盖记录的命令与路径；必须保留 does_not_prove。")
    if perspective_id == "integrations":
        common.append("Source provenance 不会被解释为 Agent 身份。")
    if perspective_id == "improvement-chain":
        common.append("Candidate 仍是 PROPOSED；只有有效 Proof 才能形成 Verified Outcome。")
    if perspective_id == "regression-lineage":
        common.append("Regression Fixture 必须绑定已验证 Outcome，不能由建议自动生成事实。")
    if perspective_id == "behavioural-risk":
        common.append("只投影能解析回 Bundle 记录的 Diagnosis；干预始终是 PROPOSED。")
    return common


def _perspective_concerns(perspective_id: str) -> list[str]:
    if perspective_id == "investigation-flow":
        return ["Evidence Candidate 可能只有 Ledger reference，没有完整候选记录。"]
    if perspective_id == "freshness":
        return ["Bundle v1 记录当前 Freshness 快照，不保证包含完整历史事件序列。"]
    if perspective_id in {"improvement-chain", "regression-lineage"}:
        return ["Portable Evidence Bundle v1 尚无独立 Improvement 记录集合。"]
    if perspective_id == "behavioural-risk":
        return ["Behavioural Risk Diagnosis 是 Bundle 的只读 sibling projection，不改变 Bundle 事实。"]
    return []


def _update_record_perspectives(
    graph: dict[str, Any], nodes: Mapping[str, Mapping[str, Any]]
) -> None:
    dependency = graph.setdefault("dependency_index", {})
    node_to_perspectives = dependency.get("node_to_perspectives", {})
    record_to_perspectives: dict[str, set[str]] = {}
    for node_id, perspective_ids in node_to_perspectives.items():
        node = nodes.get(node_id)
        if not node:
            continue
        for ref in node.get("source_refs", []):
            key = _dependency_key(ref)
            record_to_perspectives.setdefault(key, set()).update(perspective_ids)
    dependency["record_to_perspectives"] = {
        key: sorted(values)
        for key, values in sorted(record_to_perspectives.items())
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


__all__ = ["apply_perspectives", "build_perspectives"]
