from __future__ import annotations

import json
from pathlib import Path

import pytest

from aet.gate_plan import GatePlanError, assess_history_for_plan, build_gate_plan, load_gate_plan, plan_fixed_pairs, plan_sha256, registry_sha256
from aet.cli import build_parser


def bindings() -> dict:
    return {
        "candidate": {"candidate_id": "C1", "baseline_sha256": "b" * 64, "candidate_sha256": "c" * 64},
        "runner": {"name": "codex", "version": "codex-cli 1.2.0", "config_sha256": "d" * 64, "model_fingerprint": "model-1", "network_isolation": "PARTIAL", "evidence_schema": "1.11.0"},
        "suite_bindings": {
            "core": {"task_count": 2, "task_ids": ["c1", "c2"], "suite_sha256": ["1" * 64]},
            "validation": {"task_count": 3, "task_ids": ["v1", "v2", "v3"], "suite_sha256": ["2" * 64]},
            "held_out": {"task_count": 2, "task_ids": ["h1", "h2"], "suite_sha256": ["3" * 64]},
        },
        "scorer_sha256": "e" * 64,
    }


def test_docs_change_does_not_allocate_real_host_budget() -> None:
    plan = build_gate_plan(
        risk_class="R0",
        claims=["DOCS.ONLY"],
        suites={"core": 1, "validation": 1, "held_out": 1},
    )
    assert plan["applicability"] == "NOT_APPLICABLE"
    assert plan["decision"]["max_pairs"] == 0


def test_cli_accepts_a_zero_host_gate_plan() -> None:
    args = build_parser().parse_args([
        "learn", "plan", "--candidate", "candidate", "--validation", "validation",
        "--held-out", "held-out", "--runner", "scripted", "--risk-class", "R0",
        "--claim", "DOCS.ONLY", "--output", "plan.json",
    ])
    assert args.risk_class == "R0"


def test_standard_plan_uses_distinct_suite_objectives_and_soft_bounds() -> None:
    plan = build_gate_plan(
        risk_class="R3",
        claims=["TRACE.ROUTING.EXACT-COMMAND"],
        suites={"core": 2, "validation": 3, "held_out": 2},
        **bindings(),
    )
    assert plan["suite_objectives"] == {
        "core": "no_regression",
        "validation": "superiority",
        "held_out": "confirmatory_superiority",
    }
    assert 1 <= plan["decision"]["min_pairs"] <= plan["decision"]["max_pairs"]
    assert plan["decision"]["method"] == "group_sequential_bonferroni"
    assert plan["decision"]["power_analysis"]["status"] == "PLANNED"
    assert plan["decision"]["power_analysis"]["power"] >= 1 - plan["decision"]["beta"]
    assert plan["coverage"]["unique_tasks"] == 7


def test_plan_hash_ignores_no_fields_and_detects_mutation() -> None:
    bound = bindings()
    bound["suite_bindings"] = {name: bound["suite_bindings"][name] for name in ("validation", "held_out")}
    plan = build_gate_plan(risk_class="R3", claims=["A"], suites={"validation": 3, "held_out": 2}, **bound)
    original = plan_sha256(plan)
    plan["decision"]["max_pairs"] += 1
    assert plan_sha256(plan) != original


def test_load_plan_rejects_invalid_stopping_bounds(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"schema_version": "gate-plan/v2", "applicability": "REQUIRED", "risk_class": "R3", "claims": ["A"], "suite_objectives": {"validation": "superiority", "held_out": "confirmatory_superiority"}, "suite_designs": {"validation": {"min_pairs": 8, "max_pairs": 4, "batch_size": 2}, "held_out": {"min_pairs": 8, "max_pairs": 4, "batch_size": 2}}, "decision": {"method": "group_sequential_bonferroni", "alpha": 0.05, "beta": 0.2, "mcid": 0.05, "min_pairs": 8, "max_pairs": 4, "batch_size": 2}, "coverage": {"minimum_unique_tasks": 1}, "history": {"mode": "planning_only"}}), encoding="utf-8")
    with pytest.raises(GatePlanError, match="invalid bounds"):
        load_gate_plan(path)


def test_required_plan_rejects_missing_execution_bindings() -> None:
    with pytest.raises(GatePlanError, match="candidate binding"):
        build_gate_plan(risk_class="R3", claims=["A"], suites={"validation": 1, "held_out": 1})


def history_entry(plan: dict, *, version: str = "codex-cli 1.2.0", source_sha: str = "a" * 64) -> dict:
    suite_binding = plan["suite_bindings"]["validation"]
    identity = {
        "claim_ids": plan["claims"], "suite": "validation",
        "suite_binding_sha256": __import__("hashlib").sha256(json.dumps(suite_binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "scorer_sha256": plan["scorer_sha256"], "baseline_sha256": plan["candidate"]["baseline_sha256"],
        "candidate_sha256": plan["candidate"]["candidate_sha256"], "runner_name": plan["runner"]["name"],
        "runner_version": version, "runner_config_sha256": plan["runner"]["config_sha256"],
        "model_fingerprint": "model-1", "network_isolation": "PARTIAL", "evidence_schema": "1.11.0",
        "stopping_plan_sha256": plan_sha256(plan),
    }
    body = {
        "source": {"release_tag": "v1.11.0", "commit": "1" * 40, "gate_manifest_sha256": source_sha, "raw_gate_sha256": "b" * 64, "verification_sha256": "c" * 64, "status": "PASS", "verified": True},
        "identity": identity,
        "sampling": {"planned_pairs": 8, "usable_pairs": 8, "infrastructure_pairs": 0, "stopping_rule": "group_sequential_bonferroni"},
        "discordance": {"better": 8, "worse": 0, "concordant_pass": 0, "concordant_fail": 0},
    }
    body["entry_id"] = __import__("hashlib").sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return body


def test_history_is_planning_only_and_exact_version_drift_disables_borrowing() -> None:
    bound = bindings()
    bound["suite_bindings"] = {name: bound["suite_bindings"][name] for name in ("validation", "held_out")}
    plan = build_gate_plan(risk_class="R3", claims=["A"], suites={"validation": 3, "held_out": 2}, **bound)
    compatible = history_entry(plan)
    drifted = history_entry(plan, version="codex-cli 2.0.0", source_sha="d" * 64)
    registry = {"schema_version": "gate-history-registry/v1", "entries": [compatible, drifted]}
    registry["registry_id"] = registry_sha256(registry)
    report = assess_history_for_plan(registry, plan=plan, suite="validation")
    assert report["mode"] == "planning_only"
    assert report["eligible_records"] == 1
    assert report["rejected_records"] == 1
    assert report["effective_pairs"] == 2
    assert report["final_decision_uses_fresh_pairs_only"] is True
    assert report["sensitivity"]["planned_max_pairs_without_history"] == report["sensitivity"]["planned_max_pairs_with_history"]


def test_history_rejects_duplicate_verified_source() -> None:
    bound = bindings()
    bound["suite_bindings"] = {name: bound["suite_bindings"][name] for name in ("validation", "held_out")}
    plan = build_gate_plan(risk_class="R3", claims=["A"], suites={"validation": 3, "held_out": 2}, **bound)
    entry = history_entry(plan)
    registry = {"schema_version": "gate-history-registry/v1", "entries": [entry, entry]}
    with pytest.raises(GatePlanError, match="duplicate"):
        registry_sha256(registry)


def test_exact_fixed_pair_planner_meets_power_and_previous_n_does_not() -> None:
    planned = plan_fixed_pairs(alpha=0.05, beta=0.20, mcid=0.05, p_better=0.90, p_worse=0.05, max_pairs=50)
    assert planned["status"] == "PLANNED"
    assert planned["power"] >= 0.80
    assert planned["previous_power"] < 0.80
    assert planned["pairs"] > 0


def test_fixed_pair_planner_refuses_unplannable_alternative() -> None:
    planned = plan_fixed_pairs(alpha=0.05, beta=0.20, mcid=0.05, p_better=0.05, p_worse=0.05, max_pairs=12)
    assert planned["status"] == "UNPLANNABLE"
