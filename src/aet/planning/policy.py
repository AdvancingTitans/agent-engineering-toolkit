"""Fail-closed path and permission policy for Planning."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path

from .errors import PlanningError, PlanningErrorCode
from .models import PlanningConstraints, canonical_relative_path


def path_matches(path: str, patterns: list[str]) -> bool:
    normalized = canonical_relative_path(path)
    return any(
        fnmatchcase(normalized, pattern)
        or normalized == pattern.rstrip("/")
        or normalized.startswith(pattern.rstrip("/") + "/")
        for pattern in patterns
    )


def assert_path_allowed(path: str, constraints: PlanningConstraints) -> str:
    normalized = canonical_relative_path(path)
    if path_matches(normalized, constraints.protected_paths):
        raise PlanningError(
            PlanningErrorCode.PROTECTED_PATH,
            "candidate targets a protected path",
        )
    if constraints.scope_status != "RESOLVED":
        raise PlanningError(
            PlanningErrorCode.EVIDENCE_REQUIRED,
            "allowed path scope is unresolved",
        )
    if not constraints.allowed_paths or not path_matches(
        normalized, constraints.allowed_paths
    ):
        raise PlanningError(
            PlanningErrorCode.EVIDENCE_REQUIRED,
            "candidate path is outside the allowed scope",
        )
    return normalized


def resolve_workspace_path(workspace: Path, relative: str) -> Path:
    """Resolve a current source path without permitting symlink escape."""
    normalized = canonical_relative_path(relative)
    root = Path(workspace).resolve(strict=True)
    candidate = root / normalized
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise PlanningError(
            PlanningErrorCode.PATH_ESCAPE,
            "source path is missing or escapes the workspace",
        ) from error
    if not resolved.is_file():
        raise PlanningError(
            PlanningErrorCode.SOURCE_MISSING,
            "source path is not a regular file",
        )
    return resolved
