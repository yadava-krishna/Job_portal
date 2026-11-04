// Resolves which backend this frontend talks to.
//
// The backend runs on the owner's machine behind ngrok, whose free URL can change.
// Order of precedence:
//   1. ?api=https://... in the page URL (saved for later visits)
//   2. a URL the user saved in Connection settings (localStorage)
//   3. config.json published next to the app (updated by deploy/start.sh)
//   4. VITE_API_BASE_URL at build time
// This only decides *where* to look. Whether the backend is online is decided by
// polling its /api/v1/health endpoint (see ConnectionContext).

const STORAGE_KEY = "jobpilot.apiBaseUrl";

export function normalizeBaseUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  const v = value.trim().replace(/\/+$/, "").replace(/\/api\/v1$/, "");
  if (!v) return null;
  try {
    const u = new URL(v);
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    return u.origin + u.pathname.replace(/\/+$/, "");
  } catch {
    return null;
  }
}

function readStored(): string | null {
  try {
    return normalizeBaseUrl(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

export function saveBaseUrl(url: string | null): void {
  try {
    if (url) localStorage.setItem(STORAGE_KEY, url);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: keep in memory only */
  }
}

export function storedBaseUrl(): string | null {
  return readStored();
}

export function queryParamBaseUrl(): string | null {
  const search = window.location.search || window.location.hash.split("?")[1] || "";
  const params = new URLSearchParams(search.startsWith("?") ? search : `?${search}`);
  return normalizeBaseUrl(params.get("api"));
}

export async function publishedBaseUrl(): Promise<string | null> {
  try {
    const res = await fetch(`./config.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) return null;
    const data = (await res.json()) as { apiBaseUrl?: string };
    return normalizeBaseUrl(data.apiBaseUrl);
  } catch {
    return null;
  }
}

export function buildTimeBaseUrl(): string | null {
  const env = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL as string | undefined);
  if (env) return env;
  // Served by the local nginx container (same origin proxies /api): use the page's own origin.
  if (import.meta.env.VITE_SAME_ORIGIN_API === "true") return window.location.origin;
  return null;
}

export interface ResolvedBaseUrl {
  url: string | null;
  source: "query" | "saved" | "published" | "build" | "none";
}

export async function resolveBaseUrl(): Promise<ResolvedBaseUrl> {
  const q = queryParamBaseUrl();
  if (q) {
    saveBaseUrl(q);
    return { url: q, source: "query" };
  }
  const saved = readStored();
  if (saved) return { url: saved, source: "saved" };
  const published = await publishedBaseUrl();
  if (published) return { url: published, source: "published" };
  const build = buildTimeBaseUrl();
  if (build) return { url: build, source: "build" };
  return { url: null, source: "none" };
}
