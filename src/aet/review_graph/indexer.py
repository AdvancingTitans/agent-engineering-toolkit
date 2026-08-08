"""Dependency-free Python structure indexing for bounded code review."""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aet.evidence import workspace_snapshot

from .errors import ReviewGraphError
from .model import CODE_GRAPH_SCHEMA, stable_id
from .validator import validate_code_graph


DEFAULT_MAX_FILES = 2_000
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
_SKIP_PARTS = {".git", ".venv", ".aet", "build", "dist", "node_modules", "__pycache__"}
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass
class _Definition:
    node: dict[str, Any]
    parent_id: str


@dataclass
class _PendingRelation:
    source_id: str
    name: str
    path: str
    line: int
    kind: str
    heuristic: bool = False


@dataclass
class _ParsedFile:
    path: str
    file_id: str
    file_hash: str
    changed_lines: set[int]
    definitions: list[_Definition] = field(default_factory=list)
    pending: list[_PendingRelation] = field(default_factory=list)
    imports: list[tuple[str, int]] = field(default_factory=list)
    dynamic_changed_calls: int = 0


class _Visitor(ast.NodeVisitor):
    def __init__(self, parsed: _ParsedFile) -> None:
        self.parsed = parsed
        self.stack: list[tuple[str, str]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        identifier = self._definition(node, "class")
        for base in node.bases:
            name, heuristic = _call_name(base)
            if name:
                self.parsed.pending.append(
                    _PendingRelation(identifier, name, self.parsed.path, node.lineno, "INHERITS", heuristic)
                )
        self.stack.append((identifier, node.name))
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.parsed.imports.extend((alias.name, node.lineno) for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.parsed.imports.append((node.module, node.lineno))

    def visit_Call(self, node: ast.Call) -> None:
        if self.stack:
            name, heuristic = _call_name(node.func)
            if name:
                source_id = self.stack[-1][0]
                self.parsed.pending.append(
                    _PendingRelation(source_id, name, self.parsed.path, node.lineno, "CALLS", heuristic)
                )
                if heuristic and node.lineno in self.parsed.changed_lines:
                    self.parsed.dynamic_changed_calls += 1
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self.stack and self.stack[-1][1] and self.stack[-1][0].startswith("code:symbol"):
            parent_kind = next(
                (item.node["kind"] for item in self.parsed.definitions if item.node["id"] == self.stack[-1][0]),
                None,
            )
        else:
            parent_kind = None
        kind = "method" if parent_kind == "class" else "function"
        if node.name.startswith("test_") or Path(self.parsed.path).name.startswith("test_"):
            kind = "test"
        identifier = self._definition(node, kind)
        self.stack.append((identifier, node.name))
        self.generic_visit(node)
        self.stack.pop()

    def _definition(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> str:
        parent_names = [name for _, name in self.stack]
        qualified = ".".join([*parent_names, node.name])
        identifier = stable_id("code:symbol", self.parsed.path, qualified, kind)
        end_line = int(getattr(node, "end_lineno", node.lineno))
        changed = any(node.lineno <= line <= end_line for line in self.parsed.changed_lines)
        record = _node(
            identifier,
            kind,
            qualified,
            self.parsed.path,
            node.lineno,
            self.parsed.file_hash,
            {
                "path": self.parsed.path,
                "line": node.lineno,
                "end_line": end_line,
                "qualified_name": qualified,
                "simple_name": node.name,
                "changed": changed,
            },
            priority=95 if changed else 45,
        )
        parent_id = self.stack[-1][0] if self.stack else self.parsed.file_id
        self.parsed.definitions.append(_Definition(record, parent_id))
        return identifier


def build_code_graph(
    workspace: Path,
    base_ref: str,
    *,
    exclude_paths: tuple[str, ...] = (),
    max_files: int = DEFAULT_MAX_FILES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Build a deterministic Python symbol graph bound to one Git snapshot."""
    root = workspace.resolve()
    if not root.is_dir():
        raise ReviewGraphError("invalid_workspace", "workspace must be a directory")
    for name, value in (("max_files", max_files), ("max_bytes", max_bytes)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ReviewGraphError("invalid_argument", f"{name} must be a positive integer")
    _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    snapshot = _review_snapshot(root, exclude_paths)
    changed = _changed_paths(root, base_ref)
    candidates = _python_files(root)
    diagnostics: list[dict[str, Any]] = []
    if len(candidates) > max_files:
        diagnostics.append(_diagnostic("FILE_LIMIT", "UNKNOWN", f"Python file limit exceeded: {len(candidates)} > {max_files}"))
        candidates = candidates[:max_files]

    parsed_files: list[_ParsedFile] = []
    total_bytes = 0
    budget_exhausted = False
    for relative in candidates:
        path = root / relative
        raw = path.read_bytes()
        if total_bytes + len(raw) > max_bytes:
            diagnostics.append(_diagnostic("BYTE_LIMIT", "UNKNOWN", f"Python byte limit exceeded before {relative}", [relative]))
            budget_exhausted = True
            break
        total_bytes += len(raw)
        file_hash = hashlib.sha256(raw).hexdigest()
        changed_lines = _changed_lines(root, base_ref, relative, len(raw.splitlines())) if relative in changed else set()
        file_id = stable_id("code:file", relative)
        parsed = _ParsedFile(relative, file_id, file_hash, changed_lines)
        try:
            tree = ast.parse(raw, filename=relative)
        except (SyntaxError, ValueError) as error:
            diagnostics.append(
                _diagnostic(
                    "PYTHON_PARSE_ERROR",
                    "UNKNOWN",
                    f"Cannot parse {relative}: {error}",
                    [relative],
                )
            )
            parsed_files.append(parsed)
            continue
        _Visitor(parsed).visit(tree)
        if parsed.dynamic_changed_calls:
            diagnostics.append(
                _diagnostic(
                    "DYNAMIC_CALL_TARGET",
                    "UNKNOWN",
                    f"Changed lines in {relative} contain {parsed.dynamic_changed_calls} attribute call(s) whose runtime target is not proven.",
                    [relative],
                )
            )
        parsed_files.append(parsed)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    by_simple: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_module: dict[str, str] = {}
    kind_by_id: dict[str, str] = {}
    for parsed in parsed_files:
        changed_file = parsed.path in changed
        file_node = _node(
            parsed.file_id,
            "file",
            parsed.path,
            parsed.path,
            1,
            parsed.file_hash,
            {
                "path": parsed.path,
                "file_sha256": parsed.file_hash,
                "changed": changed_file,
                "language": "python",
            },
            priority=100 if changed_file else 40,
        )
        nodes.append(file_node)
        kind_by_id[parsed.file_id] = "file"
        by_module[_module_name(parsed.path)] = parsed.file_id
        for definition in parsed.definitions:
            nodes.append(definition.node)
            kind_by_id[definition.node["id"]] = definition.node["kind"]
            by_simple[definition.node["attributes"]["simple_name"]].append(definition.node)
            edges.append(
                _edge(
                    definition.parent_id,
                    definition.node["id"],
                    "CONTAINS",
                    "PASS",
                    "python_ast",
                    parsed.path,
                    definition.node["attributes"]["line"],
                    parsed.file_hash,
                    priority=80,
                )
            )

    for parsed in parsed_files:
        for module, line in parsed.imports:
            target = _resolve_module(module, by_module)
            if target is not None and target != parsed.file_id:
                edges.append(
                    _edge(parsed.file_id, target, "IMPORTS", "PASS", "python_ast", parsed.path, line, parsed.file_hash, priority=65)
                )
        for pending in parsed.pending:
            matches = by_simple.get(pending.name, [])
            if not matches:
                continue
            if len(matches) > 1:
                diagnostics.append(
                    _diagnostic(
                        "AMBIGUOUS_SYMBOL",
                        "UNKNOWN",
                        f"{pending.path}:{pending.line} has multiple possible targets named {pending.name}.",
                        [f"{pending.path}:{pending.line}"],
                    )
                )
                continue
            target = matches[0]
            relation = pending.kind
            state = "UNKNOWN" if pending.heuristic else "PASS"
            authority = "name_heuristic" if pending.heuristic else "python_ast"
            if pending.kind == "CALLS" and kind_by_id.get(pending.source_id) == "test":
                relation = "TESTS"
            elif pending.kind == "CALLS" and pending.heuristic:
                relation = "MAY_CALL"
            edges.append(
                _edge(
                    pending.source_id,
                    target["id"],
                    relation,
                    state,
                    authority,
                    pending.path,
                    pending.line,
                    parsed.file_hash,
                    priority=75 if state == "PASS" else 45,
                )
            )

    coverage_status = "UNKNOWN" if budget_exhausted or any(
        item["code"] in {"FILE_LIMIT", "BYTE_LIMIT", "PYTHON_PARSE_ERROR", "DYNAMIC_CALL_TARGET"}
        for item in diagnostics
    ) else "PASS"
    graph = {
        "schema_version": CODE_GRAPH_SCHEMA,
        "snapshot": snapshot,
        "index": {
            "language": "python",
            "base_ref": base_ref,
            "coverage_status": coverage_status,
            "file_count": sum(1 for node in nodes if node["kind"] == "file"),
            "symbol_count": sum(1 for node in nodes if node["kind"] != "file"),
            "indexed_bytes": total_bytes,
            "changed_paths": sorted(changed),
            "file_hashes": {
                parsed.path: parsed.file_hash for parsed in sorted(parsed_files, key=lambda item: item.path)
            },
        },
        "nodes": sorted(nodes, key=lambda item: item["id"]),
        "edges": _deduplicate_edges(edges),
        "diagnostics": sorted(diagnostics, key=lambda item: (item["code"], item["message"])),
    }
    return validate_code_graph(graph)


def _review_snapshot(root: Path, excluded: tuple[str, ...]) -> dict[str, Any]:
    raw = workspace_snapshot(root, excluded)
    if raw.get("status") != "PASS":
        raise ReviewGraphError("snapshot_unknown", str(raw.get("reason", "workspace snapshot unavailable")))
    return {
        "status": "PASS",
        "head_sha": raw["head_sha"],
        "worktree_digest": raw["worktree_digest"],
        "digest": raw["digest"],
        "tracked_worktree_sha256": raw["tracked_worktree_sha256"],
        "untracked_manifest_sha256": raw["untracked_manifest_sha256"],
        "intent_sha256": raw.get("intent_sha256"),
        "config_sha256": raw.get("config_sha256"),
    }


def _python_files(root: Path) -> list[str]:
    output = _git(root, "ls-files", "-co", "--exclude-standard", "--", "*.py")
    result = []
    for relative in output.splitlines():
        if not relative or any(part in _SKIP_PARTS for part in Path(relative).parts):
            continue
        candidate = root / relative
        if candidate.is_file() and not candidate.is_symlink():
            result.append(Path(relative).as_posix())
    return sorted(set(result))


def _changed_paths(root: Path, base_ref: str) -> set[str]:
    changed = set(
        line
        for line in _git(root, "diff", "--name-only", "--diff-filter=ACMR", base_ref, "--").splitlines()
        if line
    )
    changed.update(
        line for line in _git(root, "ls-files", "--others", "--exclude-standard").splitlines() if line
    )
    return changed


def _changed_lines(root: Path, base_ref: str, relative: str, line_count: int) -> set[int]:
    if relative in set(_git(root, "ls-files", "--others", "--exclude-standard").splitlines()):
        return set(range(1, line_count + 1))
    output = _git(root, "diff", "--unified=0", base_ref, "--", relative)
    lines: set[int] = set()
    for raw in output.splitlines():
        match = _HUNK.match(raw)
        if match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        lines.update(range(start, start + count))
    return lines


def _module_name(relative: str) -> str:
    path = relative[:-3] if relative.endswith(".py") else relative
    if path.endswith("/__init__"):
        path = path[: -len("/__init__")]
    return path.replace("/", ".")


def _resolve_module(module: str, modules: dict[str, str]) -> str | None:
    if module in modules:
        return modules[module]
    matches = [identifier for name, identifier in modules.items() if name.endswith("." + module)]
    return matches[0] if len(matches) == 1 else None


def _call_name(node: ast.AST) -> tuple[str | None, bool]:
    if isinstance(node, ast.Name):
        return node.id, False
    if isinstance(node, ast.Attribute):
        return node.attr, True
    return None, True


def _node(
    identifier: str,
    kind: str,
    text: str,
    path: str,
    line: int,
    file_hash: str,
    attributes: dict[str, Any],
    *,
    priority: int,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": kind,
        "state": "PASS",
        "authority": "python_ast",
        "text": text,
        "source_refs": [{"kind": "source", "ref": f"{path}:{line}#{file_hash}"}],
        "attributes": attributes,
        "mandatory": False,
        "priority": priority,
    }


def _edge(
    source: str,
    target: str,
    relation: str,
    state: str,
    authority: str,
    path: str,
    line: int,
    file_hash: str,
    *,
    priority: int,
) -> dict[str, Any]:
    return {
        "id": stable_id("code:edge", source, target, relation, path, line),
        "from": source,
        "to": target,
        "relation": relation,
        "state": state,
        "authority": authority,
        "source_refs": [{"kind": "source", "ref": f"{path}:{line}#{file_hash}"}],
        "attributes": {},
        "priority": priority,
    }


def _diagnostic(code: str, status: str, message: str, refs: list[str] | None = None) -> dict[str, Any]:
    return {"code": code, "status": status, "message": message, "refs": refs or []}


def _deduplicate_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {edge["id"]: edge for edge in edges}
    return [by_id[identifier] for identifier in sorted(by_id)]


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ReviewGraphError("git_error", detail or "Git command failed")
    return completed.stdout
