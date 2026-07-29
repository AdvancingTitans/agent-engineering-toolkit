import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import {
  EvidenceBundleError,
  loadPlan,
  queryPlanEdits,
  validatePlanReferences,
} from "../runtime/index.js";

const contents = {
  request: "request.json",
  context_summary: "context-summary.json",
  plan: "plan.json",
  plan_markdown: "plan.md",
  references: "references.jsonl",
  diagnostics: "diagnostics.jsonl",
  consumer_guide: "consumer-guide.md",
  skill: "skill/SKILL.md",
  skill_plan: "skill/references/plan.md",
  skill_authority: "skill/references/authority-boundary.md",
  skill_source_map: "skill/references/source-map.json",
};

async function makePlanPackage() {
  const root = await mkdtemp(join(tmpdir(), "aet-plan-sdk-"));
  const plan = {
    schema_version: "evidence-linked-plan/1.0",
    plan_id: "PLAN-SDK-001",
    status: "READY_FOR_HUMAN_REVIEW",
    authority: "PROPOSED",
    edit_items: [
      {
        edit_id: "EDIT-001",
        disposition: "REQUIRED",
        path: "src/example.js",
        symbol: null,
        intent: "Update the bounded implementation.",
        expected_change: "Preserve the contract.",
        rationale: "Current source confirms the location.",
        evidence_refs: [],
        atlas_refs: [],
        source_refs: ["SRC-001"],
        dependencies: [],
        tests: ["test/example.test.js"],
        risks: [],
        limitations: [],
      },
    ],
    verification_steps: [],
    diagnostics: [],
    conflicts: [],
    unknowns: [],
  };
  const references = [
    {
      schema_version: "plan-reference/1.0",
      reference_id: "SRC-001",
      kind: "SOURCE",
    },
  ];
  const files = {
    "request.json": "{}\n",
    "context-summary.json": "{}\n",
    "plan.json": `${JSON.stringify(plan)}\n`,
    "plan.md": "# Plan\n",
    "references.jsonl": `${JSON.stringify(references[0])}\n`,
    "diagnostics.jsonl": "",
    "consumer-guide.md": "# Consumer Guide\n",
    "skill/SKILL.md": "---\nname: plan-sdk\n---\n",
    "skill/references/plan.md": "# Plan\n",
    "skill/references/authority-boundary.md": "# Authority\n",
    "skill/references/source-map.json": "{}\n",
  };
  for (const [relative, value] of Object.entries(files)) {
    const destination = join(root, relative);
    await mkdir(join(destination, ".."), { recursive: true });
    await writeFile(destination, value, "utf8");
  }
  const hashes = Object.fromEntries(
    Object.entries(files).map(([relative, value]) => [
      relative,
      createHash("sha256").update(value).digest("hex"),
    ]),
  );
  await writeFile(
    join(root, "manifest.json"),
    `${JSON.stringify({
      schema_version: "plan-manifest/1.0",
      plan_id: plan.plan_id,
      status: plan.status,
      authority: "PROPOSED",
      contents,
      integrity: { algorithm: "sha256", file_hashes: hashes },
    })}\n`,
    "utf8",
  );
  return { root, plan, references };
}

test("loads, queries, and resolves a portable Evidence-Linked Plan", async () => {
  const fixture = await makePlanPackage();
  try {
    const plan = await loadPlan(fixture.root);
    assert.equal(plan.authority, "PROPOSED");
    assert.deepEqual(
      queryPlanEdits(plan, { path: "src/example.js" }).map(
        (item) => item.edit_id,
      ),
      ["EDIT-001"],
    );
    assert.equal(
      validatePlanReferences(plan, fixture.references).status,
      "PASS",
    );
    assert.throws(
      () => validatePlanReferences(plan, []),
      EvidenceBundleError,
    );
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});

test("rejects a modified Plan package", async () => {
  const fixture = await makePlanPackage();
  try {
    await writeFile(join(fixture.root, "plan.md"), "tampered\n", "utf8");
    await assert.rejects(loadPlan(fixture.root), EvidenceBundleError);
  } finally {
    await rm(fixture.root, { recursive: true, force: true });
  }
});
