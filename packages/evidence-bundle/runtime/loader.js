import { lstat, readFile, readdir } from "node:fs/promises";
import { join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { EvidenceBundleError } from "./types.js";
import { parseStrictJson } from "./strict-json.js";
import { markVerifiedBundle } from "./trusted.js";
export async function loadBundle(root) {
    const bundle = await loadBundleSnapshot(root);
    const { validateLoadedBundleSnapshot } = await import("./validator.js");
    await validateLoadedBundleSnapshot(bundle);
    return markVerifiedBundle(bundle);
}
export async function loadBundleSnapshot(root) {
    const absoluteRoot = resolve(root instanceof URL ? fileURLToPath(root) : root);
    const manifest = await readJson(absoluteRoot, "manifest.json");
    validateManifestEnvelope(manifest);
    const contents = manifest.contents;
    return {
        root: absoluteRoot,
        manifest,
        index: await readJson(absoluteRoot, contents.index),
        claims: await readJsonl(absoluteRoot, contents.claims),
        evidence: await readJsonl(absoluteRoot, contents.evidence),
        observations: await readJsonl(absoluteRoot, contents.observations),
        sources: await readJsonl(absoluteRoot, contents.sources),
        diagnostics: await readJsonl(absoluteRoot, contents.diagnostics),
        conflicts: await readJsonl(absoluteRoot, contents.conflicts),
        ledger: await readJsonl(absoluteRoot, contents.ledger),
        policy: await readJson(absoluteRoot, contents.policy),
        consumerGuide: await readText(absoluteRoot, contents.consumer_guide),
        report: await readText(absoluteRoot, contents.report)
    };
}
export const loadEvidenceBundle = loadBundle;
export function safeBundlePath(root, relative) {
    if (typeof relative !== "string" || relative.length === 0 || relative.includes("\\") || relative.startsWith("/") || relative.split("/").some((part)=>part === "" || part === "." || part === "..")) {
        throw new EvidenceBundleError("unsafe_path", `Bundle path is not a safe relative path: ${relative}`);
    }
    const destination = resolve(root, relative);
    if (!destination.startsWith(`${resolve(root)}/`)) {
        throw new EvidenceBundleError("unsafe_path", `Bundle path escapes its root: ${relative}`);
    }
    return destination;
}
async function readText(root, relative) {
    try {
        return await readRegularBundleFile(root, relative, "utf8");
    } catch (error) {
        if (error instanceof EvidenceBundleError) {
            throw error;
        }
        throw new EvidenceBundleError("read_error", `Cannot read Bundle file ${relative}: ${String(error)}`);
    }
}
async function readJson(root, relative) {
    const text = await readText(root, relative);
    try {
        const value = parseStrictJson(text, `Bundle file ${relative}`);
        if (!isObject(value)) {
            throw new EvidenceBundleError("invalid_bundle", `Bundle file ${relative} must contain one JSON object`);
        }
        return value;
    } catch (error) {
        if (error instanceof EvidenceBundleError) {
            throw error;
        }
        throw new EvidenceBundleError("invalid_json", `Bundle file ${relative} is not valid JSON: ${String(error)}`);
    }
}
async function readJsonl(root, relative) {
    const text = await readText(root, relative);
    const values = [];
    for (const [index, line] of text.split(/\r?\n/u).entries()){
        if (!line.trim()) {
            continue;
        }
        try {
            const value = parseStrictJson(line, `Bundle file ${relative} line ${index + 1}`);
            if (!isObject(value)) {
                throw new EvidenceBundleError("invalid_bundle", `Bundle file ${relative} line ${index + 1} must contain an object`);
            }
            values.push(value);
        } catch (error) {
            if (error instanceof EvidenceBundleError) {
                throw error;
            }
            throw new EvidenceBundleError("invalid_json", `Bundle file ${relative} line ${index + 1} is invalid: ${String(error)}`);
        }
    }
    return values;
}
export async function readRegularBundleFile(root, relativePath, encoding) {
    const rootPath = resolve(root);
    const rootStatus = await lstat(rootPath);
    if (rootStatus.isSymbolicLink() || !rootStatus.isDirectory()) {
        throw new EvidenceBundleError("unsafe_file", "Bundle root must be a real directory");
    }
    const destination = safeBundlePath(rootPath, relativePath);
    let cursor = rootPath;
    const parts = relativePath.split("/");
    for (const [index, part] of parts.entries()){
        cursor = join(cursor, part);
        const status = await lstat(cursor);
        if (status.isSymbolicLink()) {
            throw new EvidenceBundleError("unsafe_file", `Bundle path contains a symbolic link: ${relativePath}`);
        }
        if (index < parts.length - 1 && !status.isDirectory()) {
            throw new EvidenceBundleError("unsafe_file", `Bundle path component is not a directory: ${relativePath}`);
        }
        if (index === parts.length - 1 && !status.isFile()) {
            throw new EvidenceBundleError("unsafe_file", `Bundle content is not a regular file: ${relativePath}`);
        }
    }
    return encoding === undefined ? await readFile(destination) : await readFile(destination, encoding);
}
export async function listRegularBundleFiles(root) {
    const rootPath = resolve(root);
    const rootStatus = await lstat(rootPath);
    if (rootStatus.isSymbolicLink() || !rootStatus.isDirectory()) {
        throw new EvidenceBundleError("unsafe_file", "Bundle root must be a real directory");
    }
    const files = [];
    async function visit(directory) {
        for (const entry of (await readdir(directory, {
            withFileTypes: true
        }))){
            const path = join(directory, entry.name);
            const status = await lstat(path);
            if (status.isSymbolicLink()) {
                throw new EvidenceBundleError("unsafe_file", `Bundle contains a symbolic link: ${relative(rootPath, path)}`);
            }
            if (status.isDirectory()) {
                await visit(path);
            } else if (status.isFile()) {
                files.push(relative(rootPath, path).split("\\").join("/"));
            } else {
                throw new EvidenceBundleError("unsafe_file", `Bundle contains a special file: ${relative(rootPath, path)}`);
            }
        }
    }
    await visit(rootPath);
    return files.sort();
}
function validateManifestEnvelope(value) {
    if (!isObject(value) || !isObject(value.protocol) || value.protocol.name !== "portable-evidence-bundle" || value.protocol.version !== "1.0") {
        throw new EvidenceBundleError("unsupported_semantics", "Manifest protocol must be portable-evidence-bundle/1.0");
    }
    if (!isObject(value.bundle) || typeof value.bundle.id !== "string" || value.bundle.id.length === 0 || !isObject(value.contents) || !isObject(value.integrity)) {
        throw new EvidenceBundleError("invalid_bundle", "Manifest is missing its Bundle identity, contents, or integrity object");
    }
    for (const field of [
        "index",
        "claims",
        "evidence",
        "observations",
        "sources",
        "diagnostics",
        "conflicts",
        "ledger",
        "policy",
        "consumer_guide",
        "report"
    ]){
        if (typeof value.contents[field] !== "string") {
            throw new EvidenceBundleError("invalid_bundle", `Manifest contents.${field} must be a path`);
        }
        safeBundlePath(".", value.contents[field]);
    }
}
function isObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}
