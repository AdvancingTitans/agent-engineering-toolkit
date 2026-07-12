"""Isolated, evidence-producing runners for real learning rollouts.

The runner layer deliberately knows nothing about acceptance.  It produces a
single portable event format; deterministic scorers own PASS/FAIL decisions.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


class RunnerError(ValueError):
    """A runner could not safely start or normalize a rollout."""


@dataclass(frozen=True)
class RunnerCapabilities:
    supports_tool_events: bool
    supports_structured_output: bool
    supports_session_resume: bool
    supports_non_interactive: bool
    supports_network_isolation: bool


@dataclass(frozen=True)
class AgentRunRequest:
    run_id: str
    task_id: str
    prompt: str
    workspace: Path
    skill_path: Path
    output_dir: Path
    timeout_seconds: float
    environment_allowlist: tuple[str, ...] = ("PATH",)
    command_allowlist: tuple[str, ...] = ()
    network_policy: str = "deny"
    seed: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentRunResult:
    runner_name: str
    runner_version: str
    exit_code: int | None
    timed_out: bool
    started_at: str
    finished_at: str
    stdout_path: str | None
    stderr_path: str | None
    final_response_path: str | None
    tool_events_path: str | None
    command_events_path: str | None
    before_snapshot_path: str
    after_snapshot_path: str
    raw_artifact_manifest_path: str
    status: str


class AgentRunner(Protocol):
    name: str

    def capabilities(self) -> RunnerCapabilities: ...

    def validate(self) -> None: ...

    def run(self, request: AgentRunRequest) -> AgentRunResult: ...


def runner_names() -> tuple[str, ...]:
    return ("static", "scripted", "codex", "claude-code")


def create_runner(name: str, config: dict[str, Any] | None = None) -> AgentRunner:
    config = config or {}
    runners: dict[str, AgentRunner] = {
        "static": StaticSkillRunner(),
        "scripted": ScriptedAgentRunner(),
        "codex": CodexExecRunner(config),
        "claude-code": ClaudeCodeRunner(config),
    }
    try:
        return runners[name]
    except KeyError as error:
        raise RunnerError(f"unknown learn runner: {name}") from error


class StaticSkillRunner:
    """Marker for the legacy static contract runner; it never observes an agent."""

    name = "static"

    def capabilities(self) -> RunnerCapabilities:
        return RunnerCapabilities(False, True, False, True, True)

    def validate(self) -> None:
        return None

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        raise RunnerError("static runner has no observed Agent behavior; use the static contract gate")


class ScriptedAgentRunner:
    """Execute a declared script to test isolation, events, and scorers in CI."""

    name = "scripted"

    def capabilities(self) -> RunnerCapabilities:
        return RunnerCapabilities(True, True, False, True, True)

    def validate(self) -> None:
        return None

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        script = (request.metadata or {}).get("script", {})
        events = script.get("events", script) if isinstance(script, dict) else script
        if not isinstance(events, list):
            raise RunnerError("scripted task requires script.events array")
        return _run_scripted(request, events)


class _ProcessRunner:
    """Common, no-shell host adapter with bounded private raw outputs."""

    name = "process"
    command: tuple[str, ...]

    def __init__(self, config: dict[str, Any]) -> None:
        configured = config.get("command")
        self.command = tuple(configured) if isinstance(configured, list) and all(isinstance(item, str) for item in configured) else self.default_command()
        self.max_output_bytes = int(config.get("max_output_bytes", 1_000_000))
        self.inherit_home = bool(config.get("inherit_home", False))

    def default_command(self) -> tuple[str, ...]:
        raise NotImplementedError

    def capabilities(self) -> RunnerCapabilities:
        return RunnerCapabilities(True, True, False, True, False)

    def validate(self) -> None:
        if not self.command or shutil.which(self.command[0]) is None:
            raise RunnerError(f"{self.name} executable is unavailable: {self.command[0] if self.command else 'UNKNOWN'}")
        _execute([*self.command, "--version"], cwd=Path.cwd(), output_dir=Path(tempfile.mkdtemp(prefix="aet-runner-version-")), timeout_seconds=15, environment_allowlist=("PATH", "HOME"), max_output_bytes=8192)

    def _prompt(self, request: AgentRunRequest) -> str:
        skill = request.skill_path.read_text(encoding="utf-8")
        return (
            "You are running an isolated AET learning evaluation. Work only in the supplied workspace. "
            "Do not access the network, user history, or files outside that workspace. Follow this injected Skill exactly:\n\n"
            f"--- injected SKILL.md ({request.skill_path.name}) ---\n{skill}\n--- end SKILL.md ---\n\n"
            f"User task:\n{request.prompt}\n\n"
            "When AET is needed, use the runner-provided executable `./.aet-rollout/bin/aet` if it exists.\n"
            "Give a concise final answer with actual evidence paths."
        )

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        _atomic_json(request.output_dir / "request.json", _request_data(request))
        before = _snapshot(request.workspace)
        _atomic_json(request.output_dir / "before-snapshot.json", before)
        argv, stdin = self._argv_and_input(request, self._prompt(request))
        process = _execute(argv, cwd=request.workspace, output_dir=request.output_dir, timeout_seconds=request.timeout_seconds, environment_allowlist=request.environment_allowlist + (("HOME",) if self.inherit_home and "HOME" not in request.environment_allowlist else ()), max_output_bytes=self.max_output_bytes, stdin=stdin)
        events, final = self._normalize_output(process["stdout_text"], request)
        final_path = request.output_dir / "final-response.txt"
        if final_path.exists():
            final = final_path.read_text(encoding="utf-8")
        _write_events(request.output_dir / "events.jsonl", events)
        if final:
            _atomic_text(final_path, final)
        after = _snapshot(request.workspace)
        _atomic_json(request.output_dir / "after-snapshot.json", after)
        manifest = _raw_manifest(request, argv, process, before, after)
        _atomic_json(request.output_dir / "raw-artifact-manifest.json", manifest)
        return AgentRunResult(self.name, process["version"], process["exit_code"], process["timed_out"], process["started_at"], process["finished_at"], str(request.output_dir / "stdout.txt"), str(request.output_dir / "stderr.txt"), str(final_path) if final else None, str(request.output_dir / "events.jsonl"), str(request.output_dir / "events.jsonl"), str(request.output_dir / "before-snapshot.json"), str(request.output_dir / "after-snapshot.json"), str(request.output_dir / "raw-artifact-manifest.json"), "TIMEOUT" if process["timed_out"] else "COMPLETE")

    def _argv_and_input(self, request: AgentRunRequest, prompt: str) -> tuple[list[str], str | None]:
        raise NotImplementedError

    def _normalize_output(self, stdout: str, request: AgentRunRequest) -> tuple[list[dict[str, Any]], str]:
        return _jsonl_events(stdout, request.run_id), stdout.strip()


class CodexExecRunner(_ProcessRunner):
    name = "codex"

    def default_command(self) -> tuple[str, ...]:
        return ("codex", "exec", "--json", "--ephemeral", "--sandbox", "workspace-write", "--skip-git-repo-check")

    def _argv_and_input(self, request: AgentRunRequest, prompt: str) -> tuple[list[str], str | None]:
        # Codex supports '-' for stdin and JSONL event output. No host state is read by AET.
        return [*self.command, "-C", str(request.workspace), "--output-last-message", str(request.output_dir / "final-response.txt"), "-"], prompt

    def _normalize_output(self, stdout: str, request: AgentRunRequest) -> tuple[list[dict[str, Any]], str]:
        events: list[dict[str, Any]] = []
        final = ""
        for sequence, line in enumerate(stdout.splitlines(), start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            if item.get("type") == "command_execution" and isinstance(item.get("command"), str):
                try:
                    argv = shlex.split(item["command"])
                except ValueError:
                    argv = []
                events.append(_event(request.run_id, sequence, "command", {"argv": argv, "cwd": ".", "exit_code": item.get("exit_code"), "stdout_sha256": _sha(str(item.get("aggregated_output", "")).encode()), "host_event_type": event.get("type")}))
            elif item.get("type") == "agent_message":
                final = str(item.get("text", final))
                events.append(_event(request.run_id, sequence, "final_response", {"sha256": _sha(final.encode()), "host_event_type": event.get("type")}))
            elif event.get("type") in {"error", "turn.failed"}:
                events.append(_event(request.run_id, sequence, "runner_error", {"host_event_type": event.get("type"), "message": str(event.get("message") or event.get("error") or "host error")}))
            else:
                events.append(_event(request.run_id, sequence, "tool_call", {"host_event_type": event.get("type"), "item_type": item.get("type")}))
        return events, final


class ClaudeCodeRunner(_ProcessRunner):
    name = "claude-code"

    def default_command(self) -> tuple[str, ...]:
        return ("claude", "--print", "--output-format", "stream-json", "--verbose", "--no-session-persistence", "--bare")

    def _argv_and_input(self, request: AgentRunRequest, prompt: str) -> tuple[list[str], str | None]:
        return [*self.command, prompt], None

    def _normalize_output(self, stdout: str, request: AgentRunRequest) -> tuple[list[dict[str, Any]], str]:
        events: list[dict[str, Any]] = []
        final = ""
        for sequence, line in enumerate(stdout.splitlines(), start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            content = event.get("message", {}).get("content", []) if isinstance(event.get("message"), dict) else []
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and isinstance(block.get("input"), dict) and isinstance(block["input"].get("command"), str):
                    try:
                        argv = shlex.split(block["input"]["command"])
                    except ValueError:
                        argv = []
                    events.append(_event(request.run_id, sequence, "command", {"argv": argv, "cwd": ".", "exit_code": None, "host_event_type": event.get("type")}))
                elif block.get("type") == "text":
                    final += str(block.get("text", ""))
            if event.get("type") == "result" and isinstance(event.get("result"), str):
                final = event["result"]
                events.append(_event(request.run_id, sequence, "final_response", {"sha256": _sha(final.encode()), "host_event_type": "result"}))
                if event.get("is_error") is True:
                    events.append(_event(request.run_id, sequence + 10_000, "runner_error", {"host_event_type": "result", "message": final}))
        return events, final


def _run_scripted(request: AgentRunRequest, script: list[Any]) -> AgentRunResult:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(request.output_dir / "request.json", _request_data(request))
    before = _snapshot(request.workspace)
    _atomic_json(request.output_dir / "before-snapshot.json", before)
    started = _now()
    events: list[dict[str, Any]] = [_event(request.run_id, 1, "session_start", {"runner": "scripted"})]
    final = ""
    timed_out = False
    exit_code = 0
    for position, item in enumerate(script, start=2):
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise RunnerError("script event must be an object with type")
        kind = item["type"]
        if kind == "command":
            argv = item.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(value, str) for value in argv):
                raise RunnerError("script command requires a non-empty argv array")
            _assert_command_allowed(argv, request.command_allowlist)
            outcome = _execute(argv, cwd=request.workspace, output_dir=request.output_dir / "commands" / f"{position:03d}", timeout_seconds=request.timeout_seconds, environment_allowlist=request.environment_allowlist, max_output_bytes=1_000_000)
            events.append(_event(request.run_id, position, "command", {"argv": argv, "cwd": ".", "exit_code": outcome["exit_code"], "timed_out": outcome["timed_out"], "stdout_sha256": _sha(outcome["stdout_text"].encode()), "stderr_sha256": _sha(outcome["stderr_text"].encode())}))
            if outcome["timed_out"]:
                timed_out, exit_code = True, None
                break
            if outcome["exit_code"] not in (0, None):
                exit_code = outcome["exit_code"]
        elif kind == "final_response":
            final = str(item.get("text", ""))
            events.append(_event(request.run_id, position, "final_response", {"sha256": _sha(final.encode())}))
        elif kind in {"file_read", "file_write", "tool_call", "artifact_created"}:
            payload = item.get("payload", {})
            events.append(_event(request.run_id, position, kind, payload if isinstance(payload, dict) else {}))
        else:
            raise RunnerError(f"unsupported scripted event type: {kind}")
    events.append(_event(request.run_id, len(events) + 1, "session_end", {"exit_code": exit_code, "timed_out": timed_out}))
    _write_events(request.output_dir / "events.jsonl", events)
    _atomic_text(request.output_dir / "final-response.txt", final)
    _atomic_text(request.output_dir / "stdout.txt", "")
    _atomic_text(request.output_dir / "stderr.txt", "")
    after = _snapshot(request.workspace)
    _atomic_json(request.output_dir / "after-snapshot.json", after)
    manifest = {"report_kind": "learning_raw_rollout", "runner": "scripted", "private_raw_output": True, "before_snapshot": before["sha256"], "after_snapshot": after["sha256"], "event_count": len(events)}
    _atomic_json(request.output_dir / "raw-artifact-manifest.json", manifest)
    return AgentRunResult("scripted", "builtin", exit_code, timed_out, started, _now(), str(request.output_dir / "stdout.txt"), str(request.output_dir / "stderr.txt"), str(request.output_dir / "final-response.txt"), str(request.output_dir / "events.jsonl"), str(request.output_dir / "events.jsonl"), str(request.output_dir / "before-snapshot.json"), str(request.output_dir / "after-snapshot.json"), str(request.output_dir / "raw-artifact-manifest.json"), "TIMEOUT" if timed_out else "COMPLETE")


def _execute(argv: list[str], *, cwd: Path, output_dir: Path, timeout_seconds: float, environment_allowlist: tuple[str, ...], max_output_bytes: int, stdin: str | None = None) -> dict[str, Any]:
    if not argv or timeout_seconds <= 0:
        raise RunnerError("runner requires a non-empty argv and positive timeout")
    output_dir.mkdir(parents=True, exist_ok=True)
    environment = {key: os.environ[key] for key in environment_allowlist if key in os.environ}
    started = _now()
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE if stdin is not None else None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment, start_new_session=True)
    try:
        stdout, stderr = process.communicate(stdin, timeout=timeout_seconds)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
    stdout, stderr = stdout[:max_output_bytes], stderr[:max_output_bytes]
    _atomic_text(output_dir / "stdout.txt", stdout)
    _atomic_text(output_dir / "stderr.txt", stderr)
    return {"exit_code": None if timed_out else process.returncode, "timed_out": timed_out, "started_at": started, "finished_at": _now(), "stdout_text": stdout, "stderr_text": stderr, "version": "unknown", "truncated": len(stdout) >= max_output_bytes or len(stderr) >= max_output_bytes}


def _jsonl_events(stdout: str, run_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for sequence, line in enumerate(stdout.splitlines(), start=1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(_event(run_id, sequence, "tool_call" if payload.get("type") not in {"item.completed", "task_complete"} else "session_end", {"host_event": payload}))
    return events


def _snapshot(workspace: Path) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for source in sorted(path for path in workspace.rglob("*") if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}):
        relative = source.relative_to(workspace).as_posix()
        rows.append({"path": relative, "sha256": _sha(source.read_bytes())})
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    # Keep AET's native snapshot alongside the portable file manifest.  The
    # former lets Trace prove freshness without pretending the two digest
    # algorithms are interchangeable.
    try:
        from .evidence import workspace_snapshot
        aet_snapshot: dict[str, Any] | None = workspace_snapshot(workspace)
    except (OSError, ValueError):
        aet_snapshot = None
    return {"workspace": str(workspace), "file_count": len(rows), "files": rows, "sha256": _sha(encoded), "aet_workspace_snapshot": aet_snapshot}


def _assert_command_allowed(argv: list[str], allowlist: tuple[str, ...]) -> None:
    if not allowlist:
        return
    rendered = " ".join(argv)
    if not any(rendered == allowed or rendered.startswith(allowed + " ") for allowed in allowlist):
        raise RunnerError(f"script command is outside task allowlist: {argv[0]}")


def _event(run_id: str, sequence: int, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"event_id": f"{run_id}-EVT-{sequence:04d}", "sequence": sequence, "time": _now(), "type": kind, "source": "runner", "payload": payload}


def _write_events(path: Path, events: list[dict[str, Any]]) -> None:
    _atomic_text(path, "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events))


def _request_data(request: AgentRunRequest) -> dict[str, Any]:
    data = asdict(request)
    for key in ("workspace", "skill_path", "output_dir"):
        data[key] = str(data[key])
    return data


def _raw_manifest(request: AgentRunRequest, argv: list[str], process: dict[str, Any], before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {"report_kind": "learning_raw_rollout", "runner": request.run_id.split("-")[0], "argv_sha256": _sha(json.dumps(argv).encode()), "private_raw_output": True, "before_snapshot": before["sha256"], "after_snapshot": after["sha256"], "exit_code": process["exit_code"], "timed_out": process["timed_out"], "output_truncated": process["truncated"]}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
