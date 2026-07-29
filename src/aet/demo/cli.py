"""Argument parser and exit mapping for ``aet demo``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import DemoError, DemoInvariantError
from .models import DemoOptions
from .registry import list_demos
from .renderer import render
from .runner import run_demo


def add_demo_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "demo",
        help="Run an installed, deterministic AET demonstration.",
    )
    parser.add_argument("demo_id", help="Demo id or 'list'")
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--timeout-seconds", type=int)


def handle_demo(args: argparse.Namespace) -> int:
    if args.demo_id == "list":
        if args.output or args.keep or args.timeout_seconds:
            print("aet demo list does not accept run options", file=sys.stderr)
            return 64
        payload = "\n".join(
            f"{manifest.demo_id}\t{manifest.title}" for manifest in list_demos()
        ) + "\n"
        print(payload, end="")
        return 0
    options = DemoOptions(
        format=args.format,
        output=args.output,
        keep=args.keep,
        timeout_seconds=args.timeout_seconds,
    )
    try:
        result = run_demo(args.demo_id, options)
        payload = render(result, args.format)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            print(payload, end="")
        if result.overall_status in {"PASS", "PASS_WITH_WARNING"}:
            return 0
        if any("timed out" in item for item in result.diagnostics):
            return 124
        return 1
    except DemoInvariantError as error:
        if str(error).startswith("unknown demo"):
            print(f"aet demo: {error}", file=sys.stderr)
            return 64
        print(f"aet demo: {error}", file=sys.stderr)
        return error.exit_code
    except DemoError as error:
        print(f"aet demo: {error}", file=sys.stderr)
        return error.exit_code
    except OSError as error:
        print(f"aet demo: cannot write output: {error}", file=sys.stderr)
        return 74
