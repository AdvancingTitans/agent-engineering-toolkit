#!/usr/bin/env python3
"""Record reproducible local runtime samples for AET Quick acceptance budgets."""

from __future__ import annotations

import argparse
import json
import math
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from aet.quick import quick_check, quick_fresh, quick_proof, quick_scope
from aet.quick.common import atomic_write_json


def _measure(callable_, repetitions: int) -> list[float]:
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter()
        callable_()
        samples.append(time.perf_counter() - started)
    return samples


def _p95(samples: list[float]) -> float:
    """Nearest-rank P95; Plan §16 performance acceptance evidence."""
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def run(root: Path, base: str, intent: Path, repetitions: int) -> dict[str, object]:
    root = root.resolve()
    check = _measure(lambda: quick_check(root), repetitions)
    scope = _measure(
        lambda: quick_scope(root, base=base, intent_path=intent),
        repetitions,
    )
    with tempfile.TemporaryDirectory(prefix="aet-quick-performance-") as directory:
        fixture = Path(directory)
        _git(fixture, "init", "-q")
        _git(fixture, "config", "user.email", "aet@example.invalid")
        _git(fixture, "config", "user.name", "AET Performance")
        relevant = fixture / "relevant.txt"
        relevant.write_text("stable\n", encoding="utf-8")
        _git(fixture, "add", "relevant.txt")
        _git(fixture, "commit", "-qm", "fixture")
        previous = Path.cwd()
        try:
            import os

            os.chdir(fixture)
            proof = fixture / "proof.json"
            quick_proof(
                [sys.executable, "-c", "pass"],
                proof,
                relevant_paths=["relevant.txt"],
            )
            fresh = _measure(lambda: quick_fresh(proof), repetitions)
        finally:
            os.chdir(previous)
    tracked_files = len(_git(root, "ls-files").splitlines())
    changed_files = len(_git(root, "diff", "--name-only", base).splitlines())
    return {
        "schema_version": "aet-quick-performance/v1",
        "method": {
            "clock": "time.perf_counter",
            "p95": "nearest_rank",
            "repetitions_per_command": repetitions,
            "root": str(root),
            "base": base,
            "tracked_files": tracked_files,
            "changed_files_against_base": changed_files,
            "network_calls": 0,
            "llm_calls": 0,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "commands": {
            "check": {"budget_seconds": 30, "samples_seconds": check, "p95_seconds": _p95(check)},
            "scope": {"budget_seconds": 45, "samples_seconds": scope, "p95_seconds": _p95(scope)},
            "fresh": {"budget_seconds": 3, "samples_seconds": fresh, "p95_seconds": _p95(fresh)},
        },
        "limits": [
            "Local deterministic measurements only.",
            "Not a cross-repository or model-service latency claim.",
            "The current repository is the Check and Scope workload; Fresh uses a minimal temporary Git fixture.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="v1.12.0")
    parser.add_argument("--intent", type=Path, default=Path("aet.intent.json"))
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repetitions < 1:
        raise SystemExit("repetitions must be positive")
    atomic_write_json(
        args.output,
        run(args.root, args.base, args.intent, args.repetitions),
    )


if __name__ == "__main__":
    main()
