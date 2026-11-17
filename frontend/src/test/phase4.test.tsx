import { createEvent, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn() }));

import { ActionCentre } from "@/features/dashboard/ActionCentre";
import type { Overview } from "@/features/dashboard/types";
import { PipelineBoard } from "@/features/applications/PipelineBoard";
import { daysSince, eventLabel, followUpState } from "@/features/applications/events";
import type { Application, AppEvent } from "@/types/api";

const wrap = (ui: ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );

const overview = (over: Partial<Overview> = {}): Overview => ({
  new_jobs: { count: 1, min_score: 70, days: 7, top: [{ user_job_id: 11, title: "AR Analyst", company: "Acme", match_score: 82, location: "Pune, India",
    salary: "INR 8L–12L a year", discovered_at: null, freshness: "open", eligibility_status: null }] },
  attention: [{ kind: "follow_up", title: "Follow up: Data Analyst at Beta", detail: null, due: null, application_id: 4, user_job_id: null, interview_id: null }],
  upcoming: [],
  waiting: [],
  saved: { count: 2, no_longer_open: 1, top: [] },
  recent_submitted: [{ application_id: 4, title: "Data Analyst", company: "Beta", submitted_at: new Date().toISOString(), stage: "screening" }],
  resume: { state: "not_exported", message: null, uploaded: null, profile_confirmed: true, versions: 1,
    latest: { id: 1, name: "Main", updated_at: null, status: "draft" }, last_export_at: null },
  discovery: { state: "partial", problems: [{ source: "lever", label: "Lever", status: "partial", message: "2 boards could not be read" }],
    last_run: { id: 9, status: "completed", started_at: new Date().toISOString(), completed_at: null, jobs_found: 40, jobs_new: 3 } },
  ...over,
});

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()); });

describe("dashboard action centre", () => {
  it("links each item straight to the job or application it is about", async () => {
    api.get.mockResolvedValue({ data: overview() });
    wrap(<ActionCentre />);
    const jobs = await screen.findByRole("region", { name: /New matching jobs/ });
    expect(within(jobs).getByRole("link", { name: /AR Analyst/ })).toHaveAttribute("href", "/discover?job=11");
    const attention = screen.getByRole("region", { name: /Needs your attention/ });
    expect(within(attention).getByRole("link", { name: /Follow up: Data Analyst/ })).toHaveAttribute("href", "/applied?app=4");
    expect(screen.getByText("1 saved job is no longer open.")).toBeInTheDocument();
    expect(screen.getByText("Built, not exported yet")).toBeInTheDocument();
    expect(screen.getByText(/Lever: 2 boards could not be read/)).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/dashboard/overview");
  });

  it("says plainly when there is nothing new, and offers a retry when loading fails", async () => {
    api.get.mockResolvedValueOnce({ data: overview({ new_jobs: { count: 0, min_score: 70, days: 7, top: [] }, attention: [] }) });
    const { unmount } = wrap(<ActionCentre />);
    expect(await screen.findByText(/No new jobs scoring 70% or more/)).toBeInTheDocument();
    expect(screen.getByText("Nothing is waiting on you.")).toBeInTheDocument();
    unmount();
    api.get.mockRejectedValueOnce(new Error("offline"));
    wrap(<ActionCentre />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Your dashboard couldn't be loaded");
    api.get.mockResolvedValueOnce({ data: overview() });
    fireEvent.click(within(alert).getByRole("button", { name: /Try again/ }));
    await waitFor(() => expect(screen.getByTestId("action-centre")).toBeInTheDocument());
  });
});

const app = (id: number, stage: Application["stage"], over: Partial<Application> = {}): Application => ({
  id, status: "SUBMITTED", stage, user_job_id: null, match_score: 75, match_category: null, resume_used: null, reference_id: null,
  confirmation_text: null, confirmation_source: null, created_at: "", opened_at: null, submitted_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
  follow_up_at: null, job: { title: `Role ${id}`, company: "Acme", platform: "Greenhouse" } as Application["job"], ...over,
});

describe("applications pipeline board", () => {
  const stages = ["applied", "screening", "interview"] as Application["stage"][] as NonNullable<Application["stage"]>[];

  it("moves a card by drag and drop, and by the keyboard-friendly menu", () => {
    const onMove = vi.fn();
    wrap(<PipelineBoard apps={[app(1, "applied"), app(2, "screening", { follow_up_at: new Date(Date.now() - 86_400_000).toISOString() })]}
                        stages={stages} moveTo={stages} onMove={onMove} onOpen={vi.fn()} />);
    const applied = screen.getByRole("region", { name: "Applied: 1" });
    const interview = screen.getByRole("region", { name: "Interview: 0" });
    const card = within(applied).getByText("Role 1").closest("[draggable]")!;
    const store: Record<string, string> = {};
    const dataTransfer = { setData: (k: string, v: string) => { store[k] = v; }, getData: (k: string) => store[k], effectAllowed: "", dropEffect: "" };
    fireEvent(card, Object.assign(createEvent.dragStart(card), { dataTransfer }));
    fireEvent(interview, Object.assign(createEvent.dragOver(interview), { dataTransfer }));
    fireEvent(interview, Object.assign(createEvent.drop(interview), { dataTransfer }));
    expect(onMove).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), "interview");

    fireEvent.change(screen.getByLabelText("Move Role 2 to stage"), { target: { value: "interview" } });
    expect(onMove).toHaveBeenLastCalledWith(expect.objectContaining({ id: 2 }), "interview");
    expect(screen.getByText("Follow-up due")).toBeInTheDocument();
    expect(screen.getAllByText("Applied 3d ago")).toHaveLength(2);
  });
});

describe("application history in plain words", () => {
  const ev = (event_type: string, to_status: string | null = null): AppEvent => ({ id: 1, event_type, from_status: null, to_status, details: null, created_at: "" });
  it("names every event instead of showing internal codes", () => {
    expect(eventLabel(ev("STAGE_CHANGED", "interview"))).toBe("Moved to Interview");
    expect(eventLabel(ev("SUBMISSION_CONFIRMED"))).toBe("Confirmed as sent");
    expect(eventLabel(ev("SOMETHING_NEW"))).toBe("Something new");
    expect(followUpState(null)).toBeNull();
    expect(followUpState(new Date(Date.now() + 5 * 86_400_000).toISOString())).toBe("upcoming");
    expect(daysSince(new Date().toISOString())).toBe(0);
  });
});

describe("history details", () => {
  it("turns internal detail strings into sentences", async () => {
    const { eventDetail } = await import("@/features/applications/events");
    const ev = (event_type: string, details: string) => ({ id: 1, event_type, from_status: null, to_status: null, details, created_at: "" });
    expect(eventDetail(ev("SUBMISSION_CONFIRMED", "source=user_confirmed; reference=ABC-1"))).toBe("You confirmed it in JobPilot · reference ABC-1");
    expect(eventDetail(ev("FOLLOW_UP_SET", "cleared"))).toBe("Reminder removed");
    expect(eventDetail(ev("FOLLOW_UP_SET", "2026-11-16T09:00:00"))).toMatch(/^Remind me on /);
  });
});
