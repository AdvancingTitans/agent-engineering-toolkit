"""Promote an Improvement Outcome only after valid Proof."""

from __future__ import annotations

from dataclasses import replace

from ..models.outcome import ImprovementOutcome


def promote_outcome(
    outcome: ImprovementOutcome,
    *,
    proof_valid: bool,
    verification_pass: bool,
    code_change: bool,
) -> ImprovementOutcome:
    """Apply the exact implemented_unverified → verified transition."""
    if proof_valid and verification_pass and code_change:
        return replace(outcome, status="verified_improvement")
    return replace(outcome, status="implemented_unverified")
