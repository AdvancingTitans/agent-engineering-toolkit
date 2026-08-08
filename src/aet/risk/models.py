"""Frozen models for evidence-grounded behavioural risk diagnosis v1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import StrEnum
from typing import Any, Mapping

RISK_DIAGNOSIS_SCHEMA = "aet-risk-diagnosis/1.0"
RISK_POLICY_SCHEMA = "aet-risk-policy/1.0"
RISK_FORECAST_SCHEMA = "aet-risk-forecast/1.0"
EVALUATOR_VERSION = "1.0.0"


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Factor(StrEnum):
    GOAL_DIVERGENCE = "goal_divergence_indicator"
    HARM_REALIZATION_CAPABILITY = "harm_realization_capability"
    OVERSIGHT_RESISTANCE = "oversight_resistance_indicator"


class EvidenceStrength(StrEnum):
    DIRECT = "DIRECT"
    CORROBORATED = "CORROBORATED"
    INDIRECT = "INDIRECT"
    NONE = "NONE"


@dataclass(frozen=True)
class SourceRef:
    ref: str
    record_id: str | None = None
    source_order_id: str | None = None
    source_type: str | None = None

    def __post_init__(self) -> None:
        if not self.ref:
            raise ValueError("source reference must not be empty")


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: str = "warning"
    source_refs: tuple[SourceRef, ...] = ()


@dataclass(frozen=True)
class Coverage:
    complete: bool
    checked_surfaces: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    observability_gap: bool = False


@dataclass(frozen=True)
class RiskContext:
    run_group_id: str
    generation_id: str
    task_id: str
    records: tuple[Mapping[str, Any], ...]
    intent: Mapping[str, Any]
    policy: Any
    evidence: tuple[Mapping[str, Any], ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def context_key(self) -> str:
        return f"{self.run_group_id}:{self.generation_id}:{self.task_id}"


@dataclass(frozen=True)
class Signal:
    code: str
    factor: Factor
    refs: tuple[SourceRef, ...]
    strength: EvidenceStrength
    asset_ids: tuple[str, ...] = ()
    monitoring_surface_ids: tuple[str, ...] = ()
    counter_evidence_refs: tuple[SourceRef, ...] = ()
    limitations: tuple[str, ...] = ()
    does_not_prove: tuple[str, ...] = ()
    order_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class FactorFinding:
    factor: Factor
    observable: str
    status: Status
    strength: EvidenceStrength
    evidence_refs: tuple[SourceRef, ...]
    counter_evidence_refs: tuple[SourceRef, ...]
    coverage: Coverage
    limitations: tuple[str, ...]
    does_not_prove: tuple[str, ...]
    context_key: str
    asset_ids: tuple[str, ...] = ()
    monitoring_surface_ids: tuple[str, ...] = ()
    signal_codes: tuple[str, ...] = ()
    order_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.observable or not self.context_key:
            raise ValueError("finding observable and context_key are required")
        if not self.does_not_prove:
            raise ValueError("finding must state what it does not prove")
        if self.status is Status.FAIL and not self.evidence_refs:
            raise ValueError("FAIL requires at least one evidence reference")
        if self.status is Status.PASS and not self.coverage.complete:
            raise ValueError("PASS requires complete declared coverage")


@dataclass(frozen=True)
class RiskPathway:
    pathway_id: str
    context_key: str
    factors: tuple[FactorFinding, ...]
    ordered_refs: tuple[SourceRef, ...]
    status: Status
    causal_limitations: tuple[str, ...]


@dataclass(frozen=True)
class ProposedIntervention:
    intervention_id: str
    context_key: str
    factor_combination: tuple[Factor, ...]
    authority: str
    actions: tuple[str, ...]
    rationale_refs: tuple[SourceRef, ...]

    def __post_init__(self) -> None:
        if self.authority != "PROPOSED":
            raise ValueError("risk interventions must remain PROPOSED")


@dataclass(frozen=True)
class RiskDiagnosis:
    schema_version: str
    evaluator_version: str
    created_at: str
    policy_id: str
    policy_sha256: str
    findings: tuple[FactorFinding, ...]
    pathways: tuple[RiskPathway, ...] = ()
    interventions: tuple[ProposedIntervention, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != RISK_DIAGNOSIS_SCHEMA:
            raise ValueError("unsupported risk diagnosis schema version")


def to_primitive(value: Any) -> Any:
    """Convert frozen protocol models into JSON primitives without inference."""
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {item.name: to_primitive(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    return value


__all__ = [
    "Coverage",
    "Diagnostic",
    "EVALUATOR_VERSION",
    "EvidenceStrength",
    "Factor",
    "FactorFinding",
    "ProposedIntervention",
    "RISK_DIAGNOSIS_SCHEMA",
    "RISK_FORECAST_SCHEMA",
    "RISK_POLICY_SCHEMA",
    "RiskContext",
    "RiskDiagnosis",
    "RiskPathway",
    "Signal",
    "SourceRef",
    "Status",
    "to_primitive",
]
