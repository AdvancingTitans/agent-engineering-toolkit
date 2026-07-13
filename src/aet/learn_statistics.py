"""Small, dependency-free paired statistics for observed AET rollouts."""

from __future__ import annotations

import math
from typing import Any

from .learn_contracts import ALL_HARD_FINDINGS


def compare_pairs(pairs: list[dict[str, Any]], *, profile: str) -> dict[str, Any]:
    """Compare paired PASS/FAIL executions without inventing a composite score."""
    if profile not in {"preliminary", "adoptable"}:
        raise ValueError("statistics profile must be preliminary or adoptable")
    usable = [pair for pair in pairs if pair.get("baseline", {}).get("status") in {"PASS", "FAIL"} and pair.get("candidate", {}).get("status") in {"PASS", "FAIL"}]
    infrastructure = len(pairs) - len(usable)
    baseline_success = sum(pair["baseline"]["status"] == "PASS" for pair in usable)
    candidate_success = sum(pair["candidate"]["status"] == "PASS" for pair in usable)
    better = sum(pair["baseline"]["status"] == "FAIL" and pair["candidate"]["status"] == "PASS" for pair in usable)
    worse = sum(pair["baseline"]["status"] == "PASS" and pair["candidate"]["status"] == "FAIL" for pair in usable)
    discordant = better + worse
    p_value = _mcnemar_exact(better, worse) if discordant else 1.0
    hard_regressions = _hard_regressions(usable)
    gain = (candidate_success - baseline_success) / max(len(usable), 1)
    if infrastructure:
        status = "INFRASTRUCTURE_ERROR"
    elif profile == "adoptable" and len(usable) < 5:
        status = "INCONCLUSIVE"
    elif hard_regressions:
        status = "FAIL"
    elif profile == "adoptable" and (gain < 0.05 or p_value > 0.05):
        status = "INCONCLUSIVE"
    elif candidate_success < baseline_success:
        status = "FAIL"
    else:
        status = "PASS" if profile == "adoptable" else "PRELIMINARY"
    return {
        "report_kind": "learning_paired_statistics",
        "profile": profile,
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
        "hard_regressions": hard_regressions,
        "reliability": summarize_reliability(pairs),
        "acceptance": "PASS requires an adoptable profile, no infrastructure error, no safety regression, >=5 paired runs, >=0.05 gain, and exact p<=0.05.",
    }


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
