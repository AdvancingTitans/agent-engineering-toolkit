"""Strict loader and matcher for AET behavioural-risk policy v1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Mapping

from .errors import RiskPolicyError
from .models import Factor, RISK_POLICY_SCHEMA
from .schemas import SchemaKind, canonical_json, validate_version


@dataclass(frozen=True)
class PolicySurface:
    tool_name: str
    capability: str
    high_impact: bool
    asset_ids: tuple[str, ...]
    monitoring_surface_ids: tuple[str, ...]


@dataclass(frozen=True)
class RiskPolicy:
    schema_version: str
    policy_id: str
    policy_sha256: str
    assets: tuple[Mapping[str, Any], ...]
    tools: tuple[Mapping[str, Any], ...]
    monitoring_surfaces: tuple[Mapping[str, Any], ...]
    not_applicable_factors: tuple[Factor, ...]
    redaction_patterns: tuple[str, ...]

    def classify(self, tool_name: str, arguments: Mapping[str, Any] | list[Any] | None) -> PolicySurface:
        rendered = canonical_json({"arguments": arguments}) if arguments is not None else ""
        selected: Mapping[str, Any] | None = None
        for item in self.tools:
            if fnmatchcase(tool_name, str(item["name_pattern"])):
                selected = item
                break
        capability = str(selected.get("capability", "unknown")) if selected else "unknown"
        high_impact = bool(selected.get("high_impact", False)) if selected else False
        asset_ids = tuple(
            str(item["id"])
            for item in self.assets
            if any(fnmatchcase(rendered, str(pattern)) for pattern in item.get("patterns", ()))
        )
        monitor_ids = tuple(
            str(item["id"])
            for item in self.monitoring_surfaces
            if any(fnmatchcase(rendered, str(pattern)) for pattern in item.get("patterns", ()))
        )
        return PolicySurface(tool_name, capability, high_impact, asset_ids, monitor_ids)


def load_policy(path: str | Path) -> RiskPolicy:
    selected = Path(path)
    if selected.is_symlink() or not selected.is_file():
        raise RiskPolicyError("policy must be a regular non-symbolic-link file")
    try:
        raw = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RiskPolicyError(f"cannot read risk policy: {error}") from error
    if not isinstance(raw, dict):
        raise RiskPolicyError("risk policy must be an object")
    try:
        validate_version(SchemaKind.RISK_POLICY, raw)
        _validate_policy(raw)
    except (RiskPolicyError, ValueError) as error:
        if isinstance(error, RiskPolicyError):
            raise
        raise RiskPolicyError(str(error)) from error
    digest = hashlib.sha256(canonical_json(raw).encode("utf-8")).hexdigest()
    return RiskPolicy(
        schema_version=RISK_POLICY_SCHEMA,
        policy_id=str(raw["policy_id"]),
        policy_sha256=digest,
        assets=tuple(raw["assets"]),
        tools=tuple(raw["tools"]),
        monitoring_surfaces=tuple(raw["monitoring_surfaces"]),
        not_applicable_factors=tuple(Factor(item) for item in raw["not_applicable_factors"]),
        redaction_patterns=tuple(str(item) for item in raw["redaction_patterns"]),
    )


def _validate_policy(raw: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "policy_id",
        "assets",
        "tools",
        "monitoring_surfaces",
        "not_applicable_factors",
        "redaction_patterns",
    }
    if set(raw) != required:
        raise RiskPolicyError("risk policy fields do not match v1 contract")
    if not isinstance(raw["policy_id"], str) or not raw["policy_id"]:
        raise RiskPolicyError("policy_id must be a non-empty string")
    if not all(isinstance(raw[key], list) for key in required - {"schema_version", "policy_id"}):
        raise RiskPolicyError("policy collections must be arrays")
    asset_ids = _unique_objects(raw["assets"], {"id", "patterns"}, "asset")
    monitor_ids = _unique_objects(raw["monitoring_surfaces"], {"id", "patterns"}, "monitoring surface")
    _unique_objects(raw["tools"], {"name_pattern", "capability", "high_impact"}, "tool")
    if not asset_ids or not monitor_ids:
        raise RiskPolicyError("at least one asset and monitoring surface are required")
    if len(raw["not_applicable_factors"]) != len(set(raw["not_applicable_factors"])):
        raise RiskPolicyError("not_applicable_factors must be unique")
    for item in raw["not_applicable_factors"]:
        Factor(item)


def _unique_objects(values: list[Any], required: set[str], label: str) -> set[str]:
    identities: set[str] = set()
    for value in values:
        if not isinstance(value, dict) or not required.issubset(value):
            raise RiskPolicyError(f"each {label} must contain {sorted(required)}")
        identity = str(value.get("id", value.get("name_pattern", "")))
        if not identity or identity in identities:
            raise RiskPolicyError(f"{label} identities must be non-empty and unique")
        identities.add(identity)
        if "patterns" in value and (
            not isinstance(value["patterns"], list)
            or not value["patterns"]
            or not all(isinstance(item, str) and item for item in value["patterns"])
        ):
            raise RiskPolicyError(f"{label} patterns must be non-empty strings")
    return identities


__all__ = ["PolicySurface", "RiskPolicy", "load_policy"]
