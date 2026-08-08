#!/usr/bin/env python3
"""Verify the focused README conversion contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


HERO_COMMAND = (
    "uvx --from https://github.com/AdvancingTitans/agent-engineering-toolkit/"
    "releases/download/v1.19.0/agent_engineering_toolkit-1.19.0-py3-none-any.whl "
    "aet demo stale-proof"
)


def verify(path: Path, max_lines: int) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    failures: list[str] = []
    if len(lines) > max_lines:
        failures.append(f"{path}: {len(lines)} physical lines exceeds {max_lines}")
    if HERO_COMMAND not in "\n".join(lines[:60]):
        failures.append(f"{path}: hero command is missing from the first 60 lines")
    lower = text.lower()
    if "unknown" not in lower:
        failures.append(f"{path}: explicit UNKNOWN boundary is missing")
    if "does not replace tests or ci" not in lower:
        failures.append(f"{path}: tests/CI boundary is missing")
    for forbidden in ("pip install -e .", "uv tool install ."):
        if forbidden in text:
            failures.append(f"{path}: forbidden source-only install command: {forbidden}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=Path("README.md"))
    parser.add_argument("--max-lines", type=int, default=250)
    args = parser.parse_args(argv)
    try:
        failures = verify(args.path, args.max_lines)
    except OSError as error:
        failures = [f"{args.path}: {error}"]
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        f"README budget PASS: {len(args.path.read_text(encoding='utf-8').splitlines())}/{args.max_lines} lines"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
