"""Evidence-gated, local Skill evolution with explicit human adoption."""

from __future__ import annotations

import difflib
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
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
_EDITABLE_RE = re.compile(r'<!-- aet-learn:editable id="([^"]+)" -->\n?(.*?)<!-- aet-learn:end -->', re.DOTALL)
_LEARNING_STATES = {"HARVESTED", "MINED", "PROPOSED", "REPLAYED", "GATED", "STAGED", "REJECTED", "NOT_APPLICABLE", "STALE"}


def harvest(*, runs: Path | None, evidence: Path | None, output: Path, experience_store: Path | None = None) -> dict[str, Any]:
    """Normalize only structured AET artifacts; transcripts are never read."""
    sources = list(_json_sources(runs)) + list(_json_sources(evidence))
    experiences: list[dict[str, Any]] = []
    for source in sorted(set(sources)):
        data = _read_json(source)
        if isinstance(data.get("report_kind"), str):
            experiences.append(_experience_from_report(data, source))
    for source in _json_sources(experience_store):
        data = _read_json(source)
        if data.get("report_kind") != "learning_experiences":
            continue
        rows = data.get("experiences", [])
        if not isinstance(rows, list):
            raise LearnError(f"experience-store pack is malformed: {source}")
        for row in rows:
            if not _is_evidence_only_experience(row):
                raise LearnError(f"experience-store pack is not Evidence Only: {source}")
            experiences.append(row)
    deduplicated = {row.get("experience_id"): row for row in experiences if isinstance(row.get("experience_id"), str)}
    result = {
        "schema_version": __version__, "report_kind": "learning_experiences", "generated_at": _time(),
        "privacy": {"profile": "evidence-only", "raw_transcript_retained": False},
        "experiences": [deduplicated[key] for key in sorted(deduplicated)],
    }
    _write_json(output, result)
    return result


def collect(*, experiences: Path, store: Path) -> dict[str, Any]:
    """Copy a de-identified local experience pack into a user-controlled local store."""
    data = _read_json(experiences)
    if set(data) - {"schema_version", "report_kind", "generated_at", "privacy", "experiences"} or data.get("report_kind") != "learning_experiences" or data.get("privacy", {}).get("raw_transcript_retained") is not False:
        raise LearnError("only Evidence Only learning_experiences artifacts can enter an experience store")
    for row in data.get("experiences", []):
        if not _is_evidence_only_experience(row):
            raise LearnError("experience store rejects transcript-bearing or malformed records")
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
    destination = store / f"pack-{_sha(payload)[:16]}.json"
    existed = destination.exists()
    if not existed:
        _write_json(destination, data)
    return {"report_kind": "learning_collection", "status": Status.PASS.value, "store": str(store), "path": str(destination), "deduplicated": existed}


def inspect_experiences(*, experiences: Path, output: Path) -> dict[str, Any]:
    """Produce deterministic counts before any proposal engine sees an experience set."""
    data = _read_json(experiences)
    rows = _experience_rows(data)
    deviations: dict[str, int] = {}
    repositories, dates = set(), set()
    for row in rows:
        repositories.add(str(row.get("repository_fingerprint", "UNKNOWN")))
        if isinstance(row.get("observed_at"), str):
            dates.add(row["observed_at"][:10])
        for value in row.get("deviations", []):
            if isinstance(value, str):
                deviations[value] = deviations.get(value, 0) + 1
    result = {
        "schema_version": __version__, "report_kind": "learning_inspection", "generated_at": _time(),
        "experience_count": len(rows), "repository_count": len(repositories), "date_count": len(dates),
        "deviation_counts": dict(sorted(deviations.items())),
        "privacy": {"profile": "evidence-only", "raw_transcript_retained": False},
    }
    _write_json(output, result)
    return result


def mine(*, experiences: Path, output: Path) -> dict[str, Any]:
    data = _read_json(experiences)
    rows = _experience_rows(data)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for deviation in row.get("deviations", []):
            if isinstance(deviation, str):
                grouped.setdefault(deviation, []).append(row)
    patterns = []
    for deviation, support_rows in sorted(grouped.items()):
        identifiers = sorted({str(row.get("experience_id")) for row in support_rows})
        repositories = sorted({str(row.get("repository_fingerprint", "UNKNOWN")) for row in support_rows})
        dates = sorted({str(row.get("observed_at", "UNKNOWN"))[:10] for row in support_rows})
        count = len(identifiers)
        confidence = "HIGH" if count >= 5 and len(repositories) >= 3 and len(dates) >= 2 else "MEDIUM" if count >= 3 else "LOW"
        patterns.append({
            "pattern_id": f"PAT-{_sha(deviation.encode())[:8].upper()}", "kind": deviation,
            "support": {"experience_count": count, "repository_count": len(repositories), "date_count": len(dates)},
            "confidence": confidence, "evidence_refs": identifiers,
        })
    result = {"schema_version": __version__, "report_kind": "learning_patterns", "generated_at": _time(), "patterns": patterns}
    _write_json(output, result)
    return result


def propose(*, patterns: Path, target: Path, output: Path, engine: str, model_command: list[str] | None = None, model_timeout_seconds: float = 30, rejected: Path | None = None) -> dict[str, Any]:
    """Produce a bounded candidate; model output is accepted only as Patch IR."""
    source = target.resolve()
    text = _read_text(source)
    blocks = list(_EDITABLE_RE.finditer(text))
    if not blocks:
        raise LearnError("target has no aet-learn editable block")
    source_patterns = _read_json(patterns).get("patterns", [])
    if not isinstance(source_patterns, list) or not source_patterns:
        raise LearnError("proposal requires at least one mined failure pattern")
    rejected_summary = _rejected_summary(rejected)
    if engine == "rules":
        first = blocks[0]
        additions = _rule_additions(source_patterns)
        replacement = first.group(2).rstrip() + "\n" + "\n".join(additions) + "\n"
        candidate_text = text[:first.start(2)] + replacement + text[first.end(2):]
        operations = [{"type": "replace_editable_block", "id": first.group(1), "before_sha256": _sha(first.group(2).encode()), "new_text": replacement}]
    elif engine == "model":
        if not model_command:
            raise LearnError("--engine model requires an explicit --model-command argv")
        if model_timeout_seconds <= 0:
            raise LearnError("model timeout must be positive")
        request = {
            "target": str(source), "editable_blocks": [match.group(1) for match in blocks], "patterns": source_patterns,
            "rejected_candidates": rejected_summary, "immutable_contract": _immutable_blocks(text),
            "edit_budget": {"max_operations": 3, "max_added_characters": 800, "max_deleted_characters": 400},
            "output_schema": "{operations:[{id,new_text}]}",
        }
        with tempfile.TemporaryDirectory() as temporary:
            request_path = Path(temporary) / "request.json"
            _write_json(request_path, request)
            try:
                completed = subprocess.run(model_command, input=json.dumps(request), text=True, capture_output=True, check=False, timeout=model_timeout_seconds, env={**os.environ, "AET_LEARN_INPUT": str(request_path)})
            except subprocess.TimeoutExpired as error:
                raise LearnError("model command exceeded its explicit timeout; candidate was not created") from error
        if completed.returncode != 0:
            raise LearnError("model command failed; candidate was not created")
        response = _read_json_text(completed.stdout)
        candidate_text, operations = _apply_model_operations(text, blocks, response)
    else:
        raise LearnError("proposal engine must be rules or model")
    candidate_id = f"CAND-{_sha((str(source) + _sha(candidate_text.encode())).encode())[:8].upper()}"
    output.mkdir(parents=True, exist_ok=True)
    candidate_file = output / "candidate.SKILL.md"
    _atomic_text(candidate_file, candidate_text)
    result = {
        "schema_version": __version__, "report_kind": "learning_candidate", "candidate_id": candidate_id, "created_at": _time(),
        "engine": engine, "target_file": str(source), "baseline_sha256": _sha(text.encode()), "candidate_sha256": _sha(candidate_text.encode()),
        "pattern_ids": [item.get("pattern_id") for item in source_patterns if isinstance(item, dict)], "operations": operations,
        "edit_budget": {"max_operations": 3, "max_added_characters": 800, "max_deleted_characters": 400},
        "adoption": "human_required", "privacy": {"profile": "evidence-only"},
    }
    _write_json(output / "candidate.json", result)
    _write_json(output / "source-manifest.json", {"report_kind": "learning_candidate_sources", "patterns": result["pattern_ids"], "rejected_summary": rejected_summary})
    _atomic_text(output / "patch.diff", "".join(difflib.unified_diff(text.splitlines(keepends=True), candidate_text.splitlines(keepends=True), fromfile="baseline/SKILL.md", tofile="candidate/SKILL.md")))
    _atomic_text(output / "rationale.md", "# Candidate rationale\n\nGenerated from structured Evidence Only records. This candidate is bounded to editable blocks and awaits human adoption.\n")
    return result


def replay(*, candidate: Path, suite: Iterable[Path], output: Path) -> dict[str, Any]:
    """Evaluate both versions from temporary copies; the production Skill stays read-only."""
    metadata, baseline, proposed = _candidate_material(candidate)
    target = Path(metadata["target_file"])
    before = _sha(target.read_bytes())
    with tempfile.TemporaryDirectory(prefix="aet-learn-replay-") as temporary:
        sandbox = Path(temporary)
        _atomic_text(sandbox / "baseline.SKILL.md", baseline)
        _atomic_text(sandbox / "candidate.SKILL.md", proposed)
        results = {"baseline": _evaluate(_read_text(sandbox / "baseline.SKILL.md"), suite), "candidate": _evaluate(_read_text(sandbox / "candidate.SKILL.md"), suite)}
    data = {
        "schema_version": __version__, "report_kind": "learning_replay", "candidate_id": metadata["candidate_id"], "generated_at": _time(),
        "isolated": True, "runner": "builtin-static-skill", "target_unchanged": before == _sha(target.read_bytes()), "results": results,
    }
    _write_json(output, data)
    return data


def gate(*, candidate: Path, validation: Path, held_out: Path, output: Path, core: Path | None = None) -> dict[str, Any]:
    metadata, baseline, proposed = _candidate_material(candidate)
    hard_failures = _hard_gate_failures(metadata, baseline, proposed)
    if _suite_fingerprints(validation) & _suite_fingerprints(held_out):
        hard_failures.append("validation and held-out suites overlap")
    audit_failures = _candidate_audit_failures(metadata, proposed)
    validation_result, validation_baseline = _evaluate(proposed, [validation]), _evaluate(baseline, [validation])
    held_result, held_baseline = _evaluate(proposed, [held_out]), _evaluate(baseline, [held_out])
    core_result = _evaluate(proposed, [core]) if core else None
    core_baseline = _evaluate(baseline, [core]) if core else None
    cost = _cost_metrics(baseline, proposed, validation_baseline, validation_result)
    if cost["skill_token_delta"] > 0.10 and cost["skill_tokens"]["candidate"] - cost["skill_tokens"]["baseline"] > 180:
        hard_failures.append("skill token budget exceeded")
    if cost["command_surface_delta"] > 1:
        hard_failures.append("command-surface budget exceeded")
    if cost["workflow_overuse_rate"]["candidate"] > cost["workflow_overuse_rate"]["baseline"]:
        hard_failures.append("workflow overuse increased")
    improves = validation_result["passed"] > validation_baseline["passed"] or held_result["passed"] > held_baseline["passed"]
    no_regression = validation_result["passed"] >= validation_baseline["passed"] and held_result["passed"] >= held_baseline["passed"] and (core_result is None or core_result["passed"] >= core_baseline["passed"])
    status = Status.PASS.value if not hard_failures and not audit_failures and no_regression and improves else Status.FAIL.value
    metrics: dict[str, Any] = {
        "validation": {"baseline": validation_baseline, "candidate": validation_result},
        "held_out": {"baseline": held_baseline, "candidate": held_result}, "cost": cost,
        "quality_vector": _quality_vector(validation_result, held_result, hard_failures),
    }
    if core_result is not None:
        metrics["core"] = {"baseline": core_baseline, "candidate": core_result}
    data = {
        "schema_version": __version__, "report_kind": "learning_gate", "candidate_id": metadata["candidate_id"], "generated_at": _time(),
        "baseline_sha256": metadata["baseline_sha256"], "candidate_sha256": metadata["candidate_sha256"],
        "status": status, "hard_gate_failures": hard_failures, "candidate_audit_failures": audit_failures, "metrics": metrics,
        "acceptance": "hard gates pass; core/held-out do not regress; at least one independent task improves; human adoption remains required",
    }
    _write_json(output, data)
    return data


def stage(*, candidate: Path, gate: Path, output: Path) -> dict[str, Any]:
    metadata, baseline, proposed = _candidate_material(candidate)
    result = _read_json(gate)
    if _gate_binding_failures(result, metadata, baseline, proposed):
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
    if _gate_binding_failures(result, metadata, baseline, proposed):
        raise LearnError("adoption requires a passing gate for the exact candidate")
    if _sha(target.read_bytes()) != metadata.get("baseline_sha256"):
        raise LearnError("target changed after proposal; rerun the candidate pipeline")
    root = Path.cwd().resolve()
    ledger_path = (ledger or root / ".aet" / "learn" / "decision-ledger.json").resolve()
    try:
        candidate_source = str((candidate / "candidate.json").resolve().relative_to(root))
        gate_source = str(gate.resolve().relative_to(root))
    except ValueError as error:
        raise LearnError("adoption sources must be inside the local Decision Ledger root") from error
    try:
        if not ledger_path.exists():
            init_ledger(ledger_path)
        add_decision(ledger_path, identifier=f"DEC-{metadata['candidate_id']}", claim=f"Adopt evidence-gated Skill candidate {metadata['candidate_id']}.", evidence_state="EVIDENCED", state="ACCEPTED", sources=[candidate_source, gate_source], supersedes=[])
    except (DecisionError, ValueError) as error:
        raise LearnError(f"candidate was not adopted because Decision Ledger preparation failed: {error}") from error
    _atomic_text(target, proposed)
    return {"report_kind": "learning_adoption", "candidate_id": metadata["candidate_id"], "status": Status.PASS.value, "target": str(target), "ledger": str(ledger_path)}


def reject(*, candidate: Path, reason: str, output: Path) -> dict[str, Any]:
    metadata = _read_json(candidate / "candidate.json")
    if not reason.strip():
        raise LearnError("rejection reason must be non-empty")
    output.mkdir(parents=True, exist_ok=True)
    record = {"report_kind": "learning_rejection", "candidate_id": metadata.get("candidate_id"), "rejected_at": _time(), "reason": reason.strip(), "candidate_sha256": metadata.get("candidate_sha256")}
    _write_json(output / f"{metadata['candidate_id']}.json", record)
    return record


def render_learn_viewer(*, gate: Path, output: Path) -> None:
    """Render a local, no-network gate viewer for human adoption review."""
    data = _read_json(gate)
    body = html.escape(json.dumps(data, ensure_ascii=False, indent=2))
    _atomic_text(output, "<!doctype html><meta charset=\"utf-8\"><title>AET Evidence-Gated Evolution</title><style>body{font:16px system-ui;max-width:960px;margin:2rem auto;padding:0 1rem}pre{background:#111;color:#e8e8e8;padding:1rem;overflow:auto}strong{color:#0a7}</style><h1>Evidence-Gated Evolution</h1><p>Human review artifact. A passing gate is not adoption.</p><pre>" + body + "</pre>")


def sleep(*, runs: Path | None, evidence: Path | None, target: Path, validation: Path, held_out: Path, output: Path, core: Path | None = None, engine: str = "rules", model_command: list[str] | None = None, experience_store: Path | None = None, rejected: Path | None = None, max_candidates: int = 1, max_replays: int = 2, max_model_calls: int = 1, timeout_seconds: float = 120) -> dict[str, Any]:
    """Run a bounded local cycle. It may stage but never adopts, commits, pushes, or uploads."""
    if max_candidates != 1 or max_replays < 2 or max_model_calls < (1 if engine == "model" else 0) or timeout_seconds <= 0:
        raise LearnError("sleep policy requires max-candidates=1, max-replays>=2, sufficient model-call budget, and a positive timeout")
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    target = target.resolve()
    before = _sha(target.read_bytes())
    run = _load_learning_run(output)
    _record_learning_event(run, "HARVESTED", policy={"max_candidates": max_candidates, "max_replays": max_replays, "max_model_calls": max_model_calls, "timeout_seconds": timeout_seconds, "local_only": True, "auto_adopt": False})
    experiences, patterns = output / "experiences.json", output / "patterns.json"
    harvest(runs=runs, evidence=evidence, experience_store=experience_store, output=experiences)
    _write_learning_run(output, run)
    mined = mine(experiences=experiences, output=patterns)
    _record_learning_event(run, "MINED", pattern_count=len(mined["patterns"]))
    if not mined["patterns"]:
        _record_learning_event(run, "NOT_APPLICABLE", reason="no recurring evidence deviations")
        _write_learning_run(output, run)
        return {"report_kind": "learning_sleep", "status": "NOT_APPLICABLE", "reason": "no recurring evidence deviations", "adopted": False}
    _ensure_within_timeout(started, timeout_seconds)
    candidate_dir = output / "candidates" / "candidate"
    candidate = propose(patterns=patterns, target=target, output=candidate_dir, engine=engine, model_command=model_command, model_timeout_seconds=max(0.01, timeout_seconds - (time.monotonic() - started)), rejected=rejected)
    _record_learning_event(run, "PROPOSED", candidate_id=candidate["candidate_id"])
    replay(candidate=candidate_dir, suite=[validation, held_out], output=output / "replays" / f"{candidate['candidate_id']}.json")
    _record_learning_event(run, "REPLAYED", replay_count=2)
    _ensure_within_timeout(started, timeout_seconds)
    gate_path = output / "gates" / f"{candidate['candidate_id']}.json"
    result = gate(candidate=candidate_dir, validation=validation, held_out=held_out, core=core, output=gate_path)
    _record_learning_event(run, "GATED", gate_status=result["status"])
    _ensure_within_timeout(started, timeout_seconds)
    staged = None
    if result["status"] == Status.PASS.value:
        if before != _sha(target.read_bytes()):
            _record_learning_event(run, "STALE", reason="production target changed before stage")
            _write_learning_run(output, run)
            raise LearnError("sleep detected a production target change before stage")
        staged = stage(candidate=candidate_dir, gate=gate_path, output=output / "staged")
        _record_learning_event(run, "STAGED", stage=staged)
        _ensure_within_timeout(started, timeout_seconds)
    else:
        _record_learning_event(run, "REJECTED", reason="gate did not pass")
    if before != _sha(target.read_bytes()):
        _record_learning_event(run, "STALE", reason="production target changed during sleep")
        _write_learning_run(output, run)
        raise LearnError("sleep detected a production target change and refused to continue")
    _write_learning_run(output, run)
    return {"report_kind": "learning_sleep", "status": result["status"], "candidate_id": candidate["candidate_id"], "stage": staged, "adopted": False, "run": str(output / "learning-run.json")}


def _experience_from_report(data: dict[str, Any], source: Path) -> dict[str, Any]:
    raw = source.read_bytes()
    snapshot = data.get("workspace_snapshot") if isinstance(data.get("workspace_snapshot"), dict) else {}
    observed_at = data.get("generated_at") if isinstance(data.get("generated_at"), str) else "UNKNOWN"
    fingerprint = snapshot.get("digest") or snapshot.get("head_sha") or _sha(str(source.parent).encode())
    return {
        "experience_id": f"EXP-{_sha(raw)[:12]}", "source": {"sha256": _sha(raw), "report_kind": data["report_kind"], "path_redacted": True},
        "report_kind": data["report_kind"], "schema_version": data.get("schema_version", "UNKNOWN"), "observed_at": observed_at,
        "repository_fingerprint": str(fingerprint), "workspace_snapshot": snapshot or {"status": "UNKNOWN"},
        "target": {"aet_version": data.get("schema_version", "UNKNOWN"), "host": data.get("host", "UNKNOWN")},
        "task": {"intent_class": data.get("intent_class", "UNKNOWN")}, "outcome": {"completed": not bool(_deviations(data)), "workflow_deviation": _deviations(data)},
        "deviations": _deviations(data), "privacy": {"raw_transcript_retained": False, "profile": "evidence-only"},
    }


def _experience_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    if data.get("report_kind") != "learning_experiences" or not isinstance(data.get("experiences"), list):
        raise LearnError("experiences input must be an AET learning_experiences artifact")
    return [row for row in data["experiences"] if isinstance(row, dict)]


def _is_evidence_only_experience(row: Any) -> bool:
    allowed = {"experience_id", "source", "report_kind", "schema_version", "observed_at", "repository_fingerprint", "workspace_snapshot", "target", "task", "outcome", "deviations", "privacy"}
    if not isinstance(row, dict) or set(row) - allowed:
        return False
    source, privacy = row.get("source"), row.get("privacy")
    if not isinstance(source, dict) or set(source) - {"sha256", "report_kind", "path_redacted"}:
        return False
    if source.get("path_redacted") is not True or not isinstance(source.get("sha256"), str):
        return False
    return isinstance(privacy, dict) and privacy == {"raw_transcript_retained": False, "profile": "evidence-only"}


def _rule_additions(patterns: list[Any]) -> list[str]:
    kinds = {item.get("kind") for item in patterns if isinstance(item, dict)}
    lines = []
    if "MISSING_TRACE_PROOF" in kinds or any("TRACE" in str(kind) for kind in kinds):
        lines.append("Verify proof-oriented requests with `aet trace -- <command>` before saying a command was proven, attach the Trace path, and do not infer proof from stale reports.")
    if "UNKNOWN_REQUIRES_PRESERVATION" in kinds or any("UNKNOWN" in str(kind) for kind in kinds):
        lines.append("Always preserve UNKNOWN when proof is missing; never summarize it as a pass.")
    return lines or ["Use the smallest safe workflow and attach the structured evidence that supports the final claim."]


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
    if not _valid_patch_ir(metadata, baseline, proposed):
        failures.append("candidate operations are not a valid bounded Patch IR")
    added, deleted = _editable_edit_budget(baseline, proposed)
    if added > 800 or deleted > 400:
        failures.append("edit budget exceeded")
    if _immutable_blocks(baseline) != _immutable_blocks(proposed):
        failures.append("immutable contract changed")
    if _outside_editable_text(baseline) != _outside_editable_text(proposed):
        failures.append("candidate changed outside editable blocks")
    forbidden = ("UNKNOWN is a pass", "automatically adopt", "auto-adopt", "automatically commit", "automatically push")
    if any(value.lower() in proposed.lower() for value in forbidden):
        failures.append("forbidden evidence semantics introduced")
    return failures


def _valid_patch_ir(metadata: dict[str, Any], baseline: str, proposed: str) -> bool:
    operations = metadata.get("operations")
    baseline_blocks = {match.group(1): match.group(2) for match in _EDITABLE_RE.finditer(baseline)}
    proposed_blocks = {match.group(1): match.group(2) for match in _EDITABLE_RE.finditer(proposed)}
    if not isinstance(operations, list) or not 1 <= len(operations) <= 3 or set(baseline_blocks) != set(proposed_blocks):
        return False
    identifiers: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("type") != "replace_editable_block":
            return False
        identifier, replacement = operation.get("id"), operation.get("new_text")
        if not isinstance(identifier, str) or not isinstance(replacement, str) or identifier in identifiers or identifier not in baseline_blocks:
            return False
        if operation.get("before_sha256") != _sha(baseline_blocks[identifier].encode()) or proposed_blocks[identifier] != replacement:
            return False
        identifiers.add(identifier)
    return identifiers == {identifier for identifier in baseline_blocks if baseline_blocks[identifier] != proposed_blocks[identifier]}


def _editable_edit_budget(baseline: str, proposed: str) -> tuple[int, int]:
    baseline_blocks = {match.group(1): match.group(2) for match in _EDITABLE_RE.finditer(baseline)}
    proposed_blocks = {match.group(1): match.group(2) for match in _EDITABLE_RE.finditer(proposed)}
    added = deleted = 0
    for identifier, before in baseline_blocks.items():
        after = proposed_blocks.get(identifier, "")
        for tag, start_before, end_before, start_after, end_after in difflib.SequenceMatcher(a=before, b=after).get_opcodes():
            if tag != "equal":
                deleted += end_before - start_before
                added += end_after - start_after
    return added, deleted


def _gate_binding_failures(result: dict[str, Any], metadata: dict[str, Any], baseline: str, proposed: str) -> list[str]:
    failures = _hard_gate_failures(metadata, baseline, proposed)
    if result.get("status") != Status.PASS.value or result.get("candidate_id") != metadata.get("candidate_id"):
        failures.append("gate did not pass for this candidate id")
    if result.get("baseline_sha256") != metadata.get("baseline_sha256") or result.get("candidate_sha256") != metadata.get("candidate_sha256"):
        failures.append("gate is not hash-bound to this candidate")
    return failures


def _outside_editable_text(text: str) -> str:
    return _EDITABLE_RE.sub(lambda match: f'<!-- aet-learn:editable id="{match.group(1)}" -->\n<editable-body>\n<!-- aet-learn:end -->', text)


def _candidate_audit_failures(metadata: dict[str, Any], proposed: str) -> list[str]:
    target = Path(metadata["target_file"])
    with tempfile.TemporaryDirectory() as temporary:
        sandbox = Path(temporary) / target.parent.name
        shutil.copytree(target.parent, sandbox)
        _atomic_text(sandbox / "SKILL.md", proposed)
        findings = run_rules(sandbox.parent, discover_assets(sandbox.parent))
    return [finding.rule_id for finding in findings if finding.status != Status.PASS]


def _evaluate(text: str, suites: Iterable[Path | None]) -> dict[str, Any]:
    tasks: list[dict[str, Any]] = []
    for suite in suites:
        for source in _json_sources(suite):
            data = _read_json(source)
            if isinstance(data.get("task_id"), str):
                tasks.append(data)
    results = []
    for task in tasks:
        required = [item for item in task.get("required_patterns", []) if isinstance(item, str)]
        forbidden = [item for item in task.get("forbidden_patterns", []) if isinstance(item, str)]
        passed = all(item in text for item in required) and not any(item in text for item in forbidden)
        results.append({"task_id": task["task_id"], "category": task.get("category", "routing"), "status": Status.PASS.value if passed else Status.FAIL.value})
    return {"total": len(results), "passed": sum(item["status"] == Status.PASS.value for item in results), "results": results}


def _suite_fingerprints(suite: Path) -> set[str]:
    return {_sha(source.read_bytes()) for source in _json_sources(suite)}


def _cost_metrics(baseline: str, proposed: str, validation_baseline: dict[str, Any], validation_candidate: dict[str, Any]) -> dict[str, Any]:
    base_tokens, candidate_tokens = _token_estimate(baseline), _token_estimate(proposed)
    base_commands, candidate_commands = baseline.count("aet "), proposed.count("aet ")
    return {
        "skill_tokens": {"baseline": base_tokens, "candidate": candidate_tokens},
        "skill_token_delta": (candidate_tokens - base_tokens) / max(base_tokens, 1),
        "added_tokens": candidate_tokens - base_tokens,
        "command_surface": {"baseline": base_commands, "candidate": candidate_commands}, "command_surface_delta": candidate_commands - base_commands,
        "workflow_overuse_rate": {"baseline": _failure_rate(validation_baseline, "workflow_overuse"), "candidate": _failure_rate(validation_candidate, "workflow_overuse")},
    }


def _quality_vector(validation: dict[str, Any], held_out: dict[str, Any], hard_failures: list[str]) -> dict[str, Any]:
    all_results = validation["results"] + held_out["results"]
    return {
        "correct_routing_rate": _pass_rate(all_results, "routing"), "unsupported_claim_rate": _failure_rate_results(all_results, "evidence_authenticity"),
        "unknown_preservation_rate": _pass_rate(all_results, "unknown"), "intent_boundary_compliance": 1.0 if not hard_failures else 0.0,
        "required_trace_rate": _pass_rate(all_results, "trace"), "evidence_attachment_rate": _pass_rate(all_results, "evidence_handoff"),
    }


def _pass_rate(results: list[dict[str, Any]], category: str) -> float:
    subset = [item for item in results if item.get("category") == category]
    return sum(item["status"] == Status.PASS.value for item in subset) / len(subset) if subset else 1.0


def _failure_rate(result: dict[str, Any], category: str) -> float:
    return _failure_rate_results(result["results"], category)


def _failure_rate_results(results: list[dict[str, Any]], category: str) -> float:
    subset = [item for item in results if item.get("category") == category]
    return sum(item["status"] != Status.PASS.value for item in subset) / len(subset) if subset else 0.0


def _token_estimate(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _apply_model_operations(text: str, blocks: list[Any], response: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    operations = response.get("operations") if isinstance(response, dict) else None
    if not isinstance(operations, list) or not operations or len(operations) > 3:
        raise LearnError("model output must contain one to three bounded operations")
    allowed = {block.group(1) for block in blocks}
    replacements: dict[str, str] = {}
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get("id"), str) or not isinstance(operation.get("new_text"), str):
            raise LearnError("model output operation is invalid")
        if operation["id"] not in allowed or operation["id"] in replacements:
            raise LearnError("model output addresses an unknown or duplicate editable block")
        replacements[operation["id"]] = operation["new_text"]
    result, recorded = text, []
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


def _rejected_summary(rejected: Path | None) -> list[dict[str, str]]:
    return [{"candidate_id": str(data.get("candidate_id", "UNKNOWN")), "reason": str(data.get("reason", "UNKNOWN"))} for source in _json_sources(rejected) if (data := _read_json(source)).get("report_kind") == "learning_rejection"]


def _load_learning_run(output: Path) -> dict[str, Any]:
    path = output / "learning-run.json"
    if path.exists():
        data = _read_json(path)
        if data.get("run_type") == "SKILL_EVOLUTION" and isinstance(data.get("events"), list):
            return data
    return {"schema_version": __version__, "report_kind": "learning_run", "run_type": "SKILL_EVOLUTION", "run_id": f"learn-{_sha(str(output.resolve()).encode())[:12]}", "created_at": _time(), "state": "HARVESTED", "events": []}


def _record_learning_event(run: dict[str, Any], state: str, **details: Any) -> None:
    if state not in _LEARNING_STATES:
        raise LearnError(f"invalid learning state: {state}")
    run["state"] = state
    run["events"].append({"at": _time(), "state": state, **details})


def _write_learning_run(output: Path, run: dict[str, Any]) -> None:
    _write_json(output / "learning-run.json", run)


def _ensure_within_timeout(started: float, timeout_seconds: float) -> None:
    if time.monotonic() - started > timeout_seconds:
        raise LearnError("sleep exceeded its explicit timeout")


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
