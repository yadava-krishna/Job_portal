import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { JobCard } from "@/components/app/JobCard";
import { FeedEmptyState, RunSummary, SourceHealthList } from "@/components/app/discovery";
import { postedDisplay, seenOn } from "@/lib/format";
import type { DiscoveryRun, SourceHealth, UserJob } from "@/types/api";

const run = (over: Partial<DiscoveryRun> = {}): DiscoveryRun => ({
  id: 1, trigger: "manual", status: "completed", sources: ["all"], started_at: "2026-11-04T10:00:00Z", completed_at: "2026-11-04T10:01:00Z",
  jobs_found: 0, jobs_new: 0, jobs_matched: 0, duplicates: 0, error_details: [], platform_stats: {}, source_results: {}, summary: null, ...over,
});

const job = (over: Partial<UserJob["job"]> = {}, item: Partial<UserJob> = {}): UserJob => ({
  user_job_id: 7, status: "new", is_saved: false, match_score: 82, match_category: "good", matching_skills: ["Accounts Receivable"],
  missing_skills: ["SAP"], eligibility_status: "ELIGIBLE", scoring_method: "rule_based", discovered_at: new Date().toISOString(),
  saved_at: null, dismissed_at: null, application_id: null, application_status: null, ...item,
  job: {
    id: 3, platform: "Greenhouse", external_job_id: "101", company: "Acme Fintech", title: "AR Analyst", location: "Bengaluru", work_mode: "Hybrid",
    employment_type: "Full-time", experience_required: "3-6 years", salary_range: null, job_url: "https://job-boards.greenhouse.io/acme/jobs/101",
    posted_at: "2026-11-03", posted_at_source: "platform_api", posted_label: "Yesterday", description_preview: "Payment posting and collections.",
    has_full_description: true, source: "greenhouse", posted_at_confidence: "verified", first_seen_at: new Date().toISOString(),
    last_verified_at: null, closed_at: null, industry: "Fintech", department: "Finance",
    sources: [{ source: "greenhouse", platform: "Greenhouse", url: "https://job-boards.greenhouse.io/acme/jobs/101", first_seen_at: "" }], ...over,
  },
});

const noop = { onView: vi.fn(), onSave: vi.fn(), onApply: vi.fn(), onDismiss: vi.fn() };

describe("posting dates are never misrepresented", () => {
  it("labels verified, estimated and unknown dates", () => {
    expect(postedDisplay({ posted_at: "2026-11-04", posted_label: "Today", posted_at_confidence: "verified", platform: "Lever" }))
      .toMatchObject({ text: "Posted today", badge: "Verified" });
    expect(postedDisplay({ posted_at: "2026-11-02", posted_label: "On or before 02 Nov (alert email)", posted_at_confidence: "estimated", platform: "LinkedIn" }).badge)
      .toBe("Estimated");
    // Even if a label said "Today", a job without a posting date is shown as unknown.
    expect(postedDisplay({ posted_at: null, posted_label: "Today", posted_at_confidence: "verified", platform: "Ashby" }))
      .toMatchObject({ text: "Posting date unknown", badge: "Unknown" });
  });

  it("shows confidence, every source, discovery time and closed status on the card", () => {
    const item = job({ platform: "LinkedIn", closed_at: "2026-11-04T09:00:00Z",
      sources: [{ source: "browser_clipper", platform: "LinkedIn", url: null, first_seen_at: "" }, { source: "greenhouse", platform: "Greenhouse", url: null, first_seen_at: "" }] });
    render(<JobCard item={item} actions={noop} />);
    expect(screen.getByTestId("posted-confidence")).toHaveTextContent("Verified");
    expect(screen.getByText("LinkedIn")).toBeInTheDocument();
    expect(screen.getByText("Greenhouse")).toBeInTheDocument();
    expect(screen.getByText(/No longer listed/)).toBeInTheDocument();
    expect(screen.getByText(/Found just now/)).toBeInTheDocument();
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(seenOn(item.job)).toEqual(["LinkedIn", "Greenhouse"]);
  });

  it("an unknown date reads as unknown on the card", () => {
    render(<JobCard item={job({ posted_at: null, posted_label: "Unknown", posted_at_confidence: "unknown" })} actions={noop} />);
    expect(screen.getByText("Posting date unknown")).toBeInTheDocument();
    expect(screen.getByTestId("posted-confidence")).toHaveTextContent("Unknown");
  });

  it("Apply opens the dialog instead of marking anything applied", () => {
    const actions = { ...noop, onApply: vi.fn() };
    render(<JobCard item={job()} actions={actions} />);
    fireEvent.click(screen.getByRole("button", { name: /Apply/ }));
    expect(actions.onApply).toHaveBeenCalledTimes(1);
  });
});

describe("discovery outcomes are explained", () => {
  it("lists every source with its own status and reason", () => {
    render(<RunSummary run={run({
      status: "partial", summary: "Checked Greenhouse, Lever (12 company boards, 900 listings). 5 matching jobs: 5 new, 0 already in your feed.",
      source_results: {
        greenhouse: { label: "Greenhouse", status: "ok", message: null, found: 5, new: 5, duplicates: 0, failed_requests: 0, boards_ok: 10, listings_checked: 800 },
        lever: { label: "Lever", status: "partial", message: "1 board could not be read: Gone Ltd (board not found).", found: 0, new: 0, duplicates: 0, failed_requests: 1, boards_ok: 1, boards_failed: 1 },
        adzuna_api: { label: "Adzuna", status: "not_configured", message: "Adzuna API credentials are not configured on this server (ADZUNA_APP_ID / ADZUNA_APP_KEY).", found: 0, new: 0, duplicates: 0, failed_requests: 0 },
      },
    })} />);
    const box = screen.getByTestId("run-summary");
    expect(within(box).getByText("Completed with problems")).toBeInTheDocument();
    expect(within(box).getByText(/5 matching jobs/)).toBeInTheDocument();
    expect(within(box).getByText("Partly failed")).toBeInTheDocument();
    expect(within(box).getByText(/Gone Ltd \(board not found\)/)).toBeInTheDocument();
    // Problems are always listed; the sources that worked (or were skipped) are one click away.
    expect(within(box).queryByText("Not configured")).not.toBeInTheDocument();
    fireEvent.click(within(box).getByRole("button", { name: "Show all 3 sources" }));
    expect(within(box).getByText("Not configured")).toBeInTheDocument();
    expect(within(box).getByText(/ADZUNA_APP_ID/)).toBeInTheDocument();
    expect(within(box).getByText(/10 boards read · 800 listings checked · 5 matched · 5 new/)).toBeInTheDocument();
  });

  it("a failed run is never shown as completed", () => {
    render(<RunSummary run={run({ status: "failed", summary: "Discovery could not run. Adzuna: credentials missing." })} />);
    expect(screen.getByText("Could not run")).toBeInTheDocument();
    expect(screen.queryByText("Completed")).not.toBeInTheDocument();
  });

  const empty = (props: Partial<Parameters<typeof FeedEmptyState>[0]>) =>
    render(<MemoryRouter><FeedEmptyState lastRun={null} filtered={false} running={false} onRun={vi.fn()} onClearFilters={vi.fn()} {...props} /></MemoryRouter>);

  it("explains each kind of empty feed", () => {
    const { unmount } = empty({});
    expect(screen.getByText("Discovery hasn't run yet")).toBeInTheDocument();
    unmount();
    const r1 = empty({ running: true });
    expect(screen.getByText("Discovery is running")).toBeInTheDocument();
    r1.unmount();
    const r2 = empty({ lastRun: run({ status: "failed", summary: "Discovery could not run. No companies to search." }) });
    expect(screen.getByText(/could not search anything/)).toBeInTheDocument();
    expect(screen.getByText(/No companies to search/)).toBeInTheDocument();
    r2.unmount();
    const r3 = empty({ lastRun: run({ summary: "Checked Greenhouse. No listings matched your titles and locations right now." }) });
    expect(screen.getByText("No matching jobs found yet")).toBeInTheDocument();
    r3.unmount();
    const onClear = vi.fn();
    empty({ filtered: true, onClearFilters: onClear, lastRun: run() });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(onClear).toHaveBeenCalled();
  });

  it("offers to run discovery when it never ran", () => {
    const onRun = vi.fn();
    empty({ onRun });
    fireEvent.click(screen.getByRole("button", { name: /Run discovery now/ }));
    expect(onRun).toHaveBeenCalled();
  });
});

describe("source health panel", () => {
  const base: SourceHealth = {
    key: "greenhouse", label: "Greenhouse job boards", kind: "ats", enabled: true, configured: true, missing: null, connection: "ok",
    last_attempt_at: new Date().toISOString(), last_success_at: new Date().toISOString(), last_error: null, jobs_in_feed: 12,
    boards: { total: 18, ok: 17, failing: 1, unchecked: 0 }, last_run: null,
  };
  it("shows configuration, connection, timing, counts and missing credentials", () => {
    render(<SourceHealthList sources={[
      base,
      { ...base, key: "adzuna_api", label: "Adzuna Jobs API", kind: "api", configured: false, connection: "not_configured", boards: null, jobs_in_feed: 0,
        missing: "Server credentials are missing: set ADZUNA_APP_ID and ADZUNA_APP_KEY in the backend's .env and restart it.", last_attempt_at: null, last_success_at: null },
      { ...base, key: "lever", label: "Lever job boards", connection: "failing", last_error: "Job board timed out.", jobs_in_feed: 0, boards: { total: 2, ok: 0, failing: 2, unchecked: 0 } },
    ]} />);
    const panel = screen.getByTestId("source-health");
    expect(within(panel).getByText("Connected")).toBeInTheDocument();
    expect(within(panel).getByText(/18 company boards: 17 OK, 1 failing/)).toBeInTheDocument();
    expect(within(panel).getByText("12")).toBeInTheDocument();
    expect(within(panel).getByText("Not configured")).toBeInTheDocument();
    expect(within(panel).getByText(/ADZUNA_APP_ID and ADZUNA_APP_KEY/)).toBeInTheDocument();
    expect(within(panel).getAllByText("never").length).toBe(2);
    expect(within(panel).getByText("Failing")).toBeInTheDocument();
    expect(within(panel).getByText(/Job board timed out/)).toBeInTheDocument();
  });
});
