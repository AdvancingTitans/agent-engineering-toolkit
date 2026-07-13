"""Opt-in command traces and portable Evidence Pack compilation."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import __version__
from .models import Status


class EvidenceError(ValueError):
    """Raised when evidence cannot be safely captured or compiled."""


_SUMMARY_STATUSES = tuple(status.value for status in Status)
_DEFAULT_SECRET_PATTERNS = (
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)\s*([=:])\s*([^\s'\"]+)",
    r"(?i)(--(?:api[_-]?key|token|secret|password|passwd)|authorization)(\s+)(\S+)",
    r"(?i)\bbearer\s+[a-z0-9._~+\-/=]+",
    r"\bsk-[A-Za-z0-9_-]{12,}\b",
    r"\bgh[pousr]_[A-Za-z0-9_]{12,}\b",
)


def trace_command(
    argv: list[str],
    output: Path,
    redaction_patterns: Iterable[str] = (),
    proof: dict[str, Any] | None = None,
    artifact_paths: Iterable[str] = (),
) -> tuple[dict[str, Any], int]:
    """Run one explicit argv command and persist only redacted command evidence."""
    if not argv:
        raise EvidenceError("trace requires an explicit command after --")
    patterns = _compile_patterns(redaction_patterns)
    output = output.resolve()
    cwd = Path.cwd().resolve()
    artifacts_to_capture = _declared_artifact_paths(artifact_paths, cwd)
    artifacts_before = [_capture_artifact(path, cwd, patterns) for path in artifacts_to_capture]
    started_at = _timestamp()
    try:
        completed = subprocess.run(argv, cwd=cwd, capture_output=True, check=False)
        exit_code = completed.returncode
        stdout_bytes, stderr_bytes = completed.stdout, completed.stderr
    except FileNotFoundError as error:
        exit_code = 127
        stdout_bytes = b""
        stderr_bytes = str(error).encode("utf-8", errors="replace")
    finished_at = _timestamp()

    redacted_argv, argv_status = _redact_argv(argv, patterns)
    stdout = _redacted_log(stdout_bytes, patterns)
    stderr = _redacted_log(stderr_bytes, patterns)
    stdout_path = _log_path(output, "stdout")
    stderr_path = _log_path(output, "stderr")
    _atomic_write_text(stdout_path, stdout["content"])
    _atomic_write_text(stderr_path, stderr["content"])
    artifacts = []
    for path, before in zip(artifacts_to_capture, artifacts_before):
        after = _capture_artifact(path, cwd, patterns)
        if after.get("status") == Status.PASS.value:
            if before.get("status") != Status.PASS.value:
                after["freshness"] = "CREATED"
            elif before.get("sha256") != after.get("sha256"):
                after["freshness"] = "CHANGED"
            else:
                after["freshness"] = "UNCHANGED"
        else:
            after["freshness"] = Status.UNKNOWN.value
        artifacts.append(after)

    execution_status = Status.PASS.value if exit_code == 0 else Status.FAIL.value
    unknowns = sum(item["status"] == Status.UNKNOWN.value for item in (stdout, stderr))
    if argv_status == Status.UNKNOWN.value:
        unknowns += 1
    unknowns += sum(item["status"] == Status.UNKNOWN.value for item in artifacts)
    data = {
        "schema_version": __version__,
        "report_kind": "trace",
        "generated_at": finished_at,
        "run_id": hashlib.sha256((str(output) + started_at).encode("utf-8")).hexdigest()[:16],
        "tool": {"name": "aet", "version": __version__},
        "scope": {"root": str(cwd)},
        "root": str(cwd),
        "assets": [],
        "sources": [],
        "claims": [],
        "findings": [],
        "workspace_snapshot": workspace_snapshot(cwd),
        "summary": {
            Status.PASS.value: int(execution_status == Status.PASS.value),
            Status.FAIL.value: int(execution_status == Status.FAIL.value),
            Status.UNKNOWN.value: unknowns,
            Status.NOT_APPLICABLE.value: 0,
        },
        "trace": {
            "argv": redacted_argv,
            "argv_status": argv_status,
            "execution": {"status": execution_status, "exit_code": exit_code},
            "started_at": started_at,
            "finished_at": finished_at,
            "working_directory": str(cwd),
            "git": _git_metadata(cwd),
            "stdout": _artifact_record(stdout_path, stdout),
            "stderr": _artifact_record(stderr_path, stderr),
            "artifacts": artifacts,
            **({"proof": proof} if proof else {}),
        },
    }
    _atomic_write_json(output, data)
    # A command result and its explicitly requested evidence are separate facts.
    # A missing report must fail a CI invocation without rewriting a successful
    # child exit status as though the command itself failed.
    return data, exit_code if exit_code else (1 if any(item["status"] != Status.PASS.value for item in artifacts) else 0)


def compile_evidence_pack(*, audit: Path | None, review: Path | None, trace: Path | None, output: Path) -> dict[str, Any]:
    """Compile validated reports into a content-addressed, host-neutral pack."""
    components = {
        "audit": _component("audit", audit),
        "review": _component("review", review),
        "trace": _component("trace", trace),
    }
    proof_binding = _proof_binding(components)
    pack_snapshot = _pack_workspace_snapshot(components)
    binding = compare_workspace_snapshots({
        "pack": pack_snapshot,
        **{
            kind: component["report"].get("workspace_snapshot")
            for kind, component in components.items()
            if component["status"] == Status.PASS.value and isinstance(component.get("report"), dict)
        },
    })
    data = {
        "schema_version": __version__,
        "report_kind": "evidence_pack",
        "generated_at": _timestamp(),
        "components": components,
        "proof_binding": proof_binding,
        "workspace_snapshot": pack_snapshot,
        "snapshot_binding": binding,
    }
    _atomic_write_json(output.resolve(), data)
    return data


def bind_proof(intent_path: Path, proof_id: str) -> dict[str, Any]:
    """Bind a Trace to one declared proof without executing the declared command."""
    if not proof_id:
        raise EvidenceError("proof id must be non-empty")
    try:
        contract = json.loads(intent_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read proof contract: {error}") from error
    proofs = contract.get("required_proofs") if isinstance(contract, dict) else None
    if not isinstance(proofs, list):
        raise EvidenceError("proof contract has no required_proofs list")
    for proof in proofs:
        if isinstance(proof, dict) and proof.get("id") == proof_id and isinstance(proof.get("command"), str):
            return {"id": proof_id, "intent_path": str(intent_path.resolve()), "intent_sha256": hashlib.sha256(intent_path.read_bytes()).hexdigest(), "command": proof["command"], "status": Status.PASS.value}
    raise EvidenceError(f"proof id is not declared by contract: {proof_id}")


def render_evidence_viewer(pack_path: Path, output: Path) -> None:
    """Render a no-network static review surface from an existing JSON pack."""
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceError(f"cannot read Evidence Pack: {error}") from error
    if pack.get("report_kind") != "evidence_pack":
        raise EvidenceError("viewer input must have report_kind=evidence_pack")
    pretty = html.escape(json.dumps(pack, indent=2, ensure_ascii=False))
    proof_status = html.escape(str(pack.get("proof_binding", {}).get("status", "UNKNOWN")))
    snapshot = pack.get("snapshot_binding", {})
    snapshot_status = html.escape(str(snapshot.get("status", "UNKNOWN")))
    snapshot_state = html.escape(str(snapshot.get("state", snapshot.get("reason", "not verified"))))
    delivery_state = "READY" if proof_status == Status.PASS.value and snapshot_status == Status.PASS.value else "STALE" if snapshot_status == Status.FAIL.value else "INCOMPLETE"
    content = (
        "<!doctype html><meta charset=utf-8><title>AET Evidence Pack</title>"
        "<style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem}"
        "table{border-collapse:collapse;width:100%;max-width:680px}th,td{border:1px solid #d0d7de;padding:.65rem;text-align:left}"
        "th{background:#f6f8fa}pre{white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:6px}</style>"
        "<h1>Evidence Pack</h1><table><tr><th>Delivery state</th><td><strong>" + delivery_state + "</strong></td></tr>"
        "<tr><th>Proof binding</th><td>" + proof_status + "</td></tr>"
        "<tr><th>Snapshot binding</th><td>" + snapshot_status + " — " + snapshot_state + "</td></tr></table>"
        "<p>Proof binding records whether the declared command succeeded. Snapshot binding separately records whether the supplied evidence and current workspace are the same revision.</p>"
        "<details><summary>Raw Evidence Pack JSON</summary><pre>" + pretty + "</pre></details>"
    )
    _atomic_write_text(output.resolve(), content + "\n")


def _component(kind: str, path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"status": Status.UNKNOWN.value, "reason": "component was not supplied"}
    source = path.resolve()
    if not source.is_file():
        raise EvidenceError(f"{kind} input does not exist: {source}")
    raw = source.read_bytes()
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EvidenceError(f"{kind} input is invalid JSON at line {error.lineno}") from error
    _validate_report(kind, report)
    return {
        "status": Status.PASS.value,
        "source": str(source),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "report": _portable_report(kind, report),
    }


def _proof_binding(components: dict[str, dict[str, Any]]) -> dict[str, Any]:
    review = components["review"]
    trace = components["trace"]
    if review["status"] != Status.PASS.value or trace["status"] != Status.PASS.value:
        return {"status": Status.UNKNOWN.value, "reason": "review or trace component was not supplied"}
    trace_proof = trace["report"].get("proof")
    if not isinstance(trace_proof, dict):
        return {"status": Status.UNKNOWN.value, "reason": "trace was not bound to a declared proof"}
    review_metadata = review["report"].get("review", {})
    declared = {proof.get("id"): proof for proof in review_metadata.get("proofs", []) if isinstance(proof, dict)}
    proof = declared.get(trace_proof.get("id"))
    if proof is None:
        return {"status": Status.FAIL.value, "reason": "trace proof id is absent from review contract"}
    if review_metadata.get("contract_sha256") != trace_proof.get("intent_sha256"):
        return {"status": Status.FAIL.value, "reason": "trace contract hash does not match review contract"}
    execution = trace["report"].get("execution", {})
    if execution.get("status") != Status.PASS.value:
        return {"status": Status.FAIL.value, "reason": "bound proof command did not exit successfully"}
    artifacts = trace["report"].get("artifacts", [])
    if not isinstance(artifacts, list) or any(not isinstance(item, dict) or item.get("status") != Status.PASS.value for item in artifacts):
        return {"status": Status.UNKNOWN.value, "reason": "a declared trace artifact was not safely captured"}
    return {"status": Status.PASS.value, "proof_id": trace_proof["id"], "contract_sha256": trace_proof["intent_sha256"]}


def workspace_snapshot(cwd: Path) -> dict[str, Any]:
    """Capture the Git state that an artifact can actually support."""
    root = cwd.resolve()
    head = _git(root, "rev-parse", "HEAD")
    diff = _git(root, "diff", "--binary", "HEAD", "--")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard")
    if head is None or diff is None or untracked is None:
        return {"status": Status.UNKNOWN.value, "reason": "Git workspace state could not be captured"}
    tracked_worktree_sha256 = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    worktree = hashlib.sha256()
    worktree.update(b"tracked\\0" + diff.encode("utf-8"))
    untracked_manifest = hashlib.sha256()
    for relative in sorted(line for line in untracked.splitlines() if line):
        candidate = root / relative
        untracked_manifest.update(relative.encode("utf-8") + b"\\0")
        if candidate.is_file():
            untracked_manifest.update(hashlib.sha256(candidate.read_bytes()).digest())
        else:
            untracked_manifest.update(b"[not-a-file]")
    worktree.update(b"untracked\\0" + untracked_manifest.digest())
    worktree_digest = worktree.hexdigest()
    digest = hashlib.sha256((head.strip() + "\\0" + worktree_digest).encode("utf-8")).hexdigest()
    intent = _control_file_fingerprint(root, "aet.intent.json")
    config = _control_file_fingerprint(root, "aet.toml")
    return {
        "status": Status.PASS.value,
        "head_sha": head.strip(),
        "tracked_worktree_sha256": tracked_worktree_sha256,
        "worktree_digest": worktree_digest,
        "untracked_manifest_sha256": untracked_manifest.hexdigest(),
        "digest": digest,
        "intent_sha256": intent["sha256"],
        "config_sha256": config["sha256"],
        "control_files": {"intent": intent, "config": config},
    }


def _pack_workspace_snapshot(components: dict[str, dict[str, Any]]) -> dict[str, Any]:
    roots = {
        component["report"].get("root")
        for component in components.values()
        if component["status"] == Status.PASS.value and isinstance(component.get("report"), dict)
    }
    if len(roots) != 1 or not isinstance(next(iter(roots), None), str):
        return {"status": Status.UNKNOWN.value, "reason": "supplied reports do not share one workspace root"}
    return workspace_snapshot(Path(next(iter(roots))))


def compare_workspace_snapshots(snapshots: Mapping[str, Any]) -> dict[str, Any]:
    """Compare named snapshots without changing any proof or finding result."""
    unavailable = [name for name, snapshot in snapshots.items() if not _is_complete_snapshot(snapshot)]
    if unavailable:
        return {"status": Status.UNKNOWN.value, "reason": f"workspace snapshot unavailable for: {', '.join(unavailable)}"}
    digests = {snapshot["digest"] for snapshot in snapshots.values()}
    if len(digests) == 1:
        return {"status": Status.PASS.value, "state": "EXACT_MATCH", "digest": next(iter(digests))}
    control_changes = _changed_control_files(snapshots.values())
    if control_changes == {"intent"}:
        state = "INTENT_CHANGED"
    elif control_changes == {"config"}:
        state = "CONFIG_CHANGED"
    elif control_changes:
        state = "CONTROL_FILES_CHANGED"
    elif len({snapshot["head_sha"] for snapshot in snapshots.values()}) != 1:
        state = "HEAD_DIFFERS"
    elif len({snapshot["untracked_manifest_sha256"] for snapshot in snapshots.values()}) != 1 and len({snapshot["tracked_worktree_sha256"] for snapshot in snapshots.values()}) == 1:
        state = "UNTRACKED_SET_CHANGED"
    else:
        state = "HEAD_MATCH_WORKTREE_DIFFERS"
    return {"status": Status.FAIL.value, "state": state, "snapshots": {name: snapshot["digest"] for name, snapshot in snapshots.items()}}


def _is_complete_snapshot(snapshot: Any) -> bool:
    return (
        isinstance(snapshot, dict)
        and snapshot.get("status") == Status.PASS.value
        and all(isinstance(snapshot.get(field), str) and snapshot[field] for field in ("head_sha", "tracked_worktree_sha256", "worktree_digest", "untracked_manifest_sha256", "digest"))
    )


def _control_file_fingerprint(root: Path, relative: str) -> dict[str, Any]:
    candidate = root / relative
    if not candidate.exists():
        return {"path": relative, "status": Status.NOT_APPLICABLE.value, "sha256": None}
    if not candidate.is_file():
        return {"path": relative, "status": Status.UNKNOWN.value, "sha256": None}
    return {"path": relative, "status": Status.PASS.value, "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()}


def _changed_control_files(snapshots: Iterable[dict[str, Any]]) -> set[str]:
    values = list(snapshots)
    changed: set[str] = set()
    for name, key in (("intent", "intent_sha256"), ("config", "config_sha256")):
        if len({snapshot.get(key) for snapshot in values}) != 1:
            changed.add(name)
    return changed


def _validate_report(kind: str, report: Any) -> None:
    if not isinstance(report, dict):
        raise EvidenceError(f"{kind} input must be a JSON object")
    if report.get("report_kind") != kind:
        raise EvidenceError(f"{kind} input has report_kind={report.get('report_kind')!r}")
    if not isinstance(report.get("schema_version"), str):
        raise EvidenceError(f"{kind} input is missing schema_version")
    for field in ("generated_at", "root"):
        if not isinstance(report.get(field), str):
            raise EvidenceError(f"{kind} input is missing {field}")
    if not isinstance(report.get("assets"), list) or not isinstance(report.get("findings"), list):
        raise EvidenceError(f"{kind} input must contain assets and findings arrays")
    summary = report.get("summary")
    if not isinstance(summary, dict) or set(summary) != set(_SUMMARY_STATUSES):
        raise EvidenceError(f"{kind} input has an invalid summary")
    if not all(isinstance(summary[status], int) and not isinstance(summary[status], bool) and summary[status] >= 0 for status in _SUMMARY_STATUSES):
        raise EvidenceError(f"{kind} input has non-integer summary counts")
    if kind == "review" and not isinstance(report.get("review"), dict):
        raise EvidenceError("review input is missing review metadata")
    if kind == "trace":
        trace = report.get("trace")
        if not isinstance(trace, dict) or not isinstance(trace.get("execution"), dict):
            raise EvidenceError("trace input is missing trace execution metadata")
        execution = trace["execution"]
        if execution.get("status") not in (Status.PASS.value, Status.FAIL.value) or not isinstance(execution.get("exit_code"), int):
            raise EvidenceError("trace input has invalid execution metadata")


def _portable_report(kind: str, report: dict[str, Any]) -> dict[str, Any]:
    portable = {
        "schema_version": report["schema_version"],
        "report_kind": kind,
        "generated_at": report["generated_at"],
        "root": report["root"],
        "summary": report["summary"],
        "findings": report["findings"],
    }
    if "workspace_snapshot" in report:
        portable["workspace_snapshot"] = report["workspace_snapshot"]
    if kind == "review":
        portable["review"] = report["review"]
    if kind == "audit" and "audit_engine" in report:
        portable["audit_engine"] = report["audit_engine"]
    if kind == "trace":
        # Raw stdout/stderr never enter the pack. Explicitly requested text
        # artifacts are already redacted and are portable by user choice.
        portable["execution"] = report["trace"]["execution"]
        portable["git"] = report["trace"].get("git")
        portable["stdout"] = _portable_artifact(report["trace"].get("stdout"))
        portable["stderr"] = _portable_artifact(report["trace"].get("stderr"))
        portable["artifacts"] = [_portable_captured_artifact(item) for item in report["trace"].get("artifacts", []) if isinstance(item, dict)]
        if "proof" in report["trace"]:
            portable["proof"] = report["trace"]["proof"]
        if "validators" in report:
            portable["validators"] = report["validators"]
    return portable


def _portable_artifact(artifact: Any) -> dict[str, Any] | None:
    if not isinstance(artifact, dict):
        return None
    return {key: artifact.get(key) for key in ("status", "sha256", "excerpt")}


def _portable_captured_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    return {key: artifact.get(key) for key in ("requested_path", "status", "reason", "sha256", "freshness", "content") if key in artifact}


def _compile_patterns(custom_patterns: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    try:
        return tuple(re.compile(pattern) for pattern in (*_DEFAULT_SECRET_PATTERNS, *custom_patterns))
    except re.error as error:
        raise EvidenceError(f"invalid redaction pattern: {error}") from error


def _redact_argv(argv: list[str], patterns: tuple[re.Pattern[str], ...]) -> tuple[list[str] | None, str]:
    redacted: list[str] = []
    for value in argv:
        result = _redact_text(value, patterns)
        if result is None:
            return None, Status.UNKNOWN.value
        redacted.append(result)
    return redacted, Status.PASS.value


def _redacted_log(raw: bytes, patterns: tuple[re.Pattern[str], ...]) -> dict[str, Any]:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"status": Status.UNKNOWN.value, "content": "[UNKNOWN: log could not be decoded safely]\n", "excerpt": None}
    redacted = _redact_text(decoded, patterns)
    if redacted is None:
        return {"status": Status.UNKNOWN.value, "content": "[UNKNOWN: log could not be redacted safely]\n", "excerpt": None}
    return {"status": Status.PASS.value, "content": redacted, "excerpt": redacted[:1000]}


def _declared_artifact_paths(paths: Iterable[str], cwd: Path) -> list[Path]:
    declared: list[Path] = []
    for value in paths:
        candidate = Path(value)
        if candidate.is_absolute():
            raise EvidenceError("trace artifact paths must be relative to the working directory")
        resolved = (cwd / candidate).resolve()
        if not _is_within(resolved, cwd):
            raise EvidenceError("trace artifact paths must remain inside the working directory")
        declared.append(resolved)
    return declared


def _capture_artifact(path: Path, cwd: Path, patterns: tuple[re.Pattern[str], ...]) -> dict[str, Any]:
    resolved = path.resolve()
    requested_path = resolved.relative_to(cwd).as_posix() if _is_within(resolved, cwd) else path.name
    if not _is_within(resolved, cwd):
        return {"requested_path": requested_path, "status": Status.UNKNOWN.value, "reason": "artifact resolved outside the working directory"}
    if not resolved.is_file():
        return {"requested_path": requested_path, "status": Status.UNKNOWN.value, "reason": "declared artifact was not created as a regular file"}
    try:
        redacted = _redacted_log(resolved.read_bytes(), patterns)
    except OSError as error:
        return {"requested_path": requested_path, "status": Status.UNKNOWN.value, "reason": f"artifact could not be read safely: {error}"}
    if redacted["status"] != Status.PASS.value:
        return {"requested_path": requested_path, "status": Status.UNKNOWN.value, "reason": "artifact could not be decoded or redacted safely"}
    content = redacted["content"]
    return {
        "requested_path": requested_path,
        "status": Status.PASS.value,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content": content,
    }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _redact_text(value: str, patterns: tuple[re.Pattern[str], ...]) -> str | None:
    try:
        for pattern in patterns:
            value = pattern.sub(_redaction_replacement, value)
    except (re.error, TypeError):
        return None
    return value


def _redaction_replacement(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 2 and match.group(2) in ("=", ":"):
        return f"{match.group(1)}{match.group(2)}[REDACTED]"
    if match.lastindex and match.lastindex >= 3 and match.group(2).isspace():
        return f"{match.group(1)}{match.group(2)}[REDACTED]"
    return "[REDACTED]"


def _artifact_record(path: Path, log: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": log["status"],
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "excerpt": log["excerpt"],
    }


def _git_metadata(cwd: Path) -> dict[str, Any]:
    snapshot = workspace_snapshot(cwd)
    if snapshot["status"] != Status.PASS.value:
        return {
            "head": {"status": Status.UNKNOWN.value},
            "diff_digest": {"status": Status.UNKNOWN.value},
        }
    return {
        "head": {"status": Status.PASS.value, "value": snapshot["head_sha"]},
        "diff_digest": {"status": Status.PASS.value, "value": snapshot["worktree_digest"]},
    }


def _git(cwd: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    except OSError:
        return None
    return completed.stdout if completed.returncode == 0 else None


def _log_path(output: Path, stream: str) -> Path:
    suffix = output.suffix
    stem = output.name[: -len(suffix)] if suffix else output.name
    return output.with_name(f"{stem}.{stream}.log")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
