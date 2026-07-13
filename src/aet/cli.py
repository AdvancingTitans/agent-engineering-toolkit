"""Command-line entrypoint for Agent Engineering Toolkit."""

from __future__ import annotations

import argparse
import sys
import json
import hashlib
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, load_audit_config
from .context import ContextError, discover_context, record_context, render_context_verification, verify_context
from .decision import DecisionError, add_decision, init_ledger, list_decisions, render_decisions, supersede_decision, verify_ledger
from .discovery import discover_assets
from .evidence import EvidenceError, bind_proof, compile_evidence_pack, render_evidence_viewer, trace_command, workspace_snapshot
from .evolve import EvolveError, build_evolution, collect_evolution, query_evolution, write_evolution_plan, write_evolution_report
from .learn import LearnError, adopt, collect, gate, gate_observed, harvest, inspect_experiences, inspect_feedback, mine, propose, record_feedback, reject, render_learn_viewer, replay, replay_observed, runner_inventory, sleep, stage, tournament, verify_suite
from .reporters import render_json, render_markdown, render_sarif, report_data
from .review import ReviewError, review
from .run import RunError, attach_artifact, close_run, init_run, render_run_status, run_status, verify_run
from .rules import run_rules
from .rulepacks import RulePackError, load_rulepack, rulepack_metadata, shadow_diff
from .triage import TriageError, triage_report
from .audit_feedback import AuditFeedbackError, OUTCOMES as AUDIT_FEEDBACK_OUTCOMES, record_audit_feedback
from .audit_evolution import AuditEvolutionError, adopt_audit_rule, aggregate_shadow_audits, gate_audit_rule, propose_audit_rule, replay_audit_rule, stage_audit_rule
from .evolution import CandidateError, default_registry, load_candidate
from .policy_targets import PolicyTargetError, adopt_policy_candidate, apply_audit_profile, evaluate_trace_validator, gate_policy_candidate, propose_policy_candidate, replay_policy_candidate, review_policy_findings, stage_policy_candidate, validate_policy_transition
from .quality import QualityError, diagnose_report, promote_regression


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aet", description="Evidence-first static audits for agent context and Skills.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (commands.add_parser("audit", help="Audit agent context assets and Skills."), commands.add_parser("review", help="Review a Git diff against an intent contract.")):
        command.add_argument("path", nargs="?", default=".", help="Repository root to inspect (default: current directory).")
        command.add_argument("--format", choices=("markdown", "json", "sarif"), default="markdown")
        command.add_argument("--output", type=Path, help="Write report to this path instead of stdout.")
        command.add_argument("--strict", action="store_true", help="Return non-zero for warnings as well as failures.")
        command.add_argument("--run", type=Path, help="Optionally attach this report to an existing AET Run Manifest.")
    commands.choices["audit"].add_argument("--config", type=Path, help="Optional aet.toml scan policy (default: <root>/aet.toml).")
    commands.choices["audit"].add_argument("--rulepack", type=Path, help="Optional local declarative rule pack; default is the versioned builtin pack.")
    commands.choices["audit"].add_argument("--shadow-rulepack", type=Path, help="Run a candidate rule pack beside the official audit without affecting its output or exit code.")
    commands.choices["audit"].add_argument("--shadow-output", type=Path, help="Required private comparison artifact when --shadow-rulepack is used.")
    commands.choices["audit"].add_argument("--profile", type=Path, help="Optional bounded audit-profile/v1 JSON.")
    review_parser = commands.choices["review"]
    review_parser.add_argument("--base", required=True, help="Git revision to compare with the current worktree.")
    review_parser.add_argument("--intent", type=Path, default=Path("aet.intent.json"), help="Human-reviewed JSON intent contract (default: aet.intent.json).")
    review_parser.add_argument("--policy", type=Path, help="Optional monotonic review-policy/v1 JSON.")
    trace_parser = commands.add_parser("trace", help="Run one explicit command and record redacted execution evidence.")
    trace_parser.add_argument("--output", required=True, type=Path, help="Write the Trace JSON to this path.")
    trace_parser.add_argument("--redact-pattern", action="append", default=[], help="Additional regular expression to redact from argv and log excerpts (repeatable).")
    trace_parser.add_argument("--proof", help="Bind this Trace to a proof id declared by --intent.")
    trace_parser.add_argument("--intent", type=Path, default=Path("aet.intent.json"), help="Intent contract used with --proof.")
    trace_parser.add_argument("--artifact", action="append", default=[], help="Root-relative text artifact generated by the command to capture, redact, and embed (repeatable).")
    trace_parser.add_argument("--run", type=Path, help="Optionally attach this Trace to an existing AET Run Manifest.")
    trace_parser.add_argument("--validator-policy", type=Path, help="Optional safe trace-validator/v1 JSON policy.")
    trace_parser.add_argument("--validate-artifact", type=Path, help="Artifact generated by the command and evaluated by --validator-policy.")
    trace_parser.add_argument("argv", nargs=argparse.REMAINDER, help="Command and arguments; must follow --.")
    evidence_parser = commands.add_parser("evidence", help="Compile portable evidence artifacts.")
    evidence_commands = evidence_parser.add_subparsers(dest="evidence_command", required=True)
    pack_parser = evidence_commands.add_parser("pack", help="Compile audit, review, and trace JSON into an Evidence Pack.")
    pack_parser.add_argument("--audit", type=Path, help="Audit JSON artifact.")
    pack_parser.add_argument("--review", type=Path, help="Review JSON artifact.")
    pack_parser.add_argument("--trace", type=Path, help="Trace JSON artifact.")
    pack_parser.add_argument("--output", required=True, type=Path, help="Write the Evidence Pack JSON to this path.")
    pack_parser.add_argument("--run", type=Path, help="Optionally attach this Evidence Pack to an existing AET Run Manifest.")
    viewer_parser = evidence_commands.add_parser("viewer", help="Render a static, no-network HTML view of an Evidence Pack.")
    viewer_parser.add_argument("--pack", required=True, type=Path, help="Evidence Pack JSON artifact.")
    viewer_parser.add_argument("--output", required=True, type=Path, help="Write HTML viewer to this path.")
    init_parser = commands.add_parser("init", help="Write a non-overwriting candidate aet.toml.")
    init_parser.add_argument("--output", type=Path, default=Path("aet.toml"), help="Candidate config path.")
    triage_parser = commands.add_parser("triage", help="Explainably rank findings; this never changes PASS/FAIL/UNKNOWN.")
    triage_parser.add_argument("--report", required=True, type=Path, help="Audit or review JSON report.")
    triage_parser.add_argument("--output", required=True, type=Path, help="Write triage JSON to this path.")
    triage_parser.add_argument("--policy", type=Path, help="Optional triage-policy/v1 JSON; it can only change ordering.")
    quality_parser = commands.add_parser("quality", help="Diagnose evidence findings and stage human-reviewed regression candidates.")
    quality_commands = quality_parser.add_subparsers(dest="quality_command", required=True)
    quality_diagnose = quality_commands.add_parser("diagnose", help="Create a deterministic diagnosis without changing finding status.")
    quality_diagnose.add_argument("--report", required=True, type=Path)
    quality_diagnose.add_argument("--policy", required=True, type=Path, help="Explicit local quality-mapping/v1 owner and repair policy.")
    quality_diagnose.add_argument("--output", required=True, type=Path)
    quality_promote = quality_commands.add_parser("promote", help="Promote one confirmed badcase into a staging-only regression candidate.")
    quality_promote.add_argument("--badcase", required=True, type=Path)
    quality_promote.add_argument("--diagnosis", required=True, type=Path)
    quality_promote.add_argument("--policy", required=True, type=Path, help="The same quality-mapping/v1 policy used for diagnosis.")
    quality_promote.add_argument("--output", required=True, type=Path)
    learn_parser = commands.add_parser("learn", help="Evidence-gated local asset evolution; proposals never auto-adopt.")
    learn_commands = learn_parser.add_subparsers(dest="learn_command", required=True)
    learn_harvest = learn_commands.add_parser("harvest", help="Normalize structured AET evidence without reading transcripts.")
    learn_harvest.add_argument("--runs", type=Path)
    learn_harvest.add_argument("--evidence", type=Path)
    learn_harvest.add_argument("--experience-store", type=Path, help="Optional local Evidence Only store to merge; never fetched or uploaded.")
    learn_harvest.add_argument("--output", required=True, type=Path)
    learn_collect = learn_commands.add_parser("collect", help="Add an Evidence Only experience pack to a local cross-project store.")
    learn_collect.add_argument("--experiences", required=True, type=Path)
    learn_collect.add_argument("--store", required=True, type=Path)
    for name in ("inspect", "summarize"):
        command = learn_commands.add_parser(name, help="Deterministically summarize Evidence Only experience records.")
        command.add_argument("--experiences", required=True, type=Path)
        command.add_argument("--output", required=True, type=Path)
    learn_mine = learn_commands.add_parser("mine", help="Deterministically group recurring evidence deviations.")
    learn_mine.add_argument("--experiences", required=True, type=Path)
    learn_mine.add_argument("--output", required=True, type=Path)
    learn_mine.add_argument("--target-type", choices=tuple(item.target_type for item in default_registry().list()), default="skill")
    learn_target = learn_commands.add_parser("target", help="List bounded evolution target adapters and maturity.")
    learn_target.add_argument("action", choices=("list",))
    learn_shadow = learn_commands.add_parser("shadow", help="Aggregate existing audit shadow artifacts; does not execute or adopt.")
    learn_shadow.add_argument("--reports", required=True, type=Path)
    learn_shadow.add_argument("--confirmations", required=True, type=Path)
    learn_shadow.add_argument("--output", required=True, type=Path)
    learn_propose = learn_commands.add_parser("propose", help="Create a Constitution-bound candidate for a registered evolution target.")
    learn_propose.add_argument("--patterns", required=True, type=Path)
    learn_propose.add_argument("--target", required=True, type=Path)
    learn_propose.add_argument("--output", required=True, type=Path)
    learn_propose.add_argument("--engine", choices=("rules", "model"), default="rules")
    learn_propose.add_argument("--model-command", nargs="+", help="Explicit argv for an opt-in model adapter; it receives JSON on stdin.")
    learn_propose.add_argument("--model-timeout-seconds", type=float, default=30)
    learn_propose.add_argument("--rejected", type=Path, help="Auditable local rejection records supplied as negative constraints.")
    learn_propose.add_argument("--target-type", choices=tuple(item.target_type for item in default_registry().list()), default="skill")
    learn_propose.add_argument("--proposal", type=Path, help="Bounded JSON Patch operations for policy targets.")
    learn_replay = learn_commands.add_parser("replay", help="Replay deterministic target-specific suites without changing the production asset.")
    learn_replay.add_argument("--candidate", required=True, type=Path)
    learn_replay.add_argument("--suite", action="append", required=True, type=Path)
    learn_replay.add_argument("--output", required=True, type=Path)
    learn_replay.add_argument("--runner", choices=("static", "scripted", "codex", "claude-code"), default="static", help="Explicit host. static is a document contract check, never observed behavior.")
    learn_replay.add_argument("--rollouts", type=int, default=1, help="Repeated isolated runs for non-static hosts.")
    learn_replay.add_argument("--seed", type=int)
    learn_replay.add_argument("--runner-config", type=Path, help="Optional local runner JSON configuration; it is never fetched.")
    learn_replay.add_argument("--target-type", choices=tuple(item.target_type for item in default_registry().list()))
    learn_gate = learn_commands.add_parser("gate", help="Run the target-specific core, validation, held-out, adversarial, and safety gates.")
    learn_gate.add_argument("--candidate", required=True, type=Path)
    learn_gate.add_argument("--validation", required=True, type=Path)
    learn_gate.add_argument("--held-out", required=True, type=Path)
    learn_gate.add_argument("--core", type=Path, help="Optional immutable core task suite; it may not regress.")
    learn_gate.add_argument("--output", required=True, type=Path)
    learn_gate.add_argument("--runner", choices=("static", "scripted", "codex", "claude-code"), default="static")
    learn_gate.add_argument("--rollouts", type=int, default=1)
    learn_gate.add_argument("--statistics-profile", choices=("preliminary", "adoptable"), default="preliminary")
    learn_gate.add_argument("--runner-config", type=Path)
    learn_gate.add_argument("--adversarial", type=Path, help="Required Constitution suite for audit-rule candidates.")
    learn_gate.add_argument("--target-type", choices=tuple(item.target_type for item in default_registry().list()))
    learn_runner = learn_commands.add_parser("runner", help="List or explicitly verify locally installed real-host runners.")
    learn_runner.add_argument("action", choices=("list", "verify"))
    learn_runner.add_argument("--runner", choices=("static", "scripted", "codex", "claude-code"))
    learn_runner.add_argument("--runner-config", type=Path)
    learn_feedback = learn_commands.add_parser("feedback", help="Record or inspect compact, Evidence Only human rollout feedback.")
    feedback_commands = learn_feedback.add_subparsers(dest="feedback_command", required=True)
    feedback_record = feedback_commands.add_parser("record")
    feedback_record.add_argument("--run", required=True, type=Path)
    feedback_record.add_argument("--outcome", choices=("accepted", "rejected"), required=True)
    feedback_record.add_argument("--reason-code", action="append", required=True)
    feedback_record.add_argument("--reason")
    feedback_record.add_argument("--output", required=True, type=Path)
    feedback_inspect = feedback_commands.add_parser("inspect")
    feedback_inspect.add_argument("--feedback", required=True, type=Path)
    feedback_inspect.add_argument("--output", required=True, type=Path)
    learn_tournament = learn_commands.add_parser("tournament", help="Select one observed-behavior finalist; it never adopts or stages automatically.")
    learn_tournament.add_argument("--candidate", action="append", required=True, type=Path)
    learn_tournament.add_argument("--validation", required=True, type=Path)
    learn_tournament.add_argument("--held-out", required=True, type=Path)
    learn_tournament.add_argument("--core", type=Path)
    learn_tournament.add_argument("--runner", choices=("scripted", "codex", "claude-code"), required=True)
    learn_tournament.add_argument("--rollouts", type=int, default=1)
    learn_tournament.add_argument("--statistics-profile", choices=("preliminary", "adoptable"), default="preliminary")
    learn_tournament.add_argument("--runner-config", type=Path)
    learn_tournament.add_argument("--output", required=True, type=Path)
    learn_suite = learn_commands.add_parser("suite", help="Verify Learn Task v2 fixture and task integrity without running a host.")
    suite_commands = learn_suite.add_subparsers(dest="suite_command", required=True)
    suite_verify = suite_commands.add_parser("verify")
    suite_verify.add_argument("--suite", required=True, type=Path)
    suite_verify.add_argument("--output", required=True, type=Path)
    learn_stage = learn_commands.add_parser("stage", help="Copy a passing candidate for human review; never adopts it.")
    learn_stage.add_argument("--candidate", required=True, type=Path)
    learn_stage.add_argument("--gate", required=True, type=Path)
    learn_stage.add_argument("--output", required=True, type=Path)
    learn_stage.add_argument("--target-type", choices=tuple(item.target_type for item in default_registry().list()))
    learn_adopt = learn_commands.add_parser("adopt", help="Human-authorized adoption of a passing, hash-bound staged asset candidate.")
    learn_adopt.add_argument("--candidate", required=True, type=Path)
    learn_adopt.add_argument("--gate", required=True, type=Path)
    learn_adopt.add_argument("--ledger", type=Path)
    learn_adopt.add_argument("--yes", action="store_true", help="Required acknowledgement that adoption writes the production target asset.")
    learn_adopt.add_argument("--target-type", choices=tuple(item.target_type for item in default_registry().list()))
    learn_adopt.add_argument("--shadow-aggregate", type=Path, help="Required adoption-grade shadow evidence for audit-rule adoption.")
    learn_reject = learn_commands.add_parser("reject", help="Record an auditable rejected candidate.")
    learn_reject.add_argument("--candidate", required=True, type=Path)
    learn_reject.add_argument("--reason", required=True)
    learn_reject.add_argument("--output", required=True, type=Path)
    learn_viewer = learn_commands.add_parser("viewer", help="Render a static, no-network HTML view of a learning Gate.")
    learn_viewer.add_argument("--gate", required=True, type=Path)
    learn_viewer.add_argument("--output", required=True, type=Path)
    learn_sleep = learn_commands.add_parser("sleep", help="Run harvest→mine→propose→replay→gate→stage; it never adopts.")
    learn_sleep.add_argument("--runs", type=Path)
    learn_sleep.add_argument("--evidence", type=Path)
    learn_sleep.add_argument("--experience-store", type=Path)
    learn_sleep.add_argument("--target", required=True, type=Path)
    learn_sleep.add_argument("--validation", required=True, type=Path)
    learn_sleep.add_argument("--held-out", required=True, type=Path)
    learn_sleep.add_argument("--core", type=Path)
    learn_sleep.add_argument("--output", required=True, type=Path)
    learn_sleep.add_argument("--engine", choices=("rules", "model"), default="rules")
    learn_sleep.add_argument("--model-command", nargs="+")
    learn_sleep.add_argument("--rejected", type=Path)
    learn_sleep.add_argument("--max-candidates", type=int, default=1)
    learn_sleep.add_argument("--max-replays", type=int, default=2)
    learn_sleep.add_argument("--max-model-calls", type=int, default=1)
    learn_sleep.add_argument("--timeout-seconds", type=float, default=120)
    learn_sleep.add_argument("--runner", choices=("static", "scripted", "codex", "claude-code"), default="static")
    learn_sleep.add_argument("--rollouts", type=int, default=1)
    learn_sleep.add_argument("--statistics-profile", choices=("preliminary", "adoptable"), default="preliminary")
    learn_sleep.add_argument("--runner-config", type=Path)
    learn_sleep.add_argument("--target-type", choices=tuple(item.target_type for item in default_registry().list()), default="skill")
    learn_sleep.add_argument("--proposal", type=Path, help="Required bounded policy operations for non-Skill policy targets.")
    learn_sleep.add_argument("--adversarial", type=Path, help="Required Constitution suite for audit-rule sleep.")
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
    context_parser = commands.add_parser("context", help="Record local context discovery and explicit read attestations.")
    context_commands = context_parser.add_subparsers(dest="context_command", required=True)
    context_discover = context_commands.add_parser("discover", help="Write a non-overwriting Context Manifest from discoverable assets.")
    context_discover.add_argument("path", nargs="?", default=".")
    context_discover.add_argument("--config", type=Path, help="Optional aet.toml scan policy (default: <root>/aet.toml).")
    context_discover.add_argument("--output", required=True, type=Path)
    context_record = context_commands.add_parser("record", help="Record local references and declared-read attestations.")
    context_record.add_argument("--manifest", required=True, type=Path)
    context_record.add_argument("--read", action="append", default=[], help="Root-relative recorded asset claimed as read (repeatable).")
    context_record.add_argument("--reference", action="append", default=[], help="Root-relative local reference to record (repeatable).")
    context_verify = context_commands.add_parser("verify", help="Verify recorded local context hashes and freshness.")
    context_verify.add_argument("--manifest", required=True, type=Path)
    context_verify.add_argument("--format", choices=("markdown", "json"), default="markdown")
    context_verify.add_argument("--output", type=Path)
    decision_parser = commands.add_parser("decision", help="Maintain a source-backed local Decision Ledger.")
    decision_commands = decision_parser.add_subparsers(dest="decision_command", required=True)
    decision_init = decision_commands.add_parser("init", help="Create a non-overwriting Decision Ledger.")
    decision_init.add_argument("--output", required=True, type=Path)
    decision_add = decision_commands.add_parser("add", help="Add a source-backed project decision.")
    decision_add.add_argument("--ledger", required=True, type=Path)
    decision_add.add_argument("--id", required=True)
    decision_add.add_argument("--claim", required=True)
    decision_add.add_argument("--evidence-state", choices=("EVIDENCED", "ATTESTED", "INFERRED", "UNKNOWN"), required=True)
    decision_add.add_argument("--state", choices=("PROPOSED", "ACCEPTED"), default="ACCEPTED")
    decision_add.add_argument("--source", action="append", default=[], help="Root-relative local source file (repeatable).")
    decision_add.add_argument("--supersedes", action="append", default=[], help="Existing decision id to supersede (repeatable).")
    for name, help_text in (("list", "List recorded decisions."), ("verify", "Verify recorded source hashes without mutating the ledger.")):
        command = decision_commands.add_parser(name, help=help_text)
        command.add_argument("--ledger", required=True, type=Path)
        command.add_argument("--format", choices=("markdown", "json"), default="markdown")
        command.add_argument("--output", type=Path)
    decision_supersede = decision_commands.add_parser("supersede", help="Mark a decision superseded by an accepted replacement.")
    decision_supersede.add_argument("--ledger", required=True, type=Path)
    decision_supersede.add_argument("--id", required=True)
    decision_supersede.add_argument("--by", required=True)
    run_parser = commands.add_parser("run", help="Record an optional, evidence-only delivery lifecycle.")
    run_commands = run_parser.add_subparsers(dest="run_command", required=True)
    run_init = run_commands.add_parser("init", help="Create a Run Manifest bound to a human-reviewed intent.")
    run_init.add_argument("--intent", type=Path, default=Path("aet.intent.json"))
    run_init.add_argument("--output", required=True, type=Path)
    for name, help_text in (("status", "Show the current lifecycle state without mutating it."), ("verify", "Persist STALE if the registered workspace changed."), ("close", "Close a fresh PACKED run.")):
        command = run_commands.add_parser(name, help=help_text)
        command.add_argument("--run", required=True, type=Path)
        command.add_argument("--format", choices=("markdown", "json"), default="markdown")
        command.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv[:3] == ["audit", "feedback", "record"]:
        return _audit_feedback_record(raw_argv[3:])
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    if args.command == "context":
        try:
            if args.context_command == "discover":
                root = Path(args.path).resolve()
                if not root.is_dir():
                    raise ContextError(f"context root does not exist: {root}")
                discover_context(root, args.output, load_audit_config(root, args.config))
                return 0
            if args.context_command == "record":
                record_context(args.manifest, read_paths=args.read, reference_paths=args.reference)
                return 0
            result = verify_context(args.manifest)
            rendered = render_context_verification(result, args.format)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                print(rendered, end="")
            return 1 if result["status"] == "FAIL" else 0
        except (ContextError, ConfigError) as error:
            raise SystemExit(f"aet: context failed: {error}") from error
    if args.command == "decision":
        try:
            if args.decision_command == "init":
                init_ledger(args.output)
                return 0
            if args.decision_command == "add":
                add_decision(args.ledger, identifier=args.id, claim=args.claim, evidence_state=args.evidence_state, state=args.state, sources=args.source, supersedes=args.supersedes)
                return 0
            if args.decision_command == "supersede":
                supersede_decision(args.ledger, identifier=args.id, replacement=args.by)
                return 0
            result = list_decisions(args.ledger) if args.decision_command == "list" else verify_ledger(args.ledger)
            rendered = render_decisions(result, args.format)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                print(rendered, end="")
            return 1 if result.get("status") == "FAIL" else 0
        except DecisionError as error:
            raise SystemExit(f"aet: decision failed: {error}") from error
    if args.command == "trace":
        if "--" not in raw_argv:
            parser.error("trace requires -- before the command argv")
        if args.argv[:1] == ["--"]:
            args.argv = args.argv[1:]
        try:
            proof = bind_proof(args.intent, args.proof) if args.proof else None
            trace_data, exit_code = trace_command(args.argv, args.output, args.redact_pattern, proof, args.artifact)
            if bool(args.validator_policy) != bool(args.validate_artifact):
                raise EvidenceError("--validator-policy and --validate-artifact must be provided together")
            if args.validator_policy:
                validate_path = args.validate_artifact.as_posix()
                if args.validate_artifact.is_absolute() or validate_path not in args.artifact:
                    raise EvidenceError("validated artifact must be the same relative path declared by --artifact")
                captured = next((item for item in trace_data["trace"].get("artifacts", []) if item.get("requested_path") == validate_path), None)
                if not isinstance(captured, dict) or captured.get("status") != "PASS" or captured.get("freshness") not in {"CREATED", "CHANGED"}:
                    raise EvidenceError("validated artifact was not freshly created or changed by this traced command")
                policy = _load_local_json(args.validator_policy)
                validation = evaluate_trace_validator(policy, args.validate_artifact)
                trace_data["validators"] = [validation]
                args.output.write_text(render_json(trace_data), encoding="utf-8")
                if validation["status"] != "PASS":
                    exit_code = 1
            if args.run:
                attach_artifact(args.run, "trace", args.output)
        except (EvidenceError, PolicyTargetError) as error:
            raise SystemExit(f"aet: trace failed: {error}") from error
        except RunError as error:
            raise SystemExit(f"aet: run failed: {error}") from error
        return exit_code
    if args.command == "evidence":
        try:
            if args.evidence_command == "pack":
                compile_evidence_pack(audit=args.audit, review=args.review, trace=args.trace, output=args.output)
                if args.run:
                    attach_artifact(args.run, "evidence_pack", args.output)
            else:
                render_evidence_viewer(args.pack, args.output)
        except EvidenceError as error:
            raise SystemExit(f"aet: evidence pack failed: {error}") from error
        except RunError as error:
            raise SystemExit(f"aet: run failed: {error}") from error
        return 0
    if args.command == "run":
        try:
            if args.run_command == "init":
                init_run(args.output, args.intent)
                status = run_status(args.output)
            elif args.run_command == "status":
                status = run_status(args.run)
            elif args.run_command == "verify":
                status = verify_run(args.run)
            else:
                status = close_run(args.run)
        except RunError as error:
            raise SystemExit(f"aet: run failed: {error}") from error
        rendered = render_run_status(status, "json" if args.run_command == "init" else args.format)
        if args.run_command == "init" or args.output is None:
            print(rendered, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        return 1 if args.run_command == "verify" and status["state"] == "STALE" else 0
    if args.command == "init":
        if args.output.exists():
            raise SystemExit(f"aet: candidate already exists and will not be overwritten: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("# Candidate AET scan policy; review before committing.\n[scan]\ninclude = []\nexclude = []\n", encoding="utf-8")
        return 0
    if args.command == "triage":
        try:
            policy = _load_local_json(args.policy) if args.policy else None
            if policy:
                validate_policy_transition("triage-policy", policy, policy)
            triage_report(args.report, args.output, policy)
        except (TriageError, PolicyTargetError) as error:
            raise SystemExit(f"aet: triage failed: {error}") from error
        return 0
    if args.command == "quality":
        try:
            if args.quality_command == "diagnose":
                diagnose_report(args.report, args.policy, args.output)
            else:
                promote_regression(badcase=args.badcase, diagnosis=args.diagnosis, policy=args.policy, output=args.output)
        except QualityError as error:
            raise SystemExit(f"aet: quality failed: {error}") from error
        return 0
    if args.command == "learn":
        try:
            if args.learn_command == "harvest":
                harvest(runs=args.runs, evidence=args.evidence, experience_store=args.experience_store, output=args.output)
                return 0
            if args.learn_command == "collect":
                collect(experiences=args.experiences, store=args.store)
                return 0
            if args.learn_command in {"inspect", "summarize"}:
                inspect_experiences(experiences=args.experiences, output=args.output)
                return 0
            if args.learn_command == "mine":
                mine(experiences=args.experiences, output=args.output, target_type=args.target_type)
                return 0
            if args.learn_command == "target":
                print(render_json({"report_kind": "evolution_targets", "targets": [{"target_type": item.target_type, "status": item.status} for item in default_registry().list()]}), end="")
                return 0
            if args.learn_command == "shadow":
                result = aggregate_shadow_audits(reports=args.reports, confirmations=args.confirmations, output=args.output)
                return 0 if result["status"] == "PASS" else 1
            if args.learn_command == "propose":
                if args.target_type == "audit-rule":
                    propose_audit_rule(patterns=args.patterns, target=args.target, output=args.output)
                elif args.target_type == "skill":
                    propose(patterns=args.patterns, target=args.target, output=args.output, engine=args.engine, model_command=args.model_command, model_timeout_seconds=args.model_timeout_seconds, rejected=args.rejected)
                else:
                    if args.proposal is None:
                        raise LearnError(f"{args.target_type} proposal requires --proposal with bounded JSON Patch operations")
                    propose_policy_candidate(target_type=args.target_type, target=args.target, proposal=args.proposal, output=args.output)
                return 0
            if args.learn_command == "replay":
                target_type = args.target_type or _candidate_target(args.candidate)
                if target_type == "audit-rule":
                    if len(args.suite) != 1:
                        raise LearnError("audit-rule replay accepts exactly one partitioned suite")
                    replay_audit_rule(candidate=args.candidate, suite=args.suite[0], output=args.output)
                    return 0
                if target_type != "skill":
                    if len(args.suite) != 1:
                        raise LearnError("policy replay accepts exactly one suite")
                    replay_policy_candidate(candidate=args.candidate, suite=args.suite[0], output=args.output)
                    return 0
                config = _runner_config(args.runner_config)
                if args.runner == "static":
                    replay(candidate=args.candidate, suite=args.suite, output=args.output)
                else:
                    replay_observed(candidate=args.candidate, suite=args.suite, output=args.output, runner_name=args.runner, rollouts=args.rollouts, seed=args.seed, runner_config=config)
                return 0
            if args.learn_command == "gate":
                target_type = args.target_type or _candidate_target(args.candidate)
                if target_type == "audit-rule":
                    if args.core is None or args.adversarial is None:
                        raise LearnError("audit-rule gate requires --core and --adversarial suites")
                    result = gate_audit_rule(candidate=args.candidate, core=args.core, validation=args.validation, held_out=args.held_out, adversarial=args.adversarial, output=args.output)
                    return 0 if result["status"] == "PASS" else 1
                if target_type != "skill":
                    if args.core is None or args.adversarial is None:
                        raise LearnError("policy gate requires --core and --adversarial suites")
                    result = gate_policy_candidate(candidate=args.candidate, core=args.core, validation=args.validation, held_out=args.held_out, adversarial=args.adversarial, output=args.output)
                    return 0 if result["status"] == "PASS" else 1
                config = _runner_config(args.runner_config)
                result = gate(candidate=args.candidate, validation=args.validation, held_out=args.held_out, core=args.core, output=args.output) if args.runner == "static" else gate_observed(candidate=args.candidate, validation=args.validation, held_out=args.held_out, core=args.core, output=args.output, runner_name=args.runner, rollouts=args.rollouts, statistics_profile=args.statistics_profile, runner_config=config)
                return 0 if result["status"] == "PASS" else 1
            if args.learn_command == "runner":
                config = _runner_config(args.runner_config)
                result = runner_inventory(name=args.runner if args.action == "verify" else None, config=config)
                print(render_json(result), end="")
                return 0 if all(item["available"] for item in result["runners"]) else 1
            if args.learn_command == "feedback":
                if args.feedback_command == "record":
                    record_feedback(run=args.run, outcome=args.outcome, reason_codes=args.reason_code, reason=args.reason, output=args.output)
                else:
                    inspect_feedback(feedback=args.feedback, output=args.output)
                return 0
            if args.learn_command == "tournament":
                result = tournament(candidates=args.candidate, validation=args.validation, held_out=args.held_out, core=args.core, output=args.output, runner_name=args.runner, rollouts=args.rollouts, statistics_profile=args.statistics_profile, runner_config=_runner_config(args.runner_config))
                return 0 if result.get("finalist", {}).get("status") == "PASS" else 1
            if args.learn_command == "suite":
                result = verify_suite(suite=args.suite, output=args.output)
                return 0 if result["status"] == "PASS" else 1
            if args.learn_command == "stage":
                if (args.target_type or _candidate_target(args.candidate)) == "audit-rule":
                    stage_audit_rule(candidate=args.candidate, gate=args.gate, output=args.output)
                elif (args.target_type or _candidate_target(args.candidate)) != "skill":
                    stage_policy_candidate(candidate=args.candidate, gate=args.gate, output=args.output)
                else:
                    stage(candidate=args.candidate, gate=args.gate, output=args.output)
                return 0
            if args.learn_command == "adopt":
                target_type = args.target_type or _candidate_target(args.candidate)
                if target_type == "audit-rule":
                    adopt_audit_rule(candidate=args.candidate, gate=args.gate, shadow_aggregate=args.shadow_aggregate, yes=args.yes, ledger=args.ledger)
                elif target_type != "skill":
                    adopt_policy_candidate(candidate=args.candidate, gate=args.gate, yes=args.yes, ledger=args.ledger)
                else:
                    if not args.yes:
                        raise LearnError("adopt requires --yes; stage is the safe default")
                    adopt(candidate=args.candidate, gate=args.gate, ledger=args.ledger)
                return 0
            if args.learn_command == "viewer":
                render_learn_viewer(gate=args.gate, output=args.output)
                return 0
            if args.learn_command == "sleep":
                if args.target_type != "skill":
                    result = _sleep_asset(args)
                    return 0 if result["status"] in {"PASS", "NOT_APPLICABLE"} else 1
                result = sleep(runs=args.runs, evidence=args.evidence, experience_store=args.experience_store, target=args.target, validation=args.validation, held_out=args.held_out, core=args.core, output=args.output, engine=args.engine, model_command=args.model_command, rejected=args.rejected, max_candidates=args.max_candidates, max_replays=args.max_replays, max_model_calls=args.max_model_calls, timeout_seconds=args.timeout_seconds, runner_name=args.runner, rollouts=args.rollouts, statistics_profile=args.statistics_profile, runner_config=_runner_config(args.runner_config))
                return 0 if result["status"] in {"PASS", "NOT_APPLICABLE"} else 1
            reject(candidate=args.candidate, reason=args.reason, output=args.output)
            return 0
        except (LearnError, AuditEvolutionError, CandidateError, PolicyTargetError) as error:
            raise SystemExit(f"aet: learn failed: {error}") from error
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
            official_rulepack = load_rulepack(args.rulepack)
        except (ConfigError, RulePackError) as error:
            raise SystemExit(f"aet: invalid audit policy: {error}") from error
        if bool(args.shadow_rulepack) != bool(args.shadow_output):
            raise SystemExit("aet: --shadow-rulepack and --shadow-output must be provided together")
        assets = discover_assets(root, config)
        snapshot = workspace_snapshot(root)
        findings = run_rules(root, assets, rulepack=official_rulepack)
        try:
            profile = _load_local_json(args.profile) if args.profile else None
            if profile:
                findings = apply_audit_profile(findings, profile)
        except PolicyTargetError as error:
            raise SystemExit(f"aet: invalid audit profile: {error}") from error
        official_engine = rulepack_metadata(official_rulepack)
        data = report_data(root, assets, findings, scope={"root": str(root), "config": config.to_dict()}, workspace_snapshot=snapshot, audit_engine=official_engine)
        if args.shadow_rulepack:
            try:
                candidate_rulepack = load_rulepack(args.shadow_rulepack)
                candidate_findings = run_rules(root, assets, rulepack=candidate_rulepack)
                if profile:
                    candidate_findings = apply_audit_profile(candidate_findings, profile)
                comparison = shadow_diff(findings, candidate_findings, official_engine=official_engine, candidate_engine=rulepack_metadata(candidate_rulepack), snapshot=snapshot)
                comparison["root"] = str(root)
                comparison["repository_fingerprint"] = _repository_fingerprint(root)
            except (RulePackError, OSError, ValueError) as error:
                comparison = {"schema_version": "audit-shadow/v1", "report_kind": "audit_shadow", "status": "INFRASTRUCTURE_ERROR", "error": str(error), "affects_official_output": False, "affects_official_exit_code": False, "workspace_snapshot": snapshot}
            args.shadow_output.parent.mkdir(parents=True, exist_ok=True)
            args.shadow_output.write_text(render_json(comparison), encoding="utf-8")
    else:
        try:
            findings, review_metadata = review(root, args.base, args.intent)
        except ReviewError as error:
            raise SystemExit(f"aet: review failed: {error}") from error
        if args.policy:
            try:
                policy = _load_local_json(args.policy)
                findings.extend(review_policy_findings(review_metadata, policy))
            except PolicyTargetError as error:
                raise SystemExit(f"aet: invalid review policy: {error}") from error
        data = report_data(root, [], findings, kind="review", review=review_metadata, workspace_snapshot=workspace_snapshot(root))
    rendered = {"markdown": render_markdown, "json": render_json, "sarif": render_sarif}[args.format](data)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.run:
        try:
            if args.output is None:
                raise RunError("--run requires --output so the produced report can be attached")
            attach_artifact(args.run, args.command, args.output)
        except RunError as error:
            raise SystemExit(f"aet: run failed: {error}") from error
    has_failure = data["summary"]["FAIL"] > 0
    has_warning = any(finding.severity.value == "WARN" for finding in findings)
    return 1 if has_failure or (args.strict and has_warning) else 0


def _runner_config(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    try:
        import json
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LearnError(f"runner config must be a local JSON object: {error}") from error
    if not isinstance(value, dict):
        raise LearnError("runner config must be a JSON object")
    return value


def _candidate_target(path: Path) -> str:
    return load_candidate(path).target.target_type


def _audit_feedback_record(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="aet audit feedback record", description="Record reproducible Evidence Only audit feedback.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--finding", required=True)
    parser.add_argument("--outcome", required=True, choices=tuple(AUDIT_FEEDBACK_OUTCOMES))
    parser.add_argument("--reason-code", required=True)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        record_audit_feedback(report=args.report, finding=args.finding, outcome=args.outcome, reason_code=args.reason_code, fixture=args.fixture, output=args.output)
    except AuditFeedbackError as error:
        raise SystemExit(f"aet: audit feedback failed: {error}") from error
    return 0


def _load_local_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PolicyTargetError(f"cannot read local policy {path}: {error}") from error
    if not isinstance(value, dict):
        raise PolicyTargetError("local policy must be a JSON object")
    return value


def _repository_fingerprint(root: Path) -> str:
    git_config = root / ".git" / "config"
    if not git_config.is_file():
        return "UNKNOWN"
    return hashlib.sha256(git_config.read_bytes()).hexdigest()


def _sleep_asset(args: argparse.Namespace) -> dict[str, object]:
    output: Path = args.output
    output.mkdir(parents=True, exist_ok=True)
    experiences = output / "experiences.json"
    patterns = output / "patterns.json"
    candidate = output / "candidate"
    harvest(runs=args.runs, evidence=args.evidence, experience_store=args.experience_store, output=experiences)
    mined = mine(experiences=experiences, output=patterns, target_type=args.target_type)
    if not mined.get("patterns"):
        result = {"report_kind": "asset_evolution_sleep", "target_type": args.target_type, "status": "NOT_APPLICABLE", "adopted": False}
        (output / "learning-run.json").write_text(render_json(result), encoding="utf-8")
        return result
    if args.target_type == "audit-rule":
        if args.core is None or args.adversarial is None:
            raise LearnError("audit-rule sleep requires --core and --adversarial")
        propose_audit_rule(patterns=patterns, target=args.target, output=candidate)
        replay_audit_rule(candidate=candidate, suite=args.validation, output=output / "replay.json")
        gate_result = gate_audit_rule(candidate=candidate, core=args.core, validation=args.validation, held_out=args.held_out, adversarial=args.adversarial, output=output / "gate.json")
        staged = stage_audit_rule(candidate=candidate, gate=output / "gate.json", output=output / "staged") if gate_result["status"] == "PASS" else None
    else:
        if args.proposal is None:
            raise LearnError("policy-target sleep requires --proposal")
        propose_policy_candidate(target_type=args.target_type, target=args.target, proposal=args.proposal, output=candidate)
        replay_policy_candidate(candidate=candidate, suite=args.validation, output=output / "replay.json")
        if args.core is None or args.adversarial is None:
            raise LearnError("policy-target sleep requires --core and --adversarial")
        gate_result = gate_policy_candidate(candidate=candidate, core=args.core, validation=args.validation, held_out=args.held_out, adversarial=args.adversarial, output=output / "gate.json")
        staged = stage_policy_candidate(candidate=candidate, gate=output / "gate.json", output=output / "staged") if gate_result["status"] == "PASS" else None
    result = {"report_kind": "asset_evolution_sleep", "target_type": args.target_type, "status": gate_result["status"], "stage": staged, "adopted": False}
    (output / "learning-run.json").write_text(render_json(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
