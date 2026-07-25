"""Safe, dependency-free loading for directory Portable Evidence Bundles."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_MAX_BLOB_BYTES = 64 * 1024 * 1024


class BundleError(ValueError):
    """A Portable Evidence Bundle failed a fail-closed check."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def load_bundle(
    path: Path,
    *,
    max_blob_bytes: int = DEFAULT_MAX_BLOB_BYTES,
) -> dict[str, Any]:
    """Load a directory Bundle without trusting paths or following symlinks."""
    if (
        not isinstance(max_blob_bytes, int)
        or isinstance(max_blob_bytes, bool)
        or max_blob_bytes < 0
    ):
        raise BundleError("invalid_argument", "max_blob_bytes must be a non-negative integer")
    root = _safe_root(path)
    manifest_path = _safe_file(root, "manifest.json")
    manifest = _read_json_object(manifest_path, "manifest.json")
    contents = manifest.get("contents")
    if not isinstance(contents, dict):
        raise BundleError("invalid_bundle", "manifest contents must be an object")

    expected_content_keys = {
        "index",
        "claims",
        "evidence",
        "observations",
        "sources",
        "diagnostics",
        "conflicts",
        "ledger",
        "policy",
        "consumer_guide",
        "report",
    }
    if set(contents) != expected_content_keys:
        raise BundleError(
            "invalid_bundle",
            "manifest contents must declare exactly the v1 content files",
        )

    content_paths: dict[str, str] = {}
    for key, value in contents.items():
        if not isinstance(value, str):
            raise BundleError("invalid_bundle", f"contents.{key} must be a path string")
        _safe_relative(value)
        if value == "manifest.json":
            raise BundleError("invalid_bundle", "manifest cannot be one of its own content files")
        if value in content_paths.values():
            raise BundleError("invalid_bundle", f"content path is declared more than once: {value}")
        content_paths[key] = value

    policy = _read_json_object(
        _safe_file(root, content_paths["policy"]),
        content_paths["policy"],
    )
    loaded: dict[str, Any] = {
        "root": str(root),
        "manifest": manifest,
        "index": _read_json_object(_safe_file(root, content_paths["index"]), content_paths["index"]),
        "claims": _read_jsonl(_safe_file(root, content_paths["claims"]), content_paths["claims"]),
        "evidence": _read_jsonl(_safe_file(root, content_paths["evidence"]), content_paths["evidence"]),
        "observations": _read_jsonl(
            _safe_file(root, content_paths["observations"]), content_paths["observations"]
        ),
        "sources": _read_jsonl(_safe_file(root, content_paths["sources"]), content_paths["sources"]),
        "diagnostics": _read_jsonl(
            _safe_file(root, content_paths["diagnostics"]), content_paths["diagnostics"]
        ),
        "conflicts": _read_jsonl(
            _safe_file(root, content_paths["conflicts"]), content_paths["conflicts"]
        ),
        "ledger": _read_jsonl(_safe_file(root, content_paths["ledger"]), content_paths["ledger"]),
        "policy": policy,
        "consumer_guide": _read_text(
            _safe_file(root, content_paths["consumer_guide"]),
            content_paths["consumer_guide"],
        ),
        "report": _read_text(_safe_file(root, content_paths["report"]), content_paths["report"]),
        "blobs": {},
        "_files": {},
    }

    file_hashes = manifest.get("integrity", {}).get("file_hashes")
    if not isinstance(file_hashes, dict):
        raise BundleError("invalid_bundle", "manifest integrity.file_hashes must be an object")
    declared_maximum_blob_bytes = (
        policy.get("budgets", {}).get("max_blob_bytes_read")
        if isinstance(policy.get("budgets"), dict)
        else None
    )
    if (
        not isinstance(declared_maximum_blob_bytes, int)
        or isinstance(declared_maximum_blob_bytes, bool)
        or declared_maximum_blob_bytes < 0
    ):
        raise BundleError("invalid_bundle", "policy max_blob_bytes_read must be non-negative")
    maximum_blob_bytes = min(max_blob_bytes, declared_maximum_blob_bytes)
    blob_bytes = 0
    for relative in file_hashes:
        if not isinstance(relative, str):
            raise BundleError("invalid_bundle", "integrity file paths must be strings")
        _safe_relative(relative)
        if relative == "manifest.json":
            raise BundleError(
                "invalid_bundle",
                "manifest.json cannot contain a self-referential file hash",
            )
        source = _safe_file(root, relative)
        if relative.startswith("blobs/"):
            try:
                size = source.stat().st_size
            except OSError as error:
                raise BundleError("invalid_bundle", f"cannot inspect {relative}: {error}") from error
            blob_bytes += size
            if blob_bytes > maximum_blob_bytes:
                raise BundleError(
                    "budget_error",
                    f"Bundle Blob bytes exceed policy budget ({blob_bytes} > {maximum_blob_bytes})",
                )
        try:
            raw = source.read_bytes()
        except OSError as error:
            raise BundleError("invalid_bundle", f"cannot read {relative}: {error}") from error
        loaded["_files"][relative] = raw
        if relative.startswith("blobs/"):
            loaded["blobs"][relative] = raw

    _assert_safe_tree(root)
    return loaded


def _safe_root(path: Path) -> Path:
    candidate = Path(path)
    try:
        mode = candidate.lstat().st_mode
    except OSError as error:
        raise BundleError("invalid_bundle", f"bundle directory is unavailable: {error}") from error
    if stat.S_ISLNK(mode):
        raise BundleError("unsafe_path", "bundle root cannot be a symbolic link")
    if not stat.S_ISDIR(mode):
        raise BundleError("invalid_bundle", "bundle path must be a directory")
    try:
        return candidate.resolve(strict=True)
    except OSError as error:
        raise BundleError("invalid_bundle", f"cannot resolve bundle directory: {error}") from error


def _safe_relative(value: str) -> PurePosixPath:
    if not value or "\x00" in value or "\\" in value:
        raise BundleError("unsafe_path", f"unsafe Bundle path: {value!r}")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise BundleError("unsafe_path", f"Bundle path must be normalized and relative: {value!r}")
    return relative


def _safe_file(root: Path, relative_value: str) -> Path:
    relative = _safe_relative(relative_value)
    current = root
    for part in relative.parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError as error:
            raise BundleError("invalid_bundle", f"Bundle file is unavailable: {relative_value}") from error
        if stat.S_ISLNK(mode):
            raise BundleError("unsafe_path", f"symbolic links are forbidden: {relative_value}")
    if not stat.S_ISREG(current.lstat().st_mode):
        raise BundleError("invalid_bundle", f"Bundle path is not a regular file: {relative_value}")
    try:
        current.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as error:
        raise BundleError("unsafe_path", f"Bundle path escapes its root: {relative_value}") from error
    return current


def _assert_safe_tree(root: Path) -> None:
    try:
        for directory, directories, files in os.walk(root, followlinks=False):
            directory_path = Path(directory)
            for name in [*directories, *files]:
                candidate = directory_path / name
                mode = candidate.lstat().st_mode
                if stat.S_ISLNK(mode):
                    raise BundleError(
                        "unsafe_path",
                        f"symbolic links are forbidden: {candidate.relative_to(root).as_posix()}",
                    )
                if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                    raise BundleError(
                        "unsafe_path",
                        f"special files are forbidden: {candidate.relative_to(root).as_posix()}",
                    )
    except OSError as error:
        raise BundleError("invalid_bundle", f"cannot inspect Bundle tree: {error}") from error


def _read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BundleError("invalid_bundle", f"{label} must be readable UTF-8: {error}") from error


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    value = _decode_json(_read_text(path, label), label)
    if not isinstance(value, dict):
        raise BundleError("invalid_bundle", f"{label} must contain one JSON object")
    return value


def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    text = _read_text(path, label)
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        value = _decode_json(line, f"{label}:{number}")
        if not isinstance(value, dict):
            raise BundleError("invalid_bundle", f"{label}:{number} must contain a JSON object")
        rows.append(value)
    return rows


def _decode_json(raw: str, label: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise BundleError("invalid_bundle", f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise BundleError("invalid_bundle", f"{label} contains non-finite number {value}")

    try:
        return json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except BundleError:
        raise
    except (json.JSONDecodeError, UnicodeError) as error:
        raise BundleError("invalid_bundle", f"{label} contains invalid JSON: {error}") from error
