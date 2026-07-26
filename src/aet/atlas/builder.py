"""Build the canonical, source-backed Evidence Graph from one valid Bundle."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aet.bundle import validate_bundle

from .model import (
    GRAPH_SCHEMA,
    derived_id,
    edge_id,
    merge_policy,
    record_hashes,
    source_ref,
    stable_id,
)


_COLLECTION_PATHS = {
    "claims": "core/claims.jsonl",
    "evidence": "core/evidence.jsonl",
    "observations": "core/observations.jsonl",
    "sources": "archive/sources.jsonl",
    "diagnostics": "archive/diagnostics.jsonl",
    "conflicts": "archive/conflicts.jsonl",
    "ledger": "archive/ledger.jsonl",
    "manifest": "manifest.json",
    "index": "index.json",
    "policy": "policy.json",
}

_STALE_FRESHNESS = {
    "relevant_files_changed",
    "workspace_changed",
    "environment_changed",
}


class GraphBuilder:
    """Accumulate canonical nodes and source-backed edges without inference."""

    def __init__(self, bundle: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
        self.bundle = bundle
        self.policy = dict(policy)
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.diagnostics: list[dict[str, Any]] = []
        self.dependencies: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: {
                "nodes": set(),
                "edges": set(),
                "perspectives": set(),
                "parent_diagrams": set(),
            }
        )

    def node(
        self,
        node_type: str,
        identifier: str,
        *,
        title: str,
        summary: str,
        status: str,
        authority: str,
        refs: list[dict[str, str]],
        freshness: str = "not_applicable",
        importance: str = "normal",
        tags: list[str] | None = None,
        attributes: Mapping[str, Any] | None = None,
        canonical_id: str | None = None,
    ) -> str:
        node_id = canonical_id or stable_id(node_type, identifier)
        candidate = {
            "id": node_id,
            "type": node_type,
            "source_refs": refs,
            "title": title,
            "summary": summary,
            "status": status,
            "authority": authority,
            "freshness": freshness,
            "importance": importance,
            "complexity": {"score": 0, "classification": "leaf", "reasons": []},
            "tags": sorted(set(tags or [])),
            "attributes": dict(attributes or {}),
        }
        existing = self.nodes.get(node_id)
        if existing is not None:
            comparable_existing = dict(existing)
            comparable_candidate = dict(candidate)
            comparable_existing.pop("source_refs", None)
            comparable_candidate.pop("source_refs", None)
            if comparable_existing != comparable_candidate:
                self._diagnostic(
                    "DUPLICATE_NODE",
                    "error",
                    f"canonical node {node_id} was derived with conflicting content",
                    refs,
                )
                return node_id
            merged_refs = {
                (ref["collection"], ref["record_id"], ref["field"]): ref
                for ref in [*existing["source_refs"], *refs]
            }
            existing["source_refs"] = [
                merged_refs[key] for key in sorted(merged_refs)
            ]
            for ref in refs:
                self.dependencies[_dependency_key(ref)]["nodes"].add(node_id)
            return node_id
        self.nodes[node_id] = candidate
        for ref in refs:
            self.dependencies[_dependency_key(ref)]["nodes"].add(node_id)
        return node_id

    def edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
        *,
        refs: list[dict[str, str]],
        label: str | None = None,
        authority: str = "deterministic_reference",
        freshness_effect: str = "not_applicable",
        priority: int = 50,
    ) -> str | None:
        if from_id not in self.nodes or to_id not in self.nodes:
            self._diagnostic(
                "UNRESOLVED_EDGE",
                "warning",
                f"{edge_type} references an unavailable graph node",
                refs,
            )
            return None
        ordinal = sum(
            edge["from"] == from_id
            and edge["to"] == to_id
            and edge["type"] == edge_type
            for edge in self.edges.values()
        )
        identifier = edge_id(from_id, edge_type, to_id, ordinal)
        edge = {
            "id": identifier,
            "from": from_id,
            "to": to_id,
            "type": edge_type,
            "source_refs": refs,
            "authority": authority,
            "freshness_effect": freshness_effect,
            "render": {
                "label": label or edge_type.lower().replace("_", " "),
                "priority": priority,
            },
        }
        self.edges[identifier] = edge
        for ref in refs:
            self.dependencies[_dependency_key(ref)]["edges"].add(identifier)
        return identifier

    def _diagnostic(
        self,
        code: str,
        severity: str,
        message: str,
        refs: list[dict[str, str]],
    ) -> None:
        self.diagnostics.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "source_refs": refs,
            }
        )


def build_evidence_graph(
    bundle_or_path: Mapping[str, Any] | Path,
    *,
    generation_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic graph without modifying the source Bundle."""
    bundle = (
        validate_bundle(Path(bundle_or_path))
        if not isinstance(bundle_or_path, Mapping)
        else bundle_or_path
    )
    policy = merge_policy(generation_policy)
    builder = GraphBuilder(bundle, policy)
    manifest = bundle["manifest"]

    intent_id = _build_manifest_nodes(builder)
    claim_ids = _build_claims(builder, intent_id)
    source_ids = _build_sources(builder)
    observation_ids = _build_observations(builder, source_ids)
    evidence_ids = _build_evidence(builder, source_ids, claim_ids)
    _link_claims(builder, claim_ids, evidence_ids, observation_ids)
    _build_conflicts(builder, evidence_ids)
    _build_ledger(builder, observation_ids, evidence_ids)
    _build_policy(builder)
    _compute_complexity(builder)

    generated_from = _input_identity(bundle)
    graph = {
        "schema_version": GRAPH_SCHEMA,
        "bundle_id": manifest["bundle"]["id"],
        "generated_from": generated_from,
        "generation_policy": policy,
        "nodes": sorted(builder.nodes.values(), key=lambda item: item["id"]),
        "edges": sorted(builder.edges.values(), key=lambda item: item["id"]),
        "perspectives": [],
        "diagnostics": sorted(
            builder.diagnostics,
            key=lambda item: (item["severity"], item["code"], item["message"]),
        ),
        "dependency_index": {
            "record_hashes": record_hashes(bundle),
            "record_to_nodes": {
                key: sorted(value["nodes"])
                for key, value in sorted(builder.dependencies.items())
                if value["nodes"]
            },
            "record_to_edges": {
                key: sorted(value["edges"])
                for key, value in sorted(builder.dependencies.items())
                if value["edges"]
            },
            "node_to_edges": _node_to_edges(builder.edges.values()),
            "node_to_perspectives": {},
            "node_to_parent_diagrams": {},
            "record_to_perspectives": {},
            "record_to_parent_diagrams": {},
        },
    }
    return graph


def _build_manifest_nodes(builder: GraphBuilder) -> str:
    manifest = builder.bundle["manifest"]
    task = manifest["task"]
    investigation = manifest["investigation"]
    intent_ref = source_ref("manifest.json", "manifest", "task.request")
    intent_id = builder.node(
        "intent",
        task["task_id"],
        title=_short(task["request"]),
        summary=task["request"],
        status="recorded",
        authority="user_task",
        refs=[intent_ref],
        importance="high",
        tags=["intent"],
        attributes={
            "task_id": task["task_id"],
            "repository": task["repository"],
            "workspace_id": task["workspace_id"],
            "base_ref": task.get("base_ref"),
            "head_ref": task.get("head_ref"),
        },
    )
    investigation_ref = source_ref(
        "manifest.json", "manifest", "investigation.question"
    )
    run_ref = source_ref("manifest.json", "manifest", "investigation")
    run_id = builder.node(
        "run",
        investigation["investigation_id"],
        title=f"Investigation {investigation['investigation_id']}",
        summary=investigation["question"],
        status="recorded",
        authority="portable_investigation",
        refs=[run_ref],
        tags=["investigation"],
        attributes={
            "completed": investigation["completed"],
            "investigation_type": investigation["investigation_type"],
            "scope": list(investigation["scope"]),
        },
    )
    builder.edge(
        run_id,
        intent_id,
        "ANSWERS",
        refs=[investigation_ref],
        label="investigates",
        priority=90,
    )
    for index, limitation in enumerate(investigation.get("limitations", [])):
        _limitation_node(
            builder,
            run_id,
            "manifest.json",
            "manifest",
            f"investigation.limitations[{index}]",
            limitation,
        )
    for path in investigation.get("scope", []):
        path_id = _file_node(
            builder,
            path,
            source_ref("manifest.json", "manifest", "investigation.scope"),
        )
        builder.edge(
            run_id,
            path_id,
            "APPLIES_TO",
            refs=[source_ref("manifest.json", "manifest", "investigation.scope")],
            label="scope",
        )
    for node_type, reason in (
        ("agent", "Bundle v1 does not standardize the executing Agent identity."),
        ("symbol", "Bundle v1 does not contain symbol-level bindings."),
        ("change_group", "Declared scope and path bindings are not change groups."),
        ("subclaim", "Bundle v1 does not standardize Claim decomposition."),
        ("counter_claim", "Counter-evidence is not an independent Counter Claim."),
        ("finding", "Bundle v1 does not contain an independent Finding collection."),
    ):
        builder._diagnostic(
            "SOURCE_DATA_UNAVAILABLE",
            "info",
            f"{node_type}: {reason}",
            [investigation_ref],
        )
    return intent_id


def _build_claims(builder: GraphBuilder, intent_id: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for claim in builder.bundle["claims"]:
        ref = source_ref("core/claims.jsonl", claim["id"], "statement")
        claim_id = builder.node(
            "claim",
            claim["id"],
            title=_short(claim["statement"]),
            summary=claim["statement"],
            status=claim["status"],
            authority="portable_claim",
            refs=[ref],
            freshness="unknown",
            importance="high",
            tags=[claim["basis"]["type"]],
            attributes={
                "status_definition": claim["status_definition"],
                "basis": claim["basis"],
            },
        )
        result[claim["id"]] = claim_id
        builder.edge(
            claim_id,
            intent_id,
            "ANSWERS",
            refs=[source_ref("index.json", "index", "claim_refs")],
            label="answers",
            priority=90,
        )
        for index, limitation in enumerate(claim.get("limitations", [])):
            _limitation_node(
                builder,
                claim_id,
                "core/claims.jsonl",
                claim["id"],
                f"limitations[{index}]",
                limitation,
            )
        action = claim.get("smallest_next_action")
        if isinstance(action, str):
            recommendation_id = builder.node(
                "recommendation",
                f"{claim['id']}:next-action",
                title=_short(action),
                summary=action,
                status="recorded",
                authority="portable_claim",
                refs=[
                    source_ref(
                        "core/claims.jsonl",
                        claim["id"],
                        "smallest_next_action",
                    )
                ],
                tags=["next-action"],
            )
            builder.edge(
                claim_id,
                recommendation_id,
                "RECOMMENDS",
                refs=[
                    source_ref(
                        "core/claims.jsonl",
                        claim["id"],
                        "smallest_next_action",
                    )
                ],
                label="next action",
            )
        if claim["status"] == "unknown":
            unknown_id = builder.node(
                "unknown",
                f"claim:{claim['id']}",
                title=f"Unknown: {_short(claim['statement'], 72)}",
                summary=claim["status_definition"],
                status="unknown",
                authority="portable_claim",
                refs=[source_ref("core/claims.jsonl", claim["id"], "status")],
                importance="high",
                tags=["claim"],
            )
            builder.edge(
                claim_id,
                unknown_id,
                "LEAVES_UNKNOWN",
                refs=[source_ref("core/claims.jsonl", claim["id"], "status")],
                priority=100,
            )
    return result


def _build_sources(builder: GraphBuilder) -> dict[str, str]:
    result: dict[str, str] = {}
    for source in builder.bundle["sources"]:
        ref = source_ref("archive/sources.jsonl", source["id"], "type")
        locator = source["locator"]
        summary = ", ".join(
            f"{key}={value}" for key, value in sorted(locator.items()) if value
        )
        node_id = builder.node(
            "source",
            source["id"],
            title=f"{source['type']}: {source['id']}",
            summary=summary or source["type"],
            status="verified",
            authority=source["provenance"]["source_type"],
            refs=[ref],
            freshness="current",
            tags=[source["type"]],
            attributes={
                "source_type": source["type"],
                "locator": locator,
                "provenance": source["provenance"],
                "integrity": source["integrity"],
            },
        )
        result[source["id"]] = node_id
        if source["type"] == "user_instruction":
            authorization_id = builder.node(
                "authorization",
                source["id"],
                title=f"Authorization source {source['id']}",
                summary=summary or "Explicit user instruction source",
                status="verified",
                authority="user_instruction",
                refs=[ref],
                importance="high",
                tags=["authorization"],
                attributes={"locator": locator},
            )
            builder.edge(
                authorization_id,
                node_id,
                "DERIVED_FROM",
                refs=[ref],
                priority=100,
            )
        path = locator.get("path")
        if isinstance(path, str):
            file_id = _file_node(
                builder,
                path,
                source_ref("archive/sources.jsonl", source["id"], "locator.path"),
            )
            builder.edge(
                node_id,
                file_id,
                "APPLIES_TO",
                refs=[
                    source_ref(
                        "archive/sources.jsonl", source["id"], "locator.path"
                    )
                ],
            )
        blob_ref = locator.get("blob_ref")
        if isinstance(blob_ref, str):
            artifact_id = builder.node(
                "artifact",
                blob_ref,
                title=f"Blob {blob_ref[-12:]}",
                summary="Content-addressed Bundle Blob",
                status="verified",
                authority="bundle_integrity",
                refs=[
                    source_ref(
                        "archive/sources.jsonl", source["id"], "locator.blob_ref"
                    )
                ],
                attributes={"blob_ref": blob_ref},
            )
            builder.edge(
                node_id,
                artifact_id,
                "DERIVED_FROM",
                refs=[
                    source_ref(
                        "archive/sources.jsonl", source["id"], "locator.blob_ref"
                    )
                ],
            )
    return result


def _build_observations(
    builder: GraphBuilder, source_ids: Mapping[str, str]
) -> dict[str, str]:
    result: dict[str, str] = {}
    for observation in builder.bundle["observations"]:
        ref = source_ref(
            "core/observations.jsonl", observation["id"], "statement"
        )
        node_id = builder.node(
            "observation",
            observation["id"],
            title=_short(observation["statement"]),
            summary=observation["statement"],
            status="recorded",
            authority="observation",
            refs=[ref],
            freshness="unknown",
            tags=[observation["type"]],
            attributes={
                "proves": list(observation["proves"]),
                "does_not_prove": list(observation["does_not_prove"]),
            },
        )
        result[observation["id"]] = node_id
        for source_identifier in observation["source_refs"]:
            source_id = source_ids.get(source_identifier)
            if source_id:
                builder.edge(
                    node_id,
                    source_id,
                    "DERIVED_FROM",
                    refs=[
                        source_ref(
                            "core/observations.jsonl",
                            observation["id"],
                            "source_refs",
                        )
                    ],
                    label="observed in",
                )
            else:
                builder._diagnostic(
                    "MISSING_REFERENCE",
                    "warning",
                    f"Observation {observation['id']} references unavailable Source {source_identifier}",
                    [
                        source_ref(
                            "core/observations.jsonl",
                            observation["id"],
                            "source_refs",
                        )
                    ],
                )
        for index, limitation in enumerate(observation.get("limitations", [])):
            _limitation_node(
                builder,
                node_id,
                "core/observations.jsonl",
                observation["id"],
                f"limitations[{index}]",
                limitation,
            )
    return result


def _build_evidence(
    builder: GraphBuilder,
    source_ids: Mapping[str, str],
    claim_ids: Mapping[str, str],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for evidence in builder.bundle["evidence"]:
        freshness = evidence["freshness"]["status"]
        status = "verified" if freshness == "current" else (
            "unknown" if freshness == "unknown" else "stale"
        )
        ref = source_ref(
            "core/evidence.jsonl", evidence["id"], "proposition"
        )
        node_id = builder.node(
            "verified_evidence",
            evidence["id"],
            title=_short(evidence["proposition"]),
            summary=evidence["proposition"],
            status=status,
            authority=f"verified_evidence:{evidence['strength']}",
            refs=[ref],
            freshness=freshness,
            importance="high",
            tags=[evidence["kind"], evidence["strength"]],
            attributes={
                "kind": evidence["kind"],
                "strength": evidence["strength"],
                "strength_definition": evidence["strength_definition"],
                "bindings": evidence["bindings"],
                "integrity": evidence["integrity"],
                "checked_at": evidence["freshness"].get("checked_at"),
            },
        )
        result[evidence["id"]] = node_id
        if evidence["kind"] == "authority_fact":
            authorization_id = builder.node(
                "authorization",
                evidence["id"],
                title=f"Authorization {evidence['id']}",
                summary=evidence["proposition"],
                status=status,
                authority=f"authority_fact:{evidence['strength']}",
                refs=[ref],
                freshness=freshness,
                importance="high",
                tags=["authorization"],
                attributes={"bindings": evidence["bindings"]},
            )
            builder.edge(
                authorization_id,
                node_id,
                "DERIVED_FROM",
                refs=[ref],
                priority=100,
            )
        for source_identifier in evidence["source_refs"]:
            source_id = source_ids.get(source_identifier)
            if source_id:
                builder.edge(
                    node_id,
                    source_id,
                    "DERIVED_FROM",
                    refs=[
                        source_ref(
                            "core/evidence.jsonl", evidence["id"], "source_refs"
                        )
                    ],
                    label="derived from",
                    priority=85,
                )
            else:
                builder._diagnostic(
                    "MISSING_REFERENCE",
                    "warning",
                    f"Evidence {evidence['id']} references unavailable Source {source_identifier}",
                    [
                        source_ref(
                            "core/evidence.jsonl",
                            evidence["id"],
                            "source_refs",
                        )
                    ],
                )
        for path in evidence.get("bindings", {}).get("paths", []):
            file_id = _file_node(
                builder,
                path,
                source_ref(
                    "core/evidence.jsonl", evidence["id"], "bindings.paths"
                ),
            )
            builder.edge(
                node_id,
                file_id,
                "APPLIES_TO",
                refs=[
                    source_ref(
                        "core/evidence.jsonl", evidence["id"], "bindings.paths"
                    )
                ],
                label="applies to",
            )
        _build_proof(builder, evidence, node_id, claim_ids)
        _build_freshness(builder, evidence, node_id)
        for index, limitation in enumerate(evidence.get("limitations", [])):
            _limitation_node(
                builder,
                node_id,
                "core/evidence.jsonl",
                evidence["id"],
                f"limitations[{index}]",
                limitation,
            )
    return result


def _build_proof(
    builder: GraphBuilder,
    evidence: Mapping[str, Any],
    evidence_id: str,
    claim_ids: Mapping[str, str],
) -> None:
    if evidence["kind"] not in {"command_receipt", "test_result"}:
        return
    ref = source_ref("core/evidence.jsonl", evidence["id"], "kind")
    proof_id = builder.node(
        "proof",
        evidence["id"],
        title=f"Proof {evidence['id']}",
        summary=evidence["strength_definition"],
        status="verified"
        if evidence["freshness"]["status"] == "current"
        else "stale",
        authority="deterministic_proof",
        refs=[ref],
        freshness=evidence["freshness"]["status"],
        importance="high",
        tags=[evidence["kind"]],
        attributes={
            "does_not_prove": list(evidence.get("limitations", [])),
            "integrity": evidence["integrity"],
            "checked_at": evidence["freshness"].get("checked_at"),
        },
    )
    builder.edge(
        evidence_id,
        proof_id,
        "PRODUCED_BY",
        refs=[ref],
        label="verified by",
        priority=90,
    )
    command = evidence.get("bindings", {}).get("command")
    if isinstance(command, list) and command:
        command_ref = source_ref(
            "core/evidence.jsonl", evidence["id"], "bindings.command"
        )
        command_id = builder.node(
            "command",
            evidence["id"],
            title=_short(" ".join(command)),
            summary="Explicit argv recorded by deterministic Proof",
            status="verified",
            authority="proof_binding",
            refs=[command_ref],
            attributes={"argv": list(command)},
        )
        builder.edge(
            proof_id,
            command_id,
            "EXECUTED_BY",
            refs=[command_ref],
            label="executed",
            priority=90,
        )
    for claim_ref in (
        evidence.get("supports", [])
        if evidence["freshness"]["status"] == "current"
        else []
    ):
        claim_id = claim_ids.get(claim_ref)
        if claim_id:
            builder.edge(
                proof_id,
                claim_id,
                "VALIDATES",
                refs=[
                    source_ref(
                        "core/evidence.jsonl", evidence["id"], "supports"
                    )
                ],
                label="validates",
                freshness_effect="required",
                priority=95,
            )


def _build_freshness(
    builder: GraphBuilder, evidence: Mapping[str, Any], evidence_id: str
) -> None:
    freshness = evidence["freshness"]
    freshness_ref = source_ref(
        "core/evidence.jsonl", evidence["id"], "freshness"
    )
    status = freshness["status"]
    freshness_id = builder.node(
        "freshness_result",
        evidence["id"],
        title=f"Freshness: {status}",
        summary=freshness["explanation"],
        status="current"
        if status == "current"
        else ("unknown" if status == "unknown" else "stale"),
        authority="deterministic_freshness",
        refs=[freshness_ref],
        freshness=status,
        importance="high" if status != "current" else "normal",
        tags=[status],
        attributes={
            "checked_at": freshness.get("checked_at"),
            "effect": freshness["effect"],
        },
    )
    builder.edge(
        freshness_id,
        evidence_id,
        "FRESH_FOR" if status == "current" else "STALE_FOR",
        refs=[freshness_ref],
        label="current" if status == "current" else "freshness degraded",
        freshness_effect="required",
        priority=100,
    )
    if status != "current":
        builder.edge(
            evidence_id,
            freshness_id,
            "INVALIDATED_BY",
            refs=[freshness_ref],
            label="applicability downgraded by",
            freshness_effect="required",
            priority=100,
        )
    action = freshness.get("recommended_action")
    if isinstance(action, str):
        recommendation_id = builder.node(
            "recommendation",
            f"freshness:{evidence['id']}",
            title=_short(action),
            summary=action,
            status="recorded",
            authority="freshness_result",
            refs=[
                source_ref(
                    "core/evidence.jsonl",
                    evidence["id"],
                    "freshness.recommended_action",
                )
            ],
            tags=["rerun"],
        )
        builder.edge(
            freshness_id,
            recommendation_id,
            "RECOMMENDS",
            refs=[
                source_ref(
                    "core/evidence.jsonl",
                    evidence["id"],
                    "freshness.recommended_action",
                )
            ],
        )
    if status == "unknown":
        unknown_id = builder.node(
            "unknown",
            f"freshness:{evidence['id']}",
            title=f"Unknown freshness: {evidence['id']}",
            summary=freshness["effect"],
            status="unknown",
            authority="deterministic_freshness",
            refs=[freshness_ref],
            importance="high",
            tags=["freshness"],
        )
        builder.edge(
            freshness_id,
            unknown_id,
            "LEAVES_UNKNOWN",
            refs=[freshness_ref],
            priority=100,
        )


def _link_claims(
    builder: GraphBuilder,
    claim_ids: Mapping[str, str],
    evidence_ids: Mapping[str, str],
    observation_ids: Mapping[str, str],
) -> None:
    for claim in builder.bundle["claims"]:
        claim_id = claim_ids[claim["id"]]
        for evidence_ref in claim["evidence_refs"]:
            if evidence_ref in evidence_ids:
                evidence = next(
                    item
                    for item in builder.bundle["evidence"]
                    if item["id"] == evidence_ref
                )
                current = evidence["freshness"]["status"] == "current"
                relation = (
                    "SUPPORTED_BY"
                    if claim["status"] != "partially_supported" and current
                    else "PARTIALLY_SUPPORTED_BY"
                )
                builder.edge(
                    claim_id,
                    evidence_ids[evidence_ref],
                    relation,
                    refs=[
                        source_ref(
                            "core/claims.jsonl", claim["id"], "evidence_refs"
                        )
                    ],
                    label=(
                        "supported by"
                        if current
                        else "historically supported by (stale)"
                    ),
                    freshness_effect="required",
                    priority=100,
                )
            else:
                builder._diagnostic(
                    "MISSING_REFERENCE",
                    "warning",
                    f"Claim {claim['id']} references unavailable Evidence {evidence_ref}",
                    [
                        source_ref(
                            "core/claims.jsonl", claim["id"], "evidence_refs"
                        )
                    ],
                )
        for evidence_ref in claim["counter_evidence_refs"]:
            if evidence_ref in evidence_ids:
                builder.edge(
                    claim_id,
                    evidence_ids[evidence_ref],
                    "CONTRADICTED_BY",
                    refs=[
                        source_ref(
                            "core/claims.jsonl",
                            claim["id"],
                            "counter_evidence_refs",
                        )
                    ],
                    priority=100,
                )
            else:
                builder._diagnostic(
                    "MISSING_REFERENCE",
                    "warning",
                    f"Claim {claim['id']} references unavailable counter-evidence {evidence_ref}",
                    [
                        source_ref(
                            "core/claims.jsonl",
                            claim["id"],
                            "counter_evidence_refs",
                        )
                    ],
                )
        for observation_ref in claim["observation_refs"]:
            if observation_ref in observation_ids:
                builder.edge(
                    claim_id,
                    observation_ids[observation_ref],
                    "OBSERVED_IN",
                    refs=[
                        source_ref(
                            "core/claims.jsonl",
                            claim["id"],
                            "observation_refs",
                        )
                    ],
                    authority="deterministic_reference",
                    priority=60,
                )
            else:
                builder._diagnostic(
                    "MISSING_REFERENCE",
                    "warning",
                    f"Claim {claim['id']} references unavailable Observation {observation_ref}",
                    [
                        source_ref(
                            "core/claims.jsonl",
                            claim["id"],
                            "observation_refs",
                        )
                    ],
                )


def _build_conflicts(
    builder: GraphBuilder, evidence_ids: Mapping[str, str]
) -> None:
    for conflict in builder.bundle["conflicts"]:
        ref = source_ref(
            "archive/conflicts.jsonl", conflict["id"], "proposition"
        )
        conflict_id = builder.node(
            "conflict",
            conflict["id"],
            title=_short(conflict["proposition"]),
            summary=conflict["explanation"],
            status=(
                "resolved"
                if conflict["resolution_status"] == "resolved"
                else "conflicted"
            ),
            authority="portable_conflict",
            refs=[ref],
            importance="high",
            tags=[conflict["conflict_type"], conflict["resolution_status"]],
            attributes={
                "conflict_type": conflict["conflict_type"],
                "resolution_status": conflict["resolution_status"],
            },
        )
        for evidence_ref in conflict["evidence_refs"]:
            if evidence_ref in evidence_ids:
                builder.edge(
                    conflict_id,
                    evidence_ids[evidence_ref],
                    "CONTRADICTED_BY",
                    refs=[
                        source_ref(
                            "archive/conflicts.jsonl",
                            conflict["id"],
                            "evidence_refs",
                        )
                    ],
                    priority=100,
                )
        if conflict["resolution_status"] == "unresolved":
            unknown_id = builder.node(
                "unknown",
                f"conflict:{conflict['id']}",
                title=f"Unresolved conflict {conflict['id']}",
                summary=conflict["explanation"],
                status="unknown",
                authority="portable_conflict",
                refs=[
                    source_ref(
                        "archive/conflicts.jsonl",
                        conflict["id"],
                        "resolution_status",
                    )
                ],
                importance="high",
                tags=["conflict"],
            )
            builder.edge(
                conflict_id,
                unknown_id,
                "LEAVES_UNKNOWN",
                refs=[
                    source_ref(
                        "archive/conflicts.jsonl",
                        conflict["id"],
                        "resolution_status",
                    )
                ],
                priority=100,
            )


def _build_ledger(
    builder: GraphBuilder,
    observation_ids: Mapping[str, str],
    evidence_ids: Mapping[str, str],
) -> None:
    previous_id: str | None = None
    for entry in builder.bundle["ledger"]:
        ref = source_ref(
            "archive/ledger.jsonl", entry["id"], "explanation"
        )
        call_id = builder.node(
            "tool_call",
            entry["id"],
            title=entry.get("tool_name", entry["action"]),
            summary=entry["explanation"],
            status="recorded",
            authority="investigation_ledger",
            refs=[ref],
            tags=[entry["action"], entry["effect"]],
            attributes={
                "timestamp": entry["timestamp"],
                "question": entry["question"],
                "hypothesis_ref": entry.get("hypothesis_ref"),
                "action": entry["action"],
                "tool_name": entry.get("tool_name"),
                "effect": entry["effect"],
            },
        )
        if previous_id:
            builder.edge(
                previous_id,
                call_id,
                "PRECEDES",
                refs=[source_ref("archive/ledger.jsonl", entry["id"], "timestamp")],
                label="then",
            )
        previous_id = call_id
        for observation_ref in entry["observation_refs"]:
            if observation_ref in observation_ids:
                builder.edge(
                    call_id,
                    observation_ids[observation_ref],
                    "RETURNED",
                    refs=[
                        source_ref(
                            "archive/ledger.jsonl",
                            entry["id"],
                            "observation_refs",
                        )
                    ],
                )
        output_ref = entry.get("output_ref")
        if isinstance(output_ref, str) and output_ref in evidence_ids:
            builder.edge(
                evidence_ids[output_ref],
                call_id,
                "PRODUCED_BY",
                refs=[
                    source_ref(
                        "archive/ledger.jsonl", entry["id"], "output_ref"
                    )
                ],
            )
        for candidate_ref in entry["evidence_candidate_refs"]:
            candidate_id = builder.node(
                "evidence_candidate",
                candidate_ref,
                title=f"Candidate {candidate_ref}",
                summary=entry["explanation"],
                status="unknown",
                authority="evidence_candidate",
                refs=[
                    source_ref(
                        "archive/ledger.jsonl",
                        entry["id"],
                        "evidence_candidate_refs",
                    )
                ],
                tags=["candidate"],
            )
            builder.edge(
                call_id,
                candidate_id,
                "RETURNED",
                refs=[
                    source_ref(
                        "archive/ledger.jsonl",
                        entry["id"],
                        "evidence_candidate_refs",
                    )
                ],
            )


def _build_policy(builder: GraphBuilder) -> None:
    policy = builder.bundle["policy"]
    for name, value in sorted(policy["budgets"].items()):
        ref = source_ref("policy.json", "policy", f"budgets.{name}")
        budget_id = builder.node(
            "budget",
            name,
            title=name,
            summary=f"Maximum allowed value: {value}",
            status="recorded",
            authority="portable_policy",
            refs=[ref],
            tags=["budget"],
            attributes={"maximum": value},
        )
        for call in [
            node
            for node in builder.nodes.values()
            if node["type"] == "tool_call"
        ]:
            builder.edge(
                call["id"],
                budget_id,
                "CONSTRAINED_BY",
                refs=[ref],
                priority=40,
            )
    command_policy = policy["command_policy"]
    auth_ref = source_ref("policy.json", "policy", "command_policy")
    auth_id = builder.node(
        "constraint",
        "command-policy",
        title="Command execution policy",
        summary=(
            "Execution explicitly allowed"
            if command_policy["allow_execution"]
            else "Execution denied"
        ),
        status="recorded",
        authority="portable_policy",
        refs=[auth_ref],
        importance="high",
        tags=["execution"],
        attributes=command_policy,
    )
    for call in [
        node
        for node in builder.nodes.values()
        if node["type"] in {"tool_call", "command"}
    ]:
        builder.edge(
            call["id"],
            auth_id,
            "CONSTRAINED_BY",
            refs=[auth_ref],
            priority=95,
        )
    workspace_ref = source_ref("policy.json", "policy", "workspace_policy")
    constraint_id = builder.node(
        "constraint",
        "workspace-policy",
        title="Workspace policy",
        summary="Read-only workspace policy"
        if policy["workspace_policy"]["read_only"]
        else "Workspace writes may be allowed",
        status="recorded",
        authority="portable_policy",
        refs=[workspace_ref],
        importance="high",
        tags=["workspace", "read-only"]
        if policy["workspace_policy"]["read_only"]
        else ["workspace"],
        attributes=policy["workspace_policy"],
    )
    for file_node in [
        node for node in builder.nodes.values() if node["type"] == "file"
    ]:
        builder.edge(
            file_node["id"],
            constraint_id,
            "CONSTRAINED_BY",
            refs=[workspace_ref],
            priority=75,
        )
    privacy_ref = source_ref("policy.json", "policy", "privacy_policy")
    builder.node(
        "policy_rule",
        "privacy-policy",
        title="Privacy policy",
        summary="Secret redaction and export boundaries",
        status="recorded",
        authority="portable_policy",
        refs=[privacy_ref],
        importance="high",
        tags=["privacy"],
        attributes=policy["privacy_policy"],
    )


def _file_node(
    builder: GraphBuilder, path: str, ref: dict[str, str]
) -> str:
    return builder.node(
        "file",
        path,
        title=path.rsplit("/", 1)[-1],
        summary=path,
        status="recorded",
        authority="path_binding",
        refs=[ref],
        tags=["file"],
        attributes={"path": path},
        canonical_id=derived_id("file", path),
    )


def _limitation_node(
    builder: GraphBuilder,
    parent_id: str,
    collection: str,
    record_id: str,
    field: str,
    limitation: str,
) -> None:
    ref = source_ref(collection, record_id, field)
    limitation_id = builder.node(
        "limitation",
        f"{record_id}:{field}",
        title=_short(limitation),
        summary=limitation,
        status="recorded",
        authority="portable_limitation",
        refs=[ref],
        importance="high",
        tags=["limitation"],
    )
    builder.edge(
        parent_id,
        limitation_id,
        "LIMITED_BY",
        refs=[ref],
        label="limited by",
        priority=100,
    )


def _compute_complexity(builder: GraphBuilder) -> None:
    incoming: Counter[str] = Counter()
    outgoing: Counter[str] = Counter()
    relation_types: dict[str, set[str]] = defaultdict(set)
    for edge in builder.edges.values():
        outgoing[edge["from"]] += 1
        incoming[edge["to"]] += 1
        relation_types[edge["from"]].add(edge["type"])
        relation_types[edge["to"]].add(edge["type"])
    for node in builder.nodes.values():
        reasons: list[str] = []
        score = outgoing[node["id"]] + min(incoming[node["id"]], 3)
        distinct = len(relation_types[node["id"]])
        if distinct > 1:
            score += distinct - 1
            reasons.append("multiple relation types")
        if node["type"] == "conflict" or node["status"] == "conflicted":
            score += 3
            reasons.append("conflict")
        if node["type"] == "unknown" or node["status"] == "unknown":
            score += 2
            reasons.append("unknown")
        if node["freshness"] in _STALE_FRESHNESS:
            score += 2
            reasons.append("freshness transition")
        if outgoing[node["id"]] >= 3:
            reasons.append("multiple child entities")
        related_types = {
            builder.nodes[edge["to"]]["type"]
            for edge in builder.edges.values()
            if edge["from"] == node["id"] and edge["to"] in builder.nodes
        }
        if len(related_types) >= 3:
            score += 2
            reasons.append("cross-domain relations")
        classification = (
            "mandatory_decomposition"
            if score >= 8
            else ("expandable" if score >= 4 else "leaf")
        )
        node["complexity"] = {
            "score": score,
            "classification": classification,
            "reasons": reasons,
        }


def _input_identity(bundle: Mapping[str, Any]) -> dict[str, str]:
    root = Path(str(bundle["root"]))
    manifest_raw = (root / "manifest.json").read_bytes()
    files = bundle.get("_files", {})
    index_raw = files.get("index.json")
    if not isinstance(index_raw, bytes):
        index_raw = (root / "index.json").read_bytes()
    return {
        "bundle_content_hash": bundle["manifest"]["bundle"]["content_hash"],
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "index_sha256": hashlib.sha256(index_raw).hexdigest(),
    }


def _node_to_edges(edges: Any) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        result[edge["from"]].append(edge["id"])
        result[edge["to"]].append(edge["id"])
    return {key: sorted(value) for key, value in sorted(result.items())}


def _dependency_key(ref: Mapping[str, str]) -> str:
    collection = ref["collection"]
    record_id = ref["record_id"]
    for name, path in _COLLECTION_PATHS.items():
        if collection == path:
            return f"{name}:{record_id}" if name not in {"manifest", "index", "policy"} else name
    return f"{collection}:{record_id}"


def _short(value: str, maximum: int = 96) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= maximum else compact[: maximum - 1] + "…"
