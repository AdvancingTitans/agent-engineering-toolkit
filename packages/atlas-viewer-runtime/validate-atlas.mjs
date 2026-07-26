import { lstat, readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { parseMermaid } from "./parser.mjs";

const MAX_DIAGRAMS = 128;
const MAX_BYTES = 1024 * 1024;
const input = process.argv[2];
if (!input) {
  throw new Error("usage: node validate-atlas.mjs <atlas-sidecar>");
}
const root = resolve(input);
const rootStatus = await lstat(root);
if (!rootStatus.isDirectory() || rootStatus.isSymbolicLink()) {
  throw new Error("Atlas path must be a regular directory");
}

const diagrams = [];
async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isSymbolicLink()) {
      throw new Error(`Atlas parser gate rejects symbolic links: ${path}`);
    }
    if (entry.isDirectory()) {
      await walk(path);
    } else if (entry.isFile() && entry.name === "diagram.mmd") {
      diagrams.push(path);
      if (diagrams.length > MAX_DIAGRAMS) {
        throw new Error(`Atlas exceeds the ${MAX_DIAGRAMS}-diagram parser budget`);
      }
    }
  }
}
await walk(root);
if (diagrams.length === 0) {
  throw new Error("Atlas contains no diagram.mmd files");
}
for (const path of diagrams.sort()) {
  const status = await lstat(path);
  if (status.size > MAX_BYTES) {
    throw new Error(`Mermaid diagram exceeds ${MAX_BYTES} bytes: ${path}`);
  }
  await parseMermaid(await readFile(path, "utf8"));
}
process.stdout.write(
  `PASS Mermaid 11.16.0 parsed ${diagrams.length}/${diagrams.length} Atlas diagrams\n`,
);
