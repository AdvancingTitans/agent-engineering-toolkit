"""Fixed, model-free rules for Improvement Constraints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConstraintRule:
    objective: str
    required_behavior: tuple[str, ...]
    forbidden_behavior: tuple[str, ...]


RULES = {
    "scope_violation": ConstraintRule(
        "Restore the implementation to the evidenced and approved change scope.",
        ("Keep changes within explicitly allowed paths.",),
        ("Do not broaden scope without human review.",),
    ),
    "unsupported_claim": ConstraintRule(
        "Prevent unsupported facts from being emitted as evidence-grounded claims.",
        ("Distinguish empty or missing results.", "Propagate a structured non-evidence state."),
        ("Do not convert an empty result into a factual claim.",),
    ),
    "missing_verification": ConstraintRule(
        "Add the missing verification needed to evaluate the claimed behavior.",
        ("Define a reproducible verification command.",),
        ("Do not mark the improvement verified without Proof.",),
    ),
    "stale_verification": ConstraintRule(
        "Re-establish verification against the current relevant files and environment.",
        ("Re-run the bound verification for the current workspace.",),
        ("Do not reuse stale Proof as current Proof.",),
    ),
    "missing_test": ConstraintRule(
        "Add regression coverage for the evidenced failure behavior.",
        ("Cover both the failing and clean behavior.",),
        ("Do not delete or weaken existing tests.",),
    ),
    "error_handling_gap": ConstraintRule(
        "Handle the evidenced tool failure states without unsupported output.",
        ("Keep empty, timeout, and missing-source states distinct.",),
        ("Do not hide failures or fabricate fallback facts.",),
    ),
    "unknown_root_cause": ConstraintRule(
        "Investigate and evidence the root cause before proposing code changes.",
        ("INVESTIGATION_REQUIRED",),
        ("Do not name a file or direct code modification before the root cause is evidenced.",),
    ),
}


PROTECTED_PATHS = [
    "tests/evals/**",
    "eval/**",
    "grader/**",
    "fixtures/**",
    ".aet/**",
]
