"""Stable behavioural-risk errors and diagnostic codes."""

from __future__ import annotations

from enum import StrEnum


class RiskErrorCode(StrEnum):
    INVALID_INPUT = "AET-RISK-INPUT-001"
    INVALID_POLICY = "AET-RISK-POLICY-001"
    UNRESOLVED_REFERENCE = "AET-RISK-REF-001"
    CONTEXT_CONFLICT = "AET-RISK-CONTEXT-001"
    PARTIAL_RUN = "AET-RISK-COVERAGE-001"
    MISSING_TOOL_RESULT = "AET-RISK-COVERAGE-002"
    STALE_PROOF = "AET-RISK-PROOF-001"
    REDACTED_EVIDENCE = "AET-RISK-REDACTION-001"
    UNSAFE_OUTPUT = "AET-RISK-OUTPUT-001"
    INTERNAL_RULE_ERROR = "AET-RISK-RULE-001"


class RiskError(ValueError):
    """Base error with a stable machine-readable code."""

    def __init__(self, code: RiskErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class RiskInputError(RiskError):
    def __init__(self, message: str) -> None:
        super().__init__(RiskErrorCode.INVALID_INPUT, message)


class RiskPolicyError(RiskError):
    def __init__(self, message: str) -> None:
        super().__init__(RiskErrorCode.INVALID_POLICY, message)


class RiskReferenceError(RiskError):
    def __init__(self, message: str) -> None:
        super().__init__(RiskErrorCode.UNRESOLVED_REFERENCE, message)
