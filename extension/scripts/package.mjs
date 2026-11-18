// Build dist/fill-with-jobpilot-<version>.zip: only what the browser needs (manifest, icons, src). No tests,
// no node_modules, no keys. Unzipped, its JobPilot-Smart-Apply folder is what chrome://extensions → Load unpacked loads.
import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const { version } = JSON.parse(readFileSync(join(root, "manifest.json"), "utf8"));
const out = join(root, "dist", `fill-with-jobpilot-${version}.zip`);
mkdirSync(join(root, "dist"), { recursive: true });
rmSync(out, { force: true });
// Everything sits inside ONE folder, so unzipping anywhere gives a folder to pick in "Load unpacked"
// (a zip with loose files at its top made people choose the Downloads folder itself).
const FOLDER = "JobPilot-Smart-Apply";
const stage = join(root, "dist", "stage");
rmSync(stage, { recursive: true, force: true });
for (const item of ["manifest.json", "icons", "src"]) cpSync(join(root, item), join(stage, FOLDER, item), { recursive: true });
execFileSync("zip", ["-r", "-X", "-q", out, FOLDER, "-x", "*.DS_Store"], { cwd: stage, stdio: "inherit" });
rmSync(stage, { recursive: true, force: true });
console.log(out);
console.log(execFileSync("unzip", ["-l", out], { encoding: "utf8" }).trim().split("\n").slice(-1)[0]);
