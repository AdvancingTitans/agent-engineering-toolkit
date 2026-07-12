"""Evidence-gated, local Skill evolution with explicit human adoption."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .decision import DecisionError, add_decision, init_ledger
from .discovery import discover_assets
from .models import Status
from .rules import run_rules


class LearnError(ValueError):
    """Raised when an evolution artifact cannot satisfy its evidence boundary."""


_IMMUTABLE_START = "<!-- aet-learn:immutable -->"
_EDITABLE_RE = re.compile(r"<!-- aet-learn:editable id=\"([^\"]+)\" -->\n?(.*?)<!-- aet-learn:end -->", re.DOTALL)


def harvest(*, runs: Path | None, evidence: Path | None, output: Path) -> dict[str, Any]:
    """Normalize only structured AET artifacts; transcripts are never read."""
    sources = list(_json_sources(runs)) + list(_json_sources(evidence))
    experiences: list[dict[str, Any]] = []
    for source in sorted(set(sources)):
        data = _read_json(source)
        kind = data.get("report_kind") if isinstance(data, dict) else None
        if not isinstance(kind, str):
            continue
        deviations = _deviations(data)
        experiences.append({
            "experience_id": f"EXP-{_sha(source.read_bytes())[:12]}",
            "source": str(source.resolve()), "source_sha256": _sha(source.read_bytes()),
            "report_kind": kind, "schema_version": data.get("schema_version", "UNKNOWN"),
            "workspace_snapshot": data.get("workspace_snapshot", {"status": "UNKNOWN"}),
            "deviations": deviations,
            "privacy": {"raw_transcript_retained": False, "profile": "evidence-only"},
        })
    result = {"schema_version": __version__, "report_kind": "learning_experiences", "generated_at": _time(), "experiences": experiences}
    _write_json(output, result)
    return result


def mine(*, experiences: Path, output: Path) -> dict[str, Any]:
    data = _read_json(experiences)
    rows = data.get("experiences") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise LearnError("experiences input must be an AET learning_experiences artifact")
    grouped: dict[str, list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for deviation in row.get("deviations", []):
            if isinstance(deviation, str):
                grouped.setdefault(deviation, []).append(str(row.get("experience_id", "UNKNOWN")))
    patterns = []
    for deviation, ids in sorted(grouped.items()):
        count = len(set(ids))
        confidence = "HIGH" if count >= 5 else "MEDIUM" if count >= 3 else "LOW"
        patterns.append({"pattern_id": f"PAT-{_sha(deviation.encode())[:8].upper()}", "kind": deviation, "support": {"experience_count": count}, "confidence": confidence, "evidence_refs": sorted(set(ids))})
    result = {"schema_version": __version__, "report_kind": "learning_patterns", "generated_at": _time(), "patterns": patterns}
    _write_json(output, result)
    return result


def propose(*, patterns: Path, target: Path, output: Path, engine: str, model_command: list[str] | None = None) -> dict[str, Any]:
    """Produce a bounded candidate; model output is accepted only as Patch IR."""
    source = target.resolve()
    text = _read_text(source)
    blocks = list(_EDITABLE_RE.finditer(text))
    if not blocks:
        raise LearnError("target has no aet-learn editable block")
    source_patterns = _read_json(patterns).get("patterns", [])
    if engine == "rules":
        first = blocks[0]
        addition = "\nVerify proof-oriented requests with `aet trace -- <command>` before saying a command was proven; attach the Trace path and preserve UNKNOWN when proof is missing.\n"
        replacement = first.group(2).rstrip() + addition
        candidate_text = text[:first.start(2)] + replacement + text[first.end(2):]
        operations = [{"type": "replace_editable_block", "id": first.group(1), "before_sha256": _sha(first.group(2).encode()), "new_text": replacement}]
    elif engine == "model":
        if not model_command:
            raise LearnError("--engine model requires an explicit --model-command argv")
        request = {"target": str(source), "editable_blocks": [match.group(1) for match in blocks], "patterns": source_patterns, "immutable_contract": _immutable_blocks(text), "output_schema": "{operations:[{id,new_text}]}"}
        with tempfile.TemporaryDirectory() as temporary:
            request_path = Path(temporary) / "request.json"
            _write_json(request_path, request)
            completed = subprocess.run(model_command, input=json.dumps(request), text=True, capture_output=True, check=False, env={**os.environ, "AET_LEARN_INPUT": str(request_path)})
        if completed.returncode != 0:
            raise LearnError("model command failed; candidate was not created")
        response = _read_json_text(completed.stdout)
        candidate_text, operations = _apply_model_operations(text, blocks, response)
    else:
        raise LearnError("proposal engine must be rules or model")
    candidate_id = f"CAND-{_sha((str(source) + _sha(candidate_text.encode())).encode())[:8].upper()}"
    output.mkdir(parents=True, exist_ok=True)
    candidate_file = output / "candidate.SKILL.md"
    candidate_file.write_text(candidate_text, encoding="utf-8")
    result = {"schema_version": __version__, "report_kind": "learning_candidate", "candidate_id": candidate_id, "created_at": _time(), "engine": engine, "target_file": str(source), "baseline_sha256": _sha(text.encode()), "candidate_sha256": _sha(candidate_text.encode()), "pattern_ids": [item.get("pattern_id") for item in source_patterns if isinstance(item, dict)], "operations": operations, "edit_budget": {"max_operations": 3, "max_added_characters": 800}, "adoption": "human_required"}
    _write_json(output / "candidate.json", result)
    (output / "rationale.md").write_text("# Candidate rationale\n\nGenerated from structured evidence only. It is staged for human review; it is not adopted automatically.\n", encoding="utf-8")
    return result


def replay(*, candidate: Path, suite: Iterable[Path], output: Path) -> dict[str, Any]:
    metadata, baseline, proposed = _candidate_material(candidate)
    results = {"baseline": _evaluate(baseline, suite), "candidate": _evaluate(proposed, suite)}
    data = {"schema_version": __version__, "report_kind": "learning_replay", "candidate_id": metadata["candidate_id"], "generated_at": _time(), "isolated": True, "results": results}
    _write_json(output, data)
    return data


def gate(*, candidate: Path, validation: Path, held_out: Path, output: Path, core: Path | None = None) -> dict[str, Any]:
    metadata, baseline, proposed = _candidate_material(candidate)
    hard_failures = _hard_gate_failures(metadata, baseline, proposed)
    audit_failures = _candidate_audit_failures(metadata, proposed)
    validation_result = _evaluate(proposed, [validation])
    validation_baseline = _evaluate(baseline, [validation])
    held_result = _evaluate(proposed, [held_out])
    held_baseline = _evaluate(baseline, [held_out])
    core_result = _evaluate(proposed, [core]) if core else None
    core_baseline = _evaluate(baseline, [core]) if core else None
    improves = validation_result["passed"] > validation_baseline["passed"] or held_result["passed"] > held_baseline["passed"]
    no_regression = validation_result["passed"] >= validation_baseline["passed"] and held_result["passed"] >= held_baseline["passed"] and (core_result is None or core_result["passed"] >= core_baseline["passed"])
    status = Status.PASS.value if not hard_failures and not audit_failures and no_regression and improves else Status.FAIL.value
    metrics = {"validation": {"baseline": validation_baseline, "candidate": validation_result}, "held_out": {"baseline": held_baseline, "candidate": held_result}}
    if core_result is not None:
        metrics["core"] = {"baseline": core_baseline, "candidate": core_result}
    data = {"schema_version": __version__, "report_kind": "learning_gate", "candidate_id": metadata["candidate_id"], "generated_at": _time(), "status": status, "hard_gate_failures": hard_failures, "candidate_audit_failures": audit_failures, "metrics": metrics, "acceptance": "hard gates pass; core/held-out do not regress; at least one independent task improves; human adoption remains required"}
    _write_json(output, data)
    return data


def stage(*, candidate: Path, gate: Path, output: Path) -> dict[str, Any]:
    metadata = _read_json(candidate / "candidate.json")
    result = _read_json(gate)
    if result.get("status") != Status.PASS.value or result.get("candidate_id") != metadata.get("candidate_id"):
        raise LearnError("only a passing gate for this exact candidate can be staged")
    destination = output / str(metadata["candidate_id"])
    if destination.exists():
        existing = _read_json(destination / "candidate.json")
        if existing.get("candidate_sha256") == metadata.get("candidate_sha256"):
            return {"report_kind": "learning_stage", "candidate_id": metadata["candidate_id"], "status": Status.PASS.value, "path": str(destination), "idempotent": True}
        raise LearnError(f"a different staged candidate already exists: {destination}")
    shutil.copytree(candidate, destination)
    shutil.copy2(gate, destination / "gate.json")
    return {"report_kind": "learning_stage", "candidate_id": metadata["candidate_id"], "status": Status.PASS.value, "path": str(destination)}


def adopt(*, candidate: Path, gate: Path, ledger: Path | None = None) -> dict[str, Any]:
    metadata, baseline, proposed = _candidate_material(candidate)
    result = _read_json(gate)
    target = Path(metadata["target_file"])
    if result.get("status") != Status.PASS.value or result.get("candidate_id") != metadata.get("candidate_id"):
        raise LearnError("adoption requires a passing gate for the exact candidate")
    if _sha(target.read_bytes()) != metadata.get("baseline_sha256"):
        raise LearnError("target changed after proposal; rerun the candidate pipeline")
    _atomic_text(target, proposed)
    root = Path.cwd().resolve()
    ledger_path = (ledger or root / ".aet" / "learn" / "decision-ledger.json").resolve()
    try:
        if not ledger_path.exists():
            init_ledger(ledger_path)
        add_decision(ledger_path, identifier=f"DEC-{metadata['candidate_id']}", claim=f"Adopt evidence-gated Skill candidate {metadata['candidate_id']}.", evidence_state="EVIDENCED", state="ACCEPTED", sources=[str((candidate / "candidate.json").resolve().relative_to(root)), str(gate.resolve().relative_to(root))], supersedes=[])
    except (DecisionError, ValueError) as error:
        raise LearnError(f"candidate adopted but Decision Ledger could not be updated: {error}") from error
    return {"report_kind": "learning_adoption", "candidate_id": metadata["candidate_id"], "status": Status.PASS.value, "target": str(target), "ledger": str(ledger_path)}


def reject(*, candidate: Path, reason: str, output: Path) -> dict[str, Any]:
    metadata = _read_json(candidate / "candidate.json")
    if not reason.strip():
        raise LearnError("rejection reason must be non-empty")
    output.mkdir(parents=True, exist_ok=True)
    record = {"report_kind": "learning_rejection", "candidate_id": metadata.get("candidate_id"), "rejected_at": _time(), "reason": reason.strip(), "candidate_sha256": metadata.get("candidate_sha256")}
    _write_json(output / f"{metadata['candidate_id']}.json", record)
    return record


def sleep(*, runs: Path | None, evidence: Path | None, target: Path, validation: Path, held_out: Path, output: Path, core: Path | None = None, engine: str = "rules", model_command: list[str] | None = None) -> dict[str, Any]:
    """Run a bounded local learning cycle and only stage a passing proposal."""
    output.mkdir(parents=True, exist_ok=True)
    experiences = output / "experiences.json"
    patterns = output / "patterns.json"
    candidates = output / "candidates"
    harvest(runs=runs, evidence=evidence, output=experiences)
    mined = mine(experiences=experiences, output=patterns)
    if not mined["patterns"]:
        return {"report_kind": "learning_sleep", "status": "NOT_APPLICABLE", "reason": "no recurring evidence deviations", "adopted": False}
    candidate_dir = candidates / "candidate"
    candidate = propose(patterns=patterns, target=target, output=candidate_dir, engine=engine, model_command=model_command)
    replay(candidate=candidate_dir, suite=[validation, held_out], output=output / "replays" / f"{candidate['candidate_id']}.json")
    gate_path = output / "gates" / f"{candidate['candidate_id']}.json"
    result = gate(candidate=candidate_dir, validation=validation, held_out=held_out, core=core, output=gate_path)
    staged = None
    if result["status"] == Status.PASS.value:
        staged = stage(candidate=candidate_dir, gate=gate_path, output=output / "staged")
    return {"report_kind": "learning_sleep", "status": result["status"], "candidate_id": candidate["candidate_id"], "stage": staged, "adopted": False}


def _deviations(data: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for finding in data.get("findings", []):
        if isinstance(finding, dict) and finding.get("status") in {Status.FAIL.value, Status.UNKNOWN.value}:
            values.append(str(finding.get("rule_id", "UNCLASSIFIED_FINDING")))
    trace = data.get("trace")
    if isinstance(trace, dict) and any(isinstance(item, dict) and item.get("status") == Status.UNKNOWN.value for item in trace.get("artifacts", [])):
        values.append("MISSING_TRACE_PROOF")
    summary = data.get("summary")
    if isinstance(summary, dict) and summary.get(Status.UNKNOWN.value, 0):
        values.append("UNKNOWN_REQUIRES_PRESERVATION")
    return sorted(set(values))


def _candidate_material(candidate: Path) -> tuple[dict[str, Any], str, str]:
    metadata = _read_json(candidate / "candidate.json")
    proposed = _read_text(candidate / "candidate.SKILL.md")
    target = Path(metadata.get("target_file", ""))
    if not target.is_file() or not isinstance(metadata.get("candidate_id"), str):
        raise LearnError("candidate is incomplete or its target no longer exists")
    return metadata, _read_text(target), proposed


def _hard_gate_failures(metadata: dict[str, Any], baseline: str, proposed: str) -> list[str]:
    failures: list[str] = []
    if Path(metadata.get("target_file", "")).name != "SKILL.md":
        failures.append("target is not a SKILL.md file")
    if _sha(baseline.encode()) != metadata.get("baseline_sha256"):
        failures.append("baseline hash no longer matches the candidate record")
    if _sha(proposed.encode()) != metadata.get("candidate_sha256"):
        failures.append("candidate hash does not match the candidate record")
    if len(metadata.get("operations", [])) > 3 or len(proposed) - len(baseline) > 800 or len(baseline) - len(proposed) > 400:
        failures.append("edit budget exceeded")
    if _immutable_blocks(baseline) != _immutable_blocks(proposed):
        failures.append("immutable contract changed")
    if _outside_editable_text(baseline) != _outside_editable_text(proposed):
        failures.append("candidate changed outside editable blocks")
    if "UNKNOWN is a pass" in proposed or "automatically adopt" in proposed.lower():
        failures.append("forbidden evidence semantics introduced")
    return failures


def _outside_editable_text(text: str) -> str:
    """Erase only editable bodies, leaving marker placement and all policy bytes intact."""
    return _EDITABLE_RE.sub(lambda match: f'<!-- aet-learn:editable id="{match.group(1)}" -->\n<editable-body>\n<!-- aet-learn:end -->', text)


def _candidate_audit_failures(metadata: dict[str, Any], proposed: str) -> list[str]:
    target = Path(metadata["target_file"])
    with tempfile.TemporaryDirectory() as temporary:
        sandbox = Path(temporary) / target.parent.name
        shutil.copytree(target.parent, sandbox)
        (sandbox / "SKILL.md").write_text(proposed, encoding="utf-8")
        findings = run_rules(sandbox.parent, discover_assets(sandbox.parent))
    return [finding.rule_id for finding in findings if finding.status != Status.PASS]


def _evaluate(text: str, suites: Iterable[Path]) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for suite in suites:
        for source in _json_sources(suite):
            data = _read_json(source)
            if isinstance(data, dict) and isinstance(data.get("task_id"), str):
                tasks.append(data)
    results = []
    for task in tasks:
        required = [item for item in task.get("required_patterns", []) if isinstance(item, str)]
        forbidden = [item for item in task.get("forbidden_patterns", []) if isinstance(item, str)]
        passed = all(item in text for item in required) and not any(item in text for item in forbidden)
        results.append({"task_id": task["task_id"], "status": Status.PASS.value if passed else Status.FAIL.value})
    return {"total": len(results), "passed": sum(item["status"] == Status.PASS.value for item in results), "results": results}


def _apply_model_operations(text: str, blocks: list[Any], response: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    operations = response.get("operations") if isinstance(response, dict) else None
    if not isinstance(operations, list) or not operations or len(operations) > 3:
        raise LearnError("model output must contain one to three bounded operations")
    replacements: dict[str, str] = {}
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get("id"), str) or not isinstance(operation.get("new_text"), str):
            raise LearnError("model output operation is invalid")
        replacements[operation["id"]] = operation["new_text"]
    result = text
    recorded = []
    for block in reversed(blocks):
        identifier = block.group(1)
        if identifier in replacements:
            replacement = replacements[identifier]
            result = result[:block.start(2)] + replacement + result[block.end(2):]
            recorded.append({"type": "replace_editable_block", "id": identifier, "before_sha256": _sha(block.group(2).encode()), "new_text": replacement})
    if not recorded:
        raise LearnError("model output did not address an editable block")
    return result, list(reversed(recorded))


def _immutable_blocks(text: str) -> list[str]:
    parts = text.split(_IMMUTABLE_START)[1:]
    return [part.split("<!-- aet-learn:end -->", 1)[0] for part in parts if "<!-- aet-learn:end -->" in part]


def _json_sources(path: Path | None) -> Iterable[Path]:
    if path is None or not path.exists():
        return []
    return [path] if path.is_file() and path.suffix == ".json" else sorted(item for item in path.rglob("*.json") if item.is_file())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return _read_json_text(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise LearnError(f"cannot read JSON artifact: {path}") from error


def _read_json_text(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise LearnError("invalid JSON artifact") from error
    if not isinstance(data, dict):
        raise LearnError("JSON artifact must be an object")
    return data


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise LearnError(f"cannot read text artifact: {path}") from error


def _write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _time() -> str:
    return datetime.now(UTC).isoformat()
