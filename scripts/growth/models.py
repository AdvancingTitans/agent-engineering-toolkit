"""Stable data models for aggregate repository growth measurements."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


MetricStatus = Literal["KNOWN", "UNKNOWN", "RATE_LIMITED", "UNAVAILABLE"]


@dataclass(frozen=True)
class MetricValue:
    status: MetricStatus
    value: int | float | str | bool | None
    source: str
    observed_at: str
    diagnostic: str | None = None


@dataclass(frozen=True)
class GrowthSnapshot:
    schema_version: str
    repository: str
    observed_at: str
    stars: MetricValue
    forks: MetricValue
    watchers: MetricValue
    open_issues: MetricValue
    contributors: MetricValue
    pull_requests: MetricValue
    traffic_views: MetricValue
    traffic_unique_visitors: MetricValue
    clones: MetricValue
    release_downloads: MetricValue
    skills_installs: MetricValue
    referrers: list[dict[str, Any]] = field(default_factory=list)
    repository_state: dict[str, Any] = field(default_factory=dict)
    release_state: dict[str, Any] = field(default_factory=dict)
    pypi_state: dict[str, Any] = field(default_factory=dict)
    skills_state: dict[str, Any] = field(default_factory=dict)
    community_state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def metric(
    *,
    status: MetricStatus,
    value: int | float | str | bool | None,
    source: str,
    observed_at: str,
    diagnostic: str | None = None,
) -> MetricValue:
    if status != "KNOWN":
        value = None
    return MetricValue(status, value, source, observed_at, diagnostic)
