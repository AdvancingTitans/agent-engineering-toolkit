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
