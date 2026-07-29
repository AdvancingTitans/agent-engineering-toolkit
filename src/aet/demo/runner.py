"""Run installed demos through the existing AET Quick proof and freshness core."""

from __future__ import annotations

import hashlib
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from ..quick.fresh import quick_fresh
from ..quick.proof import quick_proof
from .errors import DemoIOError, DemoInvariantError
from .models import DemoOptions, DemoResult, MutationSpec
from .registry import get_demo
from .sandbox import create_sandbox, resolve_workspace_path


def run_demo(demo_id: str, options: DemoOptions) -> DemoResult:
    manifest = get_demo(demo_id)
    timeout = (
        options.timeout_seconds
        if options.timeout_seconds is not None
        else manifest.timeout_seconds
    )
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise DemoInvariantError("demo timeout must be a positive integer")
    with create_sandbox(manifest, keep=options.keep) as box:
        proof_path = box.artifacts / "proof.json"
        command = [
            sys.executable if token == "${PYTHON}" else token
            for token in manifest.command
        ]
        try:
            with _pushd(box.workspace):
                proof, child_exit = quick_proof(
                    command,
                    proof_path,
                    relevant_paths=manifest.relevant_paths,
                    timeout_seconds=timeout,
                )
                before = quick_fresh(proof_path)
                if child_exit == 0:
                    for mutation in manifest.mutations:
                        _apply_mutation(box.workspace, mutation)
                    after = quick_fresh(proof_path)
                else:
                    after = {"freshness_state": "UNKNOWN"}
        except OSError as error:
            raise DemoIOError(f"demo I/O failed: {error}") from error
        diagnostics: list[str] = []
        execution_status = str(proof.get("authoritative_status", "UNKNOWN"))
        before_state = str(before.get("freshness_state", "UNKNOWN"))
        after_state = str(after.get("freshness_state", "UNKNOWN"))
        if proof.get("command", {}).get("timed_out") or child_exit == 124:
            diagnostics.append(f"test command timed out after {timeout} seconds")
            overall = "FAIL"
        elif child_exit != 0:
            diagnostics.append(f"test command exited with status {child_exit}")
            overall = "FAIL"
        elif execution_status != "PASS":
            diagnostics.append(
                f"test command proof status was {execution_status}, expected PASS"
            )
            overall = "FAIL"
        elif before_state != manifest.expected_before:
            diagnostics.append(
                f"before_state was {before_state}, expected {manifest.expected_before}"
            )
            overall = "FAIL"
        elif after_state != manifest.expected_after:
            diagnostics.append(
                f"after_state was {after_state}, expected {manifest.expected_after}"
            )
            overall = "FAIL"
        else:
            overall = "PASS"
        result = DemoResult(
            schema_version="aet-demo-result/v1",
            demo_id=manifest.demo_id,
            overall_status=overall,
            execution_status=execution_status,
            before_state=before_state,
            after_state=after_state,
            proof_path=str(proof_path) if options.keep else None,
            workspace_path=str(box.workspace) if options.keep else None,
            diagnostics=tuple(diagnostics),
        )
    if box.cleanup_warning:
        return DemoResult(
            **{
                **result.to_dict(),
                "overall_status": "PASS_WITH_WARNING"
                if result.overall_status == "PASS"
                else result.overall_status,
                "workspace_path": str(box.workspace),
                "diagnostics": (*result.diagnostics, box.cleanup_warning),
            }
        )
    return result


def _apply_mutation(workspace: Path, mutation: MutationSpec) -> None:
    path = resolve_workspace_path(workspace, mutation.path)
    if not path.is_file() or path.is_symlink():
        raise DemoInvariantError(
            f"mutation target is unavailable: {mutation.path}"
        )
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != mutation.expected_old_sha256:
        raise DemoInvariantError(
            f"mutation SHA mismatch for {mutation.path}: {digest}"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DemoInvariantError(
            f"mutation target is not UTF-8: {mutation.path}"
        ) from error
    if text.count(mutation.old) != 1:
        raise DemoInvariantError(
            f"mutation old text must occur exactly once in {mutation.path}"
        )
    path.write_text(text.replace(mutation.old, mutation.new), encoding="utf-8")


@contextmanager
def _pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)
