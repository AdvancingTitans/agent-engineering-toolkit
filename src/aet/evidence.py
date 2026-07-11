"""Opt-in command traces and portable Evidence Pack compilation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

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


def trace_command(argv: list[str], output: Path, redaction_patterns: Iterable[str] = ()) -> tuple[dict[str, Any], int]:
    """Run one explicit argv command and persist only redacted command evidence."""
    if not argv:
        raise EvidenceError("trace requires an explicit command after --")
    patterns = _compile_patterns(redaction_patterns)
    output = output.resolve()
    cwd = Path.cwd().resolve()
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

    execution_status = Status.PASS.value if exit_code == 0 else Status.FAIL.value
    unknowns = sum(item["status"] == Status.UNKNOWN.value for item in (stdout, stderr))
    if argv_status == Status.UNKNOWN.value:
        unknowns += 1
    data = {
        "schema_version": __version__,
        "report_kind": "trace",
        "generated_at": finished_at,
        "root": str(cwd),
        "assets": [],
        "findings": [],
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
        },
    }
    _atomic_write_json(output, data)
    return data, exit_code


def compile_evidence_pack(*, audit: Path | None, review: Path | None, trace: Path | None, output: Path) -> dict[str, Any]:
    """Compile validated reports into a content-addressed, host-neutral pack."""
    components = {
        "audit": _component("audit", audit),
        "review": _component("review", review),
        "trace": _component("trace", trace),
    }
    data = {
        "schema_version": __version__,
        "report_kind": "evidence_pack",
        "generated_at": _timestamp(),
        "components": components,
    }
    _atomic_write_json(output.resolve(), data)
    return data


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
    if kind == "review":
        portable["review"] = report["review"]
    if kind == "trace":
        # The trace references only redacted excerpts and artifact digests; raw logs never enter the pack.
        portable["execution"] = report["trace"]["execution"]
        portable["git"] = report["trace"].get("git")
        portable["stdout"] = _portable_artifact(report["trace"].get("stdout"))
        portable["stderr"] = _portable_artifact(report["trace"].get("stderr"))
    return portable


def _portable_artifact(artifact: Any) -> dict[str, Any] | None:
    if not isinstance(artifact, dict):
        return None
    return {key: artifact.get(key) for key in ("status", "sha256", "excerpt")}


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
    head = _git(cwd, "rev-parse", "HEAD")
    if head is None:
        return {
            "head": {"status": Status.UNKNOWN.value},
            "diff_digest": {"status": Status.UNKNOWN.value},
        }
    diff = _git(cwd, "diff", "--binary", "HEAD", "--")
    untracked = _git(cwd, "ls-files", "--others", "--exclude-standard")
    if diff is None or untracked is None:
        digest = {"status": Status.UNKNOWN.value}
    else:
        hasher = hashlib.sha256()
        hasher.update(b"tracked\0")
        hasher.update(diff.encode("utf-8"))
        for relative in sorted(line for line in untracked.splitlines() if line):
            hasher.update(b"untracked\0" + relative.encode("utf-8") + b"\0")
            candidate = cwd / relative
            if candidate.is_file():
                hasher.update(hashlib.sha256(candidate.read_bytes()).digest())
        digest = {"status": Status.PASS.value, "value": hasher.hexdigest()}
    return {
        "head": {"status": Status.PASS.value, "value": head.strip()},
        "diff_digest": digest,
    }


def _git(cwd: Path, *args: str) -> str | None:
    completed = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
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
