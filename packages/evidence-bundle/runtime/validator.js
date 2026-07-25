import { manifestContentHash, sha256 } from "./canonical.js";
import { listRegularBundleFiles, loadBundleSnapshot, readRegularBundleFile } from "./loader.js";
import { EvidenceBundleError } from "./types.js";
import { assertVerifiedBundle } from "./trusted.js";
const CLAIM_STATUSES = new Set([
    "supported",
    "partially_supported",
    "unsupported",
    "conflicted",
    "unknown"
]);
const BASIS_TYPES = new Set([
    "deterministic",
    "reproduced",
    "corroborated",
    "observational",
    "mixed"
]);
const EVIDENCE_KINDS = new Set([
    "git_fact",
    "file_fact",
    "command_receipt",
    "test_result",
    "artifact_fact",
    "freshness_fact",
    "authority_fact",
    "run_observation"
]);
const STRENGTHS = new Set([
    "context_only",
    "observed",
    "corroborated",
    "reproduced"
]);
const FRESHNESS = new Set([
    "current",
    "relevant_files_changed",
    "workspace_changed",
    "environment_changed",
    "unknown"
]);
const OBSERVATION_TYPES = new Set([
    "agent_statement",
    "agent_tool_call",
    "agent_tool_result",
    "agent_reasoning",
    "run_sequence",
    "run_metadata"
]);
const SOURCE_TYPES = new Set([
    "run_record",
    "git",
    "file",
    "command",
    "artifact",
    "user_instruction",
    "proof_receipt"
]);
const IDENTITY_KINDS = new Set([
    "native",
    "location",
    "content",
    "synthetic"
]);
const INVESTIGATION_TYPES = new Set([
    "scope",
    "verification",
    "freshness",
    "security",
    "authorization",
    "general"
]);
const CONFLICT_TYPES = new Set([
    "content_conflict",
    "workspace_conflict",
    "timestamp_conflict",
    "authority_conflict",
    "interpretation_conflict"
]);
const RESOLUTION_STATUSES = new Set([
    "resolved",
    "unresolved"
]);
const DIAGNOSTIC_SEVERITIES = new Set([
    "info",
    "warning",
    "error"
]);
const LEDGER_ACTIONS = new Set([
    "read_run_record",
    "read_file",
    "inspect_git",
    "inspect_proof",
    "check_freshness",
    "execute_authorized_command",
    "record_observation",
    "propose_candidate"
]);
const HYPOTHESIS_EFFECTS = new Set([
    "supports_primary",
    "weakens_primary",
    "supports_competing",
    "weakens_competing",
    "no_change"
]);
export async function validateBundle(input) {
    if (isLoadedBundle(input)) {
        assertVerifiedBundle(input);
    }
    const bundle = await loadBundleSnapshot(isLoadedBundle(input) ? input.root : input);
    return validateLoadedBundleSnapshot(bundle);
}
export async function validateLoadedBundleSnapshot(bundle) {
    const manifest = bundle.manifest;
    if (!INVESTIGATION_TYPES.has(manifest.investigation.investigation_type)) {
        unsupported("manifest.investigation.investigation_type", manifest.investigation.investigation_type);
    }
    if (manifest.integrity.algorithm !== "sha256") {
        unsupported("manifest.integrity.algorithm", manifest.integrity.algorithm);
    }
    if (manifest.bundle.content_hash !== manifestContentHash(manifest)) {
        throw new EvidenceBundleError("integrity_error", "Manifest content hash does not bind the manifest");
    }
    const hashes = manifest.integrity.file_hashes;
    if (!isObject(hashes)) {
        invalid("Manifest integrity.file_hashes must be an object");
    }
    const contentPaths = Object.values(manifest.contents);
    if (new Set(contentPaths).size !== contentPaths.length) {
        invalid("Manifest content paths must be unique");
    }
    for (const relative of contentPaths){
        if (!(relative in hashes)) {
            throw new EvidenceBundleError("integrity_error", `Manifest does not hash required content: ${relative}`);
        }
    }
    const actualFiles = (await listRegularBundleFiles(bundle.root)).filter((path)=>path !== "manifest.json");
    if (!sameSet(new Set(actualFiles), new Set(Object.keys(hashes)))) {
        throw new EvidenceBundleError("integrity_error", "Manifest file hashes must enumerate every non-manifest regular file");
    }
    const fileBytes = new Map();
    for (const [relative, expected] of Object.entries(hashes)){
        if (!/^[0-9a-f]{64}$/u.test(expected)) {
            invalid(`Invalid sha256 for Bundle file: ${relative}`);
        }
        const raw = await readRegularBundleFile(bundle.root, relative);
        fileBytes.set(relative, raw);
        if (sha256(raw) !== expected) {
            throw new EvidenceBundleError("integrity_error", `Bundle file hash mismatch: ${relative}`);
        }
        if (relative.startsWith("blobs/sha256-") && relative.slice("blobs/sha256-".length) !== expected) {
            throw new EvidenceBundleError("integrity_error", `Blob content address mismatch: ${relative}`);
        }
    }
    const claims = uniqueById(bundle.claims, "Claim");
    const evidence = uniqueById(bundle.evidence, "Evidence");
    const observations = uniqueById(bundle.observations, "Observation");
    const sources = uniqueById(bundle.sources, "Source");
    const conflicts = uniqueById(bundle.conflicts, "Conflict");
    validateClaims(bundle.claims);
    validateEvidence(bundle.evidence, fileBytes);
    validateObservations(bundle.observations);
    validateSources(bundle.sources, fileBytes);
    validateArchiveEnums(bundle);
    validateReferences(bundle, claims, evidence, observations, sources, conflicts);
    validatePolicy(bundle);
    validateGrounding(bundle, evidence, sources);
    validateIndex(bundle, claims, evidence, observations);
    return {
        report_kind: "portable_evidence_bundle_validation",
        status: "PASS",
        bundle_id: manifest.bundle.id,
        verified_file_count: Object.keys(hashes).length,
        claim_count: bundle.claims.length,
        evidence_count: bundle.evidence.length,
        observation_count: bundle.observations.length
    };
}
function validateArchiveEnums(bundle) {
    for (const conflict of bundle.conflicts){
        enumValue(conflict.conflict_type, CONFLICT_TYPES, `Conflict ${String(conflict.id)} type`);
        enumValue(conflict.resolution_status, RESOLUTION_STATUSES, `Conflict ${String(conflict.id)} resolution_status`);
        stringArray(conflict.evidence_refs, `Conflict ${String(conflict.id)} Evidence`, true);
        if (conflict.evidence_refs.length < 2) {
            invalid(`Conflict ${String(conflict.id)} requires at least two Evidence refs`);
        }
    }
    for (const diagnostic of bundle.diagnostics){
        enumValue(diagnostic.severity, DIAGNOSTIC_SEVERITIES, `Diagnostic ${String(diagnostic.code)} severity`);
    }
    for (const entry of bundle.ledger){
        enumValue(entry.action, LEDGER_ACTIONS, `Ledger ${String(entry.id)} action`);
        enumValue(entry.effect, HYPOTHESIS_EFFECTS, `Ledger ${String(entry.id)} effect`);
    }
}
export const validateEvidenceBundle = validateBundle;
function validateClaims(values) {
    for (const claim of values){
        enumValue(claim.status, CLAIM_STATUSES, `Claim ${claim.id} status`);
        enumValue(claim.basis?.type, BASIS_TYPES, `Claim ${claim.id} basis`);
        stringArray(claim.evidence_refs, `Claim ${claim.id} Evidence`);
        stringArray(claim.counter_evidence_refs, `Claim ${claim.id} counter-evidence`);
        stringArray(claim.observation_refs, `Claim ${claim.id} Observation`);
    }
}
function validateEvidence(values, fileBytes) {
    for (const item of values){
        enumValue(item.kind, EVIDENCE_KINDS, `Evidence ${item.id} kind`);
        enumValue(item.strength, STRENGTHS, `Evidence ${item.id} strength`);
        enumValue(item.freshness?.status, FRESHNESS, `Evidence ${item.id} freshness`);
        stringArray(item.source_refs, `Evidence ${item.id} Source`, true);
        stringArray(item.supports, `Evidence ${item.id} supports`);
        stringArray(item.contradicts, `Evidence ${item.id} contradicts`);
        if (typeof item.integrity?.content_hash !== "string" || !/^[0-9a-f]{64}$/u.test(item.integrity.content_hash)) {
            invalid(`Evidence ${item.id} has an invalid content hash`);
        }
        const blobRef = item.integrity.blob_ref;
        if (blobRef !== undefined) {
            const raw = fileBytes.get(blobRef);
            if (raw === undefined || item.integrity.content_hash !== sha256(raw) || item.integrity.original_bytes !== undefined && item.integrity.original_bytes !== raw.byteLength) {
                throw new EvidenceBundleError("integrity_error", `Evidence ${item.id} Blob binding is invalid`);
            }
        }
        if (item.integrity.truncated && (blobRef === undefined || item.integrity.original_bytes === undefined)) {
            invalid(`Truncated Evidence ${item.id} requires a complete Blob binding`);
        }
    }
}
function validateObservations(values) {
    for (const item of values){
        enumValue(item.type, OBSERVATION_TYPES, `Observation ${item.id} type`);
        stringArray(item.source_refs, `Observation ${item.id} Source`, true);
        stringArray(item.proves, `Observation ${item.id} proves`, true);
        stringArray(item.does_not_prove, `Observation ${item.id} does_not_prove`, true);
    }
}
function validateSources(values, fileBytes) {
    for (const source of values){
        enumValue(source.type, SOURCE_TYPES, `Source ${source.id} type`);
        if (source.locator.identity_kind !== undefined) {
            enumValue(source.locator.identity_kind, IDENTITY_KINDS, `Source ${source.id} identity_kind`);
        }
        const blobRef = source.locator.blob_ref;
        if (blobRef !== undefined) {
            const raw = fileBytes.get(blobRef);
            if (raw === undefined || source.integrity.content_hash !== sha256(raw)) {
                throw new EvidenceBundleError("integrity_error", `Source ${source.id} Blob binding is invalid`);
            }
        }
    }
}
function validateReferences(bundle, claims, evidence, observations, sources, conflicts) {
    for (const claim of bundle.claims){
        knownReferences(claim.evidence_refs, evidence, `Claim ${claim.id} Evidence`);
        knownReferences(claim.counter_evidence_refs, evidence, `Claim ${claim.id} counter-evidence`);
        knownReferences(claim.observation_refs, observations, `Claim ${claim.id} Observation`);
        const actualSupport = new Set(bundle.evidence.filter((item)=>item.supports.includes(claim.id)).map((item)=>item.id));
        const actualCounter = new Set(bundle.evidence.filter((item)=>item.contradicts.includes(claim.id)).map((item)=>item.id));
        if (!sameSet(new Set(claim.evidence_refs), actualSupport) || !sameSet(new Set(claim.counter_evidence_refs), actualCounter)) {
            throw new EvidenceBundleError("reference_error", `Claim ${claim.id} Evidence links are not bidirectionally complete`);
        }
        if (claim.status === "conflicted") {
            if (claim.counter_evidence_refs.length === 0) {
                throw new EvidenceBundleError("counter_evidence_error", `Conflicted Claim ${claim.id} requires counter-evidence`);
            }
            const required = new Set([
                ...claim.evidence_refs,
                ...claim.counter_evidence_refs
            ]);
            const hasConflict = [
                ...conflicts.values()
            ].some((conflict)=>{
                const refs = stringArray(conflict.evidence_refs, "Conflict evidence_refs", true);
                return conflict.resolution_status === "unresolved" && [
                    ...required
                ].every((reference)=>refs.includes(reference));
            });
            if (!hasConflict) {
                throw new EvidenceBundleError("counter_evidence_error", `Conflicted Claim ${claim.id} requires an unresolved Conflict record`);
            }
        }
    }
    for (const item of bundle.evidence){
        knownReferences(item.source_refs, sources, `Evidence ${item.id} Source`);
        knownReferences(item.supports, claims, `Evidence ${item.id} supported Claim`);
        knownReferences(item.contradicts, claims, `Evidence ${item.id} contradicted Claim`);
    }
    for (const item of bundle.observations){
        knownReferences(item.source_refs, sources, `Observation ${item.id} Source`);
    }
    for (const conflict of bundle.conflicts){
        knownReferences(stringArray(conflict.evidence_refs, `Conflict ${conflict.id} Evidence`, true), evidence, `Conflict ${conflict.id} Evidence`);
    }
    for (const diagnostic of bundle.diagnostics){
        knownReferences(stringArray(diagnostic.affected_observation_refs, "Diagnostic Observation"), observations, "Diagnostic Observation");
        knownReferences(stringArray(diagnostic.affected_evidence_refs, "Diagnostic Evidence"), evidence, "Diagnostic Evidence");
    }
    const knownOutputs = new Set([
        ...claims.keys(),
        ...evidence.keys(),
        ...observations.keys(),
        ...sources.keys()
    ]);
    for (const entry of bundle.ledger){
        knownReferences(stringArray(entry.observation_refs, "Ledger Observation"), observations, "Ledger Observation");
        if (typeof entry.input_ref === "string" && !sources.has(entry.input_ref)) {
            throw new EvidenceBundleError("reference_error", `Unknown Ledger input_ref: ${entry.input_ref}`);
        }
        if (typeof entry.output_ref === "string" && !knownOutputs.has(entry.output_ref)) {
            throw new EvidenceBundleError("reference_error", `Unknown Ledger output_ref: ${entry.output_ref}`);
        }
    }
}
function validatePolicy(bundle) {
    const policy = bundle.policy;
    if (policy.schema_version !== "portable-investigation-policy/1.0") {
        unsupported("policy.schema_version", policy.schema_version);
    }
    const privacy = policy.privacy_policy;
    if (!isObject(privacy) || typeof privacy.redact_secrets !== "boolean" || typeof privacy.export_reasoning !== "boolean" || typeof privacy.export_raw_tool_output !== "boolean") {
        invalid("Policy privacy_policy must contain three booleans");
    }
    if (!privacy.export_reasoning && bundle.observations.some((item)=>item.type === "agent_reasoning")) {
        throw new EvidenceBundleError("privacy_error", "Policy forbids exported Agent reasoning");
    }
    if (!privacy.export_raw_tool_output) {
        const exposed = bundle.evidence.some((item)=>[
                "command_receipt",
                "test_result"
            ].includes(item.kind) && item.integrity.blob_ref !== undefined);
        if (exposed) {
            throw new EvidenceBundleError("privacy_error", "Policy forbids exported raw command output Blobs");
        }
    }
    const workspace = policy.workspace_policy;
    if (!isObject(workspace) || typeof workspace.read_only !== "boolean") {
        invalid("Policy workspace_policy.read_only must be a boolean");
    }
}
function validateGrounding(bundle, evidence, sources) {
    const rank = new Map([
        [
            "context_only",
            0
        ],
        [
            "observed",
            1
        ],
        [
            "corroborated",
            2
        ],
        [
            "reproduced",
            3
        ]
    ]);
    for (const item of bundle.evidence){
        if (item.kind === "run_observation" && (rank.get(item.strength) ?? 99) > 1) {
            throw new EvidenceBundleError("grounding_error", `Run Observation ${item.id} cannot exceed observed strength`);
        }
        if (item.strength === "reproduced") {
            const sourceTypes = item.source_refs.map((reference)=>sources.get(reference)?.type);
            if (![
                "command_receipt",
                "test_result"
            ].includes(item.kind) || !sourceTypes.includes("proof_receipt") || !Array.isArray(item.bindings.command) || item.bindings.command.length === 0) {
                throw new EvidenceBundleError("grounding_error", `Reproduced Evidence ${item.id} requires a Proof Receipt and command`);
            }
        }
    }
    for (const claim of bundle.claims){
        const supporting = claim.evidence_refs.map((reference)=>evidence.get(reference)).filter((item)=>item !== undefined);
        const currentStrong = supporting.filter((item)=>item.freshness.status === "current" && (rank.get(item.strength) ?? -1) >= 2);
        if (claim.status === "supported" && currentStrong.length === 0) {
            throw new EvidenceBundleError("grounding_error", `Supported Claim ${claim.id} requires current strong Evidence`);
        }
        if (claim.basis.type === "reproduced" && !currentStrong.some((item)=>item.strength === "reproduced")) {
            throw new EvidenceBundleError("grounding_error", `Reproduced Claim ${claim.id} requires reproduced Evidence`);
        }
    }
}
function validateIndex(bundle, claims, evidence, observations) {
    const index = bundle.index;
    if (index.schema_version !== "portable-evidence-bundle-index/1.0" || index.bundle_id !== bundle.manifest.bundle.id || index.question !== bundle.manifest.investigation.question) {
        throw new EvidenceBundleError("reference_error", "Index identity does not match the Bundle manifest");
    }
    const claimRefs = stringArray(index.claim_refs, "index.claim_refs");
    const evidenceRefs = stringArray(index.evidence_refs, "index.evidence_refs");
    const observationRefs = stringArray(index.observation_refs, "index.observation_refs");
    knownReferences(claimRefs, claims, "Index Claim");
    knownReferences(evidenceRefs, evidence, "Index Evidence");
    knownReferences(observationRefs, observations, "Index Observation");
    if (!sameSet(new Set(claimRefs), new Set(claims.keys())) || !sameSet(new Set(evidenceRefs), new Set(evidence.keys())) || !sameSet(new Set(observationRefs), new Set(observations.keys()))) {
        throw new EvidenceBundleError("reference_error", "Index must enumerate the complete Core record sets");
    }
}
function uniqueById(values, label) {
    if (!Array.isArray(values)) {
        invalid(`${label} records must be an array`);
    }
    const result = new Map();
    for (const value of values){
        if (!isObject(value) || typeof value.id !== "string" || value.id.length === 0) {
            invalid(`${label} requires a non-empty id`);
        }
        if (result.has(value.id)) {
            throw new EvidenceBundleError("reference_error", `Duplicate ${label} id: ${value.id}`);
        }
        result.set(value.id, value);
    }
    return result;
}
function knownReferences(references, records, label) {
    for (const reference of stringArray(references, label)){
        if (!records.has(reference)) {
            throw new EvidenceBundleError("reference_error", `Unknown ${label} id: ${reference}`);
        }
    }
}
function stringArray(value, label, nonempty = false) {
    if (!Array.isArray(value) || value.some((item)=>typeof item !== "string" || item.length === 0) || new Set(value).size !== value.length || nonempty && value.length === 0) {
        invalid(`${label} must contain unique non-empty strings`);
    }
    return value;
}
function enumValue(value, allowed, label) {
    if (typeof value !== "string" || !allowed.has(value)) {
        unsupported(label, value);
    }
}
function unsupported(label, value) {
    throw new EvidenceBundleError("unsupported_semantics", `${label} has unsupported value: ${String(value)}`);
}
function invalid(message) {
    throw new EvidenceBundleError("invalid_bundle", message);
}
function sameSet(left, right) {
    return left.size === right.size && [
        ...left
    ].every((item)=>right.has(item));
}
function isLoadedBundle(value) {
    return isObject(value) && typeof value.root === "string";
}
function isObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
