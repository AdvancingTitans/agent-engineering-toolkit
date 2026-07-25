"""Deterministic secret redaction for portable Bundle projections and Blobs."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any, Mapping

from .loader import BundleError


_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(api[_-]?key|token|secret|password|passwd|authorization)"
        r"\s*([=:])\s*([^\s'\"]+)"
    ),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+\-/=]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{12,}\b"),
)
_REFERENCE_FIELDS = {
    "id",
    "task_id",
    "workspace_id",
    "investigation_id",
    "bundle_id",
    "parent_bundle_id",
    "schema_version",
    "source_refs",
    "evidence_refs",
    "counter_evidence_refs",
    "observation_refs",
    "affected_observation_refs",
    "affected_evidence_refs",
    "evidence_candidate_refs",
    "supports",
    "contradicts",
    "input_ref",
    "output_ref",
    "hypothesis_ref",
    "content_hash",
    "configuration_hash",
    "environment_hash",
}


def redact_bundle_material(
    records: Mapping[str, list[dict[str, Any]]],
    blobs: Mapping[str, bytes],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bytes]]:
    """Redact exported text and derive new content addresses when needed."""
    redacted = {
        name: [_redact_value(deepcopy(record)) for record in values]
        for name, values in records.items()
    }
    output_blobs: dict[str, bytes] = {}
    replacements: dict[str, tuple[str, str, int]] = {}
    for reference, raw in blobs.items():
        if not isinstance(reference, str) or not isinstance(raw, bytes):
            raise BundleError("invalid_bundle", "Blob mapping must use string paths and byte values")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise BundleError(
                "privacy_error",
                f"cannot safely redact non-UTF-8 Blob: {reference}",
            ) from error
        else:
            transformed = redact_text(text).encode("utf-8")
        digest = hashlib.sha256(transformed).hexdigest()
        new_reference = f"blobs/sha256-{digest}"
        output_blobs[new_reference] = transformed
        replacements[reference] = (new_reference, digest, len(transformed))

    for values in redacted.values():
        for record in values:
            _replace_blob_bindings(record, replacements)
    return redacted, output_blobs


def redact_text(value: str) -> str:
    """Replace recognized secret values without retaining the original."""
    result = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            result = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


def _redact_value(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {item_key: _redact_value(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, key) for item in value]
    if isinstance(value, str):
        redacted = redact_text(value)
        if key in _REFERENCE_FIELDS:
            if redacted != value:
                raise BundleError(
                    "privacy_error",
                    f"cannot redact stable reference field: {key}",
                )
            return value
        return redacted
    return value


def _replace_blob_bindings(
    value: Any,
    replacements: Mapping[str, tuple[str, str, int]],
) -> None:
    if isinstance(value, dict):
        locator = value.get("locator")
        integrity = value.get("integrity")
        if (
            isinstance(locator, dict)
            and isinstance(locator.get("blob_ref"), str)
            and locator["blob_ref"] in replacements
        ):
            replacement, digest, _length = replacements[locator["blob_ref"]]
            locator["blob_ref"] = replacement
            if isinstance(integrity, dict):
                integrity["content_hash"] = digest
        blob_reference = value.get("blob_ref")
        if isinstance(blob_reference, str) and blob_reference in replacements:
            replacement, digest, length = replacements[blob_reference]
            value["blob_ref"] = replacement
            if "content_hash" in value:
                value["content_hash"] = digest
            if "original_bytes" in value:
                value["original_bytes"] = length
        for item in value.values():
            _replace_blob_bindings(item, replacements)
    elif isinstance(value, list):
        for item in value:
            _replace_blob_bindings(item, replacements)
