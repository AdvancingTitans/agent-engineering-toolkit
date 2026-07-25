import { createHash } from "node:crypto";
export function canonicalJson(value) {
    if (value === null || typeof value === "string" || typeof value === "boolean") {
        return JSON.stringify(value);
    }
    if (typeof value === "number") {
        if (!Number.isFinite(value)) {
            throw new TypeError("canonical JSON does not support non-finite numbers");
        }
        return JSON.stringify(value);
    }
    if (Array.isArray(value)) {
        return `[${value.map((item)=>canonicalJson(item)).join(",")}]`;
    }
    if (typeof value === "object") {
        const object = value;
        return `{${Object.keys(object).sort().map((key)=>`${JSON.stringify(key)}:${canonicalJson(object[key])}`).join(",")}}`;
    }
    throw new TypeError("value is not canonical JSON");
}
export function sha256(value) {
    return createHash("sha256").update(value).digest("hex");
}
export function manifestContentHash(manifest) {
    const candidate = structuredClone(manifest);
    candidate.bundle.content_hash = "0".repeat(64);
    return sha256(canonicalJson(candidate));
}
