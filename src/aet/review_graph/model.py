"""Shared Review Graph constants and deterministic helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CODE_GRAPH_SCHEMA = "aet-code-graph/1.0"
REVIEW_GRAPH_SCHEMA = "aet-review-graph/1.0"
REVIEW_SLICE_SCHEMA = "aet-review-slice/1.0"
REVIEW_MANIFEST_SCHEMA = "aet-review-manifest/1.0"

STATES = {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
MANDATORY_ROOT_KINDS = {
    "intent",
    "allowed_scope",
    "protected_scope",
    "verification_requirement",
    "stop_condition",
}


@dataclass(frozen=True)
class GraphLimits:
    """Hard context budgets; mandatory safety nodes are never truncated."""

    max_nodes: int = 24
    max_edges: int = 32
    max_bytes: int = 8_000

    def validate(self) -> None:
        for name, value in (
            ("max_nodes", self.max_nodes),
            ("max_edges", self.max_edges),
            ("max_bytes", self.max_bytes),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


def stable_id(prefix: str, *parts: object) -> str:
    """Return a stable identifier without leaking raw values into IDs."""
    payload = "\0".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(payload).hexdigest()[:20]}"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    """Serialize finite JSON deterministically."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
