// Shared constants. Imported by the service worker and the popup (extension pages only, never by content scripts).

// Where the JobPilot web app publishes the current backend address (the ngrok URL can change on restart).
export const DEFAULT_CONFIG_URL = "https://yadava-krishna.github.io/Job_portal/config.json";

// Application pages the extension may fill.
//  * builtin: allowed at install (host_permissions); Greenhouse, Lever and Ashby, with assisted submission.
//  * optional: other employer application systems. Chrome asks the user to allow each site once (optional host
//    permission, requested only from the popup after a click); autofill and review only.
//  * blocked: sites whose terms forbid browser automation. Nothing is ever injected there; the popup offers a manual
//    hand-off (copy your details, download your resume, record the application in JobPilot).
export const PLATFORMS = [
  { id: "greenhouse", name: "Greenhouse", builtin: true, hosts: ["job-boards.greenhouse.io", "boards.greenhouse.io", "job-boards.eu.greenhouse.io", "boards.eu.greenhouse.io"] },
  { id: "lever", name: "Lever", builtin: true, hosts: ["jobs.lever.co", "jobs.eu.lever.co"] },
  { id: "ashby", name: "Ashby", builtin: true, hosts: ["jobs.ashbyhq.com"] },
];
export const OPTIONAL_PLATFORMS = [
  { id: "workday", name: "Workday", re: /(^|\.)(myworkdayjobs\.com|myworkdaysite\.com)$/ },
  { id: "generic", name: "SmartRecruiters", re: /(^|\.)smartrecruiters\.com$/ },
  { id: "generic", name: "iCIMS", re: /(^|\.)icims\.com$/ },
  { id: "generic", name: "SAP SuccessFactors", re: /(^|\.)(successfactors\.(com|eu)|sapsf\.(com|eu|cn))$/ },
  { id: "generic", name: "Oracle Taleo", re: /(^|\.)taleo\.net$/ },
  { id: "generic", name: "Oracle Recruiting", re: /(^|\.)oraclecloud\.com$/ },
  { id: "generic", name: "Zoho Recruit", re: /(^|\.)zohorecruit\.(com|in|eu)$/ },
  { id: "generic", name: "Freshteam", re: /(^|\.)freshteam\.com$/ },
  { id: "generic", name: "Darwinbox", re: /(^|\.)darwinbox\.(in|com)$/ },
];
export const BLOCKED = [
  { name: "LinkedIn", re: /(^|\.)linkedin\.com$/, why: "LinkedIn's rules forbid browser extensions that automate activity on its site, including Easy Apply." },
  { name: "Naukri", re: /(^|\.)naukri(gulf)?\.com$/, why: "Naukri's terms forbid automated tools and browser extensions on its site." },
  { name: "Indeed", re: /(^|\.)indeed\.(com|co\.in|co\.uk|ca|de|fr|com\.au)$/, why: "Indeed's terms forbid bots and automating Indeed Apply." },
];

/** {id, name, builtin|optional|blocked, ...} for an https page, or null (not a web page JobPilot can help with). */
export function platformForUrl(url) {
  let u;
  try { u = new URL(url); } catch { return null; }
  if (u.protocol !== "https:") return null;
  const host = u.hostname;
  const blocked = BLOCKED.find((b) => b.re.test(host));
  if (blocked) return { id: "blocked", name: blocked.name, blocked: true, why: blocked.why };
  const builtin = PLATFORMS.find((p) => p.hosts.includes(host));
  if (builtin) return builtin;
  const opt = OPTIONAL_PLATFORMS.find((p) => p.re.test(host));
  return { id: opt?.id || "generic", name: opt?.name || "Employer site", optional: true, known: Boolean(opt), origin: `${u.origin}/*` };
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
  "src/content/dom.js",
  "src/content/fieldmap.js",
  "src/content/scan.js",
  "src/content/fill.js",
  "src/content/resume.js",
  "src/content/review.js",
  "src/content/submit.js",
  "src/content/core.js",
  "src/content/adapters/greenhouse.js",
  "src/content/adapters/lever.js",
  "src/content/adapters/ashby.js",
  "src/content/adapters/workday.js",
  "src/content/adapters/generic.js",
  "src/content/panel.js",
];

// The JobPilot web app may ask the extension (externally_connectable) to check that it is connected, and to open
// one job's application form and fill it. Nothing else; it never receives profile data back.
export const APP_ORIGINS = ["https://yadava-krishna.github.io", "http://localhost:3080", "http://127.0.0.1:3080"];

/** The application-form address for a listing on Greenhouse, Lever or Ashby (Lever and Ashby keep the form on a
 *  sub-page of the posting), or null for any other site. */
export function formUrl(value) {
  let u;
  try { u = new URL(String(value || "")); } catch { return null; }
  const p = platformForUrl(u.href);
  if (!p?.builtin || u.username || u.password) return null;
  u.hash = "";
  const parts = u.pathname.split("/").filter(Boolean);
  if (p.id === "lever" && parts.length === 2) u.pathname = `/${parts.join("/")}/apply`;
  if (p.id === "ashby" && parts.length === 2) u.pathname = `/${parts.join("/")}/application`;
  return u.toString();
}
