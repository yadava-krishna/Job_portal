import { afterEach, describe, expect, it, vi } from "vitest";
import { bookmarkletHref, decodeClip } from "@/lib/clipper";
import { normalizeBaseUrl } from "@/lib/config";

/** Run the generated bookmarklet against a fake job page and return what it would send to the portal. */
function runBookmarklet(html: string, url: string) {
  document.body.innerHTML = html;
  window.history.replaceState({}, "", url.replace(/^https?:\/\/[^/]+/, ""));
  Object.defineProperty(window, "location", { value: new URL(url), configurable: true, writable: true });
  const opened: string[] = [];
  vi.stubGlobal("open", (u: string) => { opened.push(u); return {} as Window; });
  const code = decodeURIComponent(bookmarkletHref("https://portal.example/app/").slice("javascript:".length));
  // eslint-disable-next-line no-new-func
  new Function(code)();
  expect(opened).toHaveLength(1);
  expect(opened[0].startsWith("https://portal.example/app/#/clip?d=")).toBe(true);
  return decodeClip(new URL(opened[0].replace("#/clip?", "?")).searchParams.get("d"));
}

describe("browser clipper", () => {
  afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = ""; });

  it("captures a LinkedIn job page with a canonical URL and relative posting date", () => {
    const job = runBookmarklet(`
      <div class="job-details-jobs-unified-top-card__job-title"><h1>Financial Analyst</h1></div>
      <div class="job-details-jobs-unified-top-card__company-name"><a>Acme Health</a></div>
      <div class="job-details-jobs-unified-top-card__primary-description-container">Bengaluru, Karnataka, India · 2 days ago · 40 applicants</div>
      <div id="job-details">We need FP&amp;A experience. Prepare monthly MIS reports in Excel.</div>`,
      "https://www.linkedin.com/jobs/search/?currentJobId=4012345678&keywords=fpa");
    expect(job).toMatchObject({
      url: "https://www.linkedin.com/jobs/view/4012345678/", title: "Financial Analyst", company: "Acme Health",
      location: "Bengaluru, Karnataka, India", posted_date: "2 days ago", posted_date_source: "page",
    });
    expect(job?.description).toContain("FP&A experience");
  });

  it("prefers schema.org JobPosting data when the page publishes it (Indeed)", () => {
    const ld = { "@type": "JobPosting", title: "Revenue Analyst", hiringOrganization: { name: "Globex" }, datePosted: "2026-11-03T10:00:00Z",
                 jobLocation: { address: { addressLocality: "Bengaluru", addressRegion: "KA" } }, description: "<p>Revenue <b>analysis</b> role</p><img src=x onerror=alert(1)>" };
    const job = runBookmarklet(`<script type="application/ld+json">${JSON.stringify(ld)}</script><div id="jobDescriptionText">Revenue analysis role with full details.</div>`,
      "https://in.indeed.com/viewjob?jk=0123456789ABCDEF&from=serp");
    expect(job).toMatchObject({ url: "https://in.indeed.com/viewjob?jk=0123456789abcdef", title: "Revenue Analyst", company: "Globex",
                                location: "Bengaluru, KA", posted_date: "2026-11-03", posted_date_source: "page" });
    expect(job?.description).toContain("full details");
  });

  it("handles Naukri pages and unicode text", () => {
    const job = runBookmarklet(`
      <h1 class="styles_jd-header-title__x">MIS Analyst – Finance</h1>
      <div class="styles_jd-header-comp-name__y"><a>Initech Pvt Ltd</a></div>
      <div class="styles_jhc__location__z">Bengaluru</div><div class="styles_jhc__exp__a">3 - 6 Yrs</div><div class="styles_jhc__salary__b">₹ 6-9 Lacs P.A.</div>
      <span class="styles_jhc__stat__c">Posted: 1 day ago</span>
      <section class="styles_job-desc-container__d">Prepare MIS reports. ₹ budgets.</section>`,
      "https://www.naukri.com/job-listings-mis-analyst-initech-bengaluru-3-to-6-years-031125012345");
    expect(job).toMatchObject({ title: "MIS Analyst – Finance", company: "Initech Pvt Ltd", experience: "3 - 6 Yrs", salary: "₹ 6-9 Lacs P.A.", posted_date: "1 day ago" });
    expect(job?.description).toContain("₹ budgets");
  });

  it("rejects malformed clip payloads", () => {
    expect(decodeClip("%%%not-base64")).toBeNull();
    expect(decodeClip(null)).toBeNull();
  });
});

describe("backend URL normalisation", () => {
  it.each([
    ["https://abc.ngrok-free.app/", "https://abc.ngrok-free.app"],
    ["https://abc.ngrok-free.app/api/v1", "https://abc.ngrok-free.app"],
    ["javascript:alert(1)", null],
    ["not a url", null],
  ])("%s", (input, expected) => expect(normalizeBaseUrl(input)).toBe(expected));
});
