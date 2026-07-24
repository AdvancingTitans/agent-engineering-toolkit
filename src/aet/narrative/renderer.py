"""Progressive-disclosure narratives that preserve machine states and refs."""

from __future__ import annotations

import json
from typing import Any


def render_quick_result(data: dict[str, Any], language: str) -> str:
    kind = data.get("report_kind")
    if language == "zh-CN":
        if kind == "quick_check_preflight":
            bounded = data.get("bounded_result", {})
            return (
                "【AET Quick 检查】\n\n"
                f"确定性事实：共发现 {bounded.get('eligible_findings', 0)} 项，"
                f"本次展示 {bounded.get('reported_findings', 0)} 项。\n\n"
                "下一步：宿主 LLM 可在预算内调查项目语义和反方解释；"
                "不得改写现有 PASS、FAIL、UNKNOWN 或 NOT_APPLICABLE。\n"
            )
        if kind == "quick_scope_preflight":
            return (
                "【AET Quick 范围调查】\n\n"
                f"初步状态：{data.get('disposition')}\n\n"
                "注意：路径超出声明范围只会触发必要性调查，不能单独证明修改越界。\n"
            )
        if kind == "quick_proof":
            return (
                "【AET Quick 验证记录】\n\n"
                f"结果：{data.get('authoritative_status')}\n"
                f"退出码：{data.get('command', {}).get('exit_code')}\n\n"
                "覆盖范围：仅覆盖记录的命令和声明路径，不代表完整测试套件通过。\n"
            )
        if kind == "quick_fresh":
            return (
                "【AET Quick 证据有效性】\n\n"
                f"结论：{data.get('freshness_state')}\n"
                f"原因：{'；'.join(data.get('reasons', []))}\n"
            )
    if kind == "quick_check_preflight":
        bounded = data.get("bounded_result", {})
        return (
            "# AET Quick Check\n\n"
            f"Deterministic findings: {bounded.get('eligible_findings', 0)}; "
            f"reported: {bounded.get('reported_findings', 0)}.\n\n"
            "The host LLM may investigate project semantics and counter-explanations "
            "within budget, but it cannot rewrite PASS, FAIL, UNKNOWN, or NOT_APPLICABLE.\n"
        )
    if kind == "quick_scope_preflight":
        return (
            "# AET Quick Scope\n\n"
            f"Preflight disposition: {data.get('disposition')}\n\n"
            "A path outside the declared surface triggers a necessity investigation; "
            "it does not establish an out-of-scope conclusion by itself.\n"
        )
    if kind == "quick_proof":
        return (
            "# AET Quick Proof\n\n"
            f"Result: {data.get('authoritative_status')}\n"
            f"Exit code: {data.get('command', {}).get('exit_code')}\n\n"
            "Coverage: only the recorded command and declared paths; this is not a "
            "claim that the full test suite passed.\n"
        )
    if kind == "quick_fresh":
        return (
            "# AET Quick Fresh\n\n"
            f"State: {data.get('freshness_state')}\n"
            f"Reason: {'; '.join(data.get('reasons', []))}\n"
        )
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render_investigated_finding(finding: dict[str, Any], language: str) -> str:
    """Render required sections without creating or upgrading a finding."""
    fields = (
        "conclusion",
        "confirmed_facts",
        "engineering_judgment",
        "counter_explanation",
        "remaining_uncertainty",
        "locations",
        "recommended_action",
        "evidence_refs",
    )
    missing = [field for field in fields if field not in finding]
    if missing:
        raise ValueError(f"investigated finding is missing narrative fields: {', '.join(missing)}")
    if language == "zh-CN":
        labels = (
            ("一句话结论", "conclusion"),
            ("已确认事实", "confirmed_facts"),
            ("工程判断", "engineering_judgment"),
            ("反方解释", "counter_explanation"),
            ("仍不确定", "remaining_uncertainty"),
            ("问题指向", "locations"),
            ("建议动作", "recommended_action"),
            ("原始证据", "evidence_refs"),
        )
    else:
        labels = (
            ("Conclusion", "conclusion"),
            ("Confirmed facts", "confirmed_facts"),
            ("Engineering judgment", "engineering_judgment"),
            ("Counter-explanation", "counter_explanation"),
            ("Remaining uncertainty", "remaining_uncertainty"),
            ("Location", "locations"),
            ("Next action", "recommended_action"),
            ("Evidence references", "evidence_refs"),
        )
    lines = []
    for label, key in labels:
        value = finding[key]
        if isinstance(value, list):
            rendered = "\n".join(f"- {_render_value(item)}" for item in value)
        else:
            rendered = _render_value(value)
        lines.extend((f"## {label}", "", rendered, ""))
    return "\n".join(lines).rstrip() + "\n"


def _render_value(value: Any) -> str:
    if isinstance(value, dict):
        if "statement" in value:
            details = [
                value.get("statement"),
                value.get("investigation_result"),
                ", ".join(value.get("evidence_refs", [])),
            ]
            return " — ".join(str(item) for item in details if item)
        if "path" in value:
            line = value.get("line")
            return f"{value['path']}:{line}" if line else str(value["path"])
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
