import { mkdir, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const output = join(root, "dist");

await rm(output, { force: true, recursive: true });
await mkdir(output, { recursive: true });
await writeFile(
  join(output, "index.js"),
  "// This package exports TypeScript protocol declarations only.\n",
  "utf8",
);
