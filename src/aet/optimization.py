"""Deterministic Phase 7 entry for evidence-backed optimization candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .bundle import BundleError, validate_bundle, validate_review_result


_TARGETS = {
    "source_adapter",
    "observation_extractor",
    "investigation_policy",
    "tool_selection",
    "bundle_selector",
    "consumer_guide",
    "grounding_validator",
}
_HIGH_SEVERITIES = {"high", "critical"}
_DETERMINISTIC_BASIS = {"deterministic", "reproduced"}
_STRONG_EVIDENCE = {"corroborated", "reproduced"}
_SUPPORT_KEYS = {"bundle_path", "review", "review_refs", "run_refs"}
_FAILURE_KEYS = {
    "severity",
    "bundle_ref",
    "review_ref",
    "claim_ref",
    "evidence_refs",
}


class OptimizationCandidateError(ValueError):
    """Raised when evidence cannot qualify an OptimizationCandidate."""


def build_optimization_candidate(
    *,
    candidate_id: str,
    target: str,
    observed_problem: str,
    supporting_inputs: Sequence[Mapping[str, Any]],
    proposed_change: str,
    expected_effect: str,
    possible_regression: str,
    deterministic_failure: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build, but never apply, one Phase 7 OptimizationCandidate.

    Each supporting input must name an already portable Bundle directory, a
    Portable Review Result, and the exact review/run IDs to retain. Existing
    validators are the authority for both inputs. Qualification requires
    multiple independent task IDs or one explicitly cited high/critical
    deterministic failure.
    """
    _nonempty(candidate_id, "candidate_id")
    if target not in _TARGETS:
        raise OptimizationCandidateError(f"unsupported target: {target!r}")
    _nonempty(observed_problem, "observed_problem")
    _nonempty(proposed_change, "proposed_change")
    _nonempty(expected_effect, "expected_effect")
    _nonempty(possible_regression, "possible_regression")
    if not isinstance(supporting_inputs, Sequence) or isinstance(
        supporting_inputs, (str, bytes)
    ):
        raise OptimizationCandidateError("supporting_inputs must be a sequence")
    if not supporting_inputs:
        raise OptimizationCandidateError("at least one supporting input is required")

    task_ids: set[str] = set()
    bundle_refs: set[str] = set()
    run_refs: set[str] = set()
    review_refs: set[str] = set()
    verified: dict[str, dict[str, Any]] = {}

    for number, item in enumerate(supporting_inputs, start=1):
        if not isinstance(item, Mapping):
            raise OptimizationCandidateError(
                f"supporting input {number} must be an object"
            )
        _exact_keys(item, _SUPPORT_KEYS, f"supporting input {number}")
        bundle_path = Path(item["bundle_path"])
        review = item["review"]
        selected_reviews = _string_list(
            item["review_refs"],
            f"supporting input {number}.review_refs",
            nonempty=True,
        )
        selected_runs = _string_list(
            item["run_refs"],
            f"supporting input {number}.run_refs",
        )

        bundle = validate_bundle(bundle_path)
        review_report = validate_review_result(bundle_path, review)
        review_value = _load_review(review)
        bundle_id = bundle["manifest"]["bundle"]["id"]
        task_id = bundle["manifest"]["task"]["task_id"]
        conclusions = {item["id"]: item for item in review_value["conclusions"]}
        sources = {item["id"]: item for item in bundle["sources"]}

        missing_reviews = sorted(set(selected_reviews) - set(conclusions))
        if missing_reviews:
            raise OptimizationCandidateError(
                "unknown review conclusion IDs: " + ", ".join(missing_reviews)
            )
        if set(selected_reviews) - set(review_report["validated_conclusion_refs"]):
            raise OptimizationCandidateError("review references were not validated")

        missing_runs = sorted(set(selected_runs) - set(sources))
        if missing_runs:
            raise OptimizationCandidateError(
                "unknown run source IDs: " + ", ".join(missing_runs)
            )
        wrong_source_type = sorted(
            reference
            for reference in selected_runs
            if sources[reference]["type"] != "run_record"
        )
        if wrong_source_type:
            raise OptimizationCandidateError(
                "supportingRunRefs must cite run_record Sources: "
                + ", ".join(wrong_source_type)
            )

        if bundle_id in verified:
            raise OptimizationCandidateError(
                f"duplicate supporting Bundle ID: {bundle_id}"
            )
        verified[bundle_id] = {
            "bundle": bundle,
            "conclusions": conclusions,
            "selected_reviews": set(selected_reviews),
        }
        task_ids.add(task_id)
        bundle_refs.add(bundle_id)
        review_refs.update(
            f"{bundle_id}#review-conclusion:{reference}"
            for reference in selected_reviews
        )
        run_refs.update(
            f"{bundle_id}#run-record:{reference}" for reference in selected_runs
        )

    deterministic_failure_valid = False
    if deterministic_failure is not None:
        deterministic_failure_valid = _validate_deterministic_failure(
            deterministic_failure,
            verified,
        )
    if len(task_ids) < 2 and not deterministic_failure_valid:
        raise OptimizationCandidateError(
            "candidate requires multiple independent task IDs or an explicit "
            "high/critical deterministic failure"
        )

    # Plan §13 Phase 7: this function only emits an evaluation candidate.
    # It never edits a Skill, policy, source adapter, or other production asset.
    return {
        "id": candidate_id,
        "target": target,
        "observedProblem": observed_problem,
        "supportingRunRefs": sorted(run_refs),
        "supportingBundleRefs": sorted(bundle_refs),
        "supportingReviewRefs": sorted(review_refs),
        "proposedChange": proposed_change,
        "expectedEffect": expected_effect,
        "possibleRegression": possible_regression,
        "evaluationRequired": True,
    }


def _validate_deterministic_failure(
    failure: Mapping[str, Any],
    verified: Mapping[str, dict[str, Any]],
) -> bool:
    if not isinstance(failure, Mapping):
        raise OptimizationCandidateError("deterministic_failure must be an object")
    _exact_keys(failure, _FAILURE_KEYS, "deterministic_failure")
    if failure["severity"] not in _HIGH_SEVERITIES:
        raise OptimizationCandidateError(
            "deterministic failure severity must be high or critical"
        )
    for field in ("bundle_ref", "review_ref", "claim_ref"):
        _nonempty(failure[field], f"deterministic_failure.{field}")
    evidence_refs = _string_list(
        failure["evidence_refs"],
        "deterministic_failure.evidence_refs",
        nonempty=True,
    )

    bundle_ref = failure["bundle_ref"]
    support = verified.get(bundle_ref)
    if support is None:
        raise OptimizationCandidateError(
            "deterministic failure cites an unsupported Bundle"
        )
    review_ref = failure["review_ref"]
    if review_ref not in support["selected_reviews"]:
        raise OptimizationCandidateError(
            "deterministic failure review_ref was not selected as support"
        )
    conclusion = support["conclusions"][review_ref]
    if conclusion["disposition"] != "request_change":
        raise OptimizationCandidateError(
            "deterministic failure requires a request_change review conclusion"
        )

    bundle = support["bundle"]
    claims = {item["id"]: item for item in bundle["claims"]}
    evidence = {item["id"]: item for item in bundle["evidence"]}
    claim_ref = failure["claim_ref"]
    claim = claims.get(claim_ref)
    if claim is None or claim_ref not in conclusion["claim_refs"]:
        raise OptimizationCandidateError(
            "deterministic failure claim_ref is not grounded by the review"
        )
    if claim["basis"]["type"] not in _DETERMINISTIC_BASIS:
        raise OptimizationCandidateError(
            "deterministic failure requires deterministic or reproduced Claim basis"
        )
    if not set(evidence_refs) <= set(conclusion["evidence_refs"]):
        raise OptimizationCandidateError(
            "deterministic failure Evidence must be cited by the review"
        )
    if not set(evidence_refs) <= set(claim["evidence_refs"]):
        raise OptimizationCandidateError(
            "deterministic failure Evidence must support the cited Claim"
        )
    for reference in evidence_refs:
        item = evidence[reference]
        if (
            item["kind"] == "run_observation"
            or item["strength"] not in _STRONG_EVIDENCE
            or item["freshness"]["status"] != "current"
        ):
            raise OptimizationCandidateError(
                "deterministic failure requires current corroborated or "
                "reproduced non-observational Evidence"
            )
    return True


def _load_review(review: Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(review, Mapping):
        return dict(review)
    try:
        value = json.loads(Path(review).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError(
            "invalid_review",
            f"cannot read review result: {error}",
        ) from error
    if not isinstance(value, dict):
        raise BundleError(
            "invalid_review",
            "review result must contain one JSON object",
        )
    return value


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    label: str,
) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing:
        raise OptimizationCandidateError(
            f"{label} is missing: {', '.join(sorted(missing))}"
        )
    if extra:
        raise OptimizationCandidateError(
            f"{label} has unsupported fields: {', '.join(sorted(extra))}"
        )


def _nonempty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise OptimizationCandidateError(f"{label} must be a non-empty string")


def _string_list(
    value: Any,
    label: str,
    *,
    nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise OptimizationCandidateError(
            f"{label} must be an array of non-empty strings"
        )
    if len(set(value)) != len(value):
        raise OptimizationCandidateError(f"{label} must contain unique values")
    if nonempty and not value:
        raise OptimizationCandidateError(f"{label} must not be empty")
    return value
