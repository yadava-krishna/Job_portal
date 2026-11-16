// Smart Apply 2.0: classifier confidence, unknown/missing fields, custom dropdowns, multi-step (Workday-style),
// resume attachment checks, preview from the live form, preview invalidation, submission authorisation,
// confirmation detection, the review panel flow, and unsupported/blocked sites. Local fixtures only; nothing is
// ever sent anywhere.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { platformForUrl } from "../../src/lib/config.js";
import { PROFILE, fakeLayout, fixture, guardSubmit, load } from "./helpers.js";

beforeEach(() => fakeLayout());
const byLabel = (items, l) => items.find((i) => i.label === l);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const GENERIC = `<!doctype html><html><body><main><h1>Senior Analyst</h1>
<form id="apply">
  <label for="e">Email address</label><input id="e" type="email" name="email" required>
  <label for="fn">Given name</label><input id="fn" name="applicant_first" autocomplete="given-name">
  <label for="mix">City</label><input id="mix" name="x" autocomplete="postal-code">
  <label for="c">City</label><input id="c" name="city">
  <label for="pc">Pincode</label><input id="pc" name="pin">
  <input id="nolabel" name="fname">
  <label for="a2">Address line 2</label><input id="a2" name="addr2">
  <label for="why">Why do you want this role?</label><textarea id="why" required></textarea>
  <label for="ctc">Expected CTC</label><input id="ctc" name="ctc">
  <label for="cv">Upload your CV</label><input id="cv" type="file" accept=".pdf,.doc,.docx">
  <button type="submit">Submit</button>
</form></main></body></html>`;

const FIELDS = { ...PROFILE, city: "Bengaluru", postal_code: "560001", _derived: ["city"] };

describe("field classifier (no AI: labels, autocomplete, name/id, placeholder, type)", () => {
  it("combines signals into a confidence and refuses to guess on conflicts", () => {
    const { fieldmap: f } = load("<p></p>");
    expect(f.classifyField({ label: "", autocomplete: "given-name", name: "q7" })).toMatchObject({ key: "first_name", via: ["autocomplete"] });
    const both = f.classifyField({ label: "First name", autocomplete: "given-name" });
    expect(both.key).toBe("first_name");
    expect(both.confidence).toBeGreaterThan(0.95);
    const nameOnly = f.classifyField({ label: "", name: "fname" });
    expect(nameOnly.key).toBe("first_name");
    expect(nameOnly.confidence).toBeLessThan(f.FILL_THRESHOLD);
    const conflict = f.classifyField({ label: "City", autocomplete: "postal-code" });
    expect(conflict.confidence).toBeLessThan(f.FILL_THRESHOLD);
    expect(conflict.conflict).toBeTruthy();
    expect(f.classifyField({ label: "Pincode" }).key).toBe("postal_code");
    expect(f.classifyField({ label: "Country code" }).key).toBe("phone_country_code");
    expect(f.classifyField({ label: "State your reasons for applying" })).toBeNull();  // not the "state" field
    expect(f.classifyField({ label: "Address line 2" })).toBeNull();
    expect(f.classifyField({ label: "", placeholder: "Your gender" }).never).toBe("sensitive");
    expect(f.classifyField({ label: "Year of graduation" }).key).toBe("graduation_year");
  });
});

describe("generic employer form", () => {
  it("fills only confident fields, offers unsure ones, lists unknown and missing ones, never submits", async () => {
    const JP = load(GENERIC);
    JP.allowGeneric = true;
    const submits = guardSubmit();
    const a = JP.core.adapterHere();
    expect(a?.generic).toBe(true);
    const r = await JP.core.fill(a, { fields: FIELDS, answers: { "Expected CTC": { answer: "12 LPA", status: "VERIFIED", source: "verified_facts.expected_ctc" } } });
    const v = (id) => document.getElementById(id).value;
    expect(v("e")).toBe(PROFILE.email);
    expect(v("fn")).toBe("Test");
    expect(v("c")).toBe("Bengaluru");
    expect(byLabel(r.review, "City").note).toMatch(/Suggested/);  // derived from "Bengaluru, Karnataka": review it
    expect(v("pc")).toBe("560001");
    expect(v("mix")).toBe("");  // label says City, code says postal code: not filled
    expect(r.unsure.map((i) => i.ref)).toContain(JP.scan.refFor(document.getElementById("mix")));
    expect(v("nolabel")).toBe("");
    expect(v("a2")).toBe("");
    expect(byLabel(r.needs, "Why do you want this role?")).toBeTruthy();
    expect(byLabel(r.filled, "Expected CTC")).toMatchObject({ value: "12 LPA", confirm: true });
    expect(r.files.map((x) => x.label)).toEqual(["Upload your CV"]);
    expect(submits).toEqual([]);
    // The user accepts the one unsure value explicitly.
    expect(await JP.useProposed(r.unsure.find((i) => i.ref === JP.scan.refFor(document.getElementById("mix"))).ref)).toBe(true);
  });

  it("is never used on a site the user did not allow", () => {
    const JP = load(GENERIC);
    expect(JP.core.adapterHere()).toBeNull();
    expect(JP.detect().platform).toBeNull();
  });
});

describe("blocked and unsupported sites", () => {
  it("never runs on LinkedIn, Naukri or Indeed, and asks permission for other employer sites", () => {
    for (const u of ["https://www.linkedin.com/jobs/view/1/", "https://www.naukri.com/job-listings-x", "https://in.indeed.com/viewjob?jk=1"]) {
      expect(platformForUrl(u)).toMatchObject({ blocked: true });
    }
    expect(platformForUrl("https://acme.wd5.myworkdayjobs.com/en-US/External/job/X/apply")).toMatchObject({ id: "workday", optional: true });
    expect(platformForUrl("https://careers-acme.icims.com/jobs/12/login")).toMatchObject({ name: "iCIMS", optional: true });
    expect(platformForUrl("https://job-boards.greenhouse.io/acme/jobs/1")).toMatchObject({ builtin: true });
    expect(platformForUrl("http://job-boards.greenhouse.io/acme/jobs/1")).toBeNull();
  });
});

describe("review before submission (read from the live form)", () => {
  async function filledLever() {
    const JP = load(fixture("synthetic", "lever"));
    const answers = {
      "Total Years of experience": { answer: "6.5 years", status: "SUGGESTED" },
      "What is your notice period?": { answer: "30 days", status: "VERIFIED", source: "verified_facts.notice_period" },
      "Expected CTC (LPA)": { answer: "9 LPA", status: "VERIFIED", source: "verified_facts.expected_ctc" },
    };
    await JP.core.fill(JP.adapters.lever, { fields: PROFILE, answers });
    return JP;
  }

  it("shows values, sources, sensitive answers to tick, documents and what is missing", async () => {
    const JP = await filledLever();
    document.querySelector('[name="email"]').value = "typed@example.com";
    const s = JP.review.snapshot(JP.adapters.lever, { job: { title: "AR Analyst", company: "Acme", location: "Bengaluru" } });
    expect(s.job).toMatchObject({ title: "AR Analyst", company: "Acme" });
    const email = byLabel(s.personal, "Email");
    expect(email.value).toBe("typed@example.com");  // the live value, not what JobPilot wrote
    expect(email).toMatchObject({ sourceKind: "user", source: "You changed this" });
    expect(byLabel(s.personal, "Full name").source).toMatch(/JobPilot, from your JobPilot profile/);
    const notice = byLabel(s.screening, "What is your notice period?");
    expect(notice).toMatchObject({ value: "16 to 30 days", confirm: true, confirmed: false });
    expect(s.validation.confirm).toContain("What is your notice period?");
    expect(byLabel(s.screening, "Please select your gender").manual).toBe(true);
    expect(s.documents.map((d) => [d.label, d.attached])).toEqual([["Resume/CV", false]]);
    expect(s.validation.missing).toEqual([]);  // every required question has an answer now
    expect(s.ready).toBe(true);
    // Clearing a required answer shows up at once.
    document.querySelector('[name="cards[c1][field3]"]').value = "";
    const s2 = JP.review.snapshot(JP.adapters.lever);
    expect(s2.validation.missing).toContain("Expected CTC (LPA)");
    expect(s2.ready).toBe(false);
  });

  it("changes its fingerprint when anything on the form changes, and the watcher reports it", async () => {
    const JP = await filledLever();
    const a = JP.adapters.lever;
    const before = JP.review.snapshot(a).fingerprint;
    expect(JP.review.snapshot(a).fingerprint).toBe(before);  // stable when nothing changed
    const stale = vi.fn();
    const stop = JP.review.watch(a, before, stale);
    const org = document.querySelector('[name="org"]');
    org.value = "Another Co";
    org.dispatchEvent(new Event("input", { bubbles: true }));
    await wait(400);
    expect(stale).toHaveBeenCalledTimes(1);
    expect(JP.review.snapshot(a).fingerprint).not.toBe(before);
    stop();
  });
});

describe("submission authorisation and confirmation", () => {
  async function readyGreenhouse() {
    const JP = load(fixture("synthetic", "greenhouse"));
    const loc = document.getElementById("candidate-location");
    loc.addEventListener("input", () => { document.getElementById("loc-list").innerHTML = loc.value ? '<div role="option">Bengaluru, Karnataka, India</div>' : ""; });
    await JP.core.fill(JP.adapters.greenhouse, { fields: PROFILE, answers: { "What is your notice period?": { answer: "30 days", status: "VERIFIED", source: "verified_facts.notice_period" } } });
    return JP;
  }

  it("clicks submit once, only with a fresh trusted authorisation matching the reviewed form", async () => {
    const JP = await readyGreenhouse();
    const a = JP.adapters.greenhouse;
    const btn = document.querySelector("button[type=submit]");
    const clicks = [];
    btn.addEventListener("click", (e) => { clicks.push(1); e.preventDefault(); });

    expect(JP.submit.clickSubmit(a)).toMatchObject({ ok: false, reason: expect.stringMatching(/not authorised/) });
    expect(JP.submit.authorize("x", false)).toBe(false);  // an untrusted click never authorises

    let s = JP.review.snapshot(a);
    expect(s.ready).toBe(true);
    expect(s.validation.confirm).toEqual(["What is your notice period?"]);
    JP.submit.authorize(s.fingerprint, true);
    expect(JP.submit.clickSubmit(a).reason).toMatch(/Tick the answers/);  // sensitive answer not ticked yet

    const ref = byLabel(s.screening, "What is your notice period?").ref;
    JP.review.setConfirmed(ref, true);
    s = JP.review.snapshot(a);
    JP.submit.authorize(s.fingerprint, true);
    document.getElementById("last_name").value = "Changed";  // the form changes after the review
    expect(JP.submit.clickSubmit(a)).toMatchObject({ ok: false, stale: true });

    s = JP.review.snapshot(a);
    JP.submit.authorize(s.fingerprint, true);
    expect(JP.submit.clickSubmit(a)).toEqual({ ok: true });
    expect(JP.submit.clickSubmit(a).ok).toBe(false);  // one authorisation buys one click
    expect(clicks).toEqual([1]);
  }, 30000);

  it("reports confirmed only on a confirmation signal, errors when the site refuses, and uncertain otherwise", async () => {
    const JP = await readyGreenhouse();
    const a = JP.adapters.greenhouse;
    setTimeout(() => { document.body.innerHTML = '<main><h1>Thank you for applying!</h1><p>We will be in touch.</p></main>'; }, 300);
    expect(await JP.submit.outcome(a, { timeoutMs: 3000, step: 100 })).toMatchObject({ outcome: "confirmed" });

    const JP2 = await readyGreenhouse();
    const email = document.getElementById("email");
    email.setAttribute("aria-invalid", "true");
    expect(await JP2.submit.outcome(JP2.adapters.greenhouse, { timeoutMs: 3000, step: 100 })).toMatchObject({ outcome: "errors" });

    const JP3 = await readyGreenhouse();
    expect(await JP3.submit.outcome(JP3.adapters.greenhouse, { timeoutMs: 900, step: 100 })).toEqual({ outcome: "uncertain" });
  }, 60000);

  it("never offers assisted submission on Workday or generic sites", () => {
    const JP = load(GENERIC);
    JP.allowGeneric = true;
    const a = JP.core.adapterHere();
    JP.submit.authorize(JP.review.snapshot(a).fingerprint, true);
    expect(JP.submit.clickSubmit(a).reason).toMatch(/not available/);
  });
});

describe("resume attachment checks", () => {
  it("refuses file types the form does not accept and asks before replacing", async () => {
    const JP = load(GENERIC);
    JP.allowGeneric = true;
    const a = JP.core.adapterHere();
    const input = document.getElementById("cv");
    expect(JP.resume.accepts(input, "cv.pdf", "application/pdf")).toBe(true);
    expect(JP.resume.accepts(input, "cv.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")).toBe(true);
    input.setAttribute("accept", ".pdf");
    const r = await JP.resume.attach(a, { name: "cv.docx", type: "", b64: btoa("PK") });
    expect(r).toMatchObject({ ok: false, manual: true });
    expect(r.reason).toMatch(/does not accept Word/);
    a.hasResume = () => true;
    expect(await JP.resume.attach(a, { name: "cv.pdf", type: "application/pdf", b64: btoa("%PDF") })).toMatchObject({ needsConfirm: true });
  });

  it("never claims success when the page did not take the file", async () => {
    const JP = load(GENERIC);
    JP.allowGeneric = true;
    const a = JP.core.adapterHere();
    // jsdom cannot hold a File in an <input type=file>: the attempt must end in an honest manual hand-off.
    const r = await JP.resume.attach(a, { name: "cv.pdf", type: "application/pdf", b64: btoa("%PDF-1.7") });
    expect(r.ok).toBe(false);
    expect(r.manual).toBe(true);
  }, 10000);
});

describe("Workday-style multi-step form", () => {
  const STEP1 = `<main><div data-automation-id="applyFlowPage">
    <ol data-automation-id="progressBar"><li data-automation-id="progressBarActiveStep">current step 1 of 3 My Information</li><li>My Experience</li><li>Review</li></ol>
    <div data-automation-id="formField-legalName--firstName"><label for="wf">First Name*</label><input id="wf" data-automation-id="legalNameSection_firstName" required></div>
    <div data-automation-id="formField-legalName--lastName"><label for="wl">Last Name*</label><input id="wl" data-automation-id="legalNameSection_lastName" required></div>
    <div data-automation-id="formField-email"><label for="we">Email Address</label><input id="we" data-automation-id="email"></div>
    <div data-automation-id="formField-source"><label for="src">How Did You Hear About Us?</label>
      <button id="src" type="button" aria-haspopup="listbox" aria-controls="src-list">Select One</button>
      <div id="src-list" role="listbox"></div></div>
    <div data-automation-id="formField-country"><label for="ctry">Country</label>
      <button id="ctry" type="button" aria-haspopup="listbox" aria-controls="ctry-list">Select One</button>
      <div id="ctry-list" role="listbox"></div></div>
    <button type="button" data-automation-id="bottom-navigation-next-button">Save and Continue</button>
  </div></main>`;

  it("detects the step, fills it (including button dropdowns), and notices the next step", async () => {
    const JP = load(STEP1);
    const a = JP.adapters.workday;
    a.matchesHost = () => true;  // jsdom runs on localhost
    expect(JP.core.adapterHere()).toBe(a);
    expect(a.step()).toMatchObject({ title: "My Information", index: 1, total: 3, final: false });
    const ctry = document.getElementById("ctry");
    ctry.addEventListener("click", () => { document.getElementById("ctry-list").innerHTML = '<div role="option">India</div><div role="option">Indonesia</div>'; });
    ctry.addEventListener("click", () => {}, { once: true });
    document.getElementById("ctry-list").addEventListener("click", (e) => { ctry.textContent = e.target.textContent; });
    const stepped = vi.fn();
    JP.panel.stepChanged = stepped;
    const r = await JP.core.fill(a, { fields: { ...PROFILE, country: "India" }, answers: {} });
    expect(document.getElementById("wf").value).toBe("Test");
    expect(document.getElementById("wl").value).toBe("Candidate");
    expect(document.getElementById("we").value).toBe(PROFILE.email);
    expect(ctry.textContent).toBe("India");
    expect(byLabel(r.needs, "How Did You Hear About Us?")).toBeTruthy();
    expect(JP.detect().assistedSubmit).toBe(false);
    // The user clicks Workday's own "Save and Continue": the page shows step 2.
    document.querySelector("[data-automation-id='progressBarActiveStep']").textContent = "current step 2 of 3 My Experience";
    await wait(900);
    expect(stepped).toHaveBeenCalledWith(expect.objectContaining({ title: "My Experience", index: 1 }));
  }, 20000);
});

describe("review panel flow (assisted submission on Greenhouse)", () => {
  it("records reviewed → authorised → pending → confirmed, and nothing is submitted before the user's click", async () => {
    const JP = load(fixture("synthetic", "greenhouse"));
    JP.__testing = true;
    JP.__outcomeTimeout = 3000;
    const sent = [];
    JP.bridge = { send: vi.fn(async (action, args) => { sent.push([action, args?.state || args?.outcome || null]); return { ok: true, data: {} }; }) };
    JP.context = { applicationId: 7, job: { title: "AR Analyst", company: "Acme" } };
    JP.adapters.greenhouse.matchesHost = () => true;  // jsdom runs on localhost
    const loc = document.getElementById("candidate-location");
    loc.addEventListener("input", () => { document.getElementById("loc-list").innerHTML = loc.value ? '<div role="option">Bengaluru, Karnataka, India</div>' : ""; });
    const btn = document.querySelector("button[type=submit]");
    let submitted = 0;
    btn.addEventListener("click", (e) => { e.preventDefault(); submitted++; setTimeout(() => { document.body.innerHTML = "<main><h1>Thank you for applying</h1></main>"; }, 100); });

    await JP.fill({ fields: PROFILE, answers: { "What is your notice period?": { answer: "30 days", status: "VERIFIED", source: "verified_facts.notice_period" } } });
    const root = JP.__panelRoot;
    const button = (text) => [...root.querySelectorAll("button")].find((b) => b.textContent.trim().startsWith(text));
    [...root.querySelectorAll("[role=tab]")].find((t) => t.textContent === "Review").click();
    expect(button("I have reviewed").disabled).toBe(true);  // the notice period commits the user: tick it first
    expect(button("Submit this application").disabled).toBe(true);
    root.querySelector("input[type=checkbox]").click();
    await wait(20);
    expect(submitted).toBe(0);

    button("I have reviewed").click();
    await wait(50);
    expect(button("Submit this application").disabled).toBe(false);
    button("Submit this application").click();
    await wait(1800);
    expect(submitted).toBe(1);
    expect(sent.filter(([a]) => a === "state").map(([, s]) => s)).toEqual(["reviewed", "submission_authorized", "submission_pending"]);
    expect(sent.find(([a]) => a === "outcome")).toEqual(["outcome", "confirmed"]);
  }, 30000);
});
