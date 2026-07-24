"""Deterministic validation for host-authored investigated findings."""

from __future__ import annotations

from typing import Any

from .ledger import InvestigationLedger, LedgerError
from .models import FindingOrigin, SupportState


class GroundingError(ValueError):
    """Raised when a semantic finding exceeds its evidence or authority."""


_CONTRACT_KEYS = {
    "schema_version",
    "finding_type",
    "required_investigation",
    "factual_grounding",
    "semantic_judgment",
    "prohibited",
    "stop_conditions",
}
_FACTUAL_GROUNDING = {
    "tool_claims_require_result_ref",
    "user_constraints_require_source_ref",
    "negative_claims_require_search_scope",
}
_SEMANTIC_JUDGMENT = {
    "must_distinguish_fact_and_inference",
    "must_present_counter_explanation",
    "must_disclose_unresolved_assumptions",
}
_PROHIBITED = {
    "llm_similarity_as_sole_evidence",
    "unexecuted_test_as_passed",
    "unread_file_citation",
    "hidden_conflicting_evidence",
    "unsupported_authorization_inference",
    "invented_tool_result",
}
_STOP_TO_REASON = {
    "dominant_explanation_established": "DOMINANT_EXPLANATION",
    "remaining_uncertainty_does_not_change_action": "ACTION_UNCHANGED",
    "evidence_value_exhausted": "NO_NEW_DECISION_VALUE",
    "investigation_budget_exhausted": "BUDGET_EXHAUSTED",
    "user_authority_required": "AUTHORIZATION_REQUIRED",
    "user_information_required": "USER_INPUT_REQUIRED",
    "tool_unavailable": "TOOL_UNAVAILABLE",
}
_BOUNDED_STOP_REASONS = {
    "BUDGET_EXHAUSTED",
    "AUTHORIZATION_REQUIRED",
    "USER_INPUT_REQUIRED",
    "TOOL_UNAVAILABLE",
}
_FACT_KINDS = {
    "tool_fact",
    "test_passed",
    "negative_search",
    "explicit_user_constraint",
    "freshness",
}
_EVIDENCE_CLASSES = {
    "deterministic_tool",
    "explicit_user",
    "explicit_project",
    "llm_similarity",
    "host_attestation",
}


def validate_investigated_finding(
    finding: dict[str, Any],
    ledger: InvestigationLedger,
    *,
    allowed_tools: set[str] | None = None,
    allow_project_execution: bool = False,
    allow_writes: bool = False,
    investigation_contract: dict[str, Any] | None = None,
) -> None:
    """Validate references, strength, counter-evidence, permissions and fact claims."""
    try:
        ledger.validate()
    except LedgerError as error:
        raise GroundingError(str(error)) from error
    try:
        origin = FindingOrigin(finding.get("origin"))
        support = SupportState(finding.get("assessment_state", finding.get("support_state")))
    except ValueError as error:
        raise GroundingError(f"invalid finding origin or support_state: {error}") from error

    authoritative_status = finding.get("authoritative_status")
    if authoritative_status not in {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}:
        raise GroundingError("authoritative_status must preserve the Evidence First status set")
    if origin is FindingOrigin.HYPOTHESIS and (
        finding.get("blocking")
        or authoritative_status != "UNKNOWN"
    ):
        raise GroundingError("a HYPOTHESIS cannot be blocking or override UNKNOWN")
    if origin is FindingOrigin.HYPOTHESIS and support in {SupportState.CONFIRMED, SupportState.SUPPORTED}:
        raise GroundingError("a HYPOTHESIS cannot claim confirmed or supported strength")
    if support is SupportState.CONFIRMED and origin is not FindingOrigin.DETERMINISTIC:
        raise GroundingError("CONFIRMED requires a deterministic finding")
    if investigation_contract is not None:
        _validate_contract(investigation_contract, finding, ledger, support)

    refs = finding.get("evidence_refs", finding.get("result_refs"))
    if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) for ref in refs):
        raise GroundingError("an investigated finding requires result_refs")
    missing = [ref for ref in refs if ref not in ledger.result_refs]
    if missing:
        raise GroundingError(f"finding references unknown evidence: {', '.join(missing)}")

    counter = finding.get("counter_explanation")
    if isinstance(counter, dict):
        counter_statement = counter.get("statement")
        counter_refs = counter.get("evidence_refs", [])
    else:
        counter_statement = counter
        counter_refs = finding.get("counter_result_refs", [])
    if support is SupportState.SUPPORTED:
        if not isinstance(counter_statement, str) or not counter_statement.strip():
            raise GroundingError("SUPPORTED requires a reasonable counter_explanation")
        if not isinstance(counter_refs, list) or not counter_refs:
            raise GroundingError("SUPPORTED requires evidence that investigated the counter explanation")
        if any(ref not in ledger.result_refs for ref in counter_refs):
            raise GroundingError("counter explanation references unknown evidence")
    if origin is FindingOrigin.INVESTIGATED:
        judgment = finding.get("engineering_judgment")
        if not isinstance(judgment, str) or not judgment.strip():
            raise GroundingError(
                "an investigated finding must separate a non-empty engineering judgment"
            )
        if support not in {SupportState.UNSUPPORTED, SupportState.NOT_APPLICABLE}:
            if not isinstance(counter_statement, str) or not counter_statement.strip():
                raise GroundingError(
                    "an investigated finding must present a counter explanation"
                )
    if support in {
        SupportState.SUPPORTED_WITH_LIMITS,
        SupportState.CONFLICTED,
        SupportState.UNKNOWN,
    }:
        uncertainty = finding.get("remaining_uncertainty")
        if not isinstance(uncertainty, list) or not uncertainty:
            raise GroundingError(
                "a limited, conflicted, or unknown finding must disclose uncertainty"
            )
    conflicting_refs = finding.get(
        "conflicting_evidence_refs",
        finding.get("conflicting_result_refs", []),
    )
    if conflicting_refs and support not in {
        SupportState.CONFLICTED,
        SupportState.SUPPORTED_WITH_LIMITS,
    }:
        raise GroundingError("recorded conflicting evidence requires a limited or conflicted support state")
    if any(ref not in ledger.result_refs for ref in conflicting_refs):
        raise GroundingError("conflicting evidence references unknown evidence")
    material_conflicts = set(ledger.data.get("material_conflicting_evidence_refs", []))
    if material_conflicts - set(conflicting_refs):
        raise GroundingError("finding hides material conflicting evidence recorded in the ledger")

    for ref in refs + list(counter_refs):
        try:
            step = ledger.step_for(ref)
        except LedgerError as error:
            raise GroundingError(str(error)) from error
        tool = step.get("tool")
        if allowed_tools is not None and tool not in allowed_tools:
            raise GroundingError(f"tool was not authorized: {tool}")
        if step.get("executes_project_code") and not allow_project_execution:
            raise GroundingError(f"project execution was not authorized: {tool}")
        if step.get("writes") and not allow_writes:
            raise GroundingError(f"write was not authorized: {tool}")

    claims = finding.get("confirmed_facts", finding.get("factual_claims", []))
    if not isinstance(claims, list):
        raise GroundingError("factual_claims must be a list")
    for claim in claims:
        if not isinstance(claim, dict):
            raise GroundingError("every factual claim must be an object")
        claim_refs = claim.get("evidence_refs")
        if claim_refs is None and claim.get("result_ref"):
            claim_refs = [claim["result_ref"]]
        if not isinstance(claim_refs, list) or not claim_refs or any(ref not in ledger.result_refs for ref in claim_refs):
            raise GroundingError("every factual claim requires valid evidence_refs")
        kind = claim.get("kind")
        if kind not in _FACT_KINDS:
            raise GroundingError("every factual claim requires a structured kind")
        step = ledger.step_for(claim_refs[0])
        result = step.get("result")
        if kind == "test_passed":
            if not isinstance(result, dict) or result.get("exit_code") != 0:
                raise GroundingError("test_passed requires a recorded exit_code of 0")
        if kind == "negative_search":
            scope = claim.get("search_scope")
            if not isinstance(scope, list) or not scope:
                raise GroundingError("negative_search requires a non-empty search_scope")
            searched_scope = result.get("searched_scope") if isinstance(result, dict) else None
            if not isinstance(searched_scope, list) or not set(scope).issubset(searched_scope):
                raise GroundingError(
                    "negative_search scope must be covered by the recorded tool result"
                )
        if kind == "explicit_user_constraint" and claim.get("source_type") != "explicit_user":
            raise GroundingError("a user constraint cannot be inferred")
        if kind == "explicit_user_constraint":
            source_ref = claim.get("source_ref")
            source_result = ledger.step_for(source_ref).get("result") if source_ref in ledger.result_refs else None
            if (
                not isinstance(source_result, dict)
                or source_result.get("source_type") != "explicit_user"
            ):
                raise GroundingError(
                    "an explicit user constraint requires an explicit_user source_ref"
                )
        if kind == "freshness" and step.get("tool") != "aet.quick.fresh":
            raise GroundingError("freshness claims require deterministic aet.quick.fresh evidence")


def _validate_contract(
    contract: dict[str, Any],
    finding: dict[str, Any],
    ledger: InvestigationLedger,
    support: SupportState,
) -> None:
    _validate_contract_shape(contract)
    if finding.get("finding_type") != contract["finding_type"]:
        raise GroundingError("finding_type does not match the investigation contract")
    required = contract.get("required_investigation")
    completed = set(ledger.data.get("completed_investigations", []))
    missing = [item for item in required if item not in completed]
    if missing and support in {SupportState.CONFIRMED, SupportState.SUPPORTED}:
        raise GroundingError(
            "strong finding is missing required investigation: " + ", ".join(missing)
        )
    if missing and support is SupportState.SUPPORTED_WITH_LIMITS:
        uncertainty = finding.get("remaining_uncertainty")
        if not isinstance(uncertainty, list) or not uncertainty:
            raise GroundingError(
                "limited finding must disclose uncertainty from incomplete investigation"
            )

    prohibited = set(contract["prohibited"])
    refs = finding.get("evidence_refs", [])
    for ref in refs:
        evidence_class = ledger.step_for(ref).get("evidence_class")
        if evidence_class not in _EVIDENCE_CLASSES:
            raise GroundingError(
                "contract evidence requires a structured evidence_class"
            )
    if "llm_similarity_as_sole_evidence" in prohibited and refs:
        if all(
            ledger.step_for(ref).get("evidence_class") == "llm_similarity"
            for ref in refs
        ):
            raise GroundingError("LLM similarity cannot be the sole evidence")
    if "unread_file_citation" in prohibited:
        covered_paths = _covered_paths(ledger, refs)
        cited_paths = {
            location.get("path")
            for location in finding.get("locations", [])
            if isinstance(location, dict)
        }
        if any(path not in covered_paths for path in cited_paths):
            raise GroundingError("finding cites a file not covered by referenced tool evidence")

    stop = ledger.data["stop"]
    allowed_reasons = {_STOP_TO_REASON[item] for item in contract["stop_conditions"]}
    if stop["reason"] not in allowed_reasons:
        raise GroundingError("ledger stop reason is not allowed by the investigation contract")
    if stop["reason"] in _BOUNDED_STOP_REASONS and not stop["bounded_result"]:
        raise GroundingError("bounded stop reason requires bounded_result true")


def _validate_contract_shape(contract: dict[str, Any]) -> None:
    if not isinstance(contract, dict) or set(contract) != _CONTRACT_KEYS:
        raise GroundingError("investigation contract fields do not match the v1 schema")
    if contract.get("schema_version") != "aet-investigation-contract/v1":
        raise GroundingError("investigation contract schema is invalid")
    if not isinstance(contract.get("finding_type"), str) or not contract["finding_type"]:
        raise GroundingError("investigation contract finding_type must be non-empty")
    _unique_strings(contract.get("required_investigation"), "required_investigation")
    _true_object(contract.get("factual_grounding"), _FACTUAL_GROUNDING, "factual_grounding")
    _true_object(contract.get("semantic_judgment"), _SEMANTIC_JUDGMENT, "semantic_judgment")
    prohibited = _unique_strings(contract.get("prohibited"), "prohibited")
    if not set(prohibited).issubset(_PROHIBITED):
        raise GroundingError("investigation contract has an invalid prohibited behavior")
    stops = _unique_strings(contract.get("stop_conditions"), "stop_conditions")
    if not set(stops).issubset(_STOP_TO_REASON):
        raise GroundingError("investigation contract has an invalid stop condition")


def _unique_strings(value: Any, field: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
        or len(set(value)) != len(value)
    ):
        raise GroundingError(f"investigation contract {field} must contain unique strings")
    return value


def _true_object(value: Any, keys: set[str], field: str) -> None:
    if not isinstance(value, dict) or set(value) != keys or any(value[key] is not True for key in keys):
        raise GroundingError(f"investigation contract {field} must enable every v1 requirement")


def _covered_paths(ledger: InvestigationLedger, refs: list[str]) -> set[str]:
    paths: set[str] = set()
    for ref in refs:
        result = ledger.step_for(ref).get("result")
        if not isinstance(result, dict):
            continue
        for key in ("read_paths", "searched_scope"):
            value = result.get(key, [])
            if isinstance(value, list):
                paths.update(item for item in value if isinstance(item, str))
        matches = result.get("matches", [])
        if isinstance(matches, list):
            paths.update(item.split(":", 1)[0] for item in matches if isinstance(item, str))
    return paths
