import { spawnSync } from "node:child_process";
import { readFile, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const packageData = JSON.parse(
  await readFile(join(root, "package.json"), "utf8"),
);
if (packageData.private === true || packageData.engines?.node !== ">=20") {
  throw new Error("package must be publishable with engines.node >=20");
}
const runtimeFiles = (await readdir(join(root, "runtime")))
  .filter((name) => name.endsWith(".js"))
  .sort();
const distFiles = (await readdir(join(root, "dist")))
  .filter((name) => name.endsWith(".js"))
  .sort();
if (JSON.stringify(runtimeFiles) !== JSON.stringify(distFiles)) {
  throw new Error("dist file set does not match runtime");
}
for (const name of runtimeFiles) {
  const runtime = await readFile(join(root, "runtime", name));
  const dist = await readFile(join(root, "dist", name));
  if (!runtime.equals(dist)) {
    throw new Error(`dist is stale: ${name}`);
  }
  const source = runtime.toString("utf8");
  for (const prohibited of [
    "stripTypeScriptTypes",
    'from "node:module"',
    '.ts"',
  ]) {
    if (source.includes(prohibited)) {
      throw new Error(`Node 20 incompatible runtime token in ${name}`);
    }
  }
  const check = spawnSync(process.execPath, ["--check", join(root, "runtime", name)]);
  if (check.status !== 0) {
    throw new Error(`runtime syntax check failed: ${name}`);
  }
}
