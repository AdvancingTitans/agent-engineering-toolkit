"""Deterministic, policy-bounded verification for portable investigations."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from aet.quick.fresh import quick_fresh


class VerificationError(ValueError):
    """A declared verification input is unsafe or invalid."""


def verify_proof_receipts(
    *,
    request: Mapping[str, Any],
    records: Sequence[dict[str, Any]],
    observations: Sequence[dict[str, Any]],
    candidates: list[dict[str, Any]],
    workspace: Path,
    proof_paths: Sequence[Path],
) -> dict[str, Any]:
    """Inspect explicit local Proof receipts without executing a command."""
    # 方案第 5、6 节：只有宿主显式授权的确定性工具可以晋级 Candidate。
    policy = request["policy"]
    allowed = set(policy["allowed_tools"])
    budgets = policy["budgets"]
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise VerificationError(f"workspace is not a directory: {workspace}")
    if proof_paths and "proof.inspect" not in allowed:
        raise VerificationError("proof.inspect is required when proof receipts are supplied")

    observation_by_id = {item["id"]: item for item in observations}
    record_by_id = {item["record_id"]: item for item in records}
    evidence: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    tool_calls = 0
    budget_exhausted = False
    seen_source_ids: set[str] = set()

    for proof_path in proof_paths:
        if (
            tool_calls >= budgets["max_tool_calls"]
            or len(evidence) >= budgets["max_verified_evidence"]
        ):
            budget_exhausted = True
            break
        path = _authorized_file(root, Path(proof_path), policy["workspace_policy"])
        receipt, receipt_bytes = _load_receipt(path)
        _bind_receipt_workspace(root, receipt)
        tool_calls += 1
        argv = _proof_argv(receipt)
        source_id = "proof-source-" + hashlib.sha256(receipt_bytes).hexdigest()
        relative = path.relative_to(root).as_posix()
        content_hash = hashlib.sha256(receipt_bytes).hexdigest()
        source = {
            "id": source_id,
            "type": "proof_receipt",
            "locator": {
                "path": relative,
                **(
                    {"commit": receipt["binding"]["workspace_snapshot"]["head_sha"]}
                    if isinstance(
                        receipt.get("binding", {}).get("workspace_snapshot", {}).get("head_sha"),
                        str,
                    )
                    else {}
                ),
            },
            "provenance": {
                "source_type": "deterministic_runtime",
                "schema_version": receipt["schema_version"],
            },
            "integrity": {"content_hash": content_hash},
        }
        if source_id in seen_source_ids:
            raise VerificationError("duplicate Proof receipt content was supplied")
        seen_source_ids.add(source_id)
        sources.append(source)
        matched = _matching_command_candidates(
            argv,
            candidates,
            observation_by_id,
            record_by_id,
        )
        if not matched:
            ledger.append(
                {
                    "id": f"ledger-proof-{len(ledger) + 1:04d}",
                    "question": request["question"],
                    "hypothesis_ref": "competing:0",
                    "action": "inspect_proof",
                    "tool_name": "proof.inspect",
                    "input_refs": [source_id],
                    "observation_refs": [],
                    "evidence_candidate_refs": [],
                    "effect": "no_change",
                    "explanation": (
                        "The declared Proof receipt did not match a recorded command Candidate."
                    ),
                }
            )
            continue

        authoritative_status = receipt.get("authoritative_status")
        if authoritative_status not in {"PASS", "FAIL"}:
            ledger.append(
                {
                    "id": f"ledger-proof-{len(ledger) + 1:04d}",
                    "question": request["question"],
                    "hypothesis_ref": "competing:0",
                    "action": "inspect_proof",
                    "tool_name": "proof.inspect",
                    "input_refs": [source_id],
                    "observation_refs": list(
                        dict.fromkeys(
                            reference
                            for item in matched
                            for reference in item["observation_refs"]
                        )
                    ),
                    "evidence_candidate_refs": [item["id"] for item in matched],
                    "effect": "no_change",
                    "explanation": (
                        "The matching Proof receipt did not contain an authoritative PASS or FAIL result."
                    ),
                }
            )
            continue

        freshness = _unchecked_freshness()
        if "freshness.check" in allowed:
            if tool_calls >= budgets["max_tool_calls"]:
                ledger.append(
                    {
                        "id": f"ledger-proof-{len(ledger) + 1:04d}",
                        "question": request["question"],
                        "hypothesis_ref": "primary",
                        "action": "inspect_proof",
                        "tool_name": "proof.inspect",
                        "input_refs": [source_id],
                        "observation_refs": list(
                            dict.fromkeys(
                                reference
                                for item in matched
                                for reference in item["observation_refs"]
                            )
                        ),
                        "evidence_candidate_refs": [item["id"] for item in matched],
                        "effect": "no_change",
                        "explanation": (
                            "The Proof matched a command Candidate, but the tool budget "
                            "ended before the required Freshness check."
                        ),
                    }
                )
                budget_exhausted = True
                break
            freshness_result = quick_fresh(path)
            freshness = _portable_freshness(freshness_result)
            tool_calls += 1

        exit_code = receipt["command"].get("exit_code")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise VerificationError("proof command.exit_code must be an integer")

        candidate_ids = [item["id"] for item in matched]
        observation_refs = list(
            dict.fromkeys(
                reference
                for item in matched
                for reference in item["observation_refs"]
            )
        )
        for candidate in matched:
            candidate["status"] = "verified"
            candidate["verification_required"] = False

        evidence_id = "evidence-" + hashlib.sha256(
            _canonical_bytes(
                {
                    "proof_source": source_id,
                    "candidate_refs": candidate_ids,
                    "freshness": freshness["status"],
                }
            )
        ).hexdigest()
        current = freshness["status"] == "current"
        passed = authoritative_status == "PASS" and exit_code == 0
        claim_id = _finding_id(request)
        evidence_item = {
            "extensions": {
                "candidate_refs": candidate_ids,
                "observation_refs": observation_refs,
            },
            "id": evidence_id,
            "proposition": (
                f"The authorized Proof receipt records command {json.dumps(argv, ensure_ascii=False)} "
                f"with exit code {exit_code}."
            ),
            "kind": (
                "test_result"
                if any(_looks_like_test(part) for part in argv)
                else "command_receipt"
            ),
            "strength": "reproduced",
            "strength_definition": (
                "The command result was captured by the deterministic AET Proof runtime "
                "and bound to the declared workspace."
            ),
            "source_refs": [source_id],
            "bindings": _bindings(request, receipt, argv),
            "freshness": freshness,
            "supports": [claim_id] if current and passed else [],
            "contradicts": [claim_id] if current and not passed else [],
            "limitations": [
                receipt.get("coverage", {}).get(
                    "statement",
                    "This proof covers only the recorded command and declared bindings.",
                )
            ],
            "integrity": {
                "content_hash": content_hash,
                "truncated": False,
            },
        }
        evidence.append(evidence_item)
        ledger.append(
            {
                "id": f"ledger-proof-{len(ledger) + 1:04d}",
                "question": request["question"],
                "hypothesis_ref": "primary" if passed else "competing:0",
                "action": "inspect_proof",
                "tool_name": "proof.inspect",
                "input_refs": [source_id],
                "output_ref": evidence_id,
                "observation_refs": observation_refs,
                "evidence_candidate_refs": candidate_ids,
                "effect": "supports_primary" if passed else "supports_competing",
                "explanation": (
                    "A declared AET Proof receipt deterministically verified the matching "
                    "recorded command Candidate."
                ),
            }
        )
        if "freshness.check" in allowed:
            ledger.append(
                {
                    "id": f"ledger-freshness-{len(ledger) + 1:04d}",
                    "question": request["question"],
                    "hypothesis_ref": "primary" if current else "competing:0",
                    "action": "check_freshness",
                    "tool_name": "freshness.check",
                    "input_refs": [source_id],
                    "output_ref": evidence_id,
                    "observation_refs": observation_refs,
                    "evidence_candidate_refs": candidate_ids,
                    "effect": "supports_primary" if current else "supports_competing",
                    "explanation": freshness["explanation"],
                }
            )

    return {
        "evidence": evidence,
        "sources": sources,
        "ledger": ledger,
        "tool_calls": tool_calls,
        "budget_exhausted": budget_exhausted,
    }


def _authorized_file(root: Path, path: Path, policy: Mapping[str, Any]) -> Path:
    candidate = path if path.is_absolute() else root / path
    if candidate.is_symlink():
        raise VerificationError(f"proof receipt must not be a symlink: {path}")
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise VerificationError(f"proof receipt must remain inside the workspace: {path}") from error
    if not resolved.is_file():
        raise VerificationError(f"proof receipt is not a file: {path}")
    relative_text = relative.as_posix()
    allowed_paths = policy.get("allowed_paths")
    denied_paths = policy.get("denied_paths", [])
    if allowed_paths and not any(_within(relative_text, item) for item in allowed_paths):
        raise VerificationError(f"proof receipt is outside allowed_paths: {relative_text}")
    if any(_within(relative_text, item) for item in denied_paths):
        raise VerificationError(f"proof receipt is inside denied_paths: {relative_text}")
    return resolved


def _within(path: str, prefix: str) -> bool:
    normalized = prefix.strip("/")
    if normalized in {"", "."}:
        return True
    return path == normalized or path.startswith(normalized + "/")


def _load_receipt(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda item: (_raise_nonfinite(item)),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise VerificationError(f"invalid Proof receipt JSON: {error}") from error
    if not isinstance(value, dict) or value.get("schema_version") != "aet-proof-receipt/v2":
        raise VerificationError("proof receipt must use aet-proof-receipt/v2")
    for field in ("command", "binding", "result", "coverage"):
        if not isinstance(value.get(field), dict):
            raise VerificationError(f"proof receipt {field} must be an object")
    return value, raw


def _proof_argv(receipt: Mapping[str, Any]) -> list[str]:
    argv = receipt["command"].get("argv")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
    ):
        raise VerificationError("proof command.argv must be a non-empty string array")
    return argv


def _bind_receipt_workspace(root: Path, receipt: Mapping[str, Any]) -> None:
    cwd = receipt["command"].get("cwd")
    snapshot_root = receipt["binding"].get("workspace_snapshot", {}).get("root")
    values = [("command.cwd", cwd)]
    if snapshot_root is not None:
        values.append(("workspace_snapshot.root", snapshot_root))
    for label, value in values:
        if not isinstance(value, str):
            raise VerificationError(f"proof {label} must be a string")
        try:
            bound = Path(value).resolve(strict=True)
        except OSError as error:
            raise VerificationError(f"proof {label} is unavailable") from error
        if bound != root:
            raise VerificationError(f"proof {label} does not match the declared workspace")


def _matching_command_candidates(
    argv: list[str],
    candidates: Sequence[dict[str, Any]],
    observation_by_id: Mapping[str, dict[str, Any]],
    record_by_id: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("candidate_type") != "command_observation":
            continue
        for observation_id in candidate["observation_refs"]:
            observation = observation_by_id.get(observation_id, {})
            for source_ref in observation.get("source_refs", []):
                record = record_by_id.get(source_ref, {})
                if record.get("record_type") != "tool_call":
                    continue
                try:
                    arguments = json.loads(record.get("arguments_json", ""))
                except json.JSONDecodeError:
                    continue
                command = arguments.get("command") if isinstance(arguments, dict) else None
                if command == argv:
                    matches.append(candidate)
                    break
            else:
                continue
            break
    return matches


def _portable_freshness(result: Mapping[str, Any]) -> dict[str, Any]:
    state = result.get("freshness_state")
    status = {
        "EXACT_MATCH": "current",
        "RELEVANT_FILES_MATCH": "current",
        "HEAD_CHANGED_RELEVANT_FILES_MATCH": "current",
        "RELEVANT_FILES_CHANGED": "relevant_files_changed",
        "ENVIRONMENT_CHANGED": "environment_changed",
        "ARTIFACT_CHANGED": "workspace_changed",
    }.get(state, "unknown")
    reasons = result.get("reasons")
    explanation = (
        "; ".join(item for item in reasons if isinstance(item, str) and item)
        if isinstance(reasons, list)
        else "Freshness could not be established."
    )
    effect = (
        "The historical Proof may be applied to the declared current workspace."
        if status == "current"
        else "The historical Proof must not be treated as proof of the current workspace."
    )
    value = {
        "status": status,
        "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "explanation": explanation or "Freshness could not be established.",
        "effect": effect,
    }
    if status != "current":
        value["recommended_action"] = "Rerun the affected verification command."
    return value


def _unchecked_freshness() -> dict[str, Any]:
    return {
        "status": "unknown",
        "explanation": "The policy did not authorize freshness.check.",
        "effect": "The historical Proof must not be treated as proof of the current workspace.",
        "recommended_action": "Authorize freshness.check or rerun the command.",
    }


def _bindings(
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
    argv: list[str],
) -> dict[str, Any]:
    task = request["task"]
    snapshot = receipt["binding"].get("workspace_snapshot", {})
    relevant = receipt["binding"].get("relevant_paths", [])
    environment = receipt["binding"].get("environment", {})
    bindings: dict[str, Any] = {
        "task_id": task["task_id"],
        "command": argv,
        "paths": [
            item["path"]
            for item in relevant
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        ],
    }
    for source, target in (
        ("workspace_id", "workspace_id"),
        ("repository", "repository"),
    ):
        if isinstance(task.get(source), str):
            bindings[target] = task[source]
    if isinstance(snapshot, dict) and isinstance(snapshot.get("head_sha"), str):
        bindings["commit"] = snapshot["head_sha"]
    if isinstance(environment, dict) and isinstance(environment.get("digest"), str):
        bindings["environment_hash"] = environment["digest"]
    return bindings


def _finding_id(request: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        "\0".join(
            ["finding", request["investigation_id"], request["question"]]
        ).encode("utf-8")
    ).hexdigest()


def _looks_like_test(value: str) -> bool:
    lowered = value.lower()
    return any(item in lowered for item in ("test", "pytest", "unittest"))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise VerificationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _raise_nonfinite(value: str) -> Any:
    raise VerificationError(f"non-finite JSON number: {value}")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
