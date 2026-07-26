import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  buildEvidenceGraph,
  loadBundle,
  queryClaims,
  renderMermaid,
  traceClaimSupport,
  validateBundle,
  validateEvidenceGraph,
} from "../dist/index.js";

const fixture = fileURLToPath(
  new URL(
    "../../../tests/fixtures/evidence-bundles/minimal/",
    import.meta.url,
  ),
);

test("checked JavaScript distribution is directly consumable", async () => {
  const bundle = await loadBundle(fixture);
  assert.equal((await validateBundle(bundle)).status, "PASS");
  assert.deepEqual(
    queryClaims(bundle, { status: "supported" }).map((item) => item.id),
    ["claim-001"],
  );
  const graph = buildEvidenceGraph(bundle);
  assert.equal((await validateEvidenceGraph(graph)).perspective_count, 8);
  assert.equal(traceClaimSupport(graph, "claim-001").claim_status, "supported");
  assert.match(renderMermaid(graph), /^flowchart LR\n/u);
});
