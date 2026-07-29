#!/usr/bin/env python3
"""Validate GitHub Social Preview dimensions, size, and PNG opacity."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def verify(path: Path) -> list[str]:
    failures: list[str] = []
    try:
        data = path.read_bytes()
    except OSError as error:
        return [f"{path}: {error}"]
    if len(data) >= 1_000_000:
        failures.append(f"{path}: must be smaller than 1 MB")
    if not data.startswith(PNG_SIGNATURE) or len(data) < 33:
        return [*failures, f"{path}: must be a readable PNG"]
    width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
    if (width, height) != (1280, 640):
        failures.append(f"{path}: expected 1280x640, got {width}x{height}")
    if color_type in {4, 6}:
        failures.append(f"{path}: alpha channel is not allowed for Social Preview")
    if bit_depth not in {8, 16}:
        failures.append(f"{path}: unsupported PNG bit depth {bit_depth}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    failures = verify(args.path)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Social Preview PASS: {args.path.stat().st_size} bytes, 1280x640")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
