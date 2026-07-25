"""Deterministic Markdown projection for Portable Evidence Bundle v1."""

from __future__ import annotations

from typing import Any


def render_bundle_markdown(bundle: dict[str, Any]) -> str:
    """Render only portable Claim data and immutable references."""
    question = bundle["manifest"]["investigation"]["question"]
    lines = [
        "# Portable Evidence Bundle",
        "",
        "## 调查问题",
        "",
        question,
        "",
        "## 调查结论",
        "",
    ]
    for claim in bundle["claims"]:
        lines.append(f"- `{claim['id']}` [{claim['status']}]：{claim['statement']}")
        if claim["evidence_refs"]:
            lines.append("- 支持证据：" + "、".join(f"`{item}`" for item in claim["evidence_refs"]))
        if claim["counter_evidence_refs"]:
            lines.append("- 反证：" + "、".join(f"`{item}`" for item in claim["counter_evidence_refs"]))
        if claim["observation_refs"]:
            lines.append("- 观察：" + "、".join(f"`{item}`" for item in claim["observation_refs"]))
        for limitation in claim["limitations"]:
            lines.append(f"- 限制：{limitation}")
        if claim.get("smallest_next_action"):
            lines.append(f"- 最小下一步：{claim['smallest_next_action']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_consumer_guide() -> str:
    """Return the fixed v1 no-SDK consumption boundary."""
    return """# 消费说明

Portable Evidence Bundle 是结构化来源，不是最终审查权威。

审查结论应：

1. 引用有效的 Claim ID 和 Evidence ID。
2. 区分执行记录观察、交叉验证证据与当前工作区复现证据。
3. 使用历史证据前检查 Freshness。
4. 保留 `conflicted` 和 `unknown` 状态。
5. 同时披露相关反证。

不得把执行者自述升级为已复现事实，也不得把缺失证据解释为事情没有发生。
"""
