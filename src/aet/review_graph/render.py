"""Human and compatibility projections derived from Review Graph records."""

from __future__ import annotations

import hashlib
from typing import Any


def render_mermaid(review_slice: dict[str, Any], *, title: str) -> str:
    """Render a small strict Mermaid projection; it creates no authority."""
    lines = ["flowchart LR", f"    %% {title}"]
    aliases = {node["id"]: _alias(node["id"]) for node in review_slice["nodes"]}
    for node in review_slice["nodes"]:
        label = _label(f"[{node['state']}] {node['text']}")
        lines.append(f'    {aliases[node["id"]]}["{label}"]')
    for source, relation, target in review_slice["edges"]:
        if source in aliases and target in aliases:
            lines.append(
                f'    {aliases[source]} -->|"{_label(relation.lower().replace("_", " "))}"| {aliases[target]}'
            )
    return "\n".join(lines) + "\n"


def render_human_improvements(review_slice: dict[str, Any]) -> str:
    """Render Chinese action cards while keeping IDs and unknowns explicit."""
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for node in review_slice["nodes"]:
        by_kind.setdefault(node["kind"], []).append(node)
    issue = next(iter(by_kind.get("review_issue", [])), None)
    lines = ["# Human Improvement Report", ""]
    if issue is None:
        return "# Human Improvement Report\n\n当前切片没有可执行的 Improvement Issue。\n"
    lines.extend(
        [
            f"## {issue['id']} — {issue['text']}",
            "",
            "### 可直接交给 Coding Agent 的改进提示词",
            _agent_prompt(by_kind, issue),
            "",
            "### 目标",
            _texts(by_kind.get("intent", [])),
            "",
            "### 允许修改",
            _texts(by_kind.get("allowed_scope", [])),
            "",
            "### 禁止修改与禁止行为",
            _texts(by_kind.get("protected_scope", [])),
            "",
            "### 证据与限制",
        ]
    )
    evidence = [
        node
        for node in review_slice["nodes"]
        if node["kind"]
        in {
            "claim",
            "verified_evidence",
            "observation",
            "proof",
            "conflict",
            "unknown",
            "limitation",
        }
    ]
    lines.extend(
        f"- `{node['id']}` · `{node['state']}` · {node['text']}"
        for node in evidence
    )
    lines.extend(
        [
            "",
            "### 验证方式",
            _texts(by_kind.get("verification_requirement", [])),
            "",
            "### 停止条件",
            _texts(by_kind.get("stop_condition", [])),
            "",
            "### 上下文边界",
            (
                f"本报告来自受限图切片；省略节点 {review_slice['cut']['omitted_nodes']} 个，"
                f"省略关系 {review_slice['cut']['omitted_edges']} 条。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _agent_prompt(
    by_kind: dict[str, list[dict[str, Any]]],
    issue: dict[str, Any],
) -> str:
    intent = _inline_texts(by_kind.get("intent", []))
    allowed = _inline_texts(by_kind.get("allowed_scope", []))
    protected = _inline_texts(by_kind.get("protected_scope", []))
    verification = _inline_texts(by_kind.get("verification_requirement", []))
    stop = _inline_texts(by_kind.get("stop_condition", []))
    return (
        f"{intent} 请处理以下问题：{issue['text']}。{allowed}。{protected}。"
        f"完成后执行：{verification}。{stop}"
    )


def render_compat_agent_task(review_slice: dict[str, Any]) -> str:
    """Explicit legacy export; Review Graph remains the default Agent input."""
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for node in review_slice["nodes"]:
        by_kind.setdefault(node["kind"], []).append(node)
    issue = next(iter(by_kind.get("review_issue", [])), None)
    evidence = [
        node
        for node in review_slice["nodes"]
        if node["kind"] in {"claim", "verified_evidence", "proof", "observation", "unknown", "limitation"}
    ]
    return "\n".join(
        [
            "# Agent Task (Compatibility Export)",
            "",
            "The canonical input is `review/root.slice.json`; this Markdown is non-authoritative.",
            "",
            "## Problem",
            issue["text"] if issue else "INVESTIGATION_REQUIRED: no review issue in the slice.",
            "",
            "## Evidence",
            *[f"- `{node['id']}` · `{node['state']}` · {node['text']}" for node in evidence],
            "",
            "## Allowed Scope",
            _texts(by_kind.get("allowed_scope", [])),
            "",
            "## Forbidden Scope",
            _texts(by_kind.get("protected_scope", [])),
            "",
            "## Verification",
            _texts(by_kind.get("verification_requirement", [])),
            "",
            "## Stop Conditions",
            _texts(by_kind.get("stop_condition", [])),
            "",
        ]
    )


def _texts(nodes: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {node['text']}" for node in nodes) or "- UNKNOWN: no record supplied."


def _inline_texts(nodes: list[dict[str, Any]]) -> str:
    return " ".join(node["text"] for node in nodes) or "UNKNOWN: no record supplied"


def _alias(identifier: str) -> str:
    return "N_" + hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:16]


def _label(value: str) -> str:
    return (
        value.replace("\\", "/")
        .replace('"', "'")
        .replace("\n", " ")
        .replace("<", "‹")
        .replace(">", "›")[:180]
    )
