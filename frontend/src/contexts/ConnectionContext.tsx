import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { setApiBaseUrl, setNetworkErrorHandler } from "@/lib/api";
import { normalizeBaseUrl, publishedBaseUrl, resolveBaseUrl, saveBaseUrl, storedBaseUrl, type ResolvedBaseUrl } from "@/lib/config";
import type { Health } from "@/types/api";

// The backend is the source of truth for availability: the portal is "online" only when
// GET /api/v1/health on the configured backend answers as the JobPilot service with a working
// database. A running frontend (or a reachable ngrok edge returning its own error page) is not enough.

export type ConnectionState = "resolving" | "checking" | "online" | "degraded" | "offline" | "unconfigured";

interface ConnectionValue {
  state: ConnectionState;
  baseUrl: string | null;
  baseUrlSource: ResolvedBaseUrl["source"];
  health: Health | null;
  lastOnlineAt: number | null;
  lastCheckedAt: number | null;
  lastError: string | null;
  consecutiveFailures: number;
  retry: () => void;
  setBaseUrl: (url: string | null) => Promise<boolean>;
  /** Increments every time the backend comes back after being unavailable. */
  reconnectCount: number;
}

const ConnectionContext = createContext<ConnectionValue | null>(null);

export const ONLINE_POLL_MS = 10_000;
export const OFFLINE_POLL_MS = 5_000;
export const HEALTH_TIMEOUT_MS = 4_000;
export const FAILURES_BEFORE_OFFLINE = 2;

export async function probeHealth(baseUrl: string, timeoutMs = HEALTH_TIMEOUT_MS): Promise<Health> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${baseUrl}/api/v1/health?t=${Date.now()}`, {
      signal: controller.signal,
      cache: "no-store",
      headers: { "ngrok-skip-browser-warning": "true", Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`Backend answered HTTP ${res.status}`);
    const type = res.headers.get("content-type") ?? "";
    if (!type.includes("application/json")) throw new Error("The tunnel is up but the backend is not responding");
    const body = (await res.json()) as Health;
    if (body.service !== "jobpilot-backend") throw new Error("Unexpected service at this address");
    return body;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw new Error(`No response within ${timeoutMs / 1000}s`);
    if (err instanceof TypeError) throw new Error("Backend unreachable");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export function ConnectionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConnectionState>("resolving");
  const [baseUrl, setBase] = useState<string | null>(null);
  const [baseUrlSource, setSource] = useState<ResolvedBaseUrl["source"]>("none");
  const [health, setHealth] = useState<Health | null>(null);
  const [lastOnlineAt, setLastOnlineAt] = useState<number | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<number | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [failures, setFailures] = useState(0);
  const [reconnectCount, setReconnectCount] = useState(0);
  const stateRef = useRef<ConnectionState>("resolving");
  const failuresRef = useRef(0);
  const baseRef = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const checking = useRef(false);

  const applyBase = useCallback((url: string | null, source: ResolvedBaseUrl["source"]) => {
    baseRef.current = url;
    setBase(url);
    setSource(source);
    setApiBaseUrl(url);
  }, []);

  const setStateBoth = (s: ConnectionState) => {
    stateRef.current = s;
    setState(s);
  };

  const check = useCallback(async () => {
    if (checking.current) return;
    checking.current = true;
    try {
      let url = baseRef.current;
      // While unreachable, pick up a re-published ngrok address (unless the user pinned one).
      if ((!url || failuresRef.current > 0) && !storedBaseUrl()) {
        const published = await publishedBaseUrl();
        if (published && published !== url) {
          applyBase(published, "published");
          url = published;
        }
      }
      if (!url) {
        setStateBoth("unconfigured");
        return;
      }
      if (stateRef.current === "resolving") setStateBoth("checking");
      const h = await probeHealth(url);
      const wasDown = ["offline", "degraded", "checking", "unconfigured"].includes(stateRef.current) && failuresRef.current > 0;
      setHealth(h);
      setLastCheckedAt(Date.now());
      if (h.status === "ok" && h.database.connected) {
        failuresRef.current = 0;
        setFailures(0);
        setLastError(null);
        setLastOnlineAt(Date.now());
        if (stateRef.current !== "online") {
          setStateBoth("online");
          if (wasDown) setReconnectCount((c) => c + 1);
        }
      } else {
        failuresRef.current += 1;
        setFailures(failuresRef.current);
        setLastError("The backend is running but its database is unavailable");
        setStateBoth("degraded");
      }
    } catch (err) {
      failuresRef.current += 1;
      setFailures(failuresRef.current);
      setLastCheckedAt(Date.now());
      setLastError(err instanceof Error ? err.message : "Backend unreachable");
      // One missed beat (e.g. a slow request) does not take the portal offline.
      if (failuresRef.current >= FAILURES_BEFORE_OFFLINE || stateRef.current !== "online") setStateBoth("offline");
    } finally {
      checking.current = false;
    }
  }, [applyBase]);

  const schedule = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    const delay = stateRef.current === "online" ? ONLINE_POLL_MS : OFFLINE_POLL_MS;
    timer.current = setTimeout(async () => {
      await check();
      schedule();
    }, delay);
  }, [check]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const resolved = await resolveBaseUrl();
      if (cancelled) return;
      applyBase(resolved.url, resolved.source);
      await check();
      schedule();
    })();
    const onFocus = () => void check();
    window.addEventListener("focus", onFocus);
    window.addEventListener("online", onFocus);
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("online", onFocus);
    };
  }, [applyBase, check, schedule]);

  // A failed API call (network error) triggers an immediate health check.
  useEffect(() => {
    setNetworkErrorHandler(() => void check());
  }, [check]);

  const retry = useCallback(() => {
    void check().then(schedule);
  }, [check, schedule]);

  const setBaseUrl = useCallback(async (url: string | null) => {
    const normalized = normalizeBaseUrl(url);
    saveBaseUrl(normalized);
    if (normalized) {
      applyBase(normalized, "saved");
    } else {
      const resolved = await resolveBaseUrl();
      applyBase(resolved.url, resolved.source);
    }
    failuresRef.current = 1;
    setStateBoth("checking");
    await check();
    schedule();
    return stateRef.current === "online";
  }, [applyBase, check, schedule]);

  const value = useMemo<ConnectionValue>(() => ({
    state, baseUrl, baseUrlSource, health, lastOnlineAt, lastCheckedAt, lastError, consecutiveFailures: failures, retry, setBaseUrl, reconnectCount,
  }), [state, baseUrl, baseUrlSource, health, lastOnlineAt, lastCheckedAt, lastError, failures, retry, setBaseUrl, reconnectCount]);

  return <ConnectionContext.Provider value={value}>{children}</ConnectionContext.Provider>;
}

export function useConnection(): ConnectionValue {
  const ctx = useContext(ConnectionContext);
  if (!ctx) throw new Error("useConnection must be used inside ConnectionProvider");
  return ctx;
}
