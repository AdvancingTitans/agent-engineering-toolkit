"""Read-only adapter from Portable Evidence Bundle v1 to Planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aet.bundle import BundleError, validate_bundle
from aet.improvement.analyzer.aggregator import aggregate_findings
from aet.improvement.constraint.generator import build_constraint

from .errors import PlanningError, PlanningErrorCode


@dataclass(frozen=True)
class PlanningBundleView:
    root: Path
    bundle_id: str
    content_hash: str
    workspace_id: str | None
    claims: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    policy: dict[str, Any]
    allowed_paths: list[str]
    protected_paths: list[str]
    verification_requirements: list[str]


def load_planning_bundle(path: Path) -> PlanningBundleView:
    """Reuse the authoritative Bundle validator without rewriting its records."""
    try:
        bundle = validate_bundle(Path(path))
    except BundleError as error:
        raise PlanningError(
            PlanningErrorCode.INVALID_BUNDLE,
            "Portable Evidence Bundle validation failed",
        ) from error
    manifest = bundle["manifest"]
    evidence_by_id = {item["id"]: item for item in bundle["evidence"]}
    finding_records = []
    for claim in bundle["claims"]:
        record = dict(claim)
        record["evidence_refs"] = sorted(
            {
                *claim.get("evidence_refs", []),
                *claim.get("counter_evidence_refs", []),
            }
        )
        finding_records.append(record)
    improvement_paths: set[str] = set()
    verification: set[str] = set()
    for issue in aggregate_findings(finding_records):
        paths = sorted(
            {
                path
                for reference in issue.evidence_refs
                for path in evidence_by_id.get(reference, {})
                .get("bindings", {})
                .get("paths", [])
                if isinstance(path, str) and path
            }
        )
        commands = sorted(
            {
                " ".join(command)
                for reference in issue.evidence_refs
                for command in [
                    evidence_by_id.get(reference, {})
                    .get("bindings", {})
                    .get("command")
                ]
                if isinstance(command, list)
                and command
                and all(isinstance(item, str) and item for item in command)
            }
        )
        constraint = build_constraint(
            issue,
            allowed_paths=paths,
            verification_requirements=commands,
        )
        improvement_paths.update(constraint.allowed_paths)
        verification.update(constraint.verification_requirements)
    for item in bundle["evidence"]:
        bindings = item.get("bindings", {})
        for path_value in bindings.get("paths", []):
            if isinstance(path_value, str) and path_value:
                improvement_paths.add(path_value)
        command = bindings.get("command")
        if (
            isinstance(command, list)
            and command
            and all(isinstance(part, str) and part for part in command)
        ):
            verification.add(" ".join(command))
    workspace_policy = bundle["policy"]["workspace_policy"]
    allowed = {
        _planning_pattern(item)
        for item in workspace_policy.get("allowed_paths", [])
    }
    allowed.update(improvement_paths)
    protected = {
        _planning_pattern(item)
        for item in workspace_policy.get("denied_paths", [])
    }
    task = manifest.get("task", {})
    return PlanningBundleView(
        root=Path(bundle["root"]),
        bundle_id=manifest["bundle"]["id"],
        content_hash=manifest["bundle"]["content_hash"],
        workspace_id=task.get("workspace_id"),
        claims=[dict(item) for item in bundle["claims"]],
        evidence=[dict(item) for item in bundle["evidence"]],
        observations=[dict(item) for item in bundle["observations"]],
        sources=[dict(item) for item in bundle["sources"]],
        conflicts=[dict(item) for item in bundle["conflicts"]],
        diagnostics=[dict(item) for item in bundle["diagnostics"]],
        policy=dict(bundle["policy"]),
        allowed_paths=sorted(allowed),
        protected_paths=sorted(protected),
        verification_requirements=sorted(verification),
    )


def _planning_pattern(value: str) -> str:
    normalized = value.rstrip("/")
    return normalized + "/**" if value.endswith("/") else normalized
