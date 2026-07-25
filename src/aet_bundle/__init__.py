"""Optional Python convenience API for Portable Evidence Bundle v1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from aet.bundle import (
    BundleError,
    load_bundle,
    manifest_content_hash,
    validate_bundle,
    validate_review_result,
)


def query_claims(
    bundle: Mapping[str, Any],
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Return Claims, optionally filtered by one portable status."""
    claims = _records(bundle, "claims")
    if status is None:
        return list(claims)
    return [claim for claim in claims if claim.get("status") == status]


def query_evidence(
    bundle: Mapping[str, Any],
    *,
    strength: str | None = None,
    freshness: str | None = None,
) -> list[dict[str, Any]]:
    """Return Evidence without changing its strength or Freshness."""
    evidence = _records(bundle, "evidence")
    return [
        item
        for item in evidence
        if (strength is None or item.get("strength") == strength)
        and (
            freshness is None
            or item.get("freshness", {}).get("status") == freshness
        )
    ]


def resolve_source(
    bundle: Mapping[str, Any],
    source_id: str,
) -> dict[str, Any]:
    """Resolve one Source ID."""
    if not isinstance(source_id, str) or not source_id:
        raise BundleError("reference_error", "source_id must be a non-empty string")
    for source in _records(bundle, "sources"):
        if source.get("id") == source_id:
            return source
    raise BundleError("reference_error", f"unknown Source ID: {source_id}")


def read_blob(
    bundle: Mapping[str, Any] | Path,
    blob_ref: str,
) -> bytes:
    """Return one Manifest-declared, content-addressed Blob."""
    prefix = "blobs/sha256-"
    if (
        not isinstance(blob_ref, str)
        or not blob_ref.startswith(prefix)
        or len(blob_ref) != len(prefix) + 64
        or any(
            character not in "0123456789abcdef"
            for character in blob_ref[len(prefix) :]
        )
    ):
        raise BundleError("reference_error", "blob_ref must use blobs/sha256-<hash>")
    if isinstance(bundle, Mapping):
        root = bundle.get("root")
        if not isinstance(root, str) or not root:
            raise BundleError(
                "invalid_bundle",
                "loaded Bundle must retain its validated root",
            )
        authoritative = validate_bundle(Path(root))
    else:
        authoritative = validate_bundle(Path(bundle))
    blobs = authoritative.get("blobs")
    if not isinstance(blobs, dict) or not isinstance(blobs.get(blob_ref), bytes):
        raise BundleError("reference_error", f"unknown Blob reference: {blob_ref}")
    manifest = authoritative.get("manifest")
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("bundle"), dict)
        or manifest["bundle"].get("content_hash") != manifest_content_hash(manifest)
    ):
        raise BundleError("integrity_error", "Manifest content hash mismatch")
    file_hashes = (
        manifest.get("integrity", {}).get("file_hashes")
        if isinstance(manifest.get("integrity"), dict)
        else None
    )
    if not isinstance(file_hashes, dict) or blob_ref not in file_hashes:
        raise BundleError("integrity_error", f"Blob is not declared by Manifest: {blob_ref}")
    raw = blobs[blob_ref]
    actual = hashlib.sha256(raw).hexdigest()
    if file_hashes[blob_ref] != actual or blob_ref != f"{prefix}{actual}":
        raise BundleError("integrity_error", f"Blob hash mismatch: {blob_ref}")
    return raw


def render_prompt_context(
    bundle: Mapping[str, Any],
    *,
    max_bytes: int = 65536,
) -> str:
    """Render deterministic Core JSON for a generic reviewer prompt."""
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    projection = {
        "consumer_guidance": bundle.get("consumer_guide"),
        "index": bundle.get("index"),
        "claims": _records(bundle, "claims"),
        "evidence": _records(bundle, "evidence"),
        "observations": _records(bundle, "observations"),
    }
    rendered = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(rendered.encode("utf-8")) > max_bytes:
        raise BundleError(
            "budget_error",
            "portable prompt context exceeds max_bytes; query Core records first",
        )
    return rendered


def validate_review_references(
    bundle_path: Path,
    review: Path | Mapping[str, Any],
) -> dict[str, Any]:
    """Validate reviewer references without replacing reviewer judgment."""
    return validate_review_result(bundle_path, review)


def _records(bundle: Mapping[str, Any], field: str) -> list[dict[str, Any]]:
    value = bundle.get(field)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise BundleError("invalid_bundle", f"bundle.{field} must contain objects")
    return value


__all__ = [
    "BundleError",
    "load_bundle",
    "query_claims",
    "query_evidence",
    "read_blob",
    "render_prompt_context",
    "resolve_source",
    "validate_bundle",
    "validate_review_references",
]
