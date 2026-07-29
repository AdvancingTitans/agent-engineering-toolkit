"""Planning Schema lookup and dependency-free document validation."""

from __future__ import annotations

import json
import sysconfig
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any, Mapping

from .candidate_parser import parse_candidate
from .errors import PlanningError, PlanningErrorCode
from .models import PlanningContext, PlanningRequest, model_from_mapping


class SchemaKind(StrEnum):
    PLANNING_REQUEST = "planning-request"
    PLANNING_CONTEXT = "planning-context"
    PLAN_CANDIDATE = "plan-candidate"
    EVIDENCE_LINKED_PLAN = "evidence-linked-plan"
    PLAN_REFERENCE = "plan-reference"
    PLAN_MANIFEST = "plan-manifest"


_FILES = {
    SchemaKind.PLANNING_REQUEST: "planning-request-v1.schema.json",
    SchemaKind.PLANNING_CONTEXT: "planning-context-v1.schema.json",
    SchemaKind.PLAN_CANDIDATE: "plan-candidate-v1.schema.json",
    SchemaKind.EVIDENCE_LINKED_PLAN: "evidence-linked-plan-v1.schema.json",
    SchemaKind.PLAN_REFERENCE: "plan-reference-v1.schema.json",
    SchemaKind.PLAN_MANIFEST: "plan-manifest-v1.schema.json",
}


def schema_path(kind: SchemaKind | str, version: str = "1.0") -> Path:
    selected = SchemaKind(kind)
    if version != "1.0":
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            f"unsupported {selected.value} schema version",
        )
    source = Path(__file__).resolve().parents[3] / "schemas" / "planning"
    candidate = source / _FILES[selected]
    if candidate.is_file():
        return candidate
    installed = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "aet"
        / "schemas"
        / "planning"
        / _FILES[selected]
    )
    distribution_path = None
    try:
        package = distribution("agent-engineering-toolkit")
        suffix = f"share/aet/schemas/planning/{_FILES[selected]}"
        for entry in package.files or ():
            if str(entry).endswith(suffix):
                distribution_path = Path(package.locate_file(entry))
                break
    except PackageNotFoundError:
        pass
    for candidate in (installed, distribution_path):
        if candidate is not None and candidate.is_file():
            return candidate
    raise PlanningError(
        PlanningErrorCode.INVALID_REQUEST,
        f"Planning Schema is unavailable: {_FILES[selected]}",
    )


def load_schema(kind: SchemaKind | str, version: str = "1.0") -> dict[str, Any]:
    value = json.loads(schema_path(kind, version).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PlanningError(
            PlanningErrorCode.INVALID_REQUEST,
            "Planning Schema must contain one object",
        )
    return value


def validate_document(kind: SchemaKind | str, value: Mapping[str, Any]) -> None:
    """Validate authoritative shapes through the same constructors used at runtime."""
    selected = SchemaKind(kind)
    if not isinstance(value, Mapping):
        raise PlanningError(PlanningErrorCode.INVALID_REQUEST, "document must be an object")
    if selected is SchemaKind.PLANNING_REQUEST:
        model_from_mapping(PlanningRequest, value)
    elif selected is SchemaKind.PLANNING_CONTEXT:
        model_from_mapping(PlanningContext, value)
    elif selected is SchemaKind.PLAN_CANDIDATE:
        parse_candidate(
            json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        )
    else:
        expected = {
            SchemaKind.EVIDENCE_LINKED_PLAN: "evidence-linked-plan/1.0",
            SchemaKind.PLAN_REFERENCE: "plan-reference/1.0",
            SchemaKind.PLAN_MANIFEST: "plan-manifest/1.0",
        }[selected]
        if value.get("schema_version") != expected:
            raise PlanningError(
                PlanningErrorCode.INVALID_REQUEST,
                f"unsupported {selected.value} schema version",
            )
