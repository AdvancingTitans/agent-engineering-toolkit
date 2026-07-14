"""Optional, append-only lifecycle manifests for AET delivery evidence."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .evidence import EvidenceError, compare_workspace_snapshots, verify_trace_integrity, workspace_snapshot
from .models import RunState, Status


class RunError(ValueError):
    """Raised when a Run Manifest cannot make an evidence-backed transition."""


_REPORT_KINDS = {"audit": "audit", "review": "review", "trace": "trace", "evidence_pack": "evidence_pack"}
_TRANSITIONS = {
    (RunState.CREATED, "bind_intent"): RunState.INTENT_BOUND,
    (RunState.INTENT_BOUND, "attach_audit"): RunState.AUDITED,
    (RunState.INTENT_BOUND, "attach_review"): RunState.REVIEWED,
    (RunState.AUDITED, "attach_review"): RunState.REVIEWED,
    (RunState.REVIEWED, "attach_trace"): RunState.PROVEN,
    (RunState.PROVEN, "attach_evidence_pack"): RunState.PACKED,
    (RunState.PACKED, "close"): RunState.CLOSED,
}


def init_run(output: Path, intent_path: Path) -> dict[str, Any]:
    """Create a Run Manifest bound to one existing human-reviewed intent file."""
    output = output.resolve()
    if output.exists():
        raise RunError(f"run manifest already exists and will not be overwritten: {output}")
    root = Path.cwd().resolve()
    intent = _intent_record(root, intent_path)
    created_at = _timestamp()
    snapshot = workspace_snapshot(root)
    data: dict[str, Any] = {
        "schema_version": __version__,
        "report_kind": "aet_run",
        "run_id": f"run_{uuid.uuid4().hex[:12]}",
        "created_at": created_at,
        "repository": {"root": str(root), "initial_workspace_snapshot": snapshot},
        "intent": intent,
        "artifacts": {kind: [] for kind in _REPORT_KINDS},
        "lifecycle": {"state": RunState.INTENT_BOUND.value, "history": [
            _event("created", RunState.CREATED, RunState.CREATED),
            _event("bind_intent", RunState.CREATED, RunState.INTENT_BOUND, {"intent_sha256": intent["sha256"]}),
        ]},
        "latest_workspace_snapshot": snapshot,
    }
    _write_json(output, data)
    return data


def attach_artifact(manifest_path: Path, kind: str, artifact_path: Path) -> dict[str, Any]:
    """Register an already-produced artifact; this function never runs it."""
    manifest_path = manifest_path.resolve()
    manifest = _load_run(manifest_path)
    if kind not in _REPORT_KINDS:
        raise RunError(f"unknown run artifact kind: {kind}")
    artifact = _artifact_record(manifest, kind, artifact_path)
    if any(item.get("sha256") == artifact["sha256"] for item in manifest["artifacts"].get(kind, []) if isinstance(item, dict)):
        return manifest
    state = _state(manifest)
    if state in (RunState.CLOSED, RunState.STALE):
        raise RunError(f"cannot attach {kind} while run is {state.value}; bind or review a fresh run instead")
    if kind == "trace" and state != RunState.REVIEWED:
        raise RunError("a Trace can be attached only after a passing review")
    if kind == "evidence_pack" and state != RunState.PROVEN:
        raise RunError("an Evidence Pack can be attached only after a passing proof")

    manifest["artifacts"][kind].append(artifact)
    manifest["latest_workspace_snapshot"] = artifact["workspace_snapshot"]
    next_state = state
    event = f"attach_{kind}"
    if kind == "review" and _report_passes(artifact["report"]):
        _assert_bound_intent(manifest, artifact["report"])
        next_state = _transition(state, event)
    elif kind == "trace" and _trace_passes(artifact["report"]):
        _assert_trace_matches_intent(manifest, artifact["report"])
        next_state = _transition(state, event)
    elif kind == "evidence_pack":
        if artifact["report"].get("snapshot_binding", {}).get("status") != Status.PASS.value:
            raise RunError("Evidence Pack snapshot binding must be PASS before packing a run")
        next_state = _transition(state, event)
    elif kind == "audit" and state == RunState.INTENT_BOUND:
        next_state = _transition(state, event)
    _append_event(manifest, event, state, next_state, {"artifact": {"kind": kind, "sha256": artifact["sha256"]}})
    _write_json(manifest_path, manifest)
    return manifest


def run_status(manifest_path: Path) -> dict[str, Any]:
    """Return the current lifecycle position without mutating the manifest."""
    manifest = _load_run(manifest_path.resolve())
    current = _current_snapshot(manifest)
    binding = compare_workspace_snapshots({"run": manifest["latest_workspace_snapshot"], "current": current})
    stored = _state(manifest)
    live = RunState.STALE if binding.get("status") == Status.FAIL.value and stored != RunState.CLOSED else stored
    return {
        "report_kind": "aet_run_status",
        "run_id": manifest["run_id"],
        "stored_state": stored.value,
        "state": live.value,
        "workspace_snapshot": current,
        "snapshot_binding": binding,
        "artifacts": {kind: len(items) for kind, items in manifest["artifacts"].items()},
    }


def verify_run(manifest_path: Path) -> dict[str, Any]:
    """Persist an observed stale state; otherwise return the read-only status."""
    manifest_path = manifest_path.resolve()
    status = run_status(manifest_path)
    manifest = _load_run(manifest_path)
    if status["state"] == RunState.STALE.value and _state(manifest) != RunState.STALE:
        previous = _state(manifest)
        manifest["latest_workspace_snapshot"] = status["workspace_snapshot"]
        _append_event(manifest, "repository_changed", previous, RunState.STALE, {"snapshot_binding": status["snapshot_binding"]})
        _write_json(manifest_path, manifest)
        status["stored_state"] = RunState.STALE.value
    return status


def close_run(manifest_path: Path) -> dict[str, Any]:
    """Close only a fresh, fully packed run."""
    manifest_path = manifest_path.resolve()
    status = verify_run(manifest_path)
    manifest = _load_run(manifest_path)
    if _state(manifest) != RunState.PACKED or status["snapshot_binding"].get("status") != Status.PASS.value:
        raise RunError("only a fresh PACKED run can be closed")
    _append_event(manifest, "close", RunState.PACKED, RunState.CLOSED)
    _write_json(manifest_path, manifest)
    return run_status(manifest_path)


def render_run_status(status: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(status, indent=2, ensure_ascii=False) + "\n"
    return (
        f"# AET Run {status['run_id']}\n\n"
        f"- State: `{status['state']}` (stored: `{status['stored_state']}`)\n"
        f"- Snapshot binding: `{status['snapshot_binding'].get('status', 'UNKNOWN')}`"
        f" ({status['snapshot_binding'].get('state', status['snapshot_binding'].get('reason', 'not verified'))})\n"
        f"- Artifacts: " + ", ".join(f"{kind}={count}" for kind, count in status["artifacts"].items()) + "\n"
    )


def _intent_record(root: Path, path: Path) -> dict[str, str]:
    candidate = path if path.is_absolute() else root / path
    candidate = candidate.resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError as error:
        raise RunError("intent contract must be inside the run workspace") from error
    if not candidate.is_file():
        raise RunError(f"intent contract does not exist: {candidate}")
    return {"path": relative, "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()}


def _artifact_record(manifest: dict[str, Any], kind: str, path: Path) -> dict[str, Any]:
    source = path.resolve()
    if not source.is_file():
        raise RunError(f"artifact does not exist: {source}")
    if kind == "trace":
        try:
            verify_trace_integrity(source)
        except EvidenceError as error:
            raise RunError(f"Trace integrity verification failed: {error}") from error
    try:
        report = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunError(f"cannot read {kind} artifact: {error}") from error
    if not isinstance(report, dict) or report.get("report_kind") != _REPORT_KINDS[kind]:
        raise RunError(f"artifact is not a {kind} report")
    if kind != "evidence_pack" and report.get("root") != manifest["repository"]["root"]:
        raise RunError("artifact was produced for a different workspace root")
    snapshot = report.get("workspace_snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("status") != Status.PASS.value:
        raise RunError("artifact is missing a complete workspace snapshot")
    return {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "workspace_snapshot": snapshot, "report": report}


def _assert_bound_intent(manifest: dict[str, Any], report: dict[str, Any]) -> None:
    review = report.get("review")
    if not isinstance(review, dict) or review.get("contract_sha256") != manifest["intent"]["sha256"]:
        raise RunError("review contract hash does not match the Run Manifest intent")


def _assert_trace_matches_intent(manifest: dict[str, Any], report: dict[str, Any]) -> None:
    proof = report.get("trace", {}).get("proof") if isinstance(report.get("trace"), dict) else None
    if not isinstance(proof, dict) or proof.get("intent_sha256") != manifest["intent"]["sha256"]:
        raise RunError("Trace proof is not bound to the Run Manifest intent")


def _report_passes(report: dict[str, Any]) -> bool:
    summary = report.get("summary")
    return isinstance(summary, dict) and summary.get(Status.FAIL.value) == 0


def _trace_passes(report: dict[str, Any]) -> bool:
    trace = report.get("trace", {})
    artifacts = trace.get("artifacts", []) if isinstance(trace, dict) else []
    summary = report.get("summary", {})
    validators = report.get("validators", [])
    return (
        isinstance(trace, dict)
        and trace.get("execution", {}).get("status") == Status.PASS.value
        and isinstance(summary, dict)
        and summary.get(Status.FAIL.value) == 0
        and summary.get(Status.UNKNOWN.value) == 0
        and isinstance(artifacts, list)
        and all(isinstance(item, dict) and item.get("status") == Status.PASS.value for item in artifacts)
        and isinstance(validators, list)
        and all(isinstance(item, dict) and item.get("status") == Status.PASS.value for item in validators)
    )


def _transition(state: RunState, event: str) -> RunState:
    try:
        return _TRANSITIONS[(state, event)]
    except KeyError as error:
        raise RunError(f"event {event!r} is not allowed from {state.value}") from error


def _state(manifest: dict[str, Any]) -> RunState:
    try:
        return RunState(manifest["lifecycle"]["state"])
    except (KeyError, ValueError, TypeError) as error:
        raise RunError("run manifest has an invalid lifecycle state") from error


def _append_event(manifest: dict[str, Any], event: str, previous: RunState, next_state: RunState, detail: dict[str, Any] | None = None) -> None:
    manifest["lifecycle"]["history"].append(_event(event, previous, next_state, detail))
    manifest["lifecycle"]["state"] = next_state.value


def _event(event: str, previous: RunState, next_state: RunState, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"at": _timestamp(), "event": event, "from": previous.value, "to": next_state.value, **({"detail": detail} if detail else {})}


def _current_snapshot(manifest: dict[str, Any]) -> dict[str, Any]:
    return workspace_snapshot(Path(manifest["repository"]["root"]))


def _load_run(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunError(f"cannot read run manifest: {error}") from error
    if not isinstance(data, dict) or data.get("report_kind") != "aet_run" or not isinstance(data.get("artifacts"), dict):
        raise RunError("input is not an AET Run Manifest")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
