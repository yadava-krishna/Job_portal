// Apply from JobPilot: which addresses the web app may hand over, and where the form is on each platform.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { APP_ORIGINS, formUrl } from "../../src/lib/config.js";

describe("formUrl", () => {
  it("goes to the form page on Lever and Ashby, and keeps Greenhouse pages as they are", () => {
    expect(formUrl("https://jobs.lever.co/meesho/22c4a7a0-43be")).toBe("https://jobs.lever.co/meesho/22c4a7a0-43be/apply");
    expect(formUrl("https://jobs.lever.co/meesho/22c4a7a0-43be/apply")).toBe("https://jobs.lever.co/meesho/22c4a7a0-43be/apply");
    expect(formUrl("https://jobs.ashbyhq.com/headout/742de92e")).toBe("https://jobs.ashbyhq.com/headout/742de92e/application");
    expect(formUrl("https://job-boards.greenhouse.io/glean/jobs/4702832005?gh_src=x#app")).toBe("https://job-boards.greenhouse.io/glean/jobs/4702832005?gh_src=x");
    expect(formUrl("https://job-boards.greenhouse.io/embed/job_app?for=stripe&token=1")).toBe("https://job-boards.greenhouse.io/embed/job_app?for=stripe&token=1");
  });

  it("refuses every other site, blocked boards, plain http and odd addresses", () => {
    for (const bad of ["https://www.linkedin.com/jobs/view/1", "https://www.naukri.com/job/1", "https://example.com/jobs/1",
                       "http://jobs.lever.co/a/b", "https://user:pw@jobs.lever.co/a/b", "javascript:alert(1)", "", null, 42]) {
      expect(formUrl(bad)).toBeNull();
    }
  });
});

describe("who may message the extension", () => {
  it("only the JobPilot web app, and the manifest agrees with the worker", () => {
    const m = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../manifest.json"), "utf8"));
    const origins = m.externally_connectable.matches.map((p) => new URL(p.replace("/*", "/")).origin);
    expect(new Set(origins)).toEqual(new Set(APP_ORIGINS));
    expect(m.externally_connectable.ids).toBeUndefined();  // no other extension
  });
});
