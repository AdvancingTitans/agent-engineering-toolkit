"""Command-line entrypoint for Agent Engineering Toolkit."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from . import __version__
from .discovery import discover_assets
from .reporters import render_json, render_markdown, render_sarif, report_data
from .review import ReviewError, review
from .rules import run_rules


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aet", description="Evidence-first static audits for agent context and Skills.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (commands.add_parser("audit", help="Audit agent context assets and Skills."), commands.add_parser("review", help="Review a Git diff against an intent contract.")):
        command.add_argument("path", nargs="?", default=".", help="Repository root to inspect (default: current directory).")
        command.add_argument("--format", choices=("markdown", "json", "sarif"), default="markdown")
        command.add_argument("--output", type=Path, help="Write report to this path instead of stdout.")
        command.add_argument("--strict", action="store_true", help="Return non-zero for warnings as well as failures.")
    review_parser = commands.choices["review"]
    review_parser.add_argument("--base", required=True, help="Git revision to compare with the current worktree.")
    review_parser.add_argument("--intent", type=Path, default=Path("aet.intent.json"), help="Human-reviewed JSON intent contract (default: aet.intent.json).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.path).resolve()
    if not root.is_dir():
        raise SystemExit(f"aet: root does not exist or is not a directory: {root}")
    if args.command == "audit":
        assets = discover_assets(root)
        findings = run_rules(root, assets)
        data = report_data(root, assets, findings)
    else:
        try:
            findings, review_metadata = review(root, args.base, args.intent)
        except ReviewError as error:
            raise SystemExit(f"aet: review failed: {error}") from error
        data = report_data(root, [], findings, kind="review", review=review_metadata)
    rendered = {"markdown": render_markdown, "json": render_json, "sarif": render_sarif}[args.format](data)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    has_failure = data["summary"]["FAIL"] > 0
    has_warning = any(finding.severity.value == "WARN" for finding in findings)
    return 1 if has_failure or (args.strict and has_warning) else 0


if __name__ == "__main__":
    raise SystemExit(main())
