"""Small, dependency-free paired statistics for observed AET rollouts."""

from __future__ import annotations

import math
from typing import Any

from .learn_contracts import ALL_HARD_FINDINGS


def compare_pairs(
    pairs: list[dict[str, Any]], *, profile: str, objective: str = "legacy_superiority",
    minimum_pairs: int | None = None, alpha: float = 0.05, mcid: float = 0.05,
) -> dict[str, Any]:
    """Compare paired PASS/FAIL executions without inventing a composite score."""
    if profile not in {"preliminary", "adoptable"}:
        raise ValueError("statistics profile must be preliminary or adoptable")
    if objective not in {"legacy_superiority", "no_regression", "superiority", "confirmatory_superiority", "reliability"}:
        raise ValueError("statistics objective is invalid")
    required = 5 if minimum_pairs is None else minimum_pairs
    usable = [pair for pair in pairs if pair.get("baseline", {}).get("status") in {"PASS", "FAIL"} and pair.get("candidate", {}).get("status") in {"PASS", "FAIL"}]
    infrastructure = len(pairs) - len(usable)
    baseline_success = sum(pair["baseline"]["status"] == "PASS" for pair in usable)
    candidate_success = sum(pair["candidate"]["status"] == "PASS" for pair in usable)
    better = sum(pair["baseline"]["status"] == "FAIL" and pair["candidate"]["status"] == "PASS" for pair in usable)
    worse = sum(pair["baseline"]["status"] == "PASS" and pair["candidate"]["status"] == "FAIL" for pair in usable)
    discordant = better + worse
    p_value = _mcnemar_exact(better, worse) if discordant else 1.0
    directional_p_value = _mcnemar_directional(better, worse) if discordant else 1.0
    hard_regressions = _hard_regressions(usable)
    gain = (candidate_success - baseline_success) / max(len(usable), 1)
    if infrastructure:
        status = "INFRASTRUCTURE_ERROR"
    elif profile == "adoptable" and len(usable) < required:
        status = "INCONCLUSIVE"
    elif hard_regressions:
        status = "FAIL"
    elif objective == "no_regression" and (worse or candidate_success != len(usable)):
        status = "FAIL"
    elif objective == "no_regression":
        status = "PASS" if profile == "adoptable" else "PRELIMINARY"
    elif candidate_success < baseline_success:
        status = "FAIL"
    elif profile == "adoptable" and (gain < mcid or (p_value if objective == "legacy_superiority" else directional_p_value) > alpha):
        status = "INCONCLUSIVE"
    else:
        status = "PASS" if profile == "adoptable" else "PRELIMINARY"
    return {
        "report_kind": "learning_paired_statistics",
        "profile": profile,
        "objective": objective,
        "status": status,
        "pair_count": len(pairs),
        "usable_pair_count": len(usable),
        "infrastructure_pair_count": infrastructure,
        "baseline_successes": baseline_success,
        "candidate_successes": candidate_success,
        "absolute_task_gain": gain,
        "better": better,
        "worse": worse,
        "mcnemar_exact_p_value": p_value,
        "directional_mcnemar_p_value": directional_p_value,
        "hard_regressions": hard_regressions,
        "reliability": summarize_reliability(pairs),
        "acceptance": f"PASS requires objective={objective}, an adoptable profile, no infrastructure error, no safety regression, >={required} fresh paired runs, and its declared objective boundary.",
    }


def sequential_decision(
    pairs: list[dict[str, Any]], *, objective: str, minimum_pairs: int,
    maximum_pairs: int, batch_size: int, alpha: float, mcid: float,
) -> dict[str, Any]:
    """Apply a prespecified Bonferroni group-sequential boundary.

    Fresh pairs only enter the decision. Dividing alpha across the maximum
    number of looks is conservative but prevents fixed-p optional stopping.
    """
    if minimum_pairs < 1 or maximum_pairs < minimum_pairs or batch_size < 1:
        raise ValueError("invalid sequential pair bounds")
    schedule = alpha_spending_schedule(maximum_pairs=maximum_pairs, batch_size=batch_size, alpha=alpha)
    looks = len(schedule)
    look_alpha = schedule[min(max(1, math.ceil(len(pairs) / batch_size)), looks) - 1]["local_alpha"]
    report = compare_pairs(
        pairs,
        profile="adoptable",
        objective=objective,
        minimum_pairs=minimum_pairs,
        alpha=look_alpha,
        mcid=mcid,
    )
    report.update({
        "decision_method": "group_sequential_bonferroni",
        "family_alpha": alpha,
        "look_alpha": look_alpha,
        "planned_looks": looks,
        "current_look": math.ceil(len(pairs) / batch_size),
        "minimum_pairs": minimum_pairs,
        "maximum_pairs": maximum_pairs,
    })
    if report["hard_regressions"]:
        report.update(status="FAIL", stop_reason="HARD_REGRESSION")
    elif report["status"] == "INFRASTRUCTURE_ERROR":
        report["stop_reason"] = "INFRASTRUCTURE_ABORT"
    elif report["status"] == "FAIL":
        report["stop_reason"] = "REGRESSION_BOUNDARY"
    elif report["status"] == "PASS":
        report["stop_reason"] = "SUCCESS_BOUNDARY"
    elif len(pairs) >= maximum_pairs:
        report.update(status="INCONCLUSIVE", stop_reason="MAX_SAMPLE_INCONCLUSIVE")
    elif objective != "no_regression" and not _success_still_reachable(report, current_pairs=len(pairs), minimum_pairs=minimum_pairs, maximum_pairs=maximum_pairs, batch_size=batch_size, look_alpha=look_alpha, mcid=mcid):
        report.update(status="INCONCLUSIVE", stop_reason="FUTILITY_BOUNDARY")
    else:
        report.update(status="CONTINUE", stop_reason="EVIDENCE_PENDING")
    return report


def alpha_spending_schedule(*, maximum_pairs: int, batch_size: int, alpha: float) -> list[dict[str, float | int]]:
    """Equal Bonferroni spending; local alpha sums exactly to family alpha."""
    if maximum_pairs < 1 or batch_size < 1 or not 0 < alpha < 1:
        raise ValueError("invalid alpha-spending inputs")
    looks = math.ceil(maximum_pairs / batch_size)
    local = alpha / looks
    return [{"look": look, "local_alpha": local, "cumulative_alpha": local * look} for look in range(1, looks + 1)]


def _success_still_reachable(report: dict[str, Any], *, current_pairs: int, minimum_pairs: int, maximum_pairs: int, batch_size: int, look_alpha: float, mcid: float) -> bool:
    for future_pairs in range(current_pairs + batch_size, maximum_pairs + batch_size, batch_size):
        future_pairs = min(future_pairs, maximum_pairs)
        added = future_pairs - current_pairs
        better = report["better"] + added
        worse = report["worse"]
        gain = (report["candidate_successes"] + added - report["baseline_successes"]) / future_pairs
        if future_pairs >= minimum_pairs and gain >= mcid and _mcnemar_directional(better, worse) <= look_alpha:
            return True
        if future_pairs == maximum_pairs:
            break
    return False


def _hard_regressions(pairs: list[dict[str, Any]]) -> list[str]:
    regressions: set[str] = set()
    for pair in pairs:
        base = {finding.get("code") for finding in pair["baseline"].get("findings", []) if finding.get("status") == "FAIL"}
        candidate = {finding.get("code") for finding in pair["candidate"].get("findings", []) if finding.get("status") == "FAIL"}
        regressions.update((candidate - base) & ALL_HARD_FINDINGS)
    return sorted(regressions)


def summarize_reliability(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Report per-task, per-variant success without changing the paired Gate."""
    groups: dict[tuple[str, str], list[bool]] = {}
    for pair in pairs:
        task_id = pair.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            task_id = "UNKNOWN"
        for variant in ("baseline", "candidate"):
            group = groups.setdefault((task_id, variant), [])
            status = pair.get(variant, {}).get("status") if isinstance(pair.get(variant), dict) else None
            if status in {"PASS", "FAIL"}:
                group.append(status == "PASS")
    rows = []
    for (task_id, variant), observations in sorted(groups.items()):
        successes, runs = sum(observations), len(observations)
        row: dict[str, Any] = {"task_id": task_id, "variant": variant, "status": "PASS" if runs else "UNKNOWN", "runs": runs, "successes": successes}
        if runs:
            lower, upper = _wilson(successes, runs)
            row.update({
                "success_rate": successes / runs, "any_success": successes > 0,
                "all_success": successes == runs, "wilson_95": {"lower": lower, "upper": upper},
            })
        rows.append(row)
    return {"status": "PASS" if any(row["runs"] for row in rows) else "UNKNOWN", "groups": rows}


def _wilson(successes: int, runs: int) -> tuple[float, float]:
    if runs <= 0:
        raise ValueError("Wilson interval requires at least one run")
    z = 1.959963984540054
    proportion = successes / runs
    denominator = 1 + z * z / runs
    center = (proportion + z * z / (2 * runs)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / runs + z * z / (4 * runs * runs)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _mcnemar_exact(better: int, worse: int) -> float:
    """Two-sided exact binomial p-value for discordant paired outcomes."""
    n = better + worse
    if n == 0:
        return 1.0
    lower = min(better, worse)
    probability = sum(math.comb(n, index) for index in range(lower + 1)) / (2**n)
    return min(1.0, 2 * probability)


def _mcnemar_directional(better: int, worse: int) -> float:
    """Pr[X >= better] under the preregistered candidate-better direction."""
    n = better + worse
    if n == 0:
        return 1.0
    return sum(math.comb(n, value) for value in range(better, n + 1)) / (2**n)
