// Content scripts: answers in context (stale, never, confirm), date pickers, the prepared cover letter, which
// confirmation signal matched, and "Save answers for next time" in the review panel (only what the user ticks, never
// sensitive, consent, password or file fields).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PROFILE, fakeLayout, fixture, guardSubmit, load } from "./helpers.js";

beforeEach(() => fakeLayout());
afterEach(() => history.replaceState({}, "", "/"));
const byLabel = (items, l) => items.find((i) => i.label === l);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const FORM = `<main><h1>Analyst</h1><form>
  <label for="em">Email</label><input id="em" type="email" name="email">
  <label for="fn">First name</label><input id="fn" name="first_name">
  <label for="why">Why do you want this role?</label><textarea id="why"></textarea>
  <label for="yrs">Years of experience with SAP</label><input id="yrs" name="yrs">
  <label for="ctc">Expected CTC</label><input id="ctc" name="ctc">
  <label for="arr">Have you ever been arrested?</label><input id="arr" name="arr">
  <label for="g">Gender</label><select id="g"><option value="">Select</option><option>Female</option><option>Male</option></select>
  <label for="pw">Create a password</label><input id="pw" type="password">
  <label for="np">Notice period</label><input id="np" name="np">
  <label for="sd">Earliest start date</label><input id="sd" type="date">
  <label for="af">Available from</label><input id="af" type="date">
  <label for="cl">Cover letter</label><textarea id="cl"></textarea>
  <label for="cv">Resume</label><input id="cv" type="file">
  <label><input type="checkbox" id="agree" name="agree"> I agree to the privacy policy</label>
  <button type="submit">Submit application</button>
</form></main>`;

const ANSWERS = {
  "Why do you want this role?": { question: "Why do you want this role?", answer: null, status: "NEEDS_INPUT", remember_default: true, sensitivity: "personal" },
  "Years of experience with SAP": { question: "Years of experience with SAP", answer: "3", status: "VERIFIED", source: "memory", remember_default: true, sensitivity: "personal" },
  "Expected CTC": { question: "Expected CTC", answer: null, status: "NEEDS_INPUT", remember_default: true, sensitivity: "private", confirm: true },
  "Have you ever been arrested?": { question: "Have you ever been arrested?", answer: null, status: "NEEDS_INPUT", sensitivity: "never", reason: "Sensitive" },
  "Notice period": { question: "Notice period", answer: "30 days", status: "VERIFIED", source: "memory", stale: true, confirm: true, sensitivity: "personal" },
  "Earliest start date": { question: "Earliest start date", answer: "2026-12-01", status: "VERIFIED", source: "memory", confirm: true },
  "Available from": { question: "Available from", answer: "Immediately", status: "VERIFIED", source: "memory" },
};
const COVER = "Dear hiring team,\nI would like to apply for the Analyst role.";

async function filled() {
  const JP = load(FORM);
  JP.allowGeneric = true;
  JP.__testing = true;
  const submits = guardSubmit();
  const sent = [];
  JP.bridge = { send: vi.fn(async (action, args) => { sent.push([action, args]); return action === "learn" ? { ok: true, data: { saved: args.items.map((i) => i.question), errors: [] } } : { ok: true, data: {} }; }) };
  const report = await JP.fill({ fields: PROFILE, answers: ANSWERS, coverLetter: COVER, context: { applicationId: 3 } });
  return { JP, report, sent, submits, a: JP.core.adapterHere() };
}
const type = (id, value) => {
  const e = document.getElementById(id);
  e.value = value;
  e.dispatchEvent(new Event("input", { bubbles: true }));
};

describe("answers in context", () => {
  it("never fills a 'never' answer, treats stale answers as suggestions, keeps commitments ticked, and fills ISO dates only", async () => {
    const { report, submits } = await filled();
    const v = (id) => document.getElementById(id).value;
    expect(v("arr")).toBe("");
    expect(byLabel(report.needs, "Have you ever been arrested?").reason).toBe("Answer this yourself.");
    expect(v("np")).toBe("30 days");
    expect(byLabel(report.review, "Notice period")).toMatchObject({ confirm: true, note: expect.stringMatching(/still right/) });
    expect(byLabel(report.filled, "Notice period")).toBeUndefined();
    expect(v("yrs")).toBe("3");
    expect(byLabel(report.filled, "Years of experience with SAP")).toBeTruthy();
    expect(v("sd")).toBe("2026-12-01");
    expect(byLabel(report.filled, "Earliest start date")).toMatchObject({ confirm: true });
    expect(v("af")).toBe("");
    expect(byLabel(report.needs, "Available from").reason).toMatch(/^Pick the date yourself: "Immediately" isn.t one exact date/);
    expect(byLabel(report.skipped, "Gender")).toBeTruthy();
    expect(v("pw")).toBe("");
    expect(document.getElementById("agree").checked).toBe(false);
    expect(submits).toEqual([]);
  });

  it("offers the prepared cover letter only as a suggestion to review, and never touches cover letter uploads", async () => {
    const { JP, report, a } = await filled();
    expect(document.getElementById("cl").value).toBe(COVER);
    expect(byLabel(report.review, "Cover letter")).toMatchObject({ source: "cover letter", note: expect.stringMatching(/cover letter/) });
    expect(report.files.map((f) => f.label)).toEqual(["Resume"]);
    const s = JP.review.snapshot(a);
    expect(byLabel(s.screening, "Cover letter")).toMatchObject({ sourceKind: "suggested", source: expect.stringMatching(/cover letter prepared/) });
    expect(s.validation.warnings).toContain("Cover letter: JobPilot suggestion, check it.");
  });

  it("asks the user to pick a date that is not an ISO date, and lists date inputs in the scan", () => {
    const JP = load(`<main><form><label for="e">Email</label><input id="e" type="email"><label for="d">Date of joining</label><input id="d" type="date"></form></main>`);
    JP.allowGeneric = true;
    const q = JP.core.scan(JP.core.adapterHere()).find((x) => x.label === "Date of joining");
    expect(q.kind).toBe("date");
  });
});

describe("which confirmation signal matched", () => {
  it("adapter, url or text", async () => {
    let JP = load(fixture("synthetic", "greenhouse"));
    document.body.innerHTML = "<main><h1>Thank you for applying</h1></main>";
    expect(JP.submit.confirmation(JP.adapters.greenhouse)).toMatchObject({ kind: "adapter" });
    expect(await JP.submit.outcome(JP.adapters.greenhouse, { timeoutMs: 1500, step: 100 })).toMatchObject({ outcome: "confirmed", signal_kind: "adapter" });

    JP = load(FORM);
    JP.allowGeneric = true;
    const g = JP.adapters.generic;
    history.replaceState({}, "", "/jobs/1/thanks");
    expect(JP.submit.confirmation(g)).toMatchObject({ kind: "url" });
    history.replaceState({}, "", "/jobs/1");
    document.body.innerHTML = "<main><p>Your application has been submitted.</p></main>";
    expect(JP.submit.confirmation(g)).toMatchObject({ kind: "text" });
    expect(await JP.submit.outcome(g, { timeoutMs: 1500, step: 100 })).toMatchObject({ outcome: "confirmed", signal_kind: "text" });
    JP.adapters.workday.matchesHost = () => false;
    expect(JP.checkOutcome()).toMatchObject({ outcome: "confirmed", signal_kind: "text" });
  }, 10000);

  it("back on the form after submitting: the employer's validation messages, or nothing decided", () => {
    const JP = load(FORM.replace("<form>", '<form><div role="alert">Phone number is required</div>'));
    JP.allowGeneric = true;
    JP.adapters.workday.matchesHost = () => false;
    expect(JP.checkOutcome()).toEqual({ outcome: "errors", errors: ["Phone number is required"] });
    document.querySelector("[role=alert]").remove();
    expect(JP.checkOutcome()).toEqual({ outcome: "still_on_form" });
  });
});

describe("save answers for next time", () => {
  it("offers only what the user typed or changed, excluding sensitive, never, password, consent, file and profile fields", async () => {
    const { JP, report, a } = await filled();
    expect(JP.review.learnable(a, report)).toEqual([]);  // nothing typed yet
    type("why", "I like the product.");
    type("yrs", "4");  // changed from JobPilot's "3"
    type("ctc", "12 LPA");
    type("arr", "No");  // the server says never: not offered
    document.getElementById("g").value = "Female";  // sensitive question: not offered
    type("em", "other@example.com");  // a profile field: change it in the profile instead
    type("pw", "hunter2");
    document.getElementById("agree").click();
    type("cl", `${COVER} Edited.`);  // cover letters are not remembered as answers
    const c = JP.review.learnable(a, report);
    expect(c.map((x) => [x.label, x.value, x.checked])).toEqual([
      ["Why do you want this role?", "I like the product.", true],
      ["Years of experience with SAP", "4", true],
      ["Expected CTC", "12 LPA", false],  // private: offered, never pre-ticked
    ]);
    expect(c.find((x) => x.label === "Expected CTC").sensitive).toBe(true);
  });

  it("saves nothing without the click, then only the ticked items, and shows what was saved", async () => {
    const { JP, sent } = await filled();
    type("why", "I like the product.");
    type("yrs", "4");
    type("ctc", "12 LPA");
    JP.panel.render();
    const root = JP.__panelRoot;
    [...root.querySelectorAll("[role=tab]")].find((t) => t.textContent === "What JobPilot did").click();
    const section = () => root.querySelector("[data-section=learn]");
    expect(section()).toBeTruthy();
    expect(sent.filter(([x]) => x === "learn")).toEqual([]);  // shown, not saved
    const labels = [...section().querySelectorAll("label.tick")].map((l) => l.textContent);
    expect(labels.some((t) => /arrested|Gender|password|privacy|Cover letter|Email/i.test(t))).toBe(false);
    const ticks = [...section().querySelectorAll("input[type=checkbox]")];
    expect(ticks.map((t) => t.checked)).toEqual([true, true, false]);
    ticks[1].click();  // the user unticks "Years of experience with SAP"
    [...section().querySelectorAll("button")].find((b) => b.textContent === "Save selected").click();
    await wait(20);
    const learn = sent.filter(([x]) => x === "learn");
    expect(learn).toEqual([["learn", { items: [{ question: "Why do you want this role?", answer: "I like the product." }] }]]);
    expect(section().textContent).toMatch(/Saved for next time: Why do you want this role\?/);
    // The saved answer is no longer offered; the unticked one still is.
    expect([...section().querySelectorAll("label.tick")].map((l) => l.textContent).join(" ")).not.toMatch(/Why do you want/);
    expect(section().querySelectorAll("input[type=checkbox]")).toHaveLength(2);
  });

  it("shows the tracked state only when it adds to the live check of the form", async () => {
    const { JP } = await filled();
    const chips = () => [...JP.__panelRoot.querySelectorAll(".chips .chip")].map((c) => c.textContent);
    JP.context = { ...JP.context, stateLabel: "Needs information" };
    JP.panel.render();
    // The live check of the form is newer than the state recorded at fill time: only it is shown.
    expect(chips()).toContain("Required answers complete");
    expect(chips().some((t) => /Needs information/.test(t))).toBe(false);
    JP.context = { ...JP.context, stateLabel: "Submission pending" };
    JP.panel.render();
    expect(chips()).toContain("JobPilot: Submission pending");
  });

  it("shows the server's refusals inline", async () => {
    const { JP } = await filled();
    JP.bridge.send = vi.fn(async () => ({ ok: true, data: { saved: [], errors: [{ question: "Why do you want this role?", error: "Not a valid answer." }] } }));
    type("why", "x!");
    JP.panel.render();
    const root = JP.__panelRoot;
    [...root.querySelectorAll("[role=tab]")].find((t) => t.textContent === "What JobPilot did").click();
    [...root.querySelectorAll("[data-section=learn] button")].find((b) => b.textContent === "Save selected").click();
    await wait(20);
    expect(root.querySelector("[data-section=learn]").textContent).toMatch(/Not saved: Why do you want this role\?: Not a valid answer\./);
  });
});
