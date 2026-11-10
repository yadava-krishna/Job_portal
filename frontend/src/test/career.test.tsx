import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn(), previewFile: vi.fn() }));

import { CareerSnapshotCard } from "@/features/career/SnapshotCard";
import { LearningTab } from "@/features/career/LearningTab";
import { SkillsTab } from "@/features/career/SkillsTab";
import { InternationalPage } from "@/pages/InternationalPage";
import type { CareerSnapshot, Gap } from "@/features/career/types";

const wrap = (ui: ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));

const gap: Gap = {
  id: 5, skill: "SAP FICO", severity: "high", explanation: "Asked for in 4 of your top matches.", next_action: "Finish an SAP FICO basics course.",
  evidence_state: null, status: "open", job_count: 4, rejection_count: 0,
};

const snapshot = (over: Partial<CareerSnapshot> = {}): CareerSnapshot => ({
  stage: "exploring",
  profile_completeness: { percent: 80, missing: ["summary", "experience_or_projects"] },
  top_matches: [
    { user_job_id: 11, title: "AR Analyst", company: "Acme", score: 82, eligibility: "pass", score_version: "v2" },
    { user_job_id: 12, title: "AP Executive", company: "Globex", score: 74, eligibility: "unknown", score_version: "v2" },
    { user_job_id: 13, title: "Finance Associate", company: "Initech", score: 70, eligibility: null, score_version: "v2" },
  ],
  top_gap: gap,
  alternative_gaps: [],
  counts: { applications_submitted: 0, applications_in_progress: 0, upcoming_interviews: 0 },
  show: { tracker: false, interview_prep: false, learning: true, international: false, reflection: false },
  next_step: { kind: "apply", label: "Apply: AR Analyst at Acme", link: "/discover?job=11", reason: "Your strongest current match (82/100) with no application yet." },
  ...over,
});

describe("career snapshot card", () => {
  it("shows the one next step as a link with its reason, and unknown eligibility as 'unknown' (never as eligible)", () => {
    wrap(<CareerSnapshotCard snapshot={snapshot()} />);
    const cta = screen.getByRole("link", { name: /Apply: AR Analyst at Acme/ });
    expect(cta).toHaveAttribute("href", "/discover?job=11");
    expect(screen.getByText(/strongest current match/)).toBeInTheDocument();
    // one pass, and both the "unknown" and the missing (null) eligibility show as unknown
    expect(screen.getAllByText("Eligible")).toHaveLength(1);
    expect(screen.getAllByText("unknown")).toHaveLength(2);
    // missing profile items are in plain language, and the gap shows its next action
    expect(screen.getByText(/a short summary, work experience or projects/)).toBeInTheDocument();
    expect(screen.getByText("Finish an SAP FICO basics course.")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Profile completeness" })).toHaveAttribute("aria-valuenow", "80");
  });
});

describe("learning sessions need consent", () => {
  it("shows the consent text when starting returns 403, and retries after turning tracking on", async () => {
    const consentText = "Track time on learning sessions you start (active vs idle, only while the session is open).";
    const session = { id: 9, skill: "SAP FICO", resource_id: 3, gap_id: 5, status: "active", started_at: "2026-11-10T09:00:00Z", ended_at: null,
                      active_minutes: 0, active_seconds: 0, idle_seconds: 0, notes: null, helpful: null };
    api.get.mockImplementation(async (url: string) => {
      if (url === "/gaps") return { data: { best: gap, alternatives: [], gaps: [gap] } };
      if (url === "/gaps/5") return { data: { ...gap, learning: { skill: "SAP FICO", level_suggested: "beginner", enough: false, note: "Only 1 checked resource(s) are catalogued for SAP FICO so far.",
        resources: [{ id: 3, skill: "SAP FICO", title: "SAP FICO overview", url: "https://learning.sap.com/fico", provider: "SAP", type: "course", level: "beginner",
                      duration_minutes: 90, is_free: true, source: "curated", checked_at: "2026-11-01T00:00:00Z", link_status: "unverifiable", relevance: "SAP (official source)" }] } } };
      if (url === "/learning-sessions") return { data: { sessions: started ? [session] : [], stats: { days: 30, sessions: 0, completed: 0, active_minutes: 0, idle_minutes: 0 } } };
      throw new Error(`unexpected GET ${url}`);
    });
    let refused = false;
    let started = false;
    api.post.mockImplementation(async (url: string) => {
      if (url === "/learning-sessions") {
        if (!refused) {
          refused = true;
          throw { response: { status: 403, data: { detail: { message: "This needs your permission first.", consent: "learning_tracking", text: consentText } } } };
        }
        started = true;
        return { data: session };
      }
      if (url.endsWith("/heartbeat")) return { data: session };
      throw new Error(`unexpected POST ${url}`);
    });
    api.put.mockResolvedValue({ data: [{ kind: "learning_tracking", granted: true, text: consentText, granted_at: "2026-11-10T09:00:00Z", revoked_at: null }] });

    wrap(<LearningTab gapId={null} onSelectGap={vi.fn()} />);
    expect(await screen.findByText("Site blocks automated checks", { exact: false })).toBeInTheDocument();
    expect(screen.getAllByText(/Tracking only while this session is open/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Start learning/ }));
    expect(await screen.findByText(consentText)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Turn on learning tracking" }));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/consents/learning_tracking", { granted: true }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/learning-sessions", { resource_id: 3, gap_id: 5 }));
    expect(api.post.mock.calls.filter(([u]) => u === "/learning-sessions")).toHaveLength(2);
    // The running session shows a timer and the pause / finish controls.
    expect(await screen.findByRole("timer", { name: "Session time" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pause/ })).toBeInTheDocument();
    expect(screen.queryByText(consentText)).not.toBeInTheDocument();
  });
});

describe("skill states follow the evidence", () => {
  it("shows the backend's explanation when a state change is refused (409)", async () => {
    const message = "'Project evidence' needs evidence. Your evidence supports up to 'Learning'.";
    api.get.mockResolvedValue({ data: {
      states: [{ key: "aware", label: "Aware" }],
      skills: [{ id: 1, name: "Power BI", canonical: "Power BI", state: "learning", state_label: "Learning", proficiency: null, years: null, source: "manual",
                 verified: false, evidence_supports: "learning", evidence: [{ id: 4, type: "course", title: "Power BI basics", url: null, description: null,
                 source: "manual", occurred_on: null, created_at: "2026-11-01T00:00:00Z" }] }],
    } });
    api.put.mockRejectedValue({ response: { status: 409, data: { detail: message } } });

    wrap(<SkillsTab />);
    expect(await screen.findByText("Courses and projects never count as work experience.")).toBeInTheDocument();
    fireEvent.change(await screen.findByRole("combobox", { name: "Step for Power BI" }), { target: { value: "project_evidence" } });
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/skills/1/state", { state: "project_evidence" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });
});

describe("international page", () => {
  it("shows the not-legal-advice notice, route confidence in plain words and the watch toggle", async () => {
    api.get.mockImplementation(async (url: string, cfg?: { params?: { country?: string } }) => {
      if (url === "/countries") return { data: [{ code: "GB", name: "United Kingdom", region: "Europe", currency: "GBP", official_source_url: "https://www.gov.uk/browse/visas-immigration", routes: 1 }] };
      if (url === "/career-goals") return { data: { search_mode: "both", target_countries: ["GB"], seniority: null, open_to_relocation: true, work_authorization: ["IN"], needs_sponsorship: true } };
      const route = { id: 2, country_code: "GB", code: "skilled_worker", name: "Skilled Worker visa", summary: "For a job offer from an approved employer.",
                      requires_sponsorship: true, source_url: "https://www.gov.uk/skilled-worker-visa", confidence: "unverified", verified_at: null, last_checked_at: null,
                      review_by: null, source_changed_at: null, watching: false, notice: "", rules: [] };
      if (url === "/visa-routes" && cfg?.params?.country === "GB") return { data: [{ ...route, watching: true }] };
      if (url === "/country-fit") return { data: { country: { code: "GB", name: "United Kingdom", official_source_url: null }, already_authorised: false,
        profile_used: { years_experience: 3, education: "bachelor", languages: ["English"] }, notice: "General information only, not legal or immigration advice.",
        routes: [{ ...route, fit: { strengths: ["Your education (bachelor) meets the general level (bachelor)."], gaps: [], unknown: ["A salary threshold applies."], summary: "Possible pathway" } }],
        relocation_tips: ["Ask recruiters early about sponsorship."] } };
      throw new Error(`unexpected GET ${url}`);
    });
    api.put.mockResolvedValue({ data: { route_id: 2, watching: false } });

    wrap(<InternationalPage />);
    expect(screen.getByText("This is not legal advice.")).toBeInTheDocument();
    expect(await screen.findByText("Skilled Worker visa")).toBeInTheDocument();
    expect(screen.getByText("Not yet checked by a person")).toBeInTheDocument();
    const toggle = screen.getByRole("switch", { name: /Tell me if the official page for Skilled Worker visa changes/ });
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "true"));  // watch flag comes from /visa-routes
    fireEvent.click(toggle);
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/visa-routes/2/watch", { watching: false }));
  });
});
