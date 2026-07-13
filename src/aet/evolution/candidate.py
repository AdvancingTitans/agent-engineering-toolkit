"""Versioned evolution candidate loading and hash binding."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .targets import TargetRegistry, default_registry, infer_target_type
from .constitution import constitution_sha256


class CandidateError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateTarget:
    target_type: str
    path: str
    baseline_sha256: str


@dataclass(frozen=True)
class EvolutionCandidate:
    schema_version: str
    candidate_id: str
    target: CandidateTarget
    candidate_sha256: str
    operations: tuple[dict[str, Any], ...]
    budgets: dict[str, int]
    adoption: str
    source_patterns: tuple[str, ...]
    candidate_artifact: str | None
    source_document: dict[str, Any]


_SHA256_LENGTH = 64
_V2_FIELDS = {
    "schema_version", "report_kind", "candidate_id", "target", "candidate_artifact",
    "candidate_sha256", "source_patterns", "operations", "budgets", "adoption",
    "constitution_sha256",
}


def load_candidate(
    source: Path | Mapping[str, Any],
    *,
    candidate_content: bytes | None = None,
    baseline_content: bytes | None = None,
    registry: TargetRegistry | None = None,
) -> EvolutionCandidate:
    root: Path | None = None
    if isinstance(source, Path):
        root = source if source.is_dir() else source.parent
        document_path = source / "candidate.json" if source.is_dir() else source
        try:
            document = json.loads(document_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CandidateError(f"cannot read candidate manifest: {error}") from error
    else:
        document = copy.deepcopy(dict(source))
    if not isinstance(document, dict):
        raise CandidateError("candidate manifest must be an object")

    active_registry = registry or default_registry()
    normalized = _upgrade_v1(document) if document.get("schema_version") != "evolution-candidate/v2" else copy.deepcopy(document)
    _validate_v2(normalized, active_registry)

    artifact = normalized.get("candidate_artifact")
    if candidate_content is None and root is not None and isinstance(artifact, str):
        artifact_path = (root / artifact).resolve()
        try:
            artifact_path.relative_to(root.resolve())
        except ValueError as error:
            raise CandidateError("candidate artifact escapes its candidate directory") from error
        try:
            candidate_content = artifact_path.read_bytes()
        except OSError as error:
            raise CandidateError(f"cannot read candidate artifact: {error}") from error
    if candidate_content is not None:
        _check_hash(candidate_content, normalized["candidate_sha256"], "candidate")
    if baseline_content is not None:
        _check_hash(baseline_content, normalized["target"]["baseline_sha256"], "baseline")

    target = normalized["target"]
    return EvolutionCandidate(
        schema_version="evolution-candidate/v2",
        candidate_id=normalized["candidate_id"],
        target=CandidateTarget(target["type"], target["path"], target["baseline_sha256"]),
        candidate_sha256=normalized["candidate_sha256"],
        operations=tuple(copy.deepcopy(normalized["operations"])),
        budgets=copy.deepcopy(normalized["budgets"]),
        adoption=normalized["adoption"],
        source_patterns=tuple(normalized.get("source_patterns", [])),
        candidate_artifact=artifact,
        source_document=copy.deepcopy(document),
    )


def _upgrade_v1(document: dict[str, Any]) -> dict[str, Any]:
    target_path = document.get("target_file")
    if not isinstance(target_path, str):
        raise CandidateError("candidate schema version is unsupported")
    target_type = infer_target_type(Path(target_path))
    return {
        "schema_version": "evolution-candidate/v2",
        "report_kind": "evolution_candidate",
        "candidate_id": document.get("candidate_id"),
        "target": {"type": target_type, "path": target_path, "baseline_sha256": document.get("baseline_sha256")},
        "candidate_artifact": "candidate.SKILL.md",
        "candidate_sha256": document.get("candidate_sha256"),
        "source_patterns": document.get("pattern_ids", []),
        "operations": [
            {
                "op": "replace",
                "path": f"/editable_blocks/{operation.get('id', '')}",
                "before_sha256": operation.get("before_sha256"),
                "value": operation.get("new_text"),
            }
            for operation in document.get("operations", []) if isinstance(operation, dict)
        ],
        "budgets": {
            "max_operations": document.get("edit_budget", {}).get("max_operations", 3),
            "max_added_characters": document.get("edit_budget", {}).get("max_added_characters", 800),
            "max_deleted_characters": document.get("edit_budget", {}).get("max_deleted_characters", 400),
        },
        "adoption": document.get("adoption", "human_required"),
        "constitution_sha256": constitution_sha256(),
    }


def _validate_v2(document: dict[str, Any], registry: TargetRegistry) -> None:
    unknown = set(document) - _V2_FIELDS
    if unknown:
        raise CandidateError(f"candidate contains unknown field(s): {', '.join(sorted(unknown))}")
    required = {"schema_version", "report_kind", "candidate_id", "target", "candidate_sha256", "operations", "budgets", "adoption", "constitution_sha256"}
    missing = required - set(document)
    if missing:
        raise CandidateError(f"candidate is missing field(s): {', '.join(sorted(missing))}")
    if document["schema_version"] != "evolution-candidate/v2" or document["report_kind"] != "evolution_candidate":
        raise CandidateError("candidate does not use the v2 contract")
    if not isinstance(document["candidate_id"], str) or not document["candidate_id"].startswith("CAND-"):
        raise CandidateError("candidate_id must start with CAND-")
    target = document["target"]
    if not isinstance(target, dict) or set(target) != {"type", "path", "baseline_sha256"}:
        raise CandidateError("target must contain exactly type, path, and baseline_sha256")
    if not isinstance(target["type"], str):
        raise CandidateError("target type must be a string")
    adapter = registry.get(target["type"])
    if not isinstance(target["path"], str) or not target["path"]:
        raise CandidateError("target path must be non-empty")
    _require_sha(target["baseline_sha256"], "baseline_sha256")
    _require_sha(document["candidate_sha256"], "candidate_sha256")
    operations = document["operations"]
    if not isinstance(operations, list) or not all(isinstance(item, dict) for item in operations):
        raise CandidateError("operations must be an array of objects")
    allowed_operation_fields = {"op", "path", "before_sha256", "value"}
    for operation in operations:
        if set(operation) - allowed_operation_fields:
            raise CandidateError("operation contains unknown fields")
        if operation.get("op") not in {"add", "replace"}:
            raise CandidateError("operation type must be add or replace")
        if not isinstance(operation.get("path"), str) or not operation["path"].startswith("/"):
            raise CandidateError("operation path must be a JSON pointer")
        if operation["op"] == "replace" and "before_sha256" in operation:
            _require_sha(operation["before_sha256"], "operation before_sha256")
    budgets = document["budgets"]
    if not isinstance(budgets, dict) or not isinstance(budgets.get("max_operations"), int) or budgets["max_operations"] < 1:
        raise CandidateError("budgets.max_operations must be a positive integer")
    if not 1 <= len(operations) <= budgets["max_operations"]:
        raise CandidateError("operation count is outside its budget")
    try:
        adapter.validate_operations(tuple(operations))
    except ValueError as error:
        raise CandidateError(str(error)) from error
    if document["adoption"] != "human_required":
        raise CandidateError("candidate adoption must require a human")
    if document["constitution_sha256"] != constitution_sha256():
        raise CandidateError("candidate does not bind the canonical Evolution Constitution")
    patterns = document.get("source_patterns", [])
    if not isinstance(patterns, list) or not all(isinstance(item, str) for item in patterns):
        raise CandidateError("source_patterns must be an array of strings")


def _require_sha(value: Any, field: str) -> None:
    if not isinstance(value, str) or len(value) != _SHA256_LENGTH or any(character not in "0123456789abcdef" for character in value):
        raise CandidateError(f"{field} must be a lowercase SHA-256 digest")


def _check_hash(content: bytes, expected: str, label: str) -> None:
    if hashlib.sha256(content).hexdigest() != expected:
        raise CandidateError(f"{label} artifact hash does not match the candidate manifest")
