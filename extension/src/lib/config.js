// Shared constants. Imported by the service worker and the popup (extension pages only, never by content scripts).

// Where the JobPilot web app publishes the current backend address (the ngrok URL can change on restart).
export const DEFAULT_CONFIG_URL = "https://yadava-krishna.github.io/Job_portal/config.json";

// Application pages the extension may fill. Anything else is "unsupported", and nothing runs there.
export const PLATFORMS = [
  { id: "greenhouse", name: "Greenhouse", hosts: ["job-boards.greenhouse.io", "boards.greenhouse.io", "job-boards.eu.greenhouse.io", "boards.eu.greenhouse.io"] },
  { id: "lever", name: "Lever", hosts: ["jobs.lever.co", "jobs.eu.lever.co"] },
  { id: "ashby", name: "Ashby", hosts: ["jobs.ashbyhq.com"] },
];

export function platformForUrl(url) {
  let u;
  try { u = new URL(url); } catch { return null; }
  if (u.protocol !== "https:") return null;
  return PLATFORMS.find((p) => p.hosts.includes(u.hostname)) ?? null;
}

// A backend address must be https, except a local development backend on this machine.
export function validApiBase(value) {
  let u;
  try { u = new URL(String(value || "").trim()); } catch { return null; }
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(u.hostname);
  if (u.protocol !== "https:" && !(local && u.protocol === "http:")) return null;
  if (u.username || u.password || u.search || u.hash) return null;
  return u.origin + u.pathname.replace(/\/+$/, "");
}

export const API_PREFIX = "/api/v1";
// Rotate the device credential once a month; the server keeps the old one valid for 2 minutes.
export const ROTATE_AFTER_MS = 30 * 24 * 3600 * 1000;

// Content scripts injected (in this order) into allow-listed application frames, only after a click.
export const CONTENT_FILES = [
  "src/content/fieldmap.js",
  "src/content/core.js",
  "src/content/adapters/greenhouse.js",
  "src/content/adapters/lever.js",
  "src/content/adapters/ashby.js",
  "src/content/panel.js",
];
