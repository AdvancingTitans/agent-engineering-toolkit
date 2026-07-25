import { EvidenceBundleError } from "./types.js";
import { assertVerifiedBundle } from "./trusted.js";
const DISPOSITIONS = new Set([
    "accept",
    "request_change",
    "request_investigation",
    "unknown"
]);
export function validateReviewReferences(bundle, review) {
    assertVerifiedBundle(bundle);
    if (!isObject(review) || !isObject(review.protocol) || review.protocol.name !== "portable-review-result" || review.protocol.version !== "1.0") {
        throw new EvidenceBundleError("invalid_review", "Review protocol must be portable-review-result/1.0");
    }
    if (review.bundle_id !== bundle.manifest.bundle.id) {
        throw new EvidenceBundleError("reference_error", "Review bundle_id does not match the Bundle");
    }
    if (!Array.isArray(review.conclusions)) {
        throw new EvidenceBundleError("invalid_review", "Review conclusions must be an array");
    }
    const claims = new Map(bundle.claims.map((claim)=>[
            claim.id,
            claim
        ]));
    const evidence = new Map(bundle.evidence.map((item)=>[
            item.id,
            item
        ]));
    const conclusionIds = new Set();
    for (const conclusion of review.conclusions){
        validateConclusion(conclusion, claims, evidence);
        if (conclusionIds.has(conclusion.id)) {
            throw new EvidenceBundleError("reference_error", `Duplicate review conclusion id: ${conclusion.id}`);
        }
        conclusionIds.add(conclusion.id);
    }
    return {
        report_kind: "portable_review_reference_validation",
        status: "PASS",
        bundle_id: review.bundle_id,
        conclusion_count: review.conclusions.length,
        validated_conclusion_refs: review.conclusions.map((item)=>item.id)
    };
}
function validateConclusion(conclusion, claims, evidence) {
    if (!isObject(conclusion) || typeof conclusion.id !== "string" || conclusion.id.length === 0 || !Array.isArray(conclusion.claim_refs) || conclusion.claim_refs.length === 0) {
        throw new EvidenceBundleError("invalid_review", "Every review conclusion requires an id and at least one Claim reference");
    }
    if (!DISPOSITIONS.has(conclusion.disposition)) {
        throw new EvidenceBundleError("invalid_review", `Unsupported review disposition: ${String(conclusion.disposition)}`);
    }
    const referencedClaims = conclusion.claim_refs.map((reference)=>{
        const claim = claims.get(reference);
        if (claim === undefined) {
            throw new EvidenceBundleError("reference_error", `Unknown review Claim id: ${reference}`);
        }
        return claim;
    });
    knownEvidence(conclusion.evidence_refs, evidence, "review Evidence");
    knownEvidence(conclusion.counter_evidence_refs, evidence, "review counter-evidence");
    const allowedEvidence = new Set(referencedClaims.flatMap((claim)=>claim.evidence_refs));
    const requiredCounter = new Set(referencedClaims.flatMap((claim)=>claim.counter_evidence_refs));
    if (conclusion.evidence_refs.some((reference)=>!allowedEvidence.has(reference))) {
        throw new EvidenceBundleError("grounding_error", "Review cites Evidence that does not support its referenced Claims");
    }
    if (!sameSet(new Set(conclusion.counter_evidence_refs), requiredCounter)) {
        throw new EvidenceBundleError("counter_evidence_error", "Review must retain all counter-evidence from its referenced Claims");
    }
    if ([
        "accept",
        "request_change"
    ].includes(conclusion.disposition)) {
        for (const claim of referencedClaims){
            const citedForClaim = new Set([
                ...conclusion.evidence_refs.filter((reference)=>claim.evidence_refs.includes(reference)),
                ...conclusion.counter_evidence_refs.filter((reference)=>claim.counter_evidence_refs.includes(reference))
            ]);
            if (citedForClaim.size === 0) {
                throw new EvidenceBundleError("grounding_error", "A decisive review disposition requires cited Evidence for every Claim");
            }
        }
    }
    if (referencedClaims.some((claim)=>claim.status === "unknown") && ![
        "unknown",
        "request_investigation"
    ].includes(conclusion.disposition)) {
        throw new EvidenceBundleError("grounding_error", "An unknown Claim cannot support a definitive disposition");
    }
    if (conclusion.disposition === "accept" && referencedClaims.some((claim)=>claim.status !== "supported")) {
        throw new EvidenceBundleError("grounding_error", "Acceptance requires supported Claims");
    }
    if ([
        "accept",
        "request_change"
    ].includes(conclusion.disposition)) {
        for (const claim of referencedClaims){
            const cited = conclusion.evidence_refs.filter((reference)=>claim.evidence_refs.includes(reference)).map((reference)=>evidence.get(reference)).filter((item)=>item !== undefined);
            if (!cited.some((item)=>[
                    "corroborated",
                    "reproduced"
                ].includes(item.strength) && item.freshness.status === "current")) {
                throw new EvidenceBundleError("grounding_error", "A decisive disposition requires current corroborated or reproduced supporting Evidence");
            }
        }
    }
}
function knownEvidence(references, evidence, label) {
    if (!Array.isArray(references) || references.some((reference)=>typeof reference !== "string")) {
        throw new EvidenceBundleError("invalid_review", `${label} references must be strings`);
    }
    for (const reference of references){
        if (!evidence.has(reference)) {
            throw new EvidenceBundleError("reference_error", `Unknown ${label} id: ${reference}`);
        }
    }
}
function sameSet(left, right) {
    return left.size === right.size && [
        ...left
    ].every((item)=>right.has(item));
}
function isObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
