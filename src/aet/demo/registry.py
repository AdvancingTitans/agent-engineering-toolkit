"""Strict installed-resource registry for AET demos."""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

from ..quick.fresh import FRESH_STATES
from .errors import DemoInvariantError
from .models import DemoManifest, MutationSpec


_DEMO_IDS = ("stale-proof",)
_MANIFEST_KEYS = {
    "schema_version",
    "demo_id",
    "title",
    "fixture_path",
    "command",
    "relevant_paths",
    "mutations",
    "expected_before",
    "expected_after",
    "timeout_seconds",
}
_MUTATION_KEYS = {
    "path",
    "operation",
    "expected_old_sha256",
    "old",
    "new",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def list_demos() -> tuple[DemoManifest, ...]:
    return tuple(get_demo(demo_id) for demo_id in _DEMO_IDS)


def get_demo(demo_id: str) -> DemoManifest:
    if demo_id not in _DEMO_IDS:
        raise DemoInvariantError(
            f"unknown demo {demo_id!r}; available demos: {', '.join(_DEMO_IDS)}"
        )
    manifest_path = (
        resources.files("aet.demo")
        / "fixtures"
        / demo_id
        / "manifest.json"
    )
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemoInvariantError(f"cannot load demo manifest: {error}") from error
    return parse_manifest(raw)


def parse_manifest(raw: Any) -> DemoManifest:
    if not isinstance(raw, dict) or set(raw) != _MANIFEST_KEYS:
        raise DemoInvariantError("demo manifest fields do not match the v1 contract")
    if raw.get("schema_version") != "aet-demo-manifest/v1":
        raise DemoInvariantError("unsupported demo manifest schema_version")
    demo_id = raw.get("demo_id")
    if not isinstance(demo_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", demo_id):
        raise DemoInvariantError("demo_id must be lowercase kebab-case")
    title = raw.get("title")
    fixture_path = raw.get("fixture_path")
    if not isinstance(title, str) or not title.strip():
        raise DemoInvariantError("demo title must be non-empty")
    _safe_relative(fixture_path, "fixture_path")
    command = raw.get("command")
    if (
        not isinstance(command, list)
        or not command
        or any(not isinstance(token, str) or not token for token in command)
    ):
        raise DemoInvariantError("demo command must be a non-empty token array")
    for token in command:
        placeholders = re.findall(r"\$\{[^}]+\}", token)
        if any(value != "${PYTHON}" for value in placeholders):
            raise DemoInvariantError("demo command contains an unsupported placeholder")
    relevant = raw.get("relevant_paths")
    if not isinstance(relevant, list) or not relevant:
        raise DemoInvariantError("demo relevant_paths must be a non-empty array")
    for value in relevant:
        _safe_relative(value, "relevant path")
    mutations_raw = raw.get("mutations")
    if not isinstance(mutations_raw, list) or not mutations_raw:
        raise DemoInvariantError("demo mutations must be a non-empty array")
    mutations: list[MutationSpec] = []
    for item in mutations_raw:
        if not isinstance(item, dict) or set(item) != _MUTATION_KEYS:
            raise DemoInvariantError("mutation fields do not match the v1 contract")
        _safe_relative(item.get("path"), "mutation path")
        if item.get("operation") != "replace_text":
            raise DemoInvariantError("unsupported mutation operation")
        if not _SHA256.fullmatch(str(item.get("expected_old_sha256", ""))):
            raise DemoInvariantError("mutation expected_old_sha256 is invalid")
        if (
            not isinstance(item.get("old"), str)
            or not item["old"]
            or not isinstance(item.get("new"), str)
            or item["old"] == item["new"]
        ):
            raise DemoInvariantError("mutation replacement text is invalid")
        mutations.append(MutationSpec(**item))
    for key in ("expected_before", "expected_after"):
        if raw.get(key) not in FRESH_STATES:
            raise DemoInvariantError(f"{key} is not a supported freshness state")
    timeout = raw.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise DemoInvariantError("timeout_seconds must be a positive integer")
    return DemoManifest(
        schema_version=raw["schema_version"],
        demo_id=demo_id,
        title=title,
        fixture_path=fixture_path,
        command=tuple(command),
        relevant_paths=tuple(relevant),
        mutations=tuple(mutations),
        expected_before=raw["expected_before"],
        expected_after=raw["expected_after"],
        timeout_seconds=timeout,
    )


def fixture_resource(manifest: DemoManifest):
    resource = resources.files("aet.demo")
    for part in PurePosixPath(manifest.fixture_path).parts:
        resource = resource / part
    return resource


def _safe_relative(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise DemoInvariantError(f"{label} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise DemoInvariantError(f"{label} must stay inside its declared root")
    if "\\" in value or "\x00" in value:
        raise DemoInvariantError(f"{label} contains an unsafe path character")
