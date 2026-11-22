// JobPilot backend client. Runs in the service worker only; the device credential never leaves it.

import { API_PREFIX, DEFAULT_CONFIG_URL, ROTATE_AFTER_MS, validApiBase } from "./config.js";
import { vault } from "./vault.js";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const TIMEOUT_MS = 20000;
const UNVERIFIED = "JobPilot's published server address could not be verified, so nothing was sent. Reconnect from JobPilot Settings or set the server address manually.";
const enc = (s) => new TextEncoder().encode(s);
const toHex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");

// ---- server identity proof ------------------------------------------------------------------------
// The backend address is published in config.json on GitHub Pages. A tampered file must not receive the device
// credential (or resume downloads), so before the credential goes to an address it has not used before, the extension
// asks that server to prove it issued the credential: HMAC-SHA256 keyed with SHA-256(credential) (which only the
// issuing server stores) over a fresh random nonce. The credential itself is never sent for this.
//
// The proof also names the host it is for ("jobpilot-prove:v2:<host>:<nonce>"). Without that, a tampered address could
// forward the challenge to the real server and pass its answer back (a relay). The real server signs only its own
// host, so a relayed proof names the real host, not the address the credential would go to, and is rejected.

/** A fresh random nonce: 32 bytes as 64 lowercase hex characters. */
export function newNonce() {
  return toHex(crypto.getRandomValues(new Uint8Array(32)));
}

/** The host (name[:port], lowercase) of a server address, as the proof names it. */
export function proofHost(base) {
  try { return new URL(base).host.toLowerCase(); } catch { return ""; }
}

/** The proof the real server at `host` must give for this credential and nonce (lowercase hex). */
export async function expectedProof(token, nonce, host) {
  if (!host) throw new Error("expectedProof needs the server's host");
  const keyBytes = await crypto.subtle.digest("SHA-256", enc(String(token)));
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return toHex(await crypto.subtle.sign("HMAC", key, enc(`jobpilot-prove:v2:${host}:${nonce}`)));
}

/** Constant-time string comparison (same length required). */
export function sameString(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Does `proof` (from the server) match this credential, nonce and host? Pure: no network, no storage. */
export async function verifyProof(token, nonce, proof, host) {
  if (!token || !host || typeof proof !== "string" || !/^[0-9a-f]{64}$/i.test(proof)) return false;
  return sameString(await expectedProof(token, nonce, host), proof.toLowerCase());
}

/** Make sure `base` is the server that issued `token` before sending it there. Throws ApiError(0, UNVERIFIED) if not;
 *  a network failure throws {network: true} so the caller can look the address up again. */
async function ensureVerified(base, token) {
  if ((await vault.get("apiBaseOverride")) === base) return;  // an address the user set themselves
  if ((await vault.get("verifiedBase")) === base) return;
  const info = await vault.get("tokenInfo");
  if (!Number.isInteger(info?.id)) throw new ApiError(0, UNVERIFIED);
  const nonce = newNonce();
  const host = proofHost(base);
  if (!host) throw new ApiError(0, UNVERIFIED);
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  let res;
  try {
    res = await fetch(base + API_PREFIX + "/extension/prove", {
      method: "POST", headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },  // no Authorization
      body: JSON.stringify({ token_id: info.id, nonce, v: 2, host }), signal: ctl.signal, credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
    });
  } catch {
    throw Object.assign(new ApiError(0, "JobPilot is not reachable right now."), { network: true });
  } finally {
    clearTimeout(timer);
  }
  let proof = null;
  if (res.ok) { try { proof = (await res.json())?.proof; } catch { proof = null; } }
  if (!(await verifyProof(token, nonce, proof, host))) throw new ApiError(0, UNVERIFIED);
  await vault.set("verifiedBase", base);
}

/** The backend address: a manual override if set, else the address the JobPilot web app publishes. */
export async function apiBase({ refresh = false } = {}) {
  const manual = await vault.get("apiBaseOverride");
  if (manual) return manual;
  const cached = await vault.get("apiBase");
  if (cached && !refresh) return cached;
  const res = await fetch(`${DEFAULT_CONFIG_URL}?t=${Date.now()}`, { cache: "no-store", credentials: "omit" });
  if (!res.ok) throw new ApiError(0, "Could not find the JobPilot server address.");
  const base = validApiBase((await res.json()).apiBaseUrl);
  if (!base) throw new ApiError(0, "The published JobPilot server address is not a secure (https) address.");
  await vault.set("apiBase", base);
  return base;
}

async function request(path, { method = "GET", body, auth = true, raw = false, retried = false, meta = null } = {}) {
  const base = await apiBase();
  if (meta) meta.base = base;
  const headers = { "ngrok-skip-browser-warning": "true" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = await vault.get("token");
    if (!token) throw new ApiError(401, "Not connected");
    try {
      await ensureVerified(base, token);
    } catch (e) {
      // The tunnel address may have changed since we cached it: look it up again once (and verify the new one).
      if (e.network && !retried && !(await vault.get("apiBaseOverride"))) {
        await apiBase({ refresh: true }).catch(() => null);
        return request(path, { method, body, auth, raw, retried: true, meta });
      }
      throw e;
    }
    headers.Authorization = `Bearer ${token}`;
  }
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  let res;
  try {
    res = await fetch(base + API_PREFIX + path, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: ctl.signal,
      credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
    });
  } catch {
    // The tunnel address may have changed since we cached it: look it up again once.
    if (!retried && !(await vault.get("apiBaseOverride"))) {
      await apiBase({ refresh: true }).catch(() => null);
      return request(path, { method, body, auth, raw, retried: true, meta });
    }
    throw new ApiError(0, "JobPilot is not reachable right now.");
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 401 && auth) {
    await forget();
    throw new ApiError(401, "This browser was disconnected from JobPilot. Connect it again with a new code.");
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    throw new ApiError(res.status, typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

async function remember(t) {
  await vault.set("token", t.token);
  await vault.set("tokenInfo", { id: t.token_id, expiresAt: t.expires_at, issuedAt: Date.now(), user: t.user_display_name });
}

export async function forget() {
  await vault.remove("token");
  await vault.remove("tokenInfo");
  await vault.remove("verifiedBase");
}

export const jobpilot = {
  async pair(code, deviceName) {
    const meta = {};
    const t = await request("/extension/pair", { method: "POST", body: { code, device_name: deviceName }, auth: false, meta });
    await remember(t);
    await vault.set("verifiedBase", meta.base);  // the server that just issued this credential
    return t;
  },
  async connected() {
    return Boolean(await vault.get("token"));
  },
  async info() {
    return (await vault.get("tokenInfo")) ?? null;
  },
  async rotateIfDue() {
    const info = await vault.get("tokenInfo");
    if (!info || Date.now() - info.issuedAt < ROTATE_AFTER_MS) return false;
    await remember(await request("/extension/rotate", { method: "POST" }));
    return true;
  },
  async disconnect() {
    try { await request("/extension/disconnect", { method: "POST" }); } finally { await forget(); }
  },
  status: () => request("/extension/status"),
  match: (url) => request("/extension/match", { method: "POST", body: { url } }),
  profile: () => request("/extension/autofill-profile"),
  /** Answers for the form's questions; with applicationId the server adds the employer context and this application's own answers. */
  /** requirements: {label: "required" | "optional"} as the form marks them (labels not listed are unknown). */
  answers: (questions, applicationId, requirements = {}) => request("/extension/answers", { method: "POST",
    body: { questions, ...(Number.isInteger(applicationId) ? { application_id: applicationId } : {}),
            ...(Object.keys(requirements).length ? { requirements } : {}) } }),
  /** Save answers the user ticked "save for next time" in the review panel: {saved: [question], errors: [{question, error}]}. */
  learn: (applicationId, items) => request("/extension/answers/learn", { method: "POST",
    body: Number.isInteger(applicationId) ? { application_id: applicationId, items } : { items } }),
  /** The application's package: {resume: {kind, id, format, name}|null, cover_letter, destination_url, action, overrides}. */
  package: (applicationId) => request(`/extension/applications/${applicationId}/package`),
  start: (userJobId) => request("/extension/applications/start", { method: "POST", body: { user_job_id: userJobId } }),
  confirm: (applicationId, submitted, referenceId) =>
    request(`/extension/applications/${applicationId}/confirm`, { method: "POST", body: { submitted, reference_id: referenceId || null } }),
  state: (applicationId, body) => request(`/extension/applications/${applicationId}/state`, { method: "POST", body }),
  application: (applicationId) => request(`/extension/applications/${applicationId}`),
  resumes: () => request("/extension/resumes"),
  /** The chosen resume file: {kind: "upload"|"studio", id?, format?: "pdf"|"docx"} (default: the active upload). */
  async resume(choice = { kind: "upload" }) {
    const q = new URLSearchParams({ kind: choice.kind || "upload", format: choice.format || "pdf" });
    if (Number.isInteger(choice.id)) q.set("id", String(choice.id));
    const res = await request(`/extension/resume?${q}`, { raw: true });
    const cd = res.headers.get("content-disposition") || "";
    const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
    const name = m ? decodeURIComponent(m[1]) : `resume.${choice.format || "pdf"}`;
    const buf = await res.arrayBuffer();
    return { name, type: (res.headers.get("content-type") || "application/pdf").split(";")[0], buf, sha256: res.headers.get("x-resume-sha256") || null };
  },
};
