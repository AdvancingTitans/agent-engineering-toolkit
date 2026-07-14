#!/usr/bin/env python3
"""Verify the tracked, diff-bound release classification contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


SENSITIVE_PREFIXES = ("skills/", "eval/real-agent/", "schemas/", "src/aet/")
SENSITIVE_PATHS = {
    ".github/workflows/ci.yml",
    ".github/workflows/publish-pypi.yml",
    ".github/workflows/real-host-gate.yml",
    ".github/workflows/release.yml",
    "aet.intent.json",
    "release-classification.json",
}


def paths_digest(paths: list[str]) -> str:
    payload = "".join(f"{path}\n" for path in sorted(paths)).encode()
    return hashlib.sha256(payload).hexdigest()


def is_behavior_sensitive(path: str) -> bool:
    return path in SENSITIVE_PATHS or path.startswith(SENSITIVE_PREFIXES)


def validate(document: dict[str, Any], release_tag: str, release_commit: str,
             base_commit: str, changed_paths: list[str]) -> dict[str, Any]:
    if document.get("schema_version") != "release-classification/v1":
        raise ValueError("unsupported release classification schema")
    if document.get("release_tag") != release_tag:
        raise ValueError("classification release_tag does not match the requested tag")
    release_class = document.get("release_class")
    if release_class not in {"deterministic", "governance-adoption"}:
        raise ValueError("release_class must be deterministic or governance-adoption")
    digest = paths_digest(changed_paths)
    if document.get("changed_paths_sha256") != digest:
        raise ValueError("classification changed-path digest does not match the release diff")

    sensitive = sorted(path for path in changed_paths if is_behavior_sensitive(path))
    exceptions = document.get("not_applicable_exceptions", [])
    if not isinstance(exceptions, list):
        raise ValueError("not_applicable_exceptions must be a list")
    exception_paths: list[str] = []
    for item in exceptions:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("each not-applicable exception must name one path")
        if len(item.get("reason", "").strip()) < 20:
            raise ValueError(f"exception reason is missing or too short: {item['path']}")
        proofs = item.get("deterministic_proofs")
        if not isinstance(proofs, list) or not proofs or not all(isinstance(proof, str) and proof.strip() for proof in proofs):
            raise ValueError(f"exception must cite deterministic proofs: {item['path']}")
        exception_paths.append(item["path"])
    if len(exception_paths) != len(set(exception_paths)):
        raise ValueError("not-applicable exception paths must be unique")

    claims = document.get("observed_behavior_claims")
    adoptions = document.get("governance_asset_adoptions")
    if not isinstance(claims, list) or not isinstance(adoptions, list):
        raise ValueError("behavior claims and governance adoptions must be lists")
    if release_class == "deterministic":
        if document.get("real_host_gate") != "NOT_APPLICABLE":
            raise ValueError("deterministic releases must declare Real Host Gate NOT_APPLICABLE")
        if claims or adoptions:
            raise ValueError("deterministic releases cannot declare observed behavior or governance adoption")
        if sorted(exception_paths) != sensitive:
            raise ValueError("every behavior-sensitive changed path needs one exact not-applicable exception")
        if document.get("governance_gate") not in (None, {}):
            raise ValueError("deterministic releases cannot declare a governance Gate binding")
    else:
        if document.get("real_host_gate") != "REQUIRED":
            raise ValueError("governance-adoption releases must require the Real Host Gate")
        if not claims and not adoptions:
            raise ValueError("governance-adoption requires an observed claim or adopted asset")
        if exceptions:
            raise ValueError("governance-adoption releases cannot carry not-applicable exceptions")
        binding = document.get("governance_gate")
        if not isinstance(binding, dict):
            raise ValueError("governance-adoption requires an exact Gate binding")
        candidate_sha = binding.get("candidate_sha256")
        if not isinstance(candidate_sha, str) or re.fullmatch(r"[0-9a-f]{64}", candidate_sha) is None:
            raise ValueError("governance Gate binding requires the exact candidate SHA-256")
        suites = binding.get("covered_suites")
        if not isinstance(suites, list) or not suites or not all(
            suite in {"core", "validation", "held_out"} for suite in suites
        ) or len(suites) != len(set(suites)):
            raise ValueError("governance Gate binding requires unique covered suite IDs")
        claim_ids = binding.get("claim_ids")
        if not isinstance(claim_ids, list) or not claim_ids or not all(
            isinstance(claim_id, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9._-]+", claim_id)
            for claim_id in claim_ids
        ):
            raise ValueError("governance Gate binding requires structured claim IDs")

    return {
        "schema_version": "release-classification-verification/v1",
        "release_tag": release_tag,
        "release_commit": release_commit,
        "base_tag": document.get("base_tag"),
        "base_commit": base_commit,
        "release_class": release_class,
        "changed_paths_sha256": digest,
        "behavior_sensitive_paths": sensitive,
        "not_applicable_exceptions": exceptions,
        "observed_behavior_claims": claims,
        "governance_asset_adoptions": adoptions,
        "governance_gate": document.get("governance_gate"),
    }


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def previous_release_tag(tags: list[str], release_tag: str) -> str:
    pattern = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
    release_match = pattern.fullmatch(release_tag)
    if release_match is None:
        raise ValueError("release_tag must be exact SemVer")
    release_version = tuple(map(int, release_match.groups()))
    versions = []
    for tag in tags:
        match = pattern.fullmatch(tag)
        if match:
            version = tuple(map(int, match.groups()))
            if version < release_version:
                versions.append((version, tag))
    if not versions:
        raise ValueError("no previous SemVer release tag is reachable")
    return max(versions)[1]


def changed_paths(root: Path, base_tag: str, release_tag: str) -> list[str]:
    raw = subprocess.run(
        ["git", "diff", "--name-status", "-z", "--diff-filter=ACDMRTUXB", f"{base_tag}..{release_tag}"],
        cwd=root, check=True, capture_output=True,
    ).stdout
    return parse_name_status(raw)


def parse_name_status(raw: bytes) -> list[str]:
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        status = tokens[index].decode("ascii")
        index += 1
        if index >= len(tokens):
            raise ValueError("malformed git diff name-status output")
        paths.append(tokens[index].decode("utf-8", "surrogateescape"))
        index += 1
        if status.startswith(("R", "C")):
            if index >= len(tokens):
                raise ValueError("rename/copy diff is missing its destination")
            paths.append(tokens[index].decode("utf-8", "surrogateescape"))
            index += 1
    return sorted(set(paths))


def changed_content_digest(root: Path, base_tag: str, release_tag: str) -> str:
    diff = subprocess.run(
        ["git", "diff", "--binary", f"{base_tag}..{release_tag}", "--", ".", ":(exclude)release-classification.json"],
        cwd=root, check=True, capture_output=True,
    ).stdout
    return hashlib.sha256(diff).hexdigest()


def deterministic_proof_hashes(root: Path, release_commit: str,
                               exceptions: list[dict[str, Any]]) -> dict[str, str]:
    proofs = sorted({proof for item in exceptions for proof in item["deterministic_proofs"]})
    hashes: dict[str, str] = {}
    for proof in proofs:
        path = Path(proof)
        if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "tests" or path.suffix != ".py":
            raise ValueError(f"deterministic proof must be a safe tests/*.py path: {proof}")
        object_name = f"{release_commit}:{path.as_posix()}"
        if git(root, "cat-file", "-t", object_name) != "blob":
            raise ValueError(f"deterministic proof is not a tracked file at the release commit: {proof}")
        content = subprocess.run(
            ["git", "show", object_name], cwd=root, check=True, capture_output=True
        ).stdout
        hashes[proof] = hashlib.sha256(content).hexdigest()
    return hashes


def verify(root: Path, manifest: Path, release_tag: str, expected_class: str) -> dict[str, Any]:
    document = json.loads(manifest.read_text(encoding="utf-8"))
    if document.get("release_class") != expected_class:
        raise ValueError("dispatch release_class does not match the tracked contract")
    base_tag = document.get("base_tag")
    if not isinstance(base_tag, str) or not base_tag:
        raise ValueError("classification base_tag is required")
    release_commit = git(root, "rev-list", "-n", "1", release_tag)
    base_commit = git(root, "rev-list", "-n", "1", base_tag)
    if base_tag == release_tag or base_commit == release_commit:
        raise ValueError("base release must precede the release tag and use a different commit")
    subprocess.run(["git", "merge-base", "--is-ancestor", base_commit, release_commit], cwd=root, check=True)
    reachable_tags = git(root, "tag", "--merged", release_commit).splitlines()
    if base_tag != previous_release_tag(reachable_tags, release_tag):
        raise ValueError("base_tag must be the latest preceding reachable SemVer release")
    content_digest = changed_content_digest(root, base_tag, release_tag)
    if document.get("changed_content_sha256") != content_digest:
        raise ValueError("classification content digest does not match the release Diff")
    result = validate(document, release_tag, release_commit, base_commit, changed_paths(root, base_tag, release_tag))
    result["changed_content_sha256"] = content_digest
    result["deterministic_proof_sha256"] = deterministic_proof_hashes(
        root, release_commit, result["not_applicable_exceptions"]
    )
    result["classification_contract_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--expected-class", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.root.resolve(), args.manifest.resolve(), args.release_tag, args.expected_class)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"release classification failed: {exc}") from exc


if __name__ == "__main__":
    main()
