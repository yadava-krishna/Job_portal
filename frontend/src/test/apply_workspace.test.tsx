import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn(), previewFile: vi.fn() }));

import { ApplyDialog } from "@/components/app/ApplyDialog";
import { RememberedAnswers } from "@/features/apply/RememberedAnswers";
import type { ApplyPackage, MemoryAnswer, PackageAnswer, UserJob } from "@/types/api";

const wrap = (ui: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

const item = {
  user_job_id: 7, status: "new", is_saved: false, match_score: 82, match_category: "good", matching_skills: [], missing_skills: [],
  eligibility_status: null, scoring_method: null, discovered_at: "", saved_at: null, dismissed_at: null, application_id: null, application_status: null,
  job: { id: 1, platform: "LinkedIn", company: "Stripe", title: "AR Analyst", job_url: "https://www.linkedin.com/jobs/view/1", sources: [] },
} as unknown as UserJob;

const app = { id: 5, status: "PREPARED", checklist: [], screening_answers: [], needs_candidate_input: [], resume_used: "cv.pdf", cover_letter: null, events: [],
  apply_state: null, apply_state_label: null };

const answer = (over: Partial<PackageAnswer>): PackageAnswer => ({
  question: "Q", key: null, label: "Q", answer: null, status: "NEEDS_INPUT", source: null, confidence: 1, sensitivity: "personal", confirm: false,
  stale: false, reason: null, value_type: "text", unit: null, scope: "global", notes: [], remember_default: true, origin: "common", required: true,
  options: [], field_type: "text", ...over,
});

const ANSWERS: PackageAnswer[] = [
  answer({ question: "Total years of experience", key: "experience_years.total", status: "VERIFIED", answer: "4", source: "memory", value_type: "number", unit: "years" }),
  answer({ question: "Notice period", key: "notice_period", value_type: "days", unit: "days", remember_default: false }),
  answer({ question: "Expected CTC", key: "expected_ctc", status: "SUGGESTED", answer: "12 LPA", source: "settings", sensitivity: "private", value_type: "money",
    stale: true, reason: "Saved in Settings a while ago. Check it's still right." }),
  answer({ question: "What is your gender?", sensitivity: "never", remember_default: false, reason: "Sensitive personal question" }),
  answer({ question: "Willing to relocate?", key: "willing_to_relocate", status: "SUGGESTED", answer: "Yes", source: "profile", value_type: "boolean" }),
];

const GH = "https://job-boards.greenhouse.io/stripe/jobs/8247127";
const basePkg: ApplyPackage = {
  version: 1, prepared_at: "2026-11-19T10:00:00Z",
  job: { title: "AR Analyst", company: "Stripe", source: "LinkedIn", location: "Bengaluru", match_score: 82, job_url: item.job.job_url },
  destination: { original_url: item.job.job_url, source_platform: "LinkedIn", url: GH, kind: "ats", ats: "greenhouse", platform_name: "Greenhouse",
    verified: true, evidence: ["Employer posting 8247127 on Greenhouse (board 'stripe')."], suggestions: [], confirmed_by_user: false },
  capabilities: { prepare: true, autofill: true, assisted_submit: true, native_handoff: false, verified_confirmation: true,
    summary: "JobPilot fills this Greenhouse form; you review it and confirm the submission." },
  resume: { kind: "upload", id: 3, name: "cv.pdf", format: "pdf", selected_by: "default", ready: true },
  profile: { personal: [{ key: "full_name", label: "Full name", value: "Asha Rao", source: "profile" }, { key: "phone", label: "Phone", value: null, source: "profile" }],
    professional: [], links: [] },
  answers: ANSWERS, questions_source: "not_inspected", missing: [], conflicts: [], eligibility: [],
  readiness: { profile: true, resume: true, known_questions: false, form_inspected: false, to_check: 2, needs_input: 1, level: "needs_input",
    summary: "1 answer needed before you apply." },
  action: "review_autofill", action_label: "Review and autofill",
};

const nativePkg: ApplyPackage = {
  ...basePkg,
  destination: { ...basePkg.destination, url: item.job.job_url, kind: "restricted", ats: null, platform_name: "LinkedIn", verified: false, evidence: [] },
  capabilities: { ...basePkg.capabilities, autofill: false, assisted_submit: false, native_handoff: true, summary: "LinkedIn's rules don't allow automated tools." },
  action: "open_native", action_label: "Open native application",
};

function mockServer(pkg: ApplyPackage, application: Record<string, unknown> = app) {
  api.post.mockImplementation(async (url: string) => {
    if (url.endsWith("/prepare")) return { data: application };
    if (url.includes("/handoff")) return { data: { application: { ...application, status: "OPENED", apply_state: "form_opened" }, package: pkg, url: pkg.destination.url } };
    if (url.endsWith("/answers")) return { data: { application, package: pkg, saved: ["Notice period"], errors: [] } };
    return { data: application };
  });
  api.get.mockImplementation(async (url: string) => {
    if (url.includes("/package")) return { data: { application, package: pkg } };
    if (url === "/profile/resumes") return { data: [{ id: 3, original_filename: "cv.pdf", size_bytes: 1, page_count: 1, sha256: "", uploaded_at: "2026-10-01T00:00:00Z", is_active: true }] };
    if (url === "/studio/versions") return { data: [] };
    return { data: {} };
  });
}

const sent: Record<string, unknown>[] = [];
const fakeExtension = (connected: boolean) => {
  (globalThis as { chrome?: unknown }).chrome = { runtime: { sendMessage: (_id: string, msg: { type: string }, cb: (r: unknown) => void) => {
    sent.push({ ...msg });
    cb(msg.type === "ping" ? { ok: true, data: { version: "2.2.0", connected } } : { ok: true, data: { tabId: 3 } });
  } } };
};

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()); });
afterEach(() => { delete (globalThis as { chrome?: unknown }).chrome; sent.length = 0; vi.restoreAllMocks(); });

describe("Apply Workspace", () => {
  it("shows where to apply, honest readiness, and the answers that need you first", async () => {
    mockServer(basePkg);
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    const dest = await screen.findByTestId("ws-destination");
    expect(within(dest).getByText("Greenhouse")).toBeInTheDocument();
    expect(within(dest).getByText("job-boards.greenhouse.io")).toBeInTheDocument();
    expect(within(dest).getByText("Verified employer posting")).toBeInTheDocument();
    expect(within(dest).getByText("LinkedIn")).toBeInTheDocument();  // where it was found

    const readiness = screen.getByTestId("ws-readiness");
    expect(within(readiness).getByText("Employer form not inspected yet")).toBeInTheDocument();
    expect(within(readiness).getByText("Profile ready")).toBeInTheDocument();
    expect(within(readiness).getByText("Known questions need answers")).toBeInTheDocument();
    expect(within(readiness).queryByText(/Employer form inspected$/)).toBeNull();

    const rows = within(screen.getByTestId("ws-answer-list")).getAllByRole("listitem");
    expect(rows[0]).toHaveAttribute("data-testid", "ws-answer-needs_input");
    expect(rows[0]).toHaveTextContent("Notice period");
    expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual(["ws-answer-needs_input", "ws-answer-suggested", "ws-answer-suggested", "ws-answer-never"]);
    // Ready answers are collapsed behind a count.
    expect(screen.queryByTestId("ws-ready-list")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Show 1 ready answer/ }));
    expect(within(screen.getByTestId("ws-ready-list")).getByText("Remembered answer")).toBeInTheDocument();
    // Private answers carry a lock; stale ones say why.
    expect(screen.getAllByLabelText("Private answer, stored encrypted").length).toBe(1);
    expect(screen.getByText("Saved in Settings a while ago. Check it's still right.")).toBeInTheDocument();
  });

  it("saves only the changed answers, remembering them only when ticked", async () => {
    mockServer(basePkg);
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    const notice = await screen.findByLabelText("Notice period");
    expect(notice).toHaveAttribute("placeholder", "e.g. 30 days or Immediate");
    fireEvent.change(notice, { target: { value: "30 days" } });
    const row = screen.getByTestId("ws-answer-needs_input");
    const remember = within(row).getByRole("checkbox", { name: "Remember for future applications" });
    expect(remember).not.toBeChecked();  // remember_default false
    fireEvent.click(remember);
    // Boolean questions are Yes / No buttons.
    const relocate = screen.getAllByTestId("ws-answer-suggested")[1];
    expect(within(relocate).getByRole("button", { name: "Yes" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Save answers" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/applications/5/answers", {
      items: [{ question: "Notice period", answer: "30 days", remember: true, key: "notice_period" }],
    }));
  });

  it("never offers an input for sensitive questions", async () => {
    mockServer(basePkg);
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    const row = await screen.findByTestId("ws-answer-never");
    expect(row).toHaveTextContent("What is your gender?");
    expect(row).toHaveTextContent("Answer this yourself on the form. JobPilot never answers or stores it.");
    expect(within(row).queryByRole("textbox")).toBeNull();
    expect(within(row).queryByRole("checkbox")).toBeNull();
    expect(within(row).queryByRole("combobox")).toBeNull();
  });

  it.each([
    ["review_autofill", false, "Continue on employer site"],
    ["review_autofill", true, "Review and autofill"],
    ["continue_employer", false, "Continue on employer site"],
    ["resume", false, "Resume application"],
  ] as const)("action %s (Smart Apply connected: %s) reads %s", async (action, connected, label) => {
    if (connected) fakeExtension(true);
    mockServer({ ...basePkg, action }, action === "resume" ? { ...app, status: "OPENED", apply_state: "interrupted", apply_state_label: "Interrupted: resume when ready" } : app);
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("workspace-primary")).toHaveTextContent(label));
    if (action === "resume") expect(screen.getByTestId("ws-recovery")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /submit for me|auto-?submit/i })).toBeNull();
  });

  it("reopened after the extension changed the application, it shows the server's state, not a cached copy", async () => {
    // Cached from the previous visit: the hand-off ("employer page opened"), before the tab was closed.
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 60_000 } } });
    client.setQueryData(["apply-package", 5], { application: { ...app, status: "OPENED", apply_state: "form_opened", apply_state_label: "Employer page opened" },
                                                 package: basePkg });
    const interrupted = { ...app, status: "OPENED", apply_state: "interrupted", apply_state_label: "Interrupted: resume when ready" };
    mockServer({ ...basePkg, action: "resume", action_label: "Resume application" }, interrupted);
    render(<QueryClientProvider client={client}><ApplyDialog item={item} onClose={() => {}} /></QueryClientProvider>);
    await waitFor(() => expect(screen.getByTestId("workspace-primary")).toHaveTextContent("Resume application"));
    expect(screen.getAllByText(/Interrupted: resume when ready/).length).toBeGreaterThan(0);
    expect(screen.queryAllByText(/Employer page opened/)).toEqual([]);
  });

  it("open_native reads 'Open on LinkedIn'", async () => {
    mockServer(nativePkg);
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("workspace-primary")).toHaveTextContent("Open on LinkedIn"));
  });

  it("an uncertain submission goes straight to the check step and never offers to submit again", async () => {
    mockServer({ ...basePkg, action: "resolve_uncertain" }, { ...app, status: "CONFIRMATION_PENDING", apply_state: "submission_uncertain", apply_state_label: "Submission uncertain: please check" });
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    expect(await screen.findByTestId("ws-uncertain")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Yes, I submitted it/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Not submitted/ })).toBeInTheDocument();
    expect(screen.queryByTestId("workspace-primary")).toBeNull();
    expect(screen.queryByRole("button", { name: /Back to package/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Open the page to check/ }));
    expect(open).toHaveBeenCalledWith(GH, "_blank", "noopener,noreferrer");
    expect(api.post).not.toHaveBeenCalledWith(expect.stringContaining("/handoff"));
  });

  it("native hand-off: copy-ready answers, and the page opens before the hand-off is recorded", async () => {
    mockServer(nativePkg);
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    const panel = await screen.findByTestId("ws-copy-panel");
    expect(within(panel).getByRole("button", { name: "Copy Expected CTC" })).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Copy Full name" })).toBeInTheDocument();
    expect(within(panel).queryByText("What is your gender?")).toBeNull();
    fireEvent.click(screen.getByTestId("workspace-primary"));
    expect(open).toHaveBeenCalledWith(item.job.job_url, "_blank", "noopener,noreferrer");
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/applications/5/handoff?smart=false"));
    const handoffCall = api.post.mock.calls.findIndex(([u]) => String(u).includes("/handoff"));
    expect(open.mock.invocationCallOrder[0]).toBeLessThan(api.post.mock.invocationCallOrder[handoffCall]);
    expect(api.post).not.toHaveBeenCalledWith(expect.stringContaining("/confirm"), expect.anything());
  });

  it("autofill hands the job and the application to Smart Apply after recording the hand-off", async () => {
    fakeExtension(true);
    mockServer(basePkg);
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByTestId("workspace-primary")).toHaveTextContent("Review and autofill"));
    fireEvent.click(screen.getByTestId("workspace-primary"));
    await waitFor(() => expect(sent).toContainEqual({ type: "apply", url: GH, userJobId: 7, applicationId: 5 }));
    expect(api.post).toHaveBeenCalledWith("/applications/5/handoff?smart=true");
  });

  it.each([
    ["user_reported", null, "Recorded from your confirmation (not independently verified)", "Confirmed by the employer's page"],
    ["submitted_confirmed", { source: "employer_page", confidence: "high" }, "Confirmed by the employer's page", "not independently verified"],
  ] as const)("done state for %s says how the submission is known", async (state, conf, shown, hidden) => {
    mockServer({ ...basePkg, action: "done" }, { ...app, status: "SUBMITTED", apply_state: state, confirmation: conf, submitted_at: "2026-11-18T10:00:00Z" });
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    const done = await screen.findByTestId("ws-done");
    expect(within(done).getByText(shown)).toBeInTheDocument();
    expect(within(done).queryByText(new RegExp(hidden))).toBeNull();
  });
});

describe("Remembered answers in Settings", () => {
  const rows: MemoryAnswer[] = [
    { key: "expected_ctc", scope_ref: "", label: "Expected compensation", answer: null, masked: true, value_type: "money", unit: "currency_per_year",
      sensitivity: "private", source: "apply_workspace", status: "verified", stale: true, question: "Expected CTC", last_confirmed_at: "2026-06-01T00:00:00Z",
      revalidate_days: 60, group: "professional", history: [{ at: "2026-06-01T00:00:00Z", source: "apply_workspace", question: "Expected CTC", answer: "(hidden)" }] },
    { key: "notice_period", scope_ref: "", label: "Notice period", answer: "30 days", masked: false, value_type: "days", unit: "days", sensitivity: "personal",
      source: "settings", status: "verified", stale: false, question: "Notice period", last_confirmed_at: "2026-11-01T00:00:00Z", revalidate_days: 30,
      group: "professional", history: [] },
  ];

  let all: MemoryAnswer[] = rows;
  let conflicts: unknown[] = [];
  beforeEach(() => {
    all = rows;
    conflicts = [];
    api.get.mockImplementation(async (url: string, cfg?: { params?: { reveal?: boolean } }) =>
      url === "/answers/conflicts" ? { data: conflicts }
        : ({ data: cfg?.params?.reveal ? all.map((r) => (r.masked ? { ...r, answer: "14 LPA", masked: false } : r)) : all }));
  });

  it("masks private answers until Show, which fetches them revealed", async () => {
    wrap(<RememberedAnswers />);
    const ctc = await screen.findByTestId("memory-expected_ctc");
    expect(ctc).not.toHaveTextContent("14 LPA");
    expect(within(ctc).getByLabelText("Hidden")).toBeInTheDocument();
    expect(within(ctc).getByText("Check this")).toBeInTheDocument();
    expect(within(ctc).getByText(/Saved while applying/)).toBeInTheDocument();
    fireEvent.click(within(ctc).getByRole("button", { name: "Show Expected compensation" }));
    expect(await within(ctc).findByText("14 LPA")).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith("/answers/memory", { params: { reveal: true } });
  });

  it("edits an answer inline and forgets one after confirming", async () => {
    api.put.mockResolvedValue({ data: { ...rows[1], answer: "Immediate" } });
    api.delete.mockResolvedValue({ data: null });
    wrap(<RememberedAnswers />);
    const row = await screen.findByTestId("memory-notice_period");
    fireEvent.click(within(row).getByRole("button", { name: "Edit Notice period" }));
    const input = within(row).getByRole("textbox");
    expect(input).toHaveValue("30 days");
    fireEvent.change(input, { target: { value: "Immediate" } });
    fireEvent.click(within(row).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/answers/memory", { key: "notice_period", question: "Notice period", answer: "Immediate" }));

    fireEvent.click(within(screen.getByTestId("memory-notice_period")).getByRole("button", { name: "Forget Notice period" }));
    fireEvent.click(await screen.findByRole("button", { name: /Forget it/ }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/answers/memory/notice_period", { params: undefined }));
  });

  it("edits an employer-specific answer for that employer only, and says where each answer is reused", async () => {
    const scoped: MemoryAnswer = { key: "previously_employed", scope_ref: "company:acme health", scope_kind: "company", scope_name: "Acme Health",
      reusable: false, label: "Worked for this employer before", answer: "No", masked: false, value_type: "boolean", unit: null, sensitivity: "personal",
      source: "apply_workspace", status: "verified", stale: false, question: "Have you previously worked for this company?",
      last_confirmed_at: "2026-11-01T00:00:00Z", revalidate_days: null, group: "other", history: [] };
    all = [...rows, scoped];
    api.put.mockResolvedValue({ data: { ...scoped, answer: "Yes" } });
    wrap(<RememberedAnswers />);
    const row = await screen.findByTestId("memory-previously_employed");
    expect(within(row).getByText("Only for Acme Health")).toBeInTheDocument();
    expect(within(await screen.findByTestId("memory-notice_period")).getByText("Any application")).toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: "Edit Worked for this employer before" }));
    fireEvent.change(within(row).getByRole("textbox"), { target: { value: "Yes" } });
    fireEvent.click(within(row).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/answers/memory", {
      key: "previously_employed", question: "Have you previously worked for this company?", answer: "Yes", scope_ref: "company:acme health" }));
  });

  it("flags a saved answer that differs from the profile, and reconfirms a stale one without retyping", async () => {
    const title: MemoryAnswer = { ...rows[1], key: "current_company", label: "Current employer", answer: "Old Co", value_type: "text", unit: null,
      question: "Current employer", revalidate_days: null, stale: false };
    const stale: MemoryAnswer = { ...rows[1], stale: true };
    all = [stale, title];
    conflicts = [{ key: "current_company", label: "Current employer", saved: "Old Co", profile: "New Co", used: "ask" }];
    api.put.mockResolvedValue({ data: { ...stale, stale: false } });
    wrap(<RememberedAnswers />);
    expect(await screen.findByTestId("answer-conflicts")).toHaveTextContent("1 saved answer differs");
    const row = await screen.findByTestId("memory-current_company");
    expect(within(row).getByText("Profile is newer")).toBeInTheDocument();
    expect(within(row).getByText(/Your profile says “New Co”/)).toBeInTheDocument();
    fireEvent.click(within(screen.getByTestId("memory-notice_period")).getByRole("button", { name: "Notice period is still right" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/answers/memory", { key: "notice_period", question: "Notice period", answer: "30 days" }));
  });
});
