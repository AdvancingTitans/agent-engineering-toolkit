import { sha256 } from "./canonical.js";
import { readRegularBundleFile } from "./loader.js";
import { EvidenceBundleError } from "./types.js";
import { assertVerifiedBundle } from "./trusted.js";
const BLOB_PATTERN = /^blobs\/sha256-([0-9a-f]{64})$/u;
export async function readBlob(bundle, blobRef) {
    assertVerifiedBundle(bundle);
    const match = BLOB_PATTERN.exec(blobRef);
    if (match === null) {
        throw new EvidenceBundleError("invalid_blob_ref", `Blob reference is invalid: ${blobRef}`);
    }
    const manifestHash = bundle.manifest.integrity.file_hashes[blobRef];
    if (manifestHash === undefined) {
        throw new EvidenceBundleError("reference_error", `Blob is not declared by the Bundle manifest: ${blobRef}`);
    }
    let raw;
    try {
        raw = await readRegularBundleFile(bundle.root, blobRef);
    } catch (error) {
        throw new EvidenceBundleError("read_error", `Cannot read Bundle Blob ${blobRef}: ${String(error)}`);
    }
    const digest = sha256(raw);
    if (digest !== match[1] || digest !== manifestHash) {
        throw new EvidenceBundleError("integrity_error", `Bundle Blob hash mismatch: ${blobRef}`);
    }
    return raw;
}
