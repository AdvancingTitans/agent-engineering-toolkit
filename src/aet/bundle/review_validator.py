"""Validate portable reviewer references without replacing reviewer judgment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .loader import BundleError
from .validator import validate_bundle


_DISPOSITIONS = {"accept", "request_change", "request_investigation", "unknown"}
_STRONG_ENOUGH = {"corroborated", "reproduced"}


def validate_review_result(
    bundle_path: Path,
    review: Path | Mapping[str, Any],
) -> dict[str, Any]:
    """Validate IDs, counter-evidence, freshness, and strength boundaries."""
    bundle = validate_bundle(Path(bundle_path))
    result = _load_review(review)
    required = {"protocol", "bundle_id", "conclusions", "unresolved_questions"}
    missing = required - set(result)
    if missing:
        raise BundleError("invalid_review", f"review result is missing: {', '.join(sorted(missing))}")
    _allowed_keys(result, required | {"extensions"}, "review result")
    if "extensions" in result and not isinstance(result["extensions"], dict):
        raise BundleError("invalid_review", "review result.extensions must be an object")
    protocol = _object(result["protocol"], "review protocol")
    _exact_keys(protocol, {"name", "version"}, "review protocol")
    if protocol != {"name": "portable-review-result", "version": "1.0"}:
        raise BundleError("unsupported_semantics", "review protocol must be portable-review-result/1.0")
    if result["bundle_id"] != bundle["manifest"]["bundle"]["id"]:
        raise BundleError("reference_error", "review bundle_id does not match the Bundle")
    _string_list(result["unresolved_questions"], "unresolved_questions")

    claims = {item["id"]: item for item in bundle["claims"]}
    evidence = {item["id"]: item for item in bundle["evidence"]}
    conclusions = result["conclusions"]
    if not isinstance(conclusions, list) or any(not isinstance(item, dict) for item in conclusions):
        raise BundleError("invalid_review", "conclusions must be an array of objects")
    seen: set[str] = set()
    for number, conclusion in enumerate(conclusions, start=1):
        _validate_conclusion(conclusion, number)
        identifier = conclusion["id"]
        if identifier in seen:
            raise BundleError("reference_error", f"duplicate review conclusion id: {identifier}")
        seen.add(identifier)
        _validate_conclusion_grounding(conclusion, claims, evidence)

    return {
        "report_kind": "portable_review_validation",
        "status": "PASS",
        "bundle_id": result["bundle_id"],
        "conclusion_count": len(conclusions),
        "validated_conclusion_refs": [item["id"] for item in conclusions],
    }


def _validate_conclusion(
    conclusion: dict[str, Any],
    number: int,
) -> None:
    label = f"conclusion {number}"
    required = {
        "id",
        "statement",
        "disposition",
        "claim_refs",
        "evidence_refs",
        "counter_evidence_refs",
        "reasoning_summary",
        "limitations",
    }
    _allowed_keys(conclusion, required | {"next_action"}, label)
    missing = required - set(conclusion)
    if missing:
        raise BundleError("invalid_review", f"{label} is missing: {', '.join(sorted(missing))}")
    for field in ("id", "statement", "reasoning_summary"):
        _nonempty(conclusion[field], f"{label}.{field}")
    if conclusion["disposition"] not in _DISPOSITIONS:
        raise BundleError("unsupported_semantics", f"{label}.disposition is unsupported")
    for field in ("claim_refs", "evidence_refs", "counter_evidence_refs", "limitations"):
        _string_list(conclusion[field], f"{label}.{field}", unique=field != "limitations")
    if not conclusion["claim_refs"]:
        raise BundleError("invalid_review", f"{label} requires at least one Claim reference")
    if "next_action" in conclusion:
        _nonempty(conclusion["next_action"], f"{label}.next_action")


def _validate_conclusion_grounding(
    conclusion: dict[str, Any],
    claims: Mapping[str, dict[str, Any]],
    evidence: Mapping[str, dict[str, Any]],
) -> None:
    claim_refs = conclusion["claim_refs"]
    evidence_refs = conclusion["evidence_refs"]
    counter_refs = conclusion["counter_evidence_refs"]
    _known(claim_refs, claims, "review Claim")
    _known(evidence_refs, evidence, "review Evidence")
    _known(counter_refs, evidence, "review counter-evidence")
    referenced_claims = [claims[reference] for reference in claim_refs]
    allowed_support = {
        reference for claim in referenced_claims for reference in claim["evidence_refs"]
    }
    required_counter = {
        reference for claim in referenced_claims for reference in claim["counter_evidence_refs"]
    }
    if not set(evidence_refs) <= allowed_support:
        raise BundleError(
            "grounding_error",
            "review cites Evidence that does not support its referenced Claims",
        )
    if set(counter_refs) != required_counter:
        raise BundleError(
            "counter_evidence_error",
            "review must disclose all counter-evidence from its referenced Claims",
        )
    if conclusion["disposition"] in {"accept", "request_change"}:
        for claim in referenced_claims:
            cited = [
                evidence[reference]
                for reference in evidence_refs
                if reference in claim["evidence_refs"]
            ]
            if not any(
                item["strength"] in _STRONG_ENOUGH
                and item["freshness"]["status"] == "current"
                for item in cited
            ):
                raise BundleError(
                    "grounding_error",
                    (
                        "definitive review disposition requires current "
                        "corroborated or reproduced supporting Evidence for every Claim"
                    ),
                )
    if any(claim["status"] == "unknown" for claim in referenced_claims):
        if conclusion["disposition"] not in {"unknown", "request_investigation"}:
            raise BundleError("grounding_error", "unknown Claim cannot support a definitive disposition")
    if any(claim["status"] == "conflicted" for claim in referenced_claims):
        if conclusion["disposition"] == "accept":
            raise BundleError("grounding_error", "conflicted Claim cannot support acceptance")
    if conclusion["disposition"] == "accept":
        if any(claim["status"] != "supported" for claim in referenced_claims):
            raise BundleError("grounding_error", "accept requires supported Claims")


def _load_review(review: Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(review, Mapping):
        return dict(review)
    try:
        raw = Path(review).read_text(encoding="utf-8")
        value = json.loads(
            raw,
            parse_constant=lambda item: (_raise_nonfinite(item)),
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError("invalid_review", f"cannot read review result: {error}") from error
    if not isinstance(value, dict):
        raise BundleError("invalid_review", "review result must contain one JSON object")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BundleError("invalid_review", f"review result contains duplicate key: {key}")
        result[key] = value
    return result


def _raise_nonfinite(value: str) -> Any:
    raise BundleError("invalid_review", f"review result contains non-finite number: {value}")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleError("invalid_review", f"{label} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    missing = expected - set(value)
    if missing:
        raise BundleError("invalid_review", f"{label} is missing: {', '.join(sorted(missing))}")
    _allowed_keys(value, expected, label)


def _allowed_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(value) - allowed
    if extra:
        raise BundleError("invalid_review", f"{label} has unsupported fields: {', '.join(sorted(extra))}")


def _nonempty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise BundleError("invalid_review", f"{label} must be a non-empty string")


def _string_list(
    value: Any,
    label: str,
    *,
    unique: bool = False,
) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise BundleError("invalid_review", f"{label} must be an array of non-empty strings")
    if unique and len(set(value)) != len(value):
        raise BundleError("invalid_review", f"{label} must contain unique values")


def _known(
    references: list[str],
    records: Mapping[str, dict[str, Any]],
    label: str,
) -> None:
    missing = sorted(set(references) - set(records))
    if missing:
        raise BundleError("reference_error", f"unknown {label} IDs: {', '.join(missing)}")
