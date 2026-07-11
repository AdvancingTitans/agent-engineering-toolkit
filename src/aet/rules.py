"""Deterministic, evidence-backed rules for the v0.1 static audit."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .models import Asset, Evidence, Finding, Severity, Status

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
INLINE_PATH_RE = re.compile(r"`([^`\n]+\.(?:md|py|sh|json|toml|yaml|yml))`")
COMMAND_TARGET_RE = re.compile(r"(?:python(?:3)?\s+|\.\/)([\w./-]+\.(?:py|sh))")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FIELD_RE = re.compile(r"^([\w-]+):\s*(.+?)\s*$", re.MULTILINE)
VERIFY_RE = re.compile(
    r"\b(?:verify|verification|validate|validation|test|tests|check|assert)\b|验证|校验|检查|测试|断言",
    re.IGNORECASE,
)


def run_rules(root: Path, assets: list[Asset]) -> list[Finding]:
    findings: list[Finding] = []
    if not assets:
        findings.append(
            Finding(
                "AET-GEN-001",
                Status.UNKNOWN,
                Severity.WARN,
                "No supported agent context assets were discovered.",
                (Evidence(".", detail="No AGENTS.md, CLAUDE.md, CODEX.md, .cursorrules, or SKILL.md found."),),
                "Add agent instructions or run aet against the intended repository root.",
            )
        )
        return findings

    texts: dict[Asset, str] = {asset: asset.path.read_text(encoding="utf-8") for asset in assets}
    for asset, text in texts.items():
        findings.extend(_check_local_targets(root, asset, text))
        if asset.kind == "instruction":
            findings.extend(_check_instruction_size(asset, text))
        else:
            findings.extend(_check_skill(asset, text))
    findings.extend(_check_duplicate_directives(texts))
    return sorted(findings, key=lambda item: (item.severity, item.rule_id, item.evidence[0].path))


def _check_local_targets(root: Path, asset: Asset, text: str) -> list[Finding]:
    findings: list[Finding] = []
    targets: list[tuple[str, int, str]] = []
    for match in LINK_RE.finditer(text):
        target = match.group(1).split("#", 1)[0].strip()
        if target:
            targets.append((target, _line_number(text, match.start(1)), "Markdown link"))
    for match in INLINE_PATH_RE.finditer(text):
        target = match.group(1)
        if target.startswith(("./", "../")) and not any(char.isspace() for char in target):
            targets.append((target, _line_number(text, match.start(1)), "inline path"))
    for match in COMMAND_TARGET_RE.finditer(text):
        targets.append((match.group(1), _line_number(text, match.start(1)), "command target"))

    seen: set[tuple[str, int]] = set()
    for target, line, source in targets:
        if target.startswith(("http://", "https://", "#", "~", "$", "<")) or "://" in target:
            continue
        target = target.strip("'\"")
        if not target or (target, line) in seen:
            continue
        seen.add((target, line))
        resolved = (asset.path.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        if not resolved.exists():
            rule_id = "AET-CTX-002" if source == "command target" else "AET-CTX-001"
            claim = f"{source.capitalize()} points to a missing local target: {target}"
            findings.append(
                Finding(
                    rule_id,
                    Status.FAIL,
                    Severity.ERROR,
                    claim,
                    (Evidence(asset.relative_path, line, target),),
                    "Create the target, correct the relative path, or remove the stale reference.",
                )
            )
    return findings


def _check_instruction_size(asset: Asset, text: str) -> list[Finding]:
    lines = text.count("\n") + 1
    if asset.path.parent.name == "." or asset.relative_path.count("/") == 0:
        if lines > 400 or len(text) > 16_000:
            return [
                Finding(
                    "AET-CTX-004",
                    Status.UNKNOWN,
                    Severity.WARN,
                    "Root-level instruction file is large enough to risk always-on context bloat.",
                    (Evidence(asset.relative_path, 1, f"{lines} lines; {len(text)} characters"),),
                    "Keep wayfinding in the root file and move task-specific procedures into on-demand Skills or references.",
                )
            ]
    return []


def _check_skill(asset: Asset, text: str) -> list[Finding]:
    findings: list[Finding] = []
    match = FRONTMATTER_RE.match(text)
    fields = {key: value.strip(" '\"") for key, value in FIELD_RE.findall(match.group(1))} if match else {}
    if not match or not fields.get("name") or not fields.get("description"):
        findings.append(
            Finding(
                "AET-SKL-001",
                Status.FAIL,
                Severity.ERROR,
                "Skill is missing required YAML frontmatter fields: name and description.",
                (Evidence(asset.relative_path, 1),),
                "Add a YAML frontmatter block with non-empty name and description fields.",
            )
        )
    elif fields["name"] != asset.path.parent.name:
        findings.append(
            Finding(
                "AET-SKL-002",
                Status.FAIL,
                Severity.ERROR,
                "Skill frontmatter name does not match its directory name.",
                (Evidence(asset.relative_path, 2, f"name={fields['name']}; directory={asset.path.parent.name}"),),
                "Rename the directory or set name to the exact directory name.",
            )
        )
    if not VERIFY_RE.search(text):
        findings.append(
            Finding(
                "AET-SKL-004",
                Status.UNKNOWN,
                Severity.WARN,
                "Skill does not state a verification or completion check.",
                (Evidence(asset.relative_path, 1),),
                "Add the concrete command, assertion, or observation required before the agent claims completion.",
            )
        )
    return findings


def _check_duplicate_directives(texts: dict[Asset, str]) -> list[Finding]:
    occurrences: dict[str, list[tuple[Asset, int]]] = defaultdict(list)
    for asset, text in texts.items():
        for number, line in enumerate(text.splitlines(), start=1):
            normalized = " ".join(line.strip().split())
            if len(normalized) >= 80 and not normalized.startswith(("#", "```", "|")):
                occurrences[normalized].append((asset, number))
    findings: list[Finding] = []
    for line, locations in occurrences.items():
        unique_files = {asset.relative_path for asset, _ in locations}
        if len(unique_files) < 2:
            continue
        evidence = tuple(Evidence(asset.relative_path, number, line[:120]) for asset, number in locations[:3])
        findings.append(
            Finding(
                "AET-CTX-005",
                Status.UNKNOWN,
                Severity.WARN,
                "Long directive is duplicated across agent context assets.",
                evidence,
                "Keep shared policy in one canonical reference and link to it from local instructions.",
            )
        )
    return findings


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1
