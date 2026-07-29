"""Bind Proof to a Verification Contract and produce an Outcome."""

from __future__ import annotations

from typing import Any, Mapping

from ..models.outcome import ImprovementOutcome
from ..models.verification import VerificationContract
from ..validator import ValidationResult
from .promote import promote_outcome


def validate_proof(
    contract: VerificationContract,
    proof: Mapping[str, Any] | None,
    *,
    candidate_id: str,
) -> ValidationResult:
    """Fail closed on missing, stale, unbound, or incomplete Proof."""
    if proof is None:
        return ValidationResult(False, "NOT_ACTIONABLE", "Required Proof is missing.")
    if proof.get("freshness") != "current":
        return ValidationResult(False, "STALE_PROOF", "Proof is not current.")
    if proof.get("contract_id") != contract.id:
        return ValidationResult(
            False,
            "INVALID_REFERENCE",
            "Proof does not bind the Verification Contract.",
        )
    if proof.get("candidate_id") != candidate_id:
        return ValidationResult(
            False,
            "INVALID_REFERENCE",
            "Proof does not bind the Improvement Candidate.",
        )
    if proof.get("status") != "PASS":
        return ValidationResult(False, "VERIFICATION_FAILED", "Proof status is not PASS.")
    results = proof.get("command_results")
    if not isinstance(results, list):
        return ValidationResult(
            False,
            "NOT_ACTIONABLE",
            "Proof command_results are missing.",
        )
    observed = {
        item.get("command"): item.get("exit_code")
        for item in results
        if isinstance(item, Mapping)
    }
    missing = [
        command
        for command in contract.commands
        if observed.get(command) != 0
    ]
    if missing:
        return ValidationResult(
            False,
            "VERIFICATION_FAILED",
            "Verification commands did not pass: " + ", ".join(missing),
        )
    changed_paths = proof.get("changed_paths")
    if not isinstance(changed_paths, list) or not changed_paths:
        return ValidationResult(
            False,
            "NOT_ACTIONABLE",
            "Proof does not record a Code Change.",
        )
    if not set(contract.relevant_paths).issubset(set(changed_paths)):
        return ValidationResult(
            False,
            "INVALID_REFERENCE",
            "Proof does not bind all relevant paths.",
        )
    return ValidationResult(True, "VALID", "Proof is current and contract-bound.")


def verify_improvement(
    contract: VerificationContract,
    *,
    issue_id: str = "",
    candidate_id: str = "",
    proof: Mapping[str, Any] | None = None,
    before_metrics: Mapping[str, Any] | None = None,
    after_metrics: Mapping[str, Any] | None = None,
) -> ImprovementOutcome:
    """Return verified_improvement only with Code Change + Contract + Proof."""
    proof_result = validate_proof(
        contract,
        proof,
        candidate_id=candidate_id,
    )
    proof_id = (
        proof.get("id")
        if proof_result.valid and isinstance(proof, Mapping)
        else None
    )
    base = ImprovementOutcome(
        issue_id=issue_id,
        candidate_id=candidate_id,
        status="implemented_unverified",
        before_metrics=dict(before_metrics or {}),
        after_metrics=dict(after_metrics or {}),
        proof_refs=[proof_id] if isinstance(proof_id, str) and proof_id else [],
    )
    code_change = (
        isinstance(proof, Mapping)
        and isinstance(proof.get("changed_paths"), list)
        and bool(proof["changed_paths"])
    )
    return promote_outcome(
        base,
        proof_valid=proof_result.valid,
        verification_pass=proof_result.valid,
        code_change=code_change,
    )
