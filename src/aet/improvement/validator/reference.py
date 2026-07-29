"""Validate Candidate code references against the local repository."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import Any, Mapping

from ..models.candidate import CodeTarget
from . import ValidationResult


def validate_reference(
    target: CodeTarget | Mapping[str, Any],
    *,
    root: Path = Path("."),
) -> ValidationResult:
    """Check file, symbol, and optional commit without following guesswork."""
    path_value = target.path if isinstance(target, CodeTarget) else target.get("path")
    symbol = target.symbol if isinstance(target, CodeTarget) else target.get("symbol")
    if not isinstance(path_value, str) or not isinstance(symbol, str):
        return ValidationResult(False, "INVALID_REFERENCE", "CodeTarget is incomplete.")
    relative = Path(path_value)
    if relative.is_absolute() or ".." in relative.parts:
        return ValidationResult(False, "INVALID_REFERENCE", "CodeTarget path is unsafe.")
    path = root.resolve() / relative
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return ValidationResult(False, "INVALID_REFERENCE", "CodeTarget escapes root.")
    if not path.is_file() or path.is_symlink():
        return ValidationResult(
            False,
            "INVALID_REFERENCE",
            f"File does not exist: {path_value}",
        )
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        return ValidationResult(
            False,
            "INVALID_REFERENCE",
            f"Cannot inspect {path_value}: {error}",
        )
    symbols = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if symbol not in symbols:
        return ValidationResult(
            False,
            "INVALID_REFERENCE",
            f"Symbol does not exist: {path_value}:{symbol}",
        )
    if isinstance(target, Mapping) and "commit" in target:
        expected = target["commit"]
        try:
            current = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ValidationResult(
                False,
                "INVALID_REFERENCE",
                "Cannot verify target commit.",
            )
        if current != expected:
            return ValidationResult(
                False,
                "INVALID_REFERENCE",
                "CodeTarget commit does not match the current repository.",
            )
    return ValidationResult(True, "VALID", "CodeTarget exists at the current commit.")
