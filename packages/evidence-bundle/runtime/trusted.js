import { EvidenceBundleError } from "./types.js";
const verifiedBundles = new WeakSet();
export function markVerifiedBundle(bundle) {
    deepFreeze(bundle);
    verifiedBundles.add(bundle);
    return bundle;
}
export function assertVerifiedBundle(bundle) {
    if (!verifiedBundles.has(bundle) || !Object.isFrozen(bundle)) {
        throw new EvidenceBundleError("unverified_handle", "This API requires an immutable Bundle handle returned by loadBundle");
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
