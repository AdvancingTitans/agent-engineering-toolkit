"""Strict schema checks for Agent-proposed Candidates."""

from __future__ import annotations

from typing import Any, Mapping


class CandidateSchemaError(ValueError):
    """A Candidate is not actionable."""

    code = "NOT_ACTIONABLE"


class CandidateSchema:
    """Dependency-free strict Candidate schema."""

    REQUIRED = frozenset(
        {
            "id",
            "constraint_id",
            "strategy",
            "targets",
            "assumptions",
            "risks",
            "verification_plan",
            "finding_refs",
            "evidence_refs",
        }
    )
    OPTIONAL = frozenset(
        {
            "claim_refs",
            "deleted_paths",
            "human_approval_required",
            "root_cause_status",
        }
    )

    @classmethod
    def validate(cls, candidate_json: Mapping[str, Any]) -> None:
        if not isinstance(candidate_json, Mapping):
            raise CandidateSchemaError("NOT_ACTIONABLE: Candidate must be an object")
        missing = sorted(cls.REQUIRED - set(candidate_json))
        unknown = sorted(set(candidate_json) - cls.REQUIRED - cls.OPTIONAL)
        if missing:
            raise CandidateSchemaError(
                "NOT_ACTIONABLE: missing Candidate fields: " + ", ".join(missing)
            )
        if unknown:
            raise CandidateSchemaError(
                "NOT_ACTIONABLE: unsupported Candidate fields: " + ", ".join(unknown)
            )
        for name in ("id", "constraint_id", "strategy"):
            _nonempty_string(candidate_json[name], name)
        for name in (
            "assumptions",
            "risks",
            "verification_plan",
            "finding_refs",
            "evidence_refs",
            "claim_refs",
            "deleted_paths",
        ):
            if name in candidate_json:
                _string_list(candidate_json[name], name)
        targets = candidate_json["targets"]
        if not isinstance(targets, list) or not targets:
            raise CandidateSchemaError(
                "NOT_ACTIONABLE: targets must be a non-empty list"
            )
        for number, target in enumerate(targets):
            if not isinstance(target, Mapping) or set(target) != {"path", "symbol"}:
                raise CandidateSchemaError(
                    f"NOT_ACTIONABLE: targets[{number}] must contain exactly path and symbol"
                )
            _nonempty_string(target["path"], f"targets[{number}].path")
            _nonempty_string(target["symbol"], f"targets[{number}].symbol")
        approval = candidate_json.get("human_approval_required", False)
        if not isinstance(approval, bool):
            raise CandidateSchemaError(
                "NOT_ACTIONABLE: human_approval_required must be a boolean"
            )
        root_cause = candidate_json.get("root_cause_status")
        if root_cause is not None and root_cause not in {
            "unknown",
            "plausible",
            "evidenced",
        }:
            raise CandidateSchemaError(
                "NOT_ACTIONABLE: root_cause_status is unsupported"
            )


def _nonempty_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CandidateSchemaError(f"NOT_ACTIONABLE: {label} must be non-empty")


def _string_list(value: Any, label: str) -> None:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise CandidateSchemaError(
            f"NOT_ACTIONABLE: {label} must be a unique string list"
        )
