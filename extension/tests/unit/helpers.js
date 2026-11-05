import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SCRIPTS = ["fieldmap.js", "core.js", "adapters/greenhouse.js", "adapters/lever.js", "adapters/ashby.js", "panel.js"];

/** Load a form into the jsdom document and (re)inject the content scripts, as the service worker would. */
export function load(html) {
  document.documentElement.innerHTML = html.replace(/^<!doctype html>/i, "");
  delete globalThis.__jobpilot;
  for (const f of SCRIPTS) (0, eval)(readFileSync(join(ROOT, "src", "content", f), "utf8"));
  return globalThis.__jobpilot;
}

export const fixture = (kind, name) => {
  const p = join(ROOT, "tests", "fixtures", kind, `${name}.html`);
  return existsSync(p) ? readFileSync(p, "utf8") : null;
};

// jsdom has no layout: every element reports a 0×0 box. Give elements a size unless they are display:none.
export function fakeLayout() {
  Element.prototype.getBoundingClientRect = function () {
    return getComputedStyle(this).display === "none" ? { width: 0, height: 0, top: 0, left: 0 } : { width: 120, height: 24, top: 0, left: 0 };
  };
}

/** Fail the test if anything tries to submit. */
export function guardSubmit() {
  const calls = [];
  document.addEventListener("submit", (e) => { calls.push("submit event"); e.preventDefault(); }, true);
  HTMLFormElement.prototype.submit = () => calls.push("form.submit()");
  HTMLFormElement.prototype.requestSubmit = () => calls.push("form.requestSubmit()");
  for (const b of document.querySelectorAll("button[type=submit], button:not([type])")) b.addEventListener("click", () => calls.push("submit button click"));
  return calls;
}

export const PROFILE = {
  full_name: "Test Candidate", first_name: "Test", last_name: "Candidate", email: "test.candidate@example.com", phone: "+91 9000000000",
  location: "Bengaluru, Karnataka", current_company: "Example Corp", current_title: "AR Analyst", linkedin_url: "https://www.linkedin.com/in/test-candidate",
  github_url: "https://github.com/test-candidate", school: "Example University", degree: "B.Com", total_experience_years: 6.5,
};
