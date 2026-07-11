"""Discover locally checked coding-agent assets."""

from __future__ import annotations

from pathlib import Path

from .config import AuditConfig
from .models import Asset

INSTRUCTION_NAMES = {
    "AGENTS.md",
    "CLAUDE.md",
    "CODEX.md",
    "copilot-instructions.md",
    ".cursorrules",
}
IGNORED_DIRECTORIES = {".git", ".venv", "node_modules", "__pycache__", "dist", "build"}


def discover_assets(root: Path, config: AuditConfig | None = None) -> list[Asset]:
    """Return deterministic, supported instruction and Skill assets."""
    assets: list[Asset] = []
    config = config or AuditConfig(None)
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        if not path.is_file():
            continue
        relative_path = path.relative_to(root).as_posix()
        if not config.includes_path(relative_path) or config.excludes(relative_path):
            continue
        if path.name == "SKILL.md":
            kind = "skill"
        elif path.name in INSTRUCTION_NAMES:
            kind = "instruction"
        else:
            continue
        assets.append(Asset(path=path, kind=kind, relative_path=relative_path))
    return assets
