"""Command helpers for evidence-grounded improvements."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ...bundle import validate_bundle
from ..analyzer.aggregator import aggregate_findings
from ..candidate import CandidateSchema, parse_candidate, sanitize_candidate
from ..constraint.generator import build_constraint
from ..models.constraint import ImprovementConstraint
from ..models.issue import ImprovementIssue
from ..models.outcome import ImprovementOutcome
from ..models.verification import VerificationContract
from ..lifecycle import (
    compare_before_after,
    validate_proof,
    verify_improvement,
)
from ..renderer.agent_prompt import render_agent_prompt
from ..renderer.human_report import render_human_report
from ..validator import (
    detect_gaming,
    validate_grounding,
    validate_reference,
    validate_scope,
    validate_strength,
)


def doctor_bundle(bundle_path: Path) -> str:
    """Validate the existing Bundle and its evidence/Finding references."""
    validate_bundle(bundle_path)
    return (
        "Bundle loading OK\n"
        "Evidence reference OK\n"
        "Finding loading OK\n"
    )


def generate_improvements(
    bundle_path: Path,
    *,
    output: Path = Path(".aet/improvements"),
) -> dict[str, Any]:
    """Generate deterministic Issues, Constraints, and a human report."""
    bundle = validate_bundle(bundle_path)
    evidence_by_id = {item["id"]: item for item in bundle["evidence"]}
    finding_records: list[dict[str, Any]] = []
    for claim in bundle["claims"]:
        record = dict(claim)
        record["evidence_refs"] = sorted(
            {
                *claim.get("evidence_refs", []),
                *claim.get("counter_evidence_refs", []),
            }
        )
        freshness = {
            evidence_by_id[ref].get("freshness", {}).get("status")
            for ref in record["evidence_refs"]
            if ref in evidence_by_id
        }
        stale = sorted(
            status
            for status in freshness
            if status
            in {
                "relevant_files_changed",
                "workspace_changed",
                "environment_changed",
                "stale",
            }
        )
        if stale:
            record["freshness_status"] = stale[0]
        finding_records.append(record)
    issues = aggregate_findings(finding_records)
    missing_evidence = [
        issue.id for issue in issues if not issue.evidence_refs
    ]
    if missing_evidence:
        raise ValueError(
            "INVALID_IMPROVEMENT_INPUT: Evidence is missing for "
            + ", ".join(missing_evidence)
        )
    constraints = [
        build_constraint(
            issue,
            allowed_paths=_allowed_paths(issue, evidence_by_id),
            verification_requirements=_verification_requirements(
                issue,
                evidence_by_id,
            ),
        )
        for issue in issues
    ]
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "issues.json", [asdict(item) for item in issues])
    _write_json(
        output / "constraints.json",
        [asdict(item) for item in constraints],
    )
    report = render_human_report(issues, constraints)
    (output / "human-report.md").write_text(report, encoding="utf-8")
    return {
        "report_kind": "evidence_grounded_improvements",
        "status": "PASS",
        "bundle_id": bundle["manifest"]["bundle"]["id"],
        "issue_count": len(issues),
        "output": str(output),
    }


def generate_agent_prompt(
    issue_id: str,
    *,
    output: Path = Path(".aet/improvements"),
) -> dict[str, Any]:
    """Render one Agent task from persisted deterministic state."""
    issues, constraints = _load_state(output)
    issue = next((item for item in issues if item.id == issue_id), None)
    if issue is None:
        raise ValueError(f"INVALID_REFERENCE: Improvement Issue does not exist: {issue_id}")
    constraint = next(
        (item for item in constraints if item.issue_id == issue_id),
        None,
    )
    if constraint is None:
        raise ValueError(
            f"INVALID_REFERENCE: Improvement Constraint does not exist for: {issue_id}"
        )
    rendered = render_agent_prompt(constraint, issue)
    (output / "agent-task.md").write_text(rendered, encoding="utf-8")
    return {
        "report_kind": "improvement_agent_prompt",
        "status": "PROPOSED",
        "issue_id": issue.id,
        "constraint_id": constraint.id,
        "output": str(output / "agent-task.md"),
    }


def validate_candidate_file(
    candidate_path: Path,
    *,
    output: Path = Path(".aet/improvements"),
    root: Path = Path("."),
) -> dict[str, Any]:
    """Validate an Agent Candidate without giving it evidence authority."""
    raw = json.loads(candidate_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("NOT_ACTIONABLE: Candidate file must contain one object")
    CandidateSchema.validate(raw)
    candidate = sanitize_candidate(raw)
    parsed = parse_candidate(candidate)
    issues, constraints = _load_state(output)
    constraint = next(
        (
            item
            for item in constraints
            if item.id == parsed.constraint_id
        ),
        None,
    )
    if constraint is None:
        raise ValueError(
            "INVALID_REFERENCE: Improvement Constraint does not exist: "
            + parsed.constraint_id
        )
    issue = next(
        (item for item in issues if item.id == constraint.issue_id),
        None,
    )
    if issue is None:
        raise ValueError(
            f"INVALID_REFERENCE: Improvement Issue does not exist: {constraint.issue_id}"
        )
    inventory = {
        "evidence": [
            {"id": ref}
            for item in issues
            for ref in item.evidence_refs
        ],
        "findings": [
            {"id": ref}
            for item in issues
            for ref in item.finding_refs
        ],
        "claims": [
            {"id": ref}
            for item in issues
            for ref in item.finding_refs
        ],
    }
    results = [
        validate_grounding(candidate, inventory),
        validate_scope(candidate, constraint),
        validate_strength(candidate),
        detect_gaming(candidate),
        *[
            validate_reference(target, root=root)
            for target in candidate["targets"]
        ],
    ]
    valid = all(item.valid for item in results)
    report = {
        "report_kind": "improvement_candidate_validation",
        "status": "PROPOSED" if valid else "REJECTED",
        "candidate_id": parsed.id,
        "constraint_id": parsed.constraint_id,
        "valid": valid,
        "validations": [asdict(item) for item in results],
    }
    if valid:
        _write_json(output / "candidate.json", candidate)
        number = constraint.id.removeprefix("IC-")
        contract = VerificationContract(
            id=f"VC-{number}",
            commands=list(parsed.verification_plan),
            expected_results=[
                "exit_code=0" for _ in parsed.verification_plan
            ],
            proof_required=True,
            relevant_paths=sorted(
                {target.path for target in parsed.targets}
            ),
        )
        _write_json(output / "verification-contract.json", asdict(contract))
        _write_json(output / "candidate-validation.json", report)
    return report


def verify_issue(
    issue_id: str,
    *,
    output: Path = Path(".aet/improvements"),
) -> dict[str, Any]:
    """Verify one persisted Candidate and promote only with valid Proof."""
    issues, constraints = _load_state(output)
    issue = next((item for item in issues if item.id == issue_id), None)
    if issue is None:
        raise ValueError(f"INVALID_REFERENCE: Improvement Issue does not exist: {issue_id}")
    constraint = next(
        (item for item in constraints if item.issue_id == issue_id),
        None,
    )
    if constraint is None:
        raise ValueError(
            f"INVALID_REFERENCE: Improvement Constraint does not exist for: {issue_id}"
        )
    candidate = _read_object(output / "candidate.json", "Candidate")
    if candidate.get("constraint_id") != constraint.id:
        raise ValueError("INVALID_REFERENCE: Candidate does not bind the Issue Constraint")
    contract = VerificationContract(
        **_read_object(output / "verification-contract.json", "Verification Contract")
    )
    proof_path = output / "proof.json"
    proof = _read_object(proof_path, "Proof") if proof_path.is_file() else None
    proof_result = validate_proof(
        contract,
        proof,
        candidate_id=str(candidate.get("id", "")),
    )
    before = _optional_object(output / "before.json")
    after = _optional_object(output / "after.json")
    comparison = (
        compare_before_after(before, after)
        if before is not None and after is not None
        else {
            "status": "UNKNOWN",
            "improved": [],
            "regressed": [],
            "unchanged": [],
            "unknown": ["before_or_after_metrics_missing"],
        }
    )
    outcome = verify_improvement(
        contract,
        issue_id=issue.id,
        candidate_id=str(candidate.get("id", "")),
        proof=proof,
        before_metrics=before,
        after_metrics=after,
    )
    if comparison["status"] == "FAIL":
        outcome = ImprovementOutcome(
            issue_id=outcome.issue_id,
            candidate_id=outcome.candidate_id,
            status="implemented_unverified",
            before_metrics=outcome.before_metrics,
            after_metrics=outcome.after_metrics,
            proof_refs=[],
        )
    _write_json(output / "outcome.json", asdict(outcome))
    return {
        "report_kind": "improvement_verification",
        "status": outcome.status,
        "valid": outcome.status == "verified_improvement",
        "proof": asdict(proof_result),
        "comparison": comparison,
        "outcome": asdict(outcome),
    }


def compare_improvement_metrics(
    *,
    output: Path = Path(".aet/improvements"),
) -> dict[str, Any]:
    """Compare fixed before.json and after.json artifacts."""
    before = _read_object(output / "before.json", "Before metrics")
    after = _read_object(output / "after.json", "After metrics")
    comparison = compare_before_after(before, after)
    report = {
        "report_kind": "improvement_before_after_comparison",
        **comparison,
    }
    _write_json(output / "comparison.json", report)
    return report


def _allowed_paths(
    issue: ImprovementIssue,
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    return sorted(
        {
            path
            for ref in issue.evidence_refs
            for path in evidence_by_id.get(ref, {}).get("bindings", {}).get(
                "paths",
                [],
            )
            if isinstance(path, str) and path
        }
    )


def _verification_requirements(
    issue: ImprovementIssue,
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    return sorted(
        {
            " ".join(command)
            for ref in issue.evidence_refs
            for command in [
                evidence_by_id.get(ref, {}).get("bindings", {}).get("command")
            ]
            if isinstance(command, list)
            and command
            and all(isinstance(item, str) and item for item in command)
        }
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _load_state(
    output: Path,
) -> tuple[list[ImprovementIssue], list[ImprovementConstraint]]:
    issues_raw = json.loads((output / "issues.json").read_text(encoding="utf-8"))
    constraints_raw = json.loads(
        (output / "constraints.json").read_text(encoding="utf-8")
    )
    if not isinstance(issues_raw, list) or not isinstance(constraints_raw, list):
        raise ValueError("INVALID_IMPROVEMENT_INPUT: persisted state must be arrays")
    return (
        [ImprovementIssue(**item) for item in issues_raw],
        [ImprovementConstraint(**item) for item in constraints_raw],
    )


def _read_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"NOT_ACTIONABLE: {label} must be one JSON object")
    return value


def _optional_object(path: Path) -> dict[str, Any] | None:
    return _read_object(path, path.name) if path.is_file() else None
