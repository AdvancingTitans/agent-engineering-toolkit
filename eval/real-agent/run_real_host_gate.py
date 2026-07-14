#!/usr/bin/env python3
"""Run the complete commit-bound real-host release gate from a clean checkout."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from aet import __version__


HERE = Path(__file__).resolve().parent


def load_local(name: str) -> ModuleType:
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"aet_real_agent_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load tracked helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def orchestrate(
    root: Path,
    release_dir: Path,
    expected_commit: str | None = None,
    expected_version: str | None = None,
) -> None:
    root = root.resolve()
    release_dir = release_dir.resolve()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    version = __version__
    if expected_commit is not None and expected_commit != commit:
        raise ValueError(f"checkout commit {commit} does not match expected commit {expected_commit}")
    if expected_version is not None and expected_version != version:
        raise ValueError(f"source version {version} does not match expected version {expected_version}")
    if any((release_dir / name).exists() for name in ("candidate", "runner.json", "gate-plan.json", "raw-gate.json", "real-host-gate.json")):
        raise ValueError(f"release output already exists: {release_dir}")
    release_dir.mkdir(parents=True, exist_ok=True)
    candidate = release_dir / "candidate"
    raw_gate = release_dir / "raw-gate.json"
    manifest = release_dir / "real-host-gate.json"
    runner_config = release_dir / "runner.json"
    gate_plan = release_dir / "gate-plan.json"

    load_local("build_candidate").build(root, candidate)
    runner_config.write_text(json.dumps({
        "aet_argv": [sys.executable, "-m", "aet.cli"],
        "inherit_home": True,
        "model_fingerprint": "codex-default@0.144.1",
    }, indent=2) + "\n", encoding="utf-8")
    plan_command = [
        sys.executable, "-m", "aet.cli", "learn", "plan",
        "--candidate", str(candidate), "--core", str(root / "eval/real-agent/core"),
        "--validation", str(root / "eval/real-agent/validation"),
        "--held-out", str(root / "eval/real-agent/held-out"),
        "--runner", "codex", "--runner-config", str(runner_config),
        "--risk-class", "R3", "--claim", "AET.REAL-HOST.TRACE-ROUTING",
        "--output", str(gate_plan),
    ]
    subprocess.run(plan_command, cwd=root, check=True)
    command = [
        sys.executable, "-m", "aet.cli", "learn", "gate",
        "--candidate", str(candidate),
        "--core", str(root / "eval/real-agent/core"),
        "--validation", str(root / "eval/real-agent/validation"),
        "--held-out", str(root / "eval/real-agent/held-out"),
        "--output", str(raw_gate),
        "--runner", "codex", "--gate-plan", str(gate_plan),
        "--runner-config", str(runner_config), "--statistics-profile", "adoptable",
        "--target-type", "skill",
    ]
    subprocess.run(command, cwd=root, check=True)
    observed = json.loads(raw_gate.read_text(encoding="utf-8"))
    release_gate = load_local("release_gate")
    expected_runner = {
        "runner_name": release_gate.RELEASE_RUNNER_NAME,
        "runner_version": release_gate.RELEASE_RUNNER_VERSION,
    }
    if not isinstance(observed, dict) or observed.get("status") != "PASS":
        raise ValueError("real-host gate did not produce PASS")
    if any(observed.get(key) != value for key, value in expected_runner.items()):
        raise ValueError(f"real-host gate runner provenance must equal {expected_runner!r}")

    arguments = argparse.Namespace(
        root=root, candidate=candidate, raw_gate=raw_gate, gate_plan=gate_plan, commit=commit, version=version
    )
    document = release_gate.expected(arguments)
    manifest.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-version")
    args = parser.parse_args()
    try:
        orchestrate(args.root, args.release_dir, args.expected_commit, args.expected_version)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise SystemExit(f"real-host orchestration failed: {exc}") from exc


if __name__ == "__main__":
    main()
