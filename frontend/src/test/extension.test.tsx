import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn() }));

import { ApplyDialog } from "@/components/app/ApplyDialog";
import { ExtensionSettings } from "@/components/app/ExtensionSettings";
import type { UserJob } from "@/types/api";

const wrap = (ui: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

const item = {
  user_job_id: 7, status: "new", is_saved: false, match_score: 80, match_category: "good", matching_skills: [], missing_skills: [],
  eligibility_status: null, scoring_method: null, discovered_at: "", saved_at: null, dismissed_at: null, application_id: null, application_status: null,
  job: { id: 1, platform: "Greenhouse", company: "Stripe", title: "AR Analyst", job_url: "https://stripe.com/jobs/search?gh_jid=8247127", sources: [] },
} as unknown as UserJob;

const app = { id: 5, status: "PREPARED", checklist: [], screening_answers: [], needs_candidate_input: [], resume_used: null, cover_letter: null, events: [] };

beforeEach(() => { Object.values(api).forEach((f) => f.mockReset()); });

describe("browser extension settings", () => {
  it("creates a single-use code with a countdown and lists connected browsers", async () => {
    api.get.mockResolvedValue({ data: [{ id: 3, name: "Chrome on laptop", scopes: [], created_at: "2026-11-05T10:00:00Z", last_used_at: null, expires_at: "2027-02-03T10:00:00Z" }] });
    api.post.mockResolvedValue({ data: { code: "AB12-CD34", expires_at: new Date(Date.now() + 300_000).toISOString(), expires_in_seconds: 300 } });
    wrap(<ExtensionSettings />);
    expect(await screen.findByText("Chrome on laptop")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Create connection code/ }));
    expect(await screen.findByText("AB12-CD34")).toBeInTheDocument();
    expect(screen.getByText(/Expires in 4:5\d|Expires in 5:00/)).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith("/extension/pairing-codes");
  });

  it("disconnects a browser through the API", async () => {
    api.get.mockResolvedValue({ data: [{ id: 9, name: "Work PC", scopes: [], created_at: "2026-11-05T10:00:00Z", last_used_at: null, expires_at: null }] });
    api.delete.mockResolvedValue({ data: null });
    wrap(<ExtensionSettings />);
    fireEvent.click(await screen.findByRole("button", { name: /Disconnect/ }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/extension/devices/9"));
  });
});

describe("apply destinations", () => {
  it("offers the verified Greenhouse-hosted form for employer-site listings, and opening it is not applying", async () => {
    api.post.mockImplementation(async (url: string) => ({ data: url.endsWith("/open") ? { application: { ...app, status: "OPENED" }, url: "" } : app }));
    api.get.mockResolvedValue({ data: { original_url: item.job.job_url, original_supported: false, platform: "Greenhouse",
      hosted_form_url: "https://job-boards.greenhouse.io/embed/job_app?for=stripe&token=8247127", direct_apply: false,
      message: "This listing is on the employer's own careers site, which Fill with JobPilot cannot fill." } });
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    const btn = await screen.findByRole("button", { name: /Open Greenhouse application form/ });
    expect(screen.getByText(/employer's own careers site/)).toBeInTheDocument();
    fireEvent.click(btn);
    expect(open).toHaveBeenCalledWith("https://job-boards.greenhouse.io/embed/job_app?for=stripe&token=8247127", "_blank", "noopener,noreferrer");
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/applications/5/open"));
    expect(api.post).not.toHaveBeenCalledWith(expect.stringContaining("/confirm"), expect.anything());
    open.mockRestore();
  });

  it("without a verified hosted form only the original listing is offered", async () => {
    api.post.mockResolvedValue({ data: app });
    api.get.mockResolvedValue({ data: { original_url: item.job.job_url, original_supported: false, platform: "Greenhouse", hosted_form_url: null,
      direct_apply: false, message: "Apply there manually." } });
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    expect(await screen.findByText("Apply there manually.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open original listing/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Greenhouse application form/ })).toBeNull();
  });
});
