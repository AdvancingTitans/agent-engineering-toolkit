"""Stable error codes for the Evidence-Guided Planner."""

from __future__ import annotations

from enum import StrEnum


class PlanningErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_BUNDLE = "INVALID_BUNDLE"
    INVALID_ATLAS = "INVALID_ATLAS"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    SOURCE_MISSING = "SOURCE_MISSING"
    SOURCE_STALE = "SOURCE_STALE"
    SYMBOL_NOT_FOUND = "SYMBOL_NOT_FOUND"
    PATH_ESCAPE = "PATH_ESCAPE"
    PROTECTED_PATH = "PROTECTED_PATH"
    REFERENCE_NOT_FOUND = "REFERENCE_NOT_FOUND"
    REFERENCE_KIND_MISMATCH = "REFERENCE_KIND_MISMATCH"
    CONFLICT_UNRESOLVED = "CONFLICT_UNRESOLVED"
    EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    INVALID_CANDIDATE = "INVALID_CANDIDATE"
    OVERCLAIMED_COVERAGE = "OVERCLAIMED_COVERAGE"
    EXECUTION_ATTEMPT = "EXECUTION_ATTEMPT"
    WRITE_ATTEMPT = "WRITE_ATTEMPT"


class PlanningError(ValueError):
    """A fail-closed Planning request, context, or candidate error."""

    def __init__(self, code: PlanningErrorCode | str, message: str) -> None:
        self.code = PlanningErrorCode(code)
        self.message = message
        super().__init__(f"{self.code.value}: {message}")
