"""Deterministic human projections for validated Evidence-Linked Plans."""

from __future__ import annotations

from typing import Any, Mapping


def render_plan_markdown(plan: Mapping[str, Any]) -> str:
    lines = [
        f"# {_text(plan.get('plan_id'))}",
        "",
        f"Status: `{_text(plan.get('status'))}`  ",
        "Authority: `PROPOSED`  ",
        f"Coverage: `{_text(plan.get('summary', {}).get('coverage_claim'))}`",
        "",
        "## Goal",
        "",
        _text(plan.get("request", {}).get("user_goal")),
        "",
        "## Constraints",
        "",
    ]
    request = plan.get("request", {})
    lines.extend(_list("Allowed paths", request.get("allowed_paths", [])))
    lines.extend(_list("Protected paths", request.get("protected_paths", [])))
    lines.extend(["", "## Required edits", ""])
    required = [
        item for item in plan.get("edit_items", []) if item.get("disposition") == "REQUIRED"
    ]
    lines.extend(_render_edits(required) or ["None."])
    lines.extend(["", "## Optional / investigate", ""])
    optional = [
        item
        for item in plan.get("edit_items", [])
        if item.get("disposition") in {"OPTIONAL", "INVESTIGATE", "DO_NOT_EDIT"}
    ]
    lines.extend(_render_edits(optional) or ["None."])
    lines.extend(["", "## Dependencies and change order", ""])
    dependencies = [
        f"- `{_text(item.get('edit_id'))}` depends on "
        + (
            ", ".join(f"`{_text(value)}`" for value in item.get("dependencies", []))
            or "no other edit item"
        )
        for item in plan.get("edit_items", [])
    ]
    lines.extend(dependencies or ["None."])
    lines.extend(["", "## Tests and verification", ""])
    for step in plan.get("verification_plan", {}).get("steps", []):
        command = step.get("command")
        rendered = " ".join(command) if isinstance(command, list) else "No command declared"
        lines.extend(
            [
                f"### `{_text(step.get('verification_id'))}`",
                "",
                _text(step.get("description")),
                "",
                f"- Status: `{_text(step.get('status'))}`",
                f"- Command candidate: `{_text(rendered)}`",
                f"- Expected: {_text(step.get('expected_result'))}",
                "",
            ]
        )
    if not plan.get("verification_plan", {}).get("steps"):
        lines.append("No verification step is established.")
    lines.extend(["", "## Evidence and source references", ""])
    for item in plan.get("edit_items", []):
        refs = [
            *item.get("evidence_refs", []),
            *item.get("atlas_refs", []),
            *item.get("source_refs", []),
        ]
        lines.append(
            f"- `{_text(item.get('edit_id'))}` · "
            + (", ".join(f"`{_text(ref)}`" for ref in refs) or "`UNKNOWN`")
        )
    lines.extend(["", "## Conflicts, unknowns and stop conditions", ""])
    unresolved = [
        *plan.get("conflicts", []),
        *plan.get("unknowns", []),
        *[
            item
            for item in plan.get("diagnostics", [])
            if item.get("severity") in {"ERROR", "BLOCKER"}
        ],
    ]
    lines.extend(
        [
            f"- `{_text(item.get('id') or item.get('code') or 'UNKNOWN')}`: "
            f"{_text(item.get('message') or item.get('statement') or item.get('proposition') or item.get('status'))}"
            for item in unresolved
        ]
        or ["None recorded."]
    )
    lines.extend(
        [
            "",
            "## What this plan does not prove",
            "",
            "- This `PROPOSED` plan does not prove that every edit site was found.",
            "- It does not prove that any code was changed or any command ran.",
            "- Verification remains `PENDING` until an explicit AET Proof and current Freshness check establish otherwise.",
            "",
        ]
    )
    return "\n".join(lines)


def render_consumer_guide(plan: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Evidence-Linked Plan consumer guide",
            "",
            "This directory is self-describing and can be consumed without AET.",
            "",
            "Authority order:",
            "",
            "1. `plan.json`",
            "2. `references.jsonl`",
            "3. `diagnostics.jsonl`",
            "4. `manifest.json`",
            "5. Markdown and Skill files are rebuildable projections.",
            "",
            f"Plan: `{_text(plan.get('plan_id'))}`",
            f"Status: `{_text(plan.get('status'))}`",
            "Authority: `PROPOSED`",
            "",
            "A `READY_FOR_HUMAN_REVIEW` status means the bounded structure and references passed deterministic validation. It does not mean the plan is implemented, complete, tested, or verified.",
            "",
            "Never execute a command merely because it appears in this package. An external implementation requires human authorization; verification requires the explicit AET Proof surface and a current Freshness check.",
            "",
        ]
    )


def _render_edits(items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in items:
        symbol = f" · `{_text(item.get('symbol'))}`" if item.get("symbol") else ""
        source_range = item.get("source_range")
        range_text = (
            f" · lines {source_range['start_line']}–{source_range['end_line']}"
            if isinstance(source_range, dict)
            else ""
        )
        lines.extend(
            [
                f"### `{_text(item.get('edit_id'))}` · `{_text(item.get('path'))}`{symbol}{range_text}",
                "",
                f"Disposition: `{_text(item.get('disposition'))}`  ",
                f"Reference strength: `{_text(item.get('reference_strength'))}`",
                "",
                "**Modification intent**",
                "",
                _text(item.get("intent")),
                "",
                "**Expected change**",
                "",
                _text(item.get("expected_change")),
                "",
                "**Rationale**",
                "",
                _text(item.get("rationale")),
                "",
            ]
        )
        lines.extend(_list("Tests", item.get("tests", [])))
        lines.extend(_list("Risks", item.get("risks", [])))
        lines.extend(_list("Limitations", item.get("limitations", [])))
        lines.append("")
    return lines


def _list(label: str, values: Any) -> list[str]:
    items = values if isinstance(values, list) else []
    return [f"- {label}: " + (", ".join(f"`{_text(item)}`" for item in items) or "`UNKNOWN`")]


def _text(value: Any) -> str:
    return str(value if value is not None else "UNKNOWN").replace("`", "\\`")
