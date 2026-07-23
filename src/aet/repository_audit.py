"""Static, evidence-first repository audit showcases.

Traceability: AET Repository Audit Showcase v1, sections 2–8.  This module
never executes third-party code and never copies source text into reports.
"""

from __future__ import annotations

import ast
import copy
import fnmatch
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__


CASE_IDS = ("swe-agent", "google-adk", "openhands")
PROFILE_SCHEMA_VERSION = "repository-audit-profile/v1"
RESULT_SCHEMA_VERSION = "repository-audit-result/v1"
MANIFEST_SCHEMA_VERSION = "repository-evidence-manifest/v1"

_CATEGORIES = {
    "agent",
    "tool",
    "runtime",
    "verification",
    "trajectory",
    "permission",
    "recovery",
    "feedback",
    "isolation",
    "external",
    "local_agent_definition",
    "requirement",
}
_IDENTIFIER_MARKERS = {
    "permission": (
        "permission",
        "authorization",
        "authenticated",
        "authentication",
        "credential",
        "allowlist",
        "denylist",
        "confirmation",
        "approval",
    ),
    "recovery": ("retry", "recover", "rollback", "fallback"),
    "feedback": ("feedback", "evaluation", "score", "scorer", "metric"),
    "isolation": ("sandbox", "isolation", "container"),
}
_EVIDENCE_CHAIN = (
    ("Requirement", ("requirement",)),
    ("Implementation", ("agent", "tool", "runtime")),
    ("Execution", ("trajectory",)),
    ("Verification", ("verification",)),
)


class RepositoryAuditError(ValueError):
    """Raised when a repository showcase cannot be audited safely."""


@dataclass(frozen=True)
class CollectedFile:
    path: str
    sha256: str
    size: int
    lines: int
    categories: tuple[str, ...]
    category_lines: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size": self.size,
            "lines": self.lines,
            "categories": list(self.categories),
        }


def is_repository_case(value: str) -> bool:
    return value in CASE_IDS


def run_repository_audit(case_id: str, repository: Path, output: Path) -> dict[str, Any]:
    """Audit one locked checkout and write shared machine data plus two locales."""
    started = time.monotonic()
    profile_path = _find_profile(case_id)
    profile = _load_profile(profile_path, case_id)
    root = repository.resolve()
    if not root.is_dir():
        raise RepositoryAuditError(f"local repository does not exist: {root}")
    output = _safe_output_path(output)
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise RepositoryAuditError("output directory must remain outside the audited repository")

    lock_evidence = _repository_lock_evidence(root, profile)
    files, skipped = _collect_files(root, profile, started)
    category_index = _category_index(files)
    boundary_evidence = _license_boundary_evidence(root, profile, files)
    findings = _build_findings(profile, lock_evidence, boundary_evidence, category_index)
    budget = float(profile["runtime"]["max_seconds"])
    generated_at = datetime.now(UTC).isoformat()
    repository_data = {
        "case_id": case_id,
        "name": profile["repository"]["name"],
        "url": profile["repository"]["url"],
        "branch": profile["repository"]["branch"],
        "commit": profile["repository"]["commit"],
        "license": profile["repository"]["license"],
    }
    scope = {
        "include": profile["scope"]["include"],
        "exclude": profile["scope"]["exclude"],
        "files_collected": len(files),
        "files_skipped": skipped,
    }
    summary = _finding_summary(findings)
    metadata = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "audit_version": __version__,
        "generated_at": generated_at,
        "repository": repository_data,
        "scope": scope,
        "runtime": {
            "total_seconds": 0,
            "max_seconds": budget,
            "within_budget": True,
            "excludes": ["clone", "dependency_install", "llm_network", "manual_review"],
        },
        "llm": {
            "status": "NOT_APPLICABLE",
            "model_name": None,
            "token_usage": None,
            "execution_time_seconds": 0,
            "affects_findings": False,
        },
        "review": {"status": "PENDING", "required_before_publication": True},
        "disclaimer": (
            "Static analysis of a public upstream repository. No source code is "
            "redistributed, and no affiliation or upstream endorsement is implied."
        ),
    }
    manifest = {
        **metadata,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "report_kind": "repository_evidence_manifest",
        "profile": {
            "case_id": case_id,
            "sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
            "schema_version": PROFILE_SCHEMA_VERSION,
        },
        "evidence_count": len(files),
        "files": [item.to_dict() for item in files],
    }
    result = {
        **metadata,
        "report_kind": "repository_audit",
        "summary": summary,
        "findings": findings,
    }

    # Render and stage every artifact before stopping the acceptance clock.
    # The final replacement only substitutes the measured duration.
    _measure_bundle_write(
        output, _render_bundle(profile, category_index, manifest, result)
    )
    elapsed = time.monotonic() - started
    if elapsed > budget:
        raise RepositoryAuditError(f"repository audit exceeded its {budget:g}s runtime budget")
    manifest["runtime"]["total_seconds"] = round(elapsed, 6)
    result["runtime"]["total_seconds"] = round(elapsed, 6)
    _replace_bundle(output, _render_bundle(profile, category_index, manifest, result))
    return result


def _profile_locations(case_id: str) -> tuple[Path, ...]:
    relative = Path("repository-audit-showcase") / "profiles" / f"{case_id}.json"
    source_root = Path(__file__).resolve().parents[2]
    return (
        Path.cwd() / relative,
        source_root / relative,
        Path(sys.prefix) / "share" / "aet" / relative,
    )


def _find_profile(case_id: str) -> Path:
    if case_id not in CASE_IDS:
        raise RepositoryAuditError(f"unknown repository audit case: {case_id}")
    for candidate in _profile_locations(case_id):
        if candidate.is_file():
            return candidate.resolve()
    raise RepositoryAuditError(f"installed profile is missing for case: {case_id}")


def _load_profile(path: Path, case_id: str) -> dict[str, Any]:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RepositoryAuditError(f"invalid repository audit profile: {error}") from error
    if not isinstance(profile, dict) or profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise RepositoryAuditError(f"profile must use {PROFILE_SCHEMA_VERSION}")
    required = {"case_id", "repository", "scope", "objectives", "flow", "runtime"}
    if set(profile) != required | {"schema_version"} or profile.get("case_id") != case_id:
        raise RepositoryAuditError("profile fields or case_id do not match the built-in case")
    repository = _object(profile.get("repository"), "profile repository")
    _exact_keys(repository, {"name", "url", "branch", "commit", "license"}, "profile repository")
    for field in ("name", "url", "branch"):
        _nonempty_string(repository.get(field), f"profile repository.{field}")
    if re.fullmatch(r"https://github\.com/[^/]+/[^/]+/?", repository["url"]) is None:
        raise RepositoryAuditError("profile repository.url must identify a GitHub repository")
    _sha(repository.get("commit"), "profile repository.commit")
    license_data = _object(repository.get("license"), "profile repository.license")
    _exact_keys(license_data, {"spdx", "path", "blob_sha"}, "profile repository.license")
    for field in ("spdx", "path"):
        _nonempty_string(license_data.get(field), f"profile repository.license.{field}")
    _safe_profile_path(license_data["path"], "profile repository.license.path")
    _sha(license_data.get("blob_sha"), "profile repository.license.blob_sha")

    scope = _object(profile.get("scope"), "profile scope")
    _exact_keys(
        scope,
        {"include", "exclude", "prohibited", "extensions", "max_file_bytes"},
        "profile scope",
    )
    for field in ("include", "exclude", "prohibited"):
        values = scope.get(field)
        if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
            raise RepositoryAuditError(f"profile scope.{field} must be a string array")
        if len(values) != len(set(values)):
            raise RepositoryAuditError(f"profile scope.{field} cannot contain duplicates")
        for value in values:
            _safe_profile_path(value, f"profile scope.{field}")
    extensions = scope.get("extensions")
    if (
        not isinstance(extensions, list)
        or not extensions
        or len(extensions) != len(set(extensions))
        or not all(
            isinstance(item, str) and re.fullmatch(r"\.[a-z0-9]+", item)
            for item in extensions
        )
    ):
        raise RepositoryAuditError("profile scope.extensions must contain unique lowercase extensions")
    max_file_bytes = scope.get("max_file_bytes")
    if (
        not isinstance(max_file_bytes, int)
        or isinstance(max_file_bytes, bool)
        or not 1 <= max_file_bytes <= 10485760
    ):
        raise RepositoryAuditError("profile scope.max_file_bytes must be from 1 to 10485760")

    objectives = profile.get("objectives")
    if not isinstance(objectives, list) or not objectives:
        raise RepositoryAuditError("profile objectives must be a non-empty array")
    for number, objective_value in enumerate(objectives):
        objective = _object(objective_value, f"profile objectives[{number}]")
        _exact_keys(
            objective,
            {
                "title",
                "required_categories",
                "pass_claim",
                "unknown_claim",
                "impact",
                "recommendation",
                "localization",
            },
            f"profile objectives[{number}]",
        )
        for field in ("title", "pass_claim", "unknown_claim", "recommendation"):
            _nonempty_string(objective.get(field), f"profile objectives[{number}].{field}")
        categories = objective.get("required_categories")
        if (
            not isinstance(categories, list)
            or not categories
            or len(categories) != len(set(categories))
            or not all(category in _CATEGORIES for category in categories)
        ):
            raise RepositoryAuditError(
                f"profile objectives[{number}].required_categories contains an unknown category"
            )
        impact = _object(objective.get("impact"), f"profile objectives[{number}].impact")
        _exact_keys(impact, {"level"}, f"profile objectives[{number}].impact")
        if impact.get("level") not in {"high", "medium", "low"}:
            raise RepositoryAuditError(f"profile objectives[{number}].impact.level is invalid")
        localization = _object(
            objective.get("localization"), f"profile objectives[{number}].localization"
        )
        _exact_keys(
            localization, {"zh-CN"}, f"profile objectives[{number}].localization"
        )
        chinese = _object(
            localization.get("zh-CN"),
            f"profile objectives[{number}].localization.zh-CN",
        )
        _exact_keys(
            chinese,
            {"title", "pass_claim", "unknown_claim", "recommendation"},
            f"profile objectives[{number}].localization.zh-CN",
        )
        for field in ("title", "pass_claim", "unknown_claim", "recommendation"):
            _nonempty_string(
                chinese.get(field),
                f"profile objectives[{number}].localization.zh-CN.{field}",
            )

    flow = _object(profile.get("flow"), "profile flow")
    _exact_keys(flow, {"nodes"}, "profile flow")
    nodes = flow.get("nodes")
    if not isinstance(nodes, list) or len(nodes) < 2:
        raise RepositoryAuditError("profile flow.nodes must contain at least two nodes")
    for number, node_value in enumerate(nodes):
        node = _object(node_value, f"profile flow.nodes[{number}]")
        _exact_keys(
            node, {"label", "label_zh_cn", "category"}, f"profile flow.nodes[{number}]"
        )
        _nonempty_string(node.get("label"), f"profile flow.nodes[{number}].label")
        _nonempty_string(
            node.get("label_zh_cn"), f"profile flow.nodes[{number}].label_zh_cn"
        )
        if node.get("category") not in _CATEGORIES:
            raise RepositoryAuditError(f"profile flow.nodes[{number}].category is invalid")

    runtime = _object(profile.get("runtime"), "profile runtime")
    _exact_keys(runtime, {"max_seconds", "starts_when", "includes", "excludes"}, "profile runtime")
    if runtime != {
        "max_seconds": 900,
        "starts_when": "local_repository_exists_and_dependencies_are_installed",
        "includes": [
            "evidence_collection",
            "rule_analysis",
            "artifact_generation",
            "html_svg_rendering",
        ],
        "excludes": ["clone", "dependency_install", "llm_network", "manual_review"],
    }:
        raise RepositoryAuditError("profile runtime must use the frozen 15-minute contract")
    if any(_matches("enterprise/example", pattern) for pattern in scope["include"]) and case_id == "openhands":
        raise RepositoryAuditError("OpenHands enterprise content cannot be included")
    if case_id == "openhands" and not any(_matches("enterprise/example", pattern) for pattern in scope["prohibited"]):
        raise RepositoryAuditError("OpenHands profile must prohibit enterprise/**")
    _verify_lock_file(path, case_id, repository)
    return profile


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RepositoryAuditError(f"{name} must be an object")
    return value


def _exact_keys(value: dict[str, Any], keys: set[str], name: str) -> None:
    if set(value) != keys:
        raise RepositoryAuditError(f"{name} fields do not match the v1 schema")


def _nonempty_string(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise RepositoryAuditError(f"{name} must be a non-empty string")


def _sha(value: Any, name: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise RepositoryAuditError(f"{name} must be a full lowercase SHA")


def _safe_profile_path(value: str, name: str) -> None:
    if Path(value).is_absolute() or ".." in Path(value).parts:
        raise RepositoryAuditError(f"{name} cannot escape the repository root")


def _verify_lock_file(profile_path: Path, case_id: str, repository: dict[str, Any]) -> None:
    """Keep the published lock and executable profile from drifting."""
    if profile_path.parent.name != "profiles":
        return
    lock_path = profile_path.parent.parent / "cases" / case_id / "repository-lock.json"
    if not lock_path.is_file():
        raise RepositoryAuditError(f"repository lock is missing for case: {case_id}")
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RepositoryAuditError(f"invalid repository lock: {error}") from error
    expected = {
        "repository": repository["url"].removeprefix("https://github.com/").rstrip("/"),
        "url": repository["url"],
        "commit": repository["commit"],
        "branch": repository["branch"],
        "license": repository["license"],
    }
    if not all(lock.get(key) == value for key, value in expected.items()):
        raise RepositoryAuditError(f"repository lock and profile disagree for case: {case_id}")


def _repository_lock_evidence(root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    head = _git(root, "rev-parse", "HEAD")
    dirty = _git(root, "status", "--porcelain", "--untracked-files=all")
    expected = profile["repository"]["commit"]
    return {
        "status": "PASS" if head == expected and dirty == "" else "FAIL",
        "head": head,
        "expected": expected,
        "clean": dirty == "",
        "evidence": [{"path": ".git", "line": None, "detail": f"HEAD={head or 'UNKNOWN'}"}],
    }


def _license_boundary_evidence(
    root: Path, profile: dict[str, Any], files: list[CollectedFile]
) -> dict[str, Any]:
    license_data = profile["repository"]["license"]
    license_path = root / license_data["path"]
    actual_blob = _git(root, "hash-object", "--", license_data["path"]) if license_path.is_file() else None
    prohibited = profile["scope"]["prohibited"]
    leaked = [item.path for item in files if any(_matches(item.path, pattern) for pattern in prohibited)]
    expected_blob = license_data["blob_sha"]
    status = "PASS" if actual_blob == expected_blob and not leaked else "FAIL"
    return {
        "status": status,
        "actual_blob": actual_blob,
        "expected_blob": expected_blob,
        "prohibited_paths_collected": leaked,
        "evidence": [
            {
                "path": license_data["path"],
                "line": 1,
                "detail": f"git_blob={actual_blob or 'UNKNOWN'}; expected={expected_blob}",
            }
        ],
    }


def _collect_files(
    root: Path, profile: dict[str, Any], started: float
) -> tuple[list[CollectedFile], list[dict[str, str]]]:
    scope = profile["scope"]
    extensions = tuple(scope["extensions"])
    max_bytes = int(scope["max_file_bytes"])
    max_seconds = float(profile["runtime"]["max_seconds"])
    candidates: set[Path] = set()
    skipped: list[dict[str, str]] = []
    for pattern in scope["include"]:
        prefix = pattern[:-3].rstrip("/") if pattern.endswith("/**") else pattern.rstrip("/")
        target = root / prefix
        if target.is_symlink():
            skipped.append({"path": prefix, "reason": "symbolic_link"})
            continue
        if target.is_file():
            candidates.add(target)
        elif target.is_dir():
            candidates.update(target.rglob("*"))
    collected: list[CollectedFile] = []
    for path in sorted(candidates):
        if time.monotonic() - started > max_seconds:
            raise RepositoryAuditError(f"repository audit exceeded its {max_seconds:g}s runtime budget")
        relative_path = path.relative_to(root)
        has_symlink_ancestor = any(
            (root / Path(*relative_path.parts[:index])).is_symlink()
            for index in range(1, len(relative_path.parts) + 1)
        )
        try:
            path.resolve(strict=True).relative_to(root)
        except (FileNotFoundError, ValueError):
            has_symlink_ancestor = True
        if has_symlink_ancestor or path.is_symlink() or not path.is_file():
            if has_symlink_ancestor or path.is_symlink():
                skipped.append({"path": relative_path.as_posix(), "reason": "symbolic_link"})
            continue
        relative = relative_path.as_posix()
        if not any(_matches(relative, pattern) for pattern in scope["include"]):
            continue
        if any(_matches(relative, pattern) for pattern in scope["exclude"] + scope["prohibited"]):
            continue
        if extensions and path.suffix.lower() not in extensions:
            continue
        size = path.stat().st_size
        if size > max_bytes:
            skipped.append({"path": relative, "reason": "size_limit"})
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": relative, "reason": "not_utf8"})
            continue
        category_lines = _categorize(relative, text)
        collected.append(
            CollectedFile(
                path=relative,
                sha256=hashlib.sha256(raw).hexdigest(),
                size=size,
                lines=text.count("\n") + (0 if not text or text.endswith("\n") else 1),
                categories=tuple(sorted(category_lines)),
                category_lines=category_lines,
            )
        )
    return collected, skipped


def _categorize(path: str, text: str) -> dict[str, int]:
    lowered_path = path.casefold()
    path_parts = tuple(Path(lowered_path).parts)
    filename = Path(lowered_path).name
    result: dict[str, int] = {}
    if not text.strip():
        return result
    tree: ast.AST | None = None
    if lowered_path.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            tree = None
        if tree is not None and not any(
            not (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
            and not isinstance(node, ast.Pass)
            for node in tree.body
        ):
            return result

    path_rules = {
        "agent": {"agent", "agents", "app_conversation"},
        "tool": {"tool", "tools"},
        "runtime": {
            "runtime",
            "controller",
            "runner",
            "runners",
            "environment",
            "sandbox",
            "app_server",
        },
        "verification": {"test", "tests", "eval", "evaluation"},
        "trajectory": {"trajectory", "trajectories", "event", "events"},
        "feedback": {"evaluation"},
        "isolation": {"sandbox"},
    }
    for category, segments in path_rules.items():
        if any(part in segments for part in path_parts):
            result[category] = 1
    if filename.startswith("test_") or filename.endswith("_test.py"):
        result["verification"] = 1
    if filename in {"agent.py", "agents.py"} or filename.startswith("agent_") or filename.endswith("_agent.py"):
        result["agent"] = 1
    if filename in {"tool.py", "tools.py"} or filename.startswith("tool_") or filename.endswith("_tool.py"):
        result["tool"] = 1
    if filename in {"runner.py", "runners.py", "runtime.py", "controller.py"}:
        result["runtime"] = 1
    if filename.endswith(".traj"):
        result["trajectory"] = 1

    if tree is not None:
        identifiers: list[tuple[str, int]] = []
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Name, ast.Attribute, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                name = (
                    getattr(node, "id", None)
                    or getattr(node, "attr", None)
                    or getattr(node, "name", None)
                )
                if isinstance(name, str):
                    identifiers.append((name.casefold(), getattr(node, "lineno", 1)))
            if isinstance(node, (ast.Try, ast.ExceptHandler)):
                result.setdefault("recovery", getattr(node, "lineno", 1))
        for category, markers in _IDENTIFIER_MARKERS.items():
            for identifier, line_number in identifiers:
                tokens = {
                    token for token in re.split(r"[^a-z0-9]+|_", identifier) if token
                }
                if any(
                    marker in tokens or identifier.startswith(marker + "_")
                    for marker in markers
                ):
                    result.setdefault(category, line_number)
                    break
        if "verification" not in result and any(
            isinstance(node, ast.ClassDef)
            and (
                node.name.casefold() == "agent"
                or node.name.casefold().endswith("agent")
                or node.name.casefold().endswith("_agent")
            )
            for node in ast.walk(tree)
        ):
            result["local_agent_definition"] = 1

    if filename == "pyproject.toml" and re.search(
        r"openhands-(?:agent-server|sdk)", text, flags=re.IGNORECASE
    ):
        result["external"] = 1
    if path.endswith((".md", ".rst")) and re.search(
        r"\b(requirement|must|should)\b", text, flags=re.IGNORECASE
    ):
        result["requirement"] = 1
    return result


def _category_index(files: list[CollectedFile]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {category: [] for category in _CATEGORIES}
    for item in files:
        for category in item.categories:
            index.setdefault(category, []).append(
                {
                    "path": item.path,
                    "line": item.category_lines[category],
                    "detail": f"category={category}; sha256={item.sha256}",
                }
            )
    return index


def _build_findings(
    profile: dict[str, Any],
    lock: dict[str, Any],
    boundary: dict[str, Any],
    categories: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    findings = [
        _finding(
            "AET-REPO-001",
            "Repository revision is reproducibly locked",
            lock["status"],
            "ERROR" if lock["status"] == "FAIL" else "INFO",
            lock["evidence"],
            "high",
            "A mismatched or dirty checkout makes line-level evidence non-reproducible.",
            "Checkout the locked commit and remove local repository changes.",
        ),
        _finding(
            "AET-REPO-002",
            "License and prohibited-path boundary is enforced",
            boundary["status"],
            "ERROR" if boundary["status"] == "FAIL" else "INFO",
            boundary["evidence"],
            "high",
            "A license mismatch or prohibited path in the evidence set invalidates publication.",
            "Restore the locked license file and keep prohibited paths outside every include pattern.",
        ),
    ]
    for index, objective in enumerate(profile["objectives"], 3):
        required = objective["required_categories"]
        missing = [category for category in required if not categories.get(category)]
        evidence = []
        for category in required:
            evidence.extend(categories.get(category, [])[:2])
        if not evidence:
            evidence = [{"path": ".", "line": None, "detail": "No matching static evidence in audited scope."}]
        status = "PASS" if not missing else "UNKNOWN"
        title = objective["title"]
        detail = (
            objective["pass_claim"]
            if status == "PASS"
            else f"{objective['unknown_claim']} Missing categories: {', '.join(missing)}."
        )
        findings.append(
            _finding(
                f"AET-REPO-{index:03d}",
                title,
                status,
                "INFO" if status == "PASS" else "WARN",
                evidence[:8],
                objective["impact"]["level"],
                detail,
                objective["recommendation"],
            )
        )
    return findings


def _finding(
    identifier: str,
    title: str,
    status: str,
    severity: str,
    evidence: list[dict[str, Any]],
    impact_level: str,
    impact_description: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "title": title,
        "status": status,
        "severity": severity,
        "evidence": evidence,
        "impact": {"level": impact_level, "description": impact_description},
        "recommendation": recommendation,
        "rule_version": "1",
    }


def _finding_summary(findings: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"PASS": 0, "FAIL": 0, "UNKNOWN": 0, "NOT_APPLICABLE": 0}
    for finding in findings:
        summary[finding["status"]] += 1
    return summary


def _impact_level(level: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}[level]


def _localized_result(
    profile: dict[str, Any],
    categories: dict[str, list[dict[str, Any]]],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Project canonical findings into a Simplified Chinese narrative."""
    localized = copy.deepcopy(result)
    localized["disclaimer"] = (
        "本报告对公开上游仓库进行静态分析，不重新发布源码，也不代表与上游项目"
        "存在隶属、合作或认可关系。"
    )
    fixed = {
        "AET-REPO-001": {
            "title": "仓库版本已进行可复现锁定",
            "impact": "若检出版本不匹配或工作树不干净，行级证据将无法复现。",
            "recommendation": "切换到锁定 commit，并清理本地仓库改动后重新审查。",
        },
        "AET-REPO-002": {
            "title": "许可证及禁止路径边界已落实",
            "impact": "若 License 不匹配或证据集包含禁止路径，当前报告将不满足发布条件。",
            "recommendation": "恢复锁定的 License 文件，并确保所有包含规则排除禁止路径。",
        },
    }
    for index, finding in enumerate(localized["findings"]):
        identifier = finding["id"]
        if identifier in fixed:
            translation = fixed[identifier]
            finding["title"] = translation["title"]
            finding["impact"]["description"] = translation["impact"]
            finding["recommendation"] = translation["recommendation"]
            continue
        objective = profile["objectives"][index - 2]
        translation = objective["localization"]["zh-CN"]
        finding["title"] = translation["title"]
        if finding["status"] == "PASS":
            finding["impact"]["description"] = translation["pass_claim"]
        else:
            missing = [
                category
                for category in objective["required_categories"]
                if not categories.get(category)
            ]
            category_names = {
                "agent": "Agent",
                "tool": "工具",
                "runtime": "运行时",
                "verification": "验证",
                "trajectory": "执行轨迹",
                "permission": "权限",
                "recovery": "恢复",
                "feedback": "反馈",
                "isolation": "隔离",
                "requirement": "需求",
                "external": "外部依赖",
                "local_agent_definition": "本地 Agent 核心定义",
            }
            suffix = "、".join(category_names[item] for item in missing)
            finding["impact"]["description"] = (
                f"{translation['unknown_claim']}缺失证据类别：{suffix}。"
            )
        finding["recommendation"] = translation["recommendation"]
    return localized


def _repository_summary(result: dict[str, Any], locale: str) -> str:
    repository = result["repository"]
    scope = result["scope"]
    summary = result["summary"]
    if locale == "zh-CN":
        return "\n".join(
            [
                f"# {repository['name']} 仓库审查摘要",
                "",
                f"- 案例：`{repository['case_id']}`",
                f"- 上游仓库：`{repository['url']}`",
                f"- Commit：`{repository['commit']}`",
                f"- License：`{repository['license']['spdx']}`",
                f"- 证据文件：{scope['files_collected']}",
                f"- 审查项：PASS {summary['PASS']} · FAIL {summary['FAIL']} · UNKNOWN {summary['UNKNOWN']}",
                f"- 运行时间：{result['runtime']['total_seconds']:.3f}s / {result['runtime']['max_seconds']:.0f}s",
                f"- 发布审核：`{result['review']['status']}`",
                "",
                result["disclaimer"],
                "",
            ]
        )
    return "\n".join(
        [
            f"# {repository['name']} Repository Audit Summary",
            "",
            f"- Case: `{repository['case_id']}`",
            f"- Upstream: `{repository['url']}`",
            f"- Commit: `{repository['commit']}`",
            f"- License: `{repository['license']['spdx']}`",
            f"- Evidence files: {scope['files_collected']}",
            f"- Findings: PASS {summary['PASS']} · FAIL {summary['FAIL']} · UNKNOWN {summary['UNKNOWN']}",
            f"- Runtime: {result['runtime']['total_seconds']:.3f}s / {result['runtime']['max_seconds']:.0f}s",
            f"- Publication review: `{result['review']['status']}`",
            "",
            result["disclaimer"],
            "",
        ]
    )


def _markdown_report(result: dict[str, Any], locale: str) -> str:
    repository = result["repository"]
    scope = result["scope"]
    if locale == "zh-CN":
        lines = [
            f"# AET 仓库审查 — {repository['name']}",
            "",
            "## 执行摘要",
            "",
            f"- 仓库：`{repository['url']}`",
            f"- Commit：`{repository['commit']}`",
            f"- 审查范围：{len(scope['include'])} 项包含规则，{len(scope['exclude'])} 项排除规则",
            f"- 已采集证据：{scope['files_collected']} 个文件",
            f"- 运行时间：{result['runtime']['total_seconds']:.3f}s",
            f"- 维护者审核：`{result['review']['status']}`",
            "",
            "本报告记录的是静态工程观察，不构成缺陷认定或安全漏洞报告。",
            "",
            "## 架构视图",
            "",
            "![Agent 流程](diagrams/agent-flow.svg)",
            "",
            "## 证据链",
            "",
            "![证据链](diagrams/evidence-chain.svg)",
            "",
            "## 工程观察",
            "",
        ]
    else:
        lines = [
            f"# AET Repository Audit — {repository['name']}",
            "",
            "## Executive Summary",
            "",
            f"- Repository: `{repository['url']}`",
            f"- Commit: `{repository['commit']}`",
            f"- Audit scope: {len(scope['include'])} include patterns, {len(scope['exclude'])} exclusions",
            f"- Evidence collected: {scope['files_collected']} files",
            f"- Runtime: {result['runtime']['total_seconds']:.3f}s",
            f"- Maintainer review: `{result['review']['status']}`",
            "",
            "This is a static engineering observation, not a defect or security-vulnerability report.",
            "",
            "## Architecture View",
            "",
            "![Agent flow](diagrams/agent-flow.svg)",
            "",
            "## Evidence Map",
            "",
            "![Evidence chain](diagrams/evidence-chain.svg)",
            "",
            "## Findings",
            "",
        ]
    for finding in result["findings"]:
        if locale == "zh-CN":
            lines.extend(
                [
                    f"### {finding['id']} — {finding['title']}",
                    "",
                    f"- 状态：`{finding['status']}`",
                    f"- 严重程度：`{finding['severity']}`",
                    f"- 影响：`{_impact_level(finding['impact']['level'])}` — {finding['impact']['description']}",
                    "- 证据：",
                ]
            )
        else:
            lines.extend(
                [
                    f"### {finding['id']} — {finding['title']}",
                    "",
                    f"- Status: `{finding['status']}`",
                    f"- Severity: `{finding['severity']}`",
                    f"- Impact: `{finding['impact']['level']}` — {finding['impact']['description']}",
                    "- Evidence:",
                ]
            )
        for evidence in finding["evidence"]:
            location = evidence["path"] + (f":{evidence['line']}" if evidence.get("line") else "")
            lines.append(f"  - `{location}` — {evidence.get('detail', '')}")
        label = "建议：" if locale == "zh-CN" else "Recommendation:"
        lines.extend([f"- {label} {finding['recommendation']}", ""])
    boundary = "发布边界" if locale == "zh-CN" else "Publication Boundary"
    lines.extend([f"## {boundary}", "", result["disclaimer"], ""])
    return "\n".join(lines)


def _html_report(result: dict[str, Any], locale: str) -> str:
    repository = result["repository"]
    chinese = locale == "zh-CN"
    finding_cards = []
    for finding in result["findings"]:
        evidence = "".join(
            f"<li><code>{html.escape(item['path'])}{':' + str(item['line']) if item.get('line') else ''}</code>"
            f" — {html.escape(item.get('detail', ''))}</li>"
            for item in finding["evidence"]
        )
        severity_label = "严重程度" if chinese else "Severity"
        impact_label = "影响级别" if chinese else "Impact"
        impact_value = (
            f"{_impact_level(finding['impact']['level'])}（{finding['impact']['level']}）"
            if chinese
            else finding["impact"]["level"]
        )
        label_separator = "：" if chinese else ":"
        finding_cards.append(
            "<article class=\"finding\">"
            f"<p class=\"state {finding['status'].lower()}\">{html.escape(finding['status'])}</p>"
            f"<h3>{html.escape(finding['id'])} · {html.escape(finding['title'])}</h3>"
            f"<p class=\"meta\">{severity_label}{label_separator} <code>{html.escape(finding['severity'])}</code>"
            f" · {impact_label}{label_separator} <code>{html.escape(impact_value)}</code></p>"
            f"<p>{html.escape(finding['impact']['description'])}</p><ul>{evidence}</ul>"
            f"<p><strong>{'建议：' if chinese else 'Recommendation:'}</strong> {html.escape(finding['recommendation'])}</p></article>"
        )
    page_title = "AET 仓库审查" if chinese else "AET Repository Audit"
    files_label = "个证据文件" if chinese else "evidence files"
    review_label = "审核" if chinese else "review"
    flow_title = "Agent 流程" if chinese else "Agent Flow"
    flow_alt = "由 Profile 定义的 Agent 流程证据" if chinese else "Profile-directed agent flow evidence"
    chain_title = "证据链" if chinese else "Evidence Chain"
    chain_alt = "从需求到验证的证据链" if chinese else "Requirement to verification evidence chain"
    observations = "工程观察" if chinese else "Engineering Observations"
    return f"""<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{page_title} — {html.escape(repository['name'])}</title>
<style>
:root{{--bg:#0b1020;--panel:#121a2d;--text:#e7edf8;--muted:#9fb0ca;--green:#67e8a5;--amber:#fbbf6b;--red:#fb7185}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,sans-serif}}
main{{max-width:1080px;min-width:0;margin:auto;padding:48px 24px}}header,.finding,.visual{{min-width:0;background:var(--panel);border:1px solid #26334f;border-radius:16px;padding:24px;margin:18px 0}}
h1{{font-size:clamp(2rem,5vw,4rem);line-height:1.05;overflow-wrap:anywhere}}code{{color:#b7c9ff;overflow-wrap:anywhere;word-break:break-word}}ul{{padding-left:1.3rem}}li{{min-width:0;overflow-wrap:anywhere}}.meta{{color:var(--muted)}}.state{{font-weight:800;letter-spacing:.08em}}
.pass{{color:var(--green)}}.unknown{{color:var(--amber)}}.fail{{color:var(--red)}}img{{width:100%;height:auto}}small{{color:var(--muted)}}
</style></head><body><main>
<header><small>AET REPOSITORY AUDIT SHOWCASE</small><h1>{html.escape(repository['name'])}</h1>
<p>Commit <code>{html.escape(repository['commit'])}</code></p>
<p>{result['scope']['files_collected']} {files_label} · {result['runtime']['total_seconds']:.3f}s · {review_label} {result['review']['status']}</p></header>
<section class="visual"><h2>{flow_title}</h2><img src="diagrams/agent-flow.svg" alt="{flow_alt}"></section>
<section class="visual"><h2>{chain_title}</h2><img src="diagrams/evidence-chain.svg" alt="{chain_alt}"></section>
<section><h2>{observations}</h2>{''.join(finding_cards)}</section>
<footer><small>{html.escape(result['disclaimer'])}</small></footer>
</main></body></html>
"""


def _agent_flow_svg(
    profile: dict[str, Any], categories: dict[str, list[dict[str, Any]]], locale: str
) -> str:
    nodes = profile["flow"]["nodes"]
    width = max(760, 180 * len(nodes))
    margin = 30
    box_width = 130
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="230" viewBox="0 0 {width} 230" role="img" aria-labelledby="title desc">',
        f'<title id="title">{"由 Profile 定义的 Agent 流程" if locale == "zh-CN" else "Profile-directed Agent Flow"}</title>',
        f'<desc id="desc">{"实线节点具有匹配的静态仓库证据；虚线节点尚未得到证明。" if locale == "zh-CN" else "Solid nodes have matching static repository evidence; dashed nodes remain unproven."}</desc>',
        '<rect width="100%" height="100%" fill="#0b1020"/>',
    ]
    spacing = (width - (2 * margin) - box_width) / max(1, len(nodes) - 1)
    for index, node in enumerate(nodes):
        x = margin + index * spacing
        if index:
            previous_x = margin + (index - 1) * spacing
            parts.append(f'<path d="M {previous_x + box_width} 110 L {x} 110" stroke="#667899" stroke-width="2"/>')
        present = bool(categories.get(node["category"]))
        stroke = "#67e8a5" if present else "#fbbf6b"
        dash = "" if present else ' stroke-dasharray="7 6"'
        parts.extend(
            [
                f'<rect x="{x}" y="70" width="{box_width}" height="80" rx="12" fill="#121a2d" stroke="{stroke}" stroke-width="2"{dash}/>',
                f'<text x="{x + (box_width / 2)}" y="105" text-anchor="middle" fill="#e7edf8" font-family="system-ui" font-size="14">{html.escape(node["label_zh_cn"] if locale == "zh-CN" else node["label"])}</text>',
                f'<text x="{x + (box_width / 2)}" y="129" text-anchor="middle" fill="{stroke}" font-family="system-ui" font-size="11">{("已有证据" if present else "未知") if locale == "zh-CN" else ("EVIDENCED" if present else "UNKNOWN")}</text>',
            ]
        )
    parts.append("</svg>\n")
    return "".join(parts)


def _evidence_chain_svg(
    categories: dict[str, list[dict[str, Any]]], locale: str
) -> str:
    chain_labels = {
        "Requirement": "需求",
        "Implementation": "实现",
        "Execution": "执行",
        "Verification": "验证",
    }
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="230" viewBox="0 0 900 230" role="img" aria-labelledby="title desc">',
        f'<title id="title">{"证据链" if locale == "zh-CN" else "Evidence Chain"}</title>',
        f'<desc id="desc">{"需求、实现、执行与验证四个阶段的证据状态。" if locale == "zh-CN" else "Requirement, implementation, execution, and verification evidence states."}</desc>',
        '<rect width="100%" height="100%" fill="#0b1020"/>',
    ]
    for index, (label, required) in enumerate(_EVIDENCE_CHAIN):
        x = 35 + index * 215
        present = any(categories.get(category) for category in required)
        stroke = "#67e8a5" if present else "#fbbf6b"
        if index:
            parts.append(f'<path d="M {x - 55} 110 L {x - 5} 110" stroke="#667899" stroke-width="2"/>')
        parts.extend(
            [
                f'<rect x="{x}" y="65" width="160" height="90" rx="12" fill="#121a2d" stroke="{stroke}" stroke-width="2"/>',
                f'<text x="{x + 80}" y="105" text-anchor="middle" fill="#e7edf8" font-family="system-ui" font-size="15">{chain_labels[label] if locale == "zh-CN" else label}</text>',
                f'<text x="{x + 80}" y="130" text-anchor="middle" fill="{stroke}" font-family="system-ui" font-size="11">{("已有证据" if present else "未知") if locale == "zh-CN" else ("EVIDENCED" if present else "UNKNOWN")}</text>',
            ]
        )
    parts.append("</svg>\n")
    return "".join(parts)


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)


def _git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def _safe_output_path(output: Path) -> Path:
    candidate = output if output.is_absolute() else Path.cwd() / output
    if candidate.is_symlink():
        raise RepositoryAuditError("output directory cannot be a symbolic link")
    return candidate.parent.resolve() / candidate.name


def _render_bundle(
    profile: dict[str, Any],
    categories: dict[str, list[dict[str, Any]]],
    manifest: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, str]:
    chinese_result = _localized_result(profile, categories, result)
    bundle = {
        "evidence_manifest.json": json.dumps(
            manifest, indent=2, ensure_ascii=False, sort_keys=True
        )
        + "\n",
        "findings.json": json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
        + "\n",
        "en/repository-summary.md": _repository_summary(result, "en"),
        "en/audit-report.md": _markdown_report(result, "en"),
        "en/audit-report.html": _html_report(result, "en"),
        "en/diagrams/agent-flow.svg": _agent_flow_svg(profile, categories, "en"),
        "en/diagrams/evidence-chain.svg": _evidence_chain_svg(categories, "en"),
        "zh-CN/repository-summary.md": _repository_summary(chinese_result, "zh-CN"),
        "zh-CN/audit-report.md": _markdown_report(chinese_result, "zh-CN"),
        "zh-CN/audit-report.html": _html_report(chinese_result, "zh-CN"),
        "zh-CN/diagrams/agent-flow.svg": _agent_flow_svg(
            profile, categories, "zh-CN"
        ),
        "zh-CN/diagrams/evidence-chain.svg": _evidence_chain_svg(
            categories, "zh-CN"
        ),
    }
    return bundle


def _replace_bundle(output: Path, bundle: dict[str, str]) -> None:
    """Replace the complete bilingual artifact directory as one recoverable bundle."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    backup = output.parent / f".{output.name}.backup"
    try:
        for relative, value in bundle.items():
            _atomic_text(temporary / relative, value)
        if backup.exists() or backup.is_symlink():
            raise RepositoryAuditError(f"stale audit bundle backup blocks output: {backup}")
        if output.exists() or output.is_symlink():
            if output.is_symlink() or not output.is_dir():
                raise RepositoryAuditError("output path must be a real directory")
            os.replace(output, backup)
        try:
            os.replace(temporary, output)
        except BaseException:
            if backup.exists():
                os.replace(backup, output)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def _measure_bundle_write(output: Path, bundle: dict[str, str]) -> None:
    """Exercise complete artifact rendering and disk writes without publishing."""
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.measure.", dir=output.parent))
    try:
        for relative, value in bundle.items():
            _atomic_text(temporary / relative, value)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
