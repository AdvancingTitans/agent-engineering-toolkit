import { readFileSync } from "node:fs";
import { lstat, readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalJson, sha256 } from "./canonical.js";
import { parseStrictJson } from "./strict-json.js";
import { EvidenceBundleError } from "./types.js";
import { assertVerifiedBundle } from "./trusted.js";

const GRAPH_SCHEMA = "aet-evidence-graph/1.0";
const PERSPECTIVE_SCHEMA = "aet-evidence-perspective/1.0";
const PERSPECTIVE_IDS = [
    "claim-chain",
    "investigation-flow",
    "change-scope",
    "verification-coverage",
    "evidence-data-flow",
    "integrations",
    "conflicts",
    "freshness",
    "improvement-chain",
    "regression-lineage"
];
const NODE_TYPES = new Set([
    "intent",
    "constraint",
    "authorization",
    "run",
    "agent",
    "tool_call",
    "tool_result",
    "observation",
    "evidence_candidate",
    "verified_evidence",
    "source",
    "artifact",
    "file",
    "symbol",
    "change_group",
    "command",
    "proof",
    "freshness_result",
    "claim",
    "subclaim",
    "counter_claim",
    "finding",
    "conflict",
    "unknown",
    "limitation",
    "recommendation",
    "policy_rule",
    "budget"
]);
const EDGE_TYPES = new Set([
    "ANSWERS",
    "DECOMPOSES_INTO",
    "SUPPORTED_BY",
    "PARTIALLY_SUPPORTED_BY",
    "CONTRADICTED_BY",
    "LIMITED_BY",
    "DERIVED_FROM",
    "OBSERVED_IN",
    "PRODUCED_BY",
    "EXECUTED_BY",
    "CALLED",
    "RETURNED",
    "APPLIES_TO",
    "CHANGED",
    "DEPENDS_ON",
    "VALIDATES",
    "INVALIDATED_BY",
    "FRESH_FOR",
    "STALE_FOR",
    "AUTHORIZED_BY",
    "VIOLATES",
    "CONSTRAINED_BY",
    "GROUPED_IN",
    "RESOLVES",
    "LEAVES_UNKNOWN",
    "RECOMMENDS",
    "PRECEDES",
    "DUPLICATES"
]);
const NODE_STATUSES = new Set([
    "verified",
    "supported",
    "partially_supported",
    "conflicted",
    "unsupported",
    "unknown",
    "stale",
    "current",
    "resolved",
    "not_applicable",
    "recorded"
]);
const FRESHNESS_STATUSES = new Set([
    "current",
    "relevant_files_changed",
    "workspace_changed",
    "environment_changed",
    "unknown",
    "not_applicable"
]);
const MAX_GRAPH_BYTES = 16 * 1024 * 1024;
const MAX_GRAPH_NODES = 50000;
const MAX_QUERY_NODES = 100;
const MAX_QUERY_DEPTH = 4;
const DEFAULT_GENERATION_POLICY = Object.freeze({
    max_depth: 4,
    max_nodes_per_diagram: 25,
    max_children_per_node: 12,
    max_total_diagrams: 100,
    deduplicate_by_canonical_node_id: true,
    llm_enabled: false,
    mermaid_security_level: "strict",
    allow_html_labels: false,
    allow_external_urls: false,
    allow_external_images: false
});
const DEPENDENCY_INDEX_KEYS = [
    "record_hashes",
    "record_to_nodes",
    "record_to_edges",
    "node_to_edges",
    "node_to_perspectives",
    "node_to_parent_diagrams",
    "record_to_perspectives",
    "record_to_parent_diagrams"
];
const verifiedGraphs = new WeakSet();

const PERSPECTIVE_SPECS = {
    "claim-chain": {
        title: "Claim Chain",
        question: "What evidence supports, contradicts, or limits each Claim?",
        diagram_type: "flowchart",
        direction: "LR",
        roots: [
            "claim"
        ],
        nodes: [
            "intent",
            "claim",
            "verified_evidence",
            "proof",
            "command",
            "observation",
            "conflict",
            "freshness_result",
            "unknown",
            "limitation",
            "recommendation"
        ]
    },
    "investigation-flow": {
        title: "Investigation Flow",
        question: "How did the bounded investigation reach its Claims?",
        diagram_type: "flowchart",
        direction: "LR",
        roots: [
            "run",
            "intent"
        ],
        nodes: [
            "intent",
            "run",
            "tool_call",
            "tool_result",
            "observation",
            "evidence_candidate",
            "verified_evidence",
            "claim",
            "unknown"
        ]
    },
    "change-scope": {
        title: "Change Scope",
        question: "Which declared paths and authorization boundaries apply?",
        diagram_type: "flowchart",
        direction: "TD",
        roots: [
            "change_group",
            "run",
            "intent"
        ],
        nodes: [
            "intent",
            "run",
            "file",
            "change_group",
            "authorization",
            "constraint",
            "proof",
            "verified_evidence",
            "claim",
            "unknown"
        ]
    },
    "verification-coverage": {
        title: "Verification Coverage",
        question: "What does the Proof establish and not establish?",
        diagram_type: "flowchart",
        direction: "LR",
        roots: [
            "proof",
            "claim"
        ],
        nodes: [
            "claim",
            "verified_evidence",
            "proof",
            "command",
            "file",
            "observation",
            "freshness_result",
            "limitation",
            "unknown",
            "recommendation",
            "source",
            "artifact"
        ]
    },
    "evidence-data-flow": {
        title: "Evidence Data Flow",
        question: "How did records become Observations, Evidence, and Claims?",
        diagram_type: "flowchart",
        direction: "LR",
        roots: [
            "run",
            "intent"
        ],
        nodes: [
            "intent",
            "run",
            "source",
            "tool_call",
            "tool_result",
            "observation",
            "evidence_candidate",
            "verified_evidence",
            "claim",
            "conflict",
            "artifact",
            "unknown"
        ]
    },
    integrations: {
        title: "Integration and Sources",
        question: "Which tools, Sources, and trust boundaries are involved?",
        diagram_type: "sequenceDiagram",
        direction: "LR",
        roots: [
            "run",
            "source",
            "tool_call"
        ],
        nodes: [
            "run",
            "agent",
            "tool_call",
            "tool_result",
            "source",
            "artifact",
            "command",
            "proof",
            "authorization",
            "constraint",
            "unknown"
        ]
    },
    conflicts: {
        title: "Conflict and Unknown",
        question: "Which conflicts and unknowns remain?",
        diagram_type: "stateDiagram",
        direction: "TD",
        roots: [
            "conflict",
            "unknown",
            "run"
        ],
        nodes: [
            "claim",
            "verified_evidence",
            "conflict",
            "unknown",
            "freshness_result",
            "limitation",
            "recommendation",
            "run"
        ]
    },
    freshness: {
        title: "Freshness",
        question: "Does each Evidence item still apply?",
        diagram_type: "timeline",
        direction: "LR",
        roots: [
            "freshness_result",
            "verified_evidence"
        ],
        nodes: [
            "verified_evidence",
            "proof",
            "freshness_result",
            "file",
            "claim",
            "unknown",
            "recommendation",
            "limitation"
        ]
    },
    "improvement-chain": {
        title: "Improvement Chain",
        question: "How do Finding, Constraint, Candidate, Verification, and Outcome connect?",
        diagram_type: "flowchart",
        direction: "LR",
        roots: [
            "finding",
            "claim"
        ],
        nodes: [
            "finding",
            "constraint",
            "recommendation",
            "proof",
            "claim",
            "verified_evidence",
            "unknown",
            "limitation",
            "conflict"
        ]
    },
    "regression-lineage": {
        title: "Regression Lineage",
        question: "How does a verified Outcome bind to a Regression Fixture and CI?",
        diagram_type: "flowchart",
        direction: "LR",
        roots: [
            "proof",
            "verified_evidence"
        ],
        nodes: [
            "finding",
            "proof",
            "freshness_result",
            "verified_evidence",
            "claim",
            "recommendation",
            "artifact",
            "unknown",
            "limitation",
            "conflict"
        ]
    }
};

export function buildEvidenceGraph(bundle) {
    assertVerifiedBundle(bundle);
    const nodes = new Map();
    const edges = new Map();
    const claimIds = new Map();
    const evidenceIds = new Map();
    const observationIds = new Map();
    const sourceIds = new Map();
    const manifestRef = ref("manifest.json", "manifest", "investigation");
    const task = bundle.manifest.task;
    const investigation = bundle.manifest.investigation;
    const intentId = addNode(nodes, "intent", task.task_id, {
        title: short(task.request),
        summary: task.request,
        status: "recorded",
        authority: "user_task",
        source_refs: [
            ref("manifest.json", "manifest", "task.request")
        ],
        importance: "high",
        attributes: compact({
            task_id: task.task_id,
            repository: task.repository,
            workspace_id: task.workspace_id,
            base_ref: task.base_ref,
            head_ref: task.head_ref
        })
    });
    const runId = addNode(nodes, "run", investigation.investigation_id, {
        title: `Investigation ${investigation.investigation_id}`,
        summary: investigation.question,
        status: "recorded",
        authority: "portable_investigation",
        source_refs: [
            manifestRef
        ],
        attributes: {
            completed: investigation.completed,
            investigation_type: investigation.investigation_type,
            scope: [
                ...investigation.scope
            ]
        }
    });
    addEdge(edges, runId, intentId, "ANSWERS", manifestRef, "investigates", 90);
    for (const path of investigation.scope){
        const fileId = fileNode(nodes, path, ref("manifest.json", "manifest", "investigation.scope"));
        addEdge(edges, runId, fileId, "APPLIES_TO", ref("manifest.json", "manifest", "investigation.scope"), "scope");
    }
    investigation.limitations.forEach((value, index)=>limitationNode(nodes, edges, runId, value, ref("manifest.json", "manifest", `investigation.limitations[${index}]`)));
    for (const claim of bundle.claims){
        const claimRef = ref("core/claims.jsonl", claim.id, "statement");
        const claimId = addNode(nodes, "claim", claim.id, {
            title: short(claim.statement),
            summary: claim.statement,
            status: claim.status,
            authority: "portable_claim",
            source_refs: [
                claimRef
            ],
            importance: "high",
            freshness: "unknown",
            attributes: {
                record_id: claim.id,
                status_definition: claim.status_definition,
                basis: structuredClone(claim.basis),
                evidence_refs: [
                    ...claim.evidence_refs
                ],
                counter_evidence_refs: [
                    ...claim.counter_evidence_refs
                ],
                observation_refs: [
                    ...claim.observation_refs
                ]
            }
        });
        claimIds.set(claim.id, claimId);
        addEdge(edges, claimId, intentId, "ANSWERS", ref("index.json", "index", "claim_refs"), "answers", 90);
        claim.limitations.forEach((value, index)=>limitationNode(nodes, edges, claimId, value, ref("core/claims.jsonl", claim.id, `limitations[${index}]`)));
        if (claim.smallest_next_action) {
            const recommendationId = addNode(nodes, "recommendation", `${claim.id}:next-action`, {
                title: short(claim.smallest_next_action),
                summary: claim.smallest_next_action,
                status: "recorded",
                authority: "portable_claim",
                source_refs: [
                    ref("core/claims.jsonl", claim.id, "smallest_next_action")
                ]
            });
            addEdge(edges, claimId, recommendationId, "RECOMMENDS", ref("core/claims.jsonl", claim.id, "smallest_next_action"));
        }
        if (claim.status === "unknown") {
            const unknownId = unknownNode(nodes, `claim:${claim.id}`, claim.status_definition, ref("core/claims.jsonl", claim.id, "status"));
            addEdge(edges, claimId, unknownId, "LEAVES_UNKNOWN", ref("core/claims.jsonl", claim.id, "status"), "unknown", 100);
        }
    }
    for (const source of bundle.sources){
        const sourceRef = ref("archive/sources.jsonl", source.id, "type");
        const sourceId = addNode(nodes, "source", source.id, {
            title: `${source.type}: ${source.id}`,
            summary: sourceSummary(source),
            status: "verified",
            authority: source.provenance.source_type ?? "portable_source",
            source_refs: [
                sourceRef
            ],
            freshness: "current",
            attributes: {
                record_id: source.id,
                source_type: source.type,
                locator: structuredClone(source.locator),
                provenance: structuredClone(source.provenance),
                integrity: structuredClone(source.integrity)
            }
        });
        sourceIds.set(source.id, sourceId);
        if (source.locator.path) {
            const fileId = fileNode(nodes, source.locator.path, ref("archive/sources.jsonl", source.id, "locator.path"));
            addEdge(edges, sourceId, fileId, "APPLIES_TO", ref("archive/sources.jsonl", source.id, "locator.path"));
        }
    }
    for (const observation of bundle.observations){
        const observationId = addNode(nodes, "observation", observation.id, {
            title: short(observation.statement),
            summary: observation.statement,
            status: "recorded",
            authority: "observation",
            source_refs: [
                ref("core/observations.jsonl", observation.id, "statement")
            ],
            freshness: "unknown",
            attributes: {
                record_id: observation.id,
                type: observation.type,
                proves: [
                    ...observation.proves
                ],
                does_not_prove: [
                    ...observation.does_not_prove
                ]
            }
        });
        observationIds.set(observation.id, observationId);
        for (const sourceRef of observation.source_refs){
            if (sourceIds.has(sourceRef)) {
                addEdge(edges, observationId, sourceIds.get(sourceRef), "DERIVED_FROM", ref("core/observations.jsonl", observation.id, "source_refs"), "observed in", 70);
            }
        }
        observation.limitations.forEach((value, index)=>limitationNode(nodes, edges, observationId, value, ref("core/observations.jsonl", observation.id, `limitations[${index}]`)));
    }
    for (const evidence of bundle.evidence){
        const freshness = evidence.freshness.status;
        const evidenceStatus = freshness === "current" ? "verified" : freshness === "unknown" ? "unknown" : "stale";
        const evidenceId = addNode(nodes, "verified_evidence", evidence.id, {
            title: short(evidence.proposition),
            summary: evidence.proposition,
            status: evidenceStatus,
            authority: `verified_evidence:${evidence.strength}`,
            source_refs: [
                ref("core/evidence.jsonl", evidence.id, "proposition")
            ],
            freshness,
            importance: "high",
            attributes: {
                record_id: evidence.id,
                kind: evidence.kind,
                strength: evidence.strength,
                strength_definition: evidence.strength_definition,
                bindings: structuredClone(evidence.bindings),
                supports: [
                    ...evidence.supports
                ],
                contradicts: [
                    ...evidence.contradicts
                ],
                integrity: structuredClone(evidence.integrity)
            }
        });
        evidenceIds.set(evidence.id, evidenceId);
        for (const sourceRef of evidence.source_refs){
            if (sourceIds.has(sourceRef)) {
                addEdge(edges, evidenceId, sourceIds.get(sourceRef), "DERIVED_FROM", ref("core/evidence.jsonl", evidence.id, "source_refs"), "derived from", 85);
            }
        }
        for (const path of evidence.bindings.paths ?? []){
            const fileId = fileNode(nodes, path, ref("core/evidence.jsonl", evidence.id, "bindings.paths"));
            addEdge(edges, evidenceId, fileId, "APPLIES_TO", ref("core/evidence.jsonl", evidence.id, "bindings.paths"));
        }
        if ([
            "command_receipt",
            "test_result"
        ].includes(evidence.kind)) {
            const proofId = addNode(nodes, "proof", evidence.id, {
                title: `Proof ${evidence.id}`,
                summary: evidence.strength_definition,
                status: evidenceStatus,
                authority: "deterministic_proof",
                source_refs: [
                    ref("core/evidence.jsonl", evidence.id, "kind")
                ],
                freshness,
                importance: "high",
                attributes: {
                    record_id: evidence.id,
                    does_not_prove: [
                        ...evidence.limitations
                    ]
                }
            });
            addEdge(edges, evidenceId, proofId, "PRODUCED_BY", ref("core/evidence.jsonl", evidence.id, "kind"), "verified by", 90);
            if (evidence.bindings.command?.length) {
                const commandId = addNode(nodes, "command", evidence.id, {
                    title: short(evidence.bindings.command.join(" ")),
                    summary: "Explicit argv recorded by deterministic Proof",
                    status: "verified",
                    authority: "proof_binding",
                    source_refs: [
                        ref("core/evidence.jsonl", evidence.id, "bindings.command")
                    ],
                    attributes: {
                        argv: [
                            ...evidence.bindings.command
                        ]
                    }
                });
                addEdge(edges, proofId, commandId, "EXECUTED_BY", ref("core/evidence.jsonl", evidence.id, "bindings.command"), "executed", 90);
            }
            for (const claimRef of evidence.supports){
                if (freshness === "current" && claimIds.has(claimRef)) {
                    addEdge(edges, proofId, claimIds.get(claimRef), "VALIDATES", ref("core/evidence.jsonl", evidence.id, "supports"), "validates", 95);
                }
            }
        }
        const freshnessId = addNode(nodes, "freshness_result", evidence.id, {
            title: `Freshness: ${freshness}`,
            summary: evidence.freshness.explanation,
            status: freshness === "current" ? "current" : freshness === "unknown" ? "unknown" : "stale",
            authority: "deterministic_freshness",
            source_refs: [
                ref("core/evidence.jsonl", evidence.id, "freshness")
            ],
            freshness,
            importance: freshness === "current" ? "normal" : "high",
            attributes: compact({
                record_id: evidence.id,
                checked_at: evidence.freshness.checked_at,
                effect: evidence.freshness.effect
            })
        });
        addEdge(edges, freshnessId, evidenceId, freshness === "current" ? "FRESH_FOR" : "STALE_FOR", ref("core/evidence.jsonl", evidence.id, "freshness"), freshness === "current" ? "current" : "freshness degraded", 100);
        if (freshness !== "current") {
            addEdge(edges, evidenceId, freshnessId, "INVALIDATED_BY", ref("core/evidence.jsonl", evidence.id, "freshness"), "applicability downgraded", 100);
        }
        if (freshness === "unknown") {
            const unknownId = unknownNode(nodes, `freshness:${evidence.id}`, evidence.freshness.effect, ref("core/evidence.jsonl", evidence.id, "freshness"));
            addEdge(edges, freshnessId, unknownId, "LEAVES_UNKNOWN", ref("core/evidence.jsonl", evidence.id, "freshness"), "unknown", 100);
        }
        evidence.limitations.forEach((value, index)=>limitationNode(nodes, edges, evidenceId, value, ref("core/evidence.jsonl", evidence.id, `limitations[${index}]`)));
    }
    for (const claim of bundle.claims){
        const claimId = claimIds.get(claim.id);
        for (const evidenceRef of claim.evidence_refs){
            const evidence = bundle.evidence.find((item)=>item.id === evidenceRef);
            const current = evidence?.freshness.status === "current";
            const relation = claim.status !== "partially_supported" && current ? "SUPPORTED_BY" : "PARTIALLY_SUPPORTED_BY";
            addEdge(edges, claimId, evidenceIds.get(evidenceRef), relation, ref("core/claims.jsonl", claim.id, "evidence_refs"), current ? "supported by" : "historically supported by (stale)", 100);
        }
        for (const evidenceRef of claim.counter_evidence_refs){
            addEdge(edges, claimId, evidenceIds.get(evidenceRef), "CONTRADICTED_BY", ref("core/claims.jsonl", claim.id, "counter_evidence_refs"), "contradicted by", 100);
        }
        for (const observationRef of claim.observation_refs){
            addEdge(edges, claimId, observationIds.get(observationRef), "OBSERVED_IN", ref("core/claims.jsonl", claim.id, "observation_refs"), "observed in", 60);
        }
    }
    for (const conflict of bundle.conflicts){
        const conflictId = addNode(nodes, "conflict", conflict.id, {
            title: short(conflict.proposition),
            summary: conflict.explanation,
            status: conflict.resolution_status === "resolved" ? "resolved" : "conflicted",
            authority: "portable_conflict",
            source_refs: [
                ref("archive/conflicts.jsonl", conflict.id, "proposition")
            ],
            importance: "high",
            attributes: {
                record_id: conflict.id,
                conflict_type: conflict.conflict_type,
                resolution_status: conflict.resolution_status
            }
        });
        for (const evidenceRef of conflict.evidence_refs){
            addEdge(edges, conflictId, evidenceIds.get(evidenceRef), "CONTRADICTED_BY", ref("archive/conflicts.jsonl", conflict.id, "evidence_refs"), "conflicts", 100);
        }
        if (conflict.resolution_status === "unresolved") {
            const unknownId = unknownNode(nodes, `conflict:${conflict.id}`, conflict.explanation, ref("archive/conflicts.jsonl", conflict.id, "resolution_status"));
            addEdge(edges, conflictId, unknownId, "LEAVES_UNKNOWN", ref("archive/conflicts.jsonl", conflict.id, "resolution_status"), "unresolved", 100);
        }
    }
    let previousCall;
    for (const entry of bundle.ledger){
        const callId = addNode(nodes, "tool_call", entry.id, {
            title: entry.tool_name ?? entry.action,
            summary: entry.explanation,
            status: "recorded",
            authority: "investigation_ledger",
            source_refs: [
                ref("archive/ledger.jsonl", entry.id, "explanation")
            ],
            attributes: compact({
                record_id: entry.id,
                timestamp: entry.timestamp,
                action: entry.action,
                tool_name: entry.tool_name,
                hypothesis_ref: entry.hypothesis_ref,
                effect: entry.effect
            })
        });
        if (previousCall) {
            addEdge(edges, previousCall, callId, "PRECEDES", ref("archive/ledger.jsonl", entry.id, "timestamp"), "then");
        }
        previousCall = callId;
        for (const observationRef of entry.observation_refs){
            if (observationIds.has(observationRef)) {
                addEdge(edges, callId, observationIds.get(observationRef), "RETURNED", ref("archive/ledger.jsonl", entry.id, "observation_refs"));
            }
        }
        if (entry.output_ref && evidenceIds.has(entry.output_ref)) {
            addEdge(edges, evidenceIds.get(entry.output_ref), callId, "PRODUCED_BY", ref("archive/ledger.jsonl", entry.id, "output_ref"));
        }
        for (const candidateRef of entry.evidence_candidate_refs){
            const candidateId = addNode(nodes, "evidence_candidate", candidateRef, {
                title: `Candidate ${candidateRef}`,
                summary: entry.explanation,
                status: "unknown",
                authority: "evidence_candidate_reference",
                source_refs: [
                    ref("archive/ledger.jsonl", entry.id, "evidence_candidate_refs")
                ],
                attributes: {
                    record_id: candidateRef,
                    reference_only: true
                }
            });
            addEdge(edges, callId, candidateId, "RETURNED", ref("archive/ledger.jsonl", entry.id, "evidence_candidate_refs"));
        }
    }
    const unknownPerspectiveIds = {
        "change-scope": unknownNode(nodes, "perspective:change-scope", "Bundle v1 has path bindings but no explicit Change Group; this graph cannot prove the actual diff.", manifestRef),
        "improvement-chain": unknownNode(nodes, "perspective:improvement-chain", "Bundle v1 has no independent Improvement Finding, Constraint, Candidate, Verification, or Outcome records.", manifestRef),
        "regression-lineage": unknownNode(nodes, "perspective:regression-lineage", "Bundle v1 has no bound Improvement Outcome or Regression Fixture records.", manifestRef)
    };
    const nodeValues = [
        ...nodes.values()
    ].sort(byId);
    const edgeValues = [
        ...edges.values()
    ].sort(byId);
    evaluateComplexity(nodeValues, edgeValues);
    const perspectives = buildPerspectives(nodeValues, edgeValues, unknownPerspectiveIds);
    const dependencyIndex = buildDependencyIndex(bundle, nodeValues, edgeValues, perspectives);
    const graph = {
        schema_version: GRAPH_SCHEMA,
        bundle_id: bundle.manifest.bundle.id,
        generated_from: {
            bundle_content_hash: bundle.manifest.bundle.content_hash,
            manifest_sha256: sha256(readFileSync(join(bundle.root, "manifest.json"))),
            index_sha256: sha256(readFileSync(join(bundle.root, bundle.manifest.contents.index)))
        },
        generation_policy: {
            ...DEFAULT_GENERATION_POLICY
        },
        nodes: nodeValues,
        edges: edgeValues,
        perspectives,
        diagnostics: [
            {
                code: "SOURCE_DATA_UNAVAILABLE",
                severity: "info",
                message: "Bundle v1 does not standardize Agent, Symbol, Change Group, Subclaim, Counter Claim, or independent Finding records.",
                source_refs: [
                    manifestRef
                ]
            }
        ],
        dependency_index: dependencyIndex
    };
    validateGraphObject(graph);
    return markVerifiedGraph(graph);
}

export async function loadEvidenceGraph(input) {
    const path = await resolveGraphFile(input);
    const status = await lstat(path);
    if (status.isSymbolicLink() || !status.isFile()) {
        throw new EvidenceBundleError("unsafe_file", "Evidence Graph must be a regular non-symbolic-link file");
    }
    if (status.size > MAX_GRAPH_BYTES) {
        throw new EvidenceBundleError("budget_error", `Evidence Graph exceeds ${MAX_GRAPH_BYTES} bytes`);
    }
    const value = parseStrictJson(await readFile(path, "utf8"), "Evidence Graph");
    validateGraphObject(value);
    return markVerifiedGraph(value);
}

export async function validateEvidenceGraph(input) {
    const graph = typeof input === "string" || input instanceof URL ? await loadEvidenceGraph(input) : input;
    validateGraphObject(graph);
    return {
        report_kind: "evidence_graph_validation",
        status: "PASS",
        bundle_id: graph.bundle_id,
        node_count: graph.nodes.length,
        edge_count: graph.edges.length,
        perspective_count: graph.perspectives.length
    };
}

export function queryPerspective(graph, perspectiveId, options = {}) {
    assertVerifiedGraph(graph);
    const perspective = graph.perspectives.find((item)=>item.id === perspectiveId);
    if (!perspective) {
        throw new EvidenceBundleError("reference_error", `Unknown Perspective: ${perspectiveId}`);
    }
    const maximum = queryBudget(options.maxNodes);
    const nodesById = new Map(graph.nodes.map((node)=>[
            node.id,
            node
        ]));
    const ordered = perspective.node_ids.map((id)=>nodesById.get(id)).filter(Boolean).sort(nodePriority);
    const perspectiveIds = new Set(perspective.node_ids);
    const required = new Set(perspective.root_node_ids.filter((id)=>nodesById.has(id)));
    for (const node of ordered){
        if ([
            "unknown",
            "conflict"
        ].includes(node.type)) {
            required.add(node.id);
        }
    }
    for (const edge of graph.edges){
        if (edge.type === "CONTRADICTED_BY" && perspectiveIds.has(edge.from) && perspectiveIds.has(edge.to)) {
            required.add(edge.from);
            required.add(edge.to);
        }
    }
    if (required.size > maximum) {
        throw new EvidenceBundleError("budget_error", "maxNodes is too small to preserve Perspective roots, conflicts, UNKNOWN, and counter-evidence");
    }
    const selected = new Set(required);
    for (const node of ordered){
        if (selected.size >= maximum) {
            break;
        }
        selected.add(node.id);
    }
    return projection(graph, perspective, selected);
}

export function getNodeSubgraph(graph, nodeId, options = {}) {
    assertVerifiedGraph(graph);
    const depth = queryDepth(options.depth);
    const maximum = queryBudget(options.maxNodes);
    const node = resolveNode(graph, nodeId);
    const selected = boundedTraversal(graph, node.id, depth, maximum);
    return projection(graph, undefined, selected, node.id);
}

export function traceClaimSupport(graph, claimId, options = {}) {
    assertVerifiedGraph(graph);
    const maximum = queryBudget(options.maxNodes);
    const claim = resolveTypedNode(graph, claimId, "claim");
    const directEdges = graph.edges.filter((edge)=>edge.from === claim.id && [
            "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY",
            "CONTRADICTED_BY",
            "OBSERVED_IN",
            "LIMITED_BY",
            "LEAVES_UNKNOWN"
        ].includes(edge.type));
    const required = new Set([
        claim.id,
        ...directEdges.map((edge)=>edge.to)
    ]);
    if (required.size > maximum) {
        throw new EvidenceBundleError("budget_error", "maxNodes is too small to preserve all direct support and counter-evidence");
    }
    const selected = boundedTraversal(graph, claim.id, 3, maximum, required);
    const result = projection(graph, undefined, selected, claim.id);
    return {
        ...result,
        claim_status: claim.status,
        supporting_evidence_ids: directEdges.filter((edge)=>[
                "SUPPORTED_BY",
                "PARTIALLY_SUPPORTED_BY"
            ].includes(edge.type)).map((edge)=>edge.to).sort(),
        counter_evidence_ids: directEdges.filter((edge)=>edge.type === "CONTRADICTED_BY").map((edge)=>edge.to).sort(),
        unknown_node_ids: result.nodes.filter((node)=>node.type === "unknown").map((node)=>node.id).sort()
    };
}

export function traceFreshnessImpact(graph, evidenceId, options = {}) {
    assertVerifiedGraph(graph);
    const maximum = queryBudget(options.maxNodes);
    const evidence = resolveTypedNode(graph, evidenceId, "verified_evidence");
    const required = new Set([
        evidence.id
    ]);
    for (const edge of graph.edges){
        if ((edge.from === evidence.id || edge.to === evidence.id) && [
            "FRESH_FOR",
            "STALE_FOR",
            "INVALIDATED_BY",
            "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY",
            "CONTRADICTED_BY"
        ].includes(edge.type)) {
            required.add(edge.from);
            required.add(edge.to);
        }
    }
    if (required.size > maximum) {
        throw new EvidenceBundleError("budget_error", "maxNodes is too small to preserve the direct Freshness impact");
    }
    const selected = boundedTraversal(graph, evidence.id, 3, maximum, required);
    return {
        ...projection(graph, undefined, selected, evidence.id),
        freshness: evidence.freshness,
        affected_claim_ids: graph.edges.filter((edge)=>selected.has(edge.from) && edge.to === evidence.id && [
                "SUPPORTED_BY",
                "PARTIALLY_SUPPORTED_BY",
                "CONTRADICTED_BY"
            ].includes(edge.type)).map((edge)=>edge.from).sort()
    };
}

export function renderMermaid(graph, options = {}) {
    assertVerifiedGraph(graph);
    const perspectiveId = options.perspectiveId ?? "claim-chain";
    const result = queryPerspective(graph, perspectiveId, {
        maxNodes: options.maxNodes ?? 25
    });
    const type = result.perspective.diagram_type;
    if (type === "sequenceDiagram") {
        return renderSequence(result);
    }
    if (type === "stateDiagram") {
        return renderState(result);
    }
    if (type === "timeline") {
        return renderTimeline(result);
    }
    return renderFlowchart(result);
}

function validateGraphObject(graph) {
    if (!isObject(graph) || graph.schema_version !== GRAPH_SCHEMA || typeof graph.bundle_id !== "string" || graph.bundle_id.length === 0) {
        invalid("Evidence Graph identity is invalid");
    }
    if (!Array.isArray(graph.nodes) || graph.nodes.length > MAX_GRAPH_NODES || !Array.isArray(graph.edges) || !Array.isArray(graph.perspectives) || !Array.isArray(graph.diagnostics)) {
        invalid("Evidence Graph collections are invalid or over budget");
    }
    validateGraphMetadata(graph);
    const nodes = unique(graph.nodes, "node");
    const edges = unique(graph.edges, "edge");
    for (const node of nodes.values()){
        if (!NODE_TYPES.has(node.type) || !NODE_STATUSES.has(node.status) || !FRESHNESS_STATUSES.has(node.freshness) || typeof node.title !== "string" || typeof node.summary !== "string" || !Array.isArray(node.source_refs) || node.source_refs.length === 0) {
            invalid(`Invalid Evidence Graph node: ${String(node.id)}`);
        }
        validateRefs(node.source_refs, `node ${node.id}`);
    }
    for (const edge of edges.values()){
        if (!EDGE_TYPES.has(edge.type) || !nodes.has(edge.from) || !nodes.has(edge.to) || !Array.isArray(edge.source_refs) || edge.source_refs.length === 0) {
            invalid(`Invalid Evidence Graph edge: ${String(edge.id)}`);
        }
        validateRefs(edge.source_refs, `edge ${edge.id}`);
    }
    if (graph.perspectives.length !== PERSPECTIVE_IDS.length || new Set(graph.perspectives.map((item)=>item.id)).size !== PERSPECTIVE_IDS.length) {
        invalid("Evidence Graph must contain exactly the ten fixed Perspectives");
    }
    for (const expected of PERSPECTIVE_IDS){
        const perspective = graph.perspectives.find((item)=>item.id === expected);
        if (!perspective || perspective.schema_version !== PERSPECTIVE_SCHEMA || !Array.isArray(perspective.node_ids) || !Array.isArray(perspective.edge_ids) || !Array.isArray(perspective.root_node_ids) || !Array.isArray(perspective.unknowns)) {
            invalid(`Invalid Perspective: ${expected}`);
        }
        known(perspective.node_ids, nodes, `Perspective ${expected} node`);
        known(perspective.root_node_ids, nodes, `Perspective ${expected} root`);
        known(perspective.edge_ids, edges, `Perspective ${expected} edge`);
    }
    validateDependencyIndex(graph, nodes, edges);
    for (const claim of [
        ...nodes.values()
    ].filter((node)=>node.type === "claim")){
        const declaredCounter = claim.attributes?.counter_evidence_refs;
        if (Array.isArray(declaredCounter)) {
            const actual = graph.edges.filter((edge)=>edge.from === claim.id && edge.type === "CONTRADICTED_BY").map((edge)=>nodes.get(edge.to)?.attributes?.record_id).filter((value)=>typeof value === "string");
            if (!sameSet(new Set(actual), new Set(declaredCounter))) {
                throw new EvidenceBundleError("counter_evidence_error", `Claim ${claim.id} counter-evidence is incomplete`);
            }
        }
        const declaredSupport = claim.attributes?.evidence_refs;
        if (Array.isArray(declaredSupport)) {
            const actual = graph.edges.filter((edge)=>edge.from === claim.id && [
                    "SUPPORTED_BY",
                    "PARTIALLY_SUPPORTED_BY"
                ].includes(edge.type)).map((edge)=>nodes.get(edge.to)?.attributes?.record_id).filter((value)=>typeof value === "string");
            if (!sameSet(new Set(actual), new Set(declaredSupport))) {
                throw new EvidenceBundleError("reference_error", `Claim ${claim.id} support Evidence is incomplete`);
            }
        }
        if (claim.status === "conflicted" && !graph.edges.some((edge)=>edge.from === claim.id && edge.type === "CONTRADICTED_BY")) {
            throw new EvidenceBundleError("counter_evidence_error", `Conflicted Claim ${claim.id} requires counter-evidence`);
        }
        if (claim.status === "supported") {
            const hasCurrentSupport = graph.edges.filter((edge)=>edge.from === claim.id && edge.type === "SUPPORTED_BY").some((edge)=>{
                const evidence = nodes.get(edge.to);
                return evidence?.type === "verified_evidence" && evidence.status === "verified" && evidence.freshness === "current";
            });
            if (!hasCurrentSupport) {
                throw new EvidenceBundleError("grounding_error", `Supported Claim ${claim.id} requires current verified Evidence`);
            }
        }
    }
    for (const evidence of [
        ...nodes.values()
    ].filter((node)=>node.type === "verified_evidence")){
        if (evidence.freshness === "current" && evidence.status !== "verified") {
            throw new EvidenceBundleError("grounding_error", `Current Evidence ${evidence.id} cannot be downgraded or invented`);
        }
        if (evidence.freshness !== "current" && evidence.status === "verified") {
            throw new EvidenceBundleError("grounding_error", `Stale or unknown Evidence ${evidence.id} cannot be verified`);
        }
        if (evidence.freshness !== "current" && !graph.edges.some((edge)=>edge.from === evidence.id && edge.type === "INVALIDATED_BY")) {
            throw new EvidenceBundleError("freshness_error", `Non-current Evidence ${evidence.id} must expose its applicability downgrade`);
        }
    }
    return graph;
}

function validateGraphMetadata(graph) {
    const generated = graph.generated_from;
    if (!isObject(generated) || !sameSet(new Set(Object.keys(generated)), new Set([
        "bundle_content_hash",
        "manifest_sha256",
        "index_sha256"
    ])) || Object.values(generated).some((value)=>typeof value !== "string" || !/^[a-f0-9]{64}$/u.test(value))) {
        invalid("Evidence Graph generated_from identity is invalid");
    }
    if (!isObject(graph.generation_policy) || canonicalJson(graph.generation_policy) !== canonicalJson(DEFAULT_GENERATION_POLICY)) {
        invalid("Evidence Graph generation_policy must contain the complete safe v1.16 policy");
    }
    for (const diagnostic of graph.diagnostics){
        if (!isObject(diagnostic) || typeof diagnostic.code !== "string" || !/^[A-Z][A-Z0-9_]+$/u.test(diagnostic.code) || ![
            "info",
            "warning",
            "error"
        ].includes(diagnostic.severity) || typeof diagnostic.message !== "string" || diagnostic.message.length === 0 || !Array.isArray(diagnostic.source_refs)) {
            invalid("Evidence Graph diagnostic is invalid");
        }
        validateRefs(diagnostic.source_refs, `diagnostic ${diagnostic.code}`);
    }
}

function validateDependencyIndex(graph, nodes, edges) {
    const index = graph.dependency_index;
    if (!isObject(index) || !sameSet(new Set(Object.keys(index)), new Set(DEPENDENCY_INDEX_KEYS))) {
        invalid("Evidence Graph dependency_index is incomplete");
    }
    if (!isObject(index.record_hashes) || Object.values(index.record_hashes).some((value)=>typeof value !== "string" || !/^[a-f0-9]{64}$/u.test(value))) {
        invalid("Evidence Graph dependency record hashes are invalid");
    }
    for (const key of DEPENDENCY_INDEX_KEYS.slice(1)){
        validateDependencyMap(index[key], `dependency_index.${key}`);
    }
    const expectedNodeEdges = {};
    const expectedRecordNodes = {};
    const expectedRecordEdges = {};
    for (const node of nodes.values()){
        for (const sourceRef of node.source_refs){
            addIndexValue(expectedRecordNodes, dependencyKey(sourceRef), node.id);
        }
    }
    for (const edge of edges.values()){
        addIndexValue(expectedNodeEdges, edge.from, edge.id);
        addIndexValue(expectedNodeEdges, edge.to, edge.id);
        for (const sourceRef of edge.source_refs){
            addIndexValue(expectedRecordEdges, dependencyKey(sourceRef), edge.id);
        }
    }
    for (const [actual, expected, label] of [
        [
            index.node_to_edges,
            sortedIndex(expectedNodeEdges),
            "node_to_edges"
        ],
        [
            index.record_to_nodes,
            sortedIndex(expectedRecordNodes),
            "record_to_nodes"
        ],
        [
            index.record_to_edges,
            sortedIndex(expectedRecordEdges),
            "record_to_edges"
        ]
    ]){
        if (canonicalJson(actual) !== canonicalJson(expected)) {
            invalid(`Evidence Graph ${label} is incomplete or inconsistent`);
        }
    }
    const recordKeys = new Set(Object.keys(index.record_hashes));
    for (const key of Object.keys(index.record_to_nodes)){
        if (!recordKeys.has(key)) {
            invalid(`Evidence Graph record_to_nodes references unknown record ${key}`);
        }
    }
    for (const key of Object.keys(index.record_to_edges)){
        if (!recordKeys.has(key)) {
            invalid(`Evidence Graph record_to_edges references unknown record ${key}`);
        }
    }
}

function validateDependencyMap(value, label) {
    if (!isObject(value)) {
        invalid(`Evidence Graph ${label} must be an object`);
    }
    for (const [key, identifiers] of Object.entries(value)){
        if (key.length === 0 || !Array.isArray(identifiers) || identifiers.some((identifier)=>typeof identifier !== "string" || identifier.length === 0) || new Set(identifiers).size !== identifiers.length || canonicalJson(identifiers) !== canonicalJson([
            ...identifiers
        ].sort())) {
            invalid(`Evidence Graph ${label} contains an invalid dependency list`);
        }
    }
}

function buildPerspectives(nodes, edges, unknownPerspectiveIds) {
    const nodesByType = new Map();
    for (const node of nodes){
        if (!nodesByType.has(node.type)) {
            nodesByType.set(node.type, []);
        }
        nodesByType.get(node.type).push(node.id);
    }
    return PERSPECTIVE_IDS.map((id)=>{
        const spec = PERSPECTIVE_SPECS[id];
        const selected = new Set(nodes.filter((node)=>spec.nodes.includes(node.type)).map((node)=>node.id));
        const unknowns = [];
        const unknownId = unknownPerspectiveIds[id];
        if (unknownId) {
            selected.add(unknownId);
            unknowns.push(id === "change-scope" ? "UNKNOWN: Bundle v1 path bindings do not establish an actual Change Group or diff." : "UNKNOWN: Bundle v1 does not contain the independent Improvement records required by this Perspective.");
        }
        const selectedEdges = edges.filter((edge)=>selected.has(edge.from) && selected.has(edge.to));
        const connected = new Set(selectedEdges.flatMap((edge)=>[
                edge.from,
                edge.to
            ]));
        for (const rootType of spec.roots){
            for (const nodeId of nodesByType.get(rootType) ?? []){
                if (selected.has(nodeId)) {
                    connected.add(nodeId);
                }
            }
            if (connected.size > 0) {
                break;
            }
        }
        if (unknownId && selected.has(unknownId)) {
            connected.add(unknownId);
        }
        const rootType = spec.roots.find((type)=>(nodesByType.get(type) ?? []).some((nodeId)=>connected.has(nodeId)));
        const roots = (nodesByType.get(rootType) ?? []).filter((nodeId)=>connected.has(nodeId)).sort();
        if (unknownId && selected.has(unknownId) && !roots.includes(unknownId)) {
            roots.push(unknownId);
        }
        const nodeIds = [
            ...connected
        ].sort();
        const edgeIds = selectedEdges.filter((edge)=>connected.has(edge.from) && connected.has(edge.to)).map((edge)=>edge.id).sort();
        return {
            schema_version: PERSPECTIVE_SCHEMA,
            id,
            title: spec.title,
            question: spec.question,
            description: spec.question,
            coverage_status: unknowns.length > 0 ? "UNKNOWN" : "PASS",
            diagram_type: spec.diagram_type,
            direction: spec.direction,
            root_node_ids: roots,
            node_ids: nodeIds,
            edge_ids: edgeIds,
            node_count: nodeIds.length,
            edge_count: edgeIds.length,
            unknowns
        };
    });
}

function buildDependencyIndex(bundle, nodes, edges, perspectives) {
    const recordHashes = {};
    for (const collection of [
        "claims",
        "evidence",
        "observations",
        "sources",
        "diagnostics",
        "conflicts",
        "ledger"
    ]){
        for (const record of bundle[collection]){
            recordHashes[`${collection}:${record.id}`] = sha256(canonicalJson(record));
        }
    }
    for (const name of [
        "manifest",
        "index",
        "policy"
    ]){
        recordHashes[name] = sha256(canonicalJson(bundle[name]));
    }
    const recordToNodes = {};
    const recordToEdges = {};
    const nodeToEdges = {};
    const nodeToPerspectives = {};
    const recordToPerspectives = {};
    for (const node of nodes){
        for (const sourceRef of node.source_refs){
            addIndexValue(recordToNodes, dependencyKey(sourceRef), node.id);
        }
    }
    for (const edge of edges){
        addIndexValue(nodeToEdges, edge.from, edge.id);
        addIndexValue(nodeToEdges, edge.to, edge.id);
        for (const sourceRef of edge.source_refs){
            addIndexValue(recordToEdges, dependencyKey(sourceRef), edge.id);
        }
    }
    const nodesById = new Map(nodes.map((node)=>[
            node.id,
            node
        ]));
    for (const perspective of perspectives){
        for (const nodeId of perspective.node_ids){
            addIndexValue(nodeToPerspectives, nodeId, perspective.id);
            const node = nodesById.get(nodeId);
            for (const sourceRef of node?.source_refs ?? []){
                addIndexValue(recordToPerspectives, dependencyKey(sourceRef), perspective.id);
            }
        }
    }
    return {
        record_hashes: sortedObject(recordHashes),
        record_to_nodes: sortedIndex(recordToNodes),
        record_to_edges: sortedIndex(recordToEdges),
        node_to_edges: sortedIndex(nodeToEdges),
        node_to_perspectives: sortedIndex(nodeToPerspectives),
        node_to_parent_diagrams: {},
        record_to_perspectives: sortedIndex(recordToPerspectives),
        record_to_parent_diagrams: {}
    };
}

function boundedTraversal(graph, rootId, depth, maximum, required = new Set([
    rootId
])) {
    const selected = new Set(required);
    const queue = [
        [
            rootId,
            0
        ]
    ];
    while (queue.length > 0 && selected.size < maximum){
        const [current, currentDepth] = queue.shift();
        if (currentDepth >= depth) {
            continue;
        }
        const candidates = graph.edges.filter((edge)=>edge.from === current || edge.to === current).sort(edgePriority);
        for (const edge of candidates){
            const neighbor = edge.from === current ? edge.to : edge.from;
            if (!selected.has(neighbor)) {
                selected.add(neighbor);
                queue.push([
                    neighbor,
                    currentDepth + 1
                ]);
                if (selected.size >= maximum) {
                    break;
                }
            }
        }
    }
    return selected;
}

function projection(graph, perspective, selected, rootNodeId) {
    const nodes = graph.nodes.filter((node)=>selected.has(node.id)).sort(byId);
    const edges = graph.edges.filter((edge)=>selected.has(edge.from) && selected.has(edge.to)).sort(edgePriority);
    return {
        ...(perspective ? {
            perspective
        } : {}),
        ...(rootNodeId ? {
            root_node_id: rootNodeId
        } : {}),
        nodes,
        edges,
        truncated: perspective ? selected.size < perspective.node_ids.length : false
    };
}

function addNode(nodes, type, identifier, values) {
    const id = stableId(type, identifier);
    if (!nodes.has(id)) {
        nodes.set(id, {
            id,
            type,
            source_refs: values.source_refs,
            title: values.title,
            summary: values.summary,
            status: values.status,
            authority: values.authority,
            freshness: values.freshness ?? "not_applicable",
            importance: values.importance ?? "normal",
            complexity: {
                score: 0,
                classification: "leaf",
                reasons: []
            },
            tags: [],
            attributes: values.attributes ?? {}
        });
    }
    return id;
}

function addEdge(edges, from, to, type, sourceRef, label = type.toLowerCase().replaceAll("_", " "), priority = 50) {
    if (!from || !to) {
        return;
    }
    const id = `edge:${sha256(`${from}\0${type}\0${to}\0${edges.size}`).slice(0, 24)}`;
    edges.set(id, {
        id,
        from,
        to,
        type,
        source_refs: [
            sourceRef
        ],
        authority: "deterministic_reference",
        freshness_effect: [
            "SUPPORTED_BY",
            "PARTIALLY_SUPPORTED_BY",
            "VALIDATES",
            "FRESH_FOR",
            "STALE_FOR",
            "INVALIDATED_BY"
        ].includes(type) ? "required" : "not_applicable",
        render: {
            label,
            priority
        }
    });
}

function fileNode(nodes, path, sourceRef) {
    const id = `node:file:${sha256(path).slice(0, 20)}`;
    if (!nodes.has(id)) {
        nodes.set(id, {
            id,
            type: "file",
            source_refs: [
                sourceRef
            ],
            title: path.split("/").at(-1) || path,
            summary: path,
            status: "recorded",
            authority: "path_binding",
            freshness: "not_applicable",
            importance: "normal",
            complexity: {
                score: 0,
                classification: "leaf",
                reasons: []
            },
            tags: [
                "file"
            ],
            attributes: {
                path
            }
        });
    }
    return id;
}

function limitationNode(nodes, edges, parentId, value, sourceRef) {
    const limitationId = addNode(nodes, "limitation", `${parentId}:${sourceRef.field}`, {
        title: short(value),
        summary: value,
        status: "recorded",
        authority: "portable_limitation",
        source_refs: [
            sourceRef
        ],
        importance: "high"
    });
    addEdge(edges, parentId, limitationId, "LIMITED_BY", sourceRef, "limited by", 100);
}

function unknownNode(nodes, identifier, reason, sourceRef) {
    return addNode(nodes, "unknown", identifier, {
        title: `UNKNOWN: ${short(identifier)}`,
        summary: reason,
        status: "unknown",
        authority: "deterministic_projection",
        source_refs: [
            sourceRef
        ],
        importance: "high"
    });
}

function evaluateComplexity(nodes, edges) {
    const incoming = new Map();
    const outgoing = new Map();
    const relations = new Map();
    for (const edge of edges){
        outgoing.set(edge.from, (outgoing.get(edge.from) ?? 0) + 1);
        incoming.set(edge.to, (incoming.get(edge.to) ?? 0) + 1);
        for (const id of [
            edge.from,
            edge.to
        ]){
            if (!relations.has(id)) {
                relations.set(id, new Set());
            }
            relations.get(id).add(edge.type);
        }
    }
    for (const node of nodes){
        let score = (outgoing.get(node.id) ?? 0) + Math.min(incoming.get(node.id) ?? 0, 3);
        const reasons = [];
        const relationCount = relations.get(node.id)?.size ?? 0;
        if (relationCount > 1) {
            score += relationCount - 1;
            reasons.push("multiple relation types");
        }
        if (node.type === "conflict" || node.status === "conflicted") {
            score += 3;
            reasons.push("conflict");
        }
        if (node.type === "unknown" || node.status === "unknown") {
            score += 2;
            reasons.push("unknown");
        }
        if (node.status === "stale") {
            score += 2;
            reasons.push("freshness transition");
        }
        node.complexity = {
            score,
            classification: score >= 8 ? "mandatory_decomposition" : score >= 4 ? "expandable" : "leaf",
            reasons
        };
    }
}

function renderFlowchart(result) {
    const direction = result.perspective.direction === "TD" ? "TD" : "LR";
    const lines = [
        `flowchart ${direction}`
    ];
    appendFlowNodes(lines, result.nodes);
    for (const edge of result.edges){
        lines.push(`  ${mermaidId(edge.from)} -->|${safeLabel(edge.render?.label ?? edge.type)}| ${mermaidId(edge.to)}`);
    }
    return `${lines.join("\n")}\n`;
}

function renderSequence(result) {
    const lines = [
        "sequenceDiagram"
    ];
    for (const node of result.nodes){
        lines.push(`  participant ${mermaidId(node.id)} as ${safeLabel(node.title)}`);
    }
    for (const edge of result.edges){
        lines.push(`  ${mermaidId(edge.from)}->>${mermaidId(edge.to)}: ${safeLabel(edge.render?.label ?? edge.type)}`);
    }
    return `${lines.join("\n")}\n`;
}

function renderState(result) {
    const lines = [
        "stateDiagram-v2"
    ];
    for (const node of result.nodes){
        lines.push(`  state "${safeLabel(node.title)}" as ${mermaidId(node.id)}`);
    }
    for (const edge of result.edges){
        lines.push(`  ${mermaidId(edge.from)} --> ${mermaidId(edge.to)}: ${safeLabel(edge.render?.label ?? edge.type)}`);
    }
    return `${lines.join("\n")}\n`;
}

function renderTimeline(result) {
    const lines = [
        "timeline",
        `  title ${safeLabel(result.perspective.title)}`,
        "  section Evidence freshness"
    ];
    for (const node of result.nodes){
        lines.push(`    ${safeLabel(node.title)} : ${safeLabel(node.status)}`);
    }
    return `${lines.join("\n")}\n`;
}

function appendFlowNodes(lines, nodes) {
    for (const node of nodes){
        const prefix = node.type === "unknown" ? "[UNKNOWN] " : node.type === "conflict" ? "[CONFLICT] " : node.status === "stale" ? "[STALE] " : "";
        lines.push(`  ${mermaidId(node.id)}["${safeLabel(prefix + node.title)}"]`);
    }
}

function safeLabel(value) {
    return String(value).replace(/https?:\/\/\S+/giu, "[external-url-redacted]").replace(/javascript\s*:/giu, "").replace(/<\/?(?:script|img|iframe)[^>]*>/giu, "").replace(/%%|\{\{|\}\}|[\u0000-\u001f\u007f]/gu, " ").replace(/["\\<>]/gu, "'").replace(/\s+/gu, " ").trim().slice(0, 120);
}

function resolveGraphPath(input) {
    const raw = input instanceof URL ? fileURLToPath(input) : input;
    if (typeof raw !== "string" || raw.length === 0) {
        throw new TypeError("Evidence Graph path must be a non-empty string or file URL");
    }
    return resolve(raw);
}

async function resolveGraphFile(input) {
    const candidate = resolveGraphPath(input);
    const status = await lstat(candidate);
    if (status.isSymbolicLink()) {
        throw new EvidenceBundleError("unsafe_file", "Evidence Graph path cannot be a symbolic link");
    }
    if (status.isFile()) {
        return candidate;
    }
    if (!status.isDirectory()) {
        throw new EvidenceBundleError("unsafe_file", "Evidence Graph path must be a file or directory");
    }
    for (const relative of [
        "graph.json",
        "graph/graph.json"
    ]){
        const path = join(candidate, relative);
        try {
            const childStatus = await lstat(path);
            if (childStatus.isSymbolicLink()) {
                throw new EvidenceBundleError("unsafe_file", `Evidence Graph path contains a symbolic link: ${relative}`);
            }
            if (childStatus.isFile()) {
                return path;
            }
        } catch (error) {
            if (error instanceof EvidenceBundleError) {
                throw error;
            }
            if (error?.code !== "ENOENT") {
                throw error;
            }
        }
    }
    throw new EvidenceBundleError("read_error", "Evidence Graph directory has no graph.json or graph/graph.json");
}

function resolveNode(graph, identifier) {
    const node = graph.nodes.find((item)=>item.id === identifier || item.attributes?.record_id === identifier);
    if (!node) {
        throw new EvidenceBundleError("reference_error", `Unknown Evidence Graph node: ${identifier}`);
    }
    return node;
}

function resolveTypedNode(graph, identifier, type) {
    const node = graph.nodes.find((item)=>item.type === type && (item.id === identifier || item.attributes?.record_id === identifier));
    if (!node) {
        throw new EvidenceBundleError("reference_error", `Node ${identifier} is not a ${type}`);
    }
    return node;
}

function queryBudget(value = 25) {
    if (!Number.isInteger(value) || value < 1 || value > MAX_QUERY_NODES) {
        throw new EvidenceBundleError("budget_error", `maxNodes must be between 1 and ${MAX_QUERY_NODES}`);
    }
    return value;
}

function queryDepth(value = 2) {
    if (!Number.isInteger(value) || value < 0 || value > MAX_QUERY_DEPTH) {
        throw new EvidenceBundleError("budget_error", `depth must be between 0 and ${MAX_QUERY_DEPTH}`);
    }
    return value;
}

function markVerifiedGraph(graph) {
    deepFreeze(graph);
    verifiedGraphs.add(graph);
    return graph;
}

function assertVerifiedGraph(graph) {
    if (!verifiedGraphs.has(graph) || !Object.isFrozen(graph)) {
        throw new EvidenceBundleError("unverified_handle", "This API requires an immutable Evidence Graph returned by buildEvidenceGraph or loadEvidenceGraph");
    }
}

function deepFreeze(value, seen = new WeakSet()) {
    if (typeof value !== "object" || value === null || seen.has(value)) {
        return;
    }
    seen.add(value);
    for (const item of Object.values(value)){
        deepFreeze(item, seen);
    }
    Object.freeze(value);
}

function validateRefs(values, label) {
    for (const value of values){
        if (!isObject(value) || typeof value.collection !== "string" || value.collection.length === 0 || typeof value.record_id !== "string" || value.record_id.length === 0 || typeof value.field !== "string" || value.field.length === 0) {
            invalid(`${label} has an invalid source reference`);
        }
    }
}

function unique(values, label) {
    const result = new Map();
    for (const value of values){
        if (!isObject(value) || typeof value.id !== "string" || value.id.length === 0 || result.has(value.id)) {
            invalid(`Evidence Graph ${label} IDs must be unique non-empty strings`);
        }
        result.set(value.id, value);
    }
    return result;
}

function known(ids, values, label) {
    if (ids.some((id)=>typeof id !== "string" || !values.has(id))) {
        invalid(`${label} reference is missing`);
    }
}

function stableId(type, identifier) {
    const safe = String(identifier).replace(/[^A-Za-z0-9_-]+/gu, "-").replace(/^-+|-+$/gu, "");
    return safe ? `node:${type}:${safe}` : `node:${type}:${sha256(`${type}\0${identifier}`).slice(0, 16)}`;
}

function ref(collection, recordId, field) {
    return {
        collection,
        record_id: recordId,
        field
    };
}

function sourceSummary(source) {
    const values = Object.entries(source.locator).filter(([, value])=>value !== undefined && value !== "").map(([key, value])=>`${key}=${String(value)}`);
    return values.join(", ") || source.type;
}

function compact(value) {
    return Object.fromEntries(Object.entries(value).filter(([, item])=>item !== undefined));
}

function dependencyKey(sourceRef) {
    const names = {
        "manifest.json": "manifest",
        "index.json": "index",
        "policy.json": "policy",
        "core/claims.jsonl": "claims",
        "core/evidence.jsonl": "evidence",
        "core/observations.jsonl": "observations",
        "archive/sources.jsonl": "sources",
        "archive/diagnostics.jsonl": "diagnostics",
        "archive/conflicts.jsonl": "conflicts",
        "archive/ledger.jsonl": "ledger"
    };
    const name = names[sourceRef.collection] ?? sourceRef.collection;
    return [
        "manifest",
        "index",
        "policy"
    ].includes(name) ? name : `${name}:${sourceRef.record_id}`;
}

function addIndexValue(index, key, value) {
    if (!index[key]) {
        index[key] = [];
    }
    if (!index[key].includes(value)) {
        index[key].push(value);
    }
}

function sortedIndex(index) {
    return Object.fromEntries(Object.keys(index).sort().map((key)=>[
            key,
            [
                ...index[key]
            ].sort()
        ]));
}

function sortedObject(value) {
    return Object.fromEntries(Object.keys(value).sort().map((key)=>[
            key,
            value[key]
        ]));
}

function short(value, maximum = 96) {
    const compactValue = String(value).replace(/\s+/gu, " ").trim();
    return compactValue.length <= maximum ? compactValue : `${compactValue.slice(0, maximum - 1)}…`;
}

function mermaidId(value) {
    return `N_${sha256(value).slice(0, 16)}`;
}

function edgePriority(left, right) {
    const leftPriority = left.render?.priority ?? 50;
    const rightPriority = right.render?.priority ?? 50;
    return rightPriority - leftPriority || left.id.localeCompare(right.id);
}

function nodePriority(left, right) {
    const ranks = {
        conflict: 0,
        unknown: 1,
        claim: 2,
        verified_evidence: 3,
        freshness_result: 4
    };
    return (ranks[left.type] ?? 10) - (ranks[right.type] ?? 10) || left.id.localeCompare(right.id);
}

function byId(left, right) {
    return left.id.localeCompare(right.id);
}

function sameSet(left, right) {
    return left.size === right.size && [
        ...left
    ].every((item)=>right.has(item));
}

function isObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalid(message) {
    throw new EvidenceBundleError("invalid_graph", message);
}
