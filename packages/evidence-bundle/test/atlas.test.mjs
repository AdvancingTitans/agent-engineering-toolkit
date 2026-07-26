import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  EvidenceBundleError,
  buildEvidenceGraph,
  getNodeSubgraph,
  loadBundle,
  loadEvidenceGraph,
  queryPerspective,
  renderMermaid,
  traceClaimSupport,
  traceFreshnessImpact,
  validateEvidenceGraph,
} from "../runtime/index.js";

const fixture = fileURLToPath(
  new URL(
    "../../../tests/fixtures/evidence-bundles/minimal/",
    import.meta.url,
  ),
);
const repositoryRoot = fileURLToPath(new URL("../../..", import.meta.url));

test("builds, validates, and queries the eight deterministic Atlas perspectives", async () => {
  const bundle = await loadBundle(fixture);
  const graph = buildEvidenceGraph(bundle);
  assert.equal(Object.isFrozen(graph), true);
  assert.equal((await validateEvidenceGraph(graph)).status, "PASS");
  assert.deepEqual(
    graph.perspectives.map((item) => item.id),
    [
      "claim-chain",
      "investigation-flow",
      "change-scope",
      "verification-coverage",
      "evidence-data-flow",
      "integrations",
      "conflicts",
      "freshness",
    ],
  );
  assert.equal(
    graph.perspectives.find((item) => item.id === "change-scope")
      .coverage_status,
    "UNKNOWN",
  );

  const claim = traceClaimSupport(graph, "claim-001");
  assert.equal(claim.claim_status, "supported");
  assert.deepEqual(claim.supporting_evidence_ids, [
    "node:verified_evidence:ev-001",
  ]);
  assert.deepEqual(claim.counter_evidence_ids, []);
  assert.equal(
    traceFreshnessImpact(graph, "ev-001").freshness,
    "current",
  );
  assert.ok(
    getNodeSubgraph(graph, "claim-001", {
      depth: 2,
      maxNodes: 20,
    }).nodes.length > 1,
  );
  assert.ok(
    queryPerspective(graph, "verification-coverage", {
      maxNodes: 25,
    }).nodes.some((node) => node.type === "proof"),
  );
  assert.match(renderMermaid(graph), /^flowchart LR\n/u);
});

test("matches the Python and schema graph contract", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "aet-atlas-interop-"));
  try {
    const bundle = await loadBundle(fixture);
    const graph = buildEvidenceGraph(bundle);
    const digest = (value) => createHash("sha256").update(value).digest("hex");
    assert.equal(
      graph.generated_from.manifest_sha256,
      digest(await readFile(join(fixture, "manifest.json"))),
    );
    assert.equal(
      graph.generated_from.index_sha256,
      digest(await readFile(join(fixture, "index.json"))),
    );
    assert.deepEqual(
      Object.keys(graph.dependency_index).sort(),
      [
        "node_to_edges",
        "node_to_parent_diagrams",
        "node_to_perspectives",
        "record_hashes",
        "record_to_edges",
        "record_to_nodes",
        "record_to_parent_diagrams",
        "record_to_perspectives",
      ],
    );
    assert.equal(graph.generation_policy.allow_html_labels, false);
    assert.equal(graph.generation_policy.allow_external_urls, false);
    assert.equal(graph.generation_policy.allow_external_images, false);

    const graphPath = join(temporary, "graph.json");
    await writeFile(graphPath, `${JSON.stringify(graph)}\n`, "utf8");
    const validation = spawnSync(
      "uv",
      [
        "run",
        "--no-editable",
        "python",
        "-c",
        [
          "import json, sys",
          "from pathlib import Path",
          "from aet.bundle import validate_bundle",
          "from aet.atlas.validator import validate_evidence_graph",
          "bundle = validate_bundle(Path(sys.argv[1]))",
          "graph = json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))",
          "validate_evidence_graph(graph, bundle)",
        ].join("; "),
        fixture,
        graphPath,
      ],
      {
        cwd: repositoryRoot,
        encoding: "utf8",
        env: {
          ...process.env,
          PYTHONPATH: join(repositoryRoot, "src"),
        },
      },
    );
    assert.equal(
      validation.status,
      0,
      `Python validator rejected the TypeScript Graph:\n${validation.stderr}`,
    );
  } finally {
    await rm(temporary, {
      force: true,
      recursive: true,
    });
  }
});

test("loads a strict standalone Graph and keeps the handle immutable", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "aet-atlas-ts-"));
  try {
    const bundle = await loadBundle(fixture);
    const built = buildEvidenceGraph(bundle);
    const path = join(temporary, "graph.json");
    await writeFile(path, `${JSON.stringify(built)}\n`, "utf8");
    const loaded = await loadEvidenceGraph(path);
    const loadedFromDirectory = await loadEvidenceGraph(temporary);
    assert.equal((await validateEvidenceGraph(loaded)).node_count, built.nodes.length);
    assert.equal(loadedFromDirectory.bundle_id, built.bundle_id);
    assert.equal(Object.isFrozen(loaded.nodes[0]), true);
    assert.throws(() => {
      loaded.nodes[0].status = "supported";
    }, TypeError);
  } finally {
    await rm(temporary, {
      force: true,
      recursive: true,
    });
  }
});

test("fails closed on forged grounding, missing counter-evidence, and budgets", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "aet-atlas-adversarial-"));
  try {
    const bundle = await loadBundle(fixture);
    const built = buildEvidenceGraph(bundle);
    assert.throws(
      () => queryPerspective(built, "claim-chain", { maxNodes: 101 }),
      EvidenceBundleError,
    );
    assert.throws(
      () => getNodeSubgraph(built, "claim-001", { depth: 5 }),
      EvidenceBundleError,
    );
    assert.throws(
      () => queryPerspective(structuredClone(built), "claim-chain"),
      EvidenceBundleError,
    );

    const stale = structuredClone(built);
    const evidence = stale.nodes.find(
      (node) => node.type === "verified_evidence",
    );
    evidence.freshness = "workspace_changed";
    evidence.status = "verified";
    const stalePath = join(temporary, "stale.json");
    await writeFile(stalePath, JSON.stringify(stale), "utf8");
    await assert.rejects(loadEvidenceGraph(stalePath), EvidenceBundleError);

    const counter = structuredClone(built);
    const claim = counter.nodes.find((node) => node.type === "claim");
    claim.status = "conflicted";
    claim.attributes.counter_evidence_refs = ["ev-missing"];
    const counterPath = join(temporary, "counter.json");
    await writeFile(counterPath, JSON.stringify(counter), "utf8");
    await assert.rejects(loadEvidenceGraph(counterPath), EvidenceBundleError);

    const unsafePolicy = structuredClone(built);
    unsafePolicy.generation_policy.allow_external_urls = true;
    const unsafePolicyPath = join(temporary, "unsafe-policy.json");
    await writeFile(unsafePolicyPath, JSON.stringify(unsafePolicy), "utf8");
    await assert.rejects(
      loadEvidenceGraph(unsafePolicyPath),
      EvidenceBundleError,
    );
  } finally {
    await rm(temporary, {
      force: true,
      recursive: true,
    });
  }
});

test("sanitizes untrusted labels without Mermaid links or directives", async () => {
  const temporary = await mkdtemp(join(tmpdir(), "aet-atlas-mermaid-"));
  try {
    const bundle = await loadBundle(fixture);
    const graph = structuredClone(buildEvidenceGraph(bundle));
    graph.nodes.find((node) => node.type === "claim").title =
      '<script>alert(1)</script> %%{init:{}}%% https://evil.invalid/a';
    const path = join(temporary, "malicious.json");
    await writeFile(path, JSON.stringify(graph), "utf8");
    const loaded = await loadEvidenceGraph(path);
    const mermaid = renderMermaid(loaded);
    assert.doesNotMatch(mermaid, /<script|https:\/\/|%%\{|javascript:/iu);
    assert.match(mermaid, /\[external-url-redacted\]/u);
    assert.doesNotMatch(mermaid, /\bclick\b/u);
  } finally {
    await rm(temporary, {
      force: true,
      recursive: true,
    });
  }
});
