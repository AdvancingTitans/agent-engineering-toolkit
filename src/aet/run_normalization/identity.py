"""Stable source identity and content hashes for canonical Run Records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def build_identity(
    *,
    run_group_id: str,
    generation_id: str,
    native_id: str | None,
    source_order_id: str,
    semantic_component_key: str,
    semantic_content: dict[str, Any],
    synthetic: bool = False,
    content_fallback: bool = False,
) -> dict[str, str]:
    content_hash = sha256(semantic_content)
    if synthetic:
        kind = "synthetic"
        stable_source_record_id = f"synthetic:{semantic_component_key}:{source_order_id}"
    elif native_id:
        kind = "native"
        stable_source_record_id = native_id
    elif content_fallback:
        kind = "content"
        stable_source_record_id = f"sha256:{content_hash}"
    else:
        kind = "location"
        stable_source_record_id = source_order_id
    record_id = hashlib.sha256(
        (
            run_group_id
            + "\0"
            + generation_id
            + "\0"
            + stable_source_record_id
            + "\0"
            + semantic_component_key
        ).encode("utf-8")
    ).hexdigest()
    return {
        "run_group_id": run_group_id,
        "stable_source_record_id": stable_source_record_id,
        "identity_kind": kind,
        "source_order_id": source_order_id,
        "record_id": record_id,
        "content_hash": content_hash,
    }
