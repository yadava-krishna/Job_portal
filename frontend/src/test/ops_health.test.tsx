import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn(), patch: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), api }));

import { OpsHealthPanel } from "@/features/growth/OpsHealth";
import type { OpsHealth } from "@/features/growth/types";

const wrap = (ui: ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>,
);
beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));

const base: OpsHealth = {
  generated_at: "2026-11-17T10:00:00Z",
  attention: [],
  disks: [
    { label: "Data (resumes, exports, reports, logs)", path: "/data", available: true, total_gb: 100, used_gb: 40, free_gb: 60, used_percent: 40, level: "ok" },
    { label: "Backups", path: "/backups", available: false, note: "Not available: this folder isn't mounted here." },
  ],
  database: { available: true, dialect: "postgresql", server_version: "16.4", latency_ms: 1.2, migration: "0011", size_bytes: 52_428_800, connections: 4,
              largest_tables: [{ table: "jobs", bytes: 31_457_280, rows_estimate: 12000 }] },
  backups: { available: true, level: "warning", count: 3, daily_count: 2, stale_after_hours: 26, last_status: "ok",
             newest: { name: "daily-20261115T023000Z", at: "2026-11-15T02:30:00Z", age_hours: 55, size_bytes: 10_485_760 },
             note: "The newest backup is more than 26 hours old. Check that the backup service is running." },
  background_jobs: { failed_count: 1, by_name: [{ name: "job_matching", failures: 1, last_failed_at: "2026-11-17T06:00:00Z" }],
                     recent: [{ name: "job_matching", status: "failed", trigger: "schedule", started_at: "2026-11-17T06:00:00Z", attempts: 3, error: "OperationalError: [redacted]" }],
                     stuck: [] },
  discovery: { by_status: { completed: 9, failed: 1 }, failed: 1, stuck_running: 0, failure_types: [{ type: "INTERRUPTED", count: 1 }] },
  workflows: { run_errors: [], apply_failed: 0, apply_uncertain: 1, apply_needs_information: 0 },
  sources: [{ key: "lever", name: "Lever", kind: "ats", enabled: true, health: "degraded", state: "failing", last_run_at: null,
              last_success_at: "2026-11-13T00:00:00Z", hours_since_success: 100, last_error: null, runs_7d: 5, failures_7d: 2,
              last_failed_at: "2026-11-17T05:00:00Z", last_failure: "HTTP 503" }],
  source_freshness: [{ source: "greenhouse", open_jobs: 420, newest_discovered_at: "2026-11-17T04:00:00Z", last_verified_at: "2026-11-17T04:00:00Z", hours_since_verified: 6 }],
  user_activity: { accounts: 12, active_accounts: 11, logins_24h: 3, logins_7d: 8, logins_30d: 10, active_users_7d: 7, signups_7d: 1, discovery_runs_7d: 10, applications_submitted_7d: 4 },
  extension: { connected_devices: 2, used_24h: 1, used_7d: 2, unused_30d: 0, expired: 0, bundled_version: "2.0.0", version_reporting: false,
               note: "The extension doesn't send its version to the server yet." },
};

describe("admin operational health", () => {
  it("shows disks, database, backups, failures, sources and activity, with not-available checks", async () => {
    api.get.mockResolvedValue({ data: { ...base, attention: [{ level: "warning", text: "Sources not succeeding recently: Lever." }] } });
    wrap(<OpsHealthPanel />);
    expect(await screen.findByText("Sources not succeeding recently: Lever.")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/admin/ops-health");
    expect(screen.getByText("Not available: this folder isn't mounted here.")).toBeInTheDocument();
    expect(screen.getByText("50 MB")).toBeInTheDocument();
    expect(screen.getByText("jobs")).toBeInTheDocument();
    expect(screen.getByText(/more than 26 hours old/)).toBeInTheDocument();
    expect(screen.getByText("daily-20261115T023000Z")).toBeInTheDocument();
    expect(screen.getByText("OperationalError: [redacted]")).toBeInTheDocument();
    expect(screen.getByText("HTTP 503")).toBeInTheDocument();
    expect(screen.getByText("2 / 5")).toBeInTheDocument();
    expect(screen.getByText("420")).toBeInTheDocument();
    expect(screen.getByText("2.0.0")).toBeInTheDocument();
  });

  it("says when nothing needs attention and when a whole check is unavailable", async () => {
    api.get.mockResolvedValue({ data: { ...base, database: { available: false, note: "Not available: the database did not answer." } } });
    wrap(<OpsHealthPanel />);
    expect(await screen.findByText("Nothing needs attention.")).toBeInTheDocument();
    expect(screen.getByText("Not available: the database did not answer.")).toBeInTheDocument();
  });
});
