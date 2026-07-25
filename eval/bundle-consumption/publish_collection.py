#!/usr/bin/env python3
"""Publish one sanitized, independently rescorable consumption collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from collect_consumer import _strict_object
from score_collection import score_collection


SENSITIVE_MARKERS = (
    "authorization:",
    "bearer ",
    "password=",
    "ghp_",
    "sk-",
)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def _read_strict(path: Path) -> dict[str, Any]:
    return _strict_object(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sensitive(value: Any) -> bool:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    return any(marker in serialized for marker in SENSITIVE_MARKERS)


def publish_collection(
    source_dir: Path,
    output_dir: Path,
    catalog: Path,
    bundle_root: Path,
) -> dict[str, Any]:
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError(f"publication output already exists: {output_dir}")
    response = _read_strict(source_dir / "response.json")
    report = _read_strict(source_dir / "report.json")
    metadata = _read_strict(source_dir / "metadata.json")
    elapsed = metadata.get("elapsed_seconds_to_complete_response")
    consumer_id = metadata.get("consumer_id")
    runtime_version = metadata.get("runtime_version")
    model_id = metadata.get("model_id")
    command_argv_sha256 = metadata.get("command_argv_sha256")
    if (
        not isinstance(elapsed, (int, float))
        or isinstance(elapsed, bool)
        or elapsed < 0
        or not isinstance(consumer_id, str)
        or not consumer_id
        or not isinstance(runtime_version, str)
        or not runtime_version.strip()
        or not isinstance(model_id, str)
        or not model_id.strip()
        or not isinstance(command_argv_sha256, str)
        or len(command_argv_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in command_argv_sha256
        )
        or len(set(command_argv_sha256)) == 1
    ):
        raise ValueError(
            "source metadata has invalid collection-bound identity or provenance"
        )
    reconstructed = score_collection(
        catalog,
        bundle_root,
        response,
        consumer_id=consumer_id,
        consumer_available=True,
        elapsed_seconds=float(elapsed),
    )
    if reconstructed != report:
        raise ValueError("source report cannot be reconstructed from response and metadata")
    if _sensitive(response) or _sensitive(report):
        raise ValueError("structured collection contains a sensitive marker")

    output_dir.mkdir(parents=True)
    _atomic_json(output_dir / "response.json", response)
    _atomic_json(output_dir / "report.json", report)
    published_metadata = {
        **metadata,
        "published_raw_transcript": False,
        "published_structured_response": True,
    }
    _atomic_json(output_dir / "metadata.json", published_metadata)
    integrity = {
        "schema_version": "bundle-consumption-publication-integrity/v1",
        "consumer_id": consumer_id,
        "algorithm": "sha256",
        "file_hashes": {
            name: _sha256(output_dir / name)
            for name in ("metadata.json", "report.json", "response.json")
        },
        "independently_rescorable": True,
        "aggregate_score": None,
    }
    _atomic_json(output_dir / "integrity.json", integrity)
    return integrity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        integrity = publish_collection(
            args.source_dir,
            args.output_dir,
            args.catalog,
            args.bundle_root,
        )
        print(json.dumps(integrity, ensure_ascii=False, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"collection publication failed: {error}") from error


if __name__ == "__main__":
    main()
