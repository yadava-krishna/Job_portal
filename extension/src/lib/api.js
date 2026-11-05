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

async function request(path, { method = "GET", body, auth = true, raw = false, retried = false } = {}) {
  const base = await apiBase();
  const headers = { "ngrok-skip-browser-warning": "true" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = await vault.get("token");
    if (!token) throw new ApiError(401, "Not connected");
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
      return request(path, { method, body, auth, raw, retried: true });
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
}

export const jobpilot = {
  async pair(code, deviceName) {
    const t = await request("/extension/pair", { method: "POST", body: { code, device_name: deviceName }, auth: false });
    await remember(t);
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
  answers: (questions) => request("/extension/answers", { method: "POST", body: { questions } }),
  start: (userJobId) => request("/extension/applications/start", { method: "POST", body: { user_job_id: userJobId } }),
  confirm: (applicationId, submitted, referenceId) =>
    request(`/extension/applications/${applicationId}/confirm`, { method: "POST", body: { submitted, reference_id: referenceId || null } }),
  async resume() {
    const res = await request("/extension/resume", { raw: true });
    const cd = res.headers.get("content-disposition") || "";
    const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
    const name = m ? decodeURIComponent(m[1]) : "resume.pdf";
    const buf = await res.arrayBuffer();
    return { name, type: res.headers.get("content-type") || "application/pdf", buf };
  },
};
