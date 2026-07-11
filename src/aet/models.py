"""Small, serializable audit data structures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RunState(StrEnum):
    """Lifecycle position of an optional AET delivery run, not a finding."""

    CREATED = "CREATED"
    INTENT_BOUND = "INTENT_BOUND"
    AUDITED = "AUDITED"
    REVIEWED = "REVIEWED"
    PROVEN = "PROVEN"
    PACKED = "PACKED"
    STALE = "STALE"
    CLOSED = "CLOSED"


class Severity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


@dataclass(frozen=True)
class Evidence:
    path: str
    line: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class Finding:
    rule_id: str
    status: Status
    severity: Severity
    claim: str
    evidence: tuple[Evidence, ...]
    remediation: str
    rule_version: str = "0.1.0"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Asset:
    path: Path
    kind: str
    relative_path: str


def finding_counts(findings: list[Finding]) -> dict[str, int]:
    counts = {status.value: 0 for status in Status}
    for finding in findings:
        counts[finding.status.value] += 1
    return counts
