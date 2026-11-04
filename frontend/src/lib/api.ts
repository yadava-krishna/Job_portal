import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";
import type { AuthResponse } from "@/types/api";

// Tokens: the access token lives only in memory; the refresh token is kept in localStorage so a
// session survives reloads and backend restarts. (The frontend and backend are on different sites
// - github.io and ngrok - where third-party cookies are unreliable, so bearer tokens are used.)
const REFRESH_KEY = "jobpilot.refreshToken";
let accessToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;
let onAuthLost: (() => void) | null = null;
let onNetworkError: (() => void) | null = null;

export const tokens = {
  get access() {
    return accessToken;
  },
  get refresh(): string | null {
    try {
      return localStorage.getItem(REFRESH_KEY);
    } catch {
      return null;
    }
  },
  set(auth: AuthResponse | null) {
    accessToken = auth?.access_token ?? null;
    try {
      if (auth) localStorage.setItem(REFRESH_KEY, auth.refresh_token);
      else localStorage.removeItem(REFRESH_KEY);
    } catch {
      /* ignore */
    }
  },
};

export function setAuthLostHandler(fn: () => void) {
  onAuthLost = fn;
}
export function setNetworkErrorHandler(fn: () => void) {
  onNetworkError = fn;
}

let baseUrl: string | null = null;
export function setApiBaseUrl(url: string | null) {
  baseUrl = url;
  api.defaults.baseURL = url ? `${url}/api/v1` : undefined;
}
export function getApiBaseUrl() {
  return baseUrl;
}

export const api: AxiosInstance = axios.create({
  timeout: 30_000,
  headers: { "ngrok-skip-browser-warning": "true" },
});

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});

export async function refreshAccessToken(): Promise<string | null> {
  const rt = tokens.refresh;
  if (!rt || !baseUrl) return null;
  if (!refreshInFlight) {
    refreshInFlight = axios
      .post<AuthResponse>(`${baseUrl}/api/v1/auth/refresh`, { refresh_token: rt }, {
        timeout: 10_000,
        headers: { "ngrok-skip-browser-warning": "true" },
      })
      .then((r) => {
        tokens.set(r.data);
        return r.data.access_token;
      })
      .catch((err: AxiosError) => {
        // Only an explicit rejection ends the session; a network failure keeps the refresh token.
        if (err.response && (err.response.status === 401 || err.response.status === 403)) tokens.set(null);
        return null;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    if (!error.response) {
      onNetworkError?.();
      return Promise.reject(error);
    }
    const isAuthCall = original?.url?.includes("/auth/");
    if (error.response.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true;
      const token = await refreshAccessToken();
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      }
      onAuthLost?.();
    }
    return Promise.reject(error);
  },
);

export function errorMessage(err: unknown, fallback = "Something went wrong"): string {
  if (axios.isAxiosError(err)) {
    if (!err.response) return "The job portal backend is not reachable.";
    const data = err.response.data as { detail?: unknown; errors?: { field: string; message: string }[] } | undefined;
    if (data?.errors?.length) return data.errors.map((e) => `${e.field || "input"}: ${e.message}`).join("; ");
    if (typeof data?.detail === "string") return data.detail;
    if (data?.detail && typeof data.detail === "object") {
      const d = data.detail as { message?: string; requirements?: string[] };
      if (d.requirements) return `${d.message ?? "Invalid input"} Needs: ${d.requirements.join(", ")}.`;
      if (d.message) return d.message;
    }
    if (err.response.status === 429) return "Too many attempts. Please wait a minute and try again.";
    return `${fallback} (HTTP ${err.response.status})`;
  }
  return err instanceof Error ? err.message : fallback;
}

/** Download an authenticated file (resume, Excel report) without exposing tokens in URLs. */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const res = await api.get(path, { responseType: "blob", timeout: 120_000 });
  const disposition = String(res.headers["content-disposition"] ?? "");
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const name = match ? decodeURIComponent(match[1]) : fallbackName;
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
