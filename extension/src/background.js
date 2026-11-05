// Service worker: the only part of the extension that holds the device credential or talks to JobPilot.
//
// It acts only on messages from the extension's own popup (never from content scripts or web pages), and only on
// the tab the user opened the popup on. Fill scripts are injected only into frames whose address is an
// allow-listed Greenhouse, Lever or Ashby page, and only after a click.

import { ApiError, apiBase, forget, jobpilot } from "./lib/api.js";
import { CONTENT_FILES, platformForUrl, validApiBase } from "./lib/config.js";
import { vault } from "./lib/vault.js";

// Only the extension's own popup page may ask for anything. Content scripts report the employer page's URL as
// sender.url, and web pages cannot load or message chrome-extension:// pages (none are web-accessible).
const fromPopup = (sender) => sender.id === chrome.runtime.id && (sender.url || "").startsWith(chrome.runtime.getURL("src/popup/"));

async function activeTab(tabId) {
  if (Number.isInteger(tabId)) return chrome.tabs.get(tabId);  // popup opened as a page for a given tab (tests, keyboard users)
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new ApiError(0, "No active tab.");
  return tab;
}

/** Frames of the tab that are supported application pages: [{frameId, url, platform}]. */
async function supportedFrames(tabId) {
  let probes = [];
  try {
    probes = await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: () => location.href });
  } catch {
    return [];  // a page the extension may not read (chrome://, the Web Store, …)
  }
  return probes.flatMap((r) => {
    const p = platformForUrl(r.result);
    return p ? [{ frameId: r.frameId, url: r.result, platform: p.name }] : [];
  });
}

async function inject(tabId, frameIds) {
  await chrome.scripting.executeScript({ target: { tabId, frameIds }, files: CONTENT_FILES });
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

// ---- actions ----------------------------------------------------------------------------------

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
  const frames = await supportedFrames(tab.id);
  if (!frames.length) return { supported: false, tabUrl: platformForUrl(tab.url || "") ? tab.url : null };
  await inject(tab.id, frames.map((f) => f.frameId));
  const details = [];
  for (const f of frames) {
    const d = await run(tab.id, f.frameId, () => globalThis.__jobpilot.detect());
    if (d?.platform) details.push({ ...f, ...d });
  }
  const form = details.sort((a, b) => b.fields - a.fields)[0];
  if (!form) return { supported: true, form: null, platform: frames[0].platform };
  let match = null;
  if (await jobpilot.connected()) {
    try { match = await jobpilot.match(form.url); } catch (e) { match = { error: e.message }; }
  }
  return { supported: true, tabId: tab.id, form, match };
}

async function fill({ tabId, frameId, overwrite, userJobId }) {
  const [profile, detect] = await Promise.all([jobpilot.profile(), run(tabId, frameId, () => globalThis.__jobpilot?.detect())]);
  if (!detect?.platform) throw new ApiError(0, "The application form is no longer on this page. Reload it and try again.");
  const questions = [...new Set(detect.questions || [])].slice(0, 60);
  const answers = {};
  if (questions.length) for (const a of await jobpilot.answers(questions)) answers[a.question] = a;
  let tracking = null;
  if (userJobId) {
    try { tracking = await jobpilot.start(userJobId); } catch (e) { tracking = { error: e.message }; }
  }
  const report = await run(tabId, frameId, (payload) => globalThis.__jobpilot.fill(payload),
                           [{ fields: profile.fields, answers, overwrite: Boolean(overwrite) }]);
  return { report, missing: profile.missing, tracking };
}

async function attachResume({ tabId, frameId, replace }) {
  const file = await jobpilot.resume();
  const payload = { name: file.name, type: file.type, b64: toBase64(file.buf) };
  return run(tabId, frameId, (f, opts) => globalThis.__jobpilot.attachResume(f, opts), [payload, { replace: Boolean(replace) }]);
}

async function downloadResume() {
  const file = await jobpilot.resume();
  return { name: file.name, type: file.type, b64: toBase64(file.buf) };
}

async function setApiBase({ url }) {
  if (!url) { await vault.remove("apiBaseOverride"); await vault.remove("apiBase"); return { ok: true }; }
  const base = validApiBase(url);
  if (!base) throw new ApiError(0, "Use an https:// address (or http://localhost for local development).");
  await vault.set("apiBaseOverride", base);
  return { ok: true, base };
}

const ACTIONS = {
  state,
  inspect,
  fill,
  attachResume,
  downloadResume,
  setApiBase,
  pair: ({ code, deviceName }) => jobpilot.pair(String(code || ""), String(deviceName || "Chrome").slice(0, 100)).then((t) => ({ user: t.user_display_name, expiresAt: t.expires_at })),
  disconnect: () => jobpilot.disconnect().then(() => ({ ok: true })),
  forget: () => forget().then(() => ({ ok: true })),
  confirm: ({ applicationId, submitted, referenceId }) => jobpilot.confirm(Number(applicationId), Boolean(submitted), referenceId ? String(referenceId).slice(0, 200) : null),
  apiBase: () => apiBase().then((base) => ({ base })),
};

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (!fromPopup(sender) || !msg || typeof msg.action !== "string" || !Object.hasOwn(ACTIONS, msg.action)) {
    reply({ ok: false, error: "Not allowed." });
    return false;
  }
  ACTIONS[msg.action](msg.args || {})
    .then((data) => reply({ ok: true, data }))
    .catch((e) => reply({ ok: false, error: e instanceof ApiError || e instanceof Error ? e.message : "Something went wrong.", status: e?.status ?? 0 }));
  return true;  // async reply
});

// Nobody else may talk to the extension.
chrome.runtime.onMessageExternal?.addListener((_m, _s, reply) => reply({ ok: false }));
