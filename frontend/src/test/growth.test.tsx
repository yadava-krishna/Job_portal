import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError, type AxiosResponse } from "axios";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Keep the real errorMessage (it reads the backend's detail text); only the HTTP client is mocked.
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn(), patch: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), api }));

import { JobDetailSheet } from "@/components/app/JobDetailSheet";
import { RejectionDialog } from "@/features/growth/applications";
import { ScoreDimensions } from "@/features/growth/ScoreDimensions";
import { ForgotPasswordPage } from "@/pages/AuthPages";
import { MentorPage } from "@/pages/MentorPage";
import type { ScoreDimension } from "@/features/growth/types";

const wrap = (ui: ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
    <MemoryRouter>{ui}</MemoryRouter>
  </QueryClientProvider>,
);
beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));

function httpError(status: number, data: unknown) {
  return new AxiosError("Request failed", "ERR_BAD_RESPONSE", undefined, undefined, { status, statusText: "", data, headers: {}, config: {} } as unknown as AxiosResponse);
}

const dim = (over: Partial<ScoreDimension>): ScoreDimension => ({
  name: "required_skills", label: "Required skills", status: "known", score: 80, base_weight: 30, weight: 31.6, weighted: 25.3,
  evidence: "8 of 10 required skills", method: "rule_based", ...over,
});
const dimensions = [
  dim({}),
  dim({ name: "salary", label: "Salary", status: "unknown", score: null, base_weight: 5, weight: 0, weighted: 0, evidence: "the job doesn't state a salary", method: "deterministic" }),
];

describe("versioned score breakdown", () => {
  it("shows an unknown dimension as unknown, not as a number", () => {
    render(<ScoreDimensions dimensions={dimensions} />);
    const salary = screen.getByTestId("dimension-salary");
    expect(within(salary).getByText("unknown")).toBeInTheDocument();
    expect(within(salary).queryByText("0")).not.toBeInTheDocument();
    expect(within(screen.getByTestId("dimension-required_skills")).getByText("80")).toBeInTheDocument();
  });

  it("the job sheet shows dimensions, eligibility, disclaimer, version and the prep/resume links", async () => {
    const job = {
      user_job_id: 7, status: "new", is_saved: false, match_score: 76, match_category: "good", matching_skills: [], missing_skills: [], eligibility_status: "ELIGIBLE",
      scoring_method: "rule_based", discovered_at: "", saved_at: null, dismissed_at: null, application_id: null, application_status: null,
      description: "Full description", responsibilities: [], required_skills: [], preferred_skills: [], education_requirements: [], mandatory_qualifications: [],
      verification_flags: [], description_is_snippet: false,
      job: { id: 3, platform: "Lever", external_job_id: null, company: "Acme", title: "AR Analyst", location: "Pune", work_mode: null, employment_type: null,
        experience_required: null, salary_range: null, job_url: "https://jobs.lever.co/acme/1", posted_at: null, posted_at_source: null, posted_label: "Unknown",
        description_preview: null, has_full_description: true, source: "lever", posted_at_confidence: "unknown", first_seen_at: null, last_verified_at: null,
        closed_at: null, industry: null, department: null, sources: [] },
    };
    const analysis = {
      user_job_id: 7, overall_score: 76, category: "good", components: [], matching_skills: [], missing_skills: [], missing_optional_skills: [],
      relevant_experience: "", experience_gap: "", education_match: null, location_match: null, responsibilities_match: [], reasons_for: [], reasons_against: [],
      recommendation: "", explanation: "", eligibility_status: "ELIGIBLE", eligibility_reasons: [], scoring_method: "rule_based", confidence: "medium", notes: [],
      score_version: "v2.2026-11", dimensions, eligibility: "unknown", unknown_dimensions: ["salary"],
      disclaimer: "A relevance estimate to help you prioritise. It is not a prediction that you will be hired.",
    };
    api.get.mockImplementation(async (url: string) => ({ data: url.endsWith("/analysis") ? analysis : job }));
    wrap(<JobDetailSheet userJobId={7} onOpenChange={() => {}} onApply={() => {}} />);
    const salary = await screen.findByTestId("dimension-salary");
    expect(within(salary).getByText("unknown")).toBeInTheDocument();
    expect(screen.getByTestId("eligibility")).toHaveTextContent("Eligibility: unknown");
    expect(screen.getByText(/not a prediction that you will be hired/)).toBeInTheDocument();
    expect(screen.getByText(/Score version v2.2026-11/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Prepare for interview/ })).toHaveAttribute("href", "/interview-prep?job=7");
    expect(screen.getByRole("link", { name: /Tailor a resume/ })).toHaveAttribute("href", "/studio?job=7");
  });
});

describe("recording a rejection", () => {
  it("won't save until you say whether the employer told you or it's a guess", async () => {
    api.get.mockResolvedValue({ data: [{ key: "salary", label: "Salary expectations" }, { key: "no_reason_given", label: "No reason given" }] });
    api.post.mockResolvedValue({ data: { id: 5, stage: "rejected", rejection_reason: "salary", rejection_reason_known: false } });
    const onSaved = vi.fn();
    wrap(<RejectionDialog app={{ id: 5, title: "AR Analyst", company: "Acme" }} onClose={() => {}} onSaved={onSaved} />);
    await screen.findByRole("option", { name: "Salary expectations" });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "salary" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/employer told you this or it's your guess/);
    expect(api.post).not.toHaveBeenCalled();
    expect(screen.getByText(/Guesses are kept separate/)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/No, it's my guess/));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/applications/5/rejection", { reason: "salary", detail: null, known: false }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});

describe("forgot password", () => {
  it("shows the server's message when e-mail isn't set up", async () => {
    const msg = "Password reset by e-mail is not set up on this server. Ask the JobPilot owner to reset your password.";
    api.post.mockRejectedValue(httpError(503, { detail: msg }));
    wrap(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "asha@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /Send reset link/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(msg);
    expect(api.post).toHaveBeenCalledWith("/auth/forgot-password", { email: "asha@example.com" });
  });

  it("shows a neutral message on success", async () => {
    api.post.mockResolvedValue({ data: { message: "If an account exists for that e-mail address, a reset link has been sent." } });
    wrap(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "asha@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /Send reset link/ }));
    expect(await screen.findByRole("status")).toHaveTextContent(/If an account exists/);
  });
});

describe("inviting a mentor", () => {
  it("asks for sharing permission, grants it and retries the invite", async () => {
    api.get.mockImplementation(async (url: string) => {
      if (url === "/mentor/plan") return { data: { diagnoses: [], actions: [], next_step: null, reflection_due: false, last_reflection: null, method: "rule_based", note: "" } };
      if (url === "/mentoring/mentors") return { data: { mentors: [], sessions: [] } };
      return { data: [] };
    });
    const consent = { message: "This needs your permission first.", consent: "mentor_sharing", text: "Allow mentors you invite to see the parts of your profile you choose." };
    api.post.mockRejectedValueOnce(httpError(403, { detail: consent })).mockResolvedValueOnce({ data: { id: 1, status: "active", scopes: ["funnel"] } });
    api.put.mockResolvedValue({ data: [] });
    wrap(<MentorPage />);
    fireEvent.change(await screen.findByLabelText("Mentor's e-mail"), { target: { value: "coach@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /Invite/ }));
    expect(await screen.findByText(consent.text)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Allow sharing with mentors I invite/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/consents/mentor_sharing", { granted: true }));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post).toHaveBeenLastCalledWith("/mentoring/mentors", { mentor_email: "coach@example.com", scopes: ["funnel", "gaps", "actions"] });
  });
});
