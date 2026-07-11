"""Render audit reports without losing source evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .models import Asset, Finding, Severity, Status, finding_counts


def report_data(root: Path, assets: list[Asset], findings: list[Finding]) -> dict:
    return {
        "schema_version": "0.1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(root.resolve()),
        "assets": [{"path": asset.relative_path, "kind": asset.kind} for asset in assets],
        "findings": [finding.to_dict() for finding in findings],
        "summary": finding_counts(findings),
    }


def render_markdown(data: dict) -> str:
    summary = data["summary"]
    lines = [
        "# Agent Engineering Toolkit audit",
        "",
        f"- Root: `{data['root']}`",
        f"- Generated: `{data['generated_at']}`",
        f"- Assets: {len(data['assets'])}",
        f"- Findings: FAIL {summary['FAIL']} · UNKNOWN {summary['UNKNOWN']} · PASS {summary['PASS']}",
        "",
    ]
    if not data["findings"]:
        lines.extend(["No findings. The discovered assets passed the v0.1 static rules.", ""])
        return "\n".join(lines)
    lines.extend(["## Findings", "", "| Rule | Status | Severity | Evidence | Claim |", "|---|---|---|---|---|"])
    for finding in data["findings"]:
        evidence = finding["evidence"][0]
        location = evidence["path"] + (f":{evidence['line']}" if evidence["line"] else "")
        claim = finding["claim"].replace("|", "\\|")
        lines.append(f"| `{finding['rule_id']}` | {finding['status']} | {finding['severity']} | `{location}` | {claim} |")
    lines.extend(["", "## Remediation", ""])
    for finding in data["findings"]:
        lines.append(f"- `{finding['rule_id']}` — {finding['remediation']}")
    lines.append("")
    return "\n".join(lines)


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render_sarif(data: dict) -> str:
    results = []
    rules: dict[str, dict] = {}
    for finding in data["findings"]:
        rule_id = finding["rule_id"]
        rules.setdefault(
            rule_id,
            {
                "id": rule_id,
                "shortDescription": {"text": finding["claim"]},
                "help": {"text": finding["remediation"]},
            },
        )
        evidence = finding["evidence"][0]
        level = {Severity.ERROR.value: "error", Severity.WARN.value: "warning", Severity.INFO.value: "note"}[finding["severity"]]
        result = {
            "ruleId": rule_id,
            "level": level,
            "message": {"text": f"[{finding['status']}] {finding['claim']}"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": evidence["path"]}}}],
            "properties": {"status": finding["status"], "ruleVersion": finding["rule_version"]},
        }
        if evidence["line"]:
            result["locations"][0]["physicalLocation"]["region"] = {"startLine": evidence["line"]}
        results.append(result)
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "aet", "rules": list(rules.values())}}, "results": results}],
    }
    return json.dumps(sarif, indent=2, ensure_ascii=False) + "\n"
