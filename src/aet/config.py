"""Small, explicit configuration for deterministic AET scans."""

from __future__ import annotations

import fnmatch
import tomllib
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when an AET configuration cannot be interpreted safely."""


@dataclass(frozen=True)
class Exclusion:
    pattern: str
    reason: str


@dataclass(frozen=True)
class AuditConfig:
    source: Path | None
    includes: tuple[str, ...] = ()
    exclusions: tuple[Exclusion, ...] = ()

    def includes_path(self, relative_path: str) -> bool:
        return not self.includes or any(_matches(relative_path, pattern) for pattern in self.includes)

    def excludes(self, relative_path: str) -> bool:
        return any(_matches(relative_path, item.pattern) for item in self.exclusions)

    def to_dict(self) -> dict:
        return {
            "source": str(self.source) if self.source else None,
            "includes": list(self.includes),
            "exclusions": [{"pattern": item.pattern, "reason": item.reason} for item in self.exclusions],
        }


def load_audit_config(root: Path, explicit: Path | None = None) -> AuditConfig:
    """Load an optional aet.toml without silently accepting malformed exclusions."""
    path = explicit if explicit is not None else root / "aet.toml"
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.exists() and explicit is None:
        return AuditConfig(None)
    if not path.is_file():
        raise ConfigError(f"configuration does not exist: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"invalid TOML: {error}") from error
    scan = data.get("scan", {})
    if not isinstance(scan, dict):
        raise ConfigError("[scan] must be a TOML table")
    raw_includes = scan.get("include", [])
    if not isinstance(raw_includes, list) or not all(isinstance(item, str) and item for item in raw_includes):
        raise ConfigError("scan.include must be an array of non-empty path patterns")
    raw_exclusions = scan.get("exclude", [])
    if not isinstance(raw_exclusions, list):
        raise ConfigError("scan.exclude must be an array of { pattern, reason } tables")
    exclusions: list[Exclusion] = []
    for entry in raw_exclusions:
        if not isinstance(entry, dict):
            raise ConfigError("each scan.exclude entry must be a table")
        pattern, reason = entry.get("pattern"), entry.get("reason")
        if not isinstance(pattern, str) or not pattern or not isinstance(reason, str) or not reason.strip():
            raise ConfigError("each scan.exclude entry needs non-empty pattern and reason")
        exclusions.append(Exclusion(pattern, reason.strip()))
    return AuditConfig(path, tuple(raw_includes), tuple(exclusions))


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)
