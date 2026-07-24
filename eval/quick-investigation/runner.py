#!/usr/bin/env python3
"""Run the bounded AET Quick investigation comparison.

This is an AET Lab harness. It intentionally does not add a Quick CLI command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from aet.investigation import InvestigationLedger, validate_investigated_finding
from aet.investigation.grounding import GroundingError


GROUPS = (
    "pure_rules",
    "one_shot_llm",
    "investigated_aet",
    "investigated_grounded",
)

CATEGORIES = (
    "explicit_scope_violation",
    "justified_shared_module_change",
    "ambiguous_intent",
    "later_authorization",
    "unrelated_dependency",
    "interface_migration",
    "unsupported_counter_hypothesis",
    "budget_exhausted",
)

CLAIM_CATALOG = (
    "scope_expansion",
    "insufficient_intent",
    "unrelated_dependency",
    "bounded_result",
)

EMPTY_USAGE = {
    "status": "UNKNOWN",
    "input_tokens": 0,
    "output_tokens": 0,
    "reasoning_tokens": 0,
    "total_tokens": 0,
}

ZERO_EVIDENCED_USAGE = {
    "status": "EVIDENCED",
    "input_tokens": 0,
    "output_tokens": 0,
    "reasoning_tokens": 0,
    "total_tokens": 0,
}


def _reject_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def load_suite(path: Path) -> dict[str, Any]:
    suite = read_json(path)
    if suite.get("schema_version") != "quick-investigation-suite/v1":
        raise ValueError("unsupported suite schema")
    if suite.get("groups") != list(GROUPS):
        raise ValueError("suite groups must be the four fixed comparison groups in order")
    if suite.get("claim_catalog") != list(CLAIM_CATALOG):
        raise ValueError("suite claim catalog must use the fixed comparable claim IDs")
    scenarios = suite.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 8:
        raise ValueError("suite must contain exactly eight scope scenarios")
    ids = [item.get("scenario_id") for item in scenarios if isinstance(item, dict)]
    categories = [item.get("category") for item in scenarios if isinstance(item, dict)]
    if len(ids) != 8 or len(set(ids)) != 8:
        raise ValueError("scenario IDs must be eight unique values")
    if tuple(categories) != CATEGORIES:
        raise ValueError("suite must cover the eight required scope categories in order")
    for scenario in scenarios:
        evidence = scenario.get("evidence")
        findings = scenario.get("rule_findings")
        expected = scenario.get("expected_claim_ids")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"{scenario.get('scenario_id')} requires evidence")
        if not isinstance(findings, list) or not isinstance(expected, list):
            raise ValueError(f"{scenario.get('scenario_id')} has an invalid result contract")
        evidence_ids = [item.get("id") for item in evidence if isinstance(item, dict)]
        if len(evidence_ids) != len(evidence) or len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError(f"{scenario.get('scenario_id')} evidence IDs must be unique")
        if len(expected) != len(set(expected)) or not all(isinstance(item, str) and item for item in expected):
            raise ValueError(f"{scenario.get('scenario_id')} expected claim IDs must be unique strings")
    return suite


def parse_model_parameter(value: str) -> tuple[str, Any]:
    key, separator, raw = value.partition("=")
    if not separator or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", key) is None:
        raise argparse.ArgumentTypeError("model parameters must use safe KEY=JSON syntax")
    try:
        parsed = json.loads(raw, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON model parameter {key}: {exc}") from exc
    return key, parsed


def parse_codex_jsonl(text: str) -> dict[str, Any]:
    final_text = ""
    usage = dict(EMPTY_USAGE)
    completed_tool_ids: set[str] = set()
    anonymous_tool_calls = 0
    valid_events = 0
    for line in text.splitlines():
        try:
            event = json.loads(line, parse_constant=_reject_constant)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        valid_events += 1
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        item_type = item.get("type")
        if event.get("type") == "item.completed" and item_type in {
            "command_execution",
            "mcp_tool_call",
            "tool_call",
        }:
            identifier = item.get("id")
            if isinstance(identifier, str) and identifier:
                completed_tool_ids.add(identifier)
            else:
                anonymous_tool_calls += 1
        if event.get("type") == "item.completed" and item_type == "agent_message":
            final_text = str(item.get("text", final_text))
        event_usage = event.get("usage")
        if event.get("type") == "turn.completed" and isinstance(event_usage, dict):
            input_tokens = _non_negative_int(event_usage.get("input_tokens"))
            output_tokens = _non_negative_int(event_usage.get("output_tokens"))
            reasoning_tokens = _non_negative_int(
                event_usage.get("reasoning_output_tokens", event_usage.get("reasoning_tokens"))
            )
            usage = {
                "status": "EVIDENCED",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
    return {
        "final_text": final_text,
        "usage": usage,
        "tool_calls": len(completed_tool_ids) + anonymous_tool_calls,
        "valid_events": valid_events,
    }


def _non_negative_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def parse_output(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1])
            if candidate.lstrip().startswith("json"):
                candidate = candidate.lstrip()[4:].lstrip()
    try:
        value = json.loads(candidate, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError):
        return {"schema_version": "quick-investigation-output/v1", "status": "UNKNOWN", "claims": []}
    if not isinstance(value, dict) or value.get("schema_version") != "quick-investigation-output/v1":
        return {"schema_version": "quick-investigation-output/v1", "status": "UNKNOWN", "claims": []}
    claims = value.get("claims")
    if value.get("status") not in {"COMPLETE", "UNKNOWN"} or not isinstance(claims, list):
        return {"schema_version": "quick-investigation-output/v1", "status": "UNKNOWN", "claims": []}
    normalized: list[dict[str, Any]] = []
    for claim in claims:
        required = {"claim_id", "assessment_state", "evidence_refs"}
        optional = {"counter_explanation", "counter_evidence_refs", "remaining_uncertainty"}
        if not isinstance(claim, dict) or not required.issubset(claim) or set(claim) - required - optional:
            return {"schema_version": "quick-investigation-output/v1", "status": "UNKNOWN", "claims": []}
        if not all(isinstance(claim.get(key), str) and claim[key] for key in ("claim_id", "assessment_state")):
            return {"schema_version": "quick-investigation-output/v1", "status": "UNKNOWN", "claims": []}
        refs = claim.get("evidence_refs")
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref for ref in refs):
            return {"schema_version": "quick-investigation-output/v1", "status": "UNKNOWN", "claims": []}
        normalized_claim = {
            "claim_id": claim["claim_id"],
            "assessment_state": claim["assessment_state"],
            "evidence_refs": list(dict.fromkeys(refs)),
        }
        for field in optional:
            if field in claim:
                normalized_claim[field] = claim[field]
        normalized.append(normalized_claim)
    return {
        "schema_version": "quick-investigation-output/v1",
        "status": value["status"],
        "claims": normalized,
    }


def prompt_for(group: str, scenario: dict[str, Any]) -> str:
    output_contract = (
        'Return only JSON: {"schema_version":"quick-investigation-output/v1",'
        '"status":"COMPLETE","claims":[{"claim_id":"stable_id",'
        '"assessment_state":"STATE","evidence_refs":["evidence_id"]}]}. '
        "Use an empty claims array when no problem exists. Never invent evidence IDs. "
        f"claim_id must be one of: {', '.join(CLAIM_CATALOG)}."
    )
    facts = json.dumps(
        {"task": scenario["task"], "evidence": scenario["evidence"]},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if group == "one_shot_llm":
        method = (
            "Make one scope judgment from the supplied task and evidence. "
            "Do not call tools and do not perform a separate counter-hypothesis investigation."
        )
    elif group == "investigated_aet":
        method = (
            "Act as the bounded AET investigator. Inspect scenario.json with local read-only tools when useful, "
            "compare a primary and reasonable counter-hypothesis, and stop when further evidence would not change the action."
        )
    elif group == "investigated_grounded":
        method = (
            "Act as the grounding-aware bounded AET investigator. Inspect scenario.json with local read-only tools "
            "when useful, compare a primary and reasonable counter-hypothesis, and emit a claim only when every factual "
            "basis names an evidence ID present in scenario.json. Preserve uncertainty and bounded results."
        )
        output_contract += (
            " Every claim must also include counter_explanation as a non-empty string, "
            "counter_evidence_refs as evidence IDs used to test it, and remaining_uncertainty as an array."
        )
    else:
        raise ValueError(f"LLM prompt is not defined for {group}")
    return f"{method}\n\nScenario:\n{facts}\n\n{output_contract}"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _pure_rules_output(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "quick-investigation-output/v1",
        "status": "COMPLETE",
        "claims": scenario["rule_findings"],
    }


def apply_grounding(
    output: dict[str, Any],
    scenario: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate claims against a fixture-synthesized Ledger.

    Plan §15 LLM 对照评测：场景事实全部预先提供；本组验证结构化 Claim
    约束，不声称复现真实仓库的端到端取证。
    """
    evidence = {
        item["id"]: item
        for item in scenario["evidence"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    steps = []
    for index, (identifier, item) in enumerate(evidence.items(), start=1):
        result = dict(item)
        digest = hashlib.sha256(
            json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        steps.append({
            "step_id": f"step_{index:02d}",
            "question": "Does this recorded fixture fact distinguish the scope hypotheses?",
            "tool": "fixture.evidence",
            "evidence_class": (
                "explicit_user"
                if item.get("kind") == "user_intent"
                else "explicit_project"
            ),
            "input": {"evidence_id": identifier},
            "result": result,
            "result_ref": f"evidence://fixture/{identifier}",
            "result_sha256": digest,
            "observation": {"summary": str(item.get("statement", identifier))},
            "hypothesis_effect": {"supports": ["H1"], "weakens": ["H2"]},
            "decision_value": "high",
            "cost": "low",
        })
    ledger = InvestigationLedger({
        "schema_version": "aet-investigation-ledger/v1",
        "investigation_id": f"benchmark_{scenario['scenario_id']}",
        "command": "aet-scope",
        "hypotheses": [
            {"id": "H1", "statement": "The emitted claim is supported.", "state": "SUPPORTED"},
            {"id": "H2", "statement": "A reasonable counter explanation defeats it.", "state": "WEAKENED"},
        ],
        "completed_investigations": [
            "recover_intent",
            "inspect_changed_surface",
            "evaluate_counter_hypothesis",
        ],
        "material_conflicting_evidence_refs": [],
        "budget": {
            "wall_time_seconds": 45,
            "llm_calls": 2,
            "tool_calls": 8,
            "remote_calls": 2,
            "expensive_calls": 1,
            "findings": 5,
        },
        "usage": {
            "wall_time_seconds": 0,
            "llm_calls": 1,
            "tool_calls": len(steps),
            "remote_calls": 0,
            "expensive_calls": 0,
            "findings": len(output.get("claims", [])),
        },
        "steps": steps,
        "stop": {"reason": "DOMINANT_EXPLANATION", "bounded_result": False},
    })
    accepted = []
    rejected = []
    for claim in output.get("claims", []):
        refs = claim.get("evidence_refs", [])
        counter_refs = claim.get("counter_evidence_refs", [])
        uncertainty = claim.get("remaining_uncertainty", [])
        finding_type = claim.get("claim_id")
        finding = {
            "finding_type": finding_type,
            "origin": "INVESTIGATED_FINDING",
            "authoritative_status": "UNKNOWN",
            "assessment_state": "SUPPORTED",
            "blocking": False,
            "engineering_judgment": f"The benchmark model emitted {finding_type}.",
            "evidence_refs": [f"evidence://fixture/{ref}" for ref in refs],
            "counter_explanation": {
                "statement": claim.get("counter_explanation", ""),
                "investigation_result": "WEAKENED",
                "evidence_refs": [
                    f"evidence://fixture/{ref}" for ref in counter_refs
                ],
            },
            "confirmed_facts": [
                {
                    "kind": "tool_fact",
                    "statement": str(evidence.get(ref, {}).get("statement", ref)),
                    "evidence_refs": [f"evidence://fixture/{ref}"],
                }
                for ref in refs
            ],
            "remaining_uncertainty": uncertainty,
            "locations": [],
            "recommended_action": "Review the bounded scope disposition.",
        }
        contract = {
            "schema_version": "aet-investigation-contract/v1",
            "finding_type": finding_type,
            "required_investigation": [
                "recover_intent",
                "inspect_changed_surface",
                "evaluate_counter_hypothesis",
            ],
            "factual_grounding": {
                "tool_claims_require_result_ref": True,
                "user_constraints_require_source_ref": True,
                "negative_claims_require_search_scope": True,
            },
            "semantic_judgment": {
                "must_distinguish_fact_and_inference": True,
                "must_present_counter_explanation": True,
                "must_disclose_unresolved_assumptions": True,
            },
            "prohibited": [
                "llm_similarity_as_sole_evidence",
                "unexecuted_test_as_passed",
                "unread_file_citation",
                "hidden_conflicting_evidence",
                "unsupported_authorization_inference",
                "invented_tool_result",
            ],
            "stop_conditions": [
                "dominant_explanation_established",
                "remaining_uncertainty_does_not_change_action",
                "evidence_value_exhausted",
                "investigation_budget_exhausted",
                "user_authority_required",
                "user_information_required",
                "tool_unavailable",
            ],
        }
        try:
            validate_investigated_finding(
                finding,
                ledger,
                allowed_tools={"fixture.evidence"},
                investigation_contract=contract,
            )
            accepted.append(claim)
        except (GroundingError, ValueError) as error:
            rejected.append({"claim_id": finding_type, "reason": str(error)})
    grounded = dict(output)
    grounded["claims"] = accepted
    return grounded, {
        "status": "PASS" if not rejected else "REJECTED",
        "accepted_claims": len(accepted),
        "rejected_claims": rejected,
    }


def _codex_argv(
    codex_binary: str,
    model: str,
    parameters: dict[str, Any],
    workspace: Path,
    final_path: Path,
) -> list[str]:
    argv = [
        codex_binary,
        "exec",
        "--json",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--model",
        model,
    ]
    for key, value in sorted(parameters.items()):
        argv.extend(["-c", f"{key}={json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"])
    argv.extend(["-C", str(workspace), "--output-last-message", str(final_path), "-"])
    return argv


def run_one(
    suite: dict[str, Any],
    scenario: dict[str, Any],
    group: str,
    repetition: int,
    output_root: Path,
    model: str | None,
    model_parameters: dict[str, Any],
    codex_binary: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    run_id = f"{group}-{scenario['scenario_id']}-{repetition:03d}"
    run_dir = output_root / group / scenario["scenario_id"] / f"{repetition:03d}"
    if run_dir.exists():
        raise ValueError(f"run output already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    raw_path = run_dir / "codex.jsonl"
    if group == "pure_rules":
        started = time.monotonic()
        output = _pure_rules_output(scenario)
        elapsed = time.monotonic() - started
        runner = "deterministic"
        raw_reference = None
        usage = dict(ZERO_EVIDENCED_USAGE)
        tool_calls = 0
        grounding = {"status": "NOT_APPLICABLE", "accepted_claims": 0, "rejected_claims": []}
    else:
        if not model:
            raise ValueError("a model is required for LLM comparison groups")
        workspace = run_dir / "workspace"
        workspace.mkdir()
        _atomic_json(workspace / "scenario.json", scenario)
        final_path = run_dir / "final-response.txt"
        prompt = prompt_for(group, scenario)
        argv = _codex_argv(codex_binary, model, model_parameters, workspace, final_path)
        started = time.monotonic()
        try:
            process = subprocess.run(
                argv,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            stdout = process.stdout
            stderr = process.stderr
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        elapsed = time.monotonic() - started
        raw_path.write_text(stdout, encoding="utf-8")
        (run_dir / "codex.stderr.txt").write_text(stderr, encoding="utf-8")
        parsed = parse_codex_jsonl(stdout)
        final_text = (
            final_path.read_text(encoding="utf-8")
            if final_path.is_file()
            else parsed["final_text"]
        )
        output = parse_output(final_text)
        grounding = {"status": "NOT_APPLICABLE", "accepted_claims": 0, "rejected_claims": []}
        if group == "investigated_grounded":
            output, grounding = apply_grounding(output, scenario)
        runner = "codex"
        raw_reference = raw_path.relative_to(output_root).as_posix()
        usage = parsed["usage"]
        tool_calls = parsed["tool_calls"]
    record = {
        "schema_version": "quick-investigation-run/v1",
        "run_id": run_id,
        "suite_id": suite["suite_id"],
        "scenario_id": scenario["scenario_id"],
        "group": group,
        "repetition": repetition,
        "runner": runner,
        "model": model if runner == "codex" else None,
        "model_parameters": model_parameters if runner == "codex" else {},
        "usage": usage,
        "wall_time_seconds": elapsed,
        "tool_calls": tool_calls,
        "output": output,
        "grounding": grounding,
        "raw_jsonl": raw_reference,
    }
    _atomic_json(run_dir / "run.json", record)
    return record


def run_benchmark(
    suite_path: Path,
    output_root: Path,
    groups: tuple[str, ...],
    repetitions: int,
    model: str | None,
    model_parameters: dict[str, Any],
    codex_binary: str = "codex",
    timeout_seconds: float = 120.0,
) -> list[dict[str, Any]]:
    if repetitions < 1:
        raise ValueError("repetitions must be at least one")
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    if len(set(groups)) != len(groups) or any(group not in GROUPS for group in groups):
        raise ValueError("groups must be unique fixed comparison groups")
    suite = load_suite(suite_path)
    runs: list[dict[str, Any]] = []
    for group in groups:
        for scenario in suite["scenarios"]:
            for repetition in range(repetitions):
                runs.append(
                    run_one(
                        suite,
                        scenario,
                        group,
                        repetition,
                        output_root,
                        model,
                        model_parameters,
                        codex_binary,
                        timeout_seconds,
                    )
                )
    return runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path(__file__).parent / "fixtures" / "scope-scenarios.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--group", action="append", choices=(*GROUPS, "all"), default=[])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--model")
    parser.add_argument("--model-param", action="append", type=parse_model_parameter, default=[])
    parser.add_argument("--codex-binary", default="codex")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()
    requested = args.group or ["all"]
    groups = GROUPS if "all" in requested else tuple(requested)
    parameters = dict(args.model_param)
    try:
        runs = run_benchmark(
            args.suite,
            args.output,
            groups,
            args.repetitions,
            args.model,
            parameters,
            args.codex_binary,
            args.timeout_seconds,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"quick investigation benchmark failed: {exc}") from exc
    print(json.dumps({"output": str(args.output), "run_count": len(runs)}, sort_keys=True))


if __name__ == "__main__":
    main()
