"""Fail-closed validators for bounded non-code evolution targets."""

from __future__ import annotations

import json
import hashlib
import fnmatch
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .evolution import CONSTITUTION, CandidateError, constitution_sha256, load_candidate
from .decision import DecisionError, add_decision, init_ledger
from .models import Evidence, Finding, Severity, Status


class PolicyTargetError(ValueError):
    """Raised when a policy candidate weakens evidence or executes code."""


_SEVERITY = {"INFO": 0, "WARN": 1, "ERROR": 2}


def validate_policy_transition(target_type: str, baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    expected_schema = f"{target_type}/v1"
    if baseline.get("schema_version") != expected_schema or candidate.get("schema_version") != expected_schema:
        raise PolicyTargetError(f"{target_type} must use {expected_schema}")
    serialized = json.dumps(candidate, sort_keys=True).lower()
    if any(token in serialized for token in ('"command"', '"shell"', '"module"', '"python"', '"network"', '"exec"')):
        raise PolicyTargetError("policy candidates cannot contain executable fields")
    if target_type == "audit-profile":
        _audit_profile(baseline, candidate)
    elif target_type == "review-policy":
        _review_policy(baseline, candidate)
    elif target_type == "trace-validator":
        _trace_policy(baseline, candidate)
    elif target_type == "triage-policy":
        _triage_policy(candidate)
    else:
        raise PolicyTargetError(f"unsupported bounded policy target: {target_type}")


def apply_audit_profile(findings: list[Finding], profile: dict[str, Any]) -> list[Finding]:
    validate_policy_transition("audit-profile", profile, profile)
    result: list[Finding] = []
    for finding in findings:
        evidence_paths = [item.path for item in finding.evidence]
        if any(
            any(_glob(path, str(exclusion["pattern"])) for path in evidence_paths)
            for exclusion in profile.get("exclusions", [])
        ):
            continue
        setting = profile.get("rules", {}).get(finding.rule_id, {})
        if setting.get("enabled") is False:
            raise PolicyTargetError("audit profiles cannot hide existing findings")
        severity = Severity(setting.get("severity", finding.severity.value))
        sensitive_patterns = profile.get("path_policy", {}).get("sensitive", [])
        if any(any(_glob(path, str(pattern)) for pattern in sensitive_patterns) for path in evidence_paths):
            severity = Severity.ERROR
        if _SEVERITY[severity.value] < _SEVERITY[finding.severity.value]:
            raise PolicyTargetError("audit profiles cannot lower observed severity")
        result.append(Finding(finding.rule_id, finding.status, severity, finding.claim, finding.evidence, finding.remediation, finding.rule_version))
    return result


def review_policy_findings(metadata: dict[str, Any], policy: dict[str, Any]) -> list[Finding]:
    validate_policy_transition("review-policy", policy, policy)
    changed = metadata.get("changed_paths", [])
    declared = {row.get("id") for row in metadata.get("proofs", []) if isinstance(row, dict)}
    findings = []
    for category, patterns in policy.get("path_classes", {}).items():
        matching = [path for path in changed if any(_glob(path, pattern) for pattern in patterns)]
        if not matching:
            continue
        missing = sorted(set(policy.get("proof_requirements", {}).get(category, [])) - declared)
        if missing:
            findings.append(Finding(
                "AET-REV-POL-001", Status.FAIL, Severity.ERROR,
                f"{category} paths require additional declared proofs: {', '.join(missing)}",
                tuple(Evidence(path, detail=f"class={category}") for path in matching),
                "Add the required proofs to the reviewed intent contract before delivery.", "1",
            ))
    return findings


def evaluate_trace_validator(policy: dict[str, Any], artifact: Path) -> dict[str, Any]:
    validate_policy_transition("trace-validator", policy, policy)
    kind = policy["validator"]
    requirements = policy["requirements"]
    try:
        if kind == "junit":
            root = ET.parse(artifact).getroot()
            suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
            observed = {key: sum(int(suite.attrib.get(key, 0)) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
            failures = [name for name in ("failures", "errors", "skipped") if observed[name] > int(requirements.get(f"{name}_max", observed[name]))]
            if observed["tests"] < int(requirements.get("tests_min", 0)):
                failures.append("tests_min")
        elif kind in {"sarif", "coverage", "json"}:
            data = json.loads(artifact.read_text(encoding="utf-8"))
            observed, failures = _evaluate_json_validator(kind, data, requirements)
        else:
            raise PolicyTargetError(f"unsupported validator: {kind}")
    except (OSError, ValueError, ET.ParseError, json.JSONDecodeError) as error:
        return {"report_kind": "trace_validation", "status": "UNKNOWN", "validator": kind, "error": str(error), "artifact": str(artifact)}
    return {"report_kind": "trace_validation", "status": "PASS" if not failures else "FAIL", "validator": kind, "observed": observed, "failed_requirements": failures, "artifact": str(artifact)}


def propose_policy_candidate(*, target_type: str, target: Path, proposal: Path, output: Path, source_patterns: list[str] | None = None) -> dict[str, Any]:
    if target_type not in {"audit-profile", "review-policy", "trace-validator", "triage-policy"}:
        raise PolicyTargetError(f"unsupported policy target: {target_type}")
    baseline_bytes = target.read_bytes()
    baseline = _read_json(target)
    proposal_data = _read_json(proposal)
    operations = proposal_data.get("operations")
    if not isinstance(operations, list) or not 1 <= len(operations) <= 3:
        raise PolicyTargetError("policy proposal requires one to three bounded operations")
    candidate = json.loads(json.dumps(baseline))
    for operation in operations:
        _validate_policy_operation_path(target_type, str(operation.get("path", "")))
        _apply_pointer(candidate, operation)
    validate_policy_transition(target_type, baseline, candidate)
    candidate_bytes = _json_bytes(candidate)
    identity = str(target.resolve()).encode() + b"\0" + candidate_bytes
    candidate_id = f"CAND-{hashlib.sha256(identity).hexdigest()[:8].upper()}"
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / "candidate.policy.json"
    artifact.write_bytes(candidate_bytes)
    manifest = {
        "schema_version": "evolution-candidate/v2", "report_kind": "evolution_candidate", "candidate_id": candidate_id,
        "target": {"type": target_type, "path": str(target.resolve()), "baseline_sha256": _sha(baseline_bytes)},
        "candidate_artifact": artifact.name, "candidate_sha256": _sha(candidate_bytes), "source_patterns": source_patterns or [],
        "operations": operations, "budgets": {"max_operations": 3}, "adoption": "human_required", "constitution_sha256": constitution_sha256(),
    }
    _write_json(output / "candidate.json", manifest)
    return manifest


def evaluate_policy_suite(*, policy: dict[str, Any], target_type: str, suite: Path, project_root: Path | None = None) -> dict[str, Any]:
    document = _read_json(suite)
    if document.get("schema_version") != "policy-task/v1" or not isinstance(document.get("tasks"), list):
        raise PolicyTargetError("policy suite must use policy-task/v1")
    root = (project_root or Path.cwd()).resolve()
    rows = []
    for task in document["tasks"]:
        actual = _evaluate_policy_case(target_type, policy, task.get("input", {}), root)
        expected = task.get("expected", {})
        passed = isinstance(expected, dict) and all(actual.get(key) == value for key, value in expected.items())
        rows.append({"task_id": task.get("task_id"), "status": "PASS" if passed else "FAIL", "expected": expected, "actual": actual})
    passed = sum(row["status"] == "PASS" for row in rows)
    return {"suite_id": document.get("suite_id"), "task_count": len(rows), "passed": passed, "failed": len(rows) - passed, "tasks": rows}


def gate_policy_candidate(*, candidate: Path, core: Path, validation: Path, held_out: Path, adversarial: Path, output: Path, project_root: Path | None = None) -> dict[str, Any]:
    metadata, baseline, proposed = _policy_candidate_material(candidate)
    suites = {"core": core, "validation": validation, "held_out": held_out, "adversarial": adversarial}
    ids = {name: _suite_ids(path) for name, path in suites.items()}
    hard = ["policy suites overlap"] if any(ids[left] & ids[right] for left in ids for right in ids if left < right) else []
    metrics = {}
    for name, suite in suites.items():
        metrics[name] = {
            "baseline": evaluate_policy_suite(policy=baseline, target_type=metadata.target.target_type, suite=suite, project_root=project_root),
            "candidate": evaluate_policy_suite(policy=proposed, target_type=metadata.target.target_type, suite=suite, project_root=project_root),
        }
    if metrics["held_out"]["candidate"]["passed"] < metrics["held_out"]["baseline"]["passed"]:
        hard.append("held-out policy tasks regressed")
    if metrics["core"]["candidate"]["passed"] < metrics["core"]["baseline"]["passed"]:
        hard.append("core policy tasks regressed")
    if metrics["adversarial"]["candidate"]["failed"]:
        hard.append("adversarial policy tasks failed")
    if metrics["validation"]["candidate"]["passed"] <= metrics["validation"]["baseline"]["passed"]:
        hard.append("validation policy tasks did not improve")
    result = {
        "schema_version": "policy-gate/v1", "report_kind": "policy_evolution_gate", "target_type": metadata.target.target_type,
        "candidate_id": metadata.candidate_id, "baseline_sha256": metadata.target.baseline_sha256,
        "candidate_sha256": metadata.candidate_sha256, "constitution_sha256": constitution_sha256(),
        "suite_hashes": {name: _sha(path.read_bytes()) for name, path in suites.items()},
        "status": "PASS" if not hard else "FAIL", "hard_gate_failures": hard, "metrics": metrics,
    }
    _write_json(output, result)
    return result


def replay_policy_candidate(*, candidate: Path, suite: Path, output: Path, project_root: Path | None = None) -> dict[str, Any]:
    metadata, baseline, proposed = _policy_candidate_material(candidate)
    result = {
        "schema_version": "policy-replay/v1", "report_kind": "policy_evolution_replay",
        "candidate_id": metadata.candidate_id, "target_type": metadata.target.target_type,
        "suite_sha256": _sha(suite.read_bytes()),
        "baseline": evaluate_policy_suite(policy=baseline, target_type=metadata.target.target_type, suite=suite, project_root=project_root),
        "candidate": evaluate_policy_suite(policy=proposed, target_type=metadata.target.target_type, suite=suite, project_root=project_root),
    }
    _write_json(output, result)
    return result


def stage_policy_candidate(*, candidate: Path, gate: Path, output: Path) -> dict[str, Any]:
    metadata, _, _ = _policy_candidate_material(candidate)
    _verify_policy_gate(_read_json(gate), metadata)
    destination = output / metadata.candidate_id
    if destination.exists():
        raise PolicyTargetError(f"staged candidate already exists: {destination}")
    shutil.copytree(candidate, destination)
    shutil.copy2(gate, destination / "gate.json")
    return {"report_kind": "policy_evolution_stage", "status": "PASS", "candidate_id": metadata.candidate_id, "path": str(destination)}


def adopt_policy_candidate(*, candidate: Path, gate: Path, yes: bool, ledger: Path | None = None) -> dict[str, Any]:
    if not yes:
        raise PolicyTargetError("policy adoption requires explicit human --yes authorization")
    metadata, _, proposed = _policy_candidate_material(candidate)
    _verify_policy_gate(_read_json(gate), metadata)
    target = Path(metadata.target.path)
    if _sha(target.read_bytes()) != metadata.target.baseline_sha256:
        raise PolicyTargetError("policy target changed after proposal")
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
        sources = [str((candidate / "candidate.json").resolve().relative_to(root)), str(gate.resolve().relative_to(root))]
        add_decision(prepared_ledger, identifier=f"DEC-{metadata.candidate_id}", claim=f"Adopt evidence-gated {metadata.target.target_type} candidate {metadata.candidate_id}.", evidence_state="EVIDENCED", state="ACCEPTED", sources=sources, supersedes=[])
    except (DecisionError, ValueError) as error:
        raise PolicyTargetError(f"Decision Ledger rejected policy adoption: {error}") from error
    baseline_bytes = target.read_bytes()
    try:
        _atomic_bytes(target, _json_bytes(proposed))
        prepared_ledger.replace(ledger_path)
    except OSError as error:
        _atomic_bytes(target, baseline_bytes)
        raise PolicyTargetError(f"policy adoption was rolled back: {error}") from error
    return {"report_kind": "policy_evolution_adoption", "status": "PASS", "candidate_id": metadata.candidate_id, "target_type": metadata.target.target_type, "target": str(target), "ledger": str(ledger_path)}


def _audit_profile(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    before_rules, after_rules = baseline.get("rules", {}), candidate.get("rules", {})
    if not isinstance(before_rules, dict) or not isinstance(after_rules, dict):
        raise PolicyTargetError("audit-profile rules must be objects")
    for identifier, before in before_rules.items():
        after = after_rules.get(identifier)
        if not isinstance(after, dict):
            raise PolicyTargetError(f"audit profile deleted rule {identifier}")
        if before.get("enabled", True) and not after.get("enabled", True):
            raise PolicyTargetError(f"audit profile disabled active rule {identifier}")
        if _SEVERITY.get(str(after.get("severity", "INFO")), -1) < _SEVERITY.get(str(before.get("severity", "INFO")), -1):
            raise PolicyTargetError(f"audit profile reduced severity for {identifier}")
    before_exclusions = baseline.get("exclusions", [])
    after_exclusions = candidate.get("exclusions", [])
    if not isinstance(before_exclusions, list) or not isinstance(after_exclusions, list):
        raise PolicyTargetError("audit profile exclusions must be arrays")
    if any(exclusion not in before_exclusions for exclusion in after_exclusions):
        raise PolicyTargetError("an evolution candidate cannot add audit exclusions")
    for exclusion in after_exclusions:
        if not isinstance(exclusion, dict) or exclusion.get("pattern") in {"*", "**", "**/*"} or not str(exclusion.get("reason", "")).strip():
            raise PolicyTargetError("audit profile contains an unbounded or unexplained exclusion")


def _review_policy(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    before_budget, after_budget = baseline.get("changed_path_budget"), candidate.get("changed_path_budget")
    if not isinstance(before_budget, int) or not isinstance(after_budget, int) or after_budget > before_budget:
        raise PolicyTargetError("review policy cannot expand the changed-path budget")
    for field in ("path_classes", "proof_requirements"):
        before, after = baseline.get(field, {}), candidate.get(field, {})
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise PolicyTargetError(f"review policy {field} must be an object")
        for key, values in before.items():
            if not set(values) <= set(after.get(key, [])):
                raise PolicyTargetError(f"review policy removed {field} constraints for {key}")


def _trace_policy(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    if candidate.get("validator") not in {"junit", "sarif", "coverage", "json"}:
        raise PolicyTargetError("trace validator must use a built-in safe parser")
    if candidate.get("validator") != baseline.get("validator"):
        raise PolicyTargetError("trace validator type cannot change inside one candidate")
    before, after = baseline.get("requirements", {}), candidate.get("requirements", {})
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise PolicyTargetError("trace validator requirements must be objects")
    for key, value in before.items():
        if key.endswith("_max") and int(after.get(key, value)) > int(value):
            raise PolicyTargetError(f"trace validator loosened {key}")
        if key.endswith("_min") and float(after.get(key, value)) < float(value):
            raise PolicyTargetError(f"trace validator loosened {key}")


def _triage_policy(candidate: dict[str, Any]) -> None:
    forbidden = {"status", "statuses", "hide", "hide_findings", "suppress", "remove", "evidence"}
    if forbidden & set(candidate):
        raise PolicyTargetError("triage policy may rank findings but cannot rewrite, hide, or remove them")
    weights = candidate.get("weights")
    if not isinstance(weights, dict) or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 for value in weights.values()):
        raise PolicyTargetError("triage weights must be non-negative numbers")


def _evaluate_json_validator(kind: str, data: Any, requirements: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    if kind == "sarif":
        results = [item for run in data.get("runs", []) for item in run.get("results", [])]
        errors = sum(item.get("level") == "error" for item in results)
        observed = {"errors": errors, "results": len(results)}
        failures = ["errors_max"] if errors > int(requirements.get("errors_max", errors)) else []
    elif kind == "coverage":
        percent = float(data.get("totals", {}).get("percent_covered", 0))
        observed = {"percent_covered": percent}
        failures = ["percent_covered_min"] if percent < float(requirements.get("percent_covered_min", 0)) else []
    else:
        pointer = str(requirements.get("pointer", ""))
        expected = requirements.get("equals")
        current = data
        for part in [item for item in pointer.split("/") if item]:
            current = current[part]
        observed = {"value": current}
        failures = ["equals"] if current != expected else []
    return observed, failures


def _policy_candidate_material(candidate: Path) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    try:
        metadata = load_candidate(candidate)
    except CandidateError as error:
        raise PolicyTargetError(str(error)) from error
    target = Path(metadata.target.path)
    if not CONSTITUTION.permits_target(str(target)):
        raise PolicyTargetError("Evolution Constitution forbids this policy target")
    baseline = _read_json(target)
    proposed = _read_json(candidate / str(metadata.candidate_artifact))
    if _sha(target.read_bytes()) != metadata.target.baseline_sha256:
        raise PolicyTargetError("policy baseline hash changed")
    validate_policy_transition(metadata.target.target_type, baseline, proposed)
    reconstructed = json.loads(json.dumps(baseline))
    for operation in metadata.operations:
        _validate_policy_operation_path(metadata.target.target_type, str(operation.get("path", "")))
        _apply_pointer(reconstructed, operation)
    if _json_bytes(reconstructed) != _json_bytes(proposed):
        raise PolicyTargetError("policy artifact does not match its bounded Patch IR")
    return metadata, baseline, proposed


def _evaluate_policy_case(target_type: str, policy: dict[str, Any], value: dict[str, Any], root: Path) -> dict[str, Any]:
    if target_type == "review-policy":
        changed = value.get("changed_paths", [])
        provided = set(value.get("provided_proofs", []))
        required: set[str] = set()
        for category, patterns in policy.get("path_classes", {}).items():
            if any(any(_glob(path, pattern) for pattern in patterns) for path in changed):
                required.update(policy.get("proof_requirements", {}).get(category, []))
        missing = sorted(required - provided)
        return {"compliant": not missing and len(changed) <= policy.get("changed_path_budget", 0), "missing_proofs": missing}
    if target_type == "audit-profile":
        finding = value.get("finding", {})
        setting = policy.get("rules", {}).get(finding.get("rule_id"), {"enabled": True, "severity": finding.get("severity")})
        return {"enabled": setting.get("enabled", True), "severity": setting.get("severity", finding.get("severity"))}
    if target_type == "trace-validator":
        artifact = (root / value["artifact"]).resolve()
        return {"status": evaluate_trace_validator(policy, artifact)["status"]}
    if target_type == "triage-policy":
        findings = value.get("findings", [])
        weights = policy.get("weights", {})
        critical = policy.get("critical_paths", [])
        severity = {"ERROR": 3, "WARN": 2, "INFO": 1}
        scored = []
        for row in findings:
            path = str(row.get("path", ""))
            score = severity.get(row.get("severity"), 0) * float(weights.get("severity", 0))
            if any(_glob(path, pattern) for pattern in critical):
                score += float(weights.get("critical_path", 0))
            scored.append((score, str(row.get("rule_id"))))
        return {"order": [identifier for _, identifier in sorted(scored, key=lambda item: (-item[0], item[1]))]}
    raise PolicyTargetError(f"unsupported policy evaluator: {target_type}")


def _apply_pointer(document: dict[str, Any], operation: Any) -> None:
    if not isinstance(operation, dict) or operation.get("op") not in {"add", "replace"} or not isinstance(operation.get("path"), str) or not operation["path"].startswith("/") or "value" not in operation:
        raise PolicyTargetError("invalid bounded JSON Patch operation")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in operation["path"].split("/")[1:]]
    current: Any = document
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise PolicyTargetError("policy operation path does not exist")
        current = current[part]
    leaf = parts[-1]
    if not isinstance(current, dict) or (operation["op"] == "replace" and leaf not in current):
        raise PolicyTargetError("policy operation cannot replace a missing field")
    current[leaf] = operation["value"]


def _validate_policy_operation_path(target_type: str, path: str) -> None:
    prefixes = {
        "audit-profile": ("/rules/", "/path_policy/", "/exclusions"),
        "review-policy": ("/changed_path_budget", "/path_classes/", "/proof_requirements/"),
        "trace-validator": ("/requirements/",),
        "triage-policy": ("/weights/", "/critical_paths"),
    }
    if not any(path == prefix or path.startswith(prefix) for prefix in prefixes.get(target_type, ())):
        raise PolicyTargetError(f"{target_type} operation path is outside its allowlist: {path}")


def _verify_policy_gate(gate: dict[str, Any], metadata: Any) -> None:
    if gate.get("status") != "PASS" or gate.get("candidate_id") != metadata.candidate_id or gate.get("baseline_sha256") != metadata.target.baseline_sha256 or gate.get("candidate_sha256") != metadata.candidate_sha256 or gate.get("constitution_sha256") != constitution_sha256():
        raise PolicyTargetError("policy gate does not bind this candidate")


def _suite_ids(path: Path) -> set[str]:
    return {str(row.get("task_id")) for row in _read_json(path).get("tasks", []) if isinstance(row, dict)}


def _glob(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PolicyTargetError(f"invalid local JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise PolicyTargetError("policy JSON must contain an object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
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
