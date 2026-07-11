"""Command-line entrypoint for Agent Engineering Toolkit."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from . import __version__
from .discovery import discover_assets
from .reporters import render_json, render_markdown, render_sarif, report_data
from .rules import run_rules


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aet", description="Evidence-first static audits for agent context and Skills.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="Audit agent context assets and Skills.")
    audit.add_argument("path", nargs="?", default=".", help="Repository root to audit (default: current directory).")
    audit.add_argument("--format", choices=("markdown", "json", "sarif"), default="markdown")
    audit.add_argument("--output", type=Path, help="Write report to this path instead of stdout.")
    audit.add_argument("--strict", action="store_true", help="Return non-zero for warnings as well as failures.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "audit":
        return 2
    root = Path(args.path).resolve()
    if not root.is_dir():
        raise SystemExit(f"aet: audit root does not exist or is not a directory: {root}")
    assets = discover_assets(root)
    findings = run_rules(root, assets)
    data = report_data(root, assets, findings)
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
