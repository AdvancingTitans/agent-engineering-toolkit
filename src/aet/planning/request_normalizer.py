"""Deterministic normalization for natural-language Planning requests."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from aet.evidence import workspace_snapshot

from .errors import PlanningError, PlanningErrorCode
from .models import (
    PlanningBudgets,
    PlanningRequest,
    WorkspaceIdentity,
    canonical_relative_path,
    stable_request_id,
)


_RISK_TERMS = (
    "all",
    "every",
    "complete",
    "completely",
    "guarantee",
    "ensure no omissions",
    "全部",
    "所有",
    "彻底",
    "保证",
    "确保没有遗漏",
)
_PATH_LINE = re.compile(
    r"^\s*(allowed paths?|允许路径|protected paths?|保护路径)\s*[:：]\s*(.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RequestOverrides:
    acceptance_criteria: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)
    protected_paths: list[str] = field(default_factory=list)
    required_verification: list[str] = field(default_factory=list)
    bundle_identity: str | None = None
    atlas_identity: str | None = None
    budgets: PlanningBudgets | None = None
    requested_output: str = "plan"


def normalize_request(
    raw_text: str,
    *,
    workspace: Path,
    explicit: RequestOverrides | None = None,
) -> PlanningRequest:
    """Normalize user text without treating it as policy or executed work."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "user_goal must be a non-empty string",
        )
    if len(raw_text.encode("utf-8")) > 100_000:
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "user_goal exceeds the request byte budget",
        )
    root = Path(workspace).resolve(strict=True)
    if not root.is_dir():
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "workspace must be a directory",
        )
    overrides = explicit or RequestOverrides()
    declared_allowed, declared_protected = _declared_paths(raw_text)
    allowed = _normalize_patterns([*declared_allowed, *overrides.allowed_paths])
    protected = _normalize_patterns(
        [*declared_protected, *overrides.protected_paths]
    )
    snapshot = workspace_snapshot(root)
    status = str(snapshot.get("status", "UNKNOWN"))
    digest = snapshot.get("digest")
    head = snapshot.get("head_sha")
    workspace_id = (
        str(digest)
        if isinstance(digest, str) and digest
        else "workspace-unknown"
    )
    identity = WorkspaceIdentity(
        status=status,
        workspace_id=workspace_id,
        head_sha=head if isinstance(head, str) else None,
        worktree_digest=(
            snapshot.get("worktree_digest")
            if isinstance(snapshot.get("worktree_digest"), str)
            else None
        ),
    )
    goal = raw_text.strip()
    return PlanningRequest(
        schema_version="planning-request/1.0",
        request_id=stable_request_id(goal, identity),
        user_goal=goal,
        acceptance_criteria=_unique(overrides.acceptance_criteria),
        non_goals=_unique(overrides.non_goals),
        allowed_paths=allowed,
        protected_paths=protected,
        required_verification=_unique(overrides.required_verification),
        bundle_identity=overrides.bundle_identity,
        atlas_identity=overrides.atlas_identity,
        workspace_identity=identity,
        budgets=overrides.budgets or PlanningBudgets(),
        requested_output=overrides.requested_output,
        high_risk_claims=_risk_claims(goal),
        allowed_scope_status="RESOLVED" if allowed else "UNRESOLVED",
    )


def _declared_paths(raw_text: str) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    protected: list[str] = []
    for line in raw_text.splitlines():
        match = _PATH_LINE.match(line)
        if match is None:
            continue
        values = [
            item.strip().strip("`'\"")
            for item in re.split(r"[,，;；]", match.group(2))
            if item.strip()
        ]
        target = (
            protected
            if match.group(1).casefold() in {"protected path", "protected paths", "保护路径"}
            else allowed
        )
        target.extend(values)
    return allowed, protected


def _normalize_patterns(values: list[str]) -> list[str]:
    result = []
    for value in values:
        normalized = value.rstrip("/")
        if value.endswith("/"):
            normalized += "/**"
        canonical_relative_path(normalized)
        result.append(normalized)
    return sorted(set(result))


def _unique(values: list[str]) -> list[str]:
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "request list fields must contain non-empty strings",
        )
    return sorted({item.strip() for item in values})


def _risk_claims(goal: str) -> list[str]:
    folded = goal.casefold()
    result = []
    for term in _RISK_TERMS:
        candidate = term.casefold()
        if candidate.isascii() and candidate.replace(" ", "").isalpha():
            if re.search(rf"\b{re.escape(candidate)}\b", folded):
                result.append(term)
        elif candidate in folded:
            result.append(term)
    return result
