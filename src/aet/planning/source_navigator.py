"""Read-only, workspace-contained source inspection for Planning."""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .errors import PlanningError, PlanningErrorCode
from .models import PlanningConstraints, SourceSite, canonical_relative_path
from .policy import path_matches


_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".sh": "shell",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}
_GENERATED = (
    "dist/**",
    "build/**",
    "vendor/**",
    "node_modules/**",
    "*.min.js",
    "*.generated.*",
)


@dataclass(frozen=True)
class SourceFileSnapshot:
    site: SourceSite
    size: int
    text: str | None


class SourceNavigator:
    def __init__(
        self,
        workspace: Path,
        policy: PlanningConstraints,
        *,
        max_file_bytes: int = 1_000_000,
    ) -> None:
        self.workspace = Path(workspace).resolve(strict=True)
        self.policy = policy
        self.max_file_bytes = max_file_bytes

    def inspect_path(
        self,
        path: str,
        *,
        source_id: str | None = None,
        expected_hash: str | None = None,
        reference_ids: Iterable[str] = (),
        symbol: str | None = None,
    ) -> SourceFileSnapshot:
        normalized = canonical_relative_path(path)
        if path_matches(normalized, self.policy.protected_paths):
            raise PlanningError(
                PlanningErrorCode.PROTECTED_PATH,
                "source path is protected",
            )
        if (
            self.policy.scope_status == "RESOLVED"
            and (
                not self.policy.allowed_paths
                or not path_matches(normalized, self.policy.allowed_paths)
            )
        ):
            raise PlanningError(
                PlanningErrorCode.EVIDENCE_REQUIRED,
                "source path is outside the allowed read scope",
            )
        candidate = self.workspace / normalized
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            return self._unavailable(
                normalized,
                source_id,
                "MISSING",
                reference_ids,
                symbol,
            )
        try:
            resolved.relative_to(self.workspace)
        except ValueError as error:
            raise PlanningError(
                PlanningErrorCode.PATH_ESCAPE,
                "source path resolves outside the workspace",
            ) from error
        if not resolved.is_file():
            return self._unavailable(
                normalized,
                source_id,
                "MISSING",
                reference_ids,
                symbol,
            )
        raw = resolved.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        language = _LANGUAGES.get(resolved.suffix.casefold(), "unknown")
        role = _role(normalized)
        if len(raw) > self.max_file_bytes or b"\x00" in raw:
            status = "UNSUPPORTED"
            text = None
        else:
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                status = "UNSUPPORTED"
                text = None
            else:
                status = (
                    "STALE"
                    if expected_hash is not None and expected_hash != digest
                    else "CONFIRMED"
                )
                if language == "unknown":
                    status = "UNSUPPORTED"
        ranges = self.locate_symbol_text(text, language, symbol) if symbol and text else []
        start_line = ranges[0][0] if ranges else (1 if text is not None else None)
        end_line = ranges[0][1] if ranges else (
            max(1, len(text.splitlines())) if text is not None else None
        )
        identifier = source_id or _source_id(normalized, digest)
        return SourceFileSnapshot(
            site=SourceSite(
                source_id=identifier,
                path=normalized,
                symbol=symbol,
                start_line=start_line,
                end_line=end_line,
                content_hash=digest,
                language=language,
                role=role,
                read_status=status,
                reference_ids=sorted(set(reference_ids)),
            ),
            size=len(raw),
            text=text,
        )

    def locate_symbol(
        self,
        path: str,
        symbol: str,
    ) -> list[tuple[int, int]]:
        snapshot = self.inspect_path(path)
        if snapshot.text is None:
            return []
        return self.locate_symbol_text(
            snapshot.text,
            snapshot.site.language,
            symbol,
        )

    def read_range(
        self,
        path: str,
        start: int,
        end: int,
    ) -> str:
        snapshot = self.inspect_path(path)
        if snapshot.text is None:
            raise PlanningError(
                PlanningErrorCode.UNSUPPORTED_LANGUAGE,
                "source text is unavailable",
            )
        lines = snapshot.text.splitlines()
        if start < 1 or end < start or end > len(lines):
            raise PlanningError(
                PlanningErrorCode.SOURCE_STALE,
                "requested source range is outside the current file",
            )
        return "\n".join(lines[start - 1 : end])

    @staticmethod
    def locate_symbol_text(
        text: str | None,
        language: str,
        symbol: str | None,
    ) -> list[tuple[int, int]]:
        if text is None or not symbol:
            return []
        short = symbol.rsplit(".", 1)[-1]
        if language == "python":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                return []
            return sorted(
                {
                    (node.lineno, getattr(node, "end_lineno", node.lineno))
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and node.name == short
                }
            )
        pattern = re.compile(
            rf"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|fn|func)\s+{re.escape(short)}\b"
        )
        return [
            (number, number)
            for number, line in enumerate(text.splitlines(), start=1)
            if pattern.search(line)
        ]

    def _unavailable(
        self,
        path: str,
        source_id: str | None,
        status: str,
        reference_ids: Iterable[str],
        symbol: str | None,
    ) -> SourceFileSnapshot:
        digest = hashlib.sha256(b"").hexdigest()
        return SourceFileSnapshot(
            site=SourceSite(
                source_id=source_id or _source_id(path, digest),
                path=path,
                symbol=symbol,
                start_line=None,
                end_line=None,
                content_hash=digest,
                language=_LANGUAGES.get(Path(path).suffix.casefold(), "unknown"),
                role=_role(path),
                read_status=status,
                reference_ids=sorted(set(reference_ids)),
            ),
            size=0,
            text=None,
        )


def _source_id(path: str, digest: str) -> str:
    value = hashlib.sha256(f"{path}\0{digest}".encode("utf-8")).hexdigest()[:16]
    return "SRC-" + value.upper()


def _role(path: str) -> str:
    if any(path_matches(path, [pattern]) for pattern in _GENERATED):
        return "GENERATED"
    name = Path(path).name.casefold()
    if path.startswith("tests/") or name.startswith("test_") or ".test." in name:
        return "TEST"
    if path.endswith(".schema.json") or path.startswith("schemas/"):
        return "SCHEMA"
    if path.endswith((".toml", ".yaml", ".yml", ".json")):
        return "CONFIG"
    if path.endswith(".md"):
        return "DOC"
    return "IMPLEMENTATION"
