"""Build the README's real-project Evidence Atlas example from AET source."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

from aet.bundle import compile_bundle


ROOT = Path(__file__).resolve().parents[2]
CREATED_AT = "2026-07-26T12:00:00Z"
CONFIGURATION_HASH = hashlib.sha256(b"aet-atlas-self-review/v1.19").hexdigest()

SOURCE_PATHS = {
    "src-graph": "src/aet/atlas/builder.py",
    "src-perspectives": "src/aet/atlas/perspectives.py",
    "src-viewer": "src/aet/atlas/viewer.py",
    "src-bundle-schema": "schemas/evidence-bundle/v1/evidence.schema.json",
}


def _sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def _source(identifier: str, relative: str) -> dict[str, Any]:
    digest = _sha256(relative)
    return {
        "id": identifier,
        "type": "file",
        "locator": {
            "repository": (
                "https://github.com/AdvancingTitans/"
                "agent-engineering-toolkit"
            ),
            "path": relative,
        },
        "provenance": {
            "source_type": "deterministic_file_read",
            "schema_version": "1.19.0",
            "configuration_hash": CONFIGURATION_HASH,
        },
        "integrity": {"content_hash": digest},
    }


def _evidence(
    identifier: str,
    proposition: str,
    source_id: str,
    path: str,
    *,
    supports: list[str],
    contradicts: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "proposition": proposition,
        "kind": "file_fact",
        "strength": "corroborated",
        "strength_definition": (
            "The proposition is bound to a content-addressed AET source file."
        ),
        "source_refs": [source_id],
        "bindings": {
            "task_id": "task-aet-atlas-self-review",
            "workspace_id": "aet-v1.16.0-source-tree",
            "repository": (
                "https://github.com/AdvancingTitans/"
                "agent-engineering-toolkit"
            ),
            "paths": [path],
        },
        "freshness": {
            "status": "current",
            "checked_at": CREATED_AT,
            "explanation": "The source hash was computed while building this Bundle.",
            "effect": "The file fact applies only while the bound source hash matches.",
            "recommended_action": "Rebuild the example after changing the bound source.",
        },
        "supports": supports,
        "contradicts": contradicts or [],
        "limitations": limitations or [],
        "integrity": {
            "content_hash": _sha256(path),
            "truncated": False,
        },
    }


def payload() -> dict[str, Any]:
    claims = [
        {
            "id": "claim-source-backed-graph",
            "statement": (
                "AET builds a canonical Evidence Graph from source-backed "
                "Bundle records without letting Mermaid create evidence."
            ),
            "status": "supported",
            "status_definition": "A content-addressed Graph Builder source supports the claim.",
            "evidence_refs": ["ev-graph-builder"],
            "counter_evidence_refs": [],
            "observation_refs": ["obs-source-review"],
            "basis": {
                "type": "corroborated",
                "explanation": "The claim cites the current Graph Builder source.",
            },
            "limitations": [
                "This source review does not prove behavior outside the bound files."
            ],
            "smallest_next_action": "Run the Atlas protocol tests for behavioral proof.",
        },
        {
            "id": "claim-recursive-perspectives",
            "statement": (
                "AET projects eleven fixed evidence perspectives and exposes "
                "complex nodes as recursive Viewer subgraphs."
            ),
            "status": "supported",
            "status_definition": "Perspective and Viewer sources jointly support the claim.",
            "evidence_refs": ["ev-perspectives", "ev-viewer"],
            "counter_evidence_refs": [],
            "observation_refs": ["obs-source-review"],
            "basis": {
                "type": "corroborated",
                "explanation": "Two independently hashed source files establish the structure.",
            },
            "limitations": [
                "Rendering success still requires the packaged Mermaid runtime."
            ],
            "smallest_next_action": "Open the offline Viewer and enter a complex node.",
        },
        {
            "id": "claim-change-scope-complete",
            "statement": (
                "The Bundle v1 change-scope view alone proves complete real diff grouping."
            ),
            "status": "conflicted",
            "status_definition": (
                "Path bindings exist, but the Portable Evidence v1 Evidence "
                "record schema has no explicit Change Group field."
            ),
            "evidence_refs": ["ev-path-bindings"],
            "counter_evidence_refs": ["ev-no-change-groups"],
            "observation_refs": ["obs-source-review"],
            "basis": {
                "type": "mixed",
                "explanation": "Supporting path fields and a structural limitation conflict.",
            },
            "limitations": [
                "The view must display UNKNOWN rather than infer real diff groups."
            ],
            "smallest_next_action": (
                "Add an explicit Change Group field or collection in a future "
                "Bundle protocol revision."
            ),
        },
    ]
    evidence = [
        _evidence(
            "ev-graph-builder",
            "The Graph Builder creates canonical nodes and source-backed edges.",
            "src-graph",
            SOURCE_PATHS["src-graph"],
            supports=["claim-source-backed-graph"],
        ),
        _evidence(
            "ev-perspectives",
            "The Perspective module defines eleven fixed deterministic projections.",
            "src-perspectives",
            SOURCE_PATHS["src-perspectives"],
            supports=["claim-recursive-perspectives"],
        ),
        _evidence(
            "ev-viewer",
            "The offline Viewer contains recursive subgraph navigation.",
            "src-viewer",
            SOURCE_PATHS["src-viewer"],
            supports=["claim-recursive-perspectives"],
        ),
        _evidence(
            "ev-path-bindings",
            "Bundle Evidence records can bind facts to repository paths.",
            "src-bundle-schema",
            SOURCE_PATHS["src-bundle-schema"],
            supports=["claim-change-scope-complete"],
            limitations=["A path binding is not a real diff group."],
        ),
        _evidence(
            "ev-no-change-groups",
            "The Portable Evidence v1 Evidence record schema does not define "
            "an explicit Change Group field.",
            "src-bundle-schema",
            SOURCE_PATHS["src-bundle-schema"],
            supports=[],
            contradicts=["claim-change-scope-complete"],
        ),
    ]
    source_refs = list(SOURCE_PATHS)
    return {
        "bundle_id": "bundle-aet-atlas-self-review-v1",
        "created_at": CREATED_AT,
        "producer_version": "1.19.0",
        "task": {
            "task_id": "task-aet-atlas-self-review",
            "request": (
                "Review AET's own Evidence Atlas implementation and retain "
                "support, counter-evidence, limitations, and UNKNOWN."
            ),
            "repository": (
                "https://github.com/AdvancingTitans/"
                "agent-engineering-toolkit"
            ),
            "workspace_id": "aet-v1.19.0-source-tree",
            "base_ref": "v1.14.0",
            "head_ref": "v1.19.0",
        },
        "investigation": {
            "investigation_id": "investigation-aet-atlas-self-review",
            "investigation_type": "general",
            "question": "How does AET turn its own Bundle into a reviewable evidence map?",
            "scope": sorted(SOURCE_PATHS.values()),
            "limitations": [
                "The example is a source review, not a release authorization.",
                "The generated sidecar remains a deterministic projection of this Bundle.",
            ],
            "completed": True,
        },
        "claims": claims,
        "evidence": evidence,
        "observations": [
            {
                "id": "obs-source-review",
                "type": "agent_tool_result",
                "statement": (
                    "The bounded source review read the Graph Builder, "
                    "Perspective, Viewer, and Bundle Evidence Schema."
                ),
                "source_refs": source_refs,
                "proves": ["The listed source files were included in this review."],
                "does_not_prove": [
                    "Every runtime path works.",
                    "The release is authorized.",
                ],
                "limitations": [
                    "Source inspection requires separate behavioral tests."
                ],
            }
        ],
        "sources": [
            _source(identifier, relative)
            for identifier, relative in SOURCE_PATHS.items()
        ],
        "diagnostics": [],
        "conflicts": [
            {
                "id": "conflict-change-scope-v1",
                "proposition": (
                    "Path binding is useful for scope context but insufficient "
                    "to prove complete real diff grouping."
                ),
                "evidence_refs": ["ev-path-bindings", "ev-no-change-groups"],
                "conflict_type": "interpretation_conflict",
                "resolution_status": "unresolved",
                "explanation": (
                    "Evidence Atlas must keep the missing Change Group field "
                    "or collection as UNKNOWN."
                ),
            }
        ],
        "ledger": [
            {
                "id": "ledger-source-review",
                "timestamp": CREATED_AT,
                "question": "Which source files define the Evidence Atlas boundary?",
                "hypothesis_ref": "primary",
                "action": "read_file",
                "tool_name": "file.read",
                "input_ref": "src-graph",
                "output_ref": "ev-graph-builder",
                "observation_refs": ["obs-source-review"],
                "evidence_candidate_refs": [],
                "effect": "supports_primary",
                "explanation": "Content-addressed source files were read locally.",
            },
            {
                "id": "ledger-disconfirming-search",
                "timestamp": "2026-07-26T12:00:01Z",
                "question": (
                    "Could Bundle v1 alone prove complete real diff grouping?"
                ),
                "hypothesis_ref": "competing:bundle-v1-is-complete",
                "action": "read_file",
                "tool_name": "file.read",
                "input_ref": "src-bundle-schema",
                "output_ref": "ev-no-change-groups",
                "observation_refs": ["obs-source-review"],
                "evidence_candidate_refs": [],
                "effect": "supports_competing",
                "explanation": (
                    "The source review found path bindings but no explicit "
                    "Change Group field in the Evidence record schema."
                ),
            }
        ],
        "policy": {
            "schema_version": "portable-investigation-policy/1.0",
            "allowed_tools": ["file.read"],
            "denied_tools": ["file.write", "git.push"],
            "budgets": {
                "max_tool_calls": 8,
                "max_evidence_candidates": 12,
                "max_verified_evidence": 8,
                "max_run_records_read": 20,
                "max_blob_bytes_read": 0,
            },
            "command_policy": {
                "allow_execution": False,
                "allowed_command_prefixes": [],
            },
            "workspace_policy": {
                "read_only": True,
                "allowed_paths": sorted(SOURCE_PATHS.values()),
                "denied_paths": [".git/", ".aet/"],
            },
            "privacy_policy": {
                "redact_secrets": True,
                "export_reasoning": False,
                "export_raw_tool_output": False,
            },
            "require_competing_hypothesis": True,
            "require_disconfirming_search": True,
        },
        "blobs": {},
        "consumer_guidance": {
            "must": [
                "Cite canonical Evidence IDs for factual claims.",
                "Retain conflict-change-scope-v1 and explicit UNKNOWN.",
            ],
            "must_not": [
                "Treat Mermaid as an evidence authority.",
                "Treat this example as merge or release authorization.",
            ],
        },
        "excluded_reason": "Only source records relevant to the Atlas example are included.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    compile_bundle(payload(), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
