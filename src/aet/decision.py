"""Source-backed local Decision Ledgers for durable project facts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .evidence import workspace_snapshot
from .models import Status


class DecisionError(ValueError):
    """Raised when a Decision Ledger cannot preserve its source boundary."""


_EVIDENCE_STATES = {"EVIDENCED", "ATTESTED", "INFERRED", "UNKNOWN"}
_DECISION_STATES = {"PROPOSED", "ACCEPTED", "SUPERSEDED"}


def init_ledger(output: Path) -> dict[str, Any]:
    """Create an empty local ledger without overwriting a prior decision record."""
    output = output.resolve()
    if output.exists():
        raise DecisionError(f"decision ledger already exists and will not be overwritten: {output}")
    root = Path.cwd().resolve()
    data = {
        "schema_version": __version__,
        "report_kind": "decision_ledger",
        "created_at": _timestamp(),
        "root": str(root),
        "workspace_snapshot": workspace_snapshot(root),
        "decisions": [],
        "history": [],
    }
    _write_json(output, data)
    return data


def add_decision(
    ledger_path: Path,
    *,
    identifier: str,
    claim: str,
    evidence_state: str,
    state: str,
    sources: Iterable[str],
    supersedes: Iterable[str],
) -> dict[str, Any]:
    """Add one explicit decision and optionally supersede earlier ledger entries."""
    ledger_path = ledger_path.resolve()
    ledger = _load_ledger(ledger_path)
    if not identifier or any(item["id"] == identifier for item in ledger["decisions"]):
        raise DecisionError("decision id must be non-empty and unique")
    if not claim.strip():
        raise DecisionError("decision claim must be non-empty")
    if evidence_state not in _EVIDENCE_STATES or state not in _DECISION_STATES - {"SUPERSEDED"}:
        raise DecisionError("decision evidence state or lifecycle state is invalid")
    root = Path(ledger["root"])
    source_records = _sources(root, sources)
    if evidence_state in {"EVIDENCED", "INFERRED"} and not source_records:
        raise DecisionError(f"{evidence_state} decisions require at least one local source")
    prior = {decision["id"]: decision for decision in ledger["decisions"]}
    target_ids = list(dict.fromkeys(supersedes))
    if target_ids and state != "ACCEPTED":
        raise DecisionError("a replacement decision must be ACCEPTED before it can supersede another decision")
    for target_id in target_ids:
        target = prior.get(target_id)
        if target is None or target_id == identifier:
            raise DecisionError(f"superseded decision does not exist: {target_id}")
        if target["state"] == "SUPERSEDED":
            raise DecisionError(f"decision is already superseded: {target_id}")
    decision = {
        "id": identifier,
        "claim": claim.strip(),
        "state": state,
        "evidence_state": evidence_state,
        "sources": source_records,
        "created_at": _timestamp(),
        "supersedes": target_ids,
    }
    ledger["decisions"].append(decision)
    ledger["history"].append(_event("added", identifier))
    for target_id in target_ids:
        _supersede(ledger, target_id, identifier)
    _write_json(ledger_path, ledger)
    return ledger


def supersede_decision(ledger_path: Path, *, identifier: str, replacement: str) -> dict[str, Any]:
    """Mark one live decision superseded by an already accepted replacement."""
    ledger_path = ledger_path.resolve()
    ledger = _load_ledger(ledger_path)
    decisions = {decision["id"]: decision for decision in ledger["decisions"]}
    target = decisions.get(identifier)
    next_decision = decisions.get(replacement)
    if target is None or next_decision is None or identifier == replacement:
        raise DecisionError("supersede requires distinct existing decision ids")
    if target["state"] == "SUPERSEDED":
        raise DecisionError(f"decision is already superseded: {identifier}")
    if next_decision["state"] != "ACCEPTED":
        raise DecisionError("replacement decision must be ACCEPTED")
    _supersede(ledger, identifier, replacement)
    _write_json(ledger_path, ledger)
    return ledger


def list_decisions(ledger_path: Path) -> dict[str, Any]:
    """Return the current decisions without mutating the ledger."""
    ledger = _load_ledger(ledger_path.resolve())
    return {
        "schema_version": __version__,
        "report_kind": "decision_list",
        "root": ledger["root"],
        "decisions": ledger["decisions"],
    }


def verify_ledger(ledger_path: Path) -> dict[str, Any]:
    """Verify source hashes without asserting that any decision remains correct."""
    ledger = _load_ledger(ledger_path.resolve())
    root = Path(ledger["root"])
    results: list[dict[str, Any]] = []
    for decision in ledger["decisions"]:
        source_results: list[dict[str, Any]] = []
        for source in decision["sources"]:
            candidate = root / source["path"]
            if not candidate.is_file():
                source_results.append({"path": source["path"], "status": Status.FAIL.value, "reason": "recorded source is missing"})
                continue
            actual = _sha256(candidate)
            if actual != source["sha256"]:
                source_results.append({"path": source["path"], "status": Status.FAIL.value, "recorded_sha256": source["sha256"], "current_sha256": actual})
            else:
                source_results.append({"path": source["path"], "status": Status.PASS.value, "sha256": actual})
        results.append({
            "id": decision["id"],
            "evidence_state": decision["evidence_state"],
            "status": Status.FAIL.value if any(item["status"] == Status.FAIL.value for item in source_results) else Status.PASS.value,
            "sources": source_results,
        })
    status = Status.FAIL.value if any(item["status"] == Status.FAIL.value for item in results) else Status.PASS.value
    return {
        "schema_version": __version__,
        "report_kind": "decision_verification",
        "generated_at": _timestamp(),
        "root": str(root),
        "status": status,
        "decisions": results,
    }


def render_decisions(result: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    lines = ["# AET Decision Ledger", ""]
    if "status" in result:
        lines.extend([f"- Verification status: `{result['status']}`", ""])
    lines.extend(["| Decision | State | Evidence |", "|---|---|---|"])
    for decision in result["decisions"]:
        lines.append(f"| `{decision['id']}` | {decision.get('state', decision['status'])} | {decision['evidence_state']} |")
    return "\n".join(lines) + "\n"


def _supersede(ledger: dict[str, Any], identifier: str, replacement: str) -> None:
    target = next(decision for decision in ledger["decisions"] if decision["id"] == identifier)
    target["state"] = "SUPERSEDED"
    target["superseded_by"] = replacement
    ledger["history"].append(_event("superseded", identifier, {"replacement": replacement}))


def _sources(root: Path, values: Iterable[str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for value in dict.fromkeys(values):
        candidate = (root / value).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError as error:
            raise DecisionError("decision source must be inside the ledger root") from error
        if not candidate.is_file():
            raise DecisionError(f"decision source does not exist or is not a regular file: {relative}")
        records.append({"path": relative, "sha256": _sha256(candidate)})
    return records


def _load_ledger(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DecisionError(f"cannot read decision ledger: {error}") from error
    if not isinstance(data, dict) or data.get("report_kind") != "decision_ledger":
        raise DecisionError("input is not an AET Decision Ledger")
    if not isinstance(data.get("root"), str) or not isinstance(data.get("decisions"), list) or not isinstance(data.get("history"), list):
        raise DecisionError("decision ledger is missing required fields")
    if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("sources"), list) for item in data["decisions"]):
        raise DecisionError("decision ledger has an invalid decision")
    return data


def _event(event: str, identifier: str, detail: dict[str, str] | None = None) -> dict[str, Any]:
    return {"at": _timestamp(), "event": event, "id": identifier, **({"detail": detail} if detail else {})}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
