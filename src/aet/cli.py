"""Command-line entrypoint for Agent Engineering Toolkit."""

from __future__ import annotations

import argparse
import sys
import json
import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, load_audit_config
from .context import ContextError, discover_context, record_context, render_context_verification, verify_context
from .decision import DecisionError, add_decision, init_ledger, list_decisions, render_decisions, supersede_decision, verify_ledger
from .discovery import discover_assets
from .evidence import EvidenceError, bind_proof, compile_evidence_pack, evidence_receipt, render_evidence_viewer, reuse_trace_command, seal_trace, trace_command, workspace_snapshot
from .evolve import EvolveError, build_evolution, collect_evolution, query_evolution, write_evolution_plan, write_evolution_report
from .learn import LearnError, adopt, assess_gate_history, collect, gate, gate_observed, harvest, inspect_experiences, inspect_feedback, mine, plan_observed_gate, propose, record_feedback, reject, render_learn_viewer, replay, replay_observed, runner_inventory, sleep, stage, tournament, verify_suite
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
from .gate_plan import GatePlanError
from .repository_audit import RepositoryAuditError, is_repository_case, run_repository_audit
from .narrative import render_quick_result, select_language
from .quick import quick_check, quick_fresh, quick_proof, quick_scope
from .bundle import (
    BundleError,
    compile_bundle,
    render_bundle_markdown,
    validate_bundle,
    validate_review_result,
)
from .investigation import (
    PortableInvestigationError,
    investigate_run,
    write_investigation_result,
)
from .run_normalization import (
    NormalizationError,
    load_normalized_run,
    normalize_run,
    write_normalized_run,
)
from .atlas.diff import compare_evidence_atlases
from .atlas.model import PERSPECTIVES
from .atlas.queries import (
    AtlasQueryError,
    explain_node,
    get_node_subgraph,
)
from .atlas.storage import (
    AtlasStorageError,
    build_evidence_atlas,
    default_atlas_path,
    load_evidence_atlas,
)
from .atlas.validator import AtlasValidationError, validate_evidence_atlas
from .atlas.viewer import serve_atlas, single_html
from .improvement.cli.improve import (
    compare_improvement_metrics,
    doctor_bundle,
    generate_agent_prompt,
    generate_improvements,
    validate_candidate_file,
    verify_issue,
)
from .planning.candidate_parser import parse_candidate, strict_json_loads
from .planning.context_builder import build_planning_context
from .planning.errors import PlanningError
from .planning.handoff import build_verification_handoff_from_package
from .planning.helper import explain_edit as explain_plan_edit
from .planning.helper import list_gaps as list_plan_gaps
from .planning.helper import show_plan, trace_path as trace_plan_path
from .planning.models import (
    PlanningBudgets,
    PlanningContext,
    PlanningRequest,
    canonical_json_bytes as planning_json_bytes,
    model_from_mapping,
)
from .planning.package_builder import (
    build_plan_package,
    validate_plan_package,
)
from .planning.request_normalizer import RequestOverrides, normalize_request
from .planning.skill_exporter import export_plan_skill
from .planning.validator import validate_plan_candidate


def _perspective_selection(value: str) -> tuple[str, ...]:
    identifiers = tuple(item.strip() for item in value.split(",") if item.strip())
    if not identifiers:
        raise argparse.ArgumentTypeError("select at least one Perspective")
    if len(set(identifiers)) != len(identifiers):
        raise argparse.ArgumentTypeError("Perspective selection contains duplicates")
    unsupported = sorted(set(identifiers) - set(PERSPECTIVES))
    if unsupported:
        raise argparse.ArgumentTypeError(
            f"unsupported Perspective: {', '.join(unsupported)}"
        )
    return identifiers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aet", description="Proof-carrying workflows for coding agents.")
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
    commands.choices["audit"].add_argument("--repo", type=Path, help="Local checkout for a built-in repository showcase case.")
    commands.choices["audit"].add_argument("--output-dir", type=Path, help="Bundle directory for a built-in repository showcase case (default: audit-result).")
    review_parser = commands.choices["review"]
    review_parser.add_argument("--base", required=True, help="Git revision to compare with the current worktree.")
    review_parser.add_argument("--intent", type=Path, default=Path("aet.intent.json"), help="Human-reviewed JSON intent contract (default: aet.intent.json).")
    review_parser.add_argument("--policy", type=Path, help="Optional monotonic review-policy/v1 JSON.")
    trace_parser = commands.add_parser("trace", help="Run one explicit command and record redacted execution evidence.")
    trace_parser.add_argument("--output", required=True, type=Path, help="Write the Trace JSON to this path.")
    trace_parser.add_argument("--reuse-if-fresh", action="store_true", help="Do not execute; reuse the output Trace only when command, proof, artifacts, logs, and workspace are exact and fresh.")
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
    receipt_parser = evidence_commands.add_parser("receipt", help="Write a compact hash-bound index for a canonical evidence report.")
    receipt_parser.add_argument("--report", required=True, type=Path, help="Canonical Audit, Review, Trace, or Evidence Pack JSON.")
    receipt_parser.add_argument("--output", type=Path, help="Write receipt JSON instead of stdout.")
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
    learn_replay.add_argument("--resume", action="store_true", help="Resume or reuse only an exact, hash-bound observed replay manifest; drift fails without execution.")
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
    learn_gate.add_argument("--gate-plan", type=Path, help="Pre-registered gate-plan/v2. Required for conditional observed adoption gates; legacy rollouts remain supported for compatibility.")
    learn_gate.add_argument("--adversarial", type=Path, help="Required Constitution suite for audit-rule candidates.")
    learn_gate.add_argument("--target-type", choices=tuple(item.target_type for item in default_registry().list()))
    learn_plan = learn_commands.add_parser("plan", help="Freeze a hash-bound, risk-conditioned observed Gate Plan before any rollout.")
    learn_plan.add_argument("--candidate", required=True, type=Path)
    learn_plan.add_argument("--validation", required=True, type=Path)
    learn_plan.add_argument("--held-out", required=True, type=Path)
    learn_plan.add_argument("--core", type=Path)
    learn_plan.add_argument("--runner", choices=("scripted", "codex", "claude-code"), required=True)
    learn_plan.add_argument("--runner-config", type=Path)
    learn_plan.add_argument("--risk-class", choices=("R0", "R1", "R2", "R3", "R4"), required=True)
    learn_plan.add_argument("--claim", action="append", required=True)
    learn_plan.add_argument("--min-pairs", type=int)
    learn_plan.add_argument("--max-pairs", type=int)
    learn_plan.add_argument("--batch-size", type=int)
    learn_plan.add_argument("--output", required=True, type=Path)
    learn_history = learn_commands.add_parser("history", help="Assess verified Gate history for planning only; history never enters PASS.")
    learn_history.add_argument("action", choices=("assess",))
    learn_history.add_argument("--registry", required=True, type=Path)
    learn_history.add_argument("--gate-plan", required=True, type=Path)
    learn_history.add_argument("--suite", required=True)
    learn_history.add_argument("--output", required=True, type=Path)
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
    run_normalize = run_commands.add_parser(
        "normalize",
        help="Normalize a supported native Agent run into canonical records.",
    )
    run_normalize.add_argument("--source", choices=("codex", "claude-code"), required=True)
    run_normalize.add_argument("--input", required=True, type=Path)
    run_normalize.add_argument("--output", required=True, type=Path)
    run_normalize.add_argument("--run-group-id")
    run_normalize.add_argument("--base-byte-offset", type=int, default=0)
    run_normalize.add_argument("--partial", action="store_true")
    run_normalize.add_argument("--generation-id")
    run_normalize.add_argument("--prior", type=Path)
    run_inspect = run_commands.add_parser(
        "inspect",
        help="Inspect canonical Run Records without mutating them.",
    )
    run_inspect.add_argument("--run", required=True, type=Path)
    run_inspect.add_argument("--tool-calls", action="store_true")
    run_inspect.add_argument("--format", choices=("json", "jsonl"), default="json")
    run_inspect.add_argument("--output", type=Path)
    investigate_parser = commands.add_parser(
        "investigate",
        help="Create one bounded, read-only investigation from canonical Run Records.",
    )
    investigate_parser.add_argument("--request", required=True, type=Path)
    investigate_parser.add_argument("--run", required=True, type=Path)
    investigate_parser.add_argument(
        "--workspace",
        type=Path,
        help="Read-only workspace used for explicitly supplied deterministic Proof receipts.",
    )
    investigate_parser.add_argument(
        "--proof",
        action="append",
        type=Path,
        default=[],
        help="Explicit local AET Proof receipt to inspect; repeatable.",
    )
    investigate_parser.add_argument("--output", required=True, type=Path)
    bundle_parser = commands.add_parser(
        "bundle",
        help="Create and validate Portable Evidence Bundles.",
    )
    bundle_commands = bundle_parser.add_subparsers(dest="bundle_command", required=True)
    bundle_create = bundle_commands.add_parser("create")
    bundle_create.add_argument("--investigation", required=True, type=Path)
    bundle_create.add_argument("--output", required=True, type=Path)
    bundle_create.add_argument("--bundle-id")
    bundle_create.add_argument("--created-at")
    bundle_create.add_argument("--claim-ref", action="append")
    bundle_validate = bundle_commands.add_parser("validate")
    bundle_validate.add_argument("bundle", type=Path)
    bundle_render = bundle_commands.add_parser("render")
    bundle_render.add_argument("--bundle", required=True, type=Path)
    bundle_render.add_argument("--format", choices=("markdown",), default="markdown")
    bundle_render.add_argument("--output", required=True, type=Path)
    bundle_review = bundle_commands.add_parser("validate-review")
    bundle_review.add_argument("--bundle", required=True, type=Path)
    bundle_review.add_argument("--review", required=True, type=Path)
    atlas_parser = commands.add_parser(
        "atlas",
        help="Build, validate, query, compare, and view deterministic Evidence Atlases.",
    )
    atlas_commands = atlas_parser.add_subparsers(dest="atlas_command", required=True)
    atlas_build = atlas_commands.add_parser("build")
    atlas_build.add_argument("bundle", type=Path)
    atlas_build.add_argument("--output", type=Path)
    atlas_build.add_argument("--max-depth", type=int, default=4)
    atlas_build.add_argument("--max-nodes", type=int, default=25)
    atlas_build.add_argument("--max-children", type=int, default=12)
    atlas_build.add_argument("--max-diagrams", type=int, default=100)
    atlas_build.add_argument(
        "--perspectives",
        type=_perspective_selection,
        help="Comma-separated fixed Perspective IDs; default builds all ten.",
    )
    atlas_build.add_argument("--no-llm", action="store_true")
    atlas_build.add_argument("--no-replace", action="store_true")
    atlas_validate = atlas_commands.add_parser("validate")
    atlas_validate.add_argument("input", type=Path)
    atlas_validate.add_argument("--bundle", type=Path)
    atlas_view = atlas_commands.add_parser("view")
    atlas_view.add_argument("input", type=Path)
    atlas_view.add_argument("--bundle", type=Path)
    atlas_view.add_argument("--host", default="127.0.0.1")
    atlas_view.add_argument("--port", type=int, default=0)
    atlas_view.add_argument("--no-browser", action="store_true")
    atlas_export = atlas_commands.add_parser("export")
    atlas_export.add_argument("input", type=Path)
    atlas_export.add_argument("--bundle", type=Path)
    atlas_export.add_argument(
        "--format",
        choices=("static-html", "single-html"),
        required=True,
    )
    atlas_export.add_argument("--output", required=True, type=Path)
    atlas_query = atlas_commands.add_parser("query")
    atlas_query.add_argument("input", type=Path)
    atlas_query.add_argument("--bundle", type=Path)
    atlas_query.add_argument("--perspective", required=True)
    atlas_query.add_argument("--root", required=True)
    atlas_query.add_argument("--depth", type=int, default=2)
    atlas_query.add_argument("--max-nodes", type=int, default=50)
    atlas_query.add_argument("--max-bytes", type=int, default=262_144)
    atlas_query.add_argument("--format", choices=("json",), default="json")
    atlas_explain = atlas_commands.add_parser("explain")
    atlas_explain.add_argument("input", type=Path)
    atlas_explain.add_argument("--bundle", type=Path)
    atlas_explain.add_argument("--node", required=True)
    atlas_diff = atlas_commands.add_parser("diff")
    atlas_diff.add_argument("before", type=Path)
    atlas_diff.add_argument("after", type=Path)
    atlas_diff.add_argument("--before-bundle", type=Path)
    atlas_diff.add_argument("--after-bundle", type=Path)
    atlas_diff.add_argument("--output", type=Path)
    improvement_parser = commands.add_parser(
        "improvement",
        help="Inspect Evidence Bundle readiness for deterministic improvements.",
    )
    improvement_commands = improvement_parser.add_subparsers(
        dest="improvement_command",
        required=True,
    )
    improvement_doctor = improvement_commands.add_parser("doctor")
    improvement_doctor.add_argument("bundle", type=Path)
    improve_parser = commands.add_parser(
        "improve",
        help="Generate deterministic evidence-grounded improvements.",
    )
    improve_parser.add_argument("arguments", nargs="+")
    plan_parser = commands.add_parser(
        "plan",
        help="Build and validate read-only Evidence-Guided Plans.",
    )
    plan_commands = plan_parser.add_subparsers(
        dest="plan_command",
        required=True,
    )
    plan_context = plan_commands.add_parser(
        "context",
        help="Build a deterministic Planning Context for a Host Planner.",
    )
    plan_context.add_argument("--workspace", type=Path, default=Path("."))
    request_input = plan_context.add_mutually_exclusive_group(required=True)
    request_input.add_argument("--request", type=Path)
    request_input.add_argument("--request-text")
    plan_context.add_argument("--bundle", type=Path)
    plan_context.add_argument("--atlas", type=Path)
    plan_context.add_argument("--output", required=True, type=Path)
    plan_context.add_argument("--allowed-path", action="append", default=[])
    plan_context.add_argument("--protected-path", action="append", default=[])
    plan_context.add_argument("--verification", action="append", default=[])
    plan_context.add_argument("--max-nodes", type=int, default=10_000)
    plan_context.add_argument("--max-source-files", type=int, default=200)
    plan_context.add_argument("--max-source-bytes", type=int, default=2_000_000)
    plan_context.add_argument("--max-edit-items", type=int, default=100)
    plan_context.add_argument("--max-depth", type=int, default=4)
    plan_validate_candidate = plan_commands.add_parser(
        "validate-candidate",
        help="Validate strict Host Plan Candidate JSON and write a Plan package.",
    )
    plan_validate_candidate.add_argument("--context", required=True, type=Path)
    plan_validate_candidate.add_argument("--candidate", required=True, type=Path)
    plan_validate_candidate.add_argument("--output", required=True, type=Path)
    plan_validate = plan_commands.add_parser(
        "validate",
        help="Validate an existing portable Plan package.",
    )
    plan_validate.add_argument("plan", type=Path)
    plan_show = plan_commands.add_parser("show", help="Render one validated Plan.")
    plan_show.add_argument("plan", type=Path)
    plan_explain = plan_commands.add_parser(
        "explain",
        help="Explain one validated Edit Item without creating facts.",
    )
    plan_explain.add_argument("plan", type=Path)
    plan_explain.add_argument("--edit", required=True)
    plan_trace = plan_commands.add_parser(
        "trace",
        help="Trace one Plan path to its recorded references.",
    )
    plan_trace.add_argument("plan", type=Path)
    plan_trace.add_argument("--path", required=True)
    plan_gaps = plan_commands.add_parser(
        "gaps",
        help="List recorded gaps, conflicts, and unknowns.",
    )
    plan_gaps.add_argument("plan", type=Path)
    plan_export_skill = plan_commands.add_parser(
        "export-skill",
        help="Export one validated Plan as a minimal read-only Host Skill.",
    )
    plan_export_skill.add_argument("plan", type=Path)
    plan_export_skill.add_argument(
        "--target",
        choices=("codex", "claude-code", "generic"),
        required=True,
    )
    plan_export_skill.add_argument("--output", required=True, type=Path)
    plan_handoff = plan_commands.add_parser(
        "verification-handoff",
        help="Map an external unified diff to pending Proof requests without execution.",
    )
    plan_handoff.add_argument("plan", type=Path)
    plan_handoff.add_argument("--diff", required=True, type=Path)
    plan_handoff.add_argument("--output", required=True, type=Path)
    mcp_parser = commands.add_parser(
        "mcp",
        help="Serve the optional Portable Evidence Bundle MCP convenience layer.",
    )
    mcp_commands = mcp_parser.add_subparsers(dest="mcp_command", required=True)
    mcp_commands.add_parser("serve", help="Serve newline-delimited MCP JSON-RPC over stdio.")
    quick_parser = commands.add_parser("quick", help="Run one bounded AET Quick surface.")
    quick_commands = quick_parser.add_subparsers(dest="quick_command", required=True)
    quick_check_parser = quick_commands.add_parser("check", help="Collect a bounded Agent engineering preflight.")
    quick_check_parser.add_argument("path", nargs="?", default=".")
    quick_check_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    quick_check_parser.add_argument("--request", default="", help="Original host request used only for language routing.")
    quick_check_parser.add_argument("--slash-command", action="store_true", help="Declare that the host request used a slash command.")
    quick_check_parser.add_argument("--max-findings", type=int, default=5)
    quick_scope_parser = quick_commands.add_parser("scope", help="Collect intent and diff facts for bounded investigation.")
    quick_scope_parser.add_argument("path", nargs="?", default=".")
    quick_scope_parser.add_argument("--base", required=True)
    quick_scope_parser.add_argument("--intent", type=Path)
    quick_scope_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    quick_scope_parser.add_argument("--request", default="")
    quick_scope_parser.add_argument("--slash-command", action="store_true")
    quick_proof_parser = quick_commands.add_parser("proof", help="Execute explicit argv and write one minimal proof receipt.")
    quick_proof_parser.add_argument("--output", required=True, type=Path)
    quick_proof_parser.add_argument("--relevant-path", action="append", default=[])
    quick_proof_parser.add_argument("--artifact", action="append", default=[])
    quick_proof_parser.add_argument(
        "--env-binding",
        action="append",
        default=[],
        help="Bind one named environment input by status and SHA-256 without storing its value.",
    )
    quick_proof_parser.add_argument("--redact-pattern", action="append", default=[])
    quick_proof_parser.add_argument("--request", default="")
    quick_proof_parser.add_argument("--slash-command", action="store_true")
    quick_proof_parser.add_argument("argv", nargs=argparse.REMAINDER)
    quick_fresh_parser = quick_commands.add_parser("fresh", help="Check whether a proof still applies to the current workspace.")
    quick_fresh_parser.add_argument("--proof", required=True, type=Path)
    quick_fresh_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    quick_fresh_parser.add_argument("--request", default="")
    quick_fresh_parser.add_argument("--slash-command", action="store_true")
    from .demo.cli import add_demo_parser

    add_demo_parser(commands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv[:3] == ["audit", "feedback", "record"]:
        return _audit_feedback_record(raw_argv[3:])
    parser = build_parser()
    try:
        args = parser.parse_args(raw_argv)
    except SystemExit as error:
        if raw_argv[:1] == ["demo"] and error.code:
            return 64
        raise
    if args.command == "demo":
        from .demo.cli import handle_demo

        return handle_demo(args)
    if args.command == "investigate":
        try:
            request = _load_portable_json(args.request, "investigation request")
            normalized = load_normalized_run(args.run)
            result = investigate_run(
                request,
                normalized["records"],
                workspace=args.workspace,
                proof_paths=tuple(args.proof),
            )
            write_investigation_result(result, args.output)
            print(render_json(result), end="")
            return 0
        except (PortableInvestigationError, NormalizationError, OSError, ValueError) as error:
            raise SystemExit(f"aet: investigate failed: {error}") from error
    if args.command == "bundle":
        try:
            if args.bundle_command == "create":
                investigation = _load_portable_json(
                    args.investigation,
                    "investigation result",
                )
                payload = _bundle_payload_from_investigation(
                    investigation,
                    bundle_id=args.bundle_id,
                    created_at=args.created_at,
                )
                bundle = compile_bundle(
                    payload,
                    args.output,
                    claim_refs=args.claim_ref,
                )
                print(render_json(bundle["manifest"]), end="")
            elif args.bundle_command == "validate":
                bundle = validate_bundle(args.bundle)
                print(
                    render_json(
                        {
                            "report_kind": "portable_evidence_bundle_validation",
                            "status": "PASS",
                            "bundle_id": bundle["manifest"]["bundle"]["id"],
                        }
                    ),
                    end="",
                )
            elif args.bundle_command == "render":
                bundle = validate_bundle(args.bundle)
                rendered = render_bundle_markdown(bundle)
                if args.output.exists() or args.output.is_symlink():
                    raise BundleError("output_exists", f"render output already exists: {args.output}")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                report = validate_review_result(args.bundle, args.review)
                print(render_json(report), end="")
            return 0
        except (BundleError, OSError, ValueError) as error:
            raise SystemExit(f"aet: bundle {args.bundle_command} failed: {error}") from error
    if args.command == "atlas":
        try:
            if args.atlas_command == "build":
                result = build_evidence_atlas(
                    args.bundle,
                    output=args.output,
                    generation_policy={
                        "max_depth": args.max_depth,
                        "max_nodes_per_diagram": args.max_nodes,
                        "max_children_per_node": args.max_children,
                        "max_total_diagrams": args.max_diagrams,
                        "llm_enabled": False,
                    },
                    perspective_ids=args.perspectives,
                    replace=not args.no_replace,
                )
                report = {
                    "report_kind": "evidence_atlas_build",
                    "status": "PASS",
                    "bundle_id": result["graph"]["bundle_id"],
                    "output": result["output"],
                    "node_count": len(result["graph"]["nodes"]),
                    "edge_count": len(result["graph"]["edges"]),
                    "perspectives": [
                        item["id"] for item in result["perspectives"]
                    ],
                    "incremental": result["incremental"],
                    "llm_enabled": False,
                }
            elif args.atlas_command == "diff":
                before_root, before_bundle = _resolve_atlas_input(
                    args.before,
                    args.before_bundle,
                )
                after_root, after_bundle = _resolve_atlas_input(
                    args.after,
                    args.after_bundle,
                )
                validate_evidence_atlas(before_root / "atlas-manifest.json", before_bundle)
                validate_evidence_atlas(after_root / "atlas-manifest.json", after_bundle)
                report = compare_evidence_atlases(
                    load_evidence_atlas(before_root)["graph"],
                    load_evidence_atlas(after_root)["graph"],
                )
                if args.output is not None:
                    _write_new_bytes(
                        args.output,
                        json.dumps(
                            report,
                            ensure_ascii=False,
                            sort_keys=True,
                            indent=2,
                            allow_nan=False,
                        ).encode("utf-8")
                        + b"\n",
                    )
            else:
                atlas_root, bundle_path = _resolve_atlas_input(
                    args.input,
                    args.bundle,
                )
                validation = validate_evidence_atlas(
                    atlas_root / "atlas-manifest.json",
                    bundle_path,
                )
                loaded = load_evidence_atlas(atlas_root)
                graph = loaded["graph"]
                if args.atlas_command == "validate":
                    report = {
                        "report_kind": "evidence_atlas_validation",
                        "status": "PASS",
                        "schema_version": validation["schema_version"],
                        "bundle_id": graph["bundle_id"],
                        "node_count": len(graph["nodes"]),
                        "edge_count": len(graph["edges"]),
                        "perspective_count": len(graph["perspectives"]),
                    }
                elif args.atlas_command == "query":
                    report = get_node_subgraph(
                        graph,
                        args.root,
                        perspective=args.perspective,
                        depth=args.depth,
                        max_nodes=args.max_nodes,
                        max_bytes=args.max_bytes,
                    )
                elif args.atlas_command == "explain":
                    report = explain_node(graph, args.node)
                elif args.atlas_command == "view":
                    serve_atlas(
                        atlas_root / "atlas",
                        host=args.host,
                        port=args.port,
                        open_browser=not args.no_browser,
                    )
                    return 0
                else:
                    _export_atlas(
                        atlas_root,
                        graph,
                        args.format,
                        args.output,
                    )
                    report = {
                        "report_kind": "evidence_atlas_export",
                        "status": "PASS",
                        "format": args.format,
                        "output": str(args.output),
                    }
            print(render_json(report), end="")
            return 0
        except (
            AtlasQueryError,
            AtlasStorageError,
            AtlasValidationError,
            BundleError,
            OSError,
            ValueError,
        ) as error:
            raise SystemExit(
                f"aet: atlas {args.atlas_command} failed: {error}"
            ) from error
    if args.command == "improvement":
        try:
            print(doctor_bundle(args.bundle), end="")
            return 0
        except (BundleError, OSError, ValueError) as error:
            raise SystemExit(f"aet: improvement doctor failed: {error}") from error
    if args.command == "improve":
        try:
            action = args.arguments[0]
            if action == "prompt":
                if len(args.arguments) != 2:
                    parser.error("aet improve prompt requires one Improvement Issue ID")
                report = generate_agent_prompt(args.arguments[1])
            elif action == "validate":
                if len(args.arguments) != 2:
                    parser.error("aet improve validate requires one candidate JSON path")
                report = validate_candidate_file(Path(args.arguments[1]))
            elif action == "verify":
                if len(args.arguments) != 2:
                    parser.error("aet improve verify requires one Improvement Issue ID")
                report = verify_issue(args.arguments[1])
            elif action == "compare":
                if len(args.arguments) != 1:
                    parser.error("aet improve compare takes no additional arguments")
                report = compare_improvement_metrics()
            else:
                if len(args.arguments) != 1:
                    parser.error("aet improve <bundle> accepts one Bundle path")
                report = generate_improvements(Path(action))
            print(render_json(report), end="")
            return 0 if report.get("valid", True) else 1
        except (BundleError, OSError, ValueError) as error:
            raise SystemExit(f"aet: improve failed: {error}") from error
    if args.command == "plan":
        try:
            if args.plan_command == "context":
                request = _planning_request_from_args(args)
                context = build_planning_context(
                    request,
                    workspace=args.workspace,
                    bundle_path=args.bundle,
                    atlas_path=args.atlas,
                    budgets=request.budgets,
                )
                _write_new_bytes(
                    args.output,
                    planning_json_bytes(context),
                )
                report = {
                    "schema_version": "planning-context-build/1.0",
                    "status": "PASS",
                    "request_id": context.request.request_id,
                    "bundle_identity": context.request.bundle_identity,
                    "atlas_identity": context.request.atlas_identity,
                    "source_site_count": len(context.source_sites),
                    "gap_count": len(context.gaps),
                    "output": str(args.output),
                }
                print(render_json(report), end="")
                return 0
            if args.plan_command == "validate-candidate":
                context = _load_planning_context(args.context)
                candidate = parse_candidate(args.candidate.read_bytes())
                result = validate_plan_candidate(context, candidate)
                output = build_plan_package(context, result, args.output)
                report = {
                    "schema_version": "plan-candidate-validation/1.0",
                    "plan_id": result.plan["plan_id"],
                    "status": result.status,
                    "authority": "PROPOSED",
                    "diagnostic_count": len(result.diagnostics),
                    "output": str(output),
                }
                print(render_json(report), end="")
                return _planning_status_exit(result.status)
            if args.plan_command == "validate":
                print(render_json(validate_plan_package(args.plan)), end="")
                return 0
            if args.plan_command == "show":
                print(show_plan(args.plan), end="")
                return 0
            if args.plan_command == "explain":
                print(render_json(explain_plan_edit(args.plan, args.edit)), end="")
                return 0
            if args.plan_command == "trace":
                print(render_json(trace_plan_path(args.plan, args.path)), end="")
                return 0
            if args.plan_command == "export-skill":
                output = export_plan_skill(
                    args.plan,
                    args.output,
                    target=args.target,
                )
                print(
                    render_json(
                        {
                            "schema_version": "plan-skill-export-result/1.0",
                            "status": "PASS",
                            "target": args.target,
                            "output": str(output),
                        }
                    ),
                    end="",
                )
                return 0
            if args.plan_command == "verification-handoff":
                handoff = build_verification_handoff_from_package(
                    args.plan,
                    args.diff.read_bytes(),
                )
                _write_new_bytes(
                    args.output,
                    planning_json_bytes(handoff),
                )
                print(
                    render_json(
                        {
                            "schema_version": "verification-handoff-result/1.0",
                            "status": handoff["status"],
                            "plan_id": handoff["plan_id"],
                            "handoff_id": handoff["handoff_id"],
                            "verification_status": "UNKNOWN",
                            "output": str(args.output),
                        }
                    ),
                    end="",
                )
                return 0
            print(render_json(list_plan_gaps(args.plan)), end="")
            return 0
        except (PlanningError, OSError, UnicodeError, ValueError) as error:
            print(
                f"aet: plan {args.plan_command} failed: {error}",
                file=sys.stderr,
            )
            return 2
    if args.command == "mcp":
        from .mcp_server import serve_stdio

        serve_stdio()
        return 0
    if args.command == "quick":
        try:
            language = select_language(
                request=args.request,
                slash_command=args.slash_command,
            )
            if args.quick_command == "check":
                if args.max_findings < 1 or args.max_findings > 5:
                    raise ValueError("quick check --max-findings must be between 1 and 5")
                root = Path(args.path).resolve()
                if not root.is_dir():
                    raise ValueError(f"root does not exist or is not a directory: {root}")
                result = quick_check(root, max_findings=args.max_findings)
            elif args.quick_command == "scope":
                root = Path(args.path).resolve()
                if not root.is_dir():
                    raise ValueError(f"root does not exist or is not a directory: {root}")
                result = quick_scope(root, base=args.base, intent_path=args.intent)
            elif args.quick_command == "proof":
                if "--" not in raw_argv:
                    parser.error("quick proof requires -- before the command argv")
                proof_argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
                result, exit_code = quick_proof(
                    proof_argv,
                    args.output,
                    relevant_paths=args.relevant_path,
                    artifact_paths=args.artifact,
                    redaction_patterns=args.redact_pattern,
                    environment_names=args.env_binding,
                )
                print(render_quick_result(result, language), end="")
                return exit_code
            else:
                result = quick_fresh(args.proof)
            rendered = render_json(result) if args.format == "json" else render_quick_result(result, language)
            print(rendered, end="")
            has_failure = result.get("authoritative_status") == "FAIL"
            summary = result.get("summary")
            if isinstance(summary, dict) and summary.get("FAIL", 0) > 0:
                has_failure = True
            return 1 if has_failure else 0
        except (ConfigError, EvidenceError, ReviewError, RulePackError, ValueError) as error:
            raise SystemExit(f"aet: quick {args.quick_command} failed: {error}") from error
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
            operation = reuse_trace_command if args.reuse_if_fresh else trace_command
            trace_data, exit_code = operation(args.argv, args.output, args.redact_pattern, proof, args.artifact)
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
                if validation["status"] != "PASS":
                    bucket = "FAIL" if validation["status"] == "FAIL" else "UNKNOWN"
                    trace_data["summary"][bucket] += 1
                    exit_code = 1
                args.output.write_text(render_json(trace_data), encoding="utf-8")
                seal_trace(args.output)
            if args.reuse_if_fresh:
                print(f"Reused fresh Trace: {args.output.resolve()}")
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
            elif args.evidence_command == "viewer":
                render_evidence_viewer(args.pack, args.output)
            else:
                if args.output and args.output.resolve() == args.report.resolve():
                    raise EvidenceError("receipt output must not replace its source report")
                receipt = evidence_receipt(args.report)
                rendered = render_json(receipt)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(rendered, encoding="utf-8")
                else:
                    print(rendered, end="")
        except EvidenceError as error:
            raise SystemExit(f"aet: evidence pack failed: {error}") from error
        except RunError as error:
            raise SystemExit(f"aet: run failed: {error}") from error
        return 0
    if args.command == "run":
        try:
            if args.run_command == "normalize":
                if args.output.exists() or args.output.is_symlink():
                    raise NormalizationError(
                        f"normalized run output already exists: {args.output}"
                    )
                prior = load_normalized_run(args.prior) if args.prior else None
                result = normalize_run(
                    args.source,
                    args.input,
                    run_group_id=args.run_group_id,
                    base_byte_offset=args.base_byte_offset,
                    partial=args.partial,
                    generation_id=args.generation_id,
                    prior=prior,
                )
                write_normalized_run(result, args.output)
                print(render_json(result["manifest"]), end="")
                return 0
            if args.run_command == "inspect":
                normalized = load_normalized_run(args.run)
                records = normalized["records"]
                if args.tool_calls:
                    records = [
                        record
                        for record in records
                        if record.get("record_type") in {"tool_call", "tool_result"}
                    ]
                rendered = (
                    "".join(
                        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                        for record in records
                    )
                    if args.format == "jsonl"
                    else render_json(
                        {
                            "manifest": normalized["manifest"],
                            "records": records,
                            "diagnostics": normalized["diagnostics"],
                        }
                    )
                )
                if args.output:
                    if args.output.exists():
                        raise NormalizationError(f"inspect output already exists: {args.output}")
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(rendered, encoding="utf-8")
                else:
                    print(rendered, end="")
                return 0
            if args.run_command == "init":
                init_run(args.output, args.intent)
                status = run_status(args.output)
            elif args.run_command == "status":
                status = run_status(args.run)
            elif args.run_command == "verify":
                status = verify_run(args.run)
            else:
                status = close_run(args.run)
        except (RunError, NormalizationError, OSError, ValueError) as error:
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
            if args.learn_command == "plan":
                plan_observed_gate(candidate=args.candidate, core=args.core, validation=args.validation, held_out=args.held_out, runner_name=args.runner, runner_config=_runner_config(args.runner_config), risk_class=args.risk_class, claims=args.claim, output=args.output, min_pairs=args.min_pairs, max_pairs=args.max_pairs, batch_size=args.batch_size)
                return 0
            if args.learn_command == "history":
                assess_gate_history(registry=args.registry, gate_plan=args.gate_plan, suite=args.suite, output=args.output)
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
                    replay_observed(candidate=args.candidate, suite=args.suite, output=args.output, runner_name=args.runner, rollouts=args.rollouts, seed=args.seed, runner_config=config, resume=args.resume)
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
                if args.runner == "static" and args.gate_plan is not None:
                    raise LearnError("--gate-plan is only valid for observed runners")
                result = gate(candidate=args.candidate, validation=args.validation, held_out=args.held_out, core=args.core, output=args.output) if args.runner == "static" else gate_observed(candidate=args.candidate, validation=args.validation, held_out=args.held_out, core=args.core, output=args.output, runner_name=args.runner, rollouts=args.rollouts, statistics_profile=args.statistics_profile, runner_config=config, gate_plan=args.gate_plan)
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
        except (LearnError, GatePlanError, AuditEvolutionError, CandidateError, PolicyTargetError) as error:
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
    if args.command == "audit" and is_repository_case(args.path):
        if args.repo is None:
            raise SystemExit(f"aet: repository showcase case '{args.path}' requires --repo <local-checkout>")
        incompatible = {
            "--output": args.output,
            "--config": args.config,
            "--rulepack": args.rulepack,
            "--shadow-rulepack": args.shadow_rulepack,
            "--shadow-output": args.shadow_output,
            "--profile": args.profile,
            "--run": args.run,
        }
        used = [name for name, value in incompatible.items() if value is not None]
        if used or args.format != "markdown":
            rendered = ", ".join(used + (["--format"] if args.format != "markdown" else []))
            raise SystemExit(f"aet: repository showcase cases do not accept legacy audit options: {rendered}")
        try:
            data = run_repository_audit(args.path, args.repo, args.output_dir or Path("audit-result"))
        except RepositoryAuditError as error:
            raise SystemExit(f"aet: repository showcase audit failed: {error}") from error
        has_failure = data["summary"]["FAIL"] > 0
        has_warning = any(
            finding["severity"] == "WARN" and finding["status"] != "PASS"
            for finding in data["findings"]
        )
        return 1 if has_failure or (args.strict and has_warning) else 0
    if args.command == "audit" and args.repo is not None:
        raise SystemExit("aet: --repo is only valid with swe-agent, google-adk, or openhands")
    if args.command == "audit" and args.output_dir is not None:
        raise SystemExit("aet: --output-dir is only valid with swe-agent, google-adk, or openhands")
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


def _load_portable_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"),
            parse_constant=lambda item: (_raise_portable_nonfinite(item)),
            object_pairs_hook=_portable_unique_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _planning_request_from_args(args: argparse.Namespace) -> PlanningRequest:
    budgets = PlanningBudgets(
        max_nodes=args.max_nodes,
        max_source_files=args.max_source_files,
        max_source_bytes=args.max_source_bytes,
        max_edit_items=args.max_edit_items,
        max_depth=args.max_depth,
    )
    if args.request is not None and args.request.suffix.casefold() == ".json":
        value = strict_json_loads(
            args.request.read_bytes(),
            label="Planning Request",
        )
        if not isinstance(value, dict):
            raise PlanningError(
                "INVALID_REQUEST",
                "Planning Request JSON must contain one object",
            )
        if any(
            (
                args.allowed_path,
                args.protected_path,
                args.verification,
            )
        ):
            raise PlanningError(
                "INVALID_REQUEST",
                "JSON Planning Request cannot be combined with path or verification overrides",
            )
        request = model_from_mapping(PlanningRequest, value)
        return request
    raw_text = (
        args.request_text
        if args.request_text is not None
        else args.request.read_text(encoding="utf-8")
    )
    return normalize_request(
        raw_text,
        workspace=args.workspace,
        explicit=RequestOverrides(
            allowed_paths=list(args.allowed_path),
            protected_paths=list(args.protected_path),
            required_verification=list(args.verification),
            budgets=budgets,
        ),
    )


def _load_planning_context(path: Path) -> PlanningContext:
    value = strict_json_loads(path.read_bytes(), label="Planning Context")
    if not isinstance(value, dict):
        raise PlanningError(
            "INVALID_REQUEST",
            "Planning Context must contain one object",
        )
    try:
        return model_from_mapping(PlanningContext, value)
    except (KeyError, TypeError, ValueError) as error:
        raise PlanningError(
            "INVALID_REQUEST",
            "Planning Context shape is invalid",
        ) from error


def _planning_status_exit(status: str) -> int:
    return {
        "READY_FOR_HUMAN_REVIEW": 0,
        "NEEDS_EVIDENCE": 3,
        "PARTIAL": 4,
        "BLOCKED": 5,
        "SUPERSEDED": 5,
    }.get(status, 6)


def _portable_unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"portable JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _raise_portable_nonfinite(value: str) -> object:
    raise ValueError(f"portable JSON contains non-finite number: {value}")


def _bundle_payload_from_investigation(
    investigation: dict[str, object],
    *,
    bundle_id: str | None,
    created_at: str | None,
) -> dict[str, object]:
    if all(
        field in investigation
        for field in (
            "task",
            "investigation",
            "claims",
            "evidence",
            "observations",
            "sources",
            "diagnostics",
            "conflicts",
            "ledger",
            "policy",
        )
    ):
        payload = dict(investigation)
        payload.setdefault("bundle_id", bundle_id)
        payload.setdefault("created_at", created_at)
        payload.setdefault("producer_version", __version__)
        return payload
    if investigation.get("schema_version") != "portable-investigation-result/1.0":
        raise BundleError(
            "invalid_bundle",
            "investigation must be a portable result or a complete Bundle compilation payload",
        )
    selected_bundle_id = bundle_id or (
        "bundle-"
        + hashlib.sha256(
            str(investigation["investigation_id"]).encode("utf-8")
        ).hexdigest()[:16]
    )
    selected_created_at = created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    observations = investigation.get("observations")
    if not isinstance(observations, list) or any(not isinstance(item, dict) for item in observations):
        raise BundleError("invalid_bundle", "investigation observations must be objects")
    portable_observations = [
        {
            field: item[field]
            for field in (
                "id",
                "type",
                "statement",
                "source_refs",
                "proves",
                "does_not_prove",
                "limitations",
            )
        }
        for item in observations
    ]
    source_refs = list(
        dict.fromkeys(
            [
                *(
                    reference
                    for item in portable_observations
                    for reference in item["source_refs"]
                ),
                *investigation["disconfirming_search"]["searched_record_refs"],
            ]
        )
    )
    record_sources = investigation.get("record_sources")
    if not isinstance(record_sources, list) or any(
        not isinstance(item, dict) for item in record_sources
    ):
        raise BundleError(
            "invalid_bundle",
            "investigation record_sources must contain objects",
        )
    source_binding_by_id = {item.get("id"): item for item in record_sources}
    if set(source_binding_by_id) != set(source_refs) or None in source_binding_by_id:
        raise BundleError(
            "reference_error",
            "investigation record_sources do not bind every exported Run Record",
        )
    sources = [
        {
            "id": reference,
            "type": "run_record",
            "locator": {
                "record_id": reference,
                "run_group_id": source_binding_by_id[reference]["run_group_id"],
                "identity_kind": source_binding_by_id[reference]["identity_kind"],
            },
            "provenance": {
                "source_type": source_binding_by_id[reference]["source_type"],
                "schema_version": source_binding_by_id[reference]["schema_version"],
            },
            "integrity": {
                "content_hash": source_binding_by_id[reference]["content_hash"],
            },
        }
        for reference in source_refs
    ]
    verification_sources = investigation.get("verification_sources")
    verified_evidence = investigation.get("verified_evidence")
    if not isinstance(verification_sources, list) or any(
        not isinstance(item, dict) for item in verification_sources
    ):
        raise BundleError(
            "invalid_bundle",
            "investigation verification_sources must contain objects",
        )
    if not isinstance(verified_evidence, list) or any(
        not isinstance(item, dict) for item in verified_evidence
    ):
        raise BundleError(
            "invalid_bundle",
            "investigation verified_evidence must contain objects",
        )
    sources.extend(json.loads(json.dumps(verification_sources)))
    policy = json.loads(json.dumps(investigation["policy"]))
    raw_ledger = investigation.get("ledger")
    if not isinstance(raw_ledger, list) or any(
        not isinstance(item, dict) for item in raw_ledger
    ):
        raise BundleError("invalid_bundle", "investigation ledger must contain objects")
    portable_ledger: list[dict[str, object]] = []
    for entry in raw_ledger:
        portable_entry: dict[str, object] = {
            "id": entry["id"],
            "timestamp": selected_created_at,
            "question": entry["question"],
            "hypothesis_ref": entry["hypothesis_ref"],
            "action": entry["action"],
            "observation_refs": list(entry["observation_refs"]),
            "evidence_candidate_refs": list(entry["evidence_candidate_refs"]),
            "effect": entry["effect"],
            "explanation": entry["explanation"],
        }
        if entry.get("tool_name"):
            portable_entry["tool_name"] = entry["tool_name"]
        if entry["action"] in {
            "read_run_record",
            "inspect_proof",
            "check_freshness",
        }:
            input_refs = entry.get("input_refs")
            if not isinstance(input_refs, list) or len(input_refs) != 1:
                raise BundleError(
                    "invalid_bundle",
                    f"{entry['action']} ledger entry requires exactly one input reference",
                )
            portable_entry["input_ref"] = input_refs[0]
        if entry["action"] in {
            "record_observation",
            "inspect_proof",
            "check_freshness",
        } and entry.get("output_ref"):
            portable_entry["output_ref"] = entry["output_ref"]
        portable_ledger.append(portable_entry)
    finding = investigation["findings"][0]
    claim_id = finding["id"]
    unresolved = list(investigation["unresolved"])
    task = dict(investigation["task"])
    return {
        "bundle_id": selected_bundle_id,
        "created_at": selected_created_at,
        "producer_version": __version__,
        "task": task,
        "investigation": {
            "investigation_id": investigation["investigation_id"],
            "investigation_type": "general",
            "question": investigation["question"],
            "scope": list(investigation["requested_evidence"]),
            "limitations": unresolved,
            "completed": True,
        },
        "claims": [
            {
                "id": claim_id,
                "statement": finding["statement"],
                "status": finding["status"],
                "status_definition": (
                    "The status is derived from explicit deterministic Evidence and its Freshness."
                    if verified_evidence
                    else "The investigation produced no matching verified evidence."
                ),
                "evidence_refs": [
                    item["id"]
                    for item in verified_evidence
                    if item.get("supports")
                ],
                "counter_evidence_refs": [
                    item["id"]
                    for item in verified_evidence
                    if item.get("contradicts")
                ],
                "observation_refs": [item["id"] for item in portable_observations],
                "basis": {
                    "type": (
                        "reproduced"
                        if verified_evidence
                        and all(item.get("strength") == "reproduced" for item in verified_evidence)
                        else "observational"
                    ),
                    "explanation": (
                        "The conclusion uses policy-authorized deterministic Proof and Freshness records."
                        if verified_evidence
                        else "Only normalized Run Record observations are available."
                    ),
                },
                "limitations": unresolved,
                **(
                    {"smallest_next_action": "Run an authorized deterministic verification."}
                    if not verified_evidence
                    else {}
                ),
            }
        ],
        "evidence": json.loads(json.dumps(verified_evidence)),
        "observations": portable_observations,
        "sources": sources,
        "diagnostics": [],
        "conflicts": [],
        "ledger": portable_ledger,
        "policy": policy,
        "blobs": {},
        "excluded_reason": "Only records relevant to the declared investigation question were included.",
    }


def _repository_fingerprint(root: Path) -> str:
    git_config = root / ".git" / "config"
    if not git_config.is_file():
        return "UNKNOWN"
    return hashlib.sha256(git_config.read_bytes()).hexdigest()


def _resolve_atlas_input(
    value: Path,
    explicit_bundle: Path | None,
) -> tuple[Path, Path]:
    candidate = Path(value).expanduser().resolve(strict=True)
    if candidate.is_file() and candidate.name == "atlas-manifest.json":
        atlas_root = candidate.parent
    elif candidate.is_dir() and (candidate / "atlas-manifest.json").is_file():
        atlas_root = candidate
    elif candidate.is_dir() and (candidate / "manifest.json").is_file():
        atlas_root = default_atlas_path(candidate)
        explicit_bundle = explicit_bundle or candidate
    else:
        raise ValueError(
            "input must be a Bundle, an Atlas sidecar, or atlas-manifest.json"
        )
    if explicit_bundle is not None:
        bundle = Path(explicit_bundle).expanduser().resolve(strict=True)
    elif atlas_root.name.endswith(".atlas"):
        inferred = atlas_root.with_name(atlas_root.name.removesuffix(".atlas"))
        if not inferred.is_dir():
            raise ValueError(
                "cannot infer the source Bundle; supply --bundle explicitly"
            )
        bundle = inferred.resolve(strict=True)
    else:
        raise ValueError(
            "cannot infer the source Bundle; supply --bundle explicitly"
        )
    return atlas_root.resolve(strict=True), bundle


def _export_atlas(
    atlas_root: Path,
    graph: dict[str, object],
    export_format: str,
    output: Path,
) -> None:
    destination = Path(output).expanduser().resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "static-html":
        shutil.copytree(atlas_root / "atlas", destination)
        return
    data_path = atlas_root / "atlas" / "assets" / "atlas-data.js"
    wrapper = data_path.read_text(encoding="utf-8")
    prefix = "globalThis.__AET_ATLAS_DATA__="
    if not wrapper.startswith(prefix) or not wrapper.rstrip().endswith(";"):
        raise ValueError("Atlas Viewer data asset is malformed")
    payload = json.loads(wrapper[len(prefix) :].rstrip()[:-1])
    if not isinstance(payload, dict) or payload.get("graph") != graph:
        raise ValueError("Atlas Viewer data does not match the validated graph")
    projections = payload.get("projections")
    if not isinstance(projections, dict):
        raise ValueError("Atlas Viewer data is missing recursive projections")
    _write_new_bytes(destination, single_html(graph, projections))


def _write_new_bytes(path: Path, content: bytes) -> None:
    destination = Path(path).expanduser().resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)


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
