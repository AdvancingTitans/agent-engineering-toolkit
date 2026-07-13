"""Deterministic diagnosis and human-gated Learn Task staging."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import stat
import tempfile
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .learn_contracts import validate_learn_task_v2


class QualityError(ValueError):
    """Raised when quality evidence cannot safely enter the staging loop."""


MAPPING_VERSION = "quality-mapping/v1"
DIAGNOSIS_SCHEMA_VERSION = "quality-diagnosis/v1"
DIAGNOSIS_REPORT_KIND = "quality_diagnosis"
STATUS_POLICY = "Input status is preserved; diagnosis and review routing never rewrite it."
_STATUSES = {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE", "INFRASTRUCTURE_ERROR"}
_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
_ROUTES = ("HIGH_RISK", "LOW_CONFIDENCE", "RULE_CONFLICT", "NEW_SCHEMA")
_MAPPING_FIELDS = {"candidate_repair_surface", "owner", "action", "confidence", "high_risk", "rule_conflict", "new_schema"}
_BUNDLE_LOCKS: dict[str, threading.Lock] = {}
_BUNDLE_LOCKS_GUARD = threading.Lock()
_DIRFD_SUPPORTED = (
    all(function in os.supports_dir_fd for function in (os.open, os.stat, os.rename, os.unlink))
    and os.stat in os.supports_follow_symlinks
    and hasattr(os, "O_NOFOLLOW")
)


def diagnose_report(report: Path, policy: Path, output: Path) -> dict[str, Any]:
    source = _read_object(report, "quality diagnosis input")
    mapping, mapping_sha256 = _load_policy(policy)
    observations = _observations(source)
    if not observations:
        raise QualityError("diagnosis input contains no failure phenomena")
    diagnoses = [_diagnose(item, mapping.get(item["phenomenon_code"])) for item in observations]
    diagnoses.sort(key=lambda item: (item["phenomenon_code"], item["status"], item["evidence_refs"]))
    result = {
        "schema_version": DIAGNOSIS_SCHEMA_VERSION,
        "report_kind": DIAGNOSIS_REPORT_KIND,
        "mapping_version": MAPPING_VERSION,
        "mapping_sha256": mapping_sha256,
        "source_report_kind": source["report_kind"],
        "diagnoses": diagnoses,
        "status_policy": STATUS_POLICY,
    }
    _atomic_json(output, result)
    return result


def promote_regression(*, badcase: Path, diagnosis: Path, policy: Path, output: Path) -> dict[str, Any]:
    case = _read_object(badcase, "badcase")
    diagnosed = _read_object(diagnosis, "quality diagnosis")
    mapping, mapping_sha256 = _load_policy(policy)
    _validate_badcase(case)
    _validate_diagnosis(diagnosed)
    diagnoses = diagnosed.get("diagnoses")
    if diagnosed.get("mapping_sha256") != mapping_sha256:
        raise QualityError("promotion requires a current deterministic quality diagnosis")
    matches = [item for item in diagnoses if isinstance(item, dict) and (item.get("phenomenon_code"), item.get("status")) == (case["phenomenon_code"], case["status"])]
    if len(matches) != 1:
        raise QualityError("badcase phenomenon is ambiguous")
    item = matches[0]
    if not all(isinstance(item.get(key), str) and item[key] for key in ("candidate_repair_surface", "owner", "action")):
        raise QualityError("badcase diagnosis is unconfirmed or has no explicit repair mapping")
    expected_mapping = mapping.get(case["phenomenon_code"])
    case_evidence_refs = sorted(set(_string_list(case["evidence_refs"], "badcase evidence_refs")))
    expected_decision = _diagnose({
        "phenomenon_code": case["phenomenon_code"],
        "status": case["status"],
        "evidence_refs": case_evidence_refs,
    }, expected_mapping) if expected_mapping is not None else None
    decision_fields = ("evidence_refs", "candidate_repair_surface", "confidence", "review_route", "owner", "action")
    if expected_decision is None or any(item.get(key) != expected_decision[key] for key in decision_fields):
        raise QualityError("diagnosis repair mapping does not match the supplied policy")
    fixture_source = _fixture_source(badcase, case["fixture"]["source"])
    fixture_sha256 = _tree_sha256(fixture_source)
    _reject_formal_partition(output)
    decision = {key: item[key] for key in decision_fields}
    identity = {
        "phenomenon_code": case["phenomenon_code"],
        "status": case["status"],
        "prompt": case["prompt"],
        "fixture_sha256": fixture_sha256,
        "policy": case["policy"],
        "expected_behavior": case["expected_behavior"],
        "runner": case.get("runner"),
        "diagnosis_decision": decision,
        "mapping_version": MAPPING_VERSION,
        "mapping_sha256": mapping_sha256,
    }
    digest = hashlib.sha256(_canonical(identity)).hexdigest()
    destination = output / digest
    observed_at = _utc_timestamp(case["observed_at"])
    quality = {
        "canonical_sha256": digest,
        "phenomenon_code": case["phenomenon_code"],
        "status": case["status"],
        "candidate_repair_surface": item["candidate_repair_surface"],
        "owner": item["owner"],
        "action": item["action"],
        "confidence": item["confidence"],
        "review_route": item["review_route"],
        "diagnosis_evidence_refs": item["evidence_refs"],
        "mapping_version": MAPPING_VERSION,
        "mapping_sha256": mapping_sha256,
        "representative_evidence": case_evidence_refs[:5],
        "first_seen": observed_at,
        "last_seen": observed_at,
        "support": 1,
        "source_badcase_ids": [case["badcase_id"]],
        "target_partition": "validation",
        "adoption": "human_review_required",
        "writes_formal_eval": False,
    }
    task: dict[str, Any] = {
        "schema_version": "2.0",
        "task_id": f"REG-{digest[:12].upper()}",
        "prompt": case["prompt"],
        "fixture": {"source": "fixture"},
        "policy": case["policy"],
        "expected_behavior": case["expected_behavior"],
    }
    if isinstance(case.get("runner"), dict):
        task["runner"] = case["runner"]
    task_failures = validate_learn_task_v2(task)
    if task_failures:
        raise QualityError("generated Learn Task v2 is invalid: " + "; ".join(task_failures))
    output = _prepare_output(output)
    destination = output / digest
    with _bundle_lock(output, digest):
        if destination.is_symlink():
            raise QualityError("canonical candidate destination cannot be a symbolic link")
        if destination.exists():
            with _anchored_bundle(output, digest) as (output_fd, bundle_fd, identity):
                if _tree_sha256_at(bundle_fd, "fixture") != fixture_sha256:
                    raise QualityError("canonical candidate fixture is missing or has changed")
                current = _read_object_at(bundle_fd, "task.json", "existing regression candidate")
                current_quality = _read_object_at(bundle_fd, "quality.json", "existing regression quality metadata")
                _validate_candidate_bundle(current, current_quality, digest)
                if current != task:
                    raise QualityError("canonical candidate task identity has changed")
                immutable_quality = {
                    "canonical_sha256", "phenomenon_code", "status", "candidate_repair_surface", "owner", "action",
                    "confidence", "review_route", "diagnosis_evidence_refs", "mapping_version", "mapping_sha256",
                    "target_partition", "adoption", "writes_formal_eval",
                }
                if any(current_quality.get(key) != quality.get(key) for key in immutable_quality):
                    raise QualityError("canonical candidate diagnosis identity has changed")
                identifiers = _string_list(current_quality["source_badcase_ids"], "candidate source_badcase_ids")
                if case["badcase_id"] in identifiers:
                    raise QualityError("duplicate badcase id is already represented")
                quality["source_badcase_ids"] = sorted(identifiers + [case["badcase_id"]])
                quality["support"] = len(quality["source_badcase_ids"])
                quality["representative_evidence"] = sorted(set(current_quality["representative_evidence"] + quality["representative_evidence"]))[:5]
                quality["first_seen"] = min(_utc_timestamp(current_quality["first_seen"]), observed_at)
                quality["last_seen"] = max(_utc_timestamp(current_quality["last_seen"]), observed_at)
                _assert_bundle_binding(output_fd, digest, identity)
                _replace_quality_sidecar_at(bundle_fd, quality)
                _assert_bundle_binding(output_fd, digest, identity)
        else:
            _publish_new_bundle(output, destination, fixture_source, fixture_sha256, task, quality)
    return task


def _load_policy(path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    policy = _read_object(path, "quality mapping policy")
    if set(policy) != {"schema_version", "mappings"} or policy.get("schema_version") != MAPPING_VERSION or not isinstance(policy.get("mappings"), dict):
        raise QualityError("quality policy must be an exact quality-mapping/v1 object")
    result: dict[str, dict[str, Any]] = {}
    for code, item in policy["mappings"].items():
        if not isinstance(code, str) or not code or not isinstance(item, dict) or set(item) != _MAPPING_FIELDS:
            raise QualityError("every quality mapping requires the exact versioned fields")
        if not all(isinstance(item.get(key), str) and item[key] for key in ("candidate_repair_surface", "owner", "action")):
            raise QualityError("repair surface, owner, and action must be explicit non-empty strings")
        if item.get("confidence") not in _CONFIDENCE or not all(isinstance(item.get(key), bool) for key in ("high_risk", "rule_conflict", "new_schema")):
            raise QualityError("quality confidence and review facts have invalid types")
        result[code] = item
    return result, hashlib.sha256(_canonical(policy)).hexdigest()


def _observations(source: dict[str, Any]) -> list[dict[str, Any]]:
    kind = source.get("report_kind")
    if not isinstance(kind, str) or not kind:
        raise QualityError("diagnosis input requires report_kind")
    if kind == "learning_experiences":
        rows = source.get("experiences")
        if not isinstance(rows, list):
            raise QualityError("learning_experiences requires experiences array")
        observations = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("deviations", []), list):
                raise QualityError("experience deviations must be an array")
            source_record = row.get("source", {})
            refs = [source_record.get("sha256")] if isinstance(source_record, dict) and isinstance(source_record.get("sha256"), str) else []
            represented: set[str] = set()
            phenomena = row.get("phenomena", [])
            if not isinstance(phenomena, list):
                raise QualityError("experience phenomena must be an array")
            for phenomenon in phenomena:
                if not isinstance(phenomenon, dict) or not isinstance(phenomenon.get("code"), str) or not phenomenon["code"] or phenomenon.get("status") not in _STATUSES:
                    raise QualityError("experience phenomenon requires a non-empty code and valid status")
                represented.add(phenomenon["code"])
                observations.append({"phenomenon_code": phenomenon["code"], "status": phenomenon["status"], "evidence_refs": refs})
            for deviation in row.get("deviations", []):
                if not isinstance(deviation, str) or not deviation:
                    raise QualityError("experience deviation must be a non-empty code")
                if deviation not in represented:
                    observations.append({"phenomenon_code": deviation, "status": "UNKNOWN", "evidence_refs": refs})
        return _deduplicate_observations(observations)
    if kind == "learning_patterns":
        patterns = source.get("patterns")
        if not isinstance(patterns, list):
            raise QualityError("learning_patterns requires patterns array")
        observations = []
        for pattern in patterns:
            if not isinstance(pattern, dict) or not isinstance(pattern.get("kind"), str) or not pattern["kind"]:
                raise QualityError("every pattern requires kind")
            observations.append({"phenomenon_code": pattern["kind"], "status": pattern.get("status", "UNKNOWN"), "evidence_refs": pattern.get("evidence_refs", []), "confidence": pattern.get("confidence")})
        return _deduplicate_observations(observations)
    findings = source.get("findings")
    if not isinstance(findings, list):
        raise QualityError("raw diagnosis input requires findings array")
    return [_finding_observation(item) for item in findings]


def _finding_observation(finding: Any) -> dict[str, Any]:
    if not isinstance(finding, dict):
        raise QualityError("every finding must be an object")
    code = finding.get("code", finding.get("rule_id"))
    status = finding.get("status")
    if not isinstance(code, str) or not code or status not in _STATUSES:
        raise QualityError("every finding requires a code and valid status")
    refs = finding.get("evidence_refs")
    if refs is None:
        evidence = finding.get("evidence", [])
        if not isinstance(evidence, list):
            raise QualityError("finding evidence must be an array")
        refs = [item.get("path") for item in evidence if isinstance(item, dict) and isinstance(item.get("path"), str)]
    result = {"phenomenon_code": code, "status": status, "evidence_refs": refs}
    for key in ("confidence", "high_risk", "rule_conflict", "new_schema"):
        if key in finding:
            result[key] = finding[key]
    return result


def _deduplicate_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["phenomenon_code"], row["status"])
        refs = _string_list(row.get("evidence_refs", []), "phenomenon evidence_refs")
        if key not in grouped:
            grouped[key] = {**row, "evidence_refs": refs}
        else:
            grouped[key]["evidence_refs"] = sorted(set(grouped[key]["evidence_refs"] + refs))
    return list(grouped.values())


def _diagnose(observation: dict[str, Any], mapping: dict[str, Any] | None) -> dict[str, Any]:
    status = observation.get("status")
    if status not in _STATUSES:
        raise QualityError("phenomenon status is invalid")
    refs = sorted(set(_string_list(observation.get("evidence_refs", []), "phenomenon evidence_refs")))
    declared = observation.get("confidence")
    if declared is not None and declared not in _CONFIDENCE:
        raise QualityError("phenomenon confidence is invalid")
    confidence = declared or (mapping["confidence"] if mapping else "LOW")
    facts = {}
    for key in ("high_risk", "rule_conflict", "new_schema"):
        value = observation.get(key, mapping[key] if mapping else False)
        if not isinstance(value, bool):
            raise QualityError(f"{key} must be an explicit boolean fact")
        facts[key] = value
    reasons = []
    if facts["high_risk"]:
        reasons.append("HIGH_RISK")
    if confidence == "LOW":
        reasons.append("LOW_CONFIDENCE")
    if facts["rule_conflict"]:
        reasons.append("RULE_CONFLICT")
    if facts["new_schema"]:
        reasons.append("NEW_SCHEMA")
    return {
        "phenomenon_code": observation["phenomenon_code"], "status": status, "evidence_refs": refs,
        "candidate_repair_surface": mapping["candidate_repair_surface"] if mapping else None,
        "confidence": confidence, "review_route": {"required": bool(reasons), "reasons": [route for route in _ROUTES if route in reasons]},
        "owner": mapping["owner"] if mapping else None, "action": mapping["action"] if mapping else None,
    }


def _validate_diagnosis(diagnosed: dict[str, Any]) -> None:
    top_level = {"schema_version", "report_kind", "mapping_version", "mapping_sha256", "source_report_kind", "diagnoses", "status_policy"}
    if set(diagnosed) != top_level:
        raise QualityError("quality diagnosis must contain the exact v1 fields")
    if diagnosed.get("schema_version") != DIAGNOSIS_SCHEMA_VERSION or diagnosed.get("report_kind") != DIAGNOSIS_REPORT_KIND or diagnosed.get("mapping_version") != MAPPING_VERSION:
        raise QualityError("promotion requires a quality-diagnosis/v1 artifact")
    mapping_sha256 = diagnosed.get("mapping_sha256")
    if not isinstance(mapping_sha256, str) or len(mapping_sha256) != 64 or any(character not in "0123456789abcdef" for character in mapping_sha256):
        raise QualityError("quality diagnosis mapping_sha256 is invalid")
    if not isinstance(diagnosed.get("source_report_kind"), str) or not diagnosed["source_report_kind"] or diagnosed.get("status_policy") != STATUS_POLICY:
        raise QualityError("quality diagnosis provenance fields are invalid")
    diagnoses = diagnosed.get("diagnoses")
    if not isinstance(diagnoses, list) or not diagnoses:
        raise QualityError("quality diagnosis requires at least one diagnosis")
    item_fields = {"phenomenon_code", "status", "evidence_refs", "candidate_repair_surface", "confidence", "review_route", "owner", "action"}
    identities: set[tuple[str, str]] = set()
    for item in diagnoses:
        if not isinstance(item, dict) or set(item) != item_fields:
            raise QualityError("every diagnosis must contain the exact v1 fields")
        code, status = item.get("phenomenon_code"), item.get("status")
        if not isinstance(code, str) or not code or status not in _STATUSES or (code, status) in identities:
            raise QualityError("diagnosis identity and status are invalid")
        identities.add((code, status))
        refs = _string_list(item.get("evidence_refs"), "diagnosis evidence_refs")
        if refs != sorted(set(refs)):
            raise QualityError("diagnosis evidence_refs must be canonical and unique")
        for key in ("candidate_repair_surface", "owner", "action"):
            if item.get(key) is not None and (not isinstance(item[key], str) or not item[key]):
                raise QualityError("diagnosis repair fields must be non-empty strings or null")
        if item.get("confidence") not in _CONFIDENCE:
            raise QualityError("diagnosis confidence is invalid")
        route = item.get("review_route")
        if not isinstance(route, dict) or set(route) != {"required", "reasons"} or not isinstance(route.get("required"), bool):
            raise QualityError("diagnosis review_route is invalid")
        reasons = route.get("reasons")
        if not isinstance(reasons, list) or any(reason not in _ROUTES for reason in reasons) or reasons != [route for route in _ROUTES if route in reasons] or route["required"] is not bool(reasons):
            raise QualityError("diagnosis review reasons are invalid")
    expected_order = sorted(diagnoses, key=lambda item: (item["phenomenon_code"], item["status"], item["evidence_refs"]))
    if diagnoses != expected_order:
        raise QualityError("diagnoses must use canonical order")


def _validate_badcase(case: dict[str, Any]) -> None:
    allowed = {"badcase_id", "phenomenon_code", "status", "confirmed", "reproducible", "deidentified", "target_partition", "prompt", "fixture", "policy", "expected_behavior", "runner", "evidence_refs", "observed_at", "duplicate_of"}
    if set(case) - allowed:
        raise QualityError("badcase contains unsupported fields")
    if not isinstance(case.get("badcase_id"), str) or not case["badcase_id"] or not isinstance(case.get("phenomenon_code"), str) or case.get("status") not in {"FAIL", "UNKNOWN"}:
        raise QualityError("badcase identity, phenomenon, and status are required")
    for flag in ("confirmed", "reproducible", "deidentified"):
        if case.get(flag) is not True:
            raise QualityError(f"badcase promotion requires {flag}=true")
    if case.get("duplicate_of") is not None:
        raise QualityError("duplicate badcases cannot be promoted")
    if case.get("target_partition") != "validation":
        raise QualityError("quality promotion accepts only validation candidates")
    if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
        raise QualityError("badcase prompt is required")
    fixture, policy, expected = case.get("fixture"), case.get("policy"), case.get("expected_behavior")
    if not isinstance(fixture, dict) or not isinstance(fixture.get("source"), str) or not fixture["source"] or not isinstance(policy, dict) or not isinstance(expected, dict) or not expected or not _meaningful(expected):
        raise QualityError("badcase requires executable fixture, policy, and expected_behavior")
    if "runner" in case and not isinstance(case["runner"], dict):
        raise QualityError("badcase runner must be an object")
    if not _string_list(case.get("evidence_refs"), "badcase evidence_refs"):
        raise QualityError("badcase requires representative evidence")
    _utc_timestamp(case.get("observed_at"))


def _utc_timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise QualityError("observed timestamp is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise QualityError("observed timestamp must be ISO-8601") from error
    if parsed.tzinfo is None:
        raise QualityError("observed timestamp requires timezone")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _reject_formal_partition(path: Path) -> None:
    if path.is_symlink():
        raise QualityError("quality promotion output cannot be a symbolic link")
    parts = [part.lower() for part in path.resolve().parts]
    protected = {"eval", "core", "held-out", "held_out", "adversarial"}
    if any(part in protected for part in parts) or any(parts[index:index + 2] == ["tests", "evolution"] for index in range(len(parts) - 1)):
        raise QualityError("quality promotion cannot write formal evaluation partitions")
    if path.exists() and not path.is_dir():
        raise QualityError("quality promotion output must be a staging directory")


def _fixture_source(badcase: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise QualityError("badcase fixture source must be a local relative path")
    declared = badcase.parent / relative
    if declared.is_symlink():
        raise QualityError("badcase fixture source cannot be a symbolic link")
    source = declared.resolve()
    parent = badcase.parent.resolve()
    if os.path.commonpath((source, parent)) != str(parent) or not source.is_dir():
        raise QualityError("badcase fixture source does not exist as a local directory")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise QualityError("badcase fixture source cannot contain symbolic links")
    return source


def _tree_sha256(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise QualityError("regression fixture directory is missing")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if path.is_symlink():
            raise QualityError("regression fixture cannot contain symbolic links")
        relative = path.relative_to(root).as_posix()
        digest.update(("D\0" if path.is_dir() else "F\0").encode())
        digest.update(relative.encode())
        digest.update(b"\0")
        if path.is_file():
            try:
                digest.update(b"X\0" if path.stat(follow_symlinks=False).st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) else b"N\0")
                digest.update(path.read_bytes())
            except OSError as error:
                raise QualityError(f"cannot read regression fixture: {error}") from error
    return digest.hexdigest()


def _meaningful(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(_meaningful(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and all(isinstance(key, str) and key and _meaningful(item) for key, item in value.items())
    return value is not None


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise QualityError(f"{label} must be an array of non-empty strings")
    return list(value)


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualityError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise QualityError(f"{label} must be a JSON object")
    return value


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as error:
        raise QualityError(f"quality input is not canonical JSON: {error}") from error


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise QualityError(f"cannot write quality artifact: {error}") from error


def _prepare_output(output: Path) -> Path:
    if output.is_symlink():
        raise QualityError("quality promotion output cannot be a symbolic link")
    try:
        output.mkdir(parents=True, exist_ok=True)
        resolved = output.resolve(strict=True)
    except OSError as error:
        raise QualityError(f"cannot prepare regression staging output: {error}") from error
    if not resolved.is_dir():
        raise QualityError("quality promotion output must resolve to a directory")
    return resolved


@contextmanager
def _bundle_lock(output: Path, digest: str):
    key = str(output / digest)
    with _BUNDLE_LOCKS_GUARD:
        local_lock = _BUNDLE_LOCKS.setdefault(key, threading.Lock())
    with local_lock:
        lock_path = output / f".{digest}.lock"
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError as error:
            raise QualityError(f"cannot lock regression candidate: {error}") from error
        try:
            try:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            except (ImportError, OSError) as error:
                raise QualityError(f"cannot lock regression candidate: {error}") from error
            yield
        finally:
            os.close(descriptor)


def _validate_candidate_bundle(task: dict[str, Any], quality: dict[str, Any], digest: str) -> None:
    failures = validate_learn_task_v2(task)
    if failures:
        raise QualityError("existing regression candidate is invalid: " + "; ".join(failures))
    required = {
        "canonical_sha256", "phenomenon_code", "status", "candidate_repair_surface", "owner", "action",
        "confidence", "review_route", "diagnosis_evidence_refs", "mapping_version", "mapping_sha256",
        "representative_evidence", "first_seen", "last_seen", "support", "source_badcase_ids",
        "target_partition", "adoption", "writes_formal_eval",
    }
    if set(quality) != required or quality.get("canonical_sha256") != digest:
        raise QualityError("canonical candidate quality metadata is malformed")
    if not isinstance(quality.get("phenomenon_code"), str) or not quality["phenomenon_code"] or quality.get("status") not in {"FAIL", "UNKNOWN"}:
        raise QualityError("candidate phenomenon identity is invalid")
    for key in ("candidate_repair_surface", "owner", "action"):
        if not isinstance(quality.get(key), str) or not quality[key]:
            raise QualityError("candidate repair decision is invalid")
    identifiers = _string_list(quality.get("source_badcase_ids"), "candidate source_badcase_ids")
    if identifiers != sorted(set(identifiers)) or quality.get("support") != len(identifiers) or not identifiers:
        raise QualityError("candidate support must equal its unique source badcase ids")
    mapping_sha256 = quality.get("mapping_sha256")
    if quality.get("mapping_version") != MAPPING_VERSION or not isinstance(mapping_sha256, str) or len(mapping_sha256) != 64 or any(character not in "0123456789abcdef" for character in mapping_sha256):
        raise QualityError("candidate mapping provenance is invalid")
    if quality.get("confidence") not in _CONFIDENCE:
        raise QualityError("candidate diagnosis confidence is invalid")
    diagnosis_refs = _string_list(quality.get("diagnosis_evidence_refs"), "candidate diagnosis_evidence_refs")
    representatives = _string_list(quality.get("representative_evidence"), "candidate representative_evidence")
    if diagnosis_refs != sorted(set(diagnosis_refs)) or representatives != sorted(set(representatives)) or not diagnosis_refs or not representatives or len(representatives) > 5:
        raise QualityError("candidate evidence references must be non-empty canonical sets")
    route = quality.get("review_route")
    if not isinstance(route, dict) or set(route) != {"required", "reasons"} or not isinstance(route.get("required"), bool):
        raise QualityError("candidate review route is invalid")
    reasons = route.get("reasons")
    if not isinstance(reasons, list) or reasons != [reason for reason in _ROUTES if reason in reasons] or any(reason not in _ROUTES for reason in reasons) or route["required"] is not bool(reasons):
        raise QualityError("candidate review route reasons are invalid")
    if quality.get("target_partition") != "validation" or quality.get("adoption") != "human_review_required" or quality.get("writes_formal_eval") is not False:
        raise QualityError("candidate adoption boundary is invalid")
    first_seen, last_seen = _utc_timestamp(quality.get("first_seen")), _utc_timestamp(quality.get("last_seen"))
    if first_seen > last_seen:
        raise QualityError("candidate observation interval is invalid")


def _publish_new_bundle(output: Path, destination: Path, fixture_source: Path, fixture_sha256: str, task: dict[str, Any], quality: dict[str, Any]) -> None:
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=output))
    try:
        _copy_fixture_no_symlinks(fixture_source, temporary / "fixture")
        if _tree_sha256(temporary / "fixture") != fixture_sha256 or _tree_sha256(fixture_source) != fixture_sha256:
            raise QualityError("regression fixture changed while it was copied")
        _atomic_json(temporary / "task.json", task)
        _atomic_json(temporary / "quality.json", quality)
        _validate_candidate_bundle(_read_object(temporary / "task.json", "staged regression candidate"), _read_object(temporary / "quality.json", "staged regression quality metadata"), destination.name)
        os.replace(temporary, destination)
    except (OSError, shutil.Error) as error:
        raise QualityError(f"cannot stage regression bundle: {error}") from error
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _replace_quality_sidecar_at(bundle_fd: int, quality: dict[str, Any]) -> None:
    descriptor = -1
    temporary: str | None = None
    try:
        for _ in range(128):
            temporary = f".quality.json.{secrets.token_hex(12)}.tmp"
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=bundle_fd)
                break
            except FileExistsError:
                continue
        else:
            raise QualityError("cannot allocate a unique quality sidecar temporary file")
        payload = json.dumps(quality, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, "quality.json", src_dir_fd=bundle_fd, dst_dir_fd=bundle_fd)
        temporary = None
        os.fsync(bundle_fd)
    except (OSError, TypeError, ValueError) as error:
        raise QualityError(f"cannot update regression quality sidecar: {error}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=bundle_fd)
            except FileNotFoundError:
                pass


@contextmanager
def _anchored_bundle(output: Path, digest: str):
    _require_dirfd_support()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    output_fd = bundle_fd = -1
    try:
        output_fd = os.open(output, flags)
        bundle_fd = os.open(digest, flags, dir_fd=output_fd)
        identity = os.fstat(bundle_fd)
        _assert_bundle_binding(output_fd, digest, identity)
        yield output_fd, bundle_fd, identity
    except OSError as error:
        raise QualityError(f"cannot securely anchor regression bundle: {error}") from error
    finally:
        if bundle_fd >= 0:
            os.close(bundle_fd)
        if output_fd >= 0:
            os.close(output_fd)


def _require_dirfd_support() -> None:
    if not _DIRFD_SUPPORTED:
        raise QualityError("secure existing-bundle updates require dirfd and no-follow support")


def _assert_bundle_binding(output_fd: int, digest: str, identity: os.stat_result) -> None:
    current = os.stat(digest, dir_fd=output_fd, follow_symlinks=False)
    if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
        raise QualityError("canonical candidate destination changed during update")


def _read_object_at(directory_fd: int, name: str, label: str) -> dict[str, Any]:
    try:
        descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            value = json.load(stream, parse_constant=lambda constant: (_ for _ in ()).throw(ValueError(constant)))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise QualityError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise QualityError(f"{label} must be a JSON object")
    return value


def _tree_sha256_at(directory_fd: int, name: str) -> str:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as error:
        raise QualityError(f"regression fixture directory is missing: {error}") from error
    digest = hashlib.sha256()

    def visit(source_fd: int, prefix: str) -> None:
        for child_name in sorted(os.listdir(source_fd)):
            metadata = os.stat(child_name, dir_fd=source_fd, follow_symlinks=False)
            relative = f"{prefix}/{child_name}" if prefix else child_name
            if stat.S_ISDIR(metadata.st_mode):
                digest.update(b"D\0" + relative.encode() + b"\0")
                child_fd = os.open(child_name, flags, dir_fd=source_fd)
                try:
                    visit(child_fd, relative)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(metadata.st_mode):
                digest.update(b"F\0" + relative.encode() + b"\0")
                digest.update(b"X\0" if metadata.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) else b"N\0")
                file_fd = os.open(child_name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=source_fd)
                try:
                    while chunk := os.read(file_fd, 1024 * 1024):
                        digest.update(chunk)
                finally:
                    os.close(file_fd)
            else:
                raise QualityError("regression fixture contains a link or unsupported special file")
    try:
        visit(root_fd, "")
    except OSError as error:
        raise QualityError(f"cannot securely hash regression fixture: {error}") from error
    finally:
        os.close(root_fd)
    return digest.hexdigest()


def _copy_fixture_no_symlinks(source: Path, destination: Path) -> None:
    """Copy a fixture through anchored directory descriptors without following links."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_fd = os.open(source, flags)
    except OSError as error:
        raise QualityError(f"cannot securely open regression fixture: {error}") from error
    destination.mkdir()

    def copy_directory(source_fd: int, target: Path) -> None:
        for name in sorted(os.listdir(source_fd)):
            try:
                metadata = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
            except OSError as error:
                raise QualityError(f"cannot inspect regression fixture entry: {error}") from error
            child = target / name
            if stat.S_ISLNK(metadata.st_mode):
                raise QualityError("regression fixture cannot contain symbolic links")
            if stat.S_ISDIR(metadata.st_mode):
                child.mkdir()
                try:
                    child_fd = os.open(name, flags, dir_fd=source_fd)
                except OSError as error:
                    raise QualityError(f"cannot securely open regression fixture directory: {error}") from error
                try:
                    copy_directory(child_fd, child)
                finally:
                    os.close(child_fd)
                child.chmod(stat.S_IMODE(metadata.st_mode))
            elif stat.S_ISREG(metadata.st_mode):
                try:
                    file_fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=source_fd)
                    with os.fdopen(file_fd, "rb") as source_file, child.open("wb") as target_file:
                        shutil.copyfileobj(source_file, target_file)
                except OSError as error:
                    raise QualityError(f"cannot securely copy regression fixture file: {error}") from error
                child.chmod(stat.S_IMODE(metadata.st_mode))
            else:
                raise QualityError("regression fixture contains an unsupported special file")

    try:
        copy_directory(root_fd, destination)
    finally:
        os.close(root_fd)
