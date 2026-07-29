import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  listRegularBundleFiles,
  readRegularBundleFile,
} from "./loader.js";
import { parseStrictJson } from "./strict-json.js";
import { EvidenceBundleError } from "./types.js";

const PLAN_CONTENTS = {
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
const PLAN_FILES = Object.values(PLAN_CONTENTS);

export async function loadPlan(path) {
  const root = resolve(path instanceof URL ? fileURLToPath(path) : path);
  const manifest = await readObject(root, "manifest.json");
  validateManifest(manifest);
  const expectedFiles = [...PLAN_FILES, "manifest.json"].sort();
  const actualFiles = await listRegularBundleFiles(root);
  if (JSON.stringify(actualFiles) !== JSON.stringify(expectedFiles)) {
    throw new EvidenceBundleError(
      "invalid_plan",
      "Plan package file set does not match plan-manifest/1.0",
    );
  }
  for (const [relative, expected] of Object.entries(
    manifest.integrity.file_hashes,
  )) {
    const raw = await readRegularBundleFile(root, relative);
    const actual = createHash("sha256").update(raw).digest("hex");
    if (actual !== expected) {
      throw new EvidenceBundleError(
        "integrity_error",
        `Plan package hash mismatch: ${relative}`,
      );
    }
  }
  const plan = await readObject(root, "plan.json");
  if (
    plan.schema_version !== "evidence-linked-plan/1.0" ||
    plan.authority !== "PROPOSED" ||
    plan.plan_id !== manifest.plan_id ||
    plan.status !== manifest.status
  ) {
    throw new EvidenceBundleError(
      "invalid_plan",
      "Plan and Manifest identities do not agree",
    );
  }
  const references = await readJsonl(root, "references.jsonl");
  validatePlanReferences(plan, references);
  return plan;
}

export function queryPlanEdits(plan, filter = {}) {
  requirePlan(plan);
  const allowed = new Set(["path", "disposition"]);
  if (
    typeof filter !== "object" ||
    filter === null ||
    Array.isArray(filter) ||
    Object.keys(filter).some((key) => !allowed.has(key))
  ) {
    throw new EvidenceBundleError("invalid_plan", "Edit filter is invalid");
  }
  return plan.edit_items.filter(
    (item) =>
      (filter.path === undefined || item.path === filter.path) &&
      (filter.disposition === undefined ||
        item.disposition === filter.disposition),
  );
}

export function validatePlanReferences(plan, refs) {
  requirePlan(plan);
  const values = Array.isArray(refs) ? refs : Object.values(refs ?? {});
  if (
    values.some(
      (item) =>
        typeof item !== "object" ||
        item === null ||
        Array.isArray(item) ||
        typeof item.reference_id !== "string",
    )
  ) {
    throw new EvidenceBundleError(
      "reference_error",
      "Plan Reference Index must contain plan-reference objects",
    );
  }
  const identifiers = new Set(values.map((item) => item.reference_id));
  if (identifiers.size !== values.length) {
    throw new EvidenceBundleError(
      "reference_error",
      "Plan Reference IDs must be unique",
    );
  }
  const unresolved = new Set();
  for (const edit of plan.edit_items) {
    for (const field of ["evidence_refs", "atlas_refs", "source_refs"]) {
      for (const reference of edit[field] ?? []) {
        if (!identifiers.has(reference)) {
          unresolved.add(reference);
        }
      }
    }
  }
  if (unresolved.size > 0) {
    throw new EvidenceBundleError(
      "reference_error",
      `Unresolved Plan references: ${[...unresolved].sort().join(", ")}`,
    );
  }
  return {
    schema_version: "plan-reference-validation/1.0",
    status: "PASS",
    plan_id: plan.plan_id,
    reference_count: values.length,
    resolved_reference_count: identifiers.size,
  };
}

function requirePlan(plan) {
  if (
    typeof plan !== "object" ||
    plan === null ||
    Array.isArray(plan) ||
    plan.schema_version !== "evidence-linked-plan/1.0" ||
    plan.authority !== "PROPOSED" ||
    typeof plan.plan_id !== "string" ||
    !Array.isArray(plan.edit_items)
  ) {
    throw new EvidenceBundleError(
      "invalid_plan",
      "Evidence-Linked Plan is invalid",
    );
  }
}

function validateManifest(manifest) {
  if (
    manifest.schema_version !== "plan-manifest/1.0" ||
    manifest.authority !== "PROPOSED" ||
    typeof manifest.plan_id !== "string" ||
    typeof manifest.integrity !== "object" ||
    manifest.integrity === null ||
    manifest.integrity.algorithm !== "sha256" ||
    typeof manifest.integrity.file_hashes !== "object" ||
    manifest.integrity.file_hashes === null ||
    JSON.stringify(manifest.contents) !== JSON.stringify(PLAN_CONTENTS)
  ) {
    throw new EvidenceBundleError(
      "invalid_plan",
      "Plan Manifest is invalid",
    );
  }
  const hashPaths = Object.keys(manifest.integrity.file_hashes).sort();
  if (JSON.stringify(hashPaths) !== JSON.stringify([...PLAN_FILES].sort())) {
    throw new EvidenceBundleError(
      "invalid_plan",
      "Plan Manifest contents do not match plan-manifest/1.0",
    );
  }
}

async function readObject(root, relative) {
  const value = parseStrictJson(
    await readRegularBundleFile(root, relative, "utf8"),
    `Plan file ${relative}`,
  );
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new EvidenceBundleError(
      "invalid_plan",
      `Plan file ${relative} must contain one object`,
    );
  }
  return value;
}

async function readJsonl(root, relative) {
  const text = await readRegularBundleFile(root, relative, "utf8");
  const values = [];
  for (const [index, line] of text.split(/\r?\n/u).entries()) {
    if (!line.trim()) {
      continue;
    }
    const value = parseStrictJson(
      line,
      `Plan file ${relative} line ${index + 1}`,
    );
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      throw new EvidenceBundleError(
        "invalid_plan",
        `Plan file ${relative} line ${index + 1} must contain one object`,
      );
    }
    values.push(value);
  }
  return values;
}
