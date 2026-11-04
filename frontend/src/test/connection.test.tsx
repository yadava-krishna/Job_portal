import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConnectionProvider, FAILURES_BEFORE_OFFLINE, OFFLINE_POLL_MS, ONLINE_POLL_MS, probeHealth, useConnection } from "@/contexts/ConnectionContext";

const BASE = "https://backend.example.test";
const healthy = { status: "ok", service: "jobpilot-backend", version: "1.0.0", timestamp: "", database: { connected: true, error: null }, scheduler: { enabled: true, running: true, next_run: null, last_run: null } };

let backendUp = true;
let dbUp = true;

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("config.json")) return new Response(JSON.stringify({ apiBaseUrl: BASE }), { headers: { "content-type": "application/json" } });
    if (!backendUp) throw new TypeError("Failed to fetch");
    const body = { ...healthy, status: dbUp ? "ok" : "degraded", database: { connected: dbUp, error: dbUp ? null : "OperationalError" } };
    return new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } });
  });
}

function Probe() {
  const c = useConnection();
  return <div><span data-testid="state">{c.state}</span><span data-testid="reconnects">{c.reconnectCount}</span><span data-testid="base">{c.baseUrl}</span></div>;
}

async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("backend availability", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    backendUp = true;
    dbUp = true;
    localStorage.clear();
    vi.stubGlobal("fetch", mockFetch());
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("uses the published backend address and reports online from /health", async () => {
    render(<ConnectionProvider><Probe /></ConnectionProvider>);
    await flush();
    expect(screen.getByTestId("state").textContent).toBe("online");
    expect(screen.getByTestId("base").textContent).toBe(BASE);
  });

  it("goes offline after consecutive failed health checks and reconnects automatically", async () => {
    render(<ConnectionProvider><Probe /></ConnectionProvider>);
    await flush();
    expect(screen.getByTestId("state").textContent).toBe("online");

    backendUp = false;
    await flush(ONLINE_POLL_MS);
    // one missed beat is tolerated
    expect(FAILURES_BEFORE_OFFLINE).toBeGreaterThan(1);
    await flush(ONLINE_POLL_MS + OFFLINE_POLL_MS);
    expect(screen.getByTestId("state").textContent).toBe("offline");

    backendUp = true;
    await flush(OFFLINE_POLL_MS);
    expect(screen.getByTestId("state").textContent).toBe("online");
    expect(Number(screen.getByTestId("reconnects").textContent)).toBe(1);
  });

  it("treats a running backend with a broken database as unavailable", async () => {
    dbUp = false;
    render(<ConnectionProvider><Probe /></ConnectionProvider>);
    await flush();
    expect(screen.getByTestId("state").textContent).toBe("degraded");
  });

  it("is unconfigured when no backend address exists anywhere", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) =>
      String(input).includes("config.json") ? new Response(JSON.stringify({ apiBaseUrl: "" }), { headers: { "content-type": "application/json" } }) : new Response("", { status: 500 })));
    render(<ConnectionProvider><Probe /></ConnectionProvider>);
    await flush();
    expect(screen.getByTestId("state").textContent).toBe("unconfigured");
  });
});

describe("probeHealth", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("rejects an ngrok/proxy error page that is not the JobPilot backend", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>ERR_NGROK_3200</html>", { status: 404, headers: { "content-type": "text/html" } })));
    await expect(probeHealth(BASE)).rejects.toThrow(/HTTP 404/);
  });

  it("rejects a JSON answer from a different service", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ service: "other" }), { headers: { "content-type": "application/json" } })));
    await expect(probeHealth(BASE)).rejects.toThrow(/Unexpected service/);
  });
});
