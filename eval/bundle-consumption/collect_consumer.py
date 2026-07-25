#!/usr/bin/env python3
"""Run one explicitly declared prompt-only consumer and score its JSON response."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from prepare_prompt import build_prompt
from score_collection import score_collection


def _strict_object(text: str) -> dict[str, Any]:
    value = json.loads(
        text.strip(),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"invalid JSON constant: {value}")
        ),
        object_pairs_hook=_unique_object,
    )
    if not isinstance(value, dict):
        raise ValueError("consumer output must be one JSON object")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--consumer-id", required=True)
    parser.add_argument("--runtime-version", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument(
        "--prompt-mode",
        choices=("stdin", "argument"),
        default="stdin",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise SystemExit("consumer collection failed: an explicit command is required")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise SystemExit("consumer collection failed: output directory already exists")
    prompt = build_prompt(args.catalog, args.bundle_root)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [*command, prompt] if args.prompt_mode == "argument" else command,
            input=None if args.prompt_mode == "argument" else prompt,
            text=True,
            capture_output=True,
            timeout=args.timeout_seconds,
            check=False,
        )
        elapsed = time.monotonic() - started
        if completed.returncode != 0:
            raise ValueError(
                f"consumer exited {completed.returncode}: {completed.stderr[-1000:]}"
            )
        response = _strict_object(completed.stdout)
        report = score_collection(
            args.catalog,
            args.bundle_root,
            response,
            consumer_id=args.consumer_id,
            consumer_available=True,
            elapsed_seconds=elapsed,
        )
        args.output_dir.mkdir(parents=True)
        _atomic_json(args.output_dir / "response.json", response)
        _atomic_json(args.output_dir / "report.json", report)
        _atomic_json(
            args.output_dir / "metadata.json",
            {
                "schema_version": "bundle-consumption-collection-metadata/v1",
                "consumer_id": args.consumer_id,
                "command_name": Path(command[0]).name,
                "command_argv_sha256": hashlib.sha256(
                    json.dumps(
                        command,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
                "runtime_version": args.runtime_version,
                "model_id": args.model_id,
                "external_agent_calls": 1,
                "elapsed_seconds_to_complete_response": elapsed,
                "stdout_bytes": len(completed.stdout.encode("utf-8")),
                "stderr_bytes": len(completed.stderr.encode("utf-8")),
                "raw_transcript_persisted": False,
                "aggregate_score": None,
            },
        )
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.TimeoutExpired,
    ) as error:
        raise SystemExit(f"consumer collection failed: {error}") from error


if __name__ == "__main__":
    main()
