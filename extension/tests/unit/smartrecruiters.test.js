// @vitest-environment-options {"url": "https://jobs.smartrecruiters.com/oneclick-ui/company/FintechExample/publication/00000000-test"}
// SmartRecruiters (simulated OneClick form: tests/fixtures/synthetic/smartrecruiters.html). Detection, autofill,
// validation and submission are tested separately. Nothing here talks to SmartRecruiters.
import { beforeEach, describe, expect, it } from "vitest";
import { PROFILE, attachShadows, fakeLayout, fixture, guardSubmit, load } from "./helpers.js";

beforeEach(() => fakeLayout());

const SR = () => fixture("synthetic", "smartrecruiters");
// What the components do in the browser, minimally: an option click sets the autocomplete's value. And jsdom has no
// DataTransfer, so a File list stands in for it (the real attachment is exercised in Chrome by e2e/run_sr_e2e.py).
function componentBehaviour() {
  for (const h of document.querySelectorAll("spl-autocomplete")) {
    const sr = h.shadowRoot; if (!sr) continue;
    for (const o of sr.querySelectorAll("[role=option]")) o.addEventListener("click", () => { sr.querySelector("input").value = o.textContent; });
  }
  globalThis.DataTransfer ??= class { constructor() { this.items = { add: (f) => this._f.push(f) }; this._f = []; } get files() { return this._f; } };
  // jsdom's own setter only takes a real FileList.
  Object.defineProperty(HTMLInputElement.prototype, "files", { configurable: true, get() { return this.__files || []; }, set(v) { this.__files = v; } });
}
function loadSR({ mode = null, allowGeneric = true } = {}) {
  const JP = load(SR());
  attachShadows(document, mode);
  componentBehaviour();
  JP.allowGeneric = allowGeneric;  // the user allowed Smart Apply on this site
  return JP;
}
const deep = (sel) => {
  for (const h of document.querySelectorAll("*")) { const e = h.shadowRoot?.querySelector(sel); if (e) return e; }
  return null;
};

describe("SmartRecruiters detection", () => {
  it("root cause: the generic adapter sees no fields in shadow DOM, the SmartRecruiters adapter does", () => {
    const JP = loadSR();
    // Without the new adapter (the old behaviour): only the generic adapter, which reads the light DOM inside <form>s.
    const generic = JP.adapters.generic;
    expect(generic.isApplicationPage()).toBe(false);
    const census = JP.dom.census();
    expect(census.lightFields).toBe(1);           // the unrelated search box
    expect(census.deepFields).toBeGreaterThan(10); // the application, inside components
    // With it: recognised as an application form, with the job title.
    const d = JP.detect();
    expect(d.platform).toBe("SmartRecruiters");
    expect(d.adapter).toBe("SmartRecruiters");
    expect(d.fields).toBeGreaterThanOrEqual(14);
    expect(d.title).toBe("Data Analyst, Payments Risk");
    expect(d.resumeField).toBe(true);
    expect(d.resumeAttached).toBe(false);
    expect(d.requirements["What is your notice period?"]).toBe("required");
    // Questions sent to JobPilot's answer service: the screening questions, never the identity fields it maps itself.
    expect(d.questions).toEqual(expect.arrayContaining(["What is your notice period?"]));
    expect(d.questions).not.toContain("Confirm your email");
    expect(d.questions).not.toContain("First name");
  });

  it("a form loaded after the page (dynamic rendering) is found once it is on screen", () => {
    const JP = load(`<main><h1>Data Analyst</h1><a href="#">I'm interested</a><div id="app"></div></main>`);
    JP.allowGeneric = true;
    const before = JP.detect();
    expect(before.platform).toBeNull();
    expect(before.census).toMatchObject({ lightFields: 0, deepFields: 0 });
    // The app renders the form later (as OneClick does after "I'm interested").
    const html = SR().replace(/^[\s\S]*<main class="oc-app">/, "").replace(/<\/main>[\s\S]*$/, "");
    document.getElementById("app").innerHTML = html;
    attachShadows();
    const after = JP.detect();
    expect(after.platform).toBe("SmartRecruiters");
    expect(after.fields).toBeGreaterThan(10);
  });

  it("unsupported: a form in components the extension may not read is reported as such (no false 'no form')", () => {
    const JP = loadSR({ mode: "closed" });  // closed shadow roots and no chrome.dom API (outside Chrome)
    const d = JP.detect();
    expect(d.platform).toBeNull();
    expect(d.census.deepFields).toBe(0);
    expect(d.census.opaqueHosts).toBeGreaterThan(5);
  });
});

describe("SmartRecruiters autofill (separately from submission)", () => {
  it("fills identity, confirmation e-mail, dial code, phone, city, links and verified answers; never sensitive or consent", async () => {
    const JP = loadSR();
    const submits = guardSubmit();
    const a = JP.adapters.smartrecruiters;
    const answers = {
      "Will you now or in the future require visa sponsorship to work in India?": { answer: "No", status: "VERIFIED", source: "memory" },
      "What is your notice period?": { answer: "30 days", status: "VERIFIED", source: "memory" },
      "Message to the Hiring Team": { answer: null, status: "NEEDS_INPUT" },
    };
    const fields = { ...PROFILE, phone_country_code: "+91", phone: "9000000000", location: "Bengaluru, Karnataka", website_url: "https://test.example.com", _derived: ["phone_country_code"] };
    const r = await JP.core.fill(a, { fields, answers, coverLetter: "Dear hiring team, …" });
    expect(deep("#first-name-input").value).toBe("Test");
    expect(deep("#last-name-input").value).toBe("Candidate");
    expect(deep("#email-input").value).toBe(PROFILE.email);
    expect(deep("#confirm-email-input").value).toBe(PROFILE.email);   // repeated, not "already filled"
    expect(deep("#phone-country").value).toBe("IN");                    // "+91" -> India (+91), the only option with it
    expect(deep("#phone-number").value).toBe("9000000000");
    expect(deep("#location-input").value).toBe("Bengaluru, Karnataka, India");
    expect(deep("#linkedin-input").value).toBe(PROFILE.linkedin_url);
    expect(deep("#website-input").value).toBe("https://test.example.com");
    expect(deep("#q1").value).toBe("No");
    expect(deep("#q2").value).toBe("30 days");
    expect(deep("#message-input").value).toBe("Dear hiring team, …");  // the prepared cover letter, flagged for review
    expect(r.review.map((i) => i.label)).toEqual(expect.arrayContaining(["Message to the Hiring Team", "Country code"]));
    expect(deep("#q3").value).toBe("");          // gender: never answered by JobPilot
    expect(deep("#privacy").checked).toBe(false); // consent: always the user's tick
    expect(r.skipped.map((i) => i.label)).toContain("Gender");
    expect(r.skipped.map((i) => i.label)).toContain("I agree to the privacy policy");
    expect([...r.filled, ...r.review, ...r.needs, ...r.skipped].map((i) => i.label)).not.toContain("Search jobs");
    expect(submits).toEqual([]);
  });

  it("an ambiguous dial code (+1: US or Canada) is left for the user", async () => {
    const JP = loadSR();
    await JP.core.fill(JP.adapters.smartrecruiters, { fields: { ...PROFILE, phone_country_code: "+1" }, answers: {} });
    expect(deep("#phone-country").value).toBe("");
  });

  it("attaches the chosen resume to the drop zone and verifies it by reading the input back", async () => {
    const JP = loadSR();
    const a = JP.adapters.smartrecruiters;
    const file = { name: "Asha_Rao_Data_Analyst.pdf", type: "application/pdf", b64: btoa("%PDF-1.4 test") };
    const res = await JP.resume.attach(a, { ...file });
    expect(res).toMatchObject({ ok: true, verified: true, name: "Asha_Rao_Data_Analyst.pdf" });
    expect(a.hasResume()).toBe(true);
    // A second attach never silently replaces the file.
    expect(await JP.resume.attach(a, { ...file, name: "Other.pdf" })).toMatchObject({ ok: false, needsConfirm: true });
  });

  it("no resume field: a manual-upload fallback, not a claimed success", async () => {
    const JP = loadSR();
    deep("#resume-input").remove();
    const res = await JP.resume.attach(JP.adapters.smartrecruiters, { name: "r.pdf", type: "application/pdf", b64: btoa("x") });
    expect(res).toMatchObject({ ok: false, manual: true });
  });
});

describe("SmartRecruiters validation and submission (separately)", () => {
  it("required fields left empty block the review; experience/education are reported from the form", async () => {
    const JP = loadSR();
    const a = JP.adapters.smartrecruiters;
    await JP.core.fill(a, { fields: PROFILE, answers: {} });
    const s = JP.review.snapshot(a);
    expect(s.ready).toBe(false);
    expect(s.validation.missing).toEqual(expect.arrayContaining(["What is your notice period?", "Resume"]));
    expect(s.validation.warnings.join(" ")).toMatch(/Experience is empty on the form/);
    // SmartRecruiters fills experience from the attached resume: the review then lists what it shows.
    document.querySelector("#experience .entries").innerHTML = "<li>Senior Data Analyst · Example Corp · 2022 – Present</li>";
    expect(JP.review.snapshot(a).validation.warnings.join(" ")).toMatch(/Experience on the form \(1\): Senior Data Analyst/);
  });

  it("the user's own click on Submit (inside a component) is noticed; confirmation only from SmartRecruiters' message", async () => {
    const JP = loadSR();
    const a = JP.adapters.smartrecruiters;
    const seen = [];
    const stop = JP.submit.watchUserSubmit(a, (how) => seen.push(how));
    const btn = a.submitButton();
    expect(btn?.textContent).toBe("Submit");
    btn.dispatchEvent(new MouseEvent("click", { bubbles: true, composed: true }));  // untrusted: ignored
    expect(seen).toEqual([]);
    stop();
    // No confirmation while the form is on screen; uncertain if nothing changes.
    expect(JP.submit.confirmation(a)).toBeNull();
    expect(await JP.submit.outcome(a, { timeoutMs: 900, step: 100 })).toEqual({ outcome: "uncertain" });
    // The thank-you page replaces the form.
    document.querySelector("main").innerHTML = "<h1>Thank you for applying!</h1><p>Your application has been submitted to Fintech Example Co.</p>";
    expect(await JP.submit.outcome(a, { timeoutMs: 3000, step: 100 })).toMatchObject({ outcome: "confirmed", signal_kind: "adapter" });
  });

  it("the site's validation errors after a submit attempt are reported, not a success", async () => {
    const JP = loadSR();
    const a = JP.adapters.smartrecruiters;
    const box = document.querySelector("spl-input[formcontrolname=email]").shadowRoot;
    box.querySelector("input").setAttribute("aria-invalid", "true");
    box.append(Object.assign(document.createElement("div"), { className: "error-message", textContent: "Please enter a valid email" }));
    const out = await JP.submit.outcome(a, { timeoutMs: 3000, step: 100 });
    expect(out.outcome).toBe("errors");
    expect(out.errors.join(" ")).toMatch(/valid email/);
  });
});

describe("existing platforms are unaffected", () => {
  it("Greenhouse, Lever and Ashby still pick their own adapters", () => {
    for (const [name, host] of [["greenhouse", "job-boards.greenhouse.io"], ["lever", "jobs.lever.co"], ["ashby", "jobs.ashbyhq.com"]]) {
      const JP = load(fixture("synthetic", name));
      expect(JP.adapters.smartrecruiters.matchesHost(host)).toBe(false);
      expect(JP.adapters[name].matchesHost(host)).toBe(true);
    }
  });
});
