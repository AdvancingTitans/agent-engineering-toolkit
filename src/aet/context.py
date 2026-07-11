"""Deterministic context provenance manifests for coding-agent work."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .config import AuditConfig
from .discovery import discover_assets
from .evidence import compare_workspace_snapshots, workspace_snapshot
from .models import Status


class ContextError(ValueError):
    """Raised when a Context Manifest cannot be safely created or updated."""


def discover_context(root: Path, output: Path, config: AuditConfig | None = None) -> dict[str, Any]:
    """Write a non-overwriting record of discoverable instruction and Skill assets."""
    root = root.resolve()
    output = output.resolve()
    if output.exists():
        raise ContextError(f"context manifest already exists and will not be overwritten: {output}")
    if not root.is_dir():
        raise ContextError(f"context root does not exist: {root}")
    assets = [
        {
            "path": asset.relative_path,
            "role": asset.kind,
            "sha256": _sha256(asset.path),
            "discovered": True,
            "declared_read": False,
        }
        for asset in discover_assets(root, config)
    ]
    data = {
        "schema_version": __version__,
        "report_kind": "context_manifest",
        "generated_at": _timestamp(),
        "root": str(root),
        "workspace_snapshot": workspace_snapshot(root),
        "assets": assets,
    }
    _write_json(output, data)
    return data


def record_context(manifest_path: Path, *, read_paths: Iterable[str], reference_paths: Iterable[str]) -> dict[str, Any]:
    """Record local references and explicit read attestations without inferring use."""
    manifest_path = manifest_path.resolve()
    manifest = _load_manifest(manifest_path)
    root = Path(manifest["root"])
    references = list(reference_paths)
    reads = list(read_paths)
    if not references and not reads:
        raise ContextError("context record requires at least one --read or --reference path")
    assets = {asset["path"]: asset for asset in manifest["assets"]}
    for value in references:
        relative, candidate = _local_file(root, value)
        if relative not in assets:
            asset = {
                "path": relative,
                "role": "reference",
                "sha256": _sha256(candidate),
                "discovered": False,
                "declared_read": False,
            }
            manifest["assets"].append(asset)
            assets[relative] = asset
    for value in reads:
        relative, _ = _local_file(root, value)
        try:
            asset = assets[relative]
        except KeyError as error:
            raise ContextError(f"read declaration is not a recorded context asset: {relative}") from error
        asset["declared_read"] = True
        asset["declaration_source"] = "agent_attestation"
        asset["declared_at"] = _timestamp()
    manifest["assets"].sort(key=lambda asset: asset["path"])
    manifest["recorded_at"] = _timestamp()
    _write_json(manifest_path, manifest)
    return manifest


def verify_context(manifest_path: Path) -> dict[str, Any]:
    """Verify recorded local hashes and workspace freshness without mutating the manifest."""
    manifest = _load_manifest(manifest_path.resolve())
    root = Path(manifest["root"])
    results: list[dict[str, Any]] = []
    for asset in manifest["assets"]:
        relative = asset["path"]
        candidate = root / relative
        if not candidate.is_file():
            results.append({"path": relative, "status": Status.FAIL.value, "reason": "recorded asset is missing"})
            continue
        actual = _sha256(candidate)
        if actual != asset["sha256"]:
            results.append({"path": relative, "status": Status.FAIL.value, "recorded_sha256": asset["sha256"], "current_sha256": actual})
        else:
            results.append({"path": relative, "status": Status.PASS.value, "sha256": actual})
    binding = compare_workspace_snapshots({"manifest": manifest["workspace_snapshot"], "current": workspace_snapshot(root)})
    status = Status.FAIL.value if any(item["status"] == Status.FAIL.value for item in results) or binding["status"] == Status.FAIL.value else binding["status"]
    return {
        "schema_version": __version__,
        "report_kind": "context_verification",
        "generated_at": _timestamp(),
        "root": str(root),
        "status": status,
        "assets": results,
        "workspace_snapshot_binding": binding,
    }


def render_context_verification(result: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    lines = [
        "# AET Context Verification",
        "",
        f"- Status: `{result['status']}`",
        f"- Workspace snapshot: `{result['workspace_snapshot_binding'].get('status', Status.UNKNOWN.value)}`",
        "",
        "| Asset | Status |",
        "|---|---|",
    ]
    lines.extend(f"| `{item['path']}` | {item['status']} |" for item in result["assets"])
    return "\n".join(lines) + "\n"


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContextError(f"cannot read context manifest: {error}") from error
    if not isinstance(data, dict) or data.get("report_kind") != "context_manifest":
        raise ContextError("input is not an AET Context Manifest")
    if not isinstance(data.get("root"), str) or not isinstance(data.get("assets"), list) or not isinstance(data.get("workspace_snapshot"), dict):
        raise ContextError("context manifest is missing required fields")
    if any(not isinstance(asset, dict) or not isinstance(asset.get("path"), str) or not isinstance(asset.get("sha256"), str) for asset in data["assets"]):
        raise ContextError("context manifest has an invalid asset")
    return data


def _local_file(root: Path, value: str) -> tuple[str, Path]:
    candidate = (root / value).resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError as error:
        raise ContextError("context asset must be inside the manifest root") from error
    if not candidate.is_file():
        raise ContextError(f"context asset does not exist or is not a regular file: {relative}")
    return relative, candidate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
