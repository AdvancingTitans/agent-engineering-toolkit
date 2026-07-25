"""Host-neutral, read-only investigation over normalized Agent Run Records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from aet.bundle.redaction import redact_text
from aet.bundle.loader import BundleError
from aet.bundle.validator import _validate_evidence, _validate_source
from aet.evidence_core import build_evidence_candidates
from aet.observations import extract_observations, filter_relevant_observations
from .verification import VerificationError, verify_proof_receipts


class PortableInvestigationError(ValueError):
    """A portable investigation request violates its bounded contract."""


_WRITE_TOOLS = {
    "file.write",
    "git.commit",
    "git.push",
    "git.merge",
    "git.rebase",
    "git.checkout",
    "git.reset",
}


def investigate_run(
    request: Mapping[str, Any],
    records: list[dict[str, Any]],
    *,
    workspace: Path | None = None,
    proof_paths: tuple[Path, ...] | list[Path] = (),
) -> dict[str, Any]:
    """Investigate records and inspect explicitly authorized deterministic Proofs."""
    # 方案第 5 节边界：Investigator 只读；证据晋级仅由授权确定性工具完成。
    normalized_request = _validate_request(request)
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise PortableInvestigationError("records must be an array of objects")
    policy = normalized_request["policy"]
    exported_request = _export_request_fields(normalized_request)
    _bind_run_sources(normalized_request["run_sources"], records)
    limit = policy["budgets"]["max_run_records_read"]
    budget_exhausted = len(records) > limit
    selected_records = records[:limit]
    observations = extract_observations(
        selected_records,
        investigation_id=normalized_request["investigation_id"],
        question=normalized_request["question"],
    )
    if normalized_request["requested_evidence"]:
        requested_query = " ".join(
            item.replace("_", " ")
            for item in normalized_request["requested_evidence"]
        )
        observations = filter_relevant_observations(observations, requested_query)
    observations = _apply_privacy_policy(
        observations,
        policy["privacy_policy"],
    )
    candidates = build_evidence_candidates(
        observations,
        investigation_id=normalized_request["investigation_id"],
    )
    candidate_limit = policy["budgets"]["max_evidence_candidates"]
    if len(candidates) > candidate_limit:
        candidates = []
        budget_exhausted = True

    candidate_by_observation: dict[str, list[str]] = {}
    for candidate in candidates:
        for observation_ref in candidate["observation_refs"]:
            candidate_by_observation.setdefault(observation_ref, []).append(candidate["id"])
    counter_refs = [
        candidate["id"]
        for candidate in candidates
        if candidate["candidate_type"] == "counter_evidence"
    ]
    observation_by_source: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        for source_ref in observation["source_refs"]:
            observation_by_source.setdefault(source_ref, []).append(observation)
    ledger: list[dict[str, Any]] = []
    for index, record in enumerate(selected_records, start=1):
        record_id = record["record_id"]
        related_observations = observation_by_source.get(record_id, [])
        related_observation_ids = [item["id"] for item in related_observations]
        related_candidate_ids = list(
            dict.fromkeys(
                candidate_id
                for observation_id in related_observation_ids
                for candidate_id in candidate_by_observation.get(observation_id, [])
            )
        )
        ledger.append(
            {
                "id": f"ledger-read-{index:04d}",
                "question": exported_request["question"],
                "hypothesis_ref": "competing:0",
                "action": "read_run_record",
                "tool_name": "run.read",
                "input_refs": [record_id],
                "observation_refs": related_observation_ids,
                "evidence_candidate_refs": related_candidate_ids,
                "effect": (
                    "supports_competing"
                    if any(
                        candidate_id in counter_refs
                        for candidate_id in related_candidate_ids
                    )
                    else "no_change"
                ),
                "explanation": (
                    "The bounded investigator read this declared Run Record while "
                    "testing the competing hypothesis."
                ),
            }
        )
    for index, observation in enumerate(observations, start=1):
        candidate_refs = candidate_by_observation.get(observation["id"], [])
        ledger.append(
            {
                "id": f"ledger-observation-{index:04d}",
                "question": exported_request["question"],
                "hypothesis_ref": "primary",
                "action": "record_observation",
                "input_refs": list(observation["source_refs"]),
                "output_ref": observation["id"],
                "observation_refs": [observation["id"]],
                "evidence_candidate_refs": candidate_refs,
                "effect": "no_change",
                "explanation": "A normalized Run Record produced a bounded Observation.",
            }
        )
    for index, candidate in enumerate(candidates, start=1):
        ledger.append(
            {
                "id": f"ledger-candidate-{index:04d}",
                "question": exported_request["question"],
                "hypothesis_ref": (
                    "competing:0"
                    if candidate["candidate_type"] == "counter_evidence"
                    else "primary"
                ),
                "action": "propose_candidate",
                "input_refs": list(candidate["observation_refs"]),
                "output_ref": candidate["id"],
                "observation_refs": list(candidate["observation_refs"]),
                "evidence_candidate_refs": [candidate["id"]],
                "effect": (
                    "supports_competing"
                    if candidate["candidate_type"] == "counter_evidence"
                    else "supports_primary"
                ),
                "explanation": "The Observation produced an unverified Evidence Candidate.",
            }
        )

    verification = {
        "evidence": [],
        "sources": [],
        "ledger": [],
        "tool_calls": 0,
        "budget_exhausted": False,
    }
    if proof_paths:
        if workspace is None:
            raise PortableInvestigationError(
                "workspace is required when Proof receipts are supplied"
            )
        try:
            verification = verify_proof_receipts(
                request=normalized_request,
                records=selected_records,
                observations=observations,
                candidates=candidates,
                workspace=workspace,
                proof_paths=proof_paths,
            )
        except VerificationError as error:
            raise PortableInvestigationError(str(error)) from error
        ledger.extend(verification["ledger"])
        budget_exhausted = budget_exhausted or verification["budget_exhausted"]

    verified_evidence = verification["evidence"]
    supporting = [
        item for item in verified_evidence if item["supports"]
    ]
    contradicting = [
        item for item in verified_evidence if item["contradicts"]
    ]
    if supporting and contradicting:
        status = "conflicted"
    elif supporting:
        status = "supported"
    elif contradicting:
        status = "unsupported"
    else:
        status = "unknown"

    unresolved = [] if status in {"supported", "unsupported"} else [exported_request["question"]]
    if budget_exhausted:
        unresolved.append("The investigation budget ended before all Run Records were processed.")
    elif not verified_evidence:
        unresolved.append("No matching authorized deterministic verification was available.")
    elif status == "conflicted":
        unresolved.append("Current deterministic evidence supports competing outcomes.")
    stop_reason = (
        "budget_exhausted"
        if budget_exhausted
        else "question_answered"
        if status in {"supported", "unsupported"}
        else "unknown"
        if verified_evidence
        else "tool_unavailable"
    )
    performed_disconfirming_search = bool(selected_records)
    record_sources = _record_source_bindings(
        selected_records,
        normalized_request["run_sources"],
    )
    result = {
        "schema_version": "portable-investigation-result/1.0",
        "investigation_id": normalized_request["investigation_id"],
        "question": exported_request["question"],
        "task": exported_request["task"],
        "hypotheses": exported_request["hypotheses"],
        "requested_evidence": deepcopy(normalized_request["requested_evidence"]),
        "run_sources": deepcopy(normalized_request["run_sources"]),
        "record_sources": record_sources,
        "verification_sources": verification["sources"],
        "policy": deepcopy(normalized_request["policy"]),
        "status": status,
        "observations": observations,
        "evidence_candidates": candidates,
        "verified_evidence": verified_evidence,
        "findings": [
            {
                "id": _stable_id(
                    "finding",
                    normalized_request["investigation_id"],
                    normalized_request["question"],
                ),
                "statement": exported_request["question"],
                "status": status,
                "evidence_refs": [item["id"] for item in verified_evidence],
                "counter_evidence_candidate_refs": counter_refs,
                "observation_refs": [item["id"] for item in observations],
                "limitations": list(unresolved),
            }
        ],
        "ledger": ledger,
        "disconfirming_search": {
            "performed": performed_disconfirming_search,
            "searched_record_refs": [
                item["record_id"]
                for item in selected_records
                if isinstance(item.get("record_id"), str)
            ],
            "counter_evidence_candidate_refs": counter_refs,
        },
        "unresolved": unresolved,
        "usage": {
            "run_records_read": len(selected_records),
            "evidence_candidates": len(candidates),
            "verified_evidence": len(verified_evidence),
            "tool_calls": verification["tool_calls"],
        },
        "stop": {
            "reason": stop_reason,
            "bounded_result": True,
            "explanation": (
                unresolved[-1]
                if unresolved
                else "Authorized deterministic evidence answered the declared question."
            ),
        },
    }
    return result


def write_investigation_result(result: Mapping[str, Any], output: Path) -> Path:
    """Write one result atomically without replacing an existing investigation."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise PortableInvestigationError(f"investigation output already exists: {output}")
    _validate_result(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes(dict(result)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, output)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return output


def validate_investigation_result(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Return one validated portable Investigation Result."""
    if not isinstance(result, Mapping):
        raise PortableInvestigationError("investigation result must be an object")
    value = deepcopy(dict(result))
    _validate_result(value)
    return value


def _validate_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(request, Mapping):
        raise PortableInvestigationError("request must be an object")
    value = deepcopy(dict(request))
    expected = {
        "protocol_version",
        "investigation_id",
        "question",
        "task",
        "hypotheses",
        "requested_evidence",
        "run_sources",
        "policy",
    }
    if set(value) != expected:
        raise PortableInvestigationError("request fields do not match portable-investigation-request/1.0")
    if value["protocol_version"] != "1.0":
        raise PortableInvestigationError("protocol_version must be 1.0")
    _nonempty(value["investigation_id"], "investigation_id")
    _nonempty(value["question"], "question")
    task = _object(value["task"], "task")
    allowed_task_fields = {
        "task_id",
        "request",
        "repository",
        "workspace_id",
        "base_ref",
        "head_ref",
    }
    if not set(task) <= allowed_task_fields:
        raise PortableInvestigationError("task contains unsupported fields")
    if not {"task_id", "request"} <= set(task):
        raise PortableInvestigationError("task requires task_id and request")
    _nonempty(task["task_id"], "task.task_id")
    _nonempty(task["request"], "task.request")
    for field in allowed_task_fields - {"task_id", "request"}:
        if field in task and not isinstance(task[field], str):
            raise PortableInvestigationError(f"task.{field} must be a string")
    hypotheses = _object(value["hypotheses"], "hypotheses")
    if set(hypotheses) != {"primary", "competing"}:
        raise PortableInvestigationError("hypotheses requires primary and competing")
    _nonempty(hypotheses["primary"], "hypotheses.primary")
    competing = _string_list(hypotheses["competing"], "hypotheses.competing", nonempty=True)
    if len(set(competing)) != len(competing):
        raise PortableInvestigationError("competing hypotheses must be unique")
    requested_evidence = _string_list(value["requested_evidence"], "requested_evidence")
    if len(set(requested_evidence)) != len(requested_evidence):
        raise PortableInvestigationError("requested_evidence must contain unique values")
    if not isinstance(value["run_sources"], list) or not value["run_sources"]:
        raise PortableInvestigationError("run_sources must be a non-empty array")
    source_fields = {"id", "source_type", "run_group_id", "extensions"}
    for index, item in enumerate(value["run_sources"]):
        if not isinstance(item, dict):
            raise PortableInvestigationError("run_sources entries must be objects")
        if not {"id", "source_type", "run_group_id"} <= set(item):
            raise PortableInvestigationError(
                f"run_sources[{index}] requires id, source_type, and run_group_id"
            )
        if not set(item) <= source_fields:
            raise PortableInvestigationError(
                f"run_sources[{index}] contains unsupported fields"
            )
        for field in ("id", "source_type", "run_group_id"):
            _nonempty(item[field], f"run_sources[{index}].{field}")
        if "extensions" in item and not isinstance(item["extensions"], dict):
            raise PortableInvestigationError(
                f"run_sources[{index}].extensions must be an object"
            )
    _validate_policy(_object(value["policy"], "policy"))
    return value


def _validate_policy(policy: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "allowed_tools",
        "denied_tools",
        "budgets",
        "command_policy",
        "workspace_policy",
        "privacy_policy",
        "require_competing_hypothesis",
        "require_disconfirming_search",
    }
    allowed_fields = required | {"extensions"}
    if not required <= set(policy) or not set(policy) <= allowed_fields:
        raise PortableInvestigationError("policy fields do not match portable-investigation-policy/1.0")
    if "extensions" in policy and not isinstance(policy["extensions"], dict):
        raise PortableInvestigationError("policy.extensions must be an object")
    if policy["schema_version"] != "portable-investigation-policy/1.0":
        raise PortableInvestigationError("policy schema_version is invalid")
    allowed = _string_list(policy["allowed_tools"], "policy.allowed_tools")
    denied = _string_list(policy["denied_tools"], "policy.denied_tools")
    if len(set(allowed)) != len(allowed) or len(set(denied)) != len(denied):
        raise PortableInvestigationError("policy tool lists must contain unique values")
    if set(allowed) & set(denied):
        raise PortableInvestigationError("allowed_tools and denied_tools must not overlap")
    write_markers = {
        "write",
        "delete",
        "remove",
        "commit",
        "push",
        "merge",
        "rebase",
        "reset",
        "checkout",
        "publish",
    }
    unsafe = {
        tool
        for tool in allowed
        if tool in _WRITE_TOOLS
        or any(marker in tool.lower().replace("-", ".").split(".") for marker in write_markers)
    }
    if unsafe:
        raise PortableInvestigationError("portable investigator cannot authorize write tools")
    workspace = _object(policy["workspace_policy"], "policy.workspace_policy")
    if not {"read_only"} <= set(workspace) or not set(workspace) <= {
        "read_only",
        "allowed_paths",
        "denied_paths",
    }:
        raise PortableInvestigationError("workspace_policy fields are invalid")
    if workspace.get("read_only") is not True:
        raise PortableInvestigationError("portable investigator requires read_only workspace policy")
    for field in ("allowed_paths", "denied_paths"):
        if field in workspace:
            _string_list(workspace[field], f"policy.workspace_policy.{field}")
    if policy["require_competing_hypothesis"] is not True:
        raise PortableInvestigationError("portable investigator requires a competing hypothesis")
    if policy["require_disconfirming_search"] is not True:
        raise PortableInvestigationError("portable investigator requires disconfirming search")
    budgets = _object(policy["budgets"], "policy.budgets")
    required_budgets = {
        "max_tool_calls",
        "max_evidence_candidates",
        "max_verified_evidence",
        "max_run_records_read",
        "max_blob_bytes_read",
    }
    if set(budgets) != required_budgets:
        raise PortableInvestigationError("policy budgets are incomplete")
    for name, item in budgets.items():
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise PortableInvestigationError(f"policy budget {name} must be non-negative")
    command = _object(policy["command_policy"], "policy.command_policy")
    if set(command) != {"allow_execution", "allowed_command_prefixes"}:
        raise PortableInvestigationError("command_policy fields are invalid")
    if not isinstance(command.get("allow_execution"), bool):
        raise PortableInvestigationError("command_policy.allow_execution must be boolean")
    if not isinstance(command.get("allowed_command_prefixes"), list):
        raise PortableInvestigationError("allowed_command_prefixes must be an array")
    for prefix in command["allowed_command_prefixes"]:
        if (
            not isinstance(prefix, list)
            or not prefix
            or any(not isinstance(item, str) or not item for item in prefix)
        ):
            raise PortableInvestigationError(
                "allowed_command_prefixes entries must be non-empty argv arrays"
            )
    if command["allow_execution"] or command["allowed_command_prefixes"]:
        raise PortableInvestigationError(
            "portable investigator cannot authorize command execution in this runtime"
        )
    privacy = _object(policy["privacy_policy"], "policy.privacy_policy")
    if set(privacy) != {
        "redact_secrets",
        "export_reasoning",
        "export_raw_tool_output",
    }:
        raise PortableInvestigationError("privacy_policy fields are invalid")
    for field in ("redact_secrets", "export_reasoning", "export_raw_tool_output"):
        if not isinstance(privacy.get(field), bool):
            raise PortableInvestigationError(f"privacy_policy.{field} must be boolean")


def _validate_result(result: Mapping[str, Any]) -> None:
    """Fail closed before persisting a portable investigation result."""
    if not isinstance(result, Mapping):
        raise PortableInvestigationError("result must be an object")
    value = dict(result)
    expected = {
        "schema_version",
        "investigation_id",
        "question",
        "task",
        "hypotheses",
        "requested_evidence",
        "run_sources",
        "record_sources",
        "verification_sources",
        "policy",
        "status",
        "observations",
        "evidence_candidates",
        "verified_evidence",
        "findings",
        "ledger",
        "disconfirming_search",
        "unresolved",
        "usage",
        "stop",
    }
    if set(value) != expected:
        raise PortableInvestigationError(
            "result fields do not match portable-investigation-result/1.0"
        )
    if value["schema_version"] != "portable-investigation-result/1.0":
        raise PortableInvestigationError("result schema_version is invalid")
    investigation_id = value["investigation_id"]
    _nonempty(investigation_id, "result.investigation_id")
    _nonempty(value["question"], "result.question")
    if value["status"] not in {
        "supported",
        "partially_supported",
        "unsupported",
        "conflicted",
        "unknown",
    }:
        raise PortableInvestigationError(
            "portable investigation result status is invalid"
        )
    task = _object(value["task"], "result.task")
    allowed_task_fields = {
        "task_id",
        "request",
        "repository",
        "workspace_id",
        "base_ref",
        "head_ref",
    }
    if not {"task_id", "request"} <= set(task) or not set(task) <= allowed_task_fields:
        raise PortableInvestigationError("result.task fields are invalid")
    for field, item in task.items():
        if not isinstance(item, str) or (field in {"task_id", "request"} and not item):
            raise PortableInvestigationError(f"result.task.{field} must be a string")
    hypotheses = _object(value["hypotheses"], "result.hypotheses")
    if set(hypotheses) != {"primary", "competing"}:
        raise PortableInvestigationError("result.hypotheses fields are invalid")
    _nonempty(hypotheses["primary"], "result.hypotheses.primary")
    _string_list(
        hypotheses["competing"],
        "result.hypotheses.competing",
        nonempty=True,
    )
    requested_evidence = _string_list(
        value["requested_evidence"],
        "result.requested_evidence",
    )
    if len(requested_evidence) != len(set(requested_evidence)):
        raise PortableInvestigationError(
            "result.requested_evidence must contain unique values"
        )
    run_sources = value["run_sources"]
    _validate_persisted_run_sources(run_sources)
    _validate_policy(_object(value["policy"], "result.policy"))
    if value["policy"]["privacy_policy"]["redact_secrets"]:
        _reject_secret_like_stable_value(value, "result")
    verified_evidence = value["verified_evidence"]
    verification_sources = value["verification_sources"]
    if not isinstance(verified_evidence, list) or any(
        not isinstance(item, dict) for item in verified_evidence
    ):
        raise PortableInvestigationError(
            "result.verified_evidence must be an array of objects"
        )
    if not isinstance(verification_sources, list) or any(
        not isinstance(item, dict) for item in verification_sources
    ):
        raise PortableInvestigationError(
            "result.verification_sources must be an array of objects"
        )
    observations = value["observations"]
    candidates = value["evidence_candidates"]
    if not isinstance(observations, list) or any(
        not isinstance(item, dict) for item in observations
    ):
        raise PortableInvestigationError("result.observations must be an array of objects")
    if not isinstance(candidates, list) or any(
        not isinstance(item, dict) for item in candidates
    ):
        raise PortableInvestigationError(
            "result.evidence_candidates must be an array of objects"
        )
    observation_ids = {
        item.get("id")
        for item in observations
        if item.get("investigation_id") == investigation_id
        and isinstance(item.get("id"), str)
        and item["id"]
    }
    if len(observation_ids) != len(observations):
        raise PortableInvestigationError(
            "result observations must have unique IDs bound to the investigation"
        )
    for observation in observations:
        _validate_persisted_observation(observation)
    candidate_ids: set[str] = set()
    candidate_observation_refs: dict[str, set[str]] = {}
    actual_counter_refs: set[str] = set()
    for candidate in candidates:
        identifier = candidate.get("id")
        _validate_persisted_candidate(candidate)
        if (
            candidate.get("investigation_id") != investigation_id
            or not isinstance(identifier, str)
            or not identifier
            or identifier in candidate_ids
            or candidate.get("status") not in {"unverified", "verified", "rejected", "conflicted"}
            or candidate.get("verification_required")
            is not (candidate.get("status") == "unverified")
            or candidate.get("proposed_strength") not in {"context_only", "observed"}
            or not set(candidate.get("observation_refs", [])) <= observation_ids
        ):
            raise PortableInvestigationError(
                "result candidates must be unique, unverified, and bound to observations"
            )
        candidate_ids.add(identifier)
        candidate_observation_refs[identifier] = set(candidate["observation_refs"])
        if candidate["candidate_type"] == "counter_evidence":
            actual_counter_refs.add(identifier)
    observation_source_refs = {
        item["id"]: set(item["source_refs"]) for item in observations
    }
    findings = value["findings"]
    if not isinstance(findings, list) or any(not isinstance(item, dict) for item in findings):
        raise PortableInvestigationError("result.findings must be an array of objects")
    for finding in findings:
        _validate_persisted_finding(
            finding,
            observation_ids,
            candidate_ids,
            actual_counter_refs,
        )
        if finding.get("status") != value["status"]:
            raise PortableInvestigationError(
                "finding status must match the investigation status"
            )
    evidence_ids = _validate_verified_evidence(
        verified_evidence,
        verification_sources,
        candidate_ids,
        observation_ids,
        {item["id"] for item in findings},
    )
    for finding in findings:
        if not set(finding["evidence_refs"]) <= evidence_ids:
            raise PortableInvestigationError(
                "result finding cites unknown verified evidence"
            )
    supporting = any(item["supports"] for item in verified_evidence)
    contradicting = any(item["contradicts"] for item in verified_evidence)
    derived_status = (
        "conflicted"
        if supporting and contradicting
        else "supported"
        if supporting
        else "unsupported"
        if contradicting
        else "unknown"
    )
    if value["status"] != derived_status:
        raise PortableInvestigationError(
            "result status does not match verified evidence disposition"
        )
    unresolved = _string_list(value["unresolved"], "result.unresolved")
    if value["status"] == "unknown" and not unresolved:
        raise PortableInvestigationError("unknown result requires unresolved questions")
    usage = _object(value["usage"], "result.usage")
    expected_usage = {
        "run_records_read",
        "evidence_candidates",
        "verified_evidence",
        "tool_calls",
    }
    if set(usage) != expected_usage:
        raise PortableInvestigationError("result.usage fields are invalid")
    for name, item in usage.items():
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise PortableInvestigationError(f"result.usage.{name} must be non-negative")
    if (
        usage["evidence_candidates"] != len(candidates)
        or usage["verified_evidence"] != len(verified_evidence)
    ):
        raise PortableInvestigationError("result.usage does not match persisted records")
    budgets = value["policy"]["budgets"]
    if (
        usage["verified_evidence"] > budgets["max_verified_evidence"]
        or usage["tool_calls"] > budgets["max_tool_calls"]
    ):
        raise PortableInvestigationError("result.usage exceeds the declared verification budget")
    disconfirming = _object(
        value["disconfirming_search"],
        "result.disconfirming_search",
    )
    if set(disconfirming) != {
        "performed",
        "searched_record_refs",
        "counter_evidence_candidate_refs",
    }:
        raise PortableInvestigationError("result.disconfirming_search fields are invalid")
    if not isinstance(disconfirming["performed"], bool):
        raise PortableInvestigationError(
            "result.disconfirming_search.performed must be boolean"
        )
    searched = _string_list(
        disconfirming["searched_record_refs"],
        "result.disconfirming_search.searched_record_refs",
    )
    if len(searched) != len(set(searched)):
        raise PortableInvestigationError("searched_record_refs must be unique")
    if disconfirming["performed"] != bool(searched):
        raise PortableInvestigationError(
            "disconfirming search performed state must match searched records"
        )
    _validate_record_source_bindings(
        value["record_sources"],
        run_sources,
        set(searched),
    )
    counter_refs = _string_list(
        disconfirming["counter_evidence_candidate_refs"],
        "result.disconfirming_search.counter_evidence_candidate_refs",
    )
    if set(counter_refs) != actual_counter_refs:
        raise PortableInvestigationError(
            "disconfirming search must disclose every counter-evidence candidate"
        )
    for observation_id, source_refs in observation_source_refs.items():
        if not source_refs <= set(searched):
            raise PortableInvestigationError(
                f"result observation {observation_id} cites an unsearched Run Record"
            )
    for candidate in candidates:
        if not set(candidate["source_refs"]) <= set(searched):
            raise PortableInvestigationError(
                "result candidate cites an unsearched Run Record"
            )
    if usage["run_records_read"] != len(searched):
        raise PortableInvestigationError(
            "result.usage does not match searched Run Records"
        )
    verification_ledger = [
        item
        for item in value["ledger"]
        if isinstance(item, dict)
        and item.get("action") in {"inspect_proof", "check_freshness"}
    ]
    if usage["tool_calls"] != len(verification_ledger):
        raise PortableInvestigationError(
            "result.usage tool_calls must match deterministic verification ledger entries"
        )
    ledger_verification_sources = {
        reference
        for item in verification_ledger
        for reference in item.get("input_refs", [])
    }
    if ledger_verification_sources != {
        item["id"] for item in verification_sources
    }:
        raise PortableInvestigationError(
            "result ledger must account for every verification source"
        )
    allowed_tools = set(value["policy"]["allowed_tools"])
    if any(item.get("tool_name") not in allowed_tools for item in verification_ledger):
        raise PortableInvestigationError(
            "result ledger contains a verification tool not authorized by policy"
        )
    _validate_result_ledger(
        value["ledger"],
        value["question"],
        observation_ids,
        candidate_ids,
        set(searched),
        len(hypotheses["competing"]),
        observation_source_refs,
        candidate_observation_refs,
        evidence_ids,
        {item["id"] for item in verification_sources},
    )
    stop = _object(value["stop"], "result.stop")
    if set(stop) != {"reason", "bounded_result", "explanation"}:
        raise PortableInvestigationError("result.stop fields are invalid")
    if stop["reason"] not in {
        "budget_exhausted",
        "tool_unavailable",
        "authorization_required",
        "question_answered",
        "unknown",
    }:
        raise PortableInvestigationError("result.stop.reason is invalid")
    if stop["bounded_result"] is not True:
        raise PortableInvestigationError("result.stop.bounded_result must be true")
    _nonempty(stop["explanation"], "result.stop.explanation")


def _validate_result_ledger(
    ledger: Any,
    question: str,
    observation_ids: set[str],
    candidate_ids: set[str],
    searched_record_refs: set[str],
    competing_count: int,
    observation_source_refs: Mapping[str, set[str]],
    candidate_observation_refs: Mapping[str, set[str]],
    evidence_ids: set[str],
    verification_source_ids: set[str],
) -> None:
    if not isinstance(ledger, list) or any(not isinstance(item, dict) for item in ledger):
        raise PortableInvestigationError("result.ledger must be an array of objects")
    seen: set[str] = set()
    allowed_actions = {
        "read_run_record",
        "record_observation",
        "propose_candidate",
        "inspect_proof",
        "check_freshness",
    }
    allowed_effects = {
        "supports_primary",
        "weakens_primary",
        "supports_competing",
        "weakens_competing",
        "no_change",
    }
    ledger_read_refs: list[str] = []
    for entry in ledger:
        required = {
            "id",
            "question",
            "hypothesis_ref",
            "action",
            "input_refs",
            "observation_refs",
            "evidence_candidate_refs",
            "effect",
            "explanation",
        }
        optional = {"output_ref", "tool_name"}
        if not required <= set(entry) or not set(entry) <= required | optional:
            raise PortableInvestigationError("result ledger entry fields are invalid")
        identifier = entry["id"]
        _nonempty(identifier, "result.ledger.id")
        if identifier in seen:
            raise PortableInvestigationError("result ledger IDs must be unique")
        seen.add(identifier)
        if entry["question"] != question:
            raise PortableInvestigationError("result ledger question does not match")
        hypothesis_ref = entry["hypothesis_ref"]
        _nonempty(hypothesis_ref, "result.ledger.hypothesis_ref")
        if hypothesis_ref != "primary":
            if not hypothesis_ref.startswith("competing:"):
                raise PortableInvestigationError("result ledger hypothesis reference is invalid")
            try:
                competing_index = int(hypothesis_ref.split(":", 1)[1])
            except ValueError as error:
                raise PortableInvestigationError(
                    "result ledger competing hypothesis reference is invalid"
                ) from error
            if competing_index < 0 or competing_index >= competing_count:
                raise PortableInvestigationError(
                    "result ledger cites an unknown competing hypothesis"
                )
        if entry["action"] not in allowed_actions or entry["effect"] not in allowed_effects:
            raise PortableInvestigationError("result ledger semantics are invalid")
        observation_refs = _string_list(
            entry["observation_refs"],
            "result.ledger.observation_refs",
        )
        candidate_refs = _string_list(
            entry["evidence_candidate_refs"],
            "result.ledger.evidence_candidate_refs",
        )
        input_refs = _string_list(entry["input_refs"], "result.ledger.input_refs")
        if "output_ref" in entry:
            _nonempty(entry["output_ref"], "result.ledger.output_ref")
        if "tool_name" in entry:
            _nonempty(entry["tool_name"], "result.ledger.tool_name")
        if not set(observation_refs) <= observation_ids:
            raise PortableInvestigationError("result ledger cites unknown observations")
        if not set(candidate_refs) <= candidate_ids:
            raise PortableInvestigationError("result ledger cites unknown candidates")
        if entry["action"] == "read_run_record":
            if entry.get("tool_name") != "run.read" or len(input_refs) != 1:
                raise PortableInvestigationError(
                    "read_run_record ledger entry requires run.read and one input"
                )
            if input_refs[0] not in searched_record_refs:
                raise PortableInvestigationError(
                    "read_run_record ledger entry cites an unsearched record"
                )
            ledger_read_refs.append(input_refs[0])
        elif entry["action"] == "record_observation":
            if len(observation_refs) != 1:
                raise PortableInvestigationError(
                    "record_observation ledger entry requires one Observation"
                )
            observation_id = observation_refs[0]
            if set(input_refs) != observation_source_refs[observation_id]:
                raise PortableInvestigationError(
                    "record_observation inputs must match Observation sources"
                )
            if entry.get("output_ref") != observation_id:
                raise PortableInvestigationError(
                    "record_observation output must match its Observation"
                )
        elif entry["action"] == "propose_candidate":
            if len(candidate_refs) != 1:
                raise PortableInvestigationError(
                    "propose_candidate ledger entry requires one candidate"
                )
            candidate_id = candidate_refs[0]
            if set(input_refs) != candidate_observation_refs[candidate_id]:
                raise PortableInvestigationError(
                    "propose_candidate inputs must match candidate Observations"
                )
            if entry.get("output_ref") != candidate_id:
                raise PortableInvestigationError(
                    "propose_candidate output must match its candidate"
                )
        elif entry["action"] in {"inspect_proof", "check_freshness"}:
            expected_tool = {
                "inspect_proof": "proof.inspect",
                "check_freshness": "freshness.check",
            }[entry["action"]]
            if entry.get("tool_name") != expected_tool:
                raise PortableInvestigationError(
                    f"{entry['action']} ledger entry requires {expected_tool}"
                )
            if len(input_refs) != 1 or input_refs[0] not in verification_source_ids:
                raise PortableInvestigationError(
                    "verification ledger input must cite one verification source"
                )
            if "output_ref" in entry and entry.get("output_ref") not in evidence_ids:
                raise PortableInvestigationError(
                    "verification ledger output must cite verified evidence"
                )
            if entry["action"] == "check_freshness" and not candidate_refs:
                raise PortableInvestigationError(
                    "verification ledger must cite at least one Evidence Candidate"
                )
        _nonempty(entry["explanation"], "result.ledger.explanation")
    if len(ledger_read_refs) != len(set(ledger_read_refs)):
        raise PortableInvestigationError("result ledger repeats a Run Record read")
    if set(ledger_read_refs) != searched_record_refs:
        raise PortableInvestigationError(
            "result ledger must account for every searched Run Record"
        )


def _validate_persisted_observation(value: dict[str, Any]) -> None:
    expected = {
        "id",
        "investigation_id",
        "type",
        "statement",
        "source_refs",
        "proves",
        "does_not_prove",
        "reliability",
        "limitations",
    }
    if set(value) != expected:
        raise PortableInvestigationError("result observation fields are invalid")
    for field in ("id", "investigation_id", "statement"):
        _nonempty(value[field], f"result.observation.{field}")
    if value["type"] not in {
        "agent_statement",
        "agent_tool_call",
        "agent_tool_result",
        "agent_reasoning",
        "run_sequence",
        "run_metadata",
    }:
        raise PortableInvestigationError("result observation type is invalid")
    if value["reliability"] not in {
        "self_report",
        "recorded_behavior",
        "recorded_tool_output",
    }:
        raise PortableInvestigationError("result observation reliability is invalid")
    for field in ("source_refs", "proves", "does_not_prove", "limitations"):
        items = _string_list(value[field], f"result.observation.{field}")
        if field in {"source_refs", "proves", "does_not_prove"} and not items:
            raise PortableInvestigationError(
                f"result.observation.{field} must not be empty"
            )


def _validate_persisted_candidate(value: dict[str, Any]) -> None:
    expected = {
        "id",
        "investigation_id",
        "proposition",
        "candidate_type",
        "observation_refs",
        "source_refs",
        "verification_required",
        "proposed_evidence_kind",
        "proposed_strength",
        "status",
        "verification_plan",
    }
    if set(value) != expected:
        raise PortableInvestigationError("result candidate fields are invalid")
    for field in ("id", "investigation_id", "proposition"):
        _nonempty(value[field], f"result.candidate.{field}")
    if value["candidate_type"] not in {
        "agent_claim",
        "tool_observation",
        "code_observation",
        "command_observation",
        "authorization_observation",
        "counter_evidence",
    }:
        raise PortableInvestigationError("result candidate type is invalid")
    if value["proposed_evidence_kind"] not in {
        "git_fact",
        "file_fact",
        "command_receipt",
        "test_result",
        "artifact_fact",
        "freshness_fact",
        "authority_fact",
        "run_observation",
    }:
        raise PortableInvestigationError("result candidate evidence kind is invalid")
    if value["status"] not in {"unverified", "verified", "rejected", "conflicted"}:
        raise PortableInvestigationError("result candidate status is invalid")
    if not isinstance(value["verification_required"], bool):
        raise PortableInvestigationError(
            "result candidate verification_required must be boolean"
        )
    _string_list(
        value["observation_refs"],
        "result.candidate.observation_refs",
        nonempty=True,
    )
    _string_list(
        value["source_refs"],
        "result.candidate.source_refs",
        nonempty=True,
    )
    plan = value["verification_plan"]
    if not isinstance(plan, list) or not plan:
        raise PortableInvestigationError(
            "result candidate verification_plan must not be empty"
        )
    for step in plan:
        if not isinstance(step, dict) or set(step) != {"action", "purpose"}:
            raise PortableInvestigationError(
                "result candidate verification step fields are invalid"
            )
        _nonempty(step["action"], "result.candidate.verification_plan.action")
        _nonempty(step["purpose"], "result.candidate.verification_plan.purpose")


def _validate_persisted_finding(
    value: dict[str, Any],
    observation_ids: set[str],
    candidate_ids: set[str],
    actual_counter_refs: set[str],
) -> None:
    expected = {
        "id",
        "statement",
        "status",
        "evidence_refs",
        "counter_evidence_candidate_refs",
        "observation_refs",
        "limitations",
    }
    if set(value) != expected:
        raise PortableInvestigationError("result finding fields are invalid")
    _nonempty(value["id"], "result.finding.id")
    _nonempty(value["statement"], "result.finding.statement")
    evidence_refs = _string_list(
        value["evidence_refs"],
        "result.finding.evidence_refs",
    )
    counter_refs = _string_list(
        value["counter_evidence_candidate_refs"],
        "result.finding.counter_evidence_candidate_refs",
    )
    observation_refs = _string_list(
        value["observation_refs"],
        "result.finding.observation_refs",
    )
    _string_list(value["limitations"], "result.finding.limitations")
    if value["status"] not in {
        "supported",
        "partially_supported",
        "unsupported",
        "conflicted",
        "unknown",
    }:
        raise PortableInvestigationError("result finding status is invalid")
    if set(counter_refs) != actual_counter_refs:
        raise PortableInvestigationError(
            "result finding must disclose every counter-evidence candidate"
        )
    if not set(observation_refs) <= observation_ids:
        raise PortableInvestigationError("result finding cites unknown observations")


def _validate_verified_evidence(
    evidence: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    candidate_ids: set[str],
    observation_ids: set[str],
    finding_ids: set[str],
) -> set[str]:
    source_ids: set[str] = set()
    for source in sources:
        try:
            _validate_source(source)
        except BundleError as error:
            raise PortableInvestigationError(
                f"result verification source is invalid: {error}"
            ) from error
        source_id = source["id"]
        if source_id in source_ids:
            raise PortableInvestigationError(
                "result verification source IDs must be unique"
            )
        source_ids.add(source_id)

    evidence_ids: set[str] = set()
    referenced_sources: set[str] = set()
    for item in evidence:
        try:
            _validate_evidence(item)
        except BundleError as error:
            raise PortableInvestigationError(
                f"result verified evidence is invalid: {error}"
            ) from error
        evidence_id = item["id"]
        if evidence_id in evidence_ids:
            raise PortableInvestigationError(
                "result verified evidence IDs must be unique"
            )
        evidence_ids.add(evidence_id)
        referenced_sources.update(item["source_refs"])
        if not set(item["supports"]) <= finding_ids or not set(
            item["contradicts"]
        ) <= finding_ids:
            raise PortableInvestigationError(
                "result verified evidence cites an unknown finding"
            )
        extensions = item.get("extensions")
        if not isinstance(extensions, dict) or set(extensions) != {
            "candidate_refs",
            "observation_refs",
        }:
            raise PortableInvestigationError(
                "result verified evidence requires candidate and Observation bindings"
            )
        bound_candidates = _string_list(
            extensions["candidate_refs"],
            "result.verified_evidence.extensions.candidate_refs",
            nonempty=True,
        )
        bound_observations = _string_list(
            extensions["observation_refs"],
            "result.verified_evidence.extensions.observation_refs",
            nonempty=True,
        )
        if not set(bound_candidates) <= candidate_ids or not set(
            bound_observations
        ) <= observation_ids:
            raise PortableInvestigationError(
                "result verified evidence bindings cite unknown records"
            )
    if not referenced_sources <= source_ids:
        raise PortableInvestigationError(
            "result verified evidence cites an unknown verification source"
        )
    return evidence_ids


def _bind_run_sources(
    run_sources: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    declared: dict[str, dict[str, Any]] = {}
    for source in run_sources:
        run_group_id = source["run_group_id"]
        if run_group_id in declared:
            raise PortableInvestigationError("run_sources run_group_id must be unique")
        declared[run_group_id] = source
    actual_groups: set[str] = set()
    meta_groups: set[str] = set()
    declared_types_by_group = {
        group_id: source["source_type"] for group_id, source in declared.items()
    }
    for record in records:
        _verify_run_record_identity(record)
        identity = record.get("source_identity")
        if not isinstance(identity, dict):
            raise PortableInvestigationError(
                "Run Record source_identity must be an object"
            )
        run_group_id = identity.get("run_group_id")
        if not isinstance(run_group_id, str) or not run_group_id:
            raise PortableInvestigationError(
                "Run Record source_identity.run_group_id must be a non-empty string"
            )
        if run_group_id not in declared:
            raise PortableInvestigationError(
                "Run Record belongs to an undeclared run source"
            )
        actual_groups.add(run_group_id)
        if record.get("record_type") == "meta":
            source_type = record.get("source_type")
            if (
                not isinstance(source_type, str)
                or source_type != declared_types_by_group[run_group_id]
            ):
                raise PortableInvestigationError(
                    "Run Record source_type does not match its declared run source"
                )
            meta_groups.add(run_group_id)
    if actual_groups != set(declared):
        raise PortableInvestigationError(
            "run_sources must exactly identify the supplied Run Record groups"
        )
    if meta_groups != set(declared):
        raise PortableInvestigationError(
            "each declared run source requires a bound Meta Record"
        )
    calls_by_record_id = {
        record["record_id"]: record
        for record in records
        if record.get("record_type") == "tool_call"
    }
    for record in records:
        if record.get("record_type") != "tool_result":
            continue
        linked_record_id = record.get("linked_tool_call_record_id")
        if linked_record_id is None:
            continue
        linked_call = calls_by_record_id.get(linked_record_id)
        if (
            linked_call is None
            or linked_call.get("tool_call_id") != record.get("tool_call_id")
        ):
            raise PortableInvestigationError(
                "Tool Result link must target a Tool Call with the same tool_call_id"
            )


def _verify_run_record_identity(record: dict[str, Any]) -> None:
    if record.get("schema_version") != "canonical-run-record/1.0":
        raise PortableInvestigationError("Run Record schema_version is unsupported")
    identity = record.get("source_identity")
    if not isinstance(identity, dict) or set(identity) != {
        "run_group_id",
        "stable_source_record_id",
        "identity_kind",
        "source_order_id",
        "record_id",
        "content_hash",
    }:
        raise PortableInvestigationError("Run Record source_identity fields are invalid")
    for field in (
        "run_group_id",
        "stable_source_record_id",
        "source_order_id",
        "record_id",
        "content_hash",
    ):
        _nonempty(identity[field], f"Run Record source_identity.{field}")
    if identity["identity_kind"] not in {
        "native",
        "location",
        "content",
        "synthetic",
    }:
        raise PortableInvestigationError(
            "Run Record source_identity.identity_kind is invalid"
        )
    if record.get("record_id") != identity["record_id"]:
        raise PortableInvestigationError(
            "Run Record record_id does not match source_identity.record_id"
        )
    for field in ("record_id", "content_hash"):
        if not _is_sha256(identity[field]):
            raise PortableInvestigationError(
                f"Run Record source_identity.{field} must be lowercase SHA-256"
            )
    linked_record_id = record.get("linked_tool_call_record_id")
    if linked_record_id is not None and not _is_sha256(linked_record_id):
        raise PortableInvestigationError(
            "Tool Result linked_tool_call_record_id must be lowercase SHA-256"
        )
    semantic_fields = {
        key: value
        for key, value in record.items()
        if key
        not in {
            "schema_version",
            "record_type",
            "record_id",
            "timestamp",
            "source_identity",
        }
    }
    if record.get("record_type") == "tool_result":
        semantic_fields["linked_tool_call_record_id"] = None
    expected_hash = hashlib.sha256(
        _canonical_bytes(
            {
                "record_type": record.get("record_type"),
                **semantic_fields,
            }
        )
    ).hexdigest()
    if identity["content_hash"] != expected_hash:
        raise PortableInvestigationError(
            "Run Record content_hash does not match its semantic content"
        )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _record_source_bindings(
    records: list[dict[str, Any]],
    run_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_types = {
        item["run_group_id"]: item["source_type"] for item in run_sources
    }
    bindings: list[dict[str, Any]] = []
    for record in records:
        identity = record["source_identity"]
        bindings.append(
            {
                "id": record["record_id"],
                "run_group_id": identity["run_group_id"],
                "identity_kind": identity["identity_kind"],
                "content_hash": identity["content_hash"],
                "source_type": source_types[identity["run_group_id"]],
                "schema_version": record.get(
                    "schema_version",
                    "canonical-run-record/1.0",
                ),
            }
        )
    return bindings


def _validate_persisted_run_sources(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise PortableInvestigationError(
            "result.run_sources must be a non-empty array"
        )
    groups: set[str] = set()
    source_ids: set[str] = set()
    allowed = {"id", "source_type", "run_group_id", "extensions"}
    for source in value:
        if (
            not isinstance(source, dict)
            or not {"id", "source_type", "run_group_id"} <= set(source)
            or not set(source) <= allowed
        ):
            raise PortableInvestigationError("result.run_sources fields are invalid")
        for field in ("id", "source_type", "run_group_id"):
            _nonempty(source[field], f"result.run_sources.{field}")
        if source["id"] in source_ids or source["run_group_id"] in groups:
            raise PortableInvestigationError(
                "result.run_sources IDs and Run Group IDs must be unique"
            )
        source_ids.add(source["id"])
        groups.add(source["run_group_id"])
        if "extensions" in source and not isinstance(source["extensions"], dict):
            raise PortableInvestigationError(
                "result.run_sources.extensions must be an object"
            )


def _validate_record_source_bindings(
    value: Any,
    run_sources: list[dict[str, Any]],
    searched_record_refs: set[str],
) -> None:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise PortableInvestigationError(
            "result.record_sources must be an array of objects"
        )
    expected_fields = {
        "id",
        "run_group_id",
        "identity_kind",
        "content_hash",
        "source_type",
        "schema_version",
    }
    declared = {
        item["run_group_id"]: item["source_type"] for item in run_sources
    }
    identifiers: set[str] = set()
    for source in value:
        if set(source) != expected_fields:
            raise PortableInvestigationError(
                "result.record_source fields are invalid"
            )
        for field in (
            "id",
            "run_group_id",
            "content_hash",
            "source_type",
            "schema_version",
        ):
            _nonempty(source[field], f"result.record_source.{field}")
        if source["id"] in identifiers:
            raise PortableInvestigationError(
                "result.record_source IDs must be unique"
            )
        identifiers.add(source["id"])
        if source["identity_kind"] not in {
            "native",
            "location",
            "content",
            "synthetic",
        }:
            raise PortableInvestigationError(
                "result.record_source identity_kind is invalid"
            )
        if (
            source["run_group_id"] not in declared
            or source["source_type"] != declared[source["run_group_id"]]
        ):
            raise PortableInvestigationError(
                "result.record_source does not match its declared run source"
            )
        content_hash = source["content_hash"]
        if (
            len(content_hash) != 64
            or any(character not in "0123456789abcdef" for character in content_hash)
        ):
            raise PortableInvestigationError(
                "result.record_source content_hash must be lowercase SHA-256"
            )
    if identifiers != searched_record_refs:
        raise PortableInvestigationError(
            "result.record_sources must bind every searched Run Record"
        )


def _export_request_fields(request: Mapping[str, Any]) -> dict[str, Any]:
    privacy = request["policy"]["privacy_policy"]
    task = deepcopy(request["task"])
    hypotheses = deepcopy(request["hypotheses"])
    if not privacy["redact_secrets"]:
        return {
            "question": request["question"],
            "task": task,
            "hypotheses": hypotheses,
        }
    stable_values = {
        "investigation_id": request["investigation_id"],
        "task_id": task["task_id"],
        "task_bindings": {
            key: value
            for key, value in task.items()
            if key not in {"task_id", "request"}
        },
        "run_sources": request["run_sources"],
        "requested_evidence": request["requested_evidence"],
        "policy": request["policy"],
    }
    _reject_secret_like_stable_value(stable_values, "request stable fields")
    task["request"] = redact_text(task["request"])
    return {
        "question": redact_text(request["question"]),
        "task": task,
        "hypotheses": {
            "primary": redact_text(hypotheses["primary"]),
            "competing": [
                redact_text(statement) for statement in hypotheses["competing"]
            ],
        },
    }


def _reject_secret_like_stable_value(value: Any, label: str) -> None:
    if isinstance(value, str):
        if redact_text(value) != value:
            raise PortableInvestigationError(
                f"{label} contains secret-like material that cannot be safely rebound"
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_secret_like_stable_value(str(key), label)
            _reject_secret_like_stable_value(item, label)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_secret_like_stable_value(item, label)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PortableInvestigationError(f"{label} must be an object")
    return value


def _string_list(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise PortableInvestigationError(f"{label} must be an array of non-empty strings")
    if nonempty and not value:
        raise PortableInvestigationError(f"{label} must not be empty")
    return value


def _nonempty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise PortableInvestigationError(f"{label} must be a non-empty string")


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _apply_privacy_policy(
    observations: list[dict[str, Any]],
    privacy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for observation in observations:
        if observation["type"] == "agent_reasoning" and not privacy["export_reasoning"]:
            continue
        candidate = deepcopy(observation)
        for reference in candidate["source_refs"]:
            if privacy["redact_secrets"] and redact_text(reference) != reference:
                raise PortableInvestigationError(
                    "stable Run Record reference contains secret-like material"
                )
        if (
            candidate["type"] == "agent_tool_result"
            and not privacy["export_raw_tool_output"]
        ):
            candidate["statement"] = (
                "The normalized run contains a redacted result for the linked tool call."
            )
            candidate["limitations"] = [
                *candidate["limitations"],
                "raw_tool_output_not_exported",
            ]
        if privacy["redact_secrets"]:
            for field in ("statement",):
                candidate[field] = redact_text(candidate[field])
            for field in ("proves", "does_not_prove", "limitations"):
                candidate[field] = [redact_text(item) for item in candidate[field]]
        semantic = {
            "investigation_id": candidate["investigation_id"],
            "type": candidate["type"],
            "statement": candidate["statement"],
            "source_refs": candidate["source_refs"],
        }
        candidate["id"] = hashlib.sha256(_canonical_bytes(semantic)).hexdigest()
        result.append(candidate)
    return result


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PortableInvestigationError(f"result is not canonical JSON: {error}") from error
