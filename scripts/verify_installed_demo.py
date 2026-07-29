#!/usr/bin/env python3
"""Build-environment-neutral smoke test for an installed AET wheel."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path

import tomllib


def _venv_python(root: Path) -> Path:
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _venv_aet(root: Path) -> Path:
    return root / ("Scripts/aet.exe" if os.name == "nt" else "bin/aet")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args(argv)
    project = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    version = metadata["project"]["version"]
    wheels = sorted(
        (project / args.dist).glob(f"agent_engineering_toolkit-{version}-*.whl")
    )
    if len(wheels) != 1:
        raise SystemExit(
            f"expected one wheel for {version}, found {[path.name for path in wheels]}"
        )
    with tempfile.TemporaryDirectory(prefix="aet-installed-demo-") as directory:
        root = Path(directory)
        environment = root / "venv"
        outside = root / "outside-checkout"
        outside.mkdir()
        venv.EnvBuilder(with_pip=True).create(environment)
        python = _venv_python(environment)
        aet = _venv_aet(environment)
        subprocess.run(
            [str(python), "-m", "pip", "install", str(wheels[0])],
            check=True,
            cwd=outside,
        )
        listed = subprocess.run(
            [str(aet), "demo", "list"],
            check=True,
            cwd=outside,
            text=True,
            capture_output=True,
        )
        if "stale-proof" not in listed.stdout:
            raise SystemExit("installed wheel did not list stale-proof")
        text_result = subprocess.run(
            [str(aet), "demo", "stale-proof"],
            check=True,
            cwd=outside,
            text=True,
            capture_output=True,
        )
        if "Demo result: PASS" not in text_result.stdout:
            raise SystemExit("installed wheel text demo did not pass")
        json_result = subprocess.run(
            [str(aet), "demo", "stale-proof", "--format", "json"],
            check=True,
            cwd=outside,
            text=True,
            capture_output=True,
        )
        result = json.loads(json_result.stdout)
        if result.get("overall_status") not in {"PASS", "PASS_WITH_WARNING"}:
            raise SystemExit(
                "installed demo field overall_status was "
                f"{result.get('overall_status')!r}"
            )
        expected = {
            "schema_version": "aet-demo-result/v1",
            "demo_id": "stale-proof",
            "execution_status": "PASS",
            "before_state": "EXACT_MATCH",
            "after_state": "RELEVANT_FILES_CHANGED",
            "network_calls": 0,
            "llm_calls": 0,
        }
        for key, value in expected.items():
            if result.get(key) != value:
                raise SystemExit(f"installed demo field {key} was {result.get(key)!r}")
        markdown = outside / "result.md"
        subprocess.run(
            [
                str(aet),
                "demo",
                "stale-proof",
                "--format",
                "markdown",
                "--output",
                str(markdown),
            ],
            check=True,
            cwd=outside,
        )
        if "# AET stale-proof demo" not in markdown.read_text(encoding="utf-8"):
            raise SystemExit("installed wheel Markdown demo was not written")
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
