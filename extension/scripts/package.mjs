// Build dist/fill-with-jobpilot-<version>.zip: only what the browser needs (manifest, icons, src). No tests,
// no node_modules, no keys. Unzipped, it is one folder with manifest.json inside: what chrome://extensions → Load unpacked loads.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const { version } = JSON.parse(readFileSync(join(root, "manifest.json"), "utf8"));
const out = join(root, "dist", `fill-with-jobpilot-${version}.zip`);
mkdirSync(join(root, "dist"), { recursive: true });
rmSync(out, { force: true });
// Files at the top of the zip (no folder inside it). Every unzip tool (Ubuntu "Extract Here", Windows "Extract All",
// macOS) then makes ONE folder named after the zip with manifest.json directly in it: the folder to pick in
// "Load unpacked". A folder inside the zip ends up nested twice on Ubuntu ("Manifest file is missing").
execFileSync("zip", ["-r", "-X", "-q", out, "manifest.json", "icons", "src", "-x", "*.DS_Store"], { cwd: root, stdio: "inherit" });
console.log(out);
console.log(execFileSync("unzip", ["-l", out], { encoding: "utf8" }).trim().split("\n").slice(-1)[0]);
