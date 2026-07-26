import { build } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const output = resolve(here, "../../src/aet/atlas/assets");
await mkdir(output, { recursive: true });
await build({
  entryPoints: [resolve(here, "entry.mjs")],
  outfile: resolve(output, "mermaid.min.js"),
  bundle: true,
  minify: true,
  format: "iife",
  platform: "browser",
  target: ["chrome120", "firefox121", "safari17"],
  legalComments: "none",
  banner: {
    js: "/*! Mermaid 11.16.0 | MIT License | vendored for offline AET Viewer */",
  },
});
await copyFile(
  resolve(here, "node_modules/mermaid/LICENSE"),
  resolve(output, "MERMAID-LICENSE"),
);
