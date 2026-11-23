// Service worker: the resume chosen for the application, answers in context, the web hand-off's application id,
// what is recorded when a tab closes, the confirmation signal kind, and saving answers only on request.
// chrome.*, the vault and the JobPilot client are fakes: nothing leaves the test.
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { afterTabClosed, handoffApplicationId, learnItems, resumeChoice, signalKind, validResume } from "../../src/lib/session.js";

const store = vi.hoisted(() => new Map());
vi.mock("../../src/lib/vault.js", () => ({
  vault: {
    get: async (k) => store.get(k),
    set: async (k, v) => { store.set(k, structuredClone(v)); },
    remove: async (k) => { store.delete(k); },
    clear: async () => { store.clear(); },
  },
}));
const api = vi.hoisted(() => ({
  jobpilot: {
    connected: async () => true,
    profile: async () => ({ fields: { email: "t@example.com" }, missing: [] }),
    start: null, package: null, answers: null, state: null, resume: null, learn: null, resumes: async () => [], match: async () => ({}),
  },
}));
vi.mock("../../src/lib/api.js", () => {
  class ApiError extends Error { constructor(status, message) { super(message); this.status = status; } }
  return { ApiError, apiBase: async () => "https://good.example", forget: async () => {}, jobpilot: api.jobpilot };
});

const FORM = "https://job-boards.greenhouse.io/acme/jobs/1";
const TAB = 5;
const listeners = {};
const on = (name) => ({ addListener: (fn) => { (listeners[name] ??= []).push(fn); } });
const POPUP = { id: "ext", url: "chrome-extension://ext/src/popup/popup.html" };
const PANEL = { id: "ext", tab: { id: TAB }, frameId: 0, url: FORM };
const wait = (ms = 0) => new Promise((r) => setTimeout(r, ms));

function message(msg, sender, kind = "message") {
  return new Promise((resolve) => { listeners[kind][0](msg, sender, resolve); });
}
const session = () => store.get(`session:${TAB}`);
const recorded = () => api.jobpilot.state.mock.calls.map(([, body]) => body);

beforeAll(async () => {
  globalThis.chrome = {
    runtime: { id: "ext", getURL: (p) => `chrome-extension://ext/${p}`, onMessage: on("message"), onMessageExternal: on("external"), getManifest: () => ({ version: "2.2.0" }) },
    tabs: { onUpdated: on("updated"), onRemoved: on("removed"), create: vi.fn(async () => ({ id: TAB })), update: vi.fn(async () => ({})), get: vi.fn(), query: vi.fn() },
    scripting: {
      executeScript: vi.fn(async ({ target, func, args, files }) => {
        if (files) return [];
        if (target.allFrames) return [{ frameId: 0, result: FORM }];
        return [{ frameId: 0, result: await func(...(args || [])) }];
      }),
    },
    permissions: { contains: async () => false },
    action: { setBadgeBackgroundColor: async () => {}, setBadgeText: async () => {}, setTitle: async () => {} },
  };
  await import("../../src/background.js");
});

beforeEach(() => {
  store.clear();
  Object.assign(api.jobpilot, {
    start: vi.fn(async () => ({ application_id: 55 })),
    package: vi.fn(async (id) => ({ application_id: id, resume: { kind: "studio", id: 12, format: "docx", name: "Tailored for Acme", selected_by: "you" }, cover_letter: "Dear Acme team, ..." })),
    answers: vi.fn(async (qs) => qs.map((q) => ({ question: q, answer: null, status: "NEEDS_INPUT" }))),
    state: vi.fn(async (id, body) => ({ apply_state: body.state, apply_state_label: body.state })),
    resume: vi.fn(async (c) => ({ name: c.format === "docx" ? "cv.docx" : "cv.pdf", type: "application/pdf", buf: new Uint8Array([37, 80]).buffer })),
    learn: vi.fn(async (id, items) => ({ saved: items.map((i) => i.question), errors: [] })),
  });
  globalThis.__jobpilot = {
    detect: () => ({ platform: "Greenhouse", url: FORM, fields: 3, questions: ["Why Acme?"], assistedSubmit: true, title: "Analyst", company: "Acme" }),
    fill: vi.fn(async () => ({ filled: [], review: [], unsure: [], kept: [], skipped: [], needs: [{ label: "Why Acme?" }], files: [] })),
    attachResume: vi.fn(async (f) => ({ ok: true, verified: true, name: f.name, size: 2 })),
    checkOutcome: () => ({ outcome: "confirmed", signal: "Confirmation page (/thanks)", signal_kind: "url" }),
    panel: { render() {} },
  };
});

describe("pure session decisions", () => {
  it("records interrupted for a half-done application, uncertain right after a submission click, nothing otherwise", () => {
    for (const s of ["form_opened", "filling", "needs_information", "ready_for_review", "reviewed", "submission_authorized"]) {
      expect(afterTabClosed(s)).toEqual({ state: "interrupted", message: "Tab closed before submitting." });
    }
    expect(afterTabClosed("submission_pending")).toEqual({ state: "submission_uncertain", message: "Tab closed right after submitting." });
    for (const s of [null, undefined, "draft", "submitted_confirmed", "submission_uncertain", "interrupted", "failed"]) expect(afterTabClosed(s)).toBeNull();
  });

  it("uses the popup's pick, else the resume the user chose for the application, else none (never a silent default)", () => {
    const pkg = { kind: "studio", id: 12, format: "docx", name: "Tailored" };
    expect(resumeChoice(null, { packageResume: pkg, packageResumeConfirmed: true })).toEqual({ choice: { ...pkg }, from: "package" });
    // A package resume that was only JobPilot's default (not chosen by the user) is not attached on its own.
    expect(resumeChoice(null, { packageResume: pkg, packageResumeConfirmed: false })).toEqual({ choice: null, from: "none" });
    expect(resumeChoice({ kind: "upload", id: 3, format: "pdf" }, { packageResume: pkg }).choice).toMatchObject({ kind: "upload", id: 3 });
    expect(resumeChoice(null, { resume: { kind: "upload", id: 3, format: "pdf" }, packageResume: pkg }).from).toBe("popup");
    expect(resumeChoice(null, {})).toEqual({ choice: null, from: "none" });
    expect(resumeChoice(null, { packageResume: { kind: "evil", id: 1 }, packageResumeConfirmed: true }).from).toBe("none");
    expect(validResume({ kind: "upload", id: "x" })).toBeNull();
    expect(handoffApplicationId("12")).toBe(12);
    for (const bad of [null, undefined, "", 0, -3, 1.5, "abc", {}]) expect(handoffApplicationId(bad)).toBeNull();
    expect(signalKind("text")).toBe("text");
    expect(signalKind("made-up")).toBeUndefined();
    expect(learnItems([{ question: "  Why   us? ", answer: " Because " }, { question: "x", answer: "y" }, { question: "Ok?", answer: "" }, null]))
      .toEqual([{ question: "Why us?", answer: "Because" }]);
  });
});

describe("fill and attach with the application's package", () => {
  it("passes the application to answers, fetches the package, offers its cover letter, and attaches its resume", async () => {
    const r = await message({ action: "fill", args: { tabId: TAB, frameId: 0, userJobId: 9 } }, POPUP);
    expect(r.ok).toBe(true);
    expect(api.jobpilot.start).toHaveBeenCalledWith(9);
    expect(api.jobpilot.package).toHaveBeenCalledWith(55);
    expect(api.jobpilot.answers).toHaveBeenCalledWith(["Why Acme?"], 55, {});
    expect(globalThis.__jobpilot.fill.mock.calls[0][0].coverLetter).toBe("Dear Acme team, ...");
    expect(session()).toMatchObject({ applicationId: 55, packageResume: { kind: "studio", id: 12, format: "docx" } });
    expect(recorded().map((b) => b.state)).toEqual(["filling", "needs_information"]);  // nothing authorised or submitted

    expect((await message({ action: "attachResume", args: { tabId: TAB, frameId: 0, replace: false, resume: null } }, POPUP)).ok).toBe(true);
    expect(api.jobpilot.resume).toHaveBeenLastCalledWith(expect.objectContaining({ kind: "studio", id: 12, format: "docx" }));
    expect(session().resumeUsed).toMatchObject({ kind: "studio", id: 12, format: "docx", name: "cv.docx", verified: true });

    // A resume the user picks in the popup wins for this session, also on later attaches.
    await message({ action: "attachResume", args: { tabId: TAB, frameId: 0, replace: true, resume: { kind: "upload", id: 3, format: "pdf" } } }, POPUP);
    expect(api.jobpilot.resume).toHaveBeenLastCalledWith(expect.objectContaining({ kind: "upload", id: 3, format: "pdf" }));
    await message({ action: "attachResume", args: { tabId: TAB, frameId: 0, replace: true, resume: null } }, POPUP);
    expect(api.jobpilot.resume).toHaveBeenLastCalledWith(expect.objectContaining({ kind: "upload", id: 3 }));
  });

  it("without a tracked application: plain answers, no package, and no resume until the user picks one", async () => {
    await message({ action: "fill", args: { tabId: TAB, frameId: 0, userJobId: null } }, POPUP);
    expect(api.jobpilot.answers).toHaveBeenCalledWith(["Why Acme?"], null, {});
    expect(api.jobpilot.package).not.toHaveBeenCalled();
    expect(globalThis.__jobpilot.fill.mock.calls[0][0].coverLetter).toBeNull();
    const none = await message({ action: "attachResume", args: { tabId: TAB, frameId: 0, replace: false } }, POPUP);
    expect(none.data).toMatchObject({ ok: false, needsChoice: true });
    expect(api.jobpilot.resume).not.toHaveBeenCalled();  // nothing downloaded or attached by default
    await message({ action: "attachResume", args: { tabId: TAB, frameId: 0, replace: false, resume: { kind: "upload", id: 4, format: "pdf" } } }, POPUP);
    expect(api.jobpilot.resume).toHaveBeenLastCalledWith(expect.objectContaining({ kind: "upload", id: 4 }));
  });
});

describe("Apply from JobPilot with an application id", () => {
  it("tracks the handed-over application directly and attaches the resume chosen for it", async () => {
    const r = await message({ type: "apply", url: FORM, userJobId: 9, applicationId: 77 }, { origin: "https://yadava-krishna.github.io" }, "external");
    expect(r.ok).toBe(true);
    expect(store.get(`handoff:${TAB}`)).toMatchObject({ userJobId: 9, applicationId: 77 });
    await Promise.all(listeners.updated.map((fn) => fn(TAB, { status: "complete" }, { url: FORM })));
    expect(api.jobpilot.start).not.toHaveBeenCalled();
    expect(api.jobpilot.package).toHaveBeenCalledWith(77);
    expect(api.jobpilot.answers).toHaveBeenCalledWith(["Why Acme?"], 77, {});
    expect(api.jobpilot.resume).toHaveBeenCalledWith(expect.objectContaining({ kind: "studio", id: 12 }));
    expect(globalThis.__jobpilot.attachResume.mock.calls[0][1]).toEqual({ replace: false });
    expect(recorded().map((b) => b.state)).toEqual(["filling", "needs_information"]);
    expect(store.has(`handoff:${TAB}`)).toBe(false);
  });

  it("still starts tracking when the web app sends no application id", async () => {
    await message({ type: "apply", url: FORM, userJobId: 9 }, { origin: "https://yadava-krishna.github.io" }, "external");
    expect(store.get(`handoff:${TAB}`).applicationId).toBeNull();
    await Promise.all(listeners.updated.map((fn) => fn(TAB, { status: "complete" }, { url: FORM })));
    expect(api.jobpilot.start).toHaveBeenCalledWith(9);
    expect(api.jobpilot.package).toHaveBeenCalledWith(55);
  });
});

describe("closing the tab", () => {
  const closeWith = async (state, applicationId = 55) => {
    store.set(`session:${TAB}`, { tabId: TAB, frameId: 0, url: FORM, platform: "Greenhouse", applicationId, state });
    store.set(`handoff:${TAB}`, { userJobId: 9 });
    listeners.removed[0](TAB);
    await wait(10);
  };

  it("records interrupted before dropping a half-done session", async () => {
    await closeWith("ready_for_review");
    expect(recorded()).toEqual([expect.objectContaining({ state: "interrupted", session: expect.objectContaining({ message: "Tab closed before submitting." }) })]);
    expect(session()).toBeUndefined();
    expect(store.has(`handoff:${TAB}`)).toBe(false);
  });

  it("records uncertain when the tab closes right after a submission click", async () => {
    await closeWith("submission_pending");
    expect(recorded()).toEqual([expect.objectContaining({ state: "submission_uncertain", session: expect.objectContaining({ message: "Tab closed right after submitting." }) })]);
  });

  it("records nothing for a finished or untracked application, and still drops the session if the server fails", async () => {
    await closeWith("submitted_confirmed");
    await closeWith("filling", null);
    expect(api.jobpilot.state).not.toHaveBeenCalled();
    api.jobpilot.state = vi.fn(async () => { throw new Error("offline"); });
    await closeWith("reviewed");
    expect(api.jobpilot.state).toHaveBeenCalledTimes(1);
    expect(session()).toBeUndefined();
  });
});

describe("review-panel actions", () => {
  beforeEach(() => store.set(`session:${TAB}`, { tabId: TAB, frameId: 0, url: FORM, platform: "Greenhouse", applicationId: 55, state: "submission_pending" }));

  it("passes which confirmation signal matched (panel outcome and after a navigation)", async () => {
    await message({ action: "panel:outcome", args: { outcome: "confirmed", signal: 'Page says: "Thank you for applying"', signal_kind: "text" } }, PANEL);
    expect(recorded()[0]).toMatchObject({ state: "submitted_confirmed", session: { signal_kind: "text" } });
    store.set(`session:${TAB}`, { ...session(), state: "submission_pending" });
    await Promise.all(listeners.updated.map((fn) => fn(TAB, { status: "complete" }, { url: `${FORM}/thanks` })));
    expect(recorded()[1]).toMatchObject({ state: "submitted_confirmed", session: { signal: "Confirmation page (/thanks)", signal_kind: "url" } });
  });

  it("a validation error from the employer is recorded as needs information, never as applied", async () => {
    await message({ action: "panel:outcome", args: { outcome: "errors", errors: ["Phone is required"] } }, PANEL);
    expect(recorded()[0]).toMatchObject({ state: "needs_information", session: { message: "Site refused the submission: Phone is required" } });
    store.set(`session:${TAB}`, { ...session(), state: "submission_pending" });
    globalThis.__jobpilot.checkOutcome = () => ({ outcome: "errors", errors: ["Email is invalid"] });
    await Promise.all(listeners.updated.map((fn) => fn(TAB, { status: "complete" }, { url: FORM })));
    expect(recorded()[1]).toMatchObject({ state: "needs_information", session: { message: "The site did not accept the submission: Email is invalid" } });
    store.set(`session:${TAB}`, { ...session(), state: "submission_pending" });
    globalThis.__jobpilot.checkOutcome = () => ({ outcome: "still_on_form" });
    await Promise.all(listeners.updated.map((fn) => fn(TAB, { status: "complete" }, { url: FORM })));
    expect(recorded()).toHaveLength(2);  // back on the form with no messages: nothing decided yet
  });

  it("a submission the user made on the page is recorded only with a strong confirmation", async () => {
    store.set(`session:${TAB}`, { ...session(), state: "ready_for_review" });
    globalThis.__jobpilot.checkOutcome = () => ({ outcome: "confirmed", signal: 'Page says: "Thanks"', signal_kind: "text" });
    await Promise.all(listeners.updated.map((fn) => fn(TAB, { status: "complete" }, { url: `${FORM}/done` })));
    expect(recorded()).toEqual([]);  // page text alone, without a recorded click: not enough
    globalThis.__jobpilot.checkOutcome = () => ({ outcome: "confirmed", signal: "Confirmation page (/thanks)", signal_kind: "url" });
    await Promise.all(listeners.updated.map((fn) => fn(TAB, { status: "complete" }, { url: `${FORM}/thanks` })));
    expect(recorded().map((b) => b.state)).toEqual(["submission_pending", "submitted_confirmed"]);
    expect(recorded()[0].session.message).toBe("You submitted on the page.");
    expect(recorded()[1]).toMatchObject({ session: { signal_kind: "url" } });
  });

  it("saves answers only when asked, trimmed to what the server accepts", async () => {
    const r = await message({ action: "panel:learn", args: { items: [{ question: "Why Acme?", answer: "Product " }, { question: "", answer: "x" }] } }, PANEL);
    expect(r).toEqual({ ok: true, data: { saved: ["Why Acme?"], errors: [] } });
    expect(api.jobpilot.learn).toHaveBeenCalledWith(55, [{ question: "Why Acme?", answer: "Product" }]);
    expect((await message({ action: "panel:learn", args: { items: [] } }, PANEL)).ok).toBe(false);
    expect(api.jobpilot.learn).toHaveBeenCalledTimes(1);
  });

  it("the panel cannot record a submission state it is not allowed to", async () => {
    for (const st of ["submitted_confirmed", "interrupted"]) {
      expect((await message({ action: "panel:state", args: { state: st } }, PANEL)).ok).toBe(false);
    }
  });
});
