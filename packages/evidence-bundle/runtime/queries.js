import { assertVerifiedBundle } from "./trusted.js";
export function queryClaims(bundle, query = {}) {
    assertVerifiedBundle(bundle);
    const ids = query.ids === undefined ? undefined : new Set(query.ids);
    const statuses = values(query.status);
    const text = query.text?.trim().toLocaleLowerCase();
    return bundle.claims.filter((claim)=>(ids === undefined || ids.has(claim.id)) && (statuses === undefined || statuses.has(claim.status)) && (!text || claim.statement.toLocaleLowerCase().includes(text)));
}
export function queryEvidence(bundle, query = {}) {
    assertVerifiedBundle(bundle);
    const ids = query.ids === undefined ? undefined : new Set(query.ids);
    const kinds = values(query.kind);
    const strengths = values(query.strength);
    const freshness = values(query.freshness);
    const text = query.text?.trim().toLocaleLowerCase();
    return bundle.evidence.filter((item)=>(ids === undefined || ids.has(item.id)) && (kinds === undefined || kinds.has(item.kind)) && (strengths === undefined || strengths.has(item.strength)) && (freshness === undefined || freshness.has(item.freshness.status)) && (query.claimId === undefined || item.supports.includes(query.claimId) || item.contradicts.includes(query.claimId)) && (!text || item.proposition.toLocaleLowerCase().includes(text)));
}
export function resolveSource(bundle, sourceId) {
    assertVerifiedBundle(bundle);
    return bundle.sources.find((source)=>source.id === sourceId);
}
function values(value) {
    if (value === undefined) {
        return undefined;
    }
    if (typeof value === "string") {
        return new Set([
            value
        ]);
    }
    return new Set(value);
}
