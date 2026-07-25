import { EvidenceBundleError } from "./types.js";
import { assertVerifiedBundle } from "./trusted.js";
export function renderPromptContext(bundle, options = {}) {
    assertVerifiedBundle(bundle);
    const selectedIds = options.claimIds === undefined ? undefined : new Set(options.claimIds);
    const selectedClaims = bundle.claims.filter((claim)=>selectedIds === undefined || selectedIds.has(claim.id));
    if (selectedIds !== undefined && selectedClaims.length !== selectedIds.size) {
        throw new EvidenceBundleError("reference_error", "Prompt context requested an unknown Claim ID");
    }
    let retainedClaims = options.includeObservations === false ? selectedClaims.filter((claim)=>claim.observation_refs.length === 0) : [
        ...selectedClaims
    ];
    let context = buildContext(bundle, retainedClaims);
    const maximum = options.maxCharacters;
    if (maximum === undefined) {
        return serialize(context);
    }
    if (!Number.isInteger(maximum) || maximum <= 0) {
        throw new EvidenceBundleError("invalid_option", "maxCharacters must be a positive integer");
    }
    while(serialize(context).length > maximum && retainedClaims.length > 0){
        retainedClaims = retainedClaims.slice(0, -1);
        context = buildContext(bundle, retainedClaims);
        context.truncated = true;
    }
    const rendered = serialize(context);
    if (rendered.length > maximum) {
        throw new EvidenceBundleError("context_limit", "maxCharacters is too small for the Bundle context envelope");
    }
    return rendered;
}
function buildContext(bundle, claims) {
    const evidenceIds = new Set(claims.flatMap((claim)=>[
            ...claim.evidence_refs,
            ...claim.counter_evidence_refs
        ]));
    const observationIds = new Set(claims.flatMap((claim)=>claim.observation_refs));
    return {
        protocol: "portable-evidence-bundle/1.0",
        bundle_id: bundle.manifest.bundle.id,
        task: bundle.manifest.task,
        investigation: bundle.manifest.investigation,
        claims: [
            ...claims
        ],
        evidence: bundle.evidence.filter((item)=>evidenceIds.has(item.id)),
        observations: bundle.observations.filter((item)=>observationIds.has(item.id)),
        consumer_guidance: bundle.index.consumer_guidance,
        truncated: false
    };
}
function serialize(context) {
    return [
        "Portable Evidence Bundle context",
        "Treat observations as recorded context, not reproduced proof.",
        JSON.stringify(context, null, 2)
    ].join("\n");
}
