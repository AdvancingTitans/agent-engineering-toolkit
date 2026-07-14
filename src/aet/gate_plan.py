"""Deterministic, hash-bound planning for cost-aware observed Agent gates."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


class GatePlanError(ValueError):
    """Raised when a Gate Plan would weaken or ambiguously define a gate."""


_PRESETS: dict[str, dict[str, Any]] = {
    "R0": {"applicability": "NOT_APPLICABLE", "min_pairs": 0, "max_pairs": 0, "batch_size": 0},
    "R1": {"applicability": "NOT_APPLICABLE", "min_pairs": 0, "max_pairs": 0, "batch_size": 0},
    "R2": {"applicability": "PRELIMINARY", "min_pairs": 2, "max_pairs": 4, "batch_size": 2},
    "R3": {"applicability": "REQUIRED", "min_pairs": 4, "max_pairs": 12, "batch_size": 2},
    "R4": {"applicability": "REQUIRED", "min_pairs": 8, "max_pairs": 24, "batch_size": 2},
}
_ALTERNATIVES = {"R2": (0.90, 0.05), "R3": (0.85, 0.05), "R4": (0.75, 0.05)}


def build_gate_plan(
    *,
    risk_class: str,
    claims: list[str],
    suites: Mapping[str, int],
    min_pairs: int | None = None,
    max_pairs: int | None = None,
    batch_size: int | None = None,
    alpha: float = 0.05,
    beta: float = 0.20,
    mcid: float = 0.05,
    minimum_unique_tasks: int | None = None,
    candidate: Mapping[str, Any] | None = None,
    runner: Mapping[str, Any] | None = None,
    suite_bindings: Mapping[str, Any] | None = None,
    scorer_sha256: str | None = None,
    p_better: float | None = None,
    p_worse: float | None = None,
) -> dict[str, Any]:
    """Build a deterministic plan. Presets are defaults, never universal sample laws."""
    if risk_class not in _PRESETS:
        raise GatePlanError("risk_class must be one of R0, R1, R2, R3, or R4")
    preset = _PRESETS[risk_class]
    minimum = preset["min_pairs"] if min_pairs is None else min_pairs
    maximum = preset["max_pairs"] if max_pairs is None else max_pairs
    batch = preset["batch_size"] if batch_size is None else batch_size
    power_analysis: dict[str, Any] | None = None
    if preset["applicability"] == "REQUIRED":
        alternative = _ALTERNATIVES[risk_class] if p_better is None and p_worse is None else (p_better, p_worse)
        if not all(isinstance(value, (int, float)) for value in alternative):
            raise GatePlanError("p_better and p_worse must be supplied together")
        power_analysis = plan_sequential_pairs(alpha=alpha, beta=beta, mcid=mcid, p_better=float(alternative[0]), p_worse=float(alternative[1]), batch_size=batch, max_pairs=200)
        if power_analysis["status"] != "PLANNED":
            raise GatePlanError("declared alternative cannot reach target sequential power")
        if max_pairs is None:
            maximum = max(maximum, power_analysis["pairs"])
    objectives = {
        name: "no_regression" if name == "core" else "confirmatory_superiority" if name == "held_out" else "superiority"
        for name in suites
    }
    suite_designs = {}
    for name, objective in objectives.items():
        task_count = max(1, int(suites[name]))
        if maximum == 0:
            suite_designs[name] = {"min_pairs": 0, "max_pairs": 0, "batch_size": 0}
        elif objective == "no_regression":
            suite_designs[name] = {"min_pairs": task_count, "max_pairs": task_count, "batch_size": task_count}
        else:
            aligned_minimum = max(task_count, math.ceil(minimum / task_count) * task_count)
            aligned_maximum = max(aligned_minimum, math.ceil(maximum / task_count) * task_count)
            aligned_batch = max(task_count, math.ceil(batch / task_count) * task_count)
            suite_designs[name] = {"min_pairs": aligned_minimum, "max_pairs": aligned_maximum, "batch_size": aligned_batch}
    unique_tasks = sum(max(0, int(count)) for count in suites.values())
    plan = {
        "schema_version": "gate-plan/v2",
        "applicability": preset["applicability"],
        "risk_class": risk_class,
        "claims": sorted(set(claims)),
        "suite_objectives": objectives,
        "suite_designs": suite_designs,
        "decision": {
            "method": "group_sequential_bonferroni" if maximum else "deterministic_only",
            "alpha": alpha,
            "beta": beta,
            "mcid": mcid,
            "min_pairs": minimum,
            "max_pairs": maximum,
            "batch_size": batch,
            "alternative": None if power_analysis is None else power_analysis["alternative"],
            "alternative_source": None if power_analysis is None else ("risk_preset" if p_better is None else "explicit"),
            "power_analysis": power_analysis,
        },
        "coverage": {
            "minimum_unique_tasks": minimum_unique_tasks if minimum_unique_tasks is not None else unique_tasks,
            "unique_tasks": unique_tasks,
            "suite_task_counts": dict(sorted((name, int(count)) for name, count in suites.items())),
        },
        "history": {
            "mode": "planning_only",
            "discount": 0.25,
            "max_effective_pairs": 4,
            "final_decision_uses_fresh_pairs_only": True,
        },
    }
    if candidate is not None:
        plan["candidate"] = dict(candidate)
    if runner is not None:
        plan["runner"] = dict(runner)
    if suite_bindings is not None:
        plan["suite_bindings"] = dict(suite_bindings)
    if scorer_sha256 is not None:
        plan["scorer_sha256"] = scorer_sha256
    validate_gate_plan(plan)
    return plan


def load_gate_plan(path: Path) -> dict[str, Any]:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GatePlanError(f"cannot read Gate Plan: {error}") from error
    if not isinstance(plan, dict):
        raise GatePlanError("Gate Plan must be a JSON object")
    validate_gate_plan(plan)
    return plan


def validate_gate_plan(plan: Mapping[str, Any]) -> None:
    allowed_fields = {"schema_version", "plan_sha256", "applicability", "risk_class", "claims", "suite_objectives", "suite_designs", "decision", "coverage", "history", "candidate", "runner", "suite_bindings", "scorer_sha256"}
    if set(plan) - allowed_fields:
        raise GatePlanError("Gate Plan contains unknown fields")
    if plan.get("schema_version") != "gate-plan/v2":
        raise GatePlanError("Gate Plan schema_version must be gate-plan/v2")
    if plan.get("risk_class") not in _PRESETS:
        raise GatePlanError("Gate Plan risk_class is invalid")
    if plan.get("applicability") not in {"NOT_APPLICABLE", "PRELIMINARY", "REQUIRED"}:
        raise GatePlanError("Gate Plan applicability is invalid")
    claims = plan.get("claims")
    if not isinstance(claims, list) or (plan.get("applicability") != "NOT_APPLICABLE" and not claims) or any(not isinstance(item, str) or not item for item in claims):
        raise GatePlanError("Gate Plan claims must be non-empty strings")
    objectives = plan.get("suite_objectives")
    allowed_objectives = {"no_regression", "superiority", "confirmatory_superiority", "reliability"}
    if not isinstance(objectives, dict) or any(value not in allowed_objectives for value in objectives.values()):
        raise GatePlanError("Gate Plan has an invalid suite objective")
    designs = plan.get("suite_designs")
    if not isinstance(designs, dict) or set(designs) != set(objectives):
        raise GatePlanError("Gate Plan requires one design per suite")
    for name, design in designs.items():
        if not isinstance(design, dict) or any(not isinstance(design.get(field), int) for field in ("min_pairs", "max_pairs", "batch_size")):
            raise GatePlanError(f"suite design {name} is invalid")
        if plan.get("applicability") == "NOT_APPLICABLE":
            if any(design[field] != 0 for field in ("min_pairs", "max_pairs", "batch_size")):
                raise GatePlanError(f"suite design {name} must be zero for NOT_APPLICABLE")
        elif design["min_pairs"] < 1 or design["max_pairs"] < design["min_pairs"] or design["batch_size"] < 1:
            raise GatePlanError(f"suite design {name} has invalid bounds")
    decision = plan.get("decision")
    if not isinstance(decision, dict):
        raise GatePlanError("Gate Plan decision is required")
    minimum, maximum, batch = (decision.get(name) for name in ("min_pairs", "max_pairs", "batch_size"))
    if not all(isinstance(value, int) and value >= 0 for value in (minimum, maximum, batch)):
        raise GatePlanError("Gate Plan pair bounds must be non-negative integers")
    if minimum > maximum:
        raise GatePlanError("Gate Plan min_pairs cannot exceed max_pairs")
    if maximum == 0:
        if plan.get("applicability") != "NOT_APPLICABLE" or batch != 0:
            raise GatePlanError("zero-pair Gate Plans must be NOT_APPLICABLE")
    elif batch < 1 or minimum < 1:
        raise GatePlanError("an applicable Gate Plan requires positive min_pairs and batch_size")
    for name in ("alpha", "beta", "mcid"):
        value = decision.get(name)
        if not isinstance(value, (int, float)) or not 0 < value < 1:
            raise GatePlanError(f"Gate Plan {name} must be between zero and one")
    if plan.get("applicability") == "REQUIRED":
        power = decision.get("power_analysis")
        if not isinstance(power, dict) or power.get("status") != "PLANNED" or power.get("power", 0) < 1 - decision["beta"]:
            raise GatePlanError("required Gate Plans must meet their declared power")
        if maximum < power.get("pairs", maximum + 1):
            raise GatePlanError("Gate Plan max_pairs is below its powered design")
    coverage = plan.get("coverage")
    if not isinstance(coverage, dict) or not isinstance(coverage.get("minimum_unique_tasks"), int) or coverage["minimum_unique_tasks"] < 0:
        raise GatePlanError("Gate Plan coverage minimum is invalid")
    history = plan.get("history")
    if not isinstance(history, dict) or history.get("mode") != "planning_only" or history.get("final_decision_uses_fresh_pairs_only") is not True:
        raise GatePlanError("historical evidence may only be planning_only in gate-plan/v2")
    if plan.get("applicability") != "NOT_APPLICABLE":
        candidate = plan.get("candidate")
        if not isinstance(candidate, dict) or not all(isinstance(candidate.get(name), str) and candidate[name] for name in ("candidate_id", "baseline_sha256", "candidate_sha256")):
            raise GatePlanError("an applicable Gate Plan requires an exact candidate binding")
        if not _is_sha256(candidate["baseline_sha256"]) or not _is_sha256(candidate["candidate_sha256"]):
            raise GatePlanError("Gate Plan candidate hashes are invalid")
        runner = plan.get("runner")
        if not isinstance(runner, dict) or not all(isinstance(runner.get(name), str) and runner[name] for name in ("name", "version", "config_sha256", "model_fingerprint", "network_isolation", "evidence_schema")):
            raise GatePlanError("an applicable Gate Plan requires an exact runner binding")
        if not _is_sha256(runner["config_sha256"]):
            raise GatePlanError("Gate Plan runner config hash is invalid")
        bindings = plan.get("suite_bindings")
        if not isinstance(bindings, dict) or set(bindings) != set(objectives):
            raise GatePlanError("an applicable Gate Plan requires exact bindings for every suite")
        for name, binding in bindings.items():
            if not isinstance(binding, dict) or not isinstance(binding.get("task_count"), int) or binding["task_count"] < 1:
                raise GatePlanError(f"suite binding {name} has an invalid task_count")
            if binding["task_count"] != plan.get("coverage", {}).get("suite_task_counts", {}).get(name):
                raise GatePlanError(f"suite binding {name} task_count does not match coverage")
            if not isinstance(binding.get("task_ids"), list) or len(binding["task_ids"]) != binding["task_count"]:
                raise GatePlanError(f"suite binding {name} task IDs are incomplete")
            if len(set(binding["task_ids"])) != len(binding["task_ids"]):
                raise GatePlanError(f"suite binding {name} task IDs are duplicated")
            if not isinstance(binding.get("suite_sha256"), list) or not binding["suite_sha256"] or any(not _is_sha256(value) for value in binding["suite_sha256"]):
                raise GatePlanError(f"suite binding {name} hashes are missing")
        all_task_ids = [task_id for binding in bindings.values() for task_id in binding["task_ids"]]
        if len(set(all_task_ids)) != len(all_task_ids):
            raise GatePlanError("Gate Plan suites reuse task IDs")
        all_hashes = [value for binding in bindings.values() for value in binding["suite_sha256"]]
        if len(set(all_hashes)) != len(all_hashes):
            raise GatePlanError("Gate Plan suites overlap")
        if not _is_sha256(plan.get("scorer_sha256")):
            raise GatePlanError("an applicable Gate Plan requires a scorer hash")
    if plan.get("plan_sha256") is not None:
        body = {key: value for key, value in plan.items() if key != "plan_sha256"}
        if plan["plan_sha256"] != hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest():
            raise GatePlanError("Gate Plan plan_sha256 does not match canonical bytes")


def plan_sha256(plan: Mapping[str, Any]) -> str:
    validate_gate_plan(plan)
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def plan_fixed_pairs(
    *, alpha: float, beta: float, mcid: float, p_better: float,
    p_worse: float, max_pairs: int, task_multiple: int = 1,
) -> dict[str, Any]:
    """Find the smallest fixed N whose exact directional test meets power.

    The alternative is explicit because sample size cannot be inferred from
    alpha alone. Concordant probability is the remaining mass.
    """
    if not 0 < alpha < 1 or not 0 < beta < 1 or not 0 < mcid < 1:
        raise GatePlanError("alpha, beta, and mcid must be between zero and one")
    if p_better < 0 or p_worse < 0 or p_better + p_worse > 1 or p_better <= p_worse:
        return {"status": "UNPLANNABLE", "reason": "alternative must have p_better > p_worse and valid probability mass"}
    if max_pairs < 1 or task_multiple < 1:
        raise GatePlanError("max_pairs and task_multiple must be positive")
    target = 1 - beta
    previous = 0.0
    for pairs in range(task_multiple, max_pairs + 1, task_multiple):
        power = _exact_rejection_probability(pairs, alpha=alpha, mcid=mcid, p_better=p_better, p_worse=p_worse)
        if power + 1e-12 >= target:
            return {
                "status": "PLANNED", "pairs": pairs, "power": power,
                "previous_power": previous, "target_power": target,
                "alternative": {"p_better": p_better, "p_worse": p_worse, "p_concordant": 1 - p_better - p_worse},
                "tail": "candidate_better_one_sided", "alpha": alpha, "mcid": mcid,
            }
        previous = power
    return {"status": "UNPLANNABLE", "reason": "target power is not reached within max_pairs", "maximum_power": previous, "target_power": target}


def plan_sequential_pairs(
    *, alpha: float, beta: float, mcid: float, p_better: float,
    p_worse: float, batch_size: int, max_pairs: int,
) -> dict[str, Any]:
    """Plan a conservative sequential maximum using its strictest local alpha.

    The final look alone must meet target power at alpha/number-of-looks, so
    optional earlier efficacy looks cannot reduce the declared power.
    """
    if batch_size < 1:
        raise GatePlanError("batch_size must be positive")
    target = 1 - beta
    previous = 0.0
    for pairs in range(batch_size, max_pairs + 1, batch_size):
        looks = math.ceil(pairs / batch_size)
        local_alpha = alpha / looks
        power = _exact_rejection_probability(pairs, alpha=local_alpha, mcid=mcid, p_better=p_better, p_worse=p_worse)
        if power + 1e-12 >= target:
            return {"status": "PLANNED", "pairs": pairs, "power": power, "previous_power": previous, "target_power": target, "planned_looks": looks, "local_alpha": local_alpha, "alternative": {"p_better": p_better, "p_worse": p_worse, "p_concordant": 1 - p_better - p_worse}, "method": "conservative_final_look_lower_bound"}
        previous = power
    return {"status": "UNPLANNABLE", "maximum_power": previous, "target_power": target}


def _exact_rejection_probability(pairs: int, *, alpha: float, mcid: float, p_better: float, p_worse: float) -> float:
    concordant_probability = 1 - p_better - p_worse
    total = 0.0
    for better in range(pairs + 1):
        for worse in range(pairs - better + 1):
            if (better - worse) / pairs < mcid or _directional_exact_p(better, worse) > alpha:
                continue
            concordant = pairs - better - worse
            ways = math.comb(pairs, better) * math.comb(pairs - better, worse)
            total += ways * (p_better**better) * (p_worse**worse) * (concordant_probability**concordant)
    return min(1.0, total)


def _directional_exact_p(better: int, worse: int) -> float:
    discordant = better + worse
    if discordant == 0:
        return 1.0
    return sum(math.comb(discordant, value) for value in range(better, discordant + 1)) / (2**discordant)


def registry_sha256(registry: Mapping[str, Any]) -> str:
    """Validate and hash an append-only, verified Gate history registry."""
    if registry.get("schema_version") != "gate-history-registry/v1" or not isinstance(registry.get("entries"), list):
        raise GatePlanError("history registry must use gate-history-registry/v1")
    entry_ids: set[str] = set()
    source_ids: set[str] = set()
    for entry in registry["entries"]:
        _validate_history_entry(entry)
        entry_id = entry["entry_id"]
        source_id = entry["source"]["gate_manifest_sha256"]
        if entry_id in entry_ids or source_id in source_ids:
            raise GatePlanError("history registry contains a duplicate entry or verified source")
        entry_ids.add(entry_id)
        source_ids.add(source_id)
    body = {key: value for key, value in registry.items() if key != "registry_id"}
    digest = _canonical_sha(body)
    if registry.get("registry_id") is not None and registry["registry_id"] != digest:
        raise GatePlanError("history registry_id does not match canonical bytes")
    return digest


def assess_history_for_plan(registry: Mapping[str, Any], *, plan: Mapping[str, Any], suite: str) -> dict[str, Any]:
    """Use exact-compatible history for planning sensitivity, never for PASS."""
    registry_id = registry_sha256(registry)
    validate_gate_plan(plan)
    if suite not in plan["suite_bindings"]:
        raise GatePlanError(f"suite {suite} is not bound by the Gate Plan")
    history_policy = plan["history"]
    discount = history_policy["discount"]
    cap = history_policy["max_effective_pairs"]
    plan_body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    expected = {
        "claim_ids": plan["claims"],
        "suite": suite,
        "suite_binding_sha256": _canonical_sha(plan["suite_bindings"][suite]),
        "scorer_sha256": plan["scorer_sha256"],
        "baseline_sha256": plan["candidate"]["baseline_sha256"],
        "candidate_sha256": plan["candidate"]["candidate_sha256"],
        "runner_name": plan["runner"]["name"],
        "runner_version": plan["runner"]["version"],
        "runner_config_sha256": plan["runner"]["config_sha256"],
        "model_fingerprint": plan["runner"]["model_fingerprint"],
        "network_isolation": plan["runner"]["network_isolation"],
        "evidence_schema": plan["runner"]["evidence_schema"],
        "stopping_plan_sha256": plan_sha256(plan_body),
    }
    decisions, eligible_entries, reasons = [], [], {}
    for entry in registry["entries"]:
        mismatches = [key for key, value in expected.items() if entry["identity"].get(key) != value]
        status = "ELIGIBLE" if not mismatches else "INELIGIBLE"
        reason = "EXACT_MATCH" if not mismatches else "DRIFT:" + ",".join(sorted(mismatches))
        decisions.append({"entry_id": entry["entry_id"], "status": status, "reason": reason})
        if mismatches:
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            eligible_entries.append(entry)
    raw_pairs = sum(entry["sampling"]["usable_pairs"] for entry in eligible_entries)
    effective_by_entry = [min(cap, math.floor(entry["sampling"]["usable_pairs"] * discount)) for entry in eligible_entries]
    effective_pairs = min(cap, sum(effective_by_entry))
    better = sum(entry["discordance"]["better"] for entry in eligible_entries)
    worse = sum(entry["discordance"]["worse"] for entry in eligible_entries)
    planned_max = plan["suite_designs"][suite]["max_pairs"]
    leave_one_out = [max(0, effective_pairs - value) for value in effective_by_entry]
    return {
        "schema_version": "gate-history-assessment/v1",
        "registry_sha256": registry_id,
        "gate_plan_sha256": plan_sha256(plan_body),
        "suite": suite,
        "mode": "planning_only",
        "eligible_records": len(eligible_entries),
        "rejected_records": len(registry["entries"]) - len(eligible_entries),
        "entry_decisions": decisions,
        "rejection_reasons": dict(sorted(reasons.items())),
        "raw_pairs": raw_pairs,
        "effective_pairs": effective_pairs,
        "observed_better": better,
        "observed_worse": worse,
        "discount": discount,
        "max_effective_pairs": cap,
        "drift_detected": bool(reasons),
        "sensitivity": {
            "discount_grid": [0.0, discount, 0.25],
            "planned_max_pairs_without_history": planned_max,
            "planned_max_pairs_with_history": planned_max,
            "leave_one_release_out_effective_pairs": leave_one_out,
            "worst_case_drift_effective_pairs": 0,
        },
        "final_decision_uses_fresh_pairs_only": True,
    }


def _validate_history_entry(entry: Any) -> None:
    if not isinstance(entry, dict):
        raise GatePlanError("history entry must be an object")
    body = {key: value for key, value in entry.items() if key != "entry_id"}
    if entry.get("entry_id") != _canonical_sha(body):
        raise GatePlanError("history entry_id does not match canonical bytes")
    source, identity, sampling, discordance = (entry.get(name) for name in ("source", "identity", "sampling", "discordance"))
    if not all(isinstance(value, dict) for value in (source, identity, sampling, discordance)):
        raise GatePlanError("history entry sections are incomplete")
    if source.get("verified") is not True or source.get("status") != "PASS":
        raise GatePlanError("history source must be independently verified PASS")
    for name in ("gate_manifest_sha256", "raw_gate_sha256", "verification_sha256"):
        if not _is_sha256(source.get(name)):
            raise GatePlanError(f"history source {name} is invalid")
    commit = source.get("commit")
    if not isinstance(commit, str) or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit.lower()):
        raise GatePlanError("history source commit is invalid")
    required_identity = ("claim_ids", "suite", "suite_binding_sha256", "scorer_sha256", "baseline_sha256", "candidate_sha256", "runner_name", "runner_version", "runner_config_sha256", "model_fingerprint", "network_isolation", "evidence_schema", "stopping_plan_sha256")
    if any(identity.get(name) in (None, "", []) for name in required_identity):
        raise GatePlanError("history identity is incomplete")
    integer_fields = (sampling.get("planned_pairs"), sampling.get("usable_pairs"), sampling.get("infrastructure_pairs"), discordance.get("better"), discordance.get("worse"), discordance.get("concordant_pass"), discordance.get("concordant_fail"))
    if any(not isinstance(value, int) or value < 0 for value in integer_fields):
        raise GatePlanError("history sampling counts must be non-negative integers")
    if sampling["usable_pairs"] + sampling["infrastructure_pairs"] > sampling["planned_pairs"]:
        raise GatePlanError("history sampling counts exceed planned pairs")
    if sum(discordance[name] for name in ("better", "worse", "concordant_pass", "concordant_fail")) != sampling["usable_pairs"]:
        raise GatePlanError("history discordance counts do not equal usable pairs")


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())
