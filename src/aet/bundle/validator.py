"""Fail-closed semantic validation for Portable Evidence Bundle v1."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .canonical import manifest_content_hash
from .integrity import validate_blobs, validate_integrity
from .loader import BundleError, load_bundle
from .markdown import render_bundle_markdown, render_consumer_guide


_INVESTIGATION_TYPES = {"scope", "verification", "freshness", "security", "authorization", "general"}
_CLAIM_STATUSES = {"supported", "partially_supported", "unsupported", "conflicted", "unknown"}
_BASIS_TYPES = {"deterministic", "reproduced", "corroborated", "observational", "mixed"}
_EVIDENCE_KINDS = {
    "git_fact",
    "file_fact",
    "command_receipt",
    "test_result",
    "artifact_fact",
    "freshness_fact",
    "authority_fact",
    "run_observation",
}
_STRENGTHS = {"context_only", "observed", "corroborated", "reproduced"}
_FRESHNESS = {"current", "relevant_files_changed", "workspace_changed", "environment_changed", "unknown"}
_OBSERVATION_TYPES = {
    "agent_statement",
    "agent_tool_call",
    "agent_tool_result",
    "agent_reasoning",
    "run_sequence",
    "run_metadata",
}
_SOURCE_TYPES = {"run_record", "git", "file", "command", "artifact", "user_instruction", "proof_receipt"}
_IDENTITY_KINDS = {"native", "location", "content", "synthetic"}
_DIAGNOSTIC_SEVERITIES = {"info", "warning", "error"}
_CONFLICT_TYPES = {
    "content_conflict",
    "workspace_conflict",
    "timestamp_conflict",
    "authority_conflict",
    "interpretation_conflict",
}
_RESOLUTION_STATUSES = {"resolved", "unresolved"}
_EXTENSIBLE_OBJECTS = {
    "manifest",
    "index",
    "claim",
    "evidence",
    "observation",
    "source",
    "diagnostic",
    "conflict",
    "policy",
}
_HYPOTHESIS_REF_PATTERN = re.compile(r"^(primary|competing:[A-Za-z0-9._-]+)$")


def validate_bundle(
    path: Path,
    *,
    max_blob_bytes: int = 64 * 1024 * 1024,
) -> dict[str, Any]:
    """Load and fully validate one directory Portable Evidence Bundle."""
    bundle = load_bundle(path, max_blob_bytes=max_blob_bytes)
    _validate_manifest(bundle)
    _validate_index(bundle)
    _validate_records(bundle)
    validate_integrity(bundle)
    validate_blobs(bundle)
    _validate_references(bundle)
    _validate_counter_evidence(bundle)
    return bundle


def _validate_manifest(bundle: dict[str, Any]) -> None:
    manifest = _object(bundle.get("manifest"), "manifest")
    _exact_keys(
        manifest,
        {"protocol", "bundle", "task", "producer", "investigation", "contents", "integrity"},
        "manifest",
    )
    protocol = _object(manifest["protocol"], "manifest.protocol")
    _exact_keys(protocol, {"name", "version", "schema_uri"}, "manifest.protocol")
    _enum(protocol.get("name"), {"portable-evidence-bundle"}, "protocol.name")
    _enum(protocol.get("version"), {"1.0"}, "protocol.version")
    _nonempty(protocol.get("schema_uri"), "protocol.schema_uri")

    identity = _object(manifest["bundle"], "manifest.bundle")
    _allowed_keys(identity, {"id", "created_at", "content_hash", "parent_bundle_id"}, "manifest.bundle")
    _require_keys(identity, {"id", "created_at", "content_hash"}, "manifest.bundle")
    _nonempty(identity["id"], "bundle.id")
    _nonempty(identity["created_at"], "bundle.created_at")
    _utc_timestamp(identity["created_at"], "bundle.created_at")
    _sha256(identity["content_hash"], "bundle.content_hash")
    if "parent_bundle_id" in identity:
        _nonempty(identity["parent_bundle_id"], "bundle.parent_bundle_id")

    task = _object(manifest["task"], "manifest.task")
    _allowed_keys(task, {"task_id", "request", "repository", "workspace_id", "base_ref", "head_ref"}, "manifest.task")
    _require_keys(task, {"task_id", "request"}, "manifest.task")
    _nonempty(task["task_id"], "task.task_id")
    _nonempty(task["request"], "task.request")
    _optional_strings(task, {"repository", "workspace_id", "base_ref", "head_ref"}, "task")

    producer = _object(manifest["producer"], "manifest.producer")
    _exact_keys(producer, {"name", "version"}, "manifest.producer")
    _enum(producer.get("name"), {"agent-engineering-toolkit"}, "producer.name")
    _nonempty(producer["version"], "producer.version")

    investigation = _object(manifest["investigation"], "manifest.investigation")
    _exact_keys(
        investigation,
        {"investigation_id", "investigation_type", "question", "scope", "limitations", "completed"},
        "manifest.investigation",
    )
    for field in ("investigation_id", "question"):
        _nonempty(investigation[field], f"investigation.{field}")
    _enum(investigation["investigation_type"], _INVESTIGATION_TYPES, "investigation.investigation_type")
    _string_list(investigation["scope"], "investigation.scope", unique=True)
    _string_list(investigation["limitations"], "investigation.limitations")
    _boolean(investigation["completed"], "investigation.completed")

    integrity = _object(manifest["integrity"], "manifest.integrity")
    _exact_keys(integrity, {"algorithm", "file_hashes"}, "manifest.integrity")
    _enum(integrity["algorithm"], {"sha256"}, "integrity.algorithm")
    hashes = _object(integrity["file_hashes"], "integrity.file_hashes")
    for relative, digest in hashes.items():
        _nonempty(relative, "integrity file path")
        _sha256(digest, f"integrity.file_hashes[{relative!r}]")
    content_hash = manifest_content_hash(manifest)
    if identity["content_hash"] != content_hash:
        raise BundleError(
            "integrity_error",
            "bundle.content_hash does not bind integrity.file_hashes",
        )


def _validate_index(bundle: dict[str, Any]) -> None:
    index = _object(bundle.get("index"), "index")
    _exact_keys(
        index,
        {
            "schema_version",
            "bundle_id",
            "question",
            "claim_refs",
            "evidence_refs",
            "observation_refs",
            "reading_order",
            "excluded",
            "archive_available",
            "consumer_guidance",
        },
        "index",
    )
    _enum(index["schema_version"], {"portable-evidence-bundle-index/1.0"}, "index.schema_version")
    _nonempty(index["bundle_id"], "index.bundle_id")
    _nonempty(index["question"], "index.question")
    for field in ("claim_refs", "evidence_refs", "observation_refs"):
        _string_list(index[field], f"index.{field}", unique=True)
    _string_list(index["reading_order"], "index.reading_order", nonempty=True)
    excluded = _object(index["excluded"], "index.excluded")
    _exact_keys(excluded, {"count", "reason"}, "index.excluded")
    _nonnegative_integer(excluded["count"], "index.excluded.count")
    _nonempty(excluded["reason"], "index.excluded.reason")
    _boolean(index["archive_available"], "index.archive_available")
    guidance = _object(index["consumer_guidance"], "index.consumer_guidance")
    _exact_keys(guidance, {"must", "must_not"}, "index.consumer_guidance")
    _string_list(guidance["must"], "consumer_guidance.must", nonempty=True)
    _string_list(guidance["must_not"], "consumer_guidance.must_not", nonempty=True)

    manifest = bundle["manifest"]
    if index["bundle_id"] != manifest["bundle"]["id"]:
        raise BundleError("reference_error", "index bundle_id does not match manifest")
    if index["question"] != manifest["investigation"]["question"]:
        raise BundleError("reference_error", "index question does not match manifest investigation")


def _validate_records(bundle: dict[str, Any]) -> None:
    for collection in ("claims", "evidence", "observations", "sources", "conflicts"):
        _unique_ids(bundle.get(collection), collection)
    for claim in bundle["claims"]:
        _validate_claim(claim)
    for evidence in bundle["evidence"]:
        _validate_evidence(evidence)
    for observation in bundle["observations"]:
        _validate_observation(observation)
    for source in bundle["sources"]:
        _validate_source(source)
    for diagnostic in bundle["diagnostics"]:
        _validate_diagnostic(diagnostic)
    for conflict in bundle["conflicts"]:
        _validate_conflict(conflict)
    for number, entry in enumerate(bundle["ledger"], start=1):
        _validate_ledger_entry(entry, number)
    _validate_policy(bundle["policy"])
    _validate_policy_semantics(bundle)
    _validate_grounding(bundle)
    _validate_budget_usage(bundle)
    if not isinstance(bundle["consumer_guide"], str) or not bundle["consumer_guide"].strip():
        raise BundleError("invalid_bundle", "consumer guide must be non-empty UTF-8 text")
    if bundle["consumer_guide"] != render_consumer_guide():
        raise BundleError(
            "projection_error",
            "consumer-guide.md is not the fixed v1 consumption boundary",
        )
    if not isinstance(bundle["report"], str):
        raise BundleError("invalid_bundle", "report must be UTF-8 text")
    if bundle["report"] != render_bundle_markdown(bundle):
        raise BundleError(
            "projection_error",
            "report.md is not the deterministic projection of portable Claims",
        )


def _validate_claim(value: dict[str, Any]) -> None:
    _allowed_keys(
        value,
        {
            "id",
            "statement",
            "status",
            "status_definition",
            "evidence_refs",
            "counter_evidence_refs",
            "observation_refs",
            "basis",
            "limitations",
            "smallest_next_action",
        },
        "claim",
    )
    _require_keys(
        value,
        {
            "id",
            "statement",
            "status",
            "status_definition",
            "evidence_refs",
            "counter_evidence_refs",
            "observation_refs",
            "basis",
            "limitations",
        },
        "claim",
    )
    for field in ("id", "statement", "status_definition"):
        _nonempty(value[field], f"claim.{field}")
    _enum(value["status"], _CLAIM_STATUSES, "claim.status")
    for field in ("evidence_refs", "counter_evidence_refs", "observation_refs"):
        _string_list(value[field], f"claim.{field}", unique=True)
    basis = _object(value["basis"], "claim.basis")
    _exact_keys(basis, {"type", "explanation"}, "claim.basis")
    _enum(basis["type"], _BASIS_TYPES, "claim.basis.type")
    _nonempty(basis["explanation"], "claim.basis.explanation")
    _string_list(value["limitations"], "claim.limitations")
    if "smallest_next_action" in value:
        _nonempty(value["smallest_next_action"], "claim.smallest_next_action")


def _validate_evidence(value: dict[str, Any]) -> None:
    _exact_keys(
        value,
        {
            "id",
            "proposition",
            "kind",
            "strength",
            "strength_definition",
            "source_refs",
            "bindings",
            "freshness",
            "supports",
            "contradicts",
            "limitations",
            "integrity",
        },
        "evidence",
    )
    for field in ("id", "proposition", "strength_definition"):
        _nonempty(value[field], f"evidence.{field}")
    _enum(value["kind"], _EVIDENCE_KINDS, "evidence.kind")
    _enum(value["strength"], _STRENGTHS, "evidence.strength")
    _string_list(value["source_refs"], "evidence.source_refs", unique=True, nonempty=True)
    _object(value["bindings"], "evidence.bindings")
    _allowed_keys(value["bindings"], {"task_id", "workspace_id", "repository", "commit", "paths", "command", "environment_hash"}, "evidence.bindings")
    _optional_strings(value["bindings"], {"task_id", "workspace_id", "repository", "commit"}, "evidence.bindings")
    if "paths" in value["bindings"]:
        _string_list(value["bindings"]["paths"], "evidence.bindings.paths", unique=True)
    if "command" in value["bindings"]:
        _string_list(value["bindings"]["command"], "evidence.bindings.command")
    if "environment_hash" in value["bindings"]:
        _sha256(value["bindings"]["environment_hash"], "evidence.bindings.environment_hash")
    freshness = _object(value["freshness"], "evidence.freshness")
    _allowed_keys(freshness, {"status", "checked_at", "explanation", "effect", "recommended_action"}, "evidence.freshness")
    _require_keys(freshness, {"status", "explanation", "effect"}, "evidence.freshness")
    _enum(freshness["status"], _FRESHNESS, "evidence.freshness.status")
    for field in ("explanation", "effect"):
        _nonempty(freshness[field], f"evidence.freshness.{field}")
    _optional_strings(freshness, {"checked_at", "recommended_action"}, "evidence.freshness")
    if "checked_at" in freshness:
        _utc_timestamp(freshness["checked_at"], "evidence.freshness.checked_at")
    for field in ("supports", "contradicts"):
        _string_list(value[field], f"evidence.{field}", unique=True)
    _string_list(value["limitations"], "evidence.limitations")
    integrity = _object(value["integrity"], "evidence.integrity")
    _allowed_keys(integrity, {"content_hash", "blob_ref", "truncated", "original_bytes"}, "evidence.integrity")
    _require_keys(integrity, {"content_hash", "truncated"}, "evidence.integrity")
    _sha256(integrity["content_hash"], "evidence.integrity.content_hash")
    _boolean(integrity["truncated"], "evidence.integrity.truncated")
    if "blob_ref" in integrity:
        _blob_ref(integrity["blob_ref"], "evidence.integrity.blob_ref")
    if "original_bytes" in integrity:
        _nonnegative_integer(integrity["original_bytes"], "evidence.integrity.original_bytes")
    if integrity["truncated"]:
        if "blob_ref" not in integrity or "original_bytes" not in integrity:
            raise BundleError(
                "invalid_bundle",
                "truncated evidence requires blob_ref and original_bytes",
            )


def _validate_observation(value: dict[str, Any]) -> None:
    _exact_keys(
        value,
        {"id", "type", "statement", "source_refs", "proves", "does_not_prove", "limitations"},
        "observation",
    )
    _nonempty(value["id"], "observation.id")
    _enum(value["type"], _OBSERVATION_TYPES, "observation.type")
    _nonempty(value["statement"], "observation.statement")
    _string_list(value["source_refs"], "observation.source_refs", unique=True, nonempty=True)
    _string_list(value["proves"], "observation.proves", nonempty=True)
    _string_list(value["does_not_prove"], "observation.does_not_prove", nonempty=True)
    _string_list(value["limitations"], "observation.limitations")


def _validate_source(value: dict[str, Any]) -> None:
    _exact_keys(value, {"id", "type", "locator", "provenance", "integrity"}, "source")
    _nonempty(value["id"], "source.id")
    _enum(value["type"], _SOURCE_TYPES, "source.type")
    locator = _object(value["locator"], "source.locator")
    _allowed_keys(locator, {"run_group_id", "record_id", "identity_kind", "repository", "commit", "path", "line_start", "line_end", "blob_ref"}, "source.locator")
    _optional_strings(locator, {"run_group_id", "record_id", "repository", "commit", "path"}, "source.locator")
    if "identity_kind" in locator:
        _enum(locator["identity_kind"], _IDENTITY_KINDS, "source.locator.identity_kind")
    for field in ("line_start", "line_end"):
        if field in locator:
            _positive_integer(locator[field], f"source.locator.{field}")
    if "line_start" in locator and "line_end" in locator and locator["line_end"] < locator["line_start"]:
        raise BundleError("invalid_bundle", "source locator line_end precedes line_start")
    if "blob_ref" in locator:
        _blob_ref(locator["blob_ref"], "source.locator.blob_ref")
    provenance = _object(value["provenance"], "source.provenance")
    _allowed_keys(provenance, {"source_type", "normalizer_version", "schema_version", "configuration_hash"}, "source.provenance")
    _optional_strings(provenance, {"source_type", "normalizer_version"}, "source.provenance")
    if "schema_version" in provenance and (
        isinstance(provenance["schema_version"], bool)
        or not isinstance(provenance["schema_version"], (str, int))
    ):
        raise BundleError("invalid_bundle", "source.provenance.schema_version must be a string or integer")
    if "configuration_hash" in provenance:
        _sha256(provenance["configuration_hash"], "source.provenance.configuration_hash")
    integrity = _object(value["integrity"], "source.integrity")
    _allowed_keys(integrity, {"content_hash"}, "source.integrity")
    if "content_hash" in integrity:
        _sha256(integrity["content_hash"], "source.integrity.content_hash")


def _validate_diagnostic(value: dict[str, Any]) -> None:
    _allowed_keys(value, {"code", "severity", "effect", "affected_observation_refs", "affected_evidence_refs", "recommended_action"}, "diagnostic")
    _require_keys(value, {"code", "severity", "effect", "affected_observation_refs", "affected_evidence_refs"}, "diagnostic")
    _nonempty(value["code"], "diagnostic.code")
    _enum(value["severity"], _DIAGNOSTIC_SEVERITIES, "diagnostic.severity")
    _nonempty(value["effect"], "diagnostic.effect")
    _string_list(value["affected_observation_refs"], "diagnostic.affected_observation_refs", unique=True)
    _string_list(value["affected_evidence_refs"], "diagnostic.affected_evidence_refs", unique=True)
    if "recommended_action" in value:
        _nonempty(value["recommended_action"], "diagnostic.recommended_action")


def _validate_conflict(value: dict[str, Any]) -> None:
    _exact_keys(value, {"id", "proposition", "evidence_refs", "conflict_type", "resolution_status", "explanation"}, "conflict")
    for field in ("id", "proposition", "explanation"):
        _nonempty(value[field], f"conflict.{field}")
    refs = _string_list(value["evidence_refs"], "conflict.evidence_refs", unique=True, nonempty=True)
    if len(refs) < 2:
        raise BundleError("invalid_bundle", "conflict.evidence_refs requires at least two records")
    _enum(value["conflict_type"], _CONFLICT_TYPES, "conflict.conflict_type")
    _enum(value["resolution_status"], _RESOLUTION_STATUSES, "conflict.resolution_status")


def _validate_policy(value: Any) -> None:
    policy = _object(value, "policy")
    _exact_keys(
        policy,
        {
            "schema_version",
            "allowed_tools",
            "denied_tools",
            "budgets",
            "command_policy",
            "workspace_policy",
            "privacy_policy",
            "require_competing_hypothesis",
            "require_disconfirming_search",
        },
        "policy",
    )
    _enum(policy["schema_version"], {"portable-investigation-policy/1.0"}, "policy.schema_version")
    _string_list(policy["allowed_tools"], "policy.allowed_tools", unique=True)
    _string_list(policy["denied_tools"], "policy.denied_tools", unique=True)
    overlap = set(policy["allowed_tools"]) & set(policy["denied_tools"])
    if overlap:
        raise BundleError(
            "policy_error",
            "tools cannot be both allowed and denied: " + ", ".join(sorted(overlap)),
        )
    budgets = _object(policy["budgets"], "policy.budgets")
    budget_fields = {"max_tool_calls", "max_evidence_candidates", "max_verified_evidence", "max_run_records_read", "max_blob_bytes_read"}
    _exact_keys(budgets, budget_fields, "policy.budgets")
    for field in budget_fields:
        _nonnegative_integer(budgets[field], f"policy.budgets.{field}")
    command = _object(policy["command_policy"], "policy.command_policy")
    _exact_keys(command, {"allow_execution", "allowed_command_prefixes"}, "policy.command_policy")
    _boolean(command["allow_execution"], "policy.command_policy.allow_execution")
    prefixes = command["allowed_command_prefixes"]
    if not isinstance(prefixes, list):
        raise BundleError("invalid_bundle", "allowed_command_prefixes must be an array")
    for index, prefix in enumerate(prefixes):
        _string_list(prefix, f"allowed_command_prefixes[{index}]", nonempty=True)
    workspace = _object(policy["workspace_policy"], "policy.workspace_policy")
    _allowed_keys(workspace, {"read_only", "allowed_paths", "denied_paths"}, "policy.workspace_policy")
    _require_keys(workspace, {"read_only"}, "policy.workspace_policy")
    _boolean(workspace["read_only"], "policy.workspace_policy.read_only")
    for field in ("allowed_paths", "denied_paths"):
        if field in workspace:
            _string_list(workspace[field], f"policy.workspace_policy.{field}")
    privacy = _object(policy["privacy_policy"], "policy.privacy_policy")
    _exact_keys(privacy, {"redact_secrets", "export_reasoning", "export_raw_tool_output"}, "policy.privacy_policy")
    for field in privacy:
        _boolean(privacy[field], f"policy.privacy_policy.{field}")
    _boolean(policy["require_competing_hypothesis"], "policy.require_competing_hypothesis")
    _boolean(policy["require_disconfirming_search"], "policy.require_disconfirming_search")


def _validate_ledger_entry(value: Any, number: int) -> None:
    entry = _object(value, f"ledger record {number}")
    required = {
        "id",
        "timestamp",
        "question",
        "action",
        "observation_refs",
        "evidence_candidate_refs",
        "effect",
        "explanation",
    }
    optional = {"hypothesis_ref", "tool_name", "input_ref", "output_ref"}
    _require_keys(entry, required, f"ledger record {number}")
    _allowed_keys(entry, required | optional, f"ledger record {number}")
    for field in ("id", "timestamp", "question", "explanation"):
        _nonempty(entry[field], f"ledger record {number}.{field}")
    _utc_timestamp(entry["timestamp"], f"ledger record {number}.timestamp")
    _enum(
        entry["action"],
        {
            "read_run_record",
            "read_file",
            "inspect_git",
            "inspect_proof",
            "check_freshness",
            "execute_authorized_command",
            "record_observation",
            "propose_candidate",
        },
        f"ledger record {number}.action",
    )
    _enum(
        entry["effect"],
        {
            "supports_primary",
            "weakens_primary",
            "supports_competing",
            "weakens_competing",
            "no_change",
        },
        f"ledger record {number}.effect",
    )
    for field in ("observation_refs", "evidence_candidate_refs"):
        _string_list(entry[field], f"ledger record {number}.{field}", unique=True)
    _optional_strings(entry, optional, f"ledger record {number}")
    if "hypothesis_ref" in entry:
        reference = entry["hypothesis_ref"]
        if _HYPOTHESIS_REF_PATTERN.fullmatch(reference) is None:
            raise BundleError(
                "invalid_bundle",
                f"ledger record {number}.hypothesis_ref has unsupported semantics",
            )
    if entry["action"] in {"read_run_record", "read_file"} and "input_ref" not in entry:
        raise BundleError(
            "invalid_bundle",
            f"ledger record {number}.{entry['action']} requires input_ref",
        )
    if entry["action"] == "propose_candidate" and not entry["evidence_candidate_refs"]:
        raise BundleError(
            "invalid_bundle",
            f"ledger record {number}.propose_candidate requires an evidence candidate reference",
        )


def _validate_policy_semantics(bundle: dict[str, Any]) -> None:
    policy = bundle["policy"]
    allowed = set(policy["allowed_tools"])
    denied = set(policy["denied_tools"])
    sources = {item["id"]: item for item in bundle["sources"]}
    tool_actions = {
        "read_run_record",
        "read_file",
        "inspect_git",
        "inspect_proof",
        "check_freshness",
        "execute_authorized_command",
    }
    for entry in bundle["ledger"]:
        if entry["action"] in tool_actions:
            tool_name = entry.get("tool_name")
            if not tool_name:
                raise BundleError(
                    "policy_error",
                    f"ledger tool action requires tool_name: {entry['id']}",
                )
            if tool_name not in allowed or tool_name in denied:
                raise BundleError(
                    "policy_error",
                    f"ledger tool is not allowed by policy: {tool_name}",
                )
            if entry["action"] == "read_run_record":
                source = sources.get(entry.get("input_ref"))
                if tool_name != "run.read" or not source or source["type"] != "run_record":
                    raise BundleError(
                        "policy_error",
                        "read_run_record requires run.read and a run_record Source",
                    )
        if entry["action"] == "execute_authorized_command":
            if not policy["command_policy"]["allow_execution"]:
                raise BundleError(
                    "policy_error",
                    "ledger records command execution while policy forbids execution",
                )
            output = next(
                (
                    item
                    for item in bundle["evidence"]
                    if item["id"] == entry.get("output_ref")
                ),
                None,
            )
            command = output.get("bindings", {}).get("command") if output else None
            if not isinstance(command, list) or not command:
                raise BundleError(
                    "policy_error",
                    "command execution requires an output Evidence command binding",
                )
            prefixes = policy["command_policy"]["allowed_command_prefixes"]
            if not any(command[: len(prefix)] == prefix for prefix in prefixes):
                raise BundleError(
                    "policy_error",
                    "executed command is outside allowed command prefixes",
                )

    if policy["require_competing_hypothesis"]:
        if not any(
            entry.get("hypothesis_ref", "").startswith("competing:")
            for entry in bundle["ledger"]
        ):
            raise BundleError(
                "policy_error",
                "policy requires a competing hypothesis ledger reference",
            )
    if policy["require_disconfirming_search"]:
        if not any(
            entry["action"] in tool_actions
            and entry.get("hypothesis_ref", "").startswith("competing:")
            for entry in bundle["ledger"]
        ):
            raise BundleError(
                "policy_error",
                "policy requires a recorded tool search against a competing hypothesis",
            )

    workspace = policy["workspace_policy"]
    allowed_paths = workspace.get("allowed_paths", [])
    denied_paths = workspace.get("denied_paths", [])
    for entry in bundle["ledger"]:
        if entry["action"] != "read_file":
            continue
        source = sources.get(entry.get("input_ref"))
        path = source.get("locator", {}).get("path") if source else None
        if not isinstance(path, str):
            raise BundleError(
                "policy_error",
                f"read_file requires a Source path: {entry['id']}",
            )
        normalized = _portable_relative_path(path, f"ledger {entry['id']} input path")
        if any(_path_is_within(normalized, denied) for denied in denied_paths):
            raise BundleError(
                "policy_error",
                f"read_file targets a denied path: {path}",
            )
        if allowed_paths and not any(
            _path_is_within(normalized, allowed) for allowed in allowed_paths
        ):
            raise BundleError(
                "policy_error",
                f"read_file targets a path outside allowed_paths: {path}",
            )

    privacy = policy["privacy_policy"]
    if not privacy["export_reasoning"] and any(
        item["type"] == "agent_reasoning" for item in bundle["observations"]
    ):
        raise BundleError(
            "privacy_error",
            "agent reasoning is exported while privacy policy forbids it",
        )
    if not privacy["export_raw_tool_output"]:
        for evidence in bundle["evidence"]:
            if (
                evidence["kind"] in {"command_receipt", "test_result"}
                and "blob_ref" in evidence["integrity"]
            ):
                raise BundleError(
                    "privacy_error",
                    "raw command output Blob is exported while privacy policy forbids it",
                )


def _validate_grounding(bundle: dict[str, Any]) -> None:
    evidence_by_id = {item["id"]: item for item in bundle["evidence"]}
    source_by_id = {item["id"]: item for item in bundle["sources"]}
    strength_rank = {
        "context_only": 0,
        "observed": 1,
        "corroborated": 2,
        "reproduced": 3,
    }
    for evidence in bundle["evidence"]:
        if evidence["kind"] == "run_observation" and strength_rank[evidence["strength"]] > 1:
            raise BundleError(
                "grounding_error",
                f"run observation cannot exceed observed strength: {evidence['id']}",
            )
        source_types = {
            source_by_id[source_ref]["type"]
            for source_ref in evidence["source_refs"]
            if source_ref in source_by_id
        }
        if evidence["strength"] == "reproduced":
            if (
                evidence["kind"] not in {"command_receipt", "test_result"}
                or "proof_receipt" not in source_types
                or not evidence["bindings"].get("command")
            ):
                raise BundleError(
                    "grounding_error",
                    f"reproduced evidence requires a proof receipt and command binding: {evidence['id']}",
                )

    for claim in bundle["claims"]:
        supporting = [evidence_by_id[reference] for reference in claim["evidence_refs"]]
        current_strong = [
            item
            for item in supporting
            if item["freshness"]["status"] == "current"
            and strength_rank[item["strength"]] >= strength_rank["corroborated"]
        ]
        current_reproduced = [
            item for item in current_strong if item["strength"] == "reproduced"
        ]
        if claim["status"] == "supported" and not current_strong:
            raise BundleError(
                "grounding_error",
                f"supported claim requires current corroborated or reproduced evidence: {claim['id']}",
            )
        if claim["basis"]["type"] == "reproduced" and not current_reproduced:
            raise BundleError(
                "grounding_error",
                f"reproduced claim basis requires current reproduced evidence: {claim['id']}",
            )


def _validate_budget_usage(bundle: dict[str, Any]) -> None:
    budgets = bundle["policy"]["budgets"]
    candidate_refs = {
        reference
        for entry in bundle["ledger"]
        for reference in entry["evidence_candidate_refs"]
    }
    tool_actions = {
        "read_file",
        "inspect_git",
        "inspect_proof",
        "check_freshness",
        "execute_authorized_command",
    }
    run_record_refs = {
        entry["input_ref"]
        for entry in bundle["ledger"]
        if entry["action"] == "read_run_record" and "input_ref" in entry
    }
    checks = (
        (len(candidate_refs), budgets["max_evidence_candidates"], "evidence candidates"),
        (len(bundle["evidence"]), budgets["max_verified_evidence"], "verified evidence"),
        (len(run_record_refs), budgets["max_run_records_read"], "run records"),
        (
            sum(entry["action"] in tool_actions for entry in bundle["ledger"]),
            budgets["max_tool_calls"],
            "tool calls",
        ),
    )
    for used, maximum, label in checks:
        if used > maximum:
            raise BundleError(
                "budget_error",
                f"Bundle {label} exceed policy budget ({used} > {maximum})",
            )


def _validate_references(bundle: dict[str, Any]) -> None:
    claims = {record["id"]: record for record in bundle["claims"]}
    evidence = {record["id"]: record for record in bundle["evidence"]}
    observations = {record["id"]: record for record in bundle["observations"]}
    sources = {record["id"]: record for record in bundle["sources"]}
    index = bundle["index"]
    _known(index["claim_refs"], claims, "index claim")
    _known(index["evidence_refs"], evidence, "index evidence")
    _known(index["observation_refs"], observations, "index observation")
    if set(index["claim_refs"]) != set(claims):
        raise BundleError("reference_error", "index must enumerate every Core claim")
    if set(index["evidence_refs"]) != set(evidence):
        raise BundleError("reference_error", "index must enumerate every Core evidence record")
    if set(index["observation_refs"]) != set(observations):
        raise BundleError("reference_error", "index must enumerate every Core observation")
    expected_order = [
        bundle["manifest"]["contents"]["claims"],
        bundle["manifest"]["contents"]["evidence"],
        bundle["manifest"]["contents"]["observations"],
    ]
    if index["reading_order"] != expected_order:
        raise BundleError("reference_error", "index reading_order must name the three Core files")
    if index["archive_available"] is not True:
        raise BundleError("reference_error", "v1 directory Bundles must declare the Archive")
    for claim in claims.values():
        _known(claim["evidence_refs"], evidence, f"claim {claim['id']} evidence")
        _known(claim["counter_evidence_refs"], evidence, f"claim {claim['id']} counter-evidence")
        _known(claim["observation_refs"], observations, f"claim {claim['id']} observation")
    for item in evidence.values():
        _known(item["source_refs"], sources, f"evidence {item['id']} source")
        _known(item["supports"], claims, f"evidence {item['id']} supported claim")
        _known(item["contradicts"], claims, f"evidence {item['id']} contradicted claim")
    for observation in observations.values():
        _known(observation["source_refs"], sources, f"observation {observation['id']} source")
    for diagnostic in bundle["diagnostics"]:
        _known(diagnostic["affected_observation_refs"], observations, f"diagnostic {diagnostic['code']} observation")
        _known(diagnostic["affected_evidence_refs"], evidence, f"diagnostic {diagnostic['code']} evidence")
    for conflict in bundle["conflicts"]:
        _known(conflict["evidence_refs"], evidence, f"conflict {conflict['id']} evidence")
    ledger_ids: set[str] = set()
    known_outputs = {**sources, **evidence, **observations}
    for entry in bundle["ledger"]:
        if entry["id"] in ledger_ids:
            raise BundleError("reference_error", f"duplicate ledger id: {entry['id']}")
        ledger_ids.add(entry["id"])
        _known(entry["observation_refs"], observations, f"ledger {entry['id']} observation")
        if "input_ref" in entry:
            _known([entry["input_ref"]], sources, f"ledger {entry['id']} input")
        if "output_ref" in entry:
            _known([entry["output_ref"]], known_outputs, f"ledger {entry['id']} output")


def _validate_counter_evidence(bundle: dict[str, Any]) -> None:
    claims = {record["id"]: record for record in bundle["claims"]}
    evidence = {record["id"]: record for record in bundle["evidence"]}
    for claim_id, claim in claims.items():
        declared_support = set(claim["evidence_refs"])
        declared_counter = set(claim["counter_evidence_refs"])
        actual_support = {item_id for item_id, item in evidence.items() if claim_id in item["supports"]}
        actual_counter = {item_id for item_id, item in evidence.items() if claim_id in item["contradicts"]}
        if declared_support != actual_support:
            raise BundleError(
                "reference_error",
                f"claim {claim_id} support references are not bidirectionally complete",
            )
        if declared_counter != actual_counter:
            raise BundleError(
                "counter_evidence_error",
                f"claim {claim_id} counter-evidence references are not bidirectionally complete",
            )
        if claim["status"] == "conflicted":
            if not declared_counter:
                raise BundleError(
                    "counter_evidence_error",
                    f"conflicted claim {claim_id} requires counter-evidence",
                )
            related = [
                conflict
                for conflict in bundle["conflicts"]
                if conflict["resolution_status"] == "unresolved"
                if (declared_support | declared_counter).issubset(conflict["evidence_refs"])
            ]
            if not related:
                raise BundleError(
                    "counter_evidence_error",
                    f"conflicted claim {claim_id} requires a Conflict record",
                )

    blob_bytes = sum(len(value) for value in bundle["blobs"].values())
    maximum = bundle["policy"]["budgets"]["max_blob_bytes_read"]
    if blob_bytes > maximum:
        raise BundleError(
            "budget_error",
            f"Bundle Blob bytes exceed policy budget ({blob_bytes} > {maximum})",
        )


def _unique_ids(value: Any, label: str) -> None:
    if not isinstance(value, list):
        raise BundleError("invalid_bundle", f"{label} must be an array")
    seen: set[str] = set()
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            raise BundleError("invalid_bundle", f"{label}[{index}] must be an object")
        identifier = record.get("id")
        _nonempty(identifier, f"{label}[{index}].id")
        if identifier in seen:
            raise BundleError("reference_error", f"duplicate {label} id: {identifier}")
        seen.add(identifier)


def _known(refs: Iterable[str], records: dict[str, Any], label: str) -> None:
    missing = sorted(set(refs) - set(records))
    if missing:
        raise BundleError("reference_error", f"{label} references are missing: {', '.join(missing)}")


def _enum(value: Any, allowed: set[str], label: str) -> None:
    if value not in allowed:
        raise BundleError("unsupported_semantics", f"{label} has unsupported value: {value!r}")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BundleError("invalid_bundle", f"{label} must be an object")
    return value


def _require_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(value))
    if missing:
        raise BundleError("invalid_bundle", f"{label} is missing: {', '.join(missing)}")


def _allowed_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    effective = allowed | ({"extensions"} if label in _EXTENSIBLE_OBJECTS else set())
    extra = sorted(set(value) - effective)
    if extra:
        raise BundleError("invalid_bundle", f"{label} has unsupported fields: {', '.join(extra)}")
    if "extensions" in value and not isinstance(value["extensions"], dict):
        raise BundleError("invalid_bundle", f"{label}.extensions must be an object")


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    _require_keys(value, expected, label)
    _allowed_keys(value, expected, label)


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise BundleError("invalid_bundle", f"{label} must be a non-empty string")
    return value


def _string_list(
    value: Any,
    label: str,
    *,
    unique: bool = False,
    nonempty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BundleError("invalid_bundle", f"{label} must be an array of strings")
    if nonempty and not value:
        raise BundleError("invalid_bundle", f"{label} must not be empty")
    if unique and len(set(value)) != len(value):
        raise BundleError("invalid_bundle", f"{label} must contain unique values")
    return value


def _optional_strings(value: dict[str, Any], fields: set[str], label: str) -> None:
    for field in fields:
        if field in value and not isinstance(value[field], str):
            raise BundleError("invalid_bundle", f"{label}.{field} must be a string")


def _boolean(value: Any, label: str) -> None:
    if not isinstance(value, bool):
        raise BundleError("invalid_bundle", f"{label} must be a boolean")


def _nonnegative_integer(value: Any, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BundleError("invalid_bundle", f"{label} must be a non-negative integer")


def _positive_integer(value: Any, label: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise BundleError("invalid_bundle", f"{label} must be a positive integer")


def _sha256(value: Any, label: str) -> None:
    if not (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    ):
        raise BundleError("invalid_bundle", f"{label} must be a lowercase SHA-256")


def _blob_ref(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.startswith("blobs/sha256-"):
        raise BundleError("invalid_bundle", f"{label} must be a content-addressed Blob path")
    _sha256(value.removeprefix("blobs/sha256-"), label)


def _utc_timestamp(value: Any, label: str) -> None:
    _nonempty(value, label)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise BundleError("invalid_bundle", f"{label} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise BundleError("invalid_bundle", f"{label} must use UTC")


def _portable_relative_path(value: Any, label: str) -> str:
    _nonempty(value, label)
    if "\\" in value:
        raise BundleError("invalid_bundle", f"{label} must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise BundleError("invalid_bundle", f"{label} must be a normalized relative path")
    return path.as_posix()


def _path_is_within(path: str, declared_root: str) -> bool:
    root = _portable_relative_path(declared_root.rstrip("/"), "workspace policy path")
    return path == root or path.startswith(root + "/")
