"""Temporary, Git-backed workspaces for installed AET demos."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .errors import DemoIOError, DemoInvariantError, DemoUnavailable
from .models import DemoManifest
from .registry import fixture_resource


@dataclass
class DemoSandbox:
    root: Path
    workspace: Path
    artifacts: Path
    retained: bool
    cleanup_warning: str | None = None


@contextmanager
def create_sandbox(
    manifest: DemoManifest,
    keep: bool = False,
) -> Iterator[DemoSandbox]:
    if shutil.which("git") is None:
        raise DemoUnavailable("Git is required for the stale-proof demo")
    try:
        root = Path(tempfile.mkdtemp(prefix="aet-demo-")).resolve()
        workspace = root / "workspace"
        artifacts = root / "artifacts"
        artifacts.mkdir()
        source = fixture_resource(manifest)
        _copy_fixture(source, workspace)
        box = DemoSandbox(root, workspace, artifacts, keep)
        _initialize_git(box)
    except DemoUnavailable:
        raise
    except DemoInvariantError:
        if "root" in locals():
            shutil.rmtree(root, ignore_errors=True)
        raise
    except OSError as error:
        if "root" in locals():
            shutil.rmtree(root, ignore_errors=True)
        raise DemoIOError(f"cannot create demo sandbox: {error}") from error
    try:
        yield box
    finally:
        if not keep:
            try:
                shutil.rmtree(box.root)
            except OSError as error:
                box.cleanup_warning = (
                    f"cleanup failed; retained sandbox at {box.root}: {error}"
                )


def resolve_workspace_path(workspace: Path, relative: str) -> Path:
    candidate = (workspace / relative).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError as error:
        raise DemoInvariantError(
            f"path escapes the demo workspace: {relative}"
        ) from error
    return candidate


def _copy_fixture(source, destination: Path) -> None:
    if not source.is_dir():
        raise DemoInvariantError("packaged demo fixture is missing")
    if isinstance(source, Path):
        for candidate in source.rglob("*"):
            if candidate.is_symlink():
                raise DemoInvariantError(
                    f"packaged demo fixture contains a symlink: {candidate.name}"
                )
    _copy_resource_tree(source, destination)
    for candidate in destination.rglob("*"):
        resolved = candidate.resolve()
        try:
            resolved.relative_to(destination.resolve())
        except ValueError as error:
            raise DemoInvariantError(
                f"copied fixture path escapes the sandbox: {candidate}"
            ) from error
def _copy_resource_tree(source, destination: Path) -> None:
    destination.mkdir()
    for child in source.iterdir():
        if child.name in {"", ".", ".."} or "/" in child.name or "\\" in child.name:
            raise DemoInvariantError("packaged fixture contains an unsafe entry name")
        target = destination / child.name
        if child.is_dir():
            _copy_resource_tree(child, target)
        elif child.is_file():
            with child.open("rb") as input_stream, target.open("wb") as output_stream:
                shutil.copyfileobj(input_stream, output_stream)
        else:
            raise DemoInvariantError(
                f"packaged fixture entry is not a regular file: {child.name}"
            )


def _initialize_git(box: DemoSandbox) -> None:
    hooks = box.root / "empty-hooks"
    hooks.mkdir()
    environment = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    commands = (
        ["git", "init", "--quiet"],
        ["git", "config", "--local", "user.name", "AET Demo"],
        ["git", "config", "--local", "user.email", "demo@aet.invalid"],
        ["git", "config", "--local", "core.hooksPath", str(hooks)],
        ["git", "add", "--all"],
        ["git", "commit", "--quiet", "-m", "demo baseline"],
    )
    for argv in commands:
        completed = subprocess.run(
            argv,
            cwd=box.workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode:
            diagnostic = completed.stderr.strip() or completed.stdout.strip()
            raise DemoUnavailable(
                f"cannot initialize the demo Git repository: {diagnostic}"
            )
