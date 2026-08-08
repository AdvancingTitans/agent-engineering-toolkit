import type {
  EvidenceCandidate,
  InvestigationLedger,
  InvestigationPolicy,
  InvestigationRequest,
  InvestigationResult,
  Observation,
  OptimizationCandidate,
  PortableClaim,
  PortableSource,
  RiskDiagnosis,
  RiskForecast,
  RunDiagnostics,
  RunManifest,
  RunMeta,
  RunRecord,
  SourceIdentity,
  VerifiedEvidence,
} from "@aet/protocol-types";

const digest = "0".repeat(64);

const sourceIdentity = {
  run_group_id: "run-001",
  stable_source_record_id: "native-001",
  identity_kind: "native",
  source_order_id: "0001",
  record_id: digest,
  content_hash: digest,
} satisfies SourceIdentity;

const meta = {
  schema_version: "canonical-run-record/1.0",
  record_type: "meta",
  record_id: digest,
  source_identity: sourceIdentity,
  source_type: "codex",
  working_directory: "/workspace",
} satisfies RunMeta;

const record: RunRecord = meta;

const manifest = {
  source_type: "codex",
  run_group_id: "run-001",
  generation_id: "generation-001",
  partial: false,
  base_byte_offset: 0,
  provenance: {
    normalizer_version: "1.0.0",
    schema_version: "canonical-run-record/1.0",
    adapter_name: "codex",
    adapter_version: "1.0.0",
    configuration_hash: digest,
  },
  record_count: 1,
  diagnostic_count: 0,
} satisfies RunManifest;

const diagnostics = [] satisfies RunDiagnostics;

const policy = {
  schema_version: "portable-investigation-policy/1.0",
  allowed_tools: ["run.read", "proof.inspect", "freshness.check"],
  denied_tools: [],
  budgets: {
    max_tool_calls: 2,
    max_evidence_candidates: 10,
    max_verified_evidence: 1,
    max_run_records_read: 10,
    max_blob_bytes_read: 0,
  },
  command_policy: {
    allow_execution: false,
    allowed_command_prefixes: [],
  },
  workspace_policy: {
    read_only: true,
  },
  privacy_policy: {
    redact_secrets: true,
    export_reasoning: false,
    export_raw_tool_output: false,
  },
  require_competing_hypothesis: true,
  require_disconfirming_search: true,
} satisfies InvestigationPolicy;

const request = {
  protocol_version: "1.0",
  investigation_id: "investigation-001",
  question: "What does the normalized run establish?",
  task: {
    task_id: "task-001",
    request: "Inspect the run.",
  },
  hypotheses: {
    primary: "The run contains relevant recorded behavior.",
    competing: ["The run is insufficient."],
  },
  requested_evidence: ["recorded behavior"],
  run_sources: [{
    id: "source-001",
    source_type: "codex",
    run_group_id: "run-001",
  }],
  policy,
} satisfies InvestigationRequest;

const observation = {
  id: "observation-001",
  investigation_id: request.investigation_id,
  type: "run_metadata",
  statement: "The run declares metadata.",
  source_refs: [record.record_id],
  proves: ["The metadata declaration exists."],
  does_not_prove: ["The metadata is current."],
  reliability: "recorded_behavior",
  limitations: ["Historical context only."],
} satisfies Observation;

const candidate = {
  id: "candidate-001",
  investigation_id: request.investigation_id,
  proposition: observation.statement,
  candidate_type: "command_observation",
  observation_refs: [observation.id],
  source_refs: observation.source_refs,
  verification_required: false,
  proposed_evidence_kind: "test_result",
  proposed_strength: "observed",
  status: "verified",
  verification_plan: [{
    action: "verify_against_workspace",
    purpose: "Establish current deterministic support.",
  }],
} satisfies EvidenceCandidate;

const findingId = "finding-001";

const proofSource = {
  id: "proof-source-001",
  type: "proof_receipt",
  locator: {
    path: ".aet/proof.json",
    commit: digest,
  },
  provenance: {
    source_type: "deterministic_runtime",
    schema_version: "aet-proof-receipt/v2",
  },
  integrity: {
    content_hash: digest,
  },
} satisfies PortableSource;

const verifiedEvidence = {
  extensions: {
    candidate_refs: [candidate.id],
    observation_refs: [observation.id],
  },
  id: "evidence-001",
  proposition: "The bound Proof passed and remains current.",
  kind: "test_result",
  strength: "reproduced",
  strength_definition: "The deterministic Proof was reproduced in the bound workspace.",
  source_refs: [proofSource.id],
  bindings: {
    task_id: request.task.task_id,
    commit: digest,
    command: ["python", "-m", "unittest"],
  },
  freshness: {
    status: "current",
    checked_at: "2026-07-26T00:00:00Z",
    explanation: "The Proof bindings still match the current workspace.",
    effect: "The Proof supports the current bounded finding.",
  },
  supports: [findingId],
  contradicts: [],
  limitations: ["The Proof covers only the recorded command."],
  integrity: {
    content_hash: digest,
    truncated: false,
  },
} satisfies VerifiedEvidence;

const ledger = [
  {
    id: "ledger-001",
    question: request.question,
    hypothesis_ref: "primary",
    action: "propose_candidate",
    input_refs: [observation.id],
    output_ref: candidate.id,
    observation_refs: [observation.id],
    evidence_candidate_refs: [candidate.id],
    effect: "supports_primary",
    explanation: "The Observation produced a verification candidate.",
  },
  {
    id: "ledger-002",
    question: request.question,
    hypothesis_ref: "primary",
    action: "inspect_proof",
    tool_name: "proof.inspect",
    input_refs: [proofSource.id],
    output_ref: verifiedEvidence.id,
    observation_refs: [observation.id],
    evidence_candidate_refs: [candidate.id],
    effect: "supports_primary",
    explanation: "The declared Proof verified the candidate.",
  },
  {
    id: "ledger-003",
    question: request.question,
    hypothesis_ref: "primary",
    action: "check_freshness",
    tool_name: "freshness.check",
    input_refs: [proofSource.id],
    output_ref: verifiedEvidence.id,
    observation_refs: [observation.id],
    evidence_candidate_refs: [candidate.id],
    effect: "supports_primary",
    explanation: "The Proof remains current.",
  },
] satisfies InvestigationLedger;

const result = {
  schema_version: "portable-investigation-result/1.0",
  investigation_id: request.investigation_id,
  question: request.question,
  task: request.task,
  hypotheses: request.hypotheses,
  requested_evidence: request.requested_evidence,
  run_sources: request.run_sources,
  record_sources: [{
    id: record.record_id,
    run_group_id: sourceIdentity.run_group_id,
    identity_kind: sourceIdentity.identity_kind,
    content_hash: sourceIdentity.content_hash,
    source_type: manifest.source_type,
    schema_version: record.schema_version,
  }],
  verification_sources: [proofSource],
  policy,
  status: "supported",
  observations: [observation],
  evidence_candidates: [candidate],
  verified_evidence: [verifiedEvidence],
  findings: [{
    id: findingId,
    statement: request.question,
    status: "supported",
    evidence_refs: [verifiedEvidence.id],
    counter_evidence_candidate_refs: [],
    observation_refs: [observation.id],
    limitations: verifiedEvidence.limitations,
  }],
  ledger,
  disconfirming_search: {
    performed: true,
    searched_record_refs: [record.record_id],
    counter_evidence_candidate_refs: [],
  },
  unresolved: [],
  usage: {
    run_records_read: 1,
    evidence_candidates: 1,
    verified_evidence: 1,
    tool_calls: 2,
  },
  stop: {
    reason: "question_answered",
    bounded_result: true,
    explanation: "Authorized Proof and Freshness checks answered the question.",
  },
} satisfies InvestigationResult;

const claim = {
  id: findingId,
  statement: "The bounded proposition is supported.",
  status: "supported",
  status_definition: "Supported by current reproduced evidence.",
  evidence_refs: ["evidence-001"],
  counter_evidence_refs: [],
  observation_refs: [observation.id],
  basis: {
    type: "reproduced",
    explanation: "A bounded command was reproduced.",
  },
  limitations: [],
} satisfies PortableClaim;

const optimizationCandidate = {
  id: "optimization-001",
  target: "grounding_validator",
  observedProblem: "A repeated evidence-boundary failure was validated.",
  supportingRunRefs: ["bundle-001#run-record:source-001"],
  supportingBundleRefs: ["bundle-001", "bundle-002"],
  supportingReviewRefs: [
    "bundle-001#review-conclusion:review-001",
    "bundle-002#review-conclusion:review-002",
  ],
  proposedChange: "Evaluate a stricter reference rule in isolated fixtures.",
  expectedEffect: "Reduce unsupported conclusions.",
  possibleRegression: "Reject a bounded conclusion that was previously accepted.",
  evaluationRequired: true,
} satisfies OptimizationCandidate;

const riskRef = {
  ref: "tool-result-001",
  record_id: "tool-result-001",
  source_order_id: "0002",
  source_type: "codex",
};

const riskDiagnosis = {
  schema_version: "aet-risk-diagnosis/1.0",
  evaluator_version: "1.0.0",
  created_at: "2026-08-01T00:00:00Z",
  policy_id: "policy-001",
  policy_sha256: digest,
  findings: [{
    factor: "harm_realization_capability",
    observable: "A protected action produced a verified effect.",
    status: "FAIL",
    strength: "DIRECT",
    evidence_refs: [riskRef],
    counter_evidence_refs: [],
    coverage: {
      complete: true,
      checked_surfaces: ["deploy"],
      gaps: [],
      observability_gap: false,
    },
    limitations: ["Deployment-scoped evidence only."],
    does_not_prove: ["Internal motive or general capability."],
    context_key: "run:generation:task",
    asset_ids: ["deployment"],
    monitoring_surface_ids: [],
    signal_codes: ["PROTECTED_ACTION_SUCCEEDED"],
    order_keys: ["0002"],
  }],
  pathways: [],
  interventions: [],
  diagnostics: [],
  provenance: { evaluator: "deterministic" },
} satisfies RiskDiagnosis;

const riskForecast = {
  schema_version: "aet-risk-forecast/1.0",
  created_at: "2026-08-01T00:00:00Z",
  diagnosis_sha256: digest,
  calibration_sha256: digest,
  dataset_sha256: digest,
  forecasts: [{
    pathway_id: "pathway-001",
    signature: "harm_realization_capability",
    status: "UNKNOWN",
    support: 24,
    interval: { low: null, high: null },
    baseline: { low: null, high: null },
    reason: "calibration_gate_failed",
  }],
  gate_status: "FAIL",
  limitations: ["Insufficient independent outcomes."],
  provenance: { method: "wilson_interval" },
} satisfies RiskForecast;

void diagnostics;
void result;
void verifiedEvidence;
void optimizationCandidate;
void riskDiagnosis;
void riskForecast;
