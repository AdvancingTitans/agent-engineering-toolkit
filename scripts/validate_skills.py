#!/usr/bin/env python3
"""Validate the five distributed AET Skills without invoking a model."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


EXPECTED = ("aet-check", "aet-scope", "aet-proof", "aet-fresh", "aet-plan")
COMMANDS = {
    "aet-check": "aet quick check",
    "aet-scope": "aet quick scope",
    "aet-proof": "aet quick proof",
    "aet-fresh": "aet quick fresh",
    "aet-plan": "aet plan",
}


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def validate(root: Path, strict: bool) -> list[str]:
    failures: list[str] = []
    catalog_path = root / "skills/catalog.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{catalog_path}: {error}"]
    if catalog.get("schema_version") != "aet-skill-catalog/v1":
        failures.append("skills/catalog.json: unsupported schema_version")
    entries = catalog.get("skills")
    if not isinstance(entries, list):
        return [*failures, "skills/catalog.json: skills must be an array"]
    ids = [entry.get("id") for entry in entries if isinstance(entry, dict)]
    if tuple(ids) != EXPECTED:
        failures.append(f"skills/catalog.json: expected {EXPECTED}, got {tuple(ids)}")
    readme = (root / "skills/README.md").read_text(encoding="utf-8")
    for entry in entries:
        if not isinstance(entry, dict):
            failures.append("skills/catalog.json: each entry must be an object")
            continue
        skill_id = entry.get("id")
        if skill_id not in EXPECTED:
            continue
        path = root / str(entry.get("path", ""))
        skill_path = path / "SKILL.md"
        if path.name != skill_id:
            failures.append(f"{skill_id}: catalog path does not match id")
        try:
            text = skill_path.read_text(encoding="utf-8")
        except OSError as error:
            failures.append(f"{skill_path}: {error}")
            continue
        metadata = _frontmatter(text)
        if metadata.get("name") != skill_id:
            failures.append(f"{skill_path}: frontmatter name must be {skill_id}")
        if not metadata.get("description"):
            failures.append(f"{skill_path}: frontmatter description is required")
        if COMMANDS[skill_id] not in text:
            failures.append(f"{skill_path}: missing canonical command {COMMANDS[skill_id]}")
        if f"`{skill_id}`" not in readme:
            failures.append(f"skills/README.md: missing {skill_id}")
        for field in ("writes", "executes_commands", "network", "authority", "primary_question"):
            if field not in entry:
                failures.append(f"{skill_id}: catalog field {field} is required")
        if skill_id == "aet-plan":
            if entry.get("executes_commands") is not False or entry.get("authority") != "PROPOSED":
                failures.append("aet-plan: must remain non-executing and PROPOSED")
            if not re.search(r"do not implement|Never edit", text, re.IGNORECASE):
                failures.append("aet-plan: implementation boundary is missing")
        if skill_id == "aet-proof" and "explicit" not in text.lower():
            failures.append("aet-proof: explicit execution boundary is missing")
    if strict and "DISABLE_TELEMETRY=1" not in readme:
        failures.append("skills/README.md: skills.sh telemetry opt-out is missing")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    failures = validate(args.root.resolve(), args.strict)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("AET Skill catalog PASS: 5 Skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
