import type {
  ClaimStatus,
  EvidenceKind,
  EvidenceStrength,
  FreshnessStatus,
  PortableClaim,
  PortableEvidence,
  PortableEvidenceBundleManifest,
  PortableObservation,
  PortableReviewResult,
  PortableSource,
} from "@aet/protocol-types";

export type {
  ClaimStatus,
  EvidenceKind,
  EvidenceStrength,
  FreshnessStatus,
  PortableClaim,
  PortableEvidence,
  PortableEvidenceBundleManifest,
  PortableObservation,
  PortableReviewConclusion,
  PortableReviewResult,
  PortableSource,
} from "@aet/protocol-types";

export interface LoadedEvidenceBundle {
  root: string;
  manifest: PortableEvidenceBundleManifest;
  index: Record<string, unknown>;
  claims: PortableClaim[];
  evidence: PortableEvidence[];
  observations: PortableObservation[];
  sources: PortableSource[];
  diagnostics: Record<string, unknown>[];
  conflicts: Record<string, unknown>[];
  ledger: Record<string, unknown>[];
  policy: Record<string, unknown>;
  consumerGuide: string;
  report: string;
}

export interface BundleValidationReport {
  report_kind: "portable_evidence_bundle_validation";
  status: "PASS";
  bundle_id: string;
  verified_file_count: number;
  claim_count: number;
  evidence_count: number;
  observation_count: number;
}

export interface ClaimQuery {
  ids?: Iterable<string>;
  status?: ClaimStatus | Iterable<ClaimStatus>;
  text?: string;
}

export interface EvidenceQuery {
  ids?: Iterable<string>;
  kind?: EvidenceKind | Iterable<EvidenceKind>;
  strength?: EvidenceStrength | Iterable<EvidenceStrength>;
  freshness?: FreshnessStatus | Iterable<FreshnessStatus>;
  claimId?: string;
  text?: string;
}

export interface PromptContextOptions {
  claimIds?: Iterable<string>;
  includeObservations?: boolean;
  maxCharacters?: number;
}

export interface ReviewReferenceValidationReport {
  report_kind: "portable_review_reference_validation";
  status: "PASS";
  bundle_id: string;
  conclusion_count: number;
  validated_conclusion_refs: string[];
}

export type EvidenceAtlasNodeType =
  | "intent"
  | "constraint"
  | "authorization"
  | "run"
  | "agent"
  | "tool_call"
  | "tool_result"
  | "observation"
  | "evidence_candidate"
  | "verified_evidence"
  | "source"
  | "artifact"
  | "file"
  | "symbol"
  | "change_group"
  | "command"
  | "proof"
  | "freshness_result"
  | "claim"
  | "subclaim"
  | "counter_claim"
  | "finding"
  | "conflict"
  | "unknown"
  | "limitation"
  | "recommendation"
  | "policy_rule"
  | "budget";

export interface EvidenceAtlasSourceRef {
  collection: string;
  record_id: string;
  field: string;
}

export interface EvidenceAtlasNode {
  id: string;
  type: EvidenceAtlasNodeType;
  source_refs: EvidenceAtlasSourceRef[];
  title: string;
  summary: string;
  status:
    | "verified"
    | "supported"
    | "partially_supported"
    | "conflicted"
    | "unsupported"
    | "unknown"
    | "stale"
    | "current"
    | "resolved"
    | "not_applicable"
    | "recorded";
  authority: string;
  freshness: string;
  importance: string;
  complexity: {
    score: number;
    classification: "leaf" | "expandable" | "mandatory_decomposition";
    reasons: string[];
  };
  tags: string[];
  attributes: Record<string, unknown>;
}

export interface EvidenceAtlasEdge {
  id: string;
  from: string;
  to: string;
  type: string;
  source_refs: EvidenceAtlasSourceRef[];
  authority: string;
  freshness_effect: string;
  render: {
    label: string;
    priority: number;
  };
}

export type EvidenceAtlasPerspectiveId =
  | "claim-chain"
  | "investigation-flow"
  | "change-scope"
  | "verification-coverage"
  | "evidence-data-flow"
  | "integrations"
  | "conflicts"
  | "freshness"
  | "improvement-chain"
  | "regression-lineage";

export interface EvidenceAtlasPerspective {
  schema_version: "aet-evidence-perspective/1.0";
  id: EvidenceAtlasPerspectiveId;
  title: string;
  question: string;
  description: string;
  coverage_status: "PASS" | "UNKNOWN";
  diagram_type:
    | "flowchart"
    | "sequenceDiagram"
    | "stateDiagram"
    | "timeline";
  direction: "LR" | "TD";
  root_node_ids: string[];
  node_ids: string[];
  edge_ids: string[];
  node_count: number;
  edge_count: number;
  unknowns: string[];
}

export interface EvidenceGraph {
  schema_version: "aet-evidence-graph/1.0";
  bundle_id: string;
  generated_from: {
    bundle_content_hash: string;
    manifest_sha256: string;
    index_sha256: string;
  };
  generation_policy: EvidenceAtlasGenerationPolicy;
  nodes: EvidenceAtlasNode[];
  edges: EvidenceAtlasEdge[];
  perspectives: EvidenceAtlasPerspective[];
  diagnostics: Record<string, unknown>[];
  dependency_index: {
    record_hashes: Record<string, string>;
    record_to_nodes: Record<string, string[]>;
    record_to_edges: Record<string, string[]>;
    node_to_edges: Record<string, string[]>;
    node_to_perspectives: Record<string, string[]>;
    node_to_parent_diagrams: Record<string, string[]>;
    record_to_perspectives: Record<string, string[]>;
    record_to_parent_diagrams: Record<string, string[]>;
  };
}

export interface EvidenceAtlasGenerationPolicy {
  max_depth: 4;
  max_nodes_per_diagram: 25;
  max_children_per_node: 12;
  max_total_diagrams: 100;
  deduplicate_by_canonical_node_id: true;
  llm_enabled: false;
  mermaid_security_level: "strict";
  allow_html_labels: false;
  allow_external_urls: false;
  allow_external_images: false;
}

export interface EvidenceGraphValidationReport {
  report_kind: "evidence_graph_validation";
  status: "PASS";
  bundle_id: string;
  node_count: number;
  edge_count: number;
  perspective_count: 10;
}

export interface EvidenceGraphQueryOptions {
  maxNodes?: number;
}

export interface EvidenceNodeSubgraphOptions
  extends EvidenceGraphQueryOptions {
  depth?: number;
}

export interface EvidenceGraphProjection {
  perspective?: EvidenceAtlasPerspective;
  root_node_id?: string;
  nodes: EvidenceAtlasNode[];
  edges: EvidenceAtlasEdge[];
  truncated: boolean;
}

export interface ClaimSupportTrace extends EvidenceGraphProjection {
  claim_status: EvidenceAtlasNode["status"];
  supporting_evidence_ids: string[];
  counter_evidence_ids: string[];
  unknown_node_ids: string[];
}

export interface FreshnessImpactTrace extends EvidenceGraphProjection {
  freshness: string;
  affected_claim_ids: string[];
}

export interface MermaidRenderOptions extends EvidenceGraphQueryOptions {
  perspectiveId?: EvidenceAtlasPerspectiveId;
}

export interface ValidatedPlanEditItem {
  edit_id: string;
  disposition: "REQUIRED" | "OPTIONAL" | "INVESTIGATE" | "DO_NOT_EDIT";
  path: string;
  symbol: string | null;
  intent: string;
  expected_change: string;
  rationale: string;
  evidence_refs: string[];
  atlas_refs: string[];
  source_refs: string[];
  dependencies: string[];
  tests: string[];
  risks: string[];
  limitations: string[];
}

export interface EvidenceLinkedPlan {
  schema_version: "evidence-linked-plan/1.0";
  plan_id: string;
  status:
    | "READY_FOR_HUMAN_REVIEW"
    | "NEEDS_EVIDENCE"
    | "PARTIAL"
    | "BLOCKED"
    | "SUPERSEDED";
  authority: "PROPOSED";
  edit_items: ValidatedPlanEditItem[];
  verification_steps: Record<string, unknown>[];
  diagnostics: Record<string, unknown>[];
  conflicts: Record<string, unknown>[];
  unknowns: Record<string, unknown>[];
  [key: string]: unknown;
}

export interface PlanEditFilter {
  path?: string;
  disposition?: ValidatedPlanEditItem["disposition"];
}

export interface PlanReference {
  schema_version: "plan-reference/1.0";
  reference_id: string;
  kind: string;
  [key: string]: unknown;
}

export interface PlanReferenceValidationReport {
  schema_version: "plan-reference-validation/1.0";
  status: "PASS";
  plan_id: string;
  reference_count: number;
  resolved_reference_count: number;
}

export class EvidenceBundleError extends Error {
  readonly code: string;
}

export function loadBundle(root: string | URL): Promise<LoadedEvidenceBundle>;
export const loadEvidenceBundle: typeof loadBundle;
export function validateBundle(
  input: string | URL | LoadedEvidenceBundle,
): Promise<BundleValidationReport>;
export const validateEvidenceBundle: typeof validateBundle;
export function queryClaims(
  bundle: LoadedEvidenceBundle,
  query?: ClaimQuery,
): PortableClaim[];
export function queryEvidence(
  bundle: LoadedEvidenceBundle,
  query?: EvidenceQuery,
): PortableEvidence[];
export function resolveSource(
  bundle: LoadedEvidenceBundle,
  sourceId: string,
): PortableSource | undefined;
export function readBlob(
  bundle: LoadedEvidenceBundle,
  blobRef: string,
): Promise<Uint8Array>;
export function renderPromptContext(
  bundle: LoadedEvidenceBundle,
  options?: PromptContextOptions,
): string;
export function validateReviewReferences(
  bundle: LoadedEvidenceBundle,
  review: PortableReviewResult,
): ReviewReferenceValidationReport;
export function buildEvidenceGraph(
  bundle: LoadedEvidenceBundle,
): EvidenceGraph;
export function loadEvidenceGraph(
  input: string | URL,
): Promise<EvidenceGraph>;
export function validateEvidenceGraph(
  input: string | URL | EvidenceGraph,
): Promise<EvidenceGraphValidationReport>;
export function queryPerspective(
  graph: EvidenceGraph,
  perspectiveId: EvidenceAtlasPerspectiveId,
  options?: EvidenceGraphQueryOptions,
): EvidenceGraphProjection & { perspective: EvidenceAtlasPerspective };
export function getNodeSubgraph(
  graph: EvidenceGraph,
  nodeId: string,
  options?: EvidenceNodeSubgraphOptions,
): EvidenceGraphProjection & { root_node_id: string };
export function traceClaimSupport(
  graph: EvidenceGraph,
  claimId: string,
  options?: EvidenceGraphQueryOptions,
): ClaimSupportTrace;
export function traceFreshnessImpact(
  graph: EvidenceGraph,
  evidenceId: string,
  options?: EvidenceGraphQueryOptions,
): FreshnessImpactTrace;
export function renderMermaid(
  graph: EvidenceGraph,
  options?: MermaidRenderOptions,
): string;
export function loadPlan(path: string | URL): Promise<EvidenceLinkedPlan>;
export function queryPlanEdits(
  plan: EvidenceLinkedPlan,
  filter?: PlanEditFilter,
): ValidatedPlanEditItem[];
export function validatePlanReferences(
  plan: EvidenceLinkedPlan,
  refs: PlanReference[] | Record<string, PlanReference>,
): PlanReferenceValidationReport;
