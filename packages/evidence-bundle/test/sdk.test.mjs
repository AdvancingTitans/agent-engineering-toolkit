import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { EvidenceBundleError, loadBundle, queryClaims, queryEvidence, readBlob, renderPromptContext, resolveSource, validateBundle, validateReviewReferences } from "../runtime/index.js";
const fixture = fileURLToPath(new URL("../../../tests/fixtures/evidence-bundles/minimal/", import.meta.url));
test("loads, validates, and queries a Portable Evidence Bundle", async ()=>{
    const bundle = await loadBundle(fixture);
    const report = await validateBundle(bundle);
    assert.equal(report.status, "PASS");
    assert.equal(report.bundle_id, "bundle-fixture-001");
    assert.deepEqual(queryClaims(bundle, {
        status: "supported"
    }).map((item)=>item.id), [
        "claim-001"
    ]);
    assert.deepEqual(queryEvidence(bundle, {
        strength: "reproduced",
        freshness: "current",
        claimId: "claim-001"
    }).map((item)=>item.id), [
        "ev-001"
    ]);
    assert.equal(resolveSource(bundle, "src-001")?.type, "proof_receipt");
    const context = renderPromptContext(bundle, {
        claimIds: [
            "claim-001"
        ]
    });
    assert.match(context, /claim-001/u);
    assert.match(context, /ev-001/u);
});
test("validates review references without replacing reviewer judgment", async ()=>{
    const bundle = await loadBundle(fixture);
    const review = {
        protocol: {
            name: "portable-review-result",
            version: "1.0"
        },
        bundle_id: "bundle-fixture-001",
        conclusions: [
            {
                id: "conclusion-001",
                statement: "The bounded evidence supports acceptance.",
                disposition: "accept",
                claim_refs: [
                    "claim-001"
                ],
                evidence_refs: [
                    "ev-001"
                ],
                counter_evidence_refs: [],
                reasoning_summary: "The cited evidence is current and reproduced.",
                limitations: [
                    "The conclusion covers only the declared command."
                ]
            }
        ],
        unresolved_questions: []
    };
    assert.equal(validateReviewReferences(bundle, review).status, "PASS");
    assert.throws(()=>validateReviewReferences(bundle, {
            ...review,
            bundle_id: "another-bundle"
        }), EvidenceBundleError);
});
test("rejects undeclared or malformed Blob references", async ()=>{
    const bundle = await loadBundle(fixture);
    await assert.rejects(readBlob(bundle, "../secret"), EvidenceBundleError);
    await assert.rejects(readBlob(bundle, `blobs/sha256-${"0".repeat(64)}`), EvidenceBundleError);
});
