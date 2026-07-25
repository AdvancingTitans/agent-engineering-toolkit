export type Extensions = Record<string, unknown>;

export type IdentityKind =
  | "native"
  | "location"
  | "content"
  | "synthetic";

export type DiagnosticSeverity = "info" | "warning" | "error";

export type ObservationType =
  | "agent_statement"
  | "agent_tool_call"
  | "agent_tool_result"
  | "agent_reasoning"
  | "run_sequence"
  | "run_metadata";

export type ClaimStatus =
  | "supported"
  | "partially_supported"
  | "unsupported"
  | "conflicted"
  | "unknown";

export type EvidenceKind =
  | "git_fact"
  | "file_fact"
  | "command_receipt"
  | "test_result"
  | "artifact_fact"
  | "freshness_fact"
  | "authority_fact"
  | "run_observation";

export type EvidenceStrength =
  | "context_only"
  | "observed"
  | "corroborated"
  | "reproduced";

export type FreshnessStatus =
  | "current"
  | "relevant_files_changed"
  | "workspace_changed"
  | "environment_changed"
  | "unknown";

export interface PortableEvidenceBundleManifest {
  extensions?: Record<string, unknown>;
  protocol: {
    name: "portable-evidence-bundle";
    version: "1.0";
    schema_uri: string;
  };
  bundle: {
    id: string;
    created_at: string;
    content_hash: string;
    parent_bundle_id?: string;
  };
  task: {
    task_id: string;
    request: string;
    repository?: string;
    workspace_id?: string;
    base_ref?: string;
    head_ref?: string;
  };
  producer: {
    name: "agent-engineering-toolkit";
    version: string;
  };
  investigation: {
    investigation_id: string;
    investigation_type:
      | "scope"
      | "verification"
      | "freshness"
      | "security"
      | "authorization"
      | "general";
    question: string;
    scope: string[];
    limitations: string[];
    completed: boolean;
  };
  contents: {
    index: string;
    claims: string;
    evidence: string;
    observations: string;
    sources: string;
    diagnostics: string;
    conflicts: string;
    ledger: string;
    policy: string;
    consumer_guide: string;
    report: string;
  };
  integrity: {
    algorithm: "sha256";
    file_hashes: Record<string, string>;
  };
}

export interface PortableClaim {
  extensions?: Record<string, unknown>;
  id: string;
  statement: string;
  status: ClaimStatus;
  status_definition: string;
  evidence_refs: string[];
  counter_evidence_refs: string[];
  observation_refs: string[];
  basis: {
    type:
      | "deterministic"
      | "reproduced"
      | "corroborated"
      | "observational"
      | "mixed";
    explanation: string;
  };
  limitations: string[];
  smallest_next_action?: string;
}

export interface PortableEvidence {
  extensions?: Record<string, unknown>;
  id: string;
  proposition: string;
  kind: EvidenceKind;
  strength: EvidenceStrength;
  strength_definition: string;
  source_refs: string[];
  bindings: {
    task_id?: string;
    workspace_id?: string;
    repository?: string;
    commit?: string;
    paths?: string[];
    command?: string[];
    environment_hash?: string;
  };
  freshness: {
    status: FreshnessStatus;
    checked_at?: string;
    explanation: string;
    effect: string;
    recommended_action?: string;
  };
  supports: string[];
  contradicts: string[];
  limitations: string[];
  integrity: {
    content_hash: string;
    blob_ref?: string;
    truncated: boolean;
    original_bytes?: number;
  };
}

export interface PortableObservation {
  extensions?: Record<string, unknown>;
  id: string;
  type:
    | "agent_statement"
    | "agent_tool_call"
    | "agent_tool_result"
    | "agent_reasoning"
    | "run_sequence"
    | "run_metadata";
  statement: string;
  source_refs: string[];
  proves: string[];
  does_not_prove: string[];
  limitations: string[];
}

export interface PortableSource {
  extensions?: Record<string, unknown>;
  id: string;
  type:
    | "run_record"
    | "git"
    | "file"
    | "command"
    | "artifact"
    | "user_instruction"
    | "proof_receipt";
  locator: {
    run_group_id?: string;
    record_id?: string;
    identity_kind?: "native" | "location" | "content" | "synthetic";
    repository?: string;
    commit?: string;
    path?: string;
    line_start?: number;
    line_end?: number;
    blob_ref?: string;
  };
  provenance: {
    source_type?: string;
    normalizer_version?: string;
    schema_version?: number | string;
    configuration_hash?: string;
  };
  integrity: {
    content_hash?: string;
  };
}

export interface PortableReviewConclusion {
  id: string;
  statement: string;
  disposition:
    | "accept"
    | "request_change"
    | "request_investigation"
    | "unknown";
  claim_refs: string[];
  evidence_refs: string[];
  counter_evidence_refs: string[];
  reasoning_summary: string;
  limitations: string[];
  next_action?: string;
}

export interface PortableReviewResult {
  extensions?: Record<string, unknown>;
  protocol: {
    name: "portable-review-result";
    version: "1.0";
  };
  bundle_id: string;
  conclusions: PortableReviewConclusion[];
  unresolved_questions: string[];
}

// Canonical Run Record v1

export type RunRecordType =
  | "meta"
  | "user"
  | "assistant"
  | "reasoning"
  | "tool_call"
  | "tool_result";

export interface SourceIdentity {
  run_group_id: string;
  stable_source_record_id: string;
  identity_kind: IdentityKind;
  source_order_id: string;
  record_id: string;
  content_hash: string;
}

export interface RunRecordBase {
  schema_version: "canonical-run-record/1.0";
  record_type: RunRecordType;
  record_id: string;
  timestamp?: string;
  source_identity: SourceIdentity;
}

export interface RunMeta extends RunRecordBase {
  record_type: "meta";
  source_type: string;
  working_directory?: string;
  git_branch?: string;
  model?: string;
}

export interface RunUserRecord extends RunRecordBase {
  record_type: "user";
  content: string;
}

export interface RunAssistantRecord extends RunRecordBase {
  record_type: "assistant";
  content: string;
}

export interface RunReasoningRecord extends RunRecordBase {
  record_type: "reasoning";
  content: string;
  public_export_allowed: false;
}

export interface RunToolCallRecord extends RunRecordBase {
  record_type: "tool_call";
  tool_call_id: string;
  tool_name: string;
  arguments_json: string;
}

export interface RunToolResultRecord extends RunRecordBase {
  record_type: "tool_result";
  tool_call_id: string;
  result_json?: string;
  result_text?: string;
  linked_tool_call_record_id: string | null;
}

export type RunRecord =
  | RunMeta
  | RunUserRecord
  | RunAssistantRecord
  | RunReasoningRecord
  | RunToolCallRecord
  | RunToolResultRecord;

export type CanonicalRunRecord = RunRecord;
export type RunMetaRecord = RunMeta;

export type RunDiagnosticCode =
  | "malformed_record"
  | "unsupported_record"
  | "missing_run_group"
  | "run_group_conflict"
  | "source_record_conflict"
  | "orphan_tool_result"
  | "duplicate_tool_result"
  | "missing_tool_result"
  | "invalid_tool_arguments"
  | "invalid_timestamp"
  | "synthesized_timestamp"
  | "truncated_tool_output"
  | "repaired_record"
  | "content_identity_fallback"
  | "partial_run";

export interface RunDiagnosticInputLocation {
  line?: number;
  byte_offset?: number;
  record_index?: number;
}

export interface RunDiagnostic {
  code: RunDiagnosticCode;
  severity: DiagnosticSeverity;
  message: string;
  input_location?: RunDiagnosticInputLocation;
  count?: number;
}

export type RunDiagnostics = RunDiagnostic[];
export type RunNormalizationDiagnostic = RunDiagnostic;

export type RunSourceType = "codex" | "claude-code";
export type RunAdapterName = "codex" | "claude_code";

export interface RunNormalizationProvenance {
  normalizer_version: string;
  schema_version: "canonical-run-record/1.0";
  adapter_name: RunAdapterName;
  adapter_version: string;
  configuration_hash: string;
}

export interface RunManifest {
  source_type: RunSourceType;
  run_group_id: string;
  generation_id: string;
  partial: boolean;
  base_byte_offset: number;
  provenance: RunNormalizationProvenance;
  record_count: number;
  diagnostic_count: number;
}

export type RunNormalizationManifest = RunManifest;

export interface NormalizedRun {
  schema_version: "agent-run-normalization/1.0";
  manifest: RunManifest;
  records: RunRecord[];
  diagnostics: RunDiagnostics;
}

// Portable Investigation v1

export interface InvestigationTask {
  task_id: string;
  request: string;
  repository?: string;
  workspace_id?: string;
  base_ref?: string;
  head_ref?: string;
}

export interface InvestigationHypotheses {
  primary: string;
  competing: string[];
}

export interface InvestigationRunSource {
  id: string;
  source_type: string;
  run_group_id: string;
  extensions?: Extensions;
}

export interface InvestigationBudgets {
  max_tool_calls: number;
  max_evidence_candidates: number;
  max_verified_evidence: number;
  max_run_records_read: number;
  max_blob_bytes_read: number;
}

export interface InvestigationCommandPolicy {
  allow_execution: boolean;
  allowed_command_prefixes: string[][];
}

export interface InvestigationWorkspacePolicy {
  read_only: boolean;
  allowed_paths?: string[];
  denied_paths?: string[];
}

export interface InvestigationPrivacyPolicy {
  redact_secrets: boolean;
  export_reasoning: boolean;
  export_raw_tool_output: boolean;
}

export interface InvestigationPolicy {
  extensions?: Extensions;
  schema_version: "portable-investigation-policy/1.0";
  allowed_tools: string[];
  denied_tools: string[];
  budgets: InvestigationBudgets;
  command_policy: InvestigationCommandPolicy;
  workspace_policy: InvestigationWorkspacePolicy;
  privacy_policy: InvestigationPrivacyPolicy;
  require_competing_hypothesis: boolean;
  require_disconfirming_search: boolean;
}

export type PortableInvestigationPolicy = InvestigationPolicy;

export interface InvestigationRequest {
  protocol_version: "1.0";
  investigation_id: string;
  question: string;
  task: InvestigationTask;
  hypotheses: InvestigationHypotheses;
  requested_evidence: string[];
  run_sources: InvestigationRunSource[];
  policy: InvestigationPolicy;
}

export type PortableInvestigationRequest = InvestigationRequest;

export type ObservationReliability =
  | "self_report"
  | "recorded_behavior"
  | "recorded_tool_output";

export interface Observation {
  id: string;
  investigation_id: string;
  type: ObservationType;
  statement: string;
  source_refs: string[];
  proves: string[];
  does_not_prove: string[];
  reliability: ObservationReliability;
  limitations: string[];
}

export type InvestigationObservation = Observation;

export type EvidenceCandidateType =
  | "agent_claim"
  | "tool_observation"
  | "code_observation"
  | "command_observation"
  | "authorization_observation"
  | "counter_evidence";

export interface EvidenceVerificationStep {
  action: string;
  purpose: string;
}

export interface EvidenceCandidateBase {
  id: string;
  investigation_id: string;
  proposition: string;
  candidate_type: EvidenceCandidateType;
  observation_refs: string[];
  source_refs: string[];
  proposed_evidence_kind: EvidenceKind;
  proposed_strength: "context_only" | "observed";
  verification_plan: EvidenceVerificationStep[];
}

export type EvidenceCandidate = EvidenceCandidateBase & (
  | {
    verification_required: true;
    status: "unverified";
  }
  | {
    verification_required: false;
    status: "verified" | "rejected" | "conflicted";
  }
);

export type VerifiedEvidence = PortableEvidence;
export type VerificationSource = PortableSource;

export type InvestigationHypothesisRef =
  | "primary"
  | `competing:${string}`;

export type InvestigationLedgerAction =
  | "read_run_record"
  | "record_observation"
  | "propose_candidate"
  | "inspect_proof"
  | "check_freshness";

export type HypothesisEffect =
  | "supports_primary"
  | "weakens_primary"
  | "supports_competing"
  | "weakens_competing"
  | "no_change";

export interface InvestigationLedgerEntry {
  id: string;
  question: string;
  hypothesis_ref: InvestigationHypothesisRef;
  action: InvestigationLedgerAction;
  tool_name?: string;
  input_refs: string[];
  output_ref?: string;
  observation_refs: string[];
  evidence_candidate_refs: string[];
  effect: HypothesisEffect;
  explanation: string;
}

export type InvestigationLedger = InvestigationLedgerEntry[];
export type PortableInvestigationLedger = InvestigationLedger;

export interface InvestigationRecordSource {
  id: string;
  run_group_id: string;
  identity_kind: IdentityKind;
  content_hash: string;
  source_type: string;
  schema_version: string;
}

export interface InvestigationFinding {
  id: string;
  statement: string;
  status: ClaimStatus;
  evidence_refs: string[];
  counter_evidence_candidate_refs: string[];
  observation_refs: string[];
  limitations: string[];
}

export interface InvestigationDisconfirmingSearch {
  performed: boolean;
  searched_record_refs: string[];
  counter_evidence_candidate_refs: string[];
}

export interface InvestigationUsage {
  run_records_read: number;
  evidence_candidates: number;
  verified_evidence: number;
  tool_calls: number;
}

export type InvestigationStopReason =
  | "budget_exhausted"
  | "tool_unavailable"
  | "authorization_required"
  | "question_answered"
  | "unknown";

export interface InvestigationStop {
  reason: InvestigationStopReason;
  bounded_result: true;
  explanation: string;
}

export interface InvestigationResult {
  schema_version: "portable-investigation-result/1.0";
  investigation_id: string;
  question: string;
  task: InvestigationTask;
  hypotheses: InvestigationHypotheses;
  requested_evidence: string[];
  run_sources: InvestigationRunSource[];
  record_sources: InvestigationRecordSource[];
  verification_sources: PortableSource[];
  policy: InvestigationPolicy;
  status: ClaimStatus;
  observations: Observation[];
  evidence_candidates: EvidenceCandidate[];
  verified_evidence: VerifiedEvidence[];
  findings: InvestigationFinding[];
  ledger: InvestigationLedger;
  disconfirming_search: InvestigationDisconfirmingSearch;
  unresolved: string[];
  usage: InvestigationUsage;
  stop: InvestigationStop;
}

export type PortableInvestigationResult = InvestigationResult;

// Evidence-backed optimization entry

export type OptimizationTarget =
  | "source_adapter"
  | "observation_extractor"
  | "investigation_policy"
  | "tool_selection"
  | "bundle_selector"
  | "consumer_guide"
  | "grounding_validator";

export interface OptimizationCandidate {
  id: string;
  target: OptimizationTarget;
  observedProblem: string;
  supportingRunRefs: string[];
  supportingBundleRefs: string[];
  supportingReviewRefs: string[];
  proposedChange: string;
  expectedEffect: string;
  possibleRegression: string;
  evaluationRequired: true;
}

// Remaining Portable Evidence Bundle v1 archive and index records

export interface PortableDiagnostic {
  extensions?: Extensions;
  code: string;
  severity: DiagnosticSeverity;
  effect: string;
  affected_observation_refs: string[];
  affected_evidence_refs: string[];
  recommended_action?: string;
}

export type PortableLedgerAction =
  | "read_run_record"
  | "read_file"
  | "inspect_git"
  | "inspect_proof"
  | "check_freshness"
  | "execute_authorized_command"
  | "record_observation"
  | "propose_candidate";

export interface PortableLedgerEntry {
  id: string;
  timestamp: string;
  question: string;
  hypothesis_ref?: InvestigationHypothesisRef;
  action: PortableLedgerAction;
  tool_name?: string;
  input_ref?: string;
  output_ref?: string;
  observation_refs: string[];
  evidence_candidate_refs: string[];
  effect: HypothesisEffect;
  explanation: string;
}

export interface PortableEvidenceConflict {
  extensions?: Extensions;
  id: string;
  proposition: string;
  evidence_refs: string[];
  conflict_type:
    | "content_conflict"
    | "workspace_conflict"
    | "timestamp_conflict"
    | "authority_conflict"
    | "interpretation_conflict";
  resolution_status: "resolved" | "unresolved";
  explanation: string;
}

export interface PortableEvidenceBundleIndex {
  extensions?: Extensions;
  schema_version: "portable-evidence-bundle-index/1.0";
  bundle_id: string;
  question: string;
  claim_refs: string[];
  evidence_refs: string[];
  observation_refs: string[];
  reading_order: string[];
  excluded: {
    count: number;
    reason: string;
  };
  archive_available: boolean;
  consumer_guidance: {
    must: string[];
    must_not: string[];
  };
}
