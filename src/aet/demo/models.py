"""Immutable contracts for installed AET demonstrations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


DemoStatus = Literal["PASS", "PASS_WITH_WARNING", "FAIL", "UNKNOWN", "UNAVAILABLE"]


@dataclass(frozen=True)
class MutationSpec:
    path: str
    operation: Literal["replace_text"]
    expected_old_sha256: str
    old: str
    new: str


@dataclass(frozen=True)
class DemoManifest:
    schema_version: str
    demo_id: str
    title: str
    fixture_path: str
    command: tuple[str, ...]
    relevant_paths: tuple[str, ...]
    mutations: tuple[MutationSpec, ...]
    expected_before: str
    expected_after: str
    timeout_seconds: int


@dataclass(frozen=True)
class DemoOptions:
    format: Literal["text", "json", "markdown"] = "text"
    output: Path | None = None
    keep: bool = False
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class DemoResult:
    schema_version: str
    demo_id: str
    overall_status: DemoStatus
    execution_status: str
    before_state: str
    after_state: str
    proof_path: str | None
    workspace_path: str | None
    diagnostics: tuple[str, ...]
    network_calls: int = 0
    llm_calls: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
