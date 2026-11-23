// Service worker: the only part of the extension that holds the device credential or talks to JobPilot.
//
// Who may ask for what:
//  * the extension's own popup: everything (connect, inspect the page, fill, attach, record, settings);
//  * the in-page review panel (a content script): only actions for the Smart Apply session the user started from
//    the popup (or from JobPilot) in that same tab and frame, on a page the extension is allowed on;
//  * the JobPilot web app (externally_connectable, APP_ORIGINS only): "ping" (is Smart Apply here and connected?) and
//    "apply" (open one job's Greenhouse/Lever/Ashby form and fill it). It never gets profile data back, and filling
//    never submits: the user still reviews and authorises every submission in the panel. No other page may message
//    the extension, and it has no web-accessible pages.
// Scripts are injected only after a click, only into frames of Greenhouse/Lever/Ashby pages or of sites the user
// allowed one by one, and never into LinkedIn, Naukri or Indeed.

import { ApiError, apiBase, forget, jobpilot } from "./lib/api.js";
import { APP_ORIGINS, CONTENT_FILES, formUrl, platformForUrl, validApiBase } from "./lib/config.js";
import { afterTabClosed, handoffApplicationId, learnItems, resumeChoice, signalKind, validResume } from "./lib/session.js";
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
    if (p) out.push({ frameId: r.frameId, url: r.result, platform: p.name, generic: !p.builtin && !["workday", "smartrecruiters"].includes(p.id) });
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

async function sha256(buf) {
  const d = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
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
  const diagnostics = [];  // frames with no recognised form: what they hold (counts only), so the popup can explain
  for (const f of frames) {
    const d = await run(tab.id, f.frameId, () => globalThis.__jobpilot.detect());
    if (d?.platform) details.push({ ...f, ...d, platform: d.platform });
    else diagnostics.push({ frameId: f.frameId, url: f.url, platform: f.platform, census: d?.census || null });
  }
  const form = details.sort((a, b) => b.fields - a.fields)[0];
  const connected = await jobpilot.connected();
  let match = null; let resumes = [];
  if (connected) {
    try { match = await jobpilot.match(form?.url || tab.url); } catch (e) { match = { error: e.message }; }
    try { resumes = await jobpilot.resumes(); } catch { resumes = []; }
  }
  const session = await getSession(tab.id);
  if (!form) return { supported: true, tabId: tab.id, form: null, platform: frames[0].platform, match, resumes, session, diagnostics: diagnose(diagnostics, tab.url) };
  return { supported: true, tabId: tab.id, form, match, resumes, session };
}

/** Why no form was recognised, from what the frames hold: {reason, frameHost?, origin?}. */
function diagnose(frames, topUrl) {
  const c = frames.map((f) => f.census).filter(Boolean);
  const sum = (k) => c.reduce((n, x) => n + (x[k] || 0), 0);
  let topHost = "";
  try { topHost = new URL(topUrl || "").hostname; } catch { /* about:blank */ }
  const foreign = [...new Set(c.flatMap((x) => x.frames || []).filter((h) => h && !["inline", "unknown", topHost].includes(h)))];
  const allowedHosts = new Set(frames.map((f) => { try { return new URL(f.url).hostname; } catch { return ""; } }));
  const frameHost = foreign.find((h) => !allowedHosts.has(h) && !/captcha|recaptcha|hcaptcha|google|doubleclick|youtube/.test(h));
  const counts = { lightFields: sum("lightFields"), deepFields: sum("deepFields"), shadowHosts: sum("shadowHosts"), closedHosts: sum("closedHosts"), opaqueHosts: sum("opaqueHosts"), forms: sum("forms") };
  if (frameHost) return { reason: "frame", frameHost, origin: `https://${frameHost}/*`, ...counts };
  if (counts.opaqueHosts >= 3 && !counts.deepFields && counts.lightFields < 2) return { reason: "closed_components", ...counts };
  if (counts.lightFields + counts.deepFields >= 2) return { reason: "fields_unrecognised", ...counts };
  return { reason: "no_fields", ...counts };
}

async function fill({ tabId, frameId, overwrite, userJobId, applicationId, resume }) {
  const [profile, detect] = await Promise.all([jobpilot.profile(), run(tabId, frameId, () => globalThis.__jobpilot?.detect())]);
  if (!detect?.platform) throw new ApiError(0, "The application form is no longer on this page. Reload it and try again.");
  const questions = [...new Set(detect.questions || [])].slice(0, 60);
  let session = (await getSession(tabId)) || { tabId };
  if (session.frameId !== frameId || session.url?.split("?")[0] !== detect.url.split("?")[0]) {
    session = { tabId, frameId, url: detect.url.split("?")[0], platform: detect.platform, applicationId: null, state: null, startedAt: Date.now() };
  }
  session.frameId = frameId;
  const picked = validResume(resume);
  if (picked) session.resume = picked;  // the user picked this resume in the popup for this session
  let tracking = null;
  const handed = handoffApplicationId(applicationId);
  if (handed && !session.applicationId) {  // the web app handed over the application itself
    session.applicationId = handed;
    session.userJobId = userJobId || session.userJobId || null;
  }
  if (userJobId && !session.applicationId) {
    try {
      tracking = await jobpilot.start(userJobId);
      session.applicationId = tracking.application_id;
      session.userJobId = userJobId;
    } catch (e) { tracking = { error: e.message }; }
  }
  if (detect.title || detect.company) session.job = { ...(session.job || {}), title: session.job?.title || detect.title, company: session.job?.company || detect.company };
  // This application's package: the resume chosen for it in JobPilot, and its prepared cover letter.
  let coverLetter = null;
  if (session.applicationId) {
    try {
      const pkg = await jobpilot.package(session.applicationId);
      session.packageResume = validResume(pkg?.resume);
      session.packageResumeConfirmed = pkg?.resume?.selected_by === "you";  // chosen (not just defaulted) in JobPilot
      coverLetter = typeof pkg?.cover_letter === "string" && pkg.cover_letter.trim() ? pkg.cover_letter.trim() : null;
    } catch { /* no package: the default resume, no cover letter */ }
  }
  // Answers in context: with the application, the server adds employer-specific answers and this application's own.
  const answers = {};
  if (questions.length) for (const a of await jobpilot.answers(questions, session.applicationId || null, detect.requirements || {})) answers[a.question] = a;
  await putSession(session);
  if (session.applicationId) await recordState(session, "filling", { mode: session.mode || (detect.assistedSubmit ? "assisted_submit" : "autofill_review"),
                                                                     info: { step: detect.step?.title || null } }).catch(() => null);
  const context = { job: session.job || null, applicationId: session.applicationId, stateLabel: session.stateLabel || null };
  const report = await run(tabId, frameId, (payload) => globalThis.__jobpilot.fill(payload),
                           [{ fields: profile.fields, answers, coverLetter, overwrite: Boolean(overwrite), context }]);
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
  const picked = validResume(resume);
  if (picked && session) { session.resume = picked; await putSession(session); }  // picked in the popup for this session
  // The popup's pick, else the resume the user chose for this application in JobPilot. Never a silent default.
  const { choice, from } = resumeChoice(picked, session);
  if (!choice) return { ok: false, needsChoice: true, reason: "Choose which resume to attach. JobPilot never picks one for you." };
  const file = await fetchResume(choice);
  const payload = { name: file.name, type: file.type, b64: toBase64(file.buf) };
  const res = await run(tabId, frameId, (f, opts) => globalThis.__jobpilot.attachResume(f, opts), [payload, { replace: Boolean(replace) }]);
  if (res?.ok && session) {
    // The exact file attached, for the application's history: what, chosen where, its size and content hash.
    session.resumeUsed = { kind: choice.kind, id: choice.id, format: choice.format || "pdf", name: file.name, chosen: from, verified: true,
                           size: file.buf.byteLength, sha256: await sha256(file.buf), checksum: file.checksum || null };
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
  outcome: async (s, { outcome, signal, signal_kind: kind, errors }) => {
    if (outcome === "confirmed") return recordState(s, "submitted_confirmed", { info: { signal: String(signal || "Confirmation seen").slice(0, 200), signal_kind: signalKind(kind) } });
    if (outcome === "errors") return recordState(s, "needs_information", { info: { message: `Site refused the submission: ${(errors || []).join("; ").slice(0, 400)}` } });
    return recordState(s, "submission_uncertain", { info: { message: "No confirmation seen on the page." } });
  },
  confirm: (s, { submitted }) => (s.applicationId ? ACTIONS.confirm({ applicationId: s.applicationId, submitted, tabId: s.tabId }) : { tracked: false }),
  /** Save the answers the user ticked "save for next time" (only after their click on "Save selected"). */
  learn: async (s, { items }) => {
    const clean = learnItems(items);
    if (!clean.length) throw new ApiError(0, "Nothing selected to save.");
    return jobpilot.learn(s.applicationId || null, clean);
  },
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
  // A page the user submitted themselves can navigate before the panel reports it ("You submitted on the page"): if
  // the new page carries a real confirmation, the attempt is recorded first, then the confirmation. Uncertain pages
  // are only judged after a recorded attempt.
  const userSubmitted = s && ["filling", "needs_information", "ready_for_review", "reviewed"].includes(s.state);
  if (!s || (s.state !== "submission_pending" && !userSubmitted)) return;
  if (userSubmitted) {
    if (!(await allowedPlatform(tab.url))) return;
    try {
      await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, files: CONTENT_FILES });
      const r = await run(tabId, 0, () => globalThis.__jobpilot.checkOutcome());
      if (r?.outcome === "confirmed" && ["adapter", "url"].includes(r.signal_kind)) {
        await recordState(s, "submission_pending", { info: { message: "You submitted on the page." } });
        await recordState(s, "submitted_confirmed", { info: { signal: r.signal, signal_kind: signalKind(r.signal_kind) } });
      }
    } catch { /* not readable: nothing recorded */ }
    return;
  }
  if (!(await allowedPlatform(tab.url))) {
    await recordState(s, "submission_uncertain", { info: { message: "The page moved to another site after submitting." } }).catch(() => null);
    return;
  }
  try {
    await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, files: CONTENT_FILES });
    const r = await run(tabId, 0, () => globalThis.__jobpilot.checkOutcome());
    if (r?.outcome === "confirmed") await recordState(s, "submitted_confirmed", { info: { signal: r.signal, signal_kind: signalKind(r.signal_kind) } });
    else if (r?.outcome === "errors") {
      await recordState(s, "needs_information", { info: { message: `The site did not accept the submission: ${(r.errors || []).join("; ").slice(0, 400)}` } });
    } else if (r?.outcome !== "still_on_form") await recordState(s, "submission_uncertain", { info: { message: "No confirmation seen after the page changed." } });
  } catch { /* the page could not be read: the panel or the user resolves it */ }
});

// A closed tab ends its session. A tracked application left half-done is recorded as "interrupted" (a pause: it
// resumes later with a fresh fill and review, never an automatic submission); one closed right after a submission
// click, before any confirmation, as "submission_uncertain".
async function tabClosed(tabId) {
  try {
    const s = await getSession(tabId).catch(() => null);
    const next = s?.applicationId ? afterTabClosed(s.state) : null;
    if (next) await recordState(s, next.state, { info: { message: next.message } }).catch(() => null);
  } finally {
    await dropSession(tabId).catch(() => null);
    await vault.remove(`handoff:${tabId}`).catch(() => null);
  }
}
chrome.tabs.onRemoved.addListener((tabId) => { tabClosed(tabId).catch(() => null); });

// ---- Apply from JobPilot: the web app hands over one job; the extension opens its form and fills it ------------

const HANDOFF_TTL_MS = 3 * 60 * 1000;
const handoffKey = (tabId) => `handoff:${tabId}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const badge = (tabId, text, title) => {
  chrome.action.setBadgeBackgroundColor({ tabId, color: text === "!" ? "#E11D48" : "#4F46E5" }).catch(() => null);
  chrome.action.setBadgeText({ tabId, text }).catch(() => null);
  if (title) chrome.action.setTitle({ tabId, title }).catch(() => null);
};

async function external(msg) {
  if (msg.type === "ping") return { version: chrome.runtime.getManifest().version, connected: await jobpilot.connected() };
  if (msg.type !== "apply") throw new ApiError(0, "Not allowed.");
  if (!(await jobpilot.connected())) throw new ApiError(0, "Smart Apply isn't connected yet. Open Settings → Browser extension and create a connection code.");
  const userJobId = Number(msg.userJobId);
  if (!Number.isInteger(userJobId) || userJobId <= 0) throw new ApiError(0, "Not allowed.");
  // Greenhouse, Lever and Ashby (built in), or a known application system the user already allowed on its site
  // (e.g. SmartRecruiters): the listing opens and JobPilot fills the form once it appears.
  let url = formUrl(msg.url);
  if (!url) {
    const p = platformForUrl(msg.url || "");
    if (p?.optional && p.known && (await allowedPlatform(msg.url))) url = new URL(msg.url).toString();
  }
  if (!url) throw new ApiError(0, "Smart Apply fills Greenhouse, Lever and Ashby forms, and sites you allowed it on. Open this listing and apply there.");
  // Record the hand-over before the form loads (a fast page could finish loading first and be missed).
  const applicationId = handoffApplicationId(msg.applicationId);  // optional: the application to track directly
  const tab = await chrome.tabs.create({ url: "about:blank", active: true });
  const h = { userJobId, applicationId, url, at: Date.now(), running: false };
  await vault.set(handoffKey(tab.id), h);
  await chrome.tabs.update(tab.id, { url });
  return { tabId: tab.id, url };
}

/** Find the form once the page has loaded (Ashby and some Greenhouse pages render it a moment later), then fill it
 *  and attach the resume. Same fill as the popup's button; submitting still needs the user in the review panel. */
async function autoFill(tabId, h) {
  const key = handoffKey(tabId);
  let keep = false;
  h.running = true;
  await vault.set(key, h);
  badge(tabId, "…", "JobPilot is filling this application");
  try {
    let form = null;
    for (let i = 0; i < 12 && !form; i++) {
      const frames = await supportedFrames(tabId);
      if (frames.length) {
        await inject(tabId, frames);
        const found = [];
        for (const f of frames) {
          const d = await run(tabId, f.frameId, () => globalThis.__jobpilot?.detect()).catch(() => null);
          if (d?.platform && d.fields > 0) found.push({ ...f, ...d });
        }
        form = found.sort((a, b) => b.fields - a.fields)[0] || null;
      }
      if (!form) await sleep(750);
    }
    if (!form) {
      // Still on the job listing (SmartRecruiters opens its form on the next page after "I'm interested"): keep the
      // hand-over until it expires, so the form is filled when it loads.
      badge(tabId, "!", "No application form found yet. Click Apply on the page; JobPilot fills the form when it opens.");
      keep = Date.now() - h.at < HANDOFF_TTL_MS;
      if (keep) await vault.set(key, { ...h, running: false });
      return;
    }
    const r = await fill({ tabId, frameId: form.frameId, overwrite: false, userJobId: h.userJobId, applicationId: h.applicationId });
    // The resume the user chose for this application in JobPilot (never a default, never replacing a file).
    const att = await attachResume({ tabId, frameId: form.frameId, replace: false }).catch(() => null);  // a form without a file field
    const noResume = att?.needsChoice;
    badge(tabId, r?.report?.needs?.length || noResume ? "!" : "✓",
          noResume ? "Filled. Choose your resume: open JobPilot from the toolbar." : r?.report?.needs?.length ? "Filled: some questions need you" : "Filled: review and submit in the panel");
  } catch (e) {
    badge(tabId, "!", `JobPilot couldn't fill this form: ${e?.message || "unknown error"}. Click here to try again.`);
  } finally {
    if (!keep) await vault.remove(key);
  }
}

chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (info.status !== "complete") return;
  const h = await vault.get(handoffKey(tabId)).catch(() => null);
  if (!h || h.running) return;
  if (Date.now() - h.at > HANDOFF_TTL_MS) { await vault.remove(handoffKey(tabId)); return; }
  if (!(await allowedPlatform(tab.url))) return;  // a redirect on the way to the form: wait for the next load
  await autoFill(tabId, h);
});

// Only the JobPilot web app may talk to the extension from a web page, and only with these two messages.
chrome.runtime.onMessageExternal.addListener((msg, sender, reply) => {
  let origin = sender.origin || "";
  try { origin = origin || new URL(sender.url || "").origin; } catch { origin = ""; }
  if (!APP_ORIGINS.includes(origin) || !msg || typeof msg.type !== "string") { reply({ ok: false, error: "Not allowed." }); return false; }
  external(msg)
    .then((data) => reply({ ok: true, data }))
    .catch((e) => reply({ ok: false, error: e instanceof ApiError || e instanceof Error ? e.message : "Something went wrong." }));
  return true;
});
