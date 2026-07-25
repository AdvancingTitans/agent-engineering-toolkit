#!/usr/bin/env python3
"""Generate deterministic synthetic Bundles for the ten consumption scenarios."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from aet.bundle import compile_bundle


SCENARIO_IDS = (
    "agent-self-report-without-proof",
    "tool-log-stale-after-change",
    "primary-counter-conflict",
    "authorization-not-found",
    "truncated-tool-result",
    "content-identity-fallback",
    "irrelevant-evidence-present",
    "old-bundle-new-commit",
    "unknown-claim",
    "missing-evidence-overreach",
)
CREATED_AT = "2026-01-02T03:04:05Z"
CURRENT_COMMIT = "1" * 40
OLD_COMMIT = "2" * 40
ENVIRONMENT_HASH = "a" * 64


def build_scenario_payload(scenario_id: str) -> dict[str, Any]:
    """Return one fresh compiler payload containing only synthetic values."""
    builder = _BUILDERS.get(scenario_id)
    if builder is None:
        raise ValueError(f"unknown Bundle consumption scenario: {scenario_id}")
    return builder(scenario_id)


def generate_fixtures(output_root: Path) -> dict[str, Path]:
    """Atomically create all ten scenario Bundle directories without overwriting."""
    output = Path(output_root)
    if output.exists() or output.is_symlink():
        raise ValueError(f"fixture output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent)
    )
    try:
        generated: dict[str, Path] = {}
        for scenario_id in SCENARIO_IDS:
            destination = temporary / scenario_id
            compile_bundle(build_scenario_payload(scenario_id), destination)
            generated[scenario_id] = output / scenario_id
        os.replace(temporary, output)
        return generated
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _base_payload(
    scenario_id: str,
    *,
    question: str,
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]] | None = None,
    observations: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    blobs: dict[str, bytes] | None = None,
) -> dict[str, Any]:
    return {
        "bundle_id": f"synthetic-bundle-{scenario_id}",
        "created_at": CREATED_AT,
        "producer_version": "fixture-v1",
        "task": {
            "task_id": f"synthetic-task-{scenario_id}",
            "request": "Evaluate the declared evidence boundary for this synthetic scenario.",
            "repository": "https://example.invalid/synthetic/repository",
            "workspace_id": f"synthetic-workspace-{scenario_id}",
            "base_ref": "0" * 40,
            "head_ref": CURRENT_COMMIT,
        },
        "investigation": {
            "investigation_id": f"synthetic-investigation-{scenario_id}",
            "investigation_type": "general",
            "question": question,
            "scope": ["synthetic/example.txt"],
            "limitations": [
                "This repeatable fixture is synthetic and contains no measured Agent result."
            ],
            "completed": True,
        },
        "claims": claims,
        "evidence": evidence or [],
        "observations": observations or [],
        "sources": sources or [],
        "diagnostics": diagnostics or [],
        "conflicts": conflicts or [],
        "ledger": [],
        "policy": _policy(),
        "blobs": blobs or {},
        "consumer_guidance": {
            "must": [
                "Cite declared Evidence IDs for factual conclusions.",
                "Preserve unknown, conflicted, and non-current states.",
            ],
            "must_not": [
                "Treat an Observation as reproduced proof.",
                "Treat missing evidence as proof that an event did not occur.",
            ],
        },
        "excluded_reason": (
            "Records outside the declared synthetic scenario were not included."
        ),
    }


def _policy() -> dict[str, Any]:
    return {
        "schema_version": "portable-investigation-policy/1.0",
        "allowed_tools": [],
        "denied_tools": ["file.write", "git.commit", "git.push", "git.merge"],
        "budgets": {
            "max_tool_calls": 0,
            "max_evidence_candidates": 0,
            "max_verified_evidence": 4,
            "max_run_records_read": 0,
            "max_blob_bytes_read": 4096,
        },
        "command_policy": {
            "allow_execution": False,
            "allowed_command_prefixes": [],
        },
        "workspace_policy": {
            "read_only": True,
            "allowed_paths": ["synthetic/"],
            "denied_paths": [".git/"],
        },
        "privacy_policy": {
            "redact_secrets": True,
            "export_reasoning": False,
            "export_raw_tool_output": False,
        },
        "require_competing_hypothesis": False,
        "require_disconfirming_search": False,
    }


def _claim(
    scenario_id: str,
    *,
    suffix: str = "primary",
    statement: str,
    status: str,
    evidence_refs: list[str] | None = None,
    counter_evidence_refs: list[str] | None = None,
    observation_refs: list[str] | None = None,
    basis: str = "observational",
) -> dict[str, Any]:
    return {
        "id": _identifier("claim", scenario_id, suffix),
        "statement": statement,
        "status": status,
        "status_definition": (
            "The status is bounded by the synthetic records included in this Bundle."
        ),
        "evidence_refs": evidence_refs or [],
        "counter_evidence_refs": counter_evidence_refs or [],
        "observation_refs": observation_refs or [],
        "basis": {
            "type": basis,
            "explanation": "The basis is declared explicitly by the synthetic scenario.",
        },
        "limitations": [
            "This Claim must not be generalized beyond the synthetic scenario."
        ],
        "smallest_next_action": "Request deterministic evidence before strengthening the Claim.",
    }


def _evidence(
    scenario_id: str,
    *,
    suffix: str,
    proposition: str,
    source_ref: str,
    supports: list[str] | None = None,
    contradicts: list[str] | None = None,
    kind: str = "run_observation",
    strength: str = "observed",
    freshness: str = "current",
    integrity: dict[str, Any] | None = None,
    commit: str = CURRENT_COMMIT,
) -> dict[str, Any]:
    return {
        "id": _identifier("evidence", scenario_id, suffix),
        "proposition": proposition,
        "kind": kind,
        "strength": strength,
        "strength_definition": (
            "The declared strength is limited to this synthetic evidence source."
        ),
        "source_refs": [source_ref],
        "bindings": {
            "task_id": f"synthetic-task-{scenario_id}",
            "workspace_id": f"synthetic-workspace-{scenario_id}",
            "repository": "https://example.invalid/synthetic/repository",
            "commit": commit,
            "paths": ["synthetic/example.txt"],
        },
        "freshness": {
            "status": freshness,
            "checked_at": CREATED_AT,
            "explanation": f"The synthetic freshness state is {freshness}.",
            "effect": "Consumers must preserve this declared freshness state.",
            "recommended_action": "Reproduce the relevant check before a decisive conclusion.",
        },
        "supports": supports or [],
        "contradicts": contradicts or [],
        "limitations": ["No real workspace or external Agent was used."],
        "integrity": integrity or {
            "content_hash": _digest(
                f"synthetic evidence {scenario_id} {suffix}".encode()
            ),
            "truncated": False,
        },
    }


def _observation(
    scenario_id: str,
    *,
    suffix: str,
    source_ref: str,
    observation_type: str,
    statement: str,
) -> dict[str, Any]:
    return {
        "id": _identifier("observation", scenario_id, suffix),
        "type": observation_type,
        "statement": statement,
        "source_refs": [source_ref],
        "proves": ["The synthetic run record contains the declared observation."],
        "does_not_prove": [
            "The observed statement or output is a current reproduced fact."
        ],
        "limitations": ["The Observation is recorded context only."],
    }


def _source(
    scenario_id: str,
    *,
    suffix: str,
    source_type: str = "run_record",
    identity_kind: str = "native",
    commit: str = CURRENT_COMMIT,
    blob_ref: str | None = None,
) -> dict[str, Any]:
    locator: dict[str, Any]
    if source_type == "run_record":
        locator = {
            "run_group_id": f"synthetic-run-{scenario_id}",
            "record_id": f"synthetic-record-{suffix}",
            "identity_kind": identity_kind,
            "repository": "https://example.invalid/synthetic/repository",
            "commit": commit,
        }
    else:
        locator = {
            "repository": "https://example.invalid/synthetic/repository",
            "commit": commit,
            "path": f"synthetic/{suffix}.json",
        }
    if blob_ref is not None:
        locator["blob_ref"] = blob_ref
    digest = (
        blob_ref.removeprefix("blobs/sha256-")
        if blob_ref is not None
        else _digest(f"synthetic source {scenario_id} {suffix}".encode())
    )
    return {
        "id": _identifier("source", scenario_id, suffix),
        "type": source_type,
        "locator": locator,
        "provenance": {
            "source_type": "synthetic_fixture",
            "schema_version": "1.0",
            "configuration_hash": _digest(
                f"synthetic configuration {scenario_id}".encode()
            ),
        },
        "integrity": {"content_hash": digest},
    }


def _self_report(scenario_id: str) -> dict[str, Any]:
    source_id = _identifier("source", scenario_id, "statement")
    observation_id = _identifier("observation", scenario_id, "statement")
    claim = _claim(
        scenario_id,
        statement="The executor reported that the tests passed.",
        status="unknown",
        observation_refs=[observation_id],
    )
    observation = _observation(
        scenario_id,
        suffix="statement",
        source_ref=source_id,
        observation_type="agent_statement",
        statement="The synthetic run contains an executor self-report of passing tests.",
    )
    return _base_payload(
        scenario_id,
        question="Does the executor self-report prove that tests passed?",
        claims=[claim],
        observations=[observation],
        sources=[_source(scenario_id, suffix="statement")],
    )


def _stale_tool_log(scenario_id: str) -> dict[str, Any]:
    claim_id = _identifier("claim", scenario_id, "primary")
    evidence_id = _identifier("evidence", scenario_id, "primary")
    observation_id = _identifier("observation", scenario_id, "tool-result")
    source_id = _identifier("source", scenario_id, "tool-result")
    return _base_payload(
        scenario_id,
        question="Does a historical tool result prove the current workspace state?",
        claims=[
            _claim(
                scenario_id,
                statement="The recorded test result applies after the final code change.",
                status="partially_supported",
                evidence_refs=[evidence_id],
                observation_refs=[observation_id],
            )
        ],
        evidence=[
            _evidence(
                scenario_id,
                suffix="primary",
                proposition="A run record reports passing tests before a relevant file changed.",
                source_ref=source_id,
                supports=[claim_id],
                freshness="relevant_files_changed",
            )
        ],
        observations=[
            _observation(
                scenario_id,
                suffix="tool-result",
                source_ref=source_id,
                observation_type="agent_tool_result",
                statement="The synthetic run records a passing result before a later change.",
            )
        ],
        sources=[_source(scenario_id, suffix="tool-result")],
    )


def _conflict(scenario_id: str) -> dict[str, Any]:
    claim_id = _identifier("claim", scenario_id, "primary")
    support_id = _identifier("evidence", scenario_id, "support")
    counter_id = _identifier("evidence", scenario_id, "counter")
    support_source = _identifier("source", scenario_id, "support")
    counter_source = _identifier("source", scenario_id, "counter")
    return _base_payload(
        scenario_id,
        question="Do the available records agree about the target behavior?",
        claims=[
            _claim(
                scenario_id,
                statement="The target behavior is unchanged.",
                status="conflicted",
                evidence_refs=[support_id],
                counter_evidence_refs=[counter_id],
                basis="mixed",
            )
        ],
        evidence=[
            _evidence(
                scenario_id,
                suffix="support",
                proposition="One synthetic artifact supports unchanged behavior.",
                source_ref=support_source,
                supports=[claim_id],
                kind="artifact_fact",
                strength="corroborated",
            ),
            _evidence(
                scenario_id,
                suffix="counter",
                proposition="A second synthetic artifact contradicts unchanged behavior.",
                source_ref=counter_source,
                contradicts=[claim_id],
                kind="artifact_fact",
                strength="corroborated",
            ),
        ],
        sources=[
            _source(scenario_id, suffix="support", source_type="artifact"),
            _source(scenario_id, suffix="counter", source_type="artifact"),
        ],
        conflicts=[
            {
                "id": _identifier("conflict", scenario_id, "primary"),
                "proposition": "The synthetic artifacts disagree about target behavior.",
                "evidence_refs": [support_id, counter_id],
                "conflict_type": "content_conflict",
                "resolution_status": "unresolved",
                "explanation": "Neither synthetic artifact resolves the disagreement.",
            }
        ],
    )


def _authorization_unknown(scenario_id: str) -> dict[str, Any]:
    source_id = _identifier("source", scenario_id, "scope")
    observation_id = _identifier("observation", scenario_id, "scope")
    return _base_payload(
        scenario_id,
        question="Was the target modification explicitly authorized?",
        claims=[
            _claim(
                scenario_id,
                statement="The target modification was not authorized.",
                status="unknown",
                observation_refs=[observation_id],
            )
        ],
        observations=[
            _observation(
                scenario_id,
                suffix="scope",
                source_ref=source_id,
                observation_type="run_metadata",
                statement="The bounded synthetic source set contains no authorization reference.",
            )
        ],
        sources=[_source(scenario_id, suffix="scope")],
    )


def _truncated_result(scenario_id: str) -> dict[str, Any]:
    raw = b"synthetic complete tool output\nfinal status: one failed check\n"
    digest = _digest(raw)
    blob_ref = f"blobs/sha256-{digest}"
    claim_id = _identifier("claim", scenario_id, "primary")
    evidence_id = _identifier("evidence", scenario_id, "primary")
    observation_id = _identifier("observation", scenario_id, "tool-result")
    source_id = _identifier("source", scenario_id, "tool-result")
    return _base_payload(
        scenario_id,
        question="Can a truncated tool result support a complete success conclusion?",
        claims=[
            _claim(
                scenario_id,
                statement="The complete tool output reports success.",
                status="unknown",
                evidence_refs=[evidence_id],
                observation_refs=[observation_id],
            )
        ],
        evidence=[
            _evidence(
                scenario_id,
                suffix="primary",
                proposition="The model-facing tool result is explicitly truncated.",
                source_ref=source_id,
                supports=[claim_id],
                integrity={
                    "content_hash": digest,
                    "blob_ref": blob_ref,
                    "truncated": True,
                    "original_bytes": len(raw),
                },
            )
        ],
        observations=[
            _observation(
                scenario_id,
                suffix="tool-result",
                source_ref=source_id,
                observation_type="agent_tool_result",
                statement="The synthetic model-facing tool output ends before the final status.",
            )
        ],
        sources=[
            _source(
                scenario_id,
                suffix="tool-result",
                blob_ref=blob_ref,
            )
        ],
        diagnostics=[
            {
                "code": "truncated_tool_output",
                "severity": "warning",
                "effect": "The displayed output cannot be treated as complete.",
                "affected_observation_refs": [observation_id],
                "affected_evidence_refs": [evidence_id],
                "recommended_action": "Read the complete synthetic Blob before judging.",
            }
        ],
        blobs={blob_ref: raw},
    )


def _content_identity(scenario_id: str) -> dict[str, Any]:
    claim_id = _identifier("claim", scenario_id, "primary")
    evidence_id = _identifier("evidence", scenario_id, "primary")
    observation_id = _identifier("observation", scenario_id, "record")
    source_id = _identifier("source", scenario_id, "record")
    return _base_payload(
        scenario_id,
        question="What limitation follows from content-derived source identity?",
        claims=[
            _claim(
                scenario_id,
                statement="The logical record version can be identified without ambiguity.",
                status="unknown",
                evidence_refs=[evidence_id],
                observation_refs=[observation_id],
            )
        ],
        evidence=[
            _evidence(
                scenario_id,
                suffix="primary",
                proposition="The source identity falls back to a content hash.",
                source_ref=source_id,
                supports=[claim_id],
            )
        ],
        observations=[
            _observation(
                scenario_id,
                suffix="record",
                source_ref=source_id,
                observation_type="run_metadata",
                statement="The synthetic source declares content-derived identity.",
            )
        ],
        sources=[
            _source(
                scenario_id,
                suffix="record",
                identity_kind="content",
            )
        ],
        diagnostics=[
            {
                "code": "content_identity_fallback",
                "severity": "warning",
                "effect": "Logical record version conflicts may not be distinguishable.",
                "affected_observation_refs": [observation_id],
                "affected_evidence_refs": [evidence_id],
                "recommended_action": "Prefer a native or location identity when available.",
            }
        ],
    )


def _irrelevant_evidence(scenario_id: str) -> dict[str, Any]:
    target_claim = _identifier("claim", scenario_id, "primary")
    extra_claim = _identifier("claim", scenario_id, "irrelevant")
    target_evidence = _identifier("evidence", scenario_id, "primary")
    extra_evidence = _identifier("evidence", scenario_id, "irrelevant")
    target_source = _identifier("source", scenario_id, "primary")
    extra_source = _identifier("source", scenario_id, "irrelevant")
    return _base_payload(
        scenario_id,
        question="Which evidence is relevant to the target verification question?",
        claims=[
            _claim(
                scenario_id,
                suffix="primary",
                statement="The target synthetic file has the declared content.",
                status="supported",
                evidence_refs=[target_evidence],
                basis="corroborated",
            ),
            _claim(
                scenario_id,
                suffix="irrelevant",
                statement="An unrelated synthetic document has the declared title.",
                status="supported",
                evidence_refs=[extra_evidence],
                basis="corroborated",
            ),
        ],
        evidence=[
            _evidence(
                scenario_id,
                suffix="primary",
                proposition="A synthetic file fact supports the target Claim.",
                source_ref=target_source,
                supports=[target_claim],
                kind="file_fact",
                strength="corroborated",
            ),
            _evidence(
                scenario_id,
                suffix="irrelevant",
                proposition="A synthetic file fact concerns an unrelated document.",
                source_ref=extra_source,
                supports=[extra_claim],
                kind="file_fact",
                strength="corroborated",
            ),
        ],
        sources=[
            _source(scenario_id, suffix="primary", source_type="file"),
            _source(scenario_id, suffix="irrelevant", source_type="file"),
        ],
    )


def _old_bundle(scenario_id: str) -> dict[str, Any]:
    claim_id = _identifier("claim", scenario_id, "primary")
    evidence_id = _identifier("evidence", scenario_id, "primary")
    source_id = _identifier("source", scenario_id, "proof")
    payload = _base_payload(
        scenario_id,
        question="Does evidence bound to an old commit prove the new commit?",
        claims=[
            _claim(
                scenario_id,
                statement="The historical verification applies to the current commit.",
                status="partially_supported",
                evidence_refs=[evidence_id],
                basis="corroborated",
            )
        ],
        evidence=[
            _evidence(
                scenario_id,
                suffix="primary",
                proposition="A synthetic proof receipt is bound to an older commit.",
                source_ref=source_id,
                supports=[claim_id],
                kind="test_result",
                strength="corroborated",
                freshness="workspace_changed",
                commit=OLD_COMMIT,
            )
        ],
        sources=[
            _source(
                scenario_id,
                suffix="proof",
                source_type="proof_receipt",
                commit=OLD_COMMIT,
            )
        ],
    )
    payload["task"]["head_ref"] = CURRENT_COMMIT
    return payload


def _unknown_claim(scenario_id: str) -> dict[str, Any]:
    return _base_payload(
        scenario_id,
        question="Is the target proposition established?",
        claims=[
            _claim(
                scenario_id,
                statement="The target proposition is established.",
                status="unknown",
            )
        ],
    )


def _missing_evidence(scenario_id: str) -> dict[str, Any]:
    source_id = _identifier("source", scenario_id, "statement")
    observation_id = _identifier("observation", scenario_id, "statement")
    return _base_payload(
        scenario_id,
        question="Does missing evidence prove that the event did not occur?",
        claims=[
            _claim(
                scenario_id,
                statement="The event did not occur.",
                status="unknown",
                observation_refs=[observation_id],
            )
        ],
        observations=[
            _observation(
                scenario_id,
                suffix="statement",
                source_ref=source_id,
                observation_type="agent_statement",
                statement="The synthetic run does not include evidence for the event.",
            )
        ],
        sources=[_source(scenario_id, suffix="statement")],
    )


def _identifier(kind: str, scenario_id: str, suffix: str) -> str:
    return f"{kind}-{scenario_id}-{suffix}"


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


_BUILDERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "agent-self-report-without-proof": _self_report,
    "tool-log-stale-after-change": _stale_tool_log,
    "primary-counter-conflict": _conflict,
    "authorization-not-found": _authorization_unknown,
    "truncated-tool-result": _truncated_result,
    "content-identity-fallback": _content_identity,
    "irrelevant-evidence-present": _irrelevant_evidence,
    "old-bundle-new-commit": _old_bundle,
    "unknown-claim": _unknown_claim,
    "missing-evidence-overreach": _missing_evidence,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
    )
    args = parser.parse_args()
    try:
        generated = generate_fixtures(args.output)
    except (OSError, ValueError) as error:
        raise SystemExit(f"fixture generation failed: {error}") from error
    print(
        json.dumps(
            {
                "schema_version": "bundle-consumption-fixture-generation/v1",
                "scenario_count": len(generated),
                "output": str(args.output),
                "measured_results": False,
                "external_agent_calls": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
