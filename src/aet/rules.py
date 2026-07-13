"""Deterministic, evidence-backed rules for the v0.1 static audit."""

from __future__ import annotations

import re
import json
import shlex
from collections import defaultdict
from pathlib import Path

from .models import Asset, Evidence, Finding, Severity, Status
from .rulepacks import load_rulepack

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
INLINE_PATH_RE = re.compile(r"`([^`\n]+\.(?:md|py|sh|json|toml|yaml|yml))`")
ABSOLUTE_PATH_RE = re.compile(r"(?<![\w:])(/(?:[\w .@+-]+/)*[\w .@+-]+\.(?:md|py|sh|json|toml|yaml|yml))(?!\w)")
COMMAND_TARGET_RE = re.compile(r"(?:python(?:3)?\s+|\.\/)([\w./-]+\.(?:py|sh))")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FIELD_RE = re.compile(r"^([\w-]+):\s*(.+?)\s*$", re.MULTILINE)
VERIFY_RE = re.compile(
    r"\b(?:verify|verification|validate|validation|test|tests|check|assert)\b|验证|校验|检查|测试|断言",
    re.IGNORECASE,
)


def run_rules(root: Path, assets: list[Asset], *, rulepack: dict | None = None) -> list[Finding]:
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

    texts: dict[Asset, str] = {asset: asset.path.read_text(encoding="utf-8") for asset in assets}
    selected = rulepack or load_rulepack()
    for rule in selected["rules"]:
        detector = rule["detector"]["type"]
        detected: list[Finding] = []
        if detector == "local_targets":
            for asset, text in texts.items():
                detected.extend(_check_local_targets(root, asset, text))
        elif detector == "instruction_size":
            for asset, text in texts.items():
                if asset.kind == "instruction":
                    detected.extend(_check_instruction_size(asset, text))
        elif detector == "skill_contract":
            for asset, text in texts.items():
                if asset.kind == "skill":
                    detected.extend(_check_skill(asset, text))
        elif detector == "duplicate_normalized_line":
            detected.extend(_check_duplicate_directives(texts))
        elif detector == "json_script_target_exists":
            detected.extend(_check_json_script_targets(root, rule))
        match_rule_id = rule["detector"].get("match_rule_id")
        if match_rule_id:
            detected = [item for item in detected if item.rule_id == match_rule_id]
        findings.extend(_apply_declarative_result(item, rule) for item in detected)
    return sorted(findings, key=lambda item: (item.severity, item.rule_id, item.evidence[0].path))


def _apply_declarative_result(finding: Finding, rule: dict) -> Finding:
    result = rule.get("result")
    if not result:
        return finding
    return Finding(
        str(rule["rule_id"]), Status(result["status"]), Severity(result["severity"]),
        finding.claim if result.get("preserve_detector_detail") else str(result["claim"]), finding.evidence,
        finding.remediation if result.get("preserve_detector_detail") else str(result["remediation"]),
        str(rule.get("revision", finding.rule_version)),
    )


def _check_json_script_targets(root: Path, rule: dict) -> list[Finding]:
    findings: list[Finding] = []
    for relative in rule["detector"].get("files", ["package.json"]):
        source = (root / relative).resolve()
        try:
            source.relative_to(root.resolve())
        except ValueError:
            continue
        if not source.is_file():
            continue
        try:
            source_text = source.read_text(encoding="utf-8")
            scripts = json.loads(source_text).get("scripts", {})
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        if not isinstance(scripts, dict):
            continue
        for name, command in sorted(scripts.items()):
            if not isinstance(command, str):
                continue
            try:
                tokens = shlex.split(command)
            except ValueError:
                tokens = command.split()
            for token in tokens:
                cleaned = token.strip("'\"")
                if "/" not in cleaned or not cleaned.endswith((".js", ".mjs", ".cjs", ".py", ".sh")):
                    continue
                candidate = (root / cleaned).resolve()
                try:
                    candidate.relative_to(root.resolve())
                except ValueError:
                    continue
                if candidate.exists():
                    continue
                result = rule["result"]
                findings.append(Finding(
                    rule["rule_id"], Status(result["status"]), Severity(result["severity"]),
                    result["claim"], (Evidence(Path(relative).as_posix(), _line_number(source_text, source_text.find(cleaned)), f"script={name}; target={cleaned}"),),
                    result["remediation"], str(rule.get("revision", 1)),
                ))
    return findings


def _check_local_targets(root: Path, asset: Asset, text: str) -> list[Finding]:
    findings: list[Finding] = []
    targets: list[tuple[str, int, str]] = []
    fenced = [(match.start(), match.end()) for match in re.finditer(r"```.*?```", text, re.DOTALL)]

    def is_example(index: int) -> bool:
        return any(start <= index < end for start, end in fenced)

    for match in LINK_RE.finditer(text):
        if is_example(match.start()):
            continue
        target = match.group(1).split("#", 1)[0].strip()
        if target:
            targets.append((target, _line_number(text, match.start(1)), "Markdown link"))
    for match in INLINE_PATH_RE.finditer(text):
        if is_example(match.start()):
            continue
        target = match.group(1)
        if target.startswith(("./", "../")) and not any(char.isspace() for char in target):
            targets.append((target, _line_number(text, match.start(1)), "inline path"))
    for match in ABSOLUTE_PATH_RE.finditer(text):
        if is_example(match.start()):
            continue
        targets.append((match.group(1), _line_number(text, match.start(1)), "absolute local path"))
    for match in COMMAND_TARGET_RE.finditer(text):
        if is_example(match.start()):
            continue
        targets.append((match.group(1), _line_number(text, match.start(1)), "command target"))

    seen: set[tuple[str, int]] = set()
    for target, line, source in targets:
        if target.startswith(("http://", "https://", "#", "~", "$", "<")) or "://" in target:
            continue
        target = target.strip("'\"")
        if not target or (target, line) in seen:
            continue
        seen.add((target, line))
        resolved = Path(target).resolve() if Path(target).is_absolute() else (asset.path.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            if not Path(target).is_absolute():
                continue
        if not resolved.exists():
            rule_id = "AET-CTX-002" if source == "command target" else "AET-CTX-003" if source == "absolute local path" else "AET-CTX-001"
            claim = f"{source.capitalize()} points to a missing local target: {target}"
            replacement = _absorbed_skill_replacement(Path(target), resolved)
            remediation = "Create the target, correct the relative path, or remove the stale reference."
            if replacement is not None:
                remediation += f" This Skill was absorbed; update the index to the installed replacement: {replacement}. The missing reference remains a FAIL until its owner updates it."
            findings.append(
                Finding(
                    rule_id,
                    Status.FAIL,
                    Severity.ERROR,
                    claim,
                    (Evidence(asset.relative_path, line, target),),
                    remediation,
                )
            )
    return findings


def _absorbed_skill_replacement(target: Path, resolved: Path) -> str | None:
    """Find a local Hermes-style migration marker without weakening a missing-path FAIL."""
    parts = target.parts
    if "skills" not in parts:
        return None
    index = len(parts) - 1 - parts[::-1].index("skills")
    relative = parts[index + 1:]
    if len(relative) < 3 or relative[-1] != "SKILL.md":
        return None
    skills_root = Path(*parts[:index + 1])
    category, skill_name = relative[0], relative[1]
    marker = skills_root / ".archive" / "curator-reconstructed" / category / skill_name / ".absorbed_into"
    try:
        replacement_name = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    replacement = skills_root / category / replacement_name / "SKILL.md"
    return str(replacement) if replacement.is_file() else None


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
