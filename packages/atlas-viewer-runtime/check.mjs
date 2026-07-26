import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parseMermaid } from "./parser.mjs";

const runtime = await readFile(
  resolve(import.meta.dirname, "../../src/aet/atlas/assets/mermaid.min.js"),
  "utf8",
);
if (!runtime.includes("Mermaid 11.16.0") || !runtime.includes("globalThis.mermaid")) {
  throw new Error("offline Mermaid runtime is missing its pinned identity");
}
if (/sourceMappingURL/u.test(runtime)) {
  throw new Error("offline Mermaid runtime must not depend on an external source map");
}

const generatedExample = await readFile(
  resolve(
    import.meta.dirname,
    "../../examples/evidence-atlas/aet-self-review-claim-chain.mmd",
  ),
  "utf8",
);
const fixtures = [
  generatedExample,
  "sequenceDiagram\n  participant A\n  participant B\n  A->>B: grounded event\n",
  "timeline\n  title Freshness history\n  2026-01-01 : proof created\n",
  "stateDiagram-v2\n  [*] --> current\n  current --> stale\n",
];
for (const source of fixtures) {
  await parseMermaid(source);
}
for (const invalid of [
  'flowchart LR\n A["unterminated',
  "sequenceDiagram\n participant",
  "timeline\n Step :",
]) {
  try {
    await parseMermaid(invalid);
  } catch {
    continue;
  }
  throw new Error(`Mermaid 11.16.0 accepted invalid syntax: ${invalid}`);
}
