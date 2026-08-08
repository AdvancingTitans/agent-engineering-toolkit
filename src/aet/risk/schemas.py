"""Risk Schema lookup and dependency-free authoritative shape validation."""

from __future__ import annotations

import json
import re
import sysconfig
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any, Mapping

from .errors import RiskInputError
from .models import RISK_DIAGNOSIS_SCHEMA, RISK_FORECAST_SCHEMA, RISK_POLICY_SCHEMA


class SchemaKind(StrEnum):
    RISK_POLICY = "risk-policy"
    RISK_DIAGNOSIS = "risk-diagnosis"
    RISK_FORECAST = "risk-forecast"


_FILES = {
    SchemaKind.RISK_POLICY: "risk-policy.schema.json",
    SchemaKind.RISK_DIAGNOSIS: "risk-diagnosis.schema.json",
    SchemaKind.RISK_FORECAST: "risk-forecast.schema.json",
}

_VERSIONS = {
    SchemaKind.RISK_POLICY: RISK_POLICY_SCHEMA,
    SchemaKind.RISK_DIAGNOSIS: RISK_DIAGNOSIS_SCHEMA,
    SchemaKind.RISK_FORECAST: RISK_FORECAST_SCHEMA,
}


def schema_path(kind: SchemaKind | str, version: str = "1.0") -> Path:
    selected = SchemaKind(kind)
    if version != "1.0":
        raise RiskInputError(f"unsupported {selected.value} schema version")
    filename = _FILES[selected]
    source = Path(__file__).resolve().parents[3] / "schemas" / "risk" / "v1" / filename
    if source.is_file():
        return source
    installed = Path(sysconfig.get_path("data")) / "share" / "aet" / "schemas" / "risk" / "v1" / filename
    distribution_path = None
    try:
        package = distribution("agent-engineering-toolkit")
        suffix = f"share/aet/schemas/risk/v1/{filename}"
        for entry in package.files or ():
            if str(entry).endswith(suffix):
                distribution_path = Path(package.locate_file(entry))
                break
    except PackageNotFoundError:
        pass
    for candidate in (installed, distribution_path):
        if candidate is not None and candidate.is_file():
            return candidate
    raise RiskInputError(f"risk Schema is unavailable: {filename}")


def load_schema(kind: SchemaKind | str, version: str = "1.0") -> dict[str, Any]:
    value = json.loads(schema_path(kind, version).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RiskInputError("risk Schema must contain one object")
    return value


def validate_version(kind: SchemaKind | str, value: Mapping[str, Any]) -> None:
    selected = SchemaKind(kind)
    if not isinstance(value, Mapping):
        raise RiskInputError("risk document must be an object")
    if value.get("schema_version") != _VERSIONS[selected]:
        raise RiskInputError(f"unsupported {selected.value} schema version")
    forbidden = {"overall_score", "trust_score", "model_motive", "autonomous_action"}
    if forbidden.intersection(value):
        raise RiskInputError("holistic scores, mental-state claims, and automatic action are forbidden")
    if selected is SchemaKind.RISK_DIAGNOSIS:
        _validate_diagnosis(value)
    elif selected is SchemaKind.RISK_FORECAST:
        _validate_forecast(value)


def _validate_diagnosis(value: Mapping[str, Any]) -> None:
    _exact(
        value,
        {
            "schema_version", "evaluator_version", "created_at", "policy_id",
            "policy_sha256", "findings", "pathways", "interventions",
            "diagnostics", "provenance",
        },
        "risk diagnosis",
    )
    if not _nonempty(value.get("evaluator_version")) or not _timestamp(value.get("created_at")):
        raise RiskInputError("risk diagnosis evaluator_version and created_at are invalid")
    if not _nonempty(value.get("policy_id")) or not _digest(value.get("policy_sha256")):
        raise RiskInputError("risk diagnosis policy binding is invalid")
    for key in ("findings", "pathways", "interventions", "diagnostics"):
        if not isinstance(value.get(key), list):
            raise RiskInputError(f"risk diagnosis {key} must be an array")
    if not isinstance(value.get("provenance"), Mapping):
        raise RiskInputError("risk diagnosis provenance must be an object")
    for finding in value["findings"]:
        _finding(finding)
    for pathway in value["pathways"]:
        _exact(
            pathway,
            {"pathway_id", "context_key", "factors", "ordered_refs", "status", "causal_limitations"},
            "risk pathway",
        )
        if not _nonempty(pathway.get("pathway_id")) or not _nonempty(pathway.get("context_key")):
            raise RiskInputError("risk pathway identifiers are invalid")
        if not isinstance(pathway.get("factors"), list) or not pathway["factors"]:
            raise RiskInputError("risk pathway factors must be a non-empty array")
        for finding in pathway["factors"]:
            _finding(finding)
        _refs(pathway.get("ordered_refs"), "risk pathway ordered_refs")
        _status(pathway.get("status"))
        _strings(pathway.get("causal_limitations"), "risk pathway causal_limitations")
    for intervention in value["interventions"]:
        _exact(
            intervention,
            {"intervention_id", "context_key", "factor_combination", "authority", "actions", "rationale_refs"},
            "risk intervention",
        )
        if intervention.get("authority") != "PROPOSED":
            raise RiskInputError("risk intervention authority must be PROPOSED")
        if not _nonempty(intervention.get("intervention_id")) or not _nonempty(intervention.get("context_key")):
            raise RiskInputError("risk intervention identifiers are invalid")
        factors = intervention.get("factor_combination")
        if not isinstance(factors, list) or any(item not in _FACTORS for item in factors):
            raise RiskInputError("risk intervention factor combination is invalid")
        _strings(intervention.get("actions"), "risk intervention actions", nonempty=True)
        _refs(intervention.get("rationale_refs"), "risk intervention rationale_refs")
    for diagnostic in value["diagnostics"]:
        _exact(diagnostic, {"code", "message", "severity", "source_refs"}, "risk diagnostic")
        if not _nonempty(diagnostic.get("code")) or not _nonempty(diagnostic.get("message")):
            raise RiskInputError("risk diagnostic code and message are invalid")
        if diagnostic.get("severity") not in {"info", "warning", "error"}:
            raise RiskInputError("risk diagnostic severity is invalid")
        _refs(diagnostic.get("source_refs"), "risk diagnostic source_refs")


def _finding(value: Any) -> None:
    _exact(
        value,
        {
            "factor", "observable", "status", "strength", "evidence_refs",
            "counter_evidence_refs", "coverage", "limitations", "does_not_prove",
            "context_key", "asset_ids", "monitoring_surface_ids", "signal_codes",
            "order_keys",
        },
        "risk finding",
    )
    if value.get("factor") not in _FACTORS or not _nonempty(value.get("observable")):
        raise RiskInputError("risk finding factor or observable is invalid")
    _status(value.get("status"))
    if value.get("strength") not in {"DIRECT", "CORROBORATED", "INDIRECT", "NONE"}:
        raise RiskInputError("risk finding strength is invalid")
    _refs(value.get("evidence_refs"), "risk finding evidence_refs")
    _refs(value.get("counter_evidence_refs"), "risk finding counter_evidence_refs")
    coverage = value.get("coverage")
    _exact(coverage, {"complete", "checked_surfaces", "gaps", "observability_gap"}, "risk coverage")
    if not isinstance(coverage.get("complete"), bool) or not isinstance(coverage.get("observability_gap"), bool):
        raise RiskInputError("risk coverage booleans are invalid")
    _strings(coverage.get("checked_surfaces"), "risk coverage checked_surfaces")
    _strings(coverage.get("gaps"), "risk coverage gaps")
    for key in ("limitations", "does_not_prove", "asset_ids", "monitoring_surface_ids", "signal_codes", "order_keys"):
        _strings(value.get(key), f"risk finding {key}", nonempty=key == "does_not_prove")
    if not _nonempty(value.get("context_key")):
        raise RiskInputError("risk finding context_key is invalid")
    if value["status"] == "FAIL" and not value["evidence_refs"]:
        raise RiskInputError("risk finding FAIL requires evidence_refs")
    if value["status"] == "PASS" and coverage["complete"] is not True:
        raise RiskInputError("risk finding PASS requires complete coverage")


def _validate_forecast(value: Mapping[str, Any]) -> None:
    _exact(
        value,
        {
            "schema_version", "created_at", "diagnosis_sha256", "calibration_sha256",
            "dataset_sha256", "forecasts", "gate_status", "limitations", "provenance",
        },
        "risk forecast",
    )
    if not _timestamp(value.get("created_at")):
        raise RiskInputError("risk forecast created_at is invalid")
    for key in ("diagnosis_sha256", "calibration_sha256", "dataset_sha256"):
        if not _digest(value.get(key)):
            raise RiskInputError(f"risk forecast {key} is invalid")
    if value.get("gate_status") not in {"PASS", "FAIL"} or not isinstance(value.get("forecasts"), list):
        raise RiskInputError("risk forecast gate or forecasts are invalid")
    _strings(value.get("limitations"), "risk forecast limitations")
    if not isinstance(value.get("provenance"), Mapping):
        raise RiskInputError("risk forecast provenance must be an object")
    for forecast in value["forecasts"]:
        _exact(
            forecast,
            {"pathway_id", "signature", "status", "support", "interval", "baseline", "reason"},
            "pathway forecast",
        )
        if not _nonempty(forecast.get("pathway_id")) or not _nonempty(forecast.get("signature")):
            raise RiskInputError("pathway forecast identifiers are invalid")
        if forecast.get("status") not in {"ELEVATED", "NOT_ELEVATED", "UNKNOWN"}:
            raise RiskInputError("pathway forecast status is invalid")
        if not isinstance(forecast.get("support"), int) or isinstance(forecast.get("support"), bool) or forecast["support"] < 0:
            raise RiskInputError("pathway forecast support is invalid")
        for key in ("interval", "baseline"):
            interval = forecast.get(key)
            _exact(interval, {"low", "high"}, f"pathway forecast {key}")
            if any(item is not None and (not isinstance(item, (int, float)) or isinstance(item, bool)) for item in interval.values()):
                raise RiskInputError(f"pathway forecast {key} is invalid")
        if not _nonempty(forecast.get("reason")):
            raise RiskInputError("pathway forecast reason is invalid")


_FACTORS = {
    "goal_divergence_indicator",
    "harm_realization_capability",
    "oversight_resistance_indicator",
}


def _exact(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise RiskInputError(f"{label} fields do not match the v1 contract")


def _refs(value: Any, label: str) -> None:
    if not isinstance(value, list):
        raise RiskInputError(f"{label} must be an array")
    for item in value:
        _exact(item, {"ref", "record_id", "source_order_id", "source_type"}, label)
        if not _nonempty(item.get("ref")) or any(
            item.get(key) is not None and not isinstance(item.get(key), str)
            for key in ("record_id", "source_order_id", "source_type")
        ):
            raise RiskInputError(f"{label} contains an invalid reference")


def _strings(value: Any, label: str, *, nonempty: bool = False) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value) or (nonempty and not value):
        raise RiskInputError(f"{label} must contain strings")


def _status(value: Any) -> None:
    if value not in {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}:
        raise RiskInputError("risk status is invalid")


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _timestamp(value: Any) -> bool:
    return isinstance(value, str) and value.endswith("Z") and "T" in value


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
