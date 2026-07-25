"""Canonical JSON encoding for Portable Evidence Bundle integrity checks."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from .loader import BundleError


def canonical_json_bytes(value: Any) -> bytes:
    """Encode one JSON value deterministically as UTF-8.

    Object keys are sorted, insignificant whitespace is removed, array order is
    preserved, and non-finite numbers are rejected.
    """
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise BundleError("invalid_bundle", f"value is not canonical JSON: {error}") from error


def manifest_content_hash(manifest: dict[str, Any]) -> str:
    """Bind all Manifest semantics without creating a self-reference."""
    candidate = deepcopy(manifest)
    bundle = candidate.get("bundle")
    if not isinstance(bundle, dict) or "content_hash" not in bundle:
        raise BundleError("invalid_bundle", "manifest bundle.content_hash is required")
    bundle["content_hash"] = "0" * 64
    return hashlib.sha256(canonical_json_bytes(candidate)).hexdigest()
