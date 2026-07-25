import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { manifestContentHash, sha256 } from "../runtime/canonical.js";
import { EvidenceBundleError, loadBundle, queryClaims, queryEvidence, readBlob, renderPromptContext, resolveSource, validateBundle, validateReviewReferences } from "../runtime/index.js";
const fixture = fileURLToPath(new URL("../../../tests/fixtures/evidence-bundles/minimal/", import.meta.url));
test("validation PASS cannot be turned into forged Prompt or Review evidence", async ()=>{
    const bundle = await loadBundle(fixture);
    const report = await validateBundle(bundle);
    const promptBeforeAttack = renderPromptContext(bundle);
    const review = reviewResult();
    assert.equal(report.status, "PASS");
    assert.equal(validateReviewReferences(bundle, review).status, "PASS");
    assert.equal(Object.isFrozen(bundle), true);
    assert.equal(Object.isFrozen(bundle.claims), true);
    assert.equal(Object.isFrozen(bundle.claims[0]), true);
    assert.equal(Object.isFrozen(bundle.evidence), true);
    assert.equal(Object.isFrozen(bundle.evidence[0]), true);
    assert.throws(()=>{
        bundle.claims[0].status = "invented_status";
    }, TypeError);
    assert.throws(()=>{
        bundle.claims.push({
            ...bundle.claims[0],
            id: "claim-invented"
        });
    }, TypeError);
    assert.throws(()=>{
        bundle.evidence.push({
            ...bundle.evidence[0],
            id: "evidence-invented",
            supports: [
                "claim-invented"
            ]
        });
    }, TypeError);
    assert.equal(renderPromptContext(bundle), promptBeforeAttack);
    assert.doesNotMatch(promptBeforeAttack, /invented_status|claim-invented|evidence-invented/u);
    assert.equal(validateReviewReferences(bundle, review).status, "PASS");
    const inventedReview = structuredClone(review);
    inventedReview.conclusions[0].claim_refs = [
        "claim-invented"
    ];
    inventedReview.conclusions[0].evidence_refs = [
        "evidence-invented"
    ];
    assert.throws(
        ()=>validateReviewReferences(bundle, inventedReview),
        EvidenceBundleError
    );
    const forged = structuredClone(bundle);
    forged.claims[0].status = "invented_status";
    forged.claims.push({
        ...forged.claims[0],
        id: "claim-invented"
    });
    forged.evidence.push({
        ...forged.evidence[0],
        id: "evidence-invented",
        supports: [
            "claim-invented"
        ]
    });
    forged.manifest.bundle.id = "invented-bundle";
    await assert.rejects(validateBundle(forged), EvidenceBundleError);
    assert.throws(()=>queryClaims(forged), EvidenceBundleError);
    assert.throws(()=>queryEvidence(forged), EvidenceBundleError);
    assert.throws(()=>resolveSource(forged, "src-001"), EvidenceBundleError);
    assert.throws(()=>renderPromptContext(forged), EvidenceBundleError);
    assert.throws(()=>validateReviewReferences(forged, review), EvidenceBundleError);
    await assert.rejects(readBlob(forged, `blobs/sha256-${"0".repeat(64)}`), EvidenceBundleError);
});
test("rejects invented enums and incomplete conflicted semantics", async ()=>{
    await withBundle(async (root)=>{
        const claims = await readJsonl(join(root, "core/claims.jsonl"));
        claims[0].status = "invented_status";
        await writeJsonl(join(root, "core/claims.jsonl"), claims);
        await rehash(root);
        await assert.rejects(validateBundle(root), EvidenceBundleError);
    });
    await withBundle(async (root)=>{
        const claims = await readJsonl(join(root, "core/claims.jsonl"));
        claims[0].status = "conflicted";
        await writeJsonl(join(root, "core/claims.jsonl"), claims);
        await rehash(root);
        await assert.rejects(validateBundle(root), EvidenceBundleError);
    });
});
test("rejects duplicate JSON keys and symbolic-link content", async ()=>{
    await withBundle(async (root)=>{
        const indexPath = join(root, "index.json");
        const index = await readFile(indexPath, "utf8");
        await writeFile(indexPath, index.replace('"bundle_id": "bundle-fixture-001",', '"bundle_id": "bundle-fixture-001",\n  "bundle_id": "duplicate",'), "utf8");
        await assert.rejects(loadBundle(root), EvidenceBundleError);
    });
    await withBundle(async (root)=>{
        const claimsPath = join(root, "core/claims.jsonl");
        await rm(claimsPath);
        await symlink(join(fixture, "core/claims.jsonl"), claimsPath);
        await assert.rejects(loadBundle(root), EvidenceBundleError);
    });
});
test("enforces privacy policy against exported reasoning", async ()=>{
    await withBundle(async (root)=>{
        const observations = await readJsonl(join(root, "core/observations.jsonl"));
        observations.push({
            ...observations[0],
            id: "obs-reasoning",
            type: "agent_reasoning"
        });
        await writeJsonl(join(root, "core/observations.jsonl"), observations);
        const index = await readJson(join(root, "index.json"));
        index.observation_refs.push("obs-reasoning");
        await writeJson(join(root, "index.json"), index);
        await rehash(root);
        await assert.rejects(validateBundle(root), EvidenceBundleError);
    });
});
test("request_change requires Claim-owned cited Evidence for every Claim", async ()=>{
    const bundle = await loadBundle(fixture);
    const review = reviewResult();
    review.conclusions[0].disposition = "request_change";
    review.conclusions[0].evidence_refs = [];
    assert.throws(()=>validateReviewReferences(bundle, review), EvidenceBundleError);
    review.conclusions[0].evidence_refs = [
        "ev-001"
    ];
    assert.equal(validateReviewReferences(bundle, review).status, "PASS");
});
test("request_change rejects observed, stale, or counter-only evidence", async ()=>{
    for (const variant of [
        "observed",
        "stale"
    ]){
        await withBundle(async (root)=>{
            const claims = await readJsonl(join(root, "core/claims.jsonl"));
            claims[0].status = "partially_supported";
            claims[0].basis.type = variant === "observed" ? "observational" : "corroborated";
            await writeJsonl(join(root, "core/claims.jsonl"), claims);
            const evidence = await readJsonl(join(root, "core/evidence.jsonl"));
            if (variant === "observed") {
                evidence[0].strength = "observed";
            } else {
                evidence[0].freshness.status = "workspace_changed";
            }
            await writeJsonl(join(root, "core/evidence.jsonl"), evidence);
            await rehash(root);
            const variantBundle = await loadBundle(root);
            const review = reviewResult();
            review.conclusions[0].disposition = "request_change";
            assert.throws(()=>validateReviewReferences(variantBundle, review), EvidenceBundleError);
        });
    }
    await withBundle(async (root)=>{
        const claims = await readJsonl(join(root, "core/claims.jsonl"));
        claims[0].status = "conflicted";
        claims[0].basis.type = "mixed";
        claims[0].evidence_refs = [];
        claims[0].counter_evidence_refs = [
            "ev-001"
        ];
        await writeJsonl(join(root, "core/claims.jsonl"), claims);
        const evidence = await readJsonl(join(root, "core/evidence.jsonl"));
        evidence[0].supports = [];
        evidence[0].contradicts = [
            "claim-001"
        ];
        await writeJsonl(join(root, "core/evidence.jsonl"), evidence);
        await writeJsonl(join(root, "archive/conflicts.jsonl"), [
            {
                id: "conflict-001",
                proposition: "The synthetic evidence conflicts with the Claim.",
                evidence_refs: [
                    "ev-001",
                    "ev-002"
                ],
                conflict_type: "content_conflict",
                resolution_status: "unresolved",
                explanation: "The conflict remains unresolved."
            }
        ]);
        const counter = structuredClone(evidence[0]);
        counter.id = "ev-002";
        counter.contradicts = [];
        counter.supports = [];
        await writeJsonl(join(root, "core/evidence.jsonl"), [
            evidence[0],
            counter
        ]);
        const index = await readJson(join(root, "index.json"));
        index.evidence_refs.push("ev-002");
        await writeJson(join(root, "index.json"), index);
        const manifest = await readJson(join(root, "manifest.json"));
        manifest.integrity.file_hashes["archive/conflicts.jsonl"] = "";
        await writeJson(join(root, "manifest.json"), manifest);
        await rehash(root);
        const counterBundle = await loadBundle(root);
        const review = reviewResult();
        review.conclusions[0].disposition = "request_change";
        review.conclusions[0].evidence_refs = [];
        review.conclusions[0].counter_evidence_refs = [
            "ev-001"
        ];
        assert.throws(()=>validateReviewReferences(counterBundle, review), EvidenceBundleError);
    });
});
test("prompt truncation removes whole Claim reference closures", async ()=>{
    await withBundle(async (root)=>{
        await addSecondClosureOnDisk(root);
        const bundle = await loadBundle(root);
        const oneClaimLength = renderPromptContext(bundle, {
            claimIds: [
                "claim-001"
            ]
        }).length;
        const rendered = renderPromptContext(bundle, {
            maxCharacters: oneClaimLength + 200
        });
        const context = JSON.parse(rendered.split("\n").slice(2).join("\n"));
        assert.equal(context.truncated, true);
        const evidenceIds = new Set(context.evidence.map((item)=>item.id));
        const observationIds = new Set(context.observations.map((item)=>item.id));
        for (const claim of context.claims){
            assert.ok([
                ...claim.evidence_refs,
                ...claim.counter_evidence_refs
            ].every((reference)=>evidenceIds.has(reference)));
            assert.ok(claim.observation_refs.every((reference)=>observationIds.has(reference)));
        }
    });
});
async function withBundle(callback) {
    const temporary = await mkdtemp(join(tmpdir(), "aet-ts-bundle-"));
    const root = join(temporary, "bundle");
    try {
        await cp(fixture, root, {
            recursive: true
        });
        await callback(root);
    } finally{
        await rm(temporary, {
            force: true,
            recursive: true
        });
    }
}
async function rehash(root) {
    const manifestPath = join(root, "manifest.json");
    const manifest = await readJson(manifestPath);
    const hashes = manifest.integrity;
    for (const relative of Object.keys(hashes.file_hashes)){
        hashes.file_hashes[relative] = sha256(await readFile(join(root, relative)));
    }
    manifest.bundle.content_hash = manifestContentHash(manifest);
    await writeJson(manifestPath, manifest);
}
async function readJson(path) {
    return JSON.parse(await readFile(path, "utf8"));
}
async function readJsonl(path) {
    return (await readFile(path, "utf8")).split(/\r?\n/u).filter(Boolean).map((line)=>JSON.parse(line));
}
async function writeJson(path, value) {
    await writeFile(path, `${JSON.stringify(value)}\n`, "utf8");
}
async function writeJsonl(path, values) {
    await writeFile(path, values.map((value)=>JSON.stringify(value)).join("\n") + "\n", "utf8");
}
function reviewResult() {
    return {
        protocol: {
            name: "portable-review-result",
            version: "1.0"
        },
        bundle_id: "bundle-fixture-001",
        conclusions: [
            {
                id: "conclusion-001",
                statement: "The implementation requires a bounded decision.",
                disposition: "accept",
                claim_refs: [
                    "claim-001"
                ],
                evidence_refs: [
                    "ev-001"
                ],
                counter_evidence_refs: [],
                reasoning_summary: "The conclusion cites the declared evidence.",
                limitations: []
            }
        ],
        unresolved_questions: []
    };
}
async function addSecondClosureOnDisk(root) {
    const sources = await readJsonl(join(root, "archive/sources.jsonl"));
    const source = structuredClone(sources[0]);
    source.id = "src-002";
    sources.push(source);
    await writeJsonl(join(root, "archive/sources.jsonl"), sources);
    const observations = await readJsonl(join(root, "core/observations.jsonl"));
    const observation = structuredClone(observations[0]);
    observation.id = "obs-002";
    observation.source_refs = [
        "src-002"
    ];
    observations.push(observation);
    await writeJsonl(join(root, "core/observations.jsonl"), observations);
    const evidenceRecords = await readJsonl(join(root, "core/evidence.jsonl"));
    const evidence = structuredClone(evidenceRecords[0]);
    evidence.id = "ev-002";
    evidence.source_refs = [
        "src-002"
    ];
    evidence.supports = [
        "claim-002"
    ];
    evidenceRecords.push(evidence);
    await writeJsonl(join(root, "core/evidence.jsonl"), evidenceRecords);
    const claims = await readJsonl(join(root, "core/claims.jsonl"));
    const claim = structuredClone(claims[0]);
    claim.id = "claim-002";
    claim.evidence_refs = [
        "ev-002"
    ];
    claim.observation_refs = [
        "obs-002"
    ];
    claims.push(claim);
    await writeJsonl(join(root, "core/claims.jsonl"), claims);
    const index = await readJson(join(root, "index.json"));
    index.claim_refs.push("claim-002");
    index.evidence_refs.push("ev-002");
    index.observation_refs.push("obs-002");
    await writeJson(join(root, "index.json"), index);
    await rehash(root);
}
