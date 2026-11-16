// Service worker: the only part of the extension that holds the device credential or talks to JobPilot.
//
// Who may ask for what:
//  * the extension's own popup: everything (connect, inspect the page, fill, attach, record, settings);
//  * the in-page review panel (a content script): only actions for the Smart Apply session the user started from
//    the popup in that same tab and frame, on a page the extension is allowed on. Web pages themselves can never
//    message the extension (no externally_connectable, no web-accessible pages).
// Scripts are injected only after a click, only into frames of Greenhouse/Lever/Ashby pages or of sites the user
// allowed one by one, and never into LinkedIn, Naukri or Indeed.

import { ApiError, apiBase, forget, jobpilot } from "./lib/api.js";
import { CONTENT_FILES, platformForUrl, validApiBase } from "./lib/config.js";
import { vault } from "./lib/vault.js";

const WEB_APP = "https://yadava-krishna.github.io/Job_portal/";
const fromPopup = (sender) => sender.id === chrome.runtime.id && (sender.url || "").startsWith(chrome.runtime.getURL("src/popup/"));

// ---- Smart Apply sessions (one per tab; kept in the extension's IndexedDB so they survive the worker sleeping) --

const sessKey = (tabId) => `session:${tabId}`;
const getSession = (tabId) => vault.get(sessKey(tabId)).then((s) => s || null);
async function putSession(s) { s.updatedAt = Date.now(); await vault.set(sessKey(s.tabId), s); return s; }
const dropSession = (tabId) => vault.remove(sessKey(tabId));

/** Platform info for a URL if the extension may run there (built in, or a site the user allowed), else null. */
async function allowedPlatform(url) {
  const p = platformForUrl(url || "");
  if (!p || p.blocked) return null;
  if (p.builtin) return p;
  try {
    return (await chrome.permissions.contains({ origins: [p.origin] })) ? p : null;
  } catch { return null; }
}

async function activeTab(tabId) {
  if (Number.isInteger(tabId)) return chrome.tabs.get(tabId);  // popup opened as a page for a given tab (tests, keyboard users)
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new ApiError(0, "No active tab.");
  return tab;
}

/** Frames of the tab the extension may work in: [{frameId, url, platform, generic}]. */
async function supportedFrames(tabId) {
  let probes = [];
  try {
    probes = await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: () => location.href });
  } catch {
    return [];  // a page the extension may not read (chrome://, the Web Store, a site not allowed…)
  }
  const out = [];
  for (const r of probes) {
    const p = await allowedPlatform(r.result);
    if (p) out.push({ frameId: r.frameId, url: r.result, platform: p.name, generic: !p.builtin && p.id !== "workday" });
  }
  return out;
}

async function inject(tabId, frames) {
  await chrome.scripting.executeScript({ target: { tabId, frameIds: frames.map((f) => f.frameId) }, files: CONTENT_FILES });
  const generic = frames.filter((f) => f.generic).map((f) => f.frameId);
  if (generic.length) await chrome.scripting.executeScript({ target: { tabId, frameIds: generic }, func: () => { globalThis.__jobpilot.allowGeneric = true; } });
}

async function run(tabId, frameId, func, args = []) {
  const [res] = await chrome.scripting.executeScript({ target: { tabId, frameIds: [frameId] }, func, args });
  return res?.result;
}

function toBase64(buf) {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

/** Record a Smart Apply state for the session's application (if it is tracked). Never throws for a 409 replay. */
async function recordState(session, state, { mode, info = {}, referenceId } = {}) {
  if (!session?.applicationId) { if (session) { session.state = state; await putSession(session); } return { tracked: false, state }; }
  try {
    const r = await jobpilot.state(session.applicationId, { state, mode: mode || session.mode || null, reference_id: referenceId || null,
      session: { platform: session.platform, page: session.url, resume: session.resumeUsed || undefined, ...info } });
    session.state = r.apply_state; session.stateLabel = r.apply_state_label;
    if (mode) session.mode = mode;
    await putSession(session);
    if (Number.isInteger(session.frameId)) {
      run(session.tabId, session.frameId, (label) => { const JP = globalThis.__jobpilot; if (!JP?.panel) return; JP.context = { ...(JP.context || {}), stateLabel: label }; JP.panel.render(); },
          [r.apply_state_label || null]).catch(() => null);
    }
    return { tracked: true, ...r };
  } catch (e) {
    if (e.status === 409) return { tracked: true, conflict: true, error: e.message };
    throw e;
  }
}

// ---- popup actions ----------------------------------------------------------------------------

async function state() {
  const connected = await jobpilot.connected();
  let status = null; let error = null;
  if (connected) {
    try {
      await jobpilot.rotateIfDue();
      status = await jobpilot.status();
    } catch (e) {
      error = e.message;
    }
  }
  return { connected: await jobpilot.connected(), info: await jobpilot.info(), status, error,
           apiBaseOverride: (await vault.get("apiBaseOverride")) || null };
}

async function inspect({ tabId } = {}) {
  const tab = await activeTab(tabId);
  const top = platformForUrl(tab.url || "");
  if (top?.blocked) return { supported: false, blocked: { name: top.name, why: top.why }, tabId: tab.id };
  const frames = await supportedFrames(tab.id);
  if (!frames.length) {
    return { supported: false, tabId: tab.id, canRequest: top?.optional ? { origin: top.origin, name: top.name, known: top.known } : null };
  }
  await inject(tab.id, frames);
  const details = [];
  for (const f of frames) {
    const d = await run(tab.id, f.frameId, () => globalThis.__jobpilot.detect());
    if (d?.platform) details.push({ ...f, ...d, platform: d.platform });
  }
  const form = details.sort((a, b) => b.fields - a.fields)[0];
  const connected = await jobpilot.connected();
  let match = null; let resumes = [];
  if (connected) {
    try { match = await jobpilot.match(form?.url || tab.url); } catch (e) { match = { error: e.message }; }
    try { resumes = await jobpilot.resumes(); } catch { resumes = []; }
  }
  const session = await getSession(tab.id);
  if (!form) return { supported: true, tabId: tab.id, form: null, platform: frames[0].platform, match, resumes, session };
  return { supported: true, tabId: tab.id, form, match, resumes, session };
}

async function fill({ tabId, frameId, overwrite, userJobId, resume }) {
  const [profile, detect] = await Promise.all([jobpilot.profile(), run(tabId, frameId, () => globalThis.__jobpilot?.detect())]);
  if (!detect?.platform) throw new ApiError(0, "The application form is no longer on this page. Reload it and try again.");
  const questions = [...new Set(detect.questions || [])].slice(0, 60);
  const answers = {};
  if (questions.length) for (const a of await jobpilot.answers(questions)) answers[a.question] = a;
  let session = (await getSession(tabId)) || { tabId };
  if (session.frameId !== frameId || session.url?.split("?")[0] !== detect.url.split("?")[0]) {
    session = { tabId, frameId, url: detect.url.split("?")[0], platform: detect.platform, applicationId: null, state: null, startedAt: Date.now() };
  }
  session.frameId = frameId;
  if (resume) session.resume = resume;
  let tracking = null;
  if (userJobId && !session.applicationId) {
    try {
      tracking = await jobpilot.start(userJobId);
      session.applicationId = tracking.application_id;
      session.userJobId = userJobId;
    } catch (e) { tracking = { error: e.message }; }
  }
  if (detect.title || detect.company) session.job = { ...(session.job || {}), title: session.job?.title || detect.title, company: session.job?.company || detect.company };
  await putSession(session);
  if (session.applicationId) await recordState(session, "filling", { mode: session.mode || (detect.assistedSubmit ? "assisted_submit" : "autofill_review"),
                                                                     info: { step: detect.step?.title || null } }).catch(() => null);
  const context = { job: session.job || null, applicationId: session.applicationId, stateLabel: session.stateLabel || null };
  const report = await run(tabId, frameId, (payload) => globalThis.__jobpilot.fill(payload),
                           [{ fields: profile.fields, answers, overwrite: Boolean(overwrite), context }]);
  if (report && !report.error && session.applicationId) {
    const counts = { filled: report.filled.length, review: report.review.length + (report.unsure?.length || 0), needs: report.needs.length, skipped: report.skipped.length };
    await recordState(session, report.needs.length ? "needs_information" : "ready_for_review", { info: { counts } }).catch(() => null);
    await run(tabId, frameId, (label) => { const JP = globalThis.__jobpilot; JP.context = { ...(JP.context || {}), stateLabel: label }; JP.panel?.render(); },
              [session.stateLabel || null]).catch(() => null);
  }
  return { report, missing: profile.missing, tracking, session };
}

async function fetchResume(choice) {
  const c = choice && ["upload", "studio"].includes(choice.kind) ? choice : { kind: "upload" };
  return jobpilot.resume(c);
}

async function attachResume({ tabId, frameId, replace, resume }) {
  const session = await getSession(tabId);
  const choice = resume || session?.resume || null;
  const file = await fetchResume(choice);
  const payload = { name: file.name, type: file.type, b64: toBase64(file.buf) };
  const res = await run(tabId, frameId, (f, opts) => globalThis.__jobpilot.attachResume(f, opts), [payload, { replace: Boolean(replace) }]);
  if (res?.ok && session) {
    session.resumeUsed = { kind: choice?.kind || "upload", id: choice?.id ?? file.resumeId ?? null, format: choice?.format || "pdf", name: file.name, verified: true };
    await putSession(session);
  }
  return res;
}

async function downloadResume({ resume } = {}) {
  const file = await fetchResume(resume);
  return { name: file.name, type: file.type, b64: toBase64(file.buf) };
}

async function setApiBase({ url }) {
  if (!url) { await vault.remove("apiBaseOverride"); await vault.remove("apiBase"); return { ok: true }; }
  const base = validApiBase(url);
  if (!base) throw new ApiError(0, "Use an https:// address (or http://localhost for local development).");
  await vault.set("apiBaseOverride", base);
  return { ok: true, base };
}

/** Values for a manual hand-off on sites JobPilot does not fill (copy-ready, shown only in the popup). */
async function handoff() {
  const p = await jobpilot.profile();
  const f = p.fields || {};
  const rows = [["Full name", f.full_name], ["Email", f.email], ["Phone", f.phone], ["Location", f.location], ["LinkedIn", f.linkedin_url],
                ["GitHub", f.github_url], ["Portfolio", f.portfolio_url], ["Current company", f.current_company], ["Current title", f.current_title],
                ["Degree", f.degree], ["School", f.school]].filter(([, v]) => v);
  const facts = Object.entries(p.facts || {}).map(([k, v]) => [k.replace(/_/g, " "), String(v)]);
  return { rows: [...rows, ...facts], resumeName: p.resume_filename || null };
}

const ACTIONS = {
  state,
  inspect,
  fill,
  attachResume,
  downloadResume,
  setApiBase,
  handoff,
  pair: ({ code, deviceName }) => jobpilot.pair(String(code || ""), String(deviceName || "Chrome").slice(0, 100)).then((t) => ({ user: t.user_display_name, expiresAt: t.expires_at })),
  disconnect: () => jobpilot.disconnect().then(() => ({ ok: true })),
  forget: () => forget().then(() => ({ ok: true })),
  confirm: async ({ applicationId, submitted, referenceId, tabId }) => {
    const r = await jobpilot.confirm(Number(applicationId), Boolean(submitted), referenceId ? String(referenceId).slice(0, 200) : null);
    if (Number.isInteger(tabId)) { const s = await getSession(tabId); if (s) { s.state = r.apply_state; await putSession(s); } }
    return r;
  },
  apiBase: () => apiBase().then((base) => ({ base })),
};

// ---- review-panel actions (content script in the session's frame) ----------------------------

const PANEL = {
  fill: (s) => fill({ tabId: s.tabId, frameId: s.frameId, overwrite: false, userJobId: null }).then((r) => ({ report: r.report })),
  attachResume: (s, { replace }) => attachResume({ tabId: s.tabId, frameId: s.frameId, replace }),
  state: async (s, { state: st, mode, session: info }) => {
    const allowed = ["filling", "needs_information", "ready_for_review", "reviewed", "submission_authorized", "submission_pending"];
    if (!allowed.includes(st)) throw new ApiError(0, "Not allowed.");
    const r = await recordState(s, st, { mode, info: info || {} });
    if (r.conflict) throw new ApiError(409, r.error);
    return r;
  },
  outcome: async (s, { outcome, signal, errors }) => {
    if (outcome === "confirmed") return recordState(s, "submitted_confirmed", { info: { signal: String(signal || "Confirmation seen").slice(0, 200) } });
    if (outcome === "errors") return recordState(s, "needs_information", { info: { message: `Site refused the submission: ${(errors || []).join("; ").slice(0, 400)}` } });
    return recordState(s, "submission_uncertain", { info: { message: "No confirmation seen on the page." } });
  },
  confirm: (s, { submitted }) => (s.applicationId ? ACTIONS.confirm({ applicationId: s.applicationId, submitted, tabId: s.tabId }) : { tracked: false }),
  openApp: () => chrome.tabs.create({ url: `${WEB_APP}#/applied` }).then(() => ({ ok: true })),
};

async function panelAction(msg, sender) {
  const tabId = sender.tab?.id;
  const s = Number.isInteger(tabId) ? await getSession(tabId) : null;
  if (!s || s.frameId !== sender.frameId || !(await allowedPlatform(sender.url))) throw new ApiError(0, "Open JobPilot from the toolbar and click Fill first.");
  const name = msg.action.slice("panel:".length);
  if (!Object.hasOwn(PANEL, name)) throw new ApiError(0, "Not allowed.");
  return PANEL[name](s, msg.args || {});
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const isPanel = sender.id === chrome.runtime.id && sender.tab && typeof msg?.action === "string" && msg.action.startsWith("panel:");
  if (!isPanel && (!fromPopup(sender) || !msg || typeof msg.action !== "string" || !Object.hasOwn(ACTIONS, msg.action))) {
    reply({ ok: false, error: "Not allowed." });
    return false;
  }
  (isPanel ? panelAction(msg, sender) : ACTIONS[msg.action](msg.args || {}))
    .then((data) => reply({ ok: true, data }))
    .catch((e) => reply({ ok: false, error: e instanceof ApiError || e instanceof Error ? e.message : "Something went wrong.", status: e?.status ?? 0 }));
  return true;  // async reply
});

// ---- outcome after a navigation (e.g. Lever moves to /thanks after submitting) ----------------

chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.status !== "complete") return;
  const s = await getSession(tabId).catch(() => null);
  if (!s || s.state !== "submission_pending") return;
  if (!(await allowedPlatform(tab.url))) {
    await recordState(s, "submission_uncertain", { info: { message: "The page moved to another site after submitting." } }).catch(() => null);
    return;
  }
  try {
    await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, files: CONTENT_FILES });
    const r = await run(tabId, 0, () => globalThis.__jobpilot.checkOutcome());
    if (r?.outcome === "confirmed") await recordState(s, "submitted_confirmed", { info: { signal: r.signal } });
    else if (r?.outcome !== "still_on_form") await recordState(s, "submission_uncertain", { info: { message: "No confirmation seen after the page changed." } });
  } catch { /* the page could not be read: the panel or the user resolves it */ }
});

chrome.tabs.onRemoved.addListener((tabId) => { dropSession(tabId).catch(() => null); });

// Nobody else may talk to the extension.
chrome.runtime.onMessageExternal?.addListener((_m, _s, reply) => reply({ ok: false }));
