"""Minimal proof receipt built from the stable Trace executor."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .. import __version__
from ..evidence import trace_command
from .common import atomic_write_json, sha256_file


def quick_proof(
    argv: list[str],
    output: Path,
    *,
    relevant_paths: Iterable[str] = (),
    artifact_paths: Iterable[str] = (),
    redaction_patterns: Iterable[str] = (),
    environment_names: Iterable[str] = (),
) -> tuple[dict[str, Any], int]:
    """Execute explicit argv and write one compact, hash-bound proof receipt."""
    if not argv:
        raise ValueError("quick proof requires an explicit command after --")
    root = Path.cwd().resolve()
    relevant = _capture_paths(root, relevant_paths)
    environment = _environment_binding(root, argv=argv, environment_names=environment_names)
    with tempfile.TemporaryDirectory(prefix="aet-quick-proof-") as directory:
        trace_path = Path(directory) / "trace.json"
        trace, exit_code = trace_command(
            argv,
            trace_path,
            redaction_patterns,
            artifact_paths=artifact_paths,
        )
    result = trace["trace"]
    binding_unknown = (
        any(item.get("status") != "PASS" for item in relevant)
        or environment.get("selected_executable") is None
        or any(
            item.get("status") != "PASS"
            for item in environment.get("explicit_environment", [])
        )
    )
    authoritative_status = result["execution"]["status"]
    if authoritative_status == "PASS" and binding_unknown:
        authoritative_status = "UNKNOWN"
    receipt = {
        "schema_version": "aet-proof-receipt/v2",
        "tool_version": __version__,
        "report_kind": "quick_proof",
        "proof_id": f"proof_{trace['run_id']}",
        "command": {
            "argv": result["argv"],
            "argv_sha256": result["argv_sha256"],
            "cwd": result["working_directory"],
            "started_at": result["started_at"],
            "ended_at": result["finished_at"],
            "exit_code": result["execution"]["exit_code"],
        },
        "authoritative_status": authoritative_status,
        "result": {
            "stdout_sha256": result["stdout"].get("sha256"),
            "stderr_sha256": result["stderr"].get("sha256"),
        },
        "binding": {
            "status": "UNKNOWN" if binding_unknown else "PASS",
            "workspace_snapshot": trace["workspace_snapshot"],
            "relevant_paths": relevant,
            "environment": environment,
        },
        "artifacts": [
            {
                key: item.get(key)
                for key in ("requested_path", "status", "sha256", "freshness")
            }
            for item in result.get("artifacts", [])
        ],
        "coverage": {
            "kind": "bounded",
            "statement": "This proof covers only the recorded command and declared paths; it does not imply that the full test suite passed.",
        },
        "provenance": {"executor": "aet", "requested_by": "user"},
    }
    atomic_write_json(output, receipt)
    return receipt, exit_code


def _capture_paths(root: Path, paths: Iterable[str]) -> list[dict[str, Any]]:
    records = []
    for value in paths:
        candidate = (root / value).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError(f"relevant path must remain inside the workspace: {value}") from error
        if not candidate.is_file() or candidate.is_symlink():
            records.append({"path": relative, "status": "UNKNOWN", "sha256": None})
        else:
            records.append({"path": relative, "status": "PASS", "sha256": sha256_file(candidate)})
    return records


def _environment_binding(
    root: Path,
    *,
    argv: Iterable[str] = (),
    environment_names: Iterable[str] = (),
) -> dict[str, Any]:
    lockfiles = []
    for name in ("uv.lock", "poetry.lock", "Pipfile.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            lockfiles.append({"path": name, "sha256": sha256_file(path)})
    command = list(argv)
    executable = None
    if command:
        resolved = shutil.which(command[0])
        if resolved:
            executable_path = Path(resolved).resolve()
            executable = {
                "name": executable_path.name,
                "path": str(executable_path),
                "sha256": sha256_file(executable_path)
                if executable_path.is_file() and not executable_path.is_symlink()
                else None,
            }
    explicit_environment = []
    for name in sorted(set(environment_names)):
        if not name or "=" in name:
            raise ValueError("environment binding names must be non-empty variable names")
        value = os.environ.get(name)
        explicit_environment.append({
            "name": name,
            "status": "PASS" if value is not None else "UNKNOWN",
            "sha256": hashlib.sha256(value.encode()).hexdigest() if value is not None else None,
        })
    values = {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "selected_executable": executable,
        "explicit_environment": explicit_environment,
        "lockfiles": lockfiles,
    }
    values["digest"] = hashlib.sha256(repr(values).encode()).hexdigest()
    return values
