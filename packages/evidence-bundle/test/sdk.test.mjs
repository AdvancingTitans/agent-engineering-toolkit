import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { EvidenceBundleError, loadBundle, queryClaims, queryEvidence, readBlob, renderPromptContext, resolveSource, validateBundle, validateReviewReferences, validateRiskDiagnosis, validateRiskForecast } from "../runtime/index.js";
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
test("validates evidence-bound risk contracts without granting action authority", ()=>{
    const ref = {
        ref: "tool-result-001",
        record_id: "tool-result-001",
        source_order_id: "0002",
        source_type: "codex"
    };
    const finding = {
        factor: "harm_realization_capability",
        observable: "A protected action produced a verified effect.",
        status: "FAIL",
        strength: "DIRECT",
        evidence_refs: [ref],
        counter_evidence_refs: [],
        coverage: {
            complete: true,
            checked_surfaces: ["deploy"],
            gaps: [],
            observability_gap: false
        },
        limitations: ["This does not establish capability outside this deployment."],
        does_not_prove: ["Internal motive or stable disposition."],
        context_key: "run:generation:task",
        asset_ids: ["deployment"],
        monitoring_surface_ids: [],
        signal_codes: ["PROTECTED_ACTION_SUCCEEDED"],
        order_keys: ["0002"]
    };
    const diagnosis = {
        schema_version: "aet-risk-diagnosis/1.0",
        evaluator_version: "1.0.0",
        created_at: "2026-08-01T00:00:00Z",
        policy_id: "policy-001",
        policy_sha256: "a".repeat(64),
        findings: [finding],
        pathways: [],
        interventions: [{
            intervention_id: "intervention-001",
            context_key: finding.context_key,
            factor_combination: [finding.factor],
            authority: "PROPOSED",
            actions: ["Require human approval."],
            rationale_refs: [ref]
        }],
        diagnostics: [],
        provenance: {evaluator: "deterministic"}
    };
    assert.equal(validateRiskDiagnosis(diagnosis).status, "PASS");
    assert.throws(()=>validateRiskDiagnosis({...diagnosis, trust_score: 1}), EvidenceBundleError);

    const forecast = {
        schema_version: "aet-risk-forecast/1.0",
        created_at: "2026-08-01T00:00:00Z",
        diagnosis_sha256: "b".repeat(64),
        calibration_sha256: "c".repeat(64),
        dataset_sha256: "d".repeat(64),
        forecasts: [{
            pathway_id: "pathway-001",
            signature: "harm_realization_capability",
            status: "UNKNOWN",
            support: 24,
            interval: {low: null, high: null},
            baseline: {low: null, high: null},
            reason: "calibration_gate_failed"
        }],
        gate_status: "FAIL",
        limitations: ["Insufficient independent outcomes."],
        provenance: {method: "wilson_interval"}
    };
    assert.equal(validateRiskForecast(forecast).gate_status, "FAIL");
});
