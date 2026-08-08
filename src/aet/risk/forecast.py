"""Conservative, non-training empirical pathway forecast experiment."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from .errors import RiskInputError
from .models import RISK_DIAGNOSIS_SCHEMA, RISK_FORECAST_SCHEMA
from .schemas import SchemaKind, canonical_json, validate_version


class ForecastStatus(StrEnum):
    ELEVATED = "ELEVATED"
    NOT_ELEVATED = "NOT_ELEVATED"
    UNKNOWN = "UNKNOWN"


# ponytail: forecast stays hard-disabled until a future evidence-derived gate
# replaces self-declared calibration metrics; diagnosis remains fully usable.
FORECAST_RELEASE_STATE = "research_only"


@dataclass(frozen=True)
class Interval:
    low: float | None
    high: float | None


@dataclass(frozen=True)
class Forecast:
    status: ForecastStatus
    support: int
    interval: Interval
    baseline: Interval
    reason: str


def wilson_interval(positives: int, support: int, z: float = 1.959963984540054) -> Interval:
    if support < 0 or positives < 0 or positives > support:
        raise RiskInputError("forecast counts must satisfy 0 <= positives <= support")
    if support == 0:
        return Interval(None, None)
    proportion = positives / support
    denominator = 1 + z * z / support
    centre = (proportion + z * z / (2 * support)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * support)) / support) / denominator
    return Interval(max(0.0, centre - margin), min(1.0, centre + margin))


def calibration_gate(calibration: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    gaps: list[str] = ["forecast_research_only"]
    required_counts = {
        "episode_count": 200,
        "positive_count": 30,
        "repository_count": 3,
        "host_count": 2,
    }
    for key, minimum in required_counts.items():
        value = calibration.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            gaps.append(f"{key}_below_{minimum}")
    split = calibration.get("split_manifest")
    if not isinstance(split, Mapping):
        gaps.append("missing_split_manifest")
    else:
        for key in ("temporal_holdout", "repository_holdout", "host_holdout"):
            if split.get(key) is not True:
                gaps.append(f"{key}_required")
        if split.get("leakage_detected") is not False:
            gaps.append("split_leakage_not_excluded")
        if split.get("dataset_sha256") != calibration.get("dataset_sha256"):
            gaps.append("dataset_hash_mismatch")
    metrics = calibration.get("holdout_metrics")
    if not isinstance(metrics, Mapping):
        gaps.append("missing_holdout_metrics")
    else:
        if not isinstance(metrics.get("false_positive_rate"), (int, float)) or metrics["false_positive_rate"] > 0.01:
            gaps.append("false_positive_rate_above_0.01")
        ece_ok = isinstance(metrics.get("ece"), (int, float)) and metrics["ece"] <= 0.10
        brier_ok = isinstance(metrics.get("brier_skill_ci_low"), (int, float)) and metrics["brier_skill_ci_low"] > 0
        if not (ece_ok or brier_ok):
            gaps.append("calibration_not_better_than_gate")
    return not gaps, tuple(gaps)


def forecast_pathway(signature: Mapping[str, Any], calibration: Mapping[str, Any]) -> Forecast:
    gate_ok, gate_gaps = calibration_gate(calibration)
    empty = Interval(None, None)
    if not gate_ok:
        return Forecast(ForecastStatus.UNKNOWN, 0, empty, empty, ";".join(gate_gaps))
    host = signature.get("host")
    repository = signature.get("repository")
    domain = calibration.get("domain")
    if not isinstance(domain, Mapping) or host not in domain.get("hosts", ()) or repository not in domain.get("repositories", ()):
        return Forecast(ForecastStatus.UNKNOWN, 0, empty, empty, "out_of_domain")
    buckets = calibration.get("buckets")
    key = signature.get("key")
    bucket = buckets.get(key) if isinstance(buckets, Mapping) else None
    if not isinstance(bucket, Mapping):
        return Forecast(ForecastStatus.UNKNOWN, 0, empty, empty, "unseen_signature")
    support = bucket.get("support")
    positives = bucket.get("positives")
    minimum = calibration.get("min_support", 20)
    if not isinstance(support, int) or not isinstance(positives, int) or support < minimum:
        return Forecast(ForecastStatus.UNKNOWN, int(support or 0), empty, empty, "insufficient_support")
    interval = wilson_interval(positives, support)
    baseline_data = calibration.get("baseline")
    if not isinstance(baseline_data, Mapping):
        return Forecast(ForecastStatus.UNKNOWN, support, interval, empty, "missing_baseline")
    baseline = wilson_interval(int(baseline_data["positives"]), int(baseline_data["support"]))
    if interval.low is None or baseline.high is None:
        return Forecast(ForecastStatus.UNKNOWN, support, interval, baseline, "insufficient_interval")
    status = ForecastStatus.ELEVATED if interval.low > baseline.high else ForecastStatus.NOT_ELEVATED
    reason = "pathway_interval_above_baseline" if status is ForecastStatus.ELEVATED else "no_separation_from_baseline"
    return Forecast(status, support, interval, baseline, reason)


def forecast_diagnosis(
    diagnosis_path: str | Path,
    calibration_path: str | Path,
    *,
    host: str,
    repository: str,
    now: str | None = None,
) -> dict[str, Any]:
    diagnosis_bytes, diagnosis = _load_object(Path(diagnosis_path), "diagnosis")
    calibration_bytes, calibration = _load_object(Path(calibration_path), "calibration")
    if diagnosis.get("schema_version") != RISK_DIAGNOSIS_SCHEMA:
        raise RiskInputError("forecast input must be an AET risk diagnosis v1")
    validate_version(SchemaKind.RISK_DIAGNOSIS, diagnosis)
    gate_ok, gate_gaps = calibration_gate(calibration)
    forecasts = []
    for pathway in diagnosis.get("pathways", []):
        if not isinstance(pathway, Mapping):
            continue
        factors = pathway.get("factors", [])
        factor_names = sorted(
            str(item.get("factor")) for item in factors if isinstance(item, Mapping) and item.get("factor")
        )
        key = "+".join(factor_names)
        result = forecast_pathway(
            {"key": key, "host": host, "repository": repository},
            calibration,
        )
        forecasts.append(
            {
                "pathway_id": str(pathway.get("pathway_id", "unknown-pathway")),
                "signature": key,
                "status": result.status.value,
                "support": result.support,
                "interval": {"low": result.interval.low, "high": result.interval.high},
                "baseline": {"low": result.baseline.low, "high": result.baseline.high},
                "reason": result.reason,
            }
        )
    created_at = now or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    report = {
        "schema_version": RISK_FORECAST_SCHEMA,
        "created_at": created_at,
        "diagnosis_sha256": hashlib.sha256(diagnosis_bytes).hexdigest(),
        "calibration_sha256": hashlib.sha256(calibration_bytes).hexdigest(),
        "dataset_sha256": str(calibration.get("dataset_sha256", "0" * 64)),
        "forecasts": forecasts,
        "gate_status": "PASS" if gate_ok else "FAIL",
        "limitations": [
            "pathway-specific empirical association is not a model-wide loss-of-control probability",
            "no model training, fine-tuning, distillation, parameter modification, or model judge was used",
            *(gate_gaps or ("valid only for the declared calibration domain",)),
        ],
        "provenance": {
            "host": host,
            "repository": repository,
            "model_parameter_changes": False,
            "network_used": False,
        },
    }
    validate_version(SchemaKind.RISK_FORECAST, report)
    return report


def write_forecast(report: Mapping[str, Any], output: str | Path) -> Path:
    path = Path(output)
    if path.is_symlink():
        raise RiskInputError("forecast output cannot be a symbolic link")
    if path.exists():
        raise RiskInputError(f"forecast output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def _load_object(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise RiskInputError(f"{label} must be a regular non-symbolic-link file")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RiskInputError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise RiskInputError(f"{label} must contain one object")
    return raw, value


__all__ = [
    "FORECAST_RELEASE_STATE",
    "Forecast",
    "ForecastStatus",
    "Interval",
    "calibration_gate",
    "forecast_diagnosis",
    "forecast_pathway",
    "wilson_interval",
    "write_forecast",
]
