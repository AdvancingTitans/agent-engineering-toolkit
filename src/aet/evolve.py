"""Offline, evidence-linked repository archaeology for ``aet evolve``."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__

ISSUE_RE = re.compile(r"(?<!\w)#(\d+)\b")


class EvolveError(ValueError):
    """Raised when a requested evolution input is unsafe or malformed."""


def write_evolution_plan(root: Path, output: Path, question: str, *, remote: str = "none") -> Path:
    root = root.resolve()
    if not question.strip():
        raise EvolveError("question must be non-empty")
    data = {
        "schema_version": __version__, "report_kind": "evolution_plan", "generated_at": _timestamp(),
        "root": str(root), "question": question.strip(), "remote": remote,
        "sources": ["git-local", "docs-local"] + (["github-api"] if remote == "github" else []),
        "constraints": ["read-only", "no inferred author intent", "remote access is explicit"],
    }
    _write_json(output, data)
    return output


def collect_evolution(root: Path, output: Path, *, question: str, source_export: Path | None = None, remote: str = "none") -> Path:
    """Collect local Git/doc evidence, preserving every unavailable source as UNKNOWN."""
    root, output = root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    git = _collect_git(root)
    sources.extend(git["sources"])
    objects.extend(git["objects"])
    docs = _collect_docs(root)
    sources.extend(docs["sources"])
    objects.extend(docs["objects"])
    if source_export is not None:
        imported = _collect_export(source_export.resolve())
        sources.extend(imported["sources"])
        objects.extend(imported["objects"])
    if remote == "github":
        imported = _collect_github(root)
        sources.extend(imported["sources"])
        objects.extend(imported["objects"])
    if remote not in ("none", "github"):
        raise EvolveError(f"unsupported remote adapter: {remote}")
    manifest = {
        "schema_version": __version__, "report_kind": "evolution_manifest", "generated_at": _timestamp(),
        "root": str(root), "question": question.strip(), "remote": remote,
        "sources": sources, "objects": objects,
        "summary": _summary(sources),
    }
    path = output / "source-manifest.json"
    _write_json(path, manifest)
    return path


def build_evolution(manifest_path: Path, output: Path) -> Path:
    """Normalize manifest objects and create only explainable local links."""
    manifest = _read_json(manifest_path)
    if manifest.get("report_kind") != "evolution_manifest":
        raise EvolveError("build input must be an evolution_manifest")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    objects = manifest.get("objects")
    if not isinstance(objects, list):
        raise EvolveError("manifest objects must be a list")
    by_id = {item["id"]: item for item in objects if isinstance(item, dict) and isinstance(item.get("id"), str)}
    links: list[dict[str, Any]] = []
    for item in by_id.values():
        if item.get("kind") == "tag" and item.get("target") in by_id:
            links.append(_link(item["id"], item["target"], "annotates", "DIRECT", [item["source_id"]]))
        if item.get("kind") == "document":
            content = item.get("content", "")
            for tag in (candidate for candidate in by_id.values() if candidate.get("kind") == "tag"):
                if tag.get("name") and tag["name"] in content:
                    links.append(_link(item["id"], tag["id"], "mentions-version", "DIRECT", [item["source_id"], tag["source_id"]]))
        if item.get("kind") == "commit":
            for issue in ISSUE_RE.findall(item.get("subject", "")):
                issue_id = f"issue:{issue}"
                if issue_id in by_id:
                    links.append(_link(item["id"], issue_id, "mentions", "DIRECT", [item["source_id"], by_id[issue_id]["source_id"]]))
                else:
                    links.append(_link(item["id"], issue_id, "mentions", "CANDIDATE", [item["source_id"]], "No local Issue object establishes a direct relation."))
        if item.get("kind") == "pull_request":
            head = item.get("data", {}).get("head", {}).get("sha")
            target = f"commit:{head}" if isinstance(head, str) else None
            if target in by_id:
                links.append(_link(item["id"], target, "head-commit", "DIRECT", [item["source_id"], by_id[target]["source_id"]]))
        if item.get("kind") == "release":
            tag = item.get("data", {}).get("tag_name")
            target = f"tag:{tag}" if isinstance(tag, str) else None
            if target in by_id:
                links.append(_link(item["id"], target, "release-tag", "DIRECT", [item["source_id"], by_id[target]["source_id"]]))
    links = _dedupe_links(links)
    graph = {
        "schema_version": __version__, "report_kind": "evolution_graph", "generated_at": _timestamp(),
        "root": manifest["root"], "question": manifest.get("question", ""),
        "manifest_sha256": _sha256(manifest_path), "objects": list(by_id.values()), "links": links,
    }
    graph_path = output / "object-graph.json"
    _write_json(graph_path, graph)
    _write_json(output / "linkage-report.json", {"schema_version": __version__, "report_kind": "evolution_linkage", "links": links})
    _write_json(output / "decision-index.json", _decision_index(graph))
    _write_json(output / "evolution-pack.json", _evolution_pack(graph, manifest))
    (output / "timeline.mmd").write_text(_timeline(graph), encoding="utf-8")
    (output / "unanswered-questions.md").write_text(_unanswered(graph), encoding="utf-8")
    return graph_path


def write_evolution_report(graph_path: Path, output: Path) -> Path:
    graph = _read_json(graph_path)
    if graph.get("report_kind") != "evolution_graph":
        raise EvolveError("report input must be an evolution_graph")
    lines = ["# AET Evolution Report", "", f"Question: {graph.get('question') or 'Not supplied'}", "", "## Evidence-linked timeline", ""]
    for item in graph.get("objects", []):
        if item.get("kind") in {"commit", "tag", "document"}:
            lines.append(f"- `{item['id']}` — {item.get('subject') or item.get('name') or item.get('path')} (`{item.get('source_id')}`)")
    lines.extend(["", "## Links", ""])
    for link in graph.get("links", []):
        qualifier = f" — {link['note']}" if link.get("note") else ""
        lines.append(f"- **{link['confidence']}** `{link['from']}` → `{link['to']}` ({link['relation']}; sources: {', '.join(link['evidence'])}){qualifier}")
    if not graph.get("links"):
        lines.append("- **UNKNOWN** No deterministic relationship answered the question; inspect the source manifest before inferring a cause.")
    path = output.resolve() / "evolution-report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def query_evolution(graph_path: Path, query: str) -> list[dict[str, Any]]:
    graph = _read_json(graph_path)
    needle = query.casefold().strip()
    if not needle:
        raise EvolveError("query must be non-empty")
    return [item for item in graph.get("objects", []) if needle in json.dumps(item, ensure_ascii=False).casefold()]


def _collect_git(root: Path) -> dict[str, list[dict[str, Any]]]:
    if _git(root, "rev-parse", "--is-inside-work-tree") is None:
        return {"sources": [{"id": "git:repository", "adapter": "git-local", "level": "L3", "status": "UNKNOWN", "reason": "root is not a Git worktree"}], "objects": []}
    raw = _git(root, "log", "--all", "--reverse", "--format=%H%x1f%P%x1f%aI%x1f%s%x1e") or ""
    sources: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    for record in raw.split("\x1e"):
        if not record.strip():
            continue
        sha, parents, authored_at, subject = record.strip("\n").split("\x1f", 3)
        source_id = f"git:commit:{sha}"
        sources.append({"id": source_id, "adapter": "git-local", "level": "L3", "status": "PASS", "object_id": sha, "sha256": _sha256_text(record)})
        objects.append({"id": f"commit:{sha}", "kind": "commit", "sha": sha, "parents": parents.split() if parents else [], "authored_at": authored_at, "subject": subject, "source_id": source_id})
    tags = _git(root, "for-each-ref", "refs/tags", "--format=%(refname:short)%09%(objectname)") or ""
    for record in tags.splitlines():
        if not record:
            continue
        name, _ = record.split("\t", 1)
        target = (_git(root, "rev-list", "-n", "1", name) or "").strip()
        source_id = f"git:tag:{name}"
        sources.append({"id": source_id, "adapter": "git-local", "level": "L3", "status": "PASS", "object_id": name, "sha256": _sha256_text(record)})
        objects.append({"id": f"tag:{name}", "kind": "tag", "name": name, "target": f"commit:{target}" if target else None, "source_id": source_id})
    return {"sources": sources, "objects": objects}


def _collect_docs(root: Path) -> dict[str, list[dict[str, Any]]]:
    candidates = [root / name for name in ("README.md", "CHANGELOG.md", "HISTORY.md")]
    docs = root / "docs"
    if docs.is_dir():
        candidates.extend(sorted(docs.rglob("*.md")))
    sources: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    for path in candidates:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(root).as_posix()
        source_id = f"doc:{relative}"
        sources.append({"id": source_id, "adapter": "docs-local", "level": "L1", "status": "PASS", "path": relative, "sha256": _sha256_text(content)})
        objects.append({"id": source_id, "kind": "document", "path": relative, "content": content, "source_id": source_id})
    return {"sources": sources, "objects": objects}


def _collect_export(path: Path) -> dict[str, list[dict[str, Any]]]:
    data = _read_json(path)
    sources = [{"id": f"export:{path.name}", "adapter": "github-export", "level": "L1", "status": "PASS", "path": str(path), "sha256": _sha256(path)}]
    objects: list[dict[str, Any]] = []
    for kind, key in (("issue", "issues"), ("pull_request", "pull_requests"), ("release", "releases")):
        for item in data.get(key, []):
            if not isinstance(item, dict) or item.get("number", item.get("tag_name")) is None:
                continue
            identifier = str(item.get("number", item.get("tag_name")))
            objects.append({"id": f"{kind}:{identifier}", "kind": kind, "data": item, "source_id": sources[0]["id"]})
    return {"sources": sources, "objects": objects}


def _collect_github(root: Path) -> dict[str, list[dict[str, Any]]]:
    remote = _git(root, "remote", "get-url", "origin")
    if not remote:
        return {"sources": [{"id": "github:origin", "adapter": "github-api", "level": "L4", "status": "UNKNOWN", "reason": "origin remote is unavailable"}], "objects": []}
    match = re.search(r"github\.com[/:]([^/]+)/([^/.]+)(?:\.git)?", remote.strip())
    if not match:
        return {"sources": [{"id": "github:origin", "adapter": "github-api", "level": "L4", "status": "UNKNOWN", "reason": "origin is not a GitHub repository"}], "objects": []}
    repo = f"{match.group(1)}/{match.group(2)}"
    sources: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    for kind, endpoint, identifier in (
        ("issue", f"repos/{repo}/issues?state=all&per_page=100", "number"),
        ("pull_request", f"repos/{repo}/pulls?state=all&per_page=100", "number"),
        ("release", f"repos/{repo}/releases?per_page=100", "tag_name"),
    ):
        completed = subprocess.run(["gh", "api", "--paginate", "--slurp", endpoint], text=True, capture_output=True, check=False)
        source_id = f"github:{repo}:{kind}s"
        if completed.returncode:
            sources.append({"id": source_id, "adapter": "github-api", "level": "L4", "status": "UNKNOWN", "endpoint": endpoint, "reason": completed.stderr.strip() or "GitHub request failed"})
            continue
        try:
            pages = json.loads(completed.stdout)
            payload = [item for page in pages for item in page] if isinstance(pages, list) else []
        except (json.JSONDecodeError, TypeError):
            sources.append({"id": source_id, "adapter": "github-api", "level": "L4", "status": "UNKNOWN", "endpoint": endpoint, "reason": "GitHub response could not be normalized"})
            continue
        source = {"id": source_id, "adapter": "github-api", "level": "L4", "status": "PASS", "endpoint": endpoint, "retrieved_at": _timestamp(), "pages": len(pages), "sha256": _sha256_text(completed.stdout)}
        sources.append(source)
        for item in payload:
            if not isinstance(item, dict) or identifier not in item:
                continue
            if kind == "issue" and "pull_request" in item:
                continue
            objects.append({"id": f"{kind}:{item[identifier]}", "kind": kind, "data": item, "source_id": source_id})
    return {"sources": sources, "objects": objects}


def _link(source: str, target: str, relation: str, confidence: str, evidence: list[str], note: str | None = None) -> dict[str, Any]:
    return {"from": source, "to": target, "relation": relation, "confidence": confidence, "evidence": evidence, **({"note": note} if note else {})}


def _dedupe_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {(item["from"], item["to"], item["relation"], item["confidence"]): item for item in links}
    return [unique[key] for key in sorted(unique)]


def _decision_index(graph: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": __version__, "report_kind": "decision_index", "decisions": [link for link in graph["links"] if link["confidence"] == "DIRECT"], "unknowns": [link for link in graph["links"] if link["confidence"] != "DIRECT"]}


def _evolution_pack(graph: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    direct = sum(link["confidence"] == "DIRECT" for link in graph["links"])
    candidate = sum(link["confidence"] == "CANDIDATE" for link in graph["links"])
    return {"schema_version": __version__, "report_kind": "evolution", "run_id": _sha256_text(graph["manifest_sha256"])[:16], "generated_at": _timestamp(), "tool": {"name": "aet", "version": __version__}, "scope": {"root": graph["root"], "manifest_sha256": graph["manifest_sha256"]}, "sources": manifest["sources"], "claims": graph["links"], "summary": {"PASS": direct, "FAIL": 0, "UNKNOWN": candidate + sum(source["status"] == "UNKNOWN" for source in manifest["sources"]), "NOT_APPLICABLE": 0}}


def _timeline(graph: dict[str, Any]) -> str:
    events = [item for item in graph["objects"] if item.get("kind") in {"commit", "tag"}]
    lines = ["timeline", "  title AET Evolution Timeline"]
    for item in events:
        label = item.get("subject") or item.get("name") or item["id"]
        lines.append(f"  {item.get('authored_at', 'undated')} : {label}")
    return "\n".join(lines) + "\n"


def _unanswered(graph: dict[str, Any]) -> str:
    candidates = [link for link in graph["links"] if link["confidence"] != "DIRECT"]
    if not candidates:
        return "# Unanswered questions\n\nNo candidate links require review.\n"
    lines = ["# Unanswered questions", "", "These links are not causal conclusions; obtain an Issue, PR, ADR, or human attestation.", ""]
    lines.extend(f"- `{item['from']}` → `{item['to']}`: {item.get('note', 'candidate evidence only')}" for item in candidates)
    return "\n".join(lines) + "\n"


def _summary(sources: list[dict[str, Any]]) -> dict[str, int]:
    return {"PASS": sum(item["status"] == "PASS" for item in sources), "FAIL": 0, "UNKNOWN": sum(item["status"] == "UNKNOWN" for item in sources), "NOT_APPLICABLE": 0}


def _git(root: Path, *args: str) -> str | None:
    completed = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    return completed.stdout if completed.returncode == 0 else None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvolveError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(data, dict):
        raise EvolveError(f"JSON object expected: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()
