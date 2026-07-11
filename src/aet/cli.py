"""Command-line entrypoint for Agent Engineering Toolkit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, load_audit_config
from .discovery import discover_assets
from .evidence import EvidenceError, bind_proof, compile_evidence_pack, render_evidence_viewer, trace_command, workspace_snapshot
from .evolve import EvolveError, build_evolution, collect_evolution, query_evolution, write_evolution_plan, write_evolution_report
from .reporters import render_json, render_markdown, render_sarif, report_data
from .review import ReviewError, review
from .rules import run_rules
from .triage import TriageError, triage_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aet", description="Evidence-first static audits for agent context and Skills.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (commands.add_parser("audit", help="Audit agent context assets and Skills."), commands.add_parser("review", help="Review a Git diff against an intent contract.")):
        command.add_argument("path", nargs="?", default=".", help="Repository root to inspect (default: current directory).")
        command.add_argument("--format", choices=("markdown", "json", "sarif"), default="markdown")
        command.add_argument("--output", type=Path, help="Write report to this path instead of stdout.")
        command.add_argument("--strict", action="store_true", help="Return non-zero for warnings as well as failures.")
    commands.choices["audit"].add_argument("--config", type=Path, help="Optional aet.toml scan policy (default: <root>/aet.toml).")
    review_parser = commands.choices["review"]
    review_parser.add_argument("--base", required=True, help="Git revision to compare with the current worktree.")
    review_parser.add_argument("--intent", type=Path, default=Path("aet.intent.json"), help="Human-reviewed JSON intent contract (default: aet.intent.json).")
    trace_parser = commands.add_parser("trace", help="Run one explicit command and record redacted execution evidence.")
    trace_parser.add_argument("--output", required=True, type=Path, help="Write the Trace JSON to this path.")
    trace_parser.add_argument("--redact-pattern", action="append", default=[], help="Additional regular expression to redact from argv and log excerpts (repeatable).")
    trace_parser.add_argument("--proof", help="Bind this Trace to a proof id declared by --intent.")
    trace_parser.add_argument("--intent", type=Path, default=Path("aet.intent.json"), help="Intent contract used with --proof.")
    trace_parser.add_argument("argv", nargs=argparse.REMAINDER, help="Command and arguments; must follow --.")
    evidence_parser = commands.add_parser("evidence", help="Compile portable evidence artifacts.")
    evidence_commands = evidence_parser.add_subparsers(dest="evidence_command", required=True)
    pack_parser = evidence_commands.add_parser("pack", help="Compile audit, review, and trace JSON into an Evidence Pack.")
    pack_parser.add_argument("--audit", type=Path, help="Audit JSON artifact.")
    pack_parser.add_argument("--review", type=Path, help="Review JSON artifact.")
    pack_parser.add_argument("--trace", type=Path, help="Trace JSON artifact.")
    pack_parser.add_argument("--output", required=True, type=Path, help="Write the Evidence Pack JSON to this path.")
    viewer_parser = evidence_commands.add_parser("viewer", help="Render a static, no-network HTML view of an Evidence Pack.")
    viewer_parser.add_argument("--pack", required=True, type=Path, help="Evidence Pack JSON artifact.")
    viewer_parser.add_argument("--output", required=True, type=Path, help="Write HTML viewer to this path.")
    init_parser = commands.add_parser("init", help="Write a non-overwriting candidate aet.toml.")
    init_parser.add_argument("--output", type=Path, default=Path("aet.toml"), help="Candidate config path.")
    triage_parser = commands.add_parser("triage", help="Explainably rank findings; this never changes PASS/FAIL/UNKNOWN.")
    triage_parser.add_argument("--report", required=True, type=Path, help="Audit or review JSON report.")
    triage_parser.add_argument("--output", required=True, type=Path, help="Write triage JSON to this path.")
    evolve_parser = commands.add_parser("evolve", help="Evidence-linked repository archaeology (Repo Archaeologist).")
    evolve_commands = evolve_parser.add_subparsers(dest="evolve_command", required=True)
    plan = evolve_commands.add_parser("plan", help="Write a read-only evolution collection plan.")
    plan.add_argument("path", nargs="?", default=".")
    plan.add_argument("--question", required=True)
    plan.add_argument("--output", required=True, type=Path)
    collect = evolve_commands.add_parser("collect", help="Collect local Git/docs evidence and optional explicit GitHub sources.")
    collect.add_argument("path", nargs="?", default=".")
    collect.add_argument("--question", required=True)
    collect.add_argument("--output", required=True, type=Path)
    collect.add_argument("--source-export", type=Path)
    collect.add_argument("--remote", choices=("none", "github"), default="none")
    build = evolve_commands.add_parser("build", help="Build an object graph and linked evolution pack from a manifest.")
    build.add_argument("--manifest", required=True, type=Path)
    build.add_argument("--output", required=True, type=Path)
    report = evolve_commands.add_parser("report", help="Render a cited Markdown evolution report from an object graph.")
    report.add_argument("--graph", required=True, type=Path)
    report.add_argument("--output", required=True, type=Path)
    query = evolve_commands.add_parser("query", help="Search normalized evolution objects without making new claims.")
    query.add_argument("--graph", required=True, type=Path)
    query.add_argument("--question", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    if args.command == "trace":
        if "--" not in raw_argv:
            parser.error("trace requires -- before the command argv")
        if args.argv[:1] == ["--"]:
            args.argv = args.argv[1:]
        try:
            proof = bind_proof(args.intent, args.proof) if args.proof else None
            _, exit_code = trace_command(args.argv, args.output, args.redact_pattern, proof)
        except EvidenceError as error:
            raise SystemExit(f"aet: trace failed: {error}") from error
        return exit_code
    if args.command == "evidence":
        try:
            if args.evidence_command == "pack":
                compile_evidence_pack(audit=args.audit, review=args.review, trace=args.trace, output=args.output)
            else:
                render_evidence_viewer(args.pack, args.output)
        except EvidenceError as error:
            raise SystemExit(f"aet: evidence pack failed: {error}") from error
        return 0
    if args.command == "init":
        if args.output.exists():
            raise SystemExit(f"aet: candidate already exists and will not be overwritten: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("# Candidate AET scan policy; review before committing.\n[scan]\ninclude = []\nexclude = []\n", encoding="utf-8")
        return 0
    if args.command == "triage":
        try:
            triage_report(args.report, args.output)
        except TriageError as error:
            raise SystemExit(f"aet: triage failed: {error}") from error
        return 0
    if args.command == "evolve":
        try:
            if args.evolve_command == "plan":
                write_evolution_plan(Path(args.path), args.output, args.question)
            elif args.evolve_command == "collect":
                collect_evolution(Path(args.path), args.output, question=args.question, source_export=args.source_export, remote=args.remote)
            elif args.evolve_command == "build":
                build_evolution(args.manifest, args.output)
            elif args.evolve_command == "report":
                write_evolution_report(args.graph, args.output)
            else:
                print(render_json({"report_kind": "evolution_query", "objects": query_evolution(args.graph, args.question)}), end="")
        except EvolveError as error:
            raise SystemExit(f"aet: evolve failed: {error}") from error
        return 0
    root = Path(args.path).resolve()
    if not root.is_dir():
        raise SystemExit(f"aet: root does not exist or is not a directory: {root}")
    if args.command == "audit":
        try:
            config = load_audit_config(root, args.config)
        except ConfigError as error:
            raise SystemExit(f"aet: invalid config: {error}") from error
        assets = discover_assets(root, config)
        findings = run_rules(root, assets)
        data = report_data(root, assets, findings, scope={"root": str(root), "config": config.to_dict()}, workspace_snapshot=workspace_snapshot(root))
    else:
        try:
            findings, review_metadata = review(root, args.base, args.intent)
        except ReviewError as error:
            raise SystemExit(f"aet: review failed: {error}") from error
        data = report_data(root, [], findings, kind="review", review=review_metadata, workspace_snapshot=workspace_snapshot(root))
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
