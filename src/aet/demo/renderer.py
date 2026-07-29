"""Stable text, JSON, and Markdown demo projections."""

from __future__ import annotations

import json
import re

from .models import DemoResult


def render_text(result: DemoResult) -> str:
    lines = [
        "AET stale-proof demo",
        "",
        f"1. Test command executed                    {result.execution_status}",
        f"2. Proof matches the tested source          {result.before_state}",
        f"3. Source changed without rerunning tests   {result.after_state}",
        "",
    ]
    if result.overall_status in {"PASS", "PASS_WITH_WARNING"}:
        lines.append(
            "The test really passed, but that proof no longer applies to the current code."
        )
    for diagnostic in result.diagnostics:
        lines.append(f"Diagnostic: {_safe_text(diagnostic)}")
    if result.workspace_path:
        lines.append(f"Sandbox: {_safe_text(result.workspace_path)}")
    lines.append(f"Demo result: {result.overall_status}")
    return "\n".join(lines) + "\n"


def render_json(result: DemoResult) -> str:
    return json.dumps(
        result.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def render_markdown(result: DemoResult) -> str:
    diagnostics = "\n".join(
        f"- {_markdown(_safe_text(item))}" for item in result.diagnostics
    )
    body = [
        "# AET stale-proof demo",
        "",
        "| Step | Result |",
        "| --- | --- |",
        f"| Test command executed | `{_markdown(result.execution_status)}` |",
        f"| Proof matches tested source | `{_markdown(result.before_state)}` |",
        f"| Source changed without rerunning tests | `{_markdown(result.after_state)}` |",
        "",
        "The test really passed, but that proof no longer applies to the current code.",
        "",
        f"**Demo result:** `{_markdown(result.overall_status)}`",
    ]
    if diagnostics:
        body.extend(["", "## Diagnostics", "", diagnostics])
    return "\n".join(body) + "\n"


def render(result: DemoResult, output_format: str) -> str:
    if output_format == "json":
        return render_json(result)
    if output_format == "markdown":
        return render_markdown(result)
    if output_format == "text":
        return render_text(result)
    raise ValueError(f"unsupported demo format: {output_format}")


def _safe_text(value: str) -> str:
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "�", value)
    return value if len(value) <= 1000 else value[:997] + "..."


def _markdown(value: str) -> str:
    return value.replace("\\", "\\\\").replace("`", "\\`").replace("|", "\\|")
