"""Deterministic intent-contract checks against a local Git diff."""

from __future__ import annotations

import fnmatch
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Evidence, Finding, Severity, Status


class ReviewError(ValueError):
    """Raised when review inputs cannot be inspected deterministically."""


@dataclass(frozen=True)
class Proof:
    identifier: str
    command: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class IntentContract:
    intent: str
    changed_path_budget: int
    allowed_paths: tuple[str, ...]
    required_proofs: tuple[Proof, ...]


def review(root: Path, base: str, intent_path: Path) -> tuple[list[Finding], dict[str, Any]]:
    """Review the current worktree against a human-authored intent contract."""
    root = root.resolve()
    contract_path = intent_path if intent_path.is_absolute() else root / intent_path
    contract_path = contract_path.resolve()
    try:
        contract_path.relative_to(root)
    except ValueError as error:
        raise ReviewError("intent contract must be inside the review root") from error

    relative_contract = contract_path.relative_to(root).as_posix()
    try:
        contract = _load_contract(contract_path)
    except ReviewError as error:
        return [
            Finding(
                "AET-REV-001",
                Status.FAIL,
                Severity.ERROR,
                f"Intent contract is invalid: {error}",
                (Evidence(relative_contract, 1),),
                "Create a valid JSON intent contract with intent, changed_path_budget, allowed_paths, and required_proofs.",
                "0.2.0",
            )
        ], {"base": base, "intent_contract": relative_contract, "changed_paths": []}

    changed_paths = _changed_paths(root, base)
    findings = [
        Finding(
            "AET-REV-001",
            Status.PASS,
            Severity.INFO,
            "Intent contract is valid and human-reviewable.",
            (Evidence(relative_contract, 1, contract.intent),),
            "Keep the contract concise and update it when the approved scope changes.",
            "0.2.0",
        ),
        _check_budget(relative_contract, contract, changed_paths),
    ]
    findings.extend(_check_paths(relative_contract, contract, changed_paths))
    findings.extend(_check_proofs(root, relative_contract, contract))
    metadata = {
        "base": base,
        "intent_contract": relative_contract,
        "intent": contract.intent,
        "changed_paths": changed_paths,
        "changed_path_budget": contract.changed_path_budget,
    }
    return sorted(findings, key=lambda item: (item.severity, item.rule_id, item.claim)), metadata


def _load_contract(path: Path) -> IntentContract:
    if not path.is_file():
        raise ReviewError("file does not exist")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReviewError(f"invalid JSON at line {error.lineno}") from error
    if not isinstance(data, dict):
        raise ReviewError("top-level value must be an object")
    intent = data.get("intent")
    budget = data.get("changed_path_budget")
    paths = data.get("allowed_paths")
    proofs = data.get("required_proofs")
    if not isinstance(intent, str) or not intent.strip():
        raise ReviewError("intent must be a non-empty string")
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 0:
        raise ReviewError("changed_path_budget must be a non-negative integer")
    if not isinstance(paths, list) or not paths or not all(isinstance(path, str) and path for path in paths):
        raise ReviewError("allowed_paths must be a non-empty list of path patterns")
    if not isinstance(proofs, list) or not proofs:
        raise ReviewError("required_proofs must be a non-empty list")
    parsed_proofs: list[Proof] = []
    identifiers: set[str] = set()
    for proof in proofs:
        if not isinstance(proof, dict):
            raise ReviewError("each required proof must be an object")
        identifier = proof.get("id")
        command = proof.get("command")
        evidence = proof.get("evidence")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ReviewError("each required proof needs a unique non-empty id")
        if not isinstance(command, str) or not command.strip():
            raise ReviewError(f"proof {identifier!r} needs a non-empty command")
        if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item for item in evidence):
            raise ReviewError(f"proof {identifier!r} needs at least one local evidence path")
        identifiers.add(identifier)
        parsed_proofs.append(Proof(identifier, command, tuple(evidence)))
    return IntentContract(intent.strip(), budget, tuple(paths), tuple(parsed_proofs))


def _changed_paths(root: Path, base: str) -> list[str]:
    completed = _git(root, "diff", "--name-status", "--find-renames", base, "--")
    paths: set[str] = set()
    for line in completed.stdout.splitlines():
        fields = line.split("\t")
        if not fields:
            continue
        if fields[0].startswith(("R", "C")) and len(fields) == 3:
            paths.update(fields[1:])
        elif len(fields) == 2:
            paths.add(fields[1])
    untracked = _git(root, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
    paths.update(untracked)
    return sorted(paths)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ReviewError(f"cannot inspect Git base: {detail}")
    return completed


def _check_budget(contract_path: str, contract: IntentContract, changed_paths: list[str]) -> Finding:
    count = len(changed_paths)
    if count <= contract.changed_path_budget:
        return Finding(
            "AET-REV-002", Status.PASS, Severity.INFO,
            "Changed-path budget is within the approved limit.",
            (Evidence(contract_path, 1, f"{count} changed paths; budget {contract.changed_path_budget}"),),
            "Increase the budget only after human review of the expanded scope.", "0.2.0",
        )
    return Finding(
        "AET-REV-002", Status.FAIL, Severity.ERROR,
        "Changed-path budget exceeds the approved limit.",
        (Evidence(contract_path, 1, f"{count} changed paths; budget {contract.changed_path_budget}"),),
        "Reduce the diff or update the reviewed intent contract before merging.", "0.2.0",
    )


def _check_paths(contract_path: str, contract: IntentContract, changed_paths: list[str]) -> list[Finding]:
    outside = [path for path in changed_paths if not any(_matches(path, pattern) for pattern in contract.allowed_paths)]
    if not outside:
        return [Finding(
            "AET-REV-003", Status.PASS, Severity.INFO,
            "All changed paths are within the approved intent scope.",
            (Evidence(contract_path, 1, ", ".join(contract.allowed_paths)),),
            "Update allowed_paths only when the broader scope has received human review.", "0.2.0",
        )]
    return [Finding(
        "AET-REV-003", Status.FAIL, Severity.ERROR,
        f"Changed path is outside the approved intent scope: {path}",
        (Evidence(path),),
        "Revert the unrelated change or add its path to the reviewed intent contract.", "0.2.0",
    ) for path in outside]


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)


def _check_proofs(root: Path, contract_path: str, contract: IntentContract) -> list[Finding]:
    findings: list[Finding] = []
    for proof in contract.required_proofs:
        missing: list[str] = []
        for item in proof.evidence:
            candidate = (root / item).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                missing.append(item)
                continue
            if not candidate.exists():
                missing.append(item)
        if missing:
            findings.append(Finding(
                "AET-REV-004", Status.FAIL, Severity.ERROR,
                f"Required proof {proof.identifier!r} is missing local evidence: {', '.join(missing)}",
                (Evidence(contract_path, 1, proof.command),),
                "Restore the evidence path or update the reviewed proof contract.", "0.2.0",
            ))
        else:
            findings.append(Finding(
                "AET-REV-004", Status.PASS, Severity.INFO,
                f"Required proof {proof.identifier!r} declares local evidence.",
                (Evidence(contract_path, 1, proof.command),),
                "Run the declared command separately; aet records the contract and evidence paths but does not execute commands.", "0.2.0",
            ))
    return findings
