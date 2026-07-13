"""Fixture-gated evolution for declarative audit rule packs."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from .decision import DecisionError, add_decision, init_ledger
from .discovery import discover_assets
from .evolution import CONSTITUTION, CandidateError, constitution_sha256, load_candidate
from .models import Status
from .rulepacks import RulePackError, load_rulepack, rulepack_metadata
from .rules import run_rules


class AuditEvolutionError(ValueError):
    """Raised when an audit-rule candidate cannot preserve its evidence boundary."""


def propose_audit_rule(*, patterns: Path, target: Path, output: Path) -> dict[str, Any]:
    source_patterns = _read(patterns).get("patterns")
    if not isinstance(source_patterns, list) or not source_patterns:
        raise AuditEvolutionError("audit-rule proposal requires mined patterns")
    kinds = {row.get("kind") for row in source_patterns if isinstance(row, dict)}
    if "MISSING_PACKAGE_SCRIPT" not in kinds and "AET-PKG-001" not in kinds and "FALSE_NEGATIVE" not in kinds:
        raise AuditEvolutionError("no supported reproducible audit-rule pattern was supplied")
    baseline_bytes = target.read_bytes()
    baseline = load_rulepack(target)
    if any(row["rule_id"] == "AET-PKG-001" for row in baseline["rules"]):
        raise AuditEvolutionError("target already contains the proposed package-script rule")
    rule = {
        "rule_id": "AET-PKG-001", "revision": 1, "target_kinds": ["repository"],
        "detector": {"type": "json_script_target_exists", "files": ["package.json"]},
        "result": {
            "status": "FAIL", "severity": "ERROR",
            "claim": "Package script points to a missing local target.",
            "remediation": "Create the script target or correct package.json.",
        },
        "safety": {"core": False, "minimum_severity": "ERROR"},
    }
    proposed = json.loads(json.dumps(baseline))
    proposed["rulepack_id"] = f"{baseline['rulepack_id']}-candidate"
    proposed["revision"] = baseline["revision"] + 1
    proposed["rules"].append(rule)
    proposed_bytes = _json_bytes(proposed)
    identity = str(target.resolve()).encode() + b"\0" + proposed_bytes
    candidate_id = f"CAND-{hashlib.sha256(identity).hexdigest()[:8].upper()}"
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / "candidate.rulepack.json"
    artifact.write_bytes(proposed_bytes)
    manifest = {
        "schema_version": "evolution-candidate/v2", "report_kind": "evolution_candidate",
        "candidate_id": candidate_id,
        "target": {"type": "audit-rule", "path": str(target.resolve()), "baseline_sha256": _sha(baseline_bytes)},
        "candidate_artifact": artifact.name, "candidate_sha256": _sha(proposed_bytes),
        "source_patterns": [str(row.get("pattern_id")) for row in source_patterns if isinstance(row, dict) and row.get("pattern_id")],
        "operations": [
            {"op": "replace", "path": "/rulepack_id", "value": proposed["rulepack_id"]},
            {"op": "replace", "path": "/revision", "value": proposed["revision"]},
            {"op": "add", "path": "/rules/-", "value": rule}
        ],
        "budgets": {"max_operations": 3, "max_rules_added": 1, "max_severity_reductions": 0},
        "adoption": "human_required",
        "constitution_sha256": constitution_sha256(),
    }
    _write(output / "candidate.json", manifest)
    _write(output / "source-manifest.json", {"report_kind": "evolution_candidate_sources", "pattern_ids": manifest["source_patterns"]})
    (output / "rationale.md").write_text("# Audit-rule candidate\n\nAdds a bounded detector for a reproduced package-script false negative. Human adoption remains required.\n", encoding="utf-8")
    return manifest


def replay_audit_rule(*, candidate: Path, suite: Path, output: Path, project_root: Path | None = None) -> dict[str, Any]:
    metadata, baseline, proposed = _candidate_material(candidate)
    baseline_result = evaluate_audit_suite(rulepack=baseline, suite=suite, project_root=project_root)
    candidate_result = evaluate_audit_suite(rulepack=proposed, suite=suite, project_root=project_root)
    result = {
        "schema_version": "audit-evolution-replay/v1", "report_kind": "audit_evolution_replay",
        "candidate_id": metadata.candidate_id, "target_type": "audit-rule", "suite_sha256": _sha(suite.read_bytes()),
        "baseline": baseline_result, "candidate": candidate_result,
        "delta": {
            "passed": candidate_result["passed"] - baseline_result["passed"],
            "false_negatives": candidate_result["false_negatives"] - baseline_result["false_negatives"],
            "false_positives": candidate_result["false_positives"] - baseline_result["false_positives"],
        },
    }
    _write(output, result)
    return result


def evaluate_audit_suite(*, rulepack: dict[str, Any], suite: Path, project_root: Path | None = None) -> dict[str, Any]:
    document = _read(suite)
    if document.get("schema_version") != "audit-task/v1" or not isinstance(document.get("tasks"), list):
        raise AuditEvolutionError(f"invalid audit suite: {suite}")
    root = (project_root or Path.cwd()).resolve()
    rows = []
    totals = {"true_positives": 0, "false_positives": 0, "false_negatives": 0}
    for task in document["tasks"]:
        fixture = (root / task["fixture"]["source"]).resolve()
        try:
            fixture.relative_to(root)
        except ValueError as error:
            raise AuditEvolutionError("audit fixture escapes the project root") from error
        started = time.perf_counter()
        first = run_rules(fixture, discover_assets(fixture), rulepack=rulepack)
        elapsed_ms = (time.perf_counter() - started) * 1000
        second = run_rules(fixture, discover_assets(fixture), rulepack=rulepack)
        normalized = [row.to_dict() for row in first]
        deterministic = normalized == [row.to_dict() for row in second]
        expected, forbidden = task["expected"]["must_emit"], task["expected"]["must_not_emit"]
        missing = [item for item in expected if not _matches_any(item, normalized)]
        unexpected = [row for row in normalized if any(_matches(item, row, partial=True) for item in forbidden)]
        totals["true_positives"] += len(expected) - len(missing)
        totals["false_negatives"] += len(missing)
        totals["false_positives"] += len(unexpected)
        quality = document["defaults"]["quality"]
        passed = not missing and len(unexpected) <= quality["max_unexpected_findings"] and (deterministic or not quality["require_deterministic_output"]) and elapsed_ms <= quality["max_runtime_ms"]
        keys = [f"{row['rule_id']}:{(row.get('evidence') or [{}])[0].get('path')}" for row in normalized]
        expected_keys = [f"{row.get('rule_id')}:{row.get('evidence_path')}" for row in expected]
        rows.append({"task_id": task["task_id"], "status": "PASS" if passed else "FAIL", "missing": missing, "unexpected": unexpected, "finding_keys": keys, "expected_keys": expected_keys, "deterministic": deterministic, "runtime_ms": round(elapsed_ms, 3)})
    passed = sum(row["status"] == "PASS" for row in rows)
    return {"suite_id": document["suite_id"], "partition": document["partition"], "task_count": len(rows), "passed": passed, "failed": len(rows) - passed, **totals, "tasks": rows, "rulepack": rulepack_metadata(rulepack)}


def gate_audit_rule(*, candidate: Path, core: Path, validation: Path, held_out: Path, adversarial: Path, output: Path, project_root: Path | None = None) -> dict[str, Any]:
    metadata, baseline, proposed = _candidate_material(candidate)
    suites = {"core": core, "validation": validation, "held_out": held_out, "adversarial": adversarial}
    task_sets = {name: _task_ids(path) for name, path in suites.items()}
    overlaps = sorted({item for left, left_ids in task_sets.items() for right, right_ids in task_sets.items() if left < right for item in left_ids & right_ids})
    hard: list[str] = []
    if overlaps:
        hard.append("audit suites overlap")
    root = (project_root or Path.cwd()).resolve()
    suite_cases = {name: _suite_case_fingerprints(path, root) for name, path in suites.items()}
    if suite_cases["validation"] & suite_cases["held_out"]:
        hard.append("audit validation and held-out reuse fixture/expectation cases")
    metrics = {}
    for name, path in suites.items():
        metrics[name] = {
            "baseline": evaluate_audit_suite(rulepack=baseline, suite=path, project_root=project_root),
            "candidate": evaluate_audit_suite(rulepack=proposed, suite=path, project_root=project_root),
        }
    for name in ("core", "held_out"):
        if metrics[name]["candidate"]["passed"] < metrics[name]["baseline"]["passed"]:
            hard.append(f"{name} regressed")
    for name, comparison in metrics.items():
        baseline_tasks = {row["task_id"]: row for row in comparison["baseline"]["tasks"]}
        for candidate_task in comparison["candidate"]["tasks"]:
            before = baseline_tasks[candidate_task["task_id"]]
            unapproved = set(candidate_task["finding_keys"]) - set(before["finding_keys"]) - set(candidate_task["expected_keys"])
            if unapproved:
                hard.append(f"{name} introduced unexpected findings in {candidate_task['task_id']}")
            if before["deterministic"] and not candidate_task["deterministic"]:
                hard.append(f"{name} determinism regressed in {candidate_task['task_id']}")
        if comparison["candidate"]["false_positives"] > comparison["baseline"]["false_positives"]:
            hard.append(f"{name} false positives increased")
        if name in {"core", "held_out", "adversarial"} and comparison["candidate"]["false_negatives"] > comparison["baseline"]["false_negatives"]:
            hard.append(f"{name} false negatives increased")
        baseline_runtime = sum(row["runtime_ms"] for row in comparison["baseline"]["tasks"])
        candidate_runtime = sum(row["runtime_ms"] for row in comparison["candidate"]["tasks"])
        if candidate_runtime > baseline_runtime * 1.25 + 50:
            hard.append(f"{name} runtime budget exceeded")
    if metrics["adversarial"]["candidate"]["failed"]:
        hard.append("adversarial constitution suite failed")
    improvement = metrics["validation"]["candidate"]["passed"] > metrics["validation"]["baseline"]["passed"]
    if not improvement:
        hard.append("validation did not improve")
    status = "PASS" if not hard else "FAIL"
    result = {
        "schema_version": "audit-evolution-gate/v1", "report_kind": "audit_evolution_gate",
        "candidate_id": metadata.candidate_id, "target_type": "audit-rule",
        "baseline_sha256": metadata.target.baseline_sha256, "candidate_sha256": metadata.candidate_sha256,
        "constitution_sha256": constitution_sha256(), "status": status, "hard_gate_failures": hard,
        "suite_hashes": {name: _sha(path.read_bytes()) for name, path in suites.items()}, "metrics": metrics,
        "acceptance": "core and held-out do not regress; validation improves; adversarial constitution passes; human adoption remains required",
    }
    _write(output, result)
    return result


def _suite_case_fingerprints(path: Path, project_root: Path) -> set[str]:
    document = _read(path)
    cases: set[str] = set()
    for task in document.get("tasks", []):
        fixture = str(task.get("fixture", {}).get("source", ""))
        fixture_root = (project_root / fixture).resolve()
        try:
            fixture_root.relative_to(project_root)
        except ValueError as error:
            raise AuditEvolutionError("audit fixture escapes the project root") from error
        tree = hashlib.sha256()
        for item in sorted(entry for entry in fixture_root.rglob("*") if entry.is_file()):
            tree.update(item.relative_to(fixture_root).as_posix().encode())
            tree.update(b"\0")
            tree.update(item.read_bytes())
            tree.update(b"\0")
        expected = task.get("expected")
        cases.add("fixture-tree:" + tree.hexdigest())
        payload = {"fixture_tree": tree.hexdigest(), "expected": expected}
        cases.add("case:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
    return cases


def stage_audit_rule(*, candidate: Path, gate: Path, output: Path) -> dict[str, Any]:
    metadata, _, _ = _candidate_material(candidate)
    gate_data = _read(gate)
    _verify_gate(gate_data, metadata)
    destination = output / metadata.candidate_id
    if destination.exists():
        raise AuditEvolutionError(f"staged candidate already exists: {destination}")
    shutil.copytree(candidate, destination)
    shutil.copy2(gate, destination / "gate.json")
    return {"report_kind": "audit_evolution_stage", "status": "PASS", "candidate_id": metadata.candidate_id, "path": str(destination)}


def adopt_audit_rule(*, candidate: Path, gate: Path, shadow_aggregate: Path | None, yes: bool, ledger: Path | None = None) -> dict[str, Any]:
    if not yes:
        raise AuditEvolutionError("audit-rule adoption requires explicit human --yes authorization")
    metadata, _, proposed = _candidate_material(candidate)
    gate_data = _read(gate)
    _verify_gate(gate_data, metadata)
    if shadow_aggregate is None:
        raise AuditEvolutionError("audit-rule adoption requires adoption-grade shadow evidence")
    shadow = _read(shadow_aggregate)
    if (
        shadow.get("status") != "PASS" or shadow.get("adoption_grade") is not True
        or shadow.get("candidate_rulepack_sha256") != metadata.candidate_sha256
        or int(shadow.get("run_count", 0)) < 20 or int(shadow.get("repository_count", 0)) < 5
        or int(shadow.get("date_count", 0)) < 3 or int(shadow.get("false_positive_count", 1)) != 0
        or int(shadow.get("unconfirmed_count", 1)) != 0
    ):
        raise AuditEvolutionError("shadow aggregate is not adoption-grade evidence for this candidate")
    target = Path(metadata.target.path)
    if _sha(target.read_bytes()) != metadata.target.baseline_sha256:
        raise AuditEvolutionError("audit rule pack changed after proposal")
    root = Path.cwd().resolve()
    ledger_path = (ledger or root / ".aet/learn/asset-decision-ledger.json").resolve()
    prepared_ledger = ledger_path.with_suffix(ledger_path.suffix + f".{metadata.candidate_id}.prepared")
    try:
        prepared_ledger.parent.mkdir(parents=True, exist_ok=True)
        if prepared_ledger.exists():
            prepared_ledger.unlink()
        if ledger_path.exists():
            shutil.copy2(ledger_path, prepared_ledger)
        else:
            init_ledger(prepared_ledger)
        sources = [str((candidate / "candidate.json").resolve().relative_to(root)), str(gate.resolve().relative_to(root)), str(shadow_aggregate.resolve().relative_to(root))]
        add_decision(prepared_ledger, identifier=f"DEC-{metadata.candidate_id}", claim=f"Adopt evidence-gated audit-rule candidate {metadata.candidate_id}.", evidence_state="EVIDENCED", state="ACCEPTED", sources=sources, supersedes=[])
    except (DecisionError, ValueError) as error:
        raise AuditEvolutionError(f"Decision Ledger rejected audit-rule adoption: {error}") from error
    baseline_bytes = target.read_bytes()
    try:
        _atomic_bytes(target, _json_bytes(proposed))
        prepared_ledger.replace(ledger_path)
    except OSError as error:
        _atomic_bytes(target, baseline_bytes)
        raise AuditEvolutionError(f"audit-rule adoption was rolled back: {error}") from error
    return {"report_kind": "audit_evolution_adoption", "status": "PASS", "candidate_id": metadata.candidate_id, "target": str(target), "ledger": str(ledger_path)}


def aggregate_shadow_audits(*, reports: Path, confirmations: Path, output: Path, minimum_repositories: int = 5, minimum_runs: int = 20, minimum_dates: int = 3) -> dict[str, Any]:
    rows = []
    for path in sorted(reports.rglob("*.json")):
        value = _read(path)
        if value.get("report_kind") == "audit_shadow":
            rows.append((path, value))
    confirmation_data = _read(confirmations)
    confirmations_by_key = {
        (str(row.get("shadow_sha256")), str(row.get("finding_key"))): str(row.get("outcome"))
        for row in confirmation_data.get("confirmations", []) if isinstance(row, dict)
    }
    repositories = {str(row.get("repository_fingerprint")) for _, row in rows if row.get("repository_fingerprint") not in {None, "UNKNOWN"}}
    dates = {str(row.get("generated_at", ""))[:10] for _, row in rows if row.get("generated_at")}
    added = []
    false_positives = []
    unconfirmed = []
    candidate_hashes = {str(row.get("candidate_engine", {}).get("rulepack_sha256")) for _, row in rows if row.get("candidate_engine", {}).get("rulepack_sha256")}
    for path, row in rows:
        digest = _sha(path.read_bytes())
        for finding in row.get("diff", {}).get("added_findings", []):
            evidence = (finding.get("evidence") or [{}])[0]
            key = f"{finding.get('rule_id')}:{evidence.get('path')}:{evidence.get('line')}"
            outcome = confirmations_by_key.get((digest, key))
            added.append({"shadow_sha256": digest, "finding_key": key, "outcome": outcome})
            if outcome == "false-positive":
                false_positives.append(key)
            elif outcome != "confirmed":
                unconfirmed.append(key)
    failures = []
    if len(rows) < minimum_runs:
        failures.append("minimum shadow runs not reached")
    if len(repositories) < minimum_repositories:
        failures.append("minimum repository diversity not reached")
    if len(dates) < minimum_dates:
        failures.append("minimum date diversity not reached")
    if unconfirmed:
        failures.append("new shadow findings remain unconfirmed")
    if false_positives:
        failures.append("confirmed shadow false positives exist")
    if len(candidate_hashes) != 1:
        failures.append("shadow runs do not bind one candidate rule pack")
    result = {
        "schema_version": "audit-shadow-aggregate/v1", "report_kind": "audit_shadow_aggregate",
        "status": "PASS" if not failures else "INCONCLUSIVE", "adoption_grade": not failures,
        "run_count": len(rows), "repository_count": len(repositories), "date_count": len(dates),
        "added_findings": added, "false_positive_count": len(false_positives), "unconfirmed_count": len(unconfirmed),
        "candidate_rulepack_sha256": next(iter(candidate_hashes), None),
        "hard_gate_failures": failures,
        "thresholds": {"minimum_runs": minimum_runs, "minimum_repositories": minimum_repositories, "minimum_dates": minimum_dates},
    }
    _write(output, result)
    return result


def _candidate_material(candidate: Path) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    try:
        metadata = load_candidate(candidate)
        if metadata.target.target_type != "audit-rule":
            raise AuditEvolutionError("candidate is not an audit-rule target")
        target = Path(metadata.target.path)
        baseline = load_rulepack(target)
        proposed = load_rulepack(candidate / str(metadata.candidate_artifact))
    except (CandidateError, RulePackError, OSError) as error:
        raise AuditEvolutionError(f"invalid audit-rule candidate: {error}") from error
    baseline_rules = {row["rule_id"]: row for row in baseline["rules"]}
    proposed_rules = {row["rule_id"]: row for row in proposed["rules"]}
    if any(proposed_rules.get(identifier) != rule for identifier, rule in baseline_rules.items()):
        raise AuditEvolutionError("candidate changed or deleted an existing audit rule")
    added = set(proposed_rules) - set(baseline_rules)
    if len(added) > metadata.budgets.get("max_rules_added", 0):
        raise AuditEvolutionError("candidate exceeded the added-rule budget")
    reconstructed = json.loads(json.dumps(baseline))
    for operation in metadata.operations:
        _apply_candidate_operation(reconstructed, operation)
    if _json_bytes(reconstructed) != _json_bytes(proposed):
        raise AuditEvolutionError("candidate artifact does not match its bounded Patch IR")
    if not CONSTITUTION.permits_target(metadata.target.path):
        raise AuditEvolutionError("Evolution Constitution forbids this target")
    return metadata, baseline, proposed


def _apply_candidate_operation(document: dict[str, Any], operation: dict[str, Any]) -> None:
    allowed = {"/rulepack_id": "replace", "/revision": "replace", "/rules/-": "add"}
    path, action = operation.get("path"), operation.get("op")
    if allowed.get(str(path)) != action:
        raise AuditEvolutionError("audit-rule operation is outside the allowlist")
    if path == "/rules/-":
        document["rules"].append(operation.get("value"))
    else:
        document[str(path)[1:]] = operation.get("value")


def _matches_any(expected: dict[str, Any], findings: list[dict[str, Any]]) -> bool:
    return any(_matches(expected, row, partial=False) for row in findings)


def _matches(expected: dict[str, Any], finding: dict[str, Any], *, partial: bool) -> bool:
    if finding.get("rule_id") != expected.get("rule_id"):
        return False
    evidence = (finding.get("evidence") or [{}])[0]
    checks = {
        "status": finding.get("status"), "severity": finding.get("severity"),
        "evidence_path": evidence.get("path"),
    }
    for key, actual in checks.items():
        if key in expected and expected[key] != actual:
            return False
    if not partial and expected.get("evidence_line_required") and evidence.get("line") is None:
        return False
    if not partial and expected.get("remediation_required") and not finding.get("remediation"):
        return False
    return True


def _verify_gate(gate: dict[str, Any], metadata: Any) -> None:
    if gate.get("status") != "PASS" or gate.get("candidate_id") != metadata.candidate_id or gate.get("baseline_sha256") != metadata.target.baseline_sha256 or gate.get("candidate_sha256") != metadata.candidate_sha256 or gate.get("constitution_sha256") != constitution_sha256():
        raise AuditEvolutionError("gate does not bind this exact candidate and Constitution")


def _task_ids(path: Path) -> set[str]:
    return {str(row["task_id"]) for row in _read(path).get("tasks", [])}


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditEvolutionError(f"invalid local JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise AuditEvolutionError(f"JSON must contain an object: {path}")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_json_bytes(value))
    temporary.replace(path)


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _atomic_bytes(path: Path, value: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
