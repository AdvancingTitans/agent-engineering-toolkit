"""Question-bounded record selection for Portable Evidence Bundle compilation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from .loader import BundleError


def select_records(
    payload: Mapping[str, Any],
    claim_refs: Sequence[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Select Claims and their transitive evidence provenance.

    This is the plan's Index/Core/Archive boundary: a Bundle contains the
    records needed for one declared investigation question, not an entire run.
    """
    collections = {
        name: _records(payload.get(name), name)
        for name in (
            "claims",
            "evidence",
            "observations",
            "sources",
            "diagnostics",
            "conflicts",
            "ledger",
        )
    }
    claims_by_id = _by_id(collections["claims"], "claims")
    selected_claim_ids = (
        list(claims_by_id)
        if claim_refs is None
        else _unique_strings(claim_refs, "claim_refs")
    )
    unknown = sorted(set(selected_claim_ids) - set(claims_by_id))
    if unknown:
        raise BundleError("reference_error", "unknown selected Claim IDs: " + ", ".join(unknown))

    claims = [deepcopy(claims_by_id[identifier]) for identifier in selected_claim_ids]
    declared_evidence_ids = {
        reference
        for claim in claims
        for field in ("evidence_refs", "counter_evidence_refs")
        for reference in _string_refs(claim.get(field), f"claim.{field}")
    }
    evidence_by_id = _by_id(collections["evidence"], "evidence")
    reverse_evidence_ids = {
        identifier
        for identifier, record in evidence_by_id.items()
        if set(_string_refs(record.get("supports"), "evidence.supports")) & set(selected_claim_ids)
        or set(_string_refs(record.get("contradicts"), "evidence.contradicts"))
        & set(selected_claim_ids)
    }
    evidence_ids = declared_evidence_ids | reverse_evidence_ids
    observation_ids = {
        reference
        for claim in claims
        for reference in _string_refs(claim.get("observation_refs"), "claim.observation_refs")
    }
    observations_by_id = _by_id(collections["observations"], "observations")
    evidence = _resolve(evidence_ids, evidence_by_id, "Evidence")
    observations = _resolve(observation_ids, observations_by_id, "Observation")

    source_ids = {
        reference
        for record in [*evidence, *observations]
        for reference in _string_refs(record.get("source_refs"), "record.source_refs")
    }
    conflicts = [
        deepcopy(record)
        for record in collections["conflicts"]
        if set(_string_refs(record.get("evidence_refs"), "conflict.evidence_refs"))
        <= evidence_ids
        and set(record["evidence_refs"]) & evidence_ids
    ]
    diagnostics = [
        deepcopy(record)
        for record in collections["diagnostics"]
        if (
            set(
                _string_refs(
                    record.get("affected_observation_refs"),
                    "diagnostic.affected_observation_refs",
                )
            )
            & observation_ids
        )
        or (
            set(
                _string_refs(
                    record.get("affected_evidence_refs"),
                    "diagnostic.affected_evidence_refs",
                )
            )
            & evidence_ids
        )
    ]
    if claim_refs is None:
        ledger = [deepcopy(record) for record in collections["ledger"]]
        source_ids.update(
            record["input_ref"]
            for record in ledger
            if isinstance(record.get("input_ref"), str)
        )
    else:
        known_outputs = evidence_ids | observation_ids | source_ids
        ledger = [
            deepcopy(record)
            for record in collections["ledger"]
            if (
                set(_string_refs(record.get("observation_refs"), "ledger.observation_refs"))
                & observation_ids
            )
            or record.get("input_ref") in source_ids
            or record.get("output_ref") in known_outputs
        ]
    sources = _resolve(source_ids, _by_id(collections["sources"], "sources"), "Source")
    return {
        "claims": claims,
        "evidence": evidence,
        "observations": observations,
        "sources": sources,
        "diagnostics": diagnostics,
        "conflicts": conflicts,
        "ledger": ledger,
    }


def excluded_record_count(
    payload: Mapping[str, Any],
    selected: Mapping[str, list[dict[str, Any]]],
) -> int:
    """Return the number of records omitted by the question slice."""
    return sum(
        max(0, len(_records(payload.get(name), name)) - len(selected[name]))
        for name in selected
    )


def _records(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise BundleError("invalid_bundle", f"{label} must be an array of objects")
    return value


def _by_id(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise BundleError("invalid_bundle", f"{label} record requires a non-empty id")
        if identifier in result:
            raise BundleError("reference_error", f"duplicate {label} id: {identifier}")
        result[identifier] = record
    return result


def _resolve(
    identifiers: set[str],
    records: Mapping[str, dict[str, Any]],
    label: str,
) -> list[dict[str, Any]]:
    missing = sorted(identifiers - set(records))
    if missing:
        raise BundleError("reference_error", f"unknown {label} IDs: " + ", ".join(missing))
    return [deepcopy(records[identifier]) for identifier in records if identifier in identifiers]


def _string_refs(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise BundleError("invalid_bundle", f"{label} must be an array of non-empty strings")
    return value


def _unique_strings(value: Sequence[str], label: str) -> list[str]:
    result = list(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise BundleError("invalid_bundle", f"{label} must contain non-empty strings")
    if len(set(result)) != len(result):
        raise BundleError("invalid_bundle", f"{label} must contain unique values")
    return result
