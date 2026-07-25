"""SHA-256 and Blob integrity checks for Portable Evidence Bundles."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .loader import BundleError


def validate_integrity(bundle: dict[str, Any]) -> None:
    """Verify every non-manifest file and each content-addressed Blob."""
    manifest = bundle["manifest"]
    integrity = manifest.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        raise BundleError("unsupported_semantics", "integrity algorithm must be sha256")
    expected = integrity.get("file_hashes")
    if not isinstance(expected, dict):
        raise BundleError("invalid_bundle", "integrity.file_hashes must be an object")

    root = Path(bundle["root"])
    actual_paths = _regular_file_paths(root)
    actual_paths.discard("manifest.json")
    expected_paths = set(expected)
    if actual_paths != expected_paths:
        missing = sorted(actual_paths - expected_paths)
        absent = sorted(expected_paths - actual_paths)
        detail = []
        if missing:
            detail.append("unhashed files: " + ", ".join(missing))
        if absent:
            detail.append("missing files: " + ", ".join(absent))
        raise BundleError("integrity_error", "; ".join(detail))

    files = bundle.get("_files")
    if not isinstance(files, dict) or set(files) != expected_paths:
        raise BundleError("integrity_error", "loaded file set does not match the manifest")
    for relative, digest in expected.items():
        if not _is_sha256(digest):
            raise BundleError("invalid_bundle", f"invalid SHA-256 for {relative}")
        raw = files.get(relative)
        if not isinstance(raw, bytes):
            raise BundleError("integrity_error", f"file was not loaded as bytes: {relative}")
        actual = hashlib.sha256(raw).hexdigest()
        if actual != digest:
            raise BundleError("integrity_error", f"SHA-256 mismatch for {relative}")
        if relative.startswith("blobs/"):
            _validate_blob_name(relative, actual)


def referenced_blob_paths(bundle: dict[str, Any]) -> set[str]:
    """Return all Blob references exposed by Evidence and Source records."""
    references: set[str] = set()
    for evidence in bundle.get("evidence", []):
        integrity = evidence.get("integrity")
        if isinstance(integrity, dict) and isinstance(integrity.get("blob_ref"), str):
            references.add(integrity["blob_ref"])
    for source in bundle.get("sources", []):
        locator = source.get("locator")
        if isinstance(locator, dict) and isinstance(locator.get("blob_ref"), str):
            references.add(locator["blob_ref"])
    return references


def validate_blobs(bundle: dict[str, Any]) -> None:
    """Require every referenced Blob to exist and match its content address."""
    blobs = bundle.get("blobs")
    if not isinstance(blobs, dict):
        raise BundleError("invalid_bundle", "loaded blobs must be an object")
    for reference in sorted(referenced_blob_paths(bundle)):
        raw = blobs.get(reference)
        if not isinstance(raw, bytes):
            raise BundleError("integrity_error", f"referenced Blob is missing: {reference}")
        actual = hashlib.sha256(raw).hexdigest()
        _validate_blob_name(reference, actual)
    for evidence in bundle.get("evidence", []):
        integrity = evidence.get("integrity")
        if not isinstance(integrity, dict) or not isinstance(integrity.get("blob_ref"), str):
            continue
        raw = blobs.get(integrity["blob_ref"])
        if not isinstance(raw, bytes):
            raise BundleError(
                "integrity_error",
                f"referenced Blob is missing: {integrity['blob_ref']}",
            )
        actual = hashlib.sha256(raw).hexdigest()
        if integrity.get("content_hash") != actual:
            raise BundleError(
                "integrity_error",
                f"Evidence content hash does not match Blob: {evidence.get('id', 'UNKNOWN')}",
            )
        if (
            "original_bytes" in integrity
            and integrity.get("original_bytes") != len(raw)
        ):
            raise BundleError(
                "integrity_error",
                f"Evidence original byte count does not match Blob: {evidence.get('id', 'UNKNOWN')}",
            )
    for source in bundle.get("sources", []):
        locator = source.get("locator")
        integrity = source.get("integrity")
        if (
            not isinstance(locator, dict)
            or not isinstance(locator.get("blob_ref"), str)
            or not isinstance(integrity, dict)
        ):
            continue
        raw = blobs.get(locator["blob_ref"])
        if not isinstance(raw, bytes):
            raise BundleError(
                "integrity_error",
                f"referenced Blob is missing: {locator['blob_ref']}",
            )
        actual = hashlib.sha256(raw).hexdigest()
        if integrity.get("content_hash") != actual:
            raise BundleError(
                "integrity_error",
                f"Source content hash does not match Blob: {source.get('id', 'UNKNOWN')}",
            )


def _regular_file_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    try:
        for directory, _, files in os.walk(root, followlinks=False):
            for name in files:
                paths.add((Path(directory) / name).relative_to(root).as_posix())
    except OSError as error:
        raise BundleError("integrity_error", f"cannot enumerate Bundle files: {error}") from error
    return paths


def _validate_blob_name(relative: str, actual: str) -> None:
    prefix = "blobs/sha256-"
    if not relative.startswith(prefix) or len(relative) != len(prefix) + 64:
        raise BundleError("invalid_bundle", f"invalid Blob reference: {relative}")
    declared = relative[len(prefix) :]
    if not _is_sha256(declared):
        raise BundleError("invalid_bundle", f"invalid Blob content address: {relative}")
    if declared != actual:
        raise BundleError("integrity_error", f"Blob content address mismatch: {relative}")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
