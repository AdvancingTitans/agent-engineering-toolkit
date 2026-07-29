"""Build the README's reproducible evidence-grounded improvement Bundle."""

from __future__ import annotations

import argparse
import hashlib
import tempfile
from pathlib import Path
from typing import Any

from aet.bundle import compile_bundle
from aet.quick.proof import quick_proof


ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION = "examples/evidence-grounded-improvement/sample_project/tool_result.py"
REGRESSION = (
    "examples/evidence-grounded-improvement/sample_project/test_tool_result.py"
)
COMMAND = ["python", REGRESSION]
CREATED_AT = "2026-07-29T12:00:00Z"
CONFIGURATION_HASH = hashlib.sha256(
    b"aet-evidence-grounded-improvement-readme/v1"
).hexdigest()


def _sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _run_regression() -> tuple[dict[str, Any], int, bytes]:
    with tempfile.TemporaryDirectory(prefix="aet-readme-improvement-") as raw:
        receipt_path = Path(raw) / "proof.json"
        receipt, exit_code = quick_proof(
            COMMAND,
            receipt_path,
            relevant_paths=[IMPLEMENTATION, REGRESSION],
        )
        receipt_raw = receipt_path.read_bytes()
    if exit_code == 0:
        raise RuntimeError(
            "README fixture drifted: the expected empty-result regression no longer fails"
        )
    return receipt, exit_code, receipt_raw


def payload() -> dict[str, Any]:
    receipt, exit_code, receipt_raw = _run_regression()
    command_fact = (
        f"exit_code={exit_code}; "
        "empty result was rendered as a factual success instead of no_evidence"
    )
    command_hash = hashlib.sha256(command_fact.encode("utf-8")).hexdigest()
    receipt_hash = hashlib.sha256(receipt_raw).hexdigest()
    receipt_blob = f"blobs/sha256-{receipt_hash}"
    repository = (
        "https://github.com/AdvancingTitans/agent-engineering-toolkit"
    )
    task_id = "task-review-empty-tool-result"
    workspace_id = "aet-readme-improvement-fixture"
    claim_id = "claim-empty-result-is-grounded"
    evidence_id = "ev-empty-result-regression"
    source_impl = "src-empty-result-adapter"
    source_test = "src-empty-result-regression"
    source_command = "src-empty-result-command"
    source_proof = "src-empty-result-proof"
    return {
        "bundle_id": "bundle-empty-tool-result-review-v1",
        "created_at": CREATED_AT,
        "producer_version": "1.16.0",
        "task": {
            "task_id": task_id,
            "request": (
                "Review the project and tell me whether empty tool results can "
                "be emitted as reliable facts."
            ),
            "repository": repository,
            "workspace_id": workspace_id,
            "base_ref": "v1.15.0",
            "head_ref": "working-tree",
        },
        "investigation": {
            "investigation_id": "investigation-empty-tool-result",
            "investigation_type": "general",
            "question": (
                "Does the adapter preserve an empty tool result as a "
                "non-evidence state?"
            ),
            "scope": [IMPLEMENTATION, REGRESSION],
            "limitations": [
                "This fixture demonstrates one bounded failure mode.",
                "The failing check does not prove the rest of the project is unsafe.",
            ],
            "completed": True,
        },
        "claims": [
            {
                "id": claim_id,
                "statement": (
                    "An empty tool result is evidence-grounded and may be "
                    "reported as “No security issues were found.”"
                ),
                "status": "unsupported",
                "status_definition": (
                    "The implementation manufactures a factual success from "
                    "the absence of tool evidence, and the regression check fails."
                ),
                "evidence_refs": [],
                "counter_evidence_refs": [evidence_id],
                "observation_refs": ["obs-empty-result"],
                "basis": {
                    "type": "observational",
                    "explanation": (
                        "A deterministic local regression check reproduced "
                        "the unsupported conversion."
                    ),
                },
                "limitations": [
                    "The root cause is bounded to the sample adapter.",
                    "No production repository behavior is inferred from this fixture.",
                ],
                "smallest_next_action": (
                    "Change only the adapter and make the recorded regression "
                    "command pass without weakening the test."
                ),
            }
        ],
        "evidence": [
            {
                "id": evidence_id,
                "proposition": command_fact,
                "kind": "test_result",
                "strength": "reproduced",
                "strength_definition": (
                    "AET executed the checked-in regression command and bound "
                    "the non-zero result to a Quick Proof Receipt."
                ),
                "source_refs": [
                    source_impl,
                    source_test,
                    source_command,
                    source_proof,
                ],
                "bindings": {
                    "task_id": task_id,
                    "workspace_id": workspace_id,
                    "repository": repository,
                    "paths": [IMPLEMENTATION],
                    "command": COMMAND,
                },
                "freshness": {
                    "status": "current",
                    "checked_at": CREATED_AT,
                    "explanation": (
                        "The source hashes and command result were captured "
                        "while building this Bundle."
                    ),
                    "effect": (
                        "The reproduced failure applies only while the bound "
                        "sample files retain these hashes."
                    ),
                    "recommended_action": (
                        "Rebuild the example after changing either sample file."
                    ),
                },
                "supports": [],
                "contradicts": [claim_id],
                "limitations": [
                    "A failing regression identifies the behavior, not a holistic trust score."
                ],
                "integrity": {
                    "content_hash": command_hash,
                    "truncated": False,
                },
            }
        ],
        "observations": [
            {
                "id": "obs-empty-result",
                "type": "agent_tool_result",
                "statement": (
                    "The tool returned no rows, while normalize_findings([]) "
                    "returned a factual success sentence."
                ),
                "source_refs": [
                    source_impl,
                    source_test,
                    source_command,
                    source_proof,
                ],
                "proves": [
                    "The bounded sample adapter converts an empty list into a factual success."
                ],
                "does_not_prove": [
                    "No security issues exist.",
                    "The whole repository was reviewed.",
                    "A code change is authorized.",
                ],
                "limitations": [
                    "Only the checked-in sample adapter and regression command were observed."
                ],
            }
        ],
        "sources": [
            {
                "id": source_impl,
                "type": "file",
                "locator": {
                    "repository": repository,
                    "path": IMPLEMENTATION,
                },
                "provenance": {
                    "source_type": "deterministic_file_read",
                    "schema_version": "1.16.0",
                    "configuration_hash": CONFIGURATION_HASH,
                },
                "integrity": {"content_hash": _sha256(IMPLEMENTATION)},
            },
            {
                "id": source_test,
                "type": "file",
                "locator": {
                    "repository": repository,
                    "path": REGRESSION,
                },
                "provenance": {
                    "source_type": "deterministic_file_read",
                    "schema_version": "1.16.0",
                    "configuration_hash": CONFIGURATION_HASH,
                },
                "integrity": {"content_hash": _sha256(REGRESSION)},
            },
            {
                "id": source_command,
                "type": "command",
                "locator": {
                    "repository": repository,
                    "path": REGRESSION,
                },
                "provenance": {
                    "source_type": "deterministic_command",
                    "schema_version": "1.16.0",
                    "configuration_hash": CONFIGURATION_HASH,
                },
                "integrity": {"content_hash": command_hash},
            },
            {
                "id": source_proof,
                "type": "proof_receipt",
                "locator": {
                    "repository": repository,
                    "record_id": receipt["proof_id"],
                    "blob_ref": receipt_blob,
                },
                "provenance": {
                    "source_type": "aet_quick_proof",
                    "schema_version": receipt["schema_version"],
                    "configuration_hash": CONFIGURATION_HASH,
                },
                "integrity": {"content_hash": receipt_hash},
            },
        ],
        "diagnostics": [],
        "conflicts": [],
        "ledger": [
            {
                "id": "ledger-run-empty-result-regression",
                "timestamp": CREATED_AT,
                "question": (
                    "Does an empty tool result remain a structured non-evidence state?"
                ),
                "hypothesis_ref": "primary",
                "action": "execute_authorized_command",
                "tool_name": "python",
                "input_ref": source_test,
                "output_ref": evidence_id,
                "observation_refs": ["obs-empty-result"],
                "evidence_candidate_refs": [],
                "effect": "weakens_primary",
                "explanation": (
                    "The regression failed because the adapter emitted a "
                    "factual success from an empty result."
                ),
            }
        ],
        "policy": {
            "schema_version": "portable-investigation-policy/1.0",
            "allowed_tools": ["file.read", "python"],
            "denied_tools": ["file.write", "git.push"],
            "budgets": {
                "max_tool_calls": 4,
                "max_evidence_candidates": 4,
                "max_verified_evidence": 2,
                "max_run_records_read": 4,
                "max_blob_bytes_read": 8192,
            },
            "command_policy": {
                "allow_execution": True,
                "allowed_command_prefixes": [["python", REGRESSION]],
            },
            "workspace_policy": {
                "read_only": True,
                "allowed_paths": [IMPLEMENTATION, REGRESSION],
                "denied_paths": [".git/", ".aet/"],
            },
            "privacy_policy": {
                "redact_secrets": True,
                "export_reasoning": False,
                "export_raw_tool_output": False,
            },
            "require_competing_hypothesis": False,
            "require_disconfirming_search": False,
        },
        "blobs": {receipt_blob: receipt_raw},
        "consumer_guidance": {
            "must": [
                f"Cite {evidence_id} for the reproduced failure.",
                "Keep the proposed change inside the evidence-bound adapter path.",
            ],
            "must_not": [
                "Treat an empty result as proof that no issue exists.",
                "Treat the generated prompt as Evidence or merge authority.",
            ],
        },
        "excluded_reason": (
            "Only the sample adapter and its regression check are required for "
            "this bounded README case."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    compile_bundle(payload(), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
