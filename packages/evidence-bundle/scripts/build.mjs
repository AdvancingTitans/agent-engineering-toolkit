import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const runtime = join(root, "runtime");
const output = join(root, "dist");

await rm(output, { force: true, recursive: true });
await mkdir(output, { recursive: true });
await cp(runtime, output, { recursive: true });
