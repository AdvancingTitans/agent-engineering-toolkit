#!/usr/bin/env python3
"""Create or verify a commit-bound, content-addressed real-host release gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SUITES = ("core", "validation", "held-out")
RELEASE_RUNNER_NAME = "codex"
RELEASE_RUNNER_VERSION = "codex-cli 0.144.1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def relative_hashes(base: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(base.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlinks are not release evidence: {path}")
        if path.is_file():
            result[path.relative_to(base).as_posix()] = sha256(path)
    return result


def suite_hashes(root: Path, name: str) -> dict[str, dict[str, str]]:
    root = root.resolve()
    suite = root / "eval" / "real-agent" / name
    tasks: dict[str, str] = {}
    fixtures: dict[str, str] = {}
    for task_path in sorted(suite.glob("*.json")):
        if task_path.is_symlink() or not task_path.is_file():
            raise ValueError(f"suite task must be a regular non-symlink file: {task_path}")
        tasks[task_path.relative_to(root).as_posix()] = sha256(task_path)
        task = read_json(task_path)
        fixture_source = task.get("fixture", {}).get("source")
        if not isinstance(fixture_source, str):
            raise ValueError(f"{task_path} has no fixture source")
        fixture = (suite / fixture_source).resolve()
        fixture_root = (root / "eval" / "real-agent" / "fixtures").resolve()
        if fixture_root not in fixture.parents:
            raise ValueError(f"fixture escapes tracked fixture root: {fixture}")
        declared_fixture = suite / fixture_source
        if declared_fixture.is_symlink() or not fixture.is_dir():
            raise ValueError(f"task fixture must be an existing non-symlink directory: {declared_fixture}")
        fixture_files = relative_hashes(fixture)
        if not fixture_files:
            raise ValueError(f"task fixture must contain at least one regular file: {fixture}")
        for relative, digest in fixture_files.items():
            key = f"{fixture.relative_to(root).as_posix()}/{relative}"
            fixtures[key] = digest
    if not tasks or not fixtures:
        raise ValueError(f"suite {name} must bind tasks and fixtures")
    return {"tasks": tasks, "fixtures": dict(sorted(fixtures.items()))}


def expected(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    candidate_file = args.candidate / "candidate.SKILL.md"
    metadata = read_json(args.candidate / "candidate.json")
    candidate_sha = sha256(candidate_file)
    if metadata.get("candidate_sha256") != candidate_sha:
        raise ValueError("candidate content does not match candidate.json")
    raw = read_json(args.raw_gate)
    required = {
        "report_kind": "learning_observed_gate",
        "status": "PASS",
        "runner": "codex",
        "runner_name": RELEASE_RUNNER_NAME,
        "runner_version": RELEASE_RUNNER_VERSION,
        "statistics_profile": "adoptable",
        "candidate_sha256": candidate_sha,
    }
    for key, value in required.items():
        if raw.get(key) != value:
            raise ValueError(f"raw gate {key} must equal {value!r}")
    if raw.get("hard_gate_failures") != [] or raw.get("candidate_audit_failures") != []:
        raise ValueError("raw gate must contain empty hard and candidate-audit failure lists")
    comparisons = raw.get("comparisons")
    if not isinstance(comparisons, dict) or set(comparisons) != {"core", "validation", "held_out"}:
        raise ValueError("raw gate comparisons must be exactly core, validation, and held_out")
    for name, comparison in comparisons.items():
        if not isinstance(comparison, dict) or set(comparison) != {"replay", "statistics"}:
            raise ValueError(f"raw gate comparison {name} has an invalid contract")
        if not isinstance(comparison.get("replay"), str) or not comparison["replay"]:
            raise ValueError(f"raw gate comparison {name} requires a replay reference")
        statistics = comparison.get("statistics")
        if not isinstance(statistics, dict):
            raise ValueError(f"raw gate comparison {name} requires statistics")
        statistics_required = {
            "report_kind": "learning_paired_statistics",
            "profile": "adoptable",
            "status": "PASS",
            "pair_count": 6,
            "usable_pair_count": 6,
            "infrastructure_pair_count": 0,
        }
        for key, value in statistics_required.items():
            if statistics.get(key) != value:
                raise ValueError(f"raw gate comparison {name} statistics {key} must equal {value!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise ValueError("commit must be a lowercase 40-character Git SHA")
    raw_gate_path = args.raw_gate.resolve()
    try:
        raw_gate_label = raw_gate_path.relative_to(root).as_posix()
    except ValueError:
        raw_gate_label = str(raw_gate_path)
    return {
        "schema_version": "real-host-release-gate/v1",
        "report_kind": "real_host_release_gate",
        "release_commit": args.commit,
        "version": args.version,
        "candidate_sha256": candidate_sha,
        "runner": {"name": raw["runner_name"], "version": raw["runner_version"]},
        "raw_gate": {
            "path": raw_gate_label,
            "sha256": sha256(args.raw_gate),
            "status": raw["status"],
            "runner": raw["runner"],
            "runner_name": raw["runner_name"],
            "runner_version": raw["runner_version"],
            "statistics_profile": raw["statistics_profile"],
            "comparisons": {
                name: {
                    "replay": comparisons[name]["replay"],
                    "statistics": {
                        key: comparisons[name]["statistics"][key]
                        for key in ("profile", "status", "pair_count", "usable_pair_count", "infrastructure_pair_count")
                    },
                }
                for name in ("core", "validation", "held_out")
            },
        },
        "suites": {name: suite_hashes(root, name) for name in SUITES},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("create", "verify"):
        sub = subparsers.add_parser(action)
        sub.add_argument("--root", type=Path, required=True)
        sub.add_argument("--candidate", type=Path, required=True)
        sub.add_argument("--raw-gate", type=Path, required=True)
        sub.add_argument("--commit", required=True)
        sub.add_argument("--version", required=True)
        if action == "create":
            sub.add_argument("--output", type=Path, required=True)
        else:
            sub.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        document = expected(args)
        if args.action == "create":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        elif read_json(args.manifest) != document:
            raise ValueError("release gate manifest does not match reconstructed evidence")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"release gate verification failed: {exc}") from exc


if __name__ == "__main__":
    main()
