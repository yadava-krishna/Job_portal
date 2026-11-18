import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn() }));

import { ApplyDialog } from "@/components/app/ApplyDialog";
import { canSmartApply } from "@/lib/smartApply";
import { ExtensionSettings } from "@/components/app/ExtensionSettings";
import type { UserJob } from "@/types/api";

const wrap = (ui: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

const item = {
  user_job_id: 7, status: "new", is_saved: false, match_score: 80, match_category: "good", matching_skills: [], missing_skills: [],
  eligibility_status: null, scoring_method: null, discovered_at: "", saved_at: null, dismissed_at: null, application_id: null, application_status: null,
  job: { id: 1, platform: "Greenhouse", company: "Stripe", title: "AR Analyst", job_url: "https://stripe.com/jobs/search?gh_jid=8247127", sources: [] },
} as unknown as UserJob;

const ghItem = { ...item, user_job_id: 11, job: { ...item.job, job_url: "https://job-boards.greenhouse.io/stripe/jobs/8247127" } } as unknown as UserJob;

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


describe("getting the extension from where you apply", () => {
  it("the apply dialog offers the extension download and the setup steps", async () => {
    api.get.mockImplementation(async (url: string) => url.includes("apply-options")
      ? { data: { message: "Open the form on Greenhouse.", original_supported: true, hosted_url: null } }
      : { data: {} });
    api.post.mockResolvedValue({ data: app });
    wrap(<ApplyDialog item={ghItem} onClose={() => {}} />);
    const cta = await screen.findByTestId("apply-extension-cta");
    expect(cta.querySelector("a[download]")?.getAttribute("href")).toMatch(/downloads\/jobpilot-smart-apply-2\.1\.0\.zip$/);
    expect(screen.getByText("How to set it up").getAttribute("href")).toBe("#/settings?tab=extension");
  });
});

describe("moving between apply steps", () => {
  it("goes back from the confirm step to the package without confirming anything", async () => {
    api.post.mockResolvedValue({ data: { ...app, status: "OPENED" } });
    api.get.mockResolvedValue({ data: { original_url: item.job.job_url, original_supported: true, platform: "Greenhouse", hosted_form_url: null,
      direct_apply: false, message: "Open the form on Greenhouse." } });
    wrap(<ApplyDialog item={item} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: /Back to package/ }));
    expect(await screen.findByRole("button", { name: /I already applied/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Yes, I submitted it/ })).toBeNull();
    expect(api.post).not.toHaveBeenCalledWith(expect.stringContaining("/confirm"), expect.anything());
  });
});


describe("one-click Smart Apply from JobPilot", () => {
  const sent: unknown[] = [];
  const fakeExtension = (status: { version: string; connected: boolean }) => {
    (globalThis as { chrome?: unknown }).chrome = { runtime: { sendMessage: (id: string, msg: { type: string }, cb: (r: unknown) => void) => {
      sent.push({ id, ...msg });
      cb(msg.type === "ping" ? { ok: true, data: status } : { ok: true, data: { tabId: 7 } });
    } } };
  };
  afterEach(() => { delete (globalThis as { chrome?: unknown }).chrome; sent.length = 0; });
  const setup = () => {
    api.post.mockResolvedValue({ data: app });
    api.get.mockResolvedValue({ data: { original_url: ghItem.job.job_url, original_supported: true, platform: "Greenhouse", hosted_form_url: null,
      direct_apply: false, message: "Open the form on Greenhouse." } });
  };

  it("when Smart Apply is connected, one button hands the job to it (and never confirms anything)", async () => {
    fakeExtension({ version: "2.1.0", connected: true });
    setup();
    wrap(<ApplyDialog item={ghItem} onClose={() => {}} />);
    expect(await screen.findByText("Smart Apply is ready.")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("smart-apply-start"));
    await waitFor(() => expect(sent).toContainEqual({ id: "ehpfmhhbnijflgagkpdbhiakldmgedgp", type: "apply", url: ghItem.job.job_url, userJobId: ghItem.user_job_id }));
    expect(screen.queryByTestId("apply-extension-cta")).toBeNull();
    expect(api.post).not.toHaveBeenCalledWith(expect.stringContaining("/confirm"), expect.anything());
  });

  it("installed but not connected: points to connecting, no one-click button", async () => {
    fakeExtension({ version: "2.1.0", connected: false });
    setup();
    wrap(<ApplyDialog item={ghItem} onClose={() => {}} />);
    expect(await screen.findByText("Connect it now")).toBeInTheDocument();
    expect(screen.queryByTestId("smart-apply-start")).toBeNull();
  });

  it("only Greenhouse, Lever and Ashby forms are offered for one-click applying", () => {
    expect(canSmartApply("https://jobs.lever.co/acme/123")).toBe(true);
    expect(canSmartApply("https://jobs.ashbyhq.com/acme/123")).toBe(true);
    expect(canSmartApply("https://www.linkedin.com/jobs/view/1")).toBe(false);
    expect(canSmartApply("http://jobs.lever.co/acme/123")).toBe(false);
    expect(canSmartApply(null)).toBe(false);
  });
});
