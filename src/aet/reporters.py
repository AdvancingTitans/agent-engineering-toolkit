"""Render audit reports without losing source evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .models import Asset, Finding, Severity, Status, finding_counts


def report_data(root: Path, assets: list[Asset], findings: list[Finding], *, kind: str = "audit", review: dict | None = None, scope: dict | None = None, workspace_snapshot: dict | None = None, audit_engine: dict | None = None) -> dict:
    data = {
        "schema_version": __version__,
        "report_kind": kind,
        "generated_at": datetime.now(UTC).isoformat(),
        "root": str(root.resolve()),
        "run_id": __import__("uuid").uuid4().hex,
        "tool": {"name": "aet", "version": __version__},
        "scope": scope or {"root": str(root.resolve())},
        "assets": [{"path": asset.relative_path, "kind": asset.kind} for asset in assets],
        "sources": [],
        "claims": [],
        "findings": [finding.to_dict() for finding in findings],
        "summary": finding_counts(findings),
    }
    if review is not None:
        data["review"] = review
    if workspace_snapshot is not None:
        data["workspace_snapshot"] = workspace_snapshot
    if audit_engine is not None:
        data["audit_engine"] = audit_engine
    return data


def render_markdown(data: dict) -> str:
    summary = data["summary"]
    lines = [
        f"# Agent Engineering Toolkit {data['report_kind']}",
        "",
        f"- Root: `{data['root']}`",
        f"- Generated: `{data['generated_at']}`",
        f"- Assets: {len(data['assets'])}",
        f"- Findings: FAIL {summary['FAIL']} · UNKNOWN {summary['UNKNOWN']} · PASS {summary['PASS']}",
        "",
    ]
    if data["report_kind"] == "review":
        review = data["review"]
        lines.extend([
            f"- Base: `{review['base']}`",
            f"- Intent contract: `{review['intent_contract']}`",
            f"- Changed paths: {len(review['changed_paths'])}/{review['changed_path_budget']}",
        ])
    if data["report_kind"] == "audit" and isinstance(data.get("audit_engine"), dict):
        engine = data["audit_engine"]
        lines.extend([f"- Rule pack: `{engine.get('rulepack_id')}` revision {engine.get('rulepack_revision')}", f"- Rule pack SHA-256: `{engine.get('rulepack_sha256')}`"])
    if not data["findings"]:
        lines.extend(["No findings. The discovered assets passed the active, hash-bound audit rule pack.", ""])
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
