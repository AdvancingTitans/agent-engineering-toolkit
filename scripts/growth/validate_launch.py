#!/usr/bin/env python3
"""Aggregate deterministic repository-side launch readiness checks."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_links import check as check_links
from verify_readme_budget import verify as verify_readme
from verify_social_preview import verify as verify_social


COMMUNITY_FILES = (
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "SUPPORT.md",
    "GOVERNANCE.md",
    "ROADMAP.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)
FORBIDDEN_CLAIMS = (
    "guaranteed star growth",
    "guarantee github stars",
    "proves all agents",
    "produces a holistic trust score",
)
LAUNCH_BRIEFS = (
    "github-release.md",
    "show-hn.md",
    "product-hunt.md",
    "x.md",
    "linkedin.md",
    "reddit.md",
    "zhihu.md",
    "juejin.md",
    "v2ex.md",
)


def validate(stage: str, strict: bool) -> list[str]:
    root = Path.cwd()
    failures = verify_readme(root / "README.md", 250)
    failures.extend(verify_social(root / "site/assets/social-preview.png"))
    failures.extend(check_links([root / "README.md", root / "docs", root / "site"]))
    for relative in COMMUNITY_FILES:
        if not (root / relative).is_file():
            failures.append(f"missing community file: {relative}")
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "README.md", root / "PYPI_README.md", root / "docs/README.zh-CN.md")
    ).lower()
    for claim in FORBIDDEN_CLAIMS:
        if claim in text:
            failures.append(f"forbidden generalized claim: {claim}")
    if "not another coding agent" not in text:
        failures.append("README/PyPI boundary is missing")
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = re.search(
        r'__version__\s*=\s*"([^"]+)"',
        (root / "src/aet/__init__.py").read_text(encoding="utf-8"),
    )
    if runtime is None or metadata["project"]["version"] != runtime.group(1):
        failures.append("pyproject and runtime version differ")
    if stage in {"distribution", "launch", "all"}:
        required = (
            "skills/README.md",
            "skills/catalog.json",
            "integrations/github-action-template/action.yml",
            "ops/growth/experiments.yml",
            "ops/growth/launch/manual-actions.md",
        )
        for relative in required:
            if not (root / relative).is_file():
                failures.append(f"missing distribution asset: {relative}")
    if stage in {"launch", "all"}:
        copy_root = root / "ops/growth/launch/copy"
        for name in LAUNCH_BRIEFS:
            path = copy_root / name
            if not path.is_file():
                failures.append(f"missing launch brief: {name}")
                continue
            brief = path.read_text(encoding="utf-8")
            if "Owner:" not in brief or "Stop Rule:" not in brief:
                failures.append(f"{path}: owner or Stop Rule is missing")
        show_hn = copy_root / "show-hn.md"
        if show_hn.is_file():
            value = show_hn.read_text(encoding="utf-8")
            if value.splitlines()[:1] != ["HUMAN_REWRITE_REQUIRED"]:
                failures.append("show-hn.md: first line must be HUMAN_REWRITE_REQUIRED")
            for phrase in ("please upvote", "vote for this", "ask friends to"):
                if phrase in value.lower():
                    failures.append(f"show-hn.md: prohibited solicitation: {phrase}")
        product_hunt = copy_root / "product-hunt.md"
        if product_hunt.is_file():
            value = product_hunt.read_text(encoding="utf-8")
            match = re.search(
                r"Description \(\d+ characters;[^\n]*\):\n\n> ([^\n]+)",
                value,
            )
            if match is None:
                failures.append("product-hunt.md: measurable description is missing")
            elif len(match.group(1)) > 260:
                failures.append(
                    f"product-hunt.md: description is {len(match.group(1))}/260 characters"
                )
    readme = (root / "README.md").read_text(encoding="utf-8")
    readme_lower = readme.lower()
    version = metadata["project"]["version"]
    if strict and not (
        ("public pypi" in readme_lower and "v1.11.1" in readme_lower)
        or f"pypi v{version}" in readme_lower
    ):
        failures.append(
            "strict readiness requires the current PyPI release-state disclosure"
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=("conversion", "distribution", "launch", "all"),
        default="all",
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    failures = validate(args.stage, args.strict)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Launch readiness PASS: stage={args.stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
