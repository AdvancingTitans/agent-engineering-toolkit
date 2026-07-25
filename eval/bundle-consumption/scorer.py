#!/usr/bin/env python3
"""Deterministically score one Portable Bundle and structured Review Result."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from aet.bundle import validate_bundle


STATUSES = {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
METRIC_NAMES = (
    "citation_correctness",
    "observation_evidence_distinction",
    "counter_evidence_retention",
    "unknown_preservation",
    "freshness_handling",
    "unsupported_conclusion_rate",
    "missing_evidence_overreach_rate",
    "relevant_evidence_recall",
    "context_tokens",
    "time_to_first_grounded_conclusion",
)
DECISIVE = {"accept", "request_change"}
STRONG = {"corroborated", "reproduced"}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"invalid JSON constant: {value}")
        ),
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _metric(status: str, **values: Any) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"unsupported metric status: {status}")
    return {"status": status, **values}


def _rate_metric(passed: int, total: int, *, explanation: str) -> dict[str, Any]:
    if total == 0:
        return _metric(
            "NOT_APPLICABLE",
            passed=0,
            total=0,
            rate=None,
            explanation=explanation,
        )
    return _metric(
        "PASS" if passed == total else "FAIL",
        passed=passed,
        total=total,
        rate=passed / total,
        explanation=explanation,
    )


def _failure_rate_metric(
    failed: int,
    total: int,
    *,
    explanation: str,
) -> dict[str, Any]:
    if total == 0:
        return _metric(
            "NOT_APPLICABLE",
            failed=0,
            total=0,
            rate=None,
            explanation=explanation,
        )
    return _metric(
        "PASS" if failed == 0 else "FAIL",
        failed=failed,
        total=total,
        rate=failed / total,
        explanation=explanation,
    )


def _not_applicable_metrics(reason: str) -> dict[str, dict[str, Any]]:
    return {
        name: _metric("NOT_APPLICABLE", explanation=reason)
        for name in METRIC_NAMES
    }


def _validate_review_shape(review: dict[str, Any]) -> list[dict[str, Any]]:
    protocol = review.get("protocol")
    if (
        not isinstance(protocol, dict)
        or protocol.get("name") != "portable-review-result"
        or protocol.get("version") != "1.0"
    ):
        raise ValueError("review protocol must be portable-review-result/1.0")
    conclusions = review.get("conclusions")
    if not isinstance(conclusions, list) or any(
        not isinstance(item, dict) for item in conclusions
    ):
        raise ValueError("review conclusions must be an array of objects")
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
    for conclusion in conclusions:
        if not required <= set(conclusion):
            raise ValueError("review conclusion is missing required fields")
        for field in ("claim_refs", "evidence_refs", "counter_evidence_refs"):
            refs = conclusion[field]
            if not isinstance(refs, list) or any(
                not isinstance(item, str) or not item for item in refs
            ):
                raise ValueError(f"review conclusion {field} must contain strings")
        if conclusion["disposition"] not in {
            "accept",
            "request_change",
            "request_investigation",
            "unknown",
        }:
            raise ValueError("review conclusion disposition is invalid")
    return conclusions


def _is_grounded(
    conclusion: dict[str, Any],
    claims: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> bool:
    claim_refs = conclusion["claim_refs"]
    if not claim_refs or any(reference not in claims for reference in claim_refs):
        return False
    cited = [
        evidence[reference]
        for reference in conclusion["evidence_refs"]
        if reference in evidence
    ]
    if len(cited) != len(conclusion["evidence_refs"]):
        return False
    if conclusion["disposition"] not in DECISIVE:
        return True
    for claim_ref in claim_refs:
        if not any(
            claim_ref in item["supports"]
            and item["strength"] in STRONG
            and item["freshness"]["status"] == "current"
            for item in cited
        ):
            return False
    return True


def _estimate_context_tokens(
    bundle: dict[str, Any],
    review: dict[str, Any],
) -> tuple[int, int]:
    projection = {
        "manifest": bundle["manifest"],
        "index": bundle["index"],
        "claims": bundle["claims"],
        "evidence": bundle["evidence"],
        "observations": bundle["observations"],
        "review": review,
    }
    raw = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return len(raw), math.ceil(len(raw) / 4)


def evaluate(
    bundle_path: Path | None,
    review: dict[str, Any] | None,
    *,
    scenario_id: str,
    consumer_id: str,
    expected_relevant_evidence_refs: list[str] | None = None,
    consumer_available: bool = True,
) -> dict[str, Any]:
    """Return independent metrics; intentionally no aggregate score."""
    if not consumer_available:
        return {
            "schema_version": "bundle-consumption-evaluation/v1",
            "report_kind": "bundle_consumption_evaluation",
            "scenario_id": scenario_id,
            "consumer_id": consumer_id,
            "consumer_status": "NOT_APPLICABLE",
            "metrics": _not_applicable_metrics(
                "The declared consumer or its structured output is unavailable."
            ),
            "method": {
                "external_agent_calls": 0,
                "aggregate_score": False,
            },
            "limitations": [
                "No conclusion about an unavailable third-party consumer is inferred."
            ],
        }
    if bundle_path is None or review is None:
        raise ValueError("available evaluation requires a Bundle and Review Result")

    bundle = validate_bundle(bundle_path)
    if review.get("bundle_id") != bundle["manifest"]["bundle"]["id"]:
        raise ValueError("review bundle_id does not match the evaluated Bundle")
    conclusions = _validate_review_shape(review)
    claims = {item["id"]: item for item in bundle["claims"]}
    evidence = {item["id"]: item for item in bundle["evidence"]}
    observations = {item["id"]: item for item in bundle["observations"]}

    citation_pairs = [
        *(("claim", ref) for item in conclusions for ref in item["claim_refs"]),
        *(("evidence", ref) for item in conclusions for ref in item["evidence_refs"]),
        *(("evidence", ref) for item in conclusions for ref in item["counter_evidence_refs"]),
    ]
    valid_citations = sum(
        reference in (claims if kind == "claim" else evidence)
        for kind, reference in citation_pairs
    )
    citation = _rate_metric(
        valid_citations,
        len(citation_pairs),
        explanation="References must resolve to the declared record kind.",
    )

    evidence_role_refs = [
        reference
        for item in conclusions
        for reference in [
            *item["evidence_refs"],
            *item["counter_evidence_refs"],
        ]
    ]
    role_correct = sum(reference in evidence for reference in evidence_role_refs)
    distinction = _rate_metric(
        role_correct,
        len(evidence_role_refs),
        explanation=(
            "Observation IDs cannot be presented in Evidence or counter-evidence roles."
        ),
    )
    distinction["observation_ids_misused"] = sorted(
        {reference for reference in evidence_role_refs if reference in observations}
    )

    required_counters: set[str] = set()
    cited_counters: set[str] = set()
    for conclusion in conclusions:
        for claim_ref in conclusion["claim_refs"]:
            if claim_ref in claims:
                required_counters.update(claims[claim_ref]["counter_evidence_refs"])
        cited_counters.update(conclusion["counter_evidence_refs"])
    retained = required_counters & cited_counters
    counter = _rate_metric(
        len(retained),
        len(required_counters),
        explanation="Every counter-evidence reference declared by cited Claims must remain visible.",
    )
    counter["missing_refs"] = sorted(required_counters - cited_counters)

    unknown_cases = [
        conclusion
        for conclusion in conclusions
        if any(
            claims.get(reference, {}).get("status") == "unknown"
            for reference in conclusion["claim_refs"]
        )
    ]
    preserved_unknown = sum(
        item["disposition"] in {"request_investigation", "unknown"}
        for item in unknown_cases
    )
    unknown = _rate_metric(
        preserved_unknown,
        len(unknown_cases),
        explanation="Unknown Claims cannot be strengthened into a decisive disposition.",
    )

    freshness_cases = [
        (conclusion, evidence[reference])
        for conclusion in conclusions
        for reference in conclusion["evidence_refs"]
        if reference in evidence
    ]
    safe_freshness = sum(
        conclusion["disposition"] not in DECISIVE
        or item["freshness"]["status"] == "current"
        for conclusion, item in freshness_cases
    )
    freshness = _rate_metric(
        safe_freshness,
        len(freshness_cases),
        explanation="A decisive conclusion cannot rely on non-current Evidence.",
    )

    decisive = [item for item in conclusions if item["disposition"] in DECISIVE]
    unsupported_ids = [
        item["id"] for item in decisive if not _is_grounded(item, claims, evidence)
    ]
    unsupported = _failure_rate_metric(
        len(unsupported_ids),
        len(decisive),
        explanation=(
            "Each decisive Claim requires cited, current, corroborated or reproduced Evidence."
        ),
    )
    unsupported["unsupported_count"] = len(unsupported_ids)
    unsupported["unsupported_conclusion_ids"] = unsupported_ids

    missing_basis_cases = [
        conclusion
        for conclusion in conclusions
        if any(
            reference in claims
            and (
                claims[reference]["status"] == "unknown"
                or not claims[reference]["evidence_refs"]
            )
            for reference in conclusion["claim_refs"]
        )
    ]
    overreach_ids = [
        item["id"]
        for item in missing_basis_cases
        if item["disposition"] in DECISIVE
    ]
    overreach = _failure_rate_metric(
        len(overreach_ids),
        len(missing_basis_cases),
        explanation="Missing evidence must not be converted into a decisive conclusion.",
    )
    overreach["overreach_count"] = len(overreach_ids)
    overreach["overreach_conclusion_ids"] = overreach_ids

    if expected_relevant_evidence_refs is None:
        recall = _metric(
            "UNKNOWN",
            recalled=0,
            expected=None,
            rate=None,
            explanation="No expected relevant Evidence annotation was supplied.",
        )
    else:
        expected = set(expected_relevant_evidence_refs)
        cited = {
            reference
            for item in conclusions
            for reference in [
                *item["evidence_refs"],
                *item["counter_evidence_refs"],
            ]
        }
        recall = _rate_metric(
            len(expected & cited),
            len(expected),
            explanation="Expected relevant Evidence IDs cited by the Review Result.",
        )
        recall["missing_refs"] = sorted(expected - cited)

    context_bytes, token_estimate = _estimate_context_tokens(bundle, review)
    context = _metric(
        "PASS",
        estimated_tokens=token_estimate,
        utf8_bytes=context_bytes,
        explanation=(
            "Approximation: ceil(UTF-8 bytes of canonical Bundle Index/Core plus Review JSON / 4)."
        ),
    )

    timings = (
        review.get("extensions", {})
        .get("evaluation", {})
        .get("conclusion_elapsed_seconds")
    )
    grounded_ids = {
        item["id"]
        for item in conclusions
        if _is_grounded(item, claims, evidence)
    }
    if not isinstance(timings, dict):
        first_grounded = _metric(
            "UNKNOWN",
            seconds=None,
            conclusion_id=None,
            explanation="No measured conclusion timing was supplied.",
        )
    else:
        candidates = [
            (seconds, identifier)
            for identifier, seconds in timings.items()
            if identifier in grounded_ids
            and isinstance(seconds, (int, float))
            and not isinstance(seconds, bool)
            and math.isfinite(seconds)
            and seconds >= 0
        ]
        if candidates:
            seconds, identifier = min(candidates)
            first_grounded = _metric(
                "PASS",
                seconds=seconds,
                conclusion_id=identifier,
                explanation="Minimum measured elapsed time among grounded conclusions.",
            )
        else:
            first_grounded = _metric(
                "UNKNOWN",
                seconds=None,
                conclusion_id=None,
                explanation="No grounded conclusion has a measured elapsed time.",
            )

    return {
        "schema_version": "bundle-consumption-evaluation/v1",
        "report_kind": "bundle_consumption_evaluation",
        "scenario_id": scenario_id,
        "consumer_id": consumer_id,
        "consumer_status": "AVAILABLE",
        "bundle_id": bundle["manifest"]["bundle"]["id"],
        "metrics": {
            "citation_correctness": citation,
            "observation_evidence_distinction": distinction,
            "counter_evidence_retention": counter,
            "unknown_preservation": unknown,
            "freshness_handling": freshness,
            "unsupported_conclusion_rate": unsupported,
            "missing_evidence_overreach_rate": overreach,
            "relevant_evidence_recall": recall,
            "context_tokens": context,
            "time_to_first_grounded_conclusion": first_grounded,
        },
        "method": {
            "external_agent_calls": 0,
            "aggregate_score": False,
            "token_estimation": "ceil(canonical UTF-8 bytes / 4)",
        },
        "limitations": [
            "Metrics describe only the supplied Bundle, Review Result, and annotations.",
            "No metric authorizes merge, release, or trust.",
        ],
    }
