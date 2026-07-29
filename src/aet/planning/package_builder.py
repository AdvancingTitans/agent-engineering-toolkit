"""Atomic, deterministic Evidence-Linked Plan package construction."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .candidate_parser import strict_json_loads
from .errors import PlanningError, PlanningErrorCode
from .models import PlanningContext, ValidationResult, canonical_json_bytes
from .renderer import render_consumer_guide, render_plan_markdown


PLAN_FILES = {
    "request": "request.json",
    "context_summary": "context-summary.json",
    "plan": "plan.json",
    "plan_markdown": "plan.md",
    "references": "references.jsonl",
    "diagnostics": "diagnostics.jsonl",
    "consumer_guide": "consumer-guide.md",
    "skill": "skill/SKILL.md",
    "skill_plan": "skill/references/plan.md",
    "skill_authority": "skill/references/authority-boundary.md",
    "skill_source_map": "skill/references/source-map.json",
}


def build_plan_package(
    context: PlanningContext,
    result: ValidationResult,
    output_dir: Path,
    *,
    replace: bool = True,
) -> Path:
    """Write, seal, validate, and atomically publish one portable Plan."""
    destination = Path(output_dir).expanduser().resolve(strict=False)
    if destination == destination.parent:
        raise PlanningError(
            PlanningErrorCode.WRITE_ATTEMPT,
            "refusing to use a filesystem root as Plan output",
        )
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    try:
        plan = result.plan
        references = _references(context)
        _write_json(temporary / PLAN_FILES["request"], asdict(context.request))
        _write_json(
            temporary / PLAN_FILES["context_summary"],
            _context_summary(context),
        )
        _write_json(temporary / PLAN_FILES["plan"], plan)
        _write_text(
            temporary / PLAN_FILES["plan_markdown"],
            render_plan_markdown(plan),
        )
        _write_jsonl(temporary / PLAN_FILES["references"], references)
        _write_jsonl(
            temporary / PLAN_FILES["diagnostics"],
            plan["diagnostics"],
        )
        _write_text(
            temporary / PLAN_FILES["consumer_guide"],
            render_consumer_guide(plan),
        )
        _write_embedded_skill(temporary, plan, references)
        hashes = {
            relative: hashlib.sha256((temporary / relative).read_bytes()).hexdigest()
            for relative in sorted(PLAN_FILES.values())
        }
        manifest = {
            "schema_version": "plan-manifest/1.0",
            "plan_id": plan["plan_id"],
            "status": plan["status"],
            "authority": "PROPOSED",
            "producer": {
                "name": "agent-engineering-toolkit",
                "role": "deterministic-plan-package-builder",
            },
            "source_identity": plan["source_identity"],
            "bundle_identity": plan["bundle_identity"],
            "atlas_identity": plan["atlas_identity"],
            "contents": dict(sorted(PLAN_FILES.items())),
            "integrity": {"algorithm": "sha256", "file_hashes": hashes},
        }
        _write_json(temporary / "manifest.json", manifest)
        validate_plan_package(temporary)
        _publish(temporary, destination, replace=replace)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def validate_plan_package(path: Path) -> dict[str, Any]:
    root = _safe_root(Path(path))
    manifest = _read_object(root / "manifest.json", "manifest.json")
    if manifest.get("schema_version") != "plan-manifest/1.0":
        _invalid("unsupported Plan Manifest version")
    if manifest.get("authority") != "PROPOSED":
        _invalid("Plan Manifest authority must be PROPOSED")
    contents = manifest.get("contents")
    if not isinstance(contents, dict) or contents != dict(sorted(PLAN_FILES.items())):
        _invalid("Plan Manifest contents do not match the v1 package")
    hashes = manifest.get("integrity", {}).get("file_hashes")
    if (
        manifest.get("integrity", {}).get("algorithm") != "sha256"
        or not isinstance(hashes, dict)
        or set(hashes) != set(PLAN_FILES.values())
    ):
        _invalid("Plan Manifest integrity is invalid")
    actual = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and item.name != "manifest.json"
    }
    if actual != set(PLAN_FILES.values()):
        _invalid("Plan package file set does not match the Manifest")
    for relative, expected in hashes.items():
        _safe_relative(relative)
        raw = (root / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            _invalid(f"Plan package hash mismatch: {relative}")
    plan = _read_object(root / PLAN_FILES["plan"], "plan.json")
    request = _read_object(root / PLAN_FILES["request"], "request.json")
    if (
        plan.get("schema_version") != "evidence-linked-plan/1.0"
        or plan.get("authority") != "PROPOSED"
        or plan.get("plan_id") != manifest.get("plan_id")
        or plan.get("status") != manifest.get("status")
        or plan.get("request") != request
    ):
        _invalid("Plan, Request, and Manifest identities do not agree")
    references = _read_jsonl(root / PLAN_FILES["references"], "references.jsonl")
    reference_ids = {item.get("reference_id") for item in references}
    if None in reference_ids or len(reference_ids) != len(references):
        _invalid("Plan references must have unique IDs")
    for item in plan.get("edit_items", []):
        for reference in [
            *item.get("evidence_refs", []),
            *item.get("atlas_refs", []),
            *item.get("source_refs", []),
        ]:
            if reference not in reference_ids:
                _invalid(f"Plan edit reference is unresolved: {reference}")
    _assert_safe_tree(root)
    return {
        "schema_version": "plan-package-validation/1.0",
        "status": "PASS",
        "plan_id": plan["plan_id"],
        "plan_status": plan["status"],
        "authority": "PROPOSED",
        "file_count": len(actual) + 1,
        "root": str(root),
    }


def _references(context: PlanningContext) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    bundle_identity = context.request.bundle_identity
    for values, kind in (
        (context.relevant_claims, "CLAIM"),
        (context.relevant_evidence, "EVIDENCE"),
        (context.counter_evidence, "EVIDENCE"),
        (context.conflicts, "EVIDENCE"),
        (context.unknowns, "EVIDENCE"),
    ):
        for item in values:
            identifier = _identifier(item)
            if not identifier:
                continue
            records[identifier] = {
                "schema_version": "plan-reference/1.0",
                "reference_id": identifier,
                "kind": kind,
                "source_identity": bundle_identity,
                "target_id": identifier,
                "path": _first_path(item),
                "content_hash": item.get("integrity", {}).get("content_hash"),
                "status": _status(item),
                "strength": "EVIDENCE_BACKED",
                "limitations": list(item.get("limitations", [])),
            }
    for item in context.atlas_nodes:
        identifier = _identifier(item)
        if not identifier:
            continue
        records[identifier] = {
            "schema_version": "plan-reference/1.0",
            "reference_id": identifier,
            "kind": "ATLAS",
            "source_identity": context.request.atlas_identity,
            "target_id": identifier,
            "path": item.get("path"),
            "content_hash": item.get("content_hash"),
            "status": "UNKNOWN" if item.get("status") == "UNKNOWN" else "PASS",
            "strength": "EVIDENCE_BACKED",
            "limitations": list(item.get("limitations", [])),
        }
    for item in context.source_sites:
        records[item.source_id] = {
            "schema_version": "plan-reference/1.0",
            "reference_id": item.source_id,
            "kind": "SOURCE",
            "source_identity": context.workspace.workspace_id,
            "target_id": item.source_id,
            "path": item.path,
            "content_hash": item.content_hash,
            "status": (
                "CONFIRMED"
                if item.read_status == "CONFIRMED"
                else "STALE"
                if item.read_status == "STALE"
                else "UNKNOWN"
            ),
            "strength": (
                "SOURCE_CONFIRMED"
                if item.read_status == "CONFIRMED"
                else "NEEDS_EVIDENCE"
            ),
            "limitations": (
                []
                if item.read_status == "CONFIRMED"
                else [f"Current source read status is {item.read_status}."]
            ),
        }
    return [records[key] for key in sorted(records)]


def _context_summary(context: PlanningContext) -> dict[str, Any]:
    return {
        "schema_version": "planning-context-summary/1.0",
        "request_id": context.request.request_id,
        "workspace": asdict(context.workspace),
        "bundle_identity": context.request.bundle_identity,
        "atlas_identity": context.request.atlas_identity,
        "counts": {
            "claims": len(context.relevant_claims),
            "evidence": len(context.relevant_evidence),
            "counter_evidence": len(context.counter_evidence),
            "conflicts": len(context.conflicts),
            "unknowns": len(context.unknowns),
            "atlas_nodes": len(context.atlas_nodes),
            "source_sites": len(context.source_sites),
            "gaps": len(context.gaps),
        },
        "constraints": asdict(context.constraints),
        "gaps": [asdict(item) for item in context.gaps],
        "omitted": asdict(context.omitted),
    }


def _write_embedded_skill(
    root: Path,
    plan: Mapping[str, Any],
    references: list[dict[str, Any]],
) -> None:
    skill = root / "skill"
    refs = skill / "references"
    refs.mkdir(parents=True)
    _write_text(
        skill / "SKILL.md",
        "\n".join(
            [
                "---",
                f"name: aet-plan-{str(plan['plan_id']).casefold()}",
                "description: Consume one validated AET Evidence-Linked Plan.",
                "---",
                "",
                "# Plan-only implementation handoff",
                "",
                "Read `references/authority-boundary.md`, then `references/plan.md` and `references/source-map.json`.",
                "Treat the plan as `PROPOSED`. Do not claim implementation or verification from this package.",
                "Before changing a file, re-read the current source and stop if its hash or scope no longer matches.",
                "",
            ]
        ),
    )
    _write_text(refs / "plan.md", render_plan_markdown(plan))
    _write_text(
        refs / "authority-boundary.md",
        "# Authority boundary\n\nThis Skill contains a `PROPOSED` plan. Evidence remains authoritative in the source Bundle; execution and verification require separate explicit authorization and current Proof/Freshness.\n",
    )
    _write_json(
        refs / "source-map.json",
        {
            "schema_version": "plan-skill-source-map/1.0",
            "plan_id": plan["plan_id"],
            "references": references,
        },
    )


def _publish(temporary: Path, destination: Path, *, replace: bool) -> None:
    if destination.exists() or destination.is_symlink():
        if not replace:
            raise PlanningError(
                PlanningErrorCode.WRITE_ATTEMPT,
                "Plan output already exists",
            )
        if destination.is_symlink() or not destination.is_dir():
            raise PlanningError(
                PlanningErrorCode.WRITE_ATTEMPT,
                "existing Plan output must be a real directory",
            )
        backup = destination.with_name(
            f".{destination.name}.backup-{os.getpid()}"
        )
        if backup.exists():
            raise PlanningError(
                PlanningErrorCode.WRITE_ATTEMPT,
                "Plan output backup path already exists",
            )
        os.replace(destination, backup)
        try:
            os.replace(temporary, destination)
        except Exception:
            os.replace(backup, destination)
            raise
        shutil.rmtree(backup)
    else:
        os.replace(temporary, destination)


def _safe_root(path: Path) -> Path:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        _invalid("Plan package directory is unavailable", cause=error)
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        _invalid("Plan package root must be a real directory")
    return path.resolve(strict=True)


def _assert_safe_tree(root: Path) -> None:
    for item in root.rglob("*"):
        mode = item.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            _invalid("Plan package contains a symlink or special file")
        try:
            item.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as error:
            _invalid("Plan package path escapes its root", cause=error)


def _safe_relative(value: str) -> None:
    relative = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _invalid("Plan Manifest contains an unsafe path")


def _read_object(path: Path, label: str) -> dict[str, Any]:
    value = strict_json_loads(path.read_bytes(), label=label)
    if not isinstance(value, dict):
        _invalid(f"{label} must contain one object")
    return value


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_bytes().splitlines(), start=1):
        if not line.strip():
            continue
        value = strict_json_loads(line, label=f"{label}:{number}")
        if not isinstance(value, dict):
            _invalid(f"{label}:{number} must contain one object")
        rows.append(value)
    return rows


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"".join(canonical_json_bytes(item) for item in values)
    )


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def _identifier(value: Mapping[str, Any]) -> str | None:
    for key in ("id", "node_id", "reference_id"):
        if isinstance(value.get(key), str) and value[key]:
            return str(value[key])
    return None


def _first_path(value: Mapping[str, Any]) -> str | None:
    paths = value.get("bindings", {}).get("paths", [])
    if isinstance(paths, list) and paths and isinstance(paths[0], str):
        return paths[0]
    locator = value.get("locator")
    if isinstance(locator, Mapping) and isinstance(locator.get("path"), str):
        return str(locator["path"])
    return None


def _status(value: Mapping[str, Any]) -> str:
    status = str(
        value.get("freshness", {}).get("status")
        or value.get("status")
        or "unknown"
    ).casefold()
    if status in {"supported", "partially_supported", "current", "pass"}:
        return "PASS"
    if status in {"unsupported", "fail"}:
        return "FAIL"
    if status == "stale":
        return "STALE"
    if status == "not_applicable":
        return "NOT_APPLICABLE"
    return "UNKNOWN"


def _invalid(message: str, *, cause: Exception | None = None) -> None:
    error = PlanningError(PlanningErrorCode.INVALID_CANDIDATE, message)
    if cause is None:
        raise error
    raise error from cause
