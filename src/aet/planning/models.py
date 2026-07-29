"""Dependency-free data models and canonical serialization for Planning v1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Mapping

from .errors import PlanningError, PlanningErrorCode


class PlanStatus(StrEnum):
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    SUPERSEDED = "SUPERSEDED"


class CoverageClaim(StrEnum):
    BOUNDED_COMPLETE = "BOUNDED_COMPLETE"
    BEST_EFFORT = "BEST_EFFORT"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class EditDisposition(StrEnum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    INVESTIGATE = "INVESTIGATE"
    DO_NOT_EDIT = "DO_NOT_EDIT"


class ReferenceStrength(StrEnum):
    EVIDENCE_BACKED = "EVIDENCE_BACKED"
    SOURCE_CONFIRMED = "SOURCE_CONFIRMED"
    INFERRED_WITH_LIMITS = "INFERRED_WITH_LIMITS"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LineRange:
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.start_line, bool)
            or isinstance(self.end_line, bool)
            or self.start_line < 1
            or self.end_line < self.start_line
        ):
            raise PlanningError(
                PlanningErrorCode.INVALID_CANDIDATE,
                "line ranges require 1 <= start_line <= end_line",
            )


@dataclass(frozen=True)
class WorkspaceIdentity:
    status: str
    workspace_id: str
    head_sha: str | None
    worktree_digest: str | None


@dataclass(frozen=True)
class PlanningBudgets:
    max_nodes: int = 10_000
    max_source_files: int = 200
    max_source_bytes: int = 2_000_000
    max_edit_items: int = 100
    max_depth: int = 4

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PlanningError(
                    PlanningErrorCode.INVALID_REQUEST,
                    f"budget {name} must be a non-negative integer",
                )


@dataclass(frozen=True)
class PlanningRequest:
    schema_version: str
    request_id: str
    user_goal: str
    acceptance_criteria: list[str]
    non_goals: list[str]
    allowed_paths: list[str]
    protected_paths: list[str]
    required_verification: list[str]
    bundle_identity: str | None
    atlas_identity: str | None
    workspace_identity: WorkspaceIdentity
    budgets: PlanningBudgets
    requested_output: str = "plan"
    high_risk_claims: list[str] = field(default_factory=list)
    allowed_scope_status: str = "UNRESOLVED"

    def __post_init__(self) -> None:
        if self.schema_version != "planning-request/1.0":
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "unsupported Planning Request schema version",
            )
        if not self.request_id or not self.user_goal.strip():
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "request_id and user_goal are required",
            )
        if self.requested_output not in {"plan", "explain", "gaps", "skill"}:
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "requested_output is unsupported",
            )
        if self.allowed_scope_status not in {"RESOLVED", "UNRESOLVED"}:
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "allowed_scope_status is unsupported",
            )


@dataclass(frozen=True)
class SourceSite:
    source_id: str
    path: str
    symbol: str | None
    start_line: int | None
    end_line: int | None
    content_hash: str
    language: str
    role: str
    read_status: str
    reference_ids: list[str]

    def __post_init__(self) -> None:
        canonical_relative_path(self.path)
        if self.role not in {
            "ENTRYPOINT",
            "IMPLEMENTATION",
            "CALLER",
            "CALLEE",
            "SCHEMA",
            "CONFIG",
            "TEST",
            "DOC",
            "GENERATED",
            "UNKNOWN",
        }:
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "Source Site role is unsupported",
            )
        if self.read_status not in {"CONFIRMED", "STALE", "MISSING", "UNSUPPORTED"}:
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "Source Site read_status is unsupported",
            )
        if len(self.content_hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.content_hash
        ):
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "Source Site content_hash must be SHA-256",
            )
        if (self.start_line is None) != (self.end_line is None):
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "Source Site line range must be complete or absent",
            )
        if self.start_line is not None:
            LineRange(self.start_line, self.end_line)


@dataclass(frozen=True)
class PlanningConstraints:
    allowed_paths: list[str]
    protected_paths: list[str]
    read_only: bool = True
    execution_allowed: bool = False
    write_allowed: bool = False
    scope_status: str = "UNRESOLVED"

    def __post_init__(self) -> None:
        if not self.read_only or self.execution_allowed or self.write_allowed:
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "Planning constraints must remain read-only and non-executing",
            )
        if self.scope_status not in {"RESOLVED", "UNRESOLVED"}:
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "Planning scope status is unsupported",
            )


@dataclass(frozen=True)
class PlanningGap:
    gap_id: str
    code: str
    severity: str
    message: str
    critical: bool
    reference_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OmissionSummary:
    nodes: int = 0
    source_ranges: int = 0
    source_bytes: int = 0

    @property
    def total(self) -> int:
        return self.nodes + self.source_ranges + self.source_bytes


@dataclass(frozen=True)
class PlanningContext:
    schema_version: str
    request: PlanningRequest
    workspace: WorkspaceIdentity
    relevant_claims: list[dict[str, Any]]
    relevant_evidence: list[dict[str, Any]]
    counter_evidence: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    unknowns: list[dict[str, Any]]
    atlas_nodes: list[dict[str, Any]]
    source_sites: list[SourceSite]
    candidate_relations: list[dict[str, Any]]
    constraints: PlanningConstraints
    gaps: list[PlanningGap]
    omitted: OmissionSummary
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.schema_version != "planning-context/1.0":
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                "unsupported Planning Context schema version",
            )


@dataclass(frozen=True)
class EditItemCandidate:
    edit_id: str
    disposition: str
    path: str
    symbol: str | None
    source_range: LineRange | None
    intent: str
    expected_change: str
    rationale: str
    behavior_links: list[str]
    evidence_refs: list[str]
    atlas_refs: list[str]
    source_refs: list[str]
    dependencies: list[str]
    tests: list[str]
    risks: list[str]
    limitations: list[str]


@dataclass(frozen=True)
class VerificationStep:
    verification_id: str
    description: str
    command: list[str] | None
    edit_refs: list[str]
    expected_result: str
    status: str = "PENDING"


@dataclass(frozen=True)
class PlanCandidate:
    schema_version: str
    request_id: str
    summary: str
    coverage_claim: str
    edit_items: list[EditItemCandidate]
    investigation_items: list[dict[str, Any]]
    verification_steps: list[VerificationStep]
    assumptions: list[dict[str, Any]]
    unresolved: list[dict[str, Any]]


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    edit_id: str | None = None
    reference_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationResult:
    plan: dict[str, Any]
    diagnostics: list[Diagnostic]

    @property
    def status(self) -> str:
        return str(self.plan["status"])


def canonical_relative_path(value: str) -> str:
    """Return one canonical repository-relative POSIX path or fail closed."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise PlanningError(
            PlanningErrorCode.PATH_ESCAPE,
            "path must be a non-empty repository-relative POSIX path",
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PlanningError(
            PlanningErrorCode.PATH_ESCAPE,
            "path must be canonical and repository-relative",
        )
    return value


def canonicalize_model(value: Any) -> dict[str, Any]:
    """Convert one dataclass model into a stable JSON-compatible object."""
    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError("canonicalize_model requires a dataclass instance")
    converted = _json_value(asdict(value))
    if not isinstance(converted, dict):
        raise TypeError("model must serialize to one object")
    return converted


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def stable_request_id(user_goal: str, workspace: WorkspaceIdentity) -> str:
    payload = {"user_goal": user_goal.strip(), "workspace": canonicalize_model(workspace)}
    return "REQ-" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:16].upper()


def stable_plan_id(
    request: PlanningRequest,
    workspace: WorkspaceIdentity,
    bundle_identity: str | None,
) -> str:
    payload = {
        "request": canonicalize_model(request),
        "workspace": canonicalize_model(workspace),
        "bundle_identity": bundle_identity,
    }
    return "PLAN-" + hashlib.sha256(canonical_json_bytes(payload)).hexdigest()[:16].upper()


def model_from_mapping(cls: type[Any], value: Mapping[str, Any]) -> Any:
    """Construct supported nested models from a validated mapping."""
    data = dict(value)
    if cls is PlanningRequest:
        data["workspace_identity"] = WorkspaceIdentity(**data["workspace_identity"])
        data["budgets"] = PlanningBudgets(**data["budgets"])
    elif cls is PlanningContext:
        data["request"] = model_from_mapping(PlanningRequest, data["request"])
        data["workspace"] = WorkspaceIdentity(**data["workspace"])
        data["source_sites"] = [SourceSite(**item) for item in data["source_sites"]]
        data["constraints"] = PlanningConstraints(**data["constraints"])
        data["gaps"] = [PlanningGap(**item) for item in data["gaps"]]
        omission = dict(data["omitted"])
        omission.pop("total", None)
        data["omitted"] = OmissionSummary(**omission)
    return cls(**data)


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
