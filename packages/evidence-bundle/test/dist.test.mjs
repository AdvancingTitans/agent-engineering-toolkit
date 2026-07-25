import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  loadBundle,
  queryClaims,
  validateBundle,
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
});
