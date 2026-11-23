import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
const auth = vi.hoisted(() => ({ role: "user" as string }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)), downloadFile: vi.fn(), previewFile: vi.fn() }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { id: 1, email: "u@example.com", role: auth.role } }) }));
// The Apply Workspace has its own tests (apply_workspace.test.tsx); here it only has to open with the chosen job.
vi.mock("@/components/app/ApplyDialog", () => ({
  ApplyDialog: ({ item }: { item: { job: { title: string } } | null }) => (item ? <div role="dialog" aria-label="Apply Workspace">{item.job.title}</div> : null),
}));

import { PortalConnections, type Portal } from "@/components/settings/PortalConnections";
import type { SetupRow } from "@/components/settings/portals/types";
import callbackScript from "../../public/oauth-callback.js?raw";

function Where() { const l = useLocation(); return <output data-testid="where">{l.pathname + l.search}</output>; }
const wrap = (ui: ReactNode) =>
  render(<MemoryRouter initialEntries={["/settings?tab=portals"]}><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}<Where /></QueryClientProvider></MemoryRouter>);

const cap = (available: boolean, detail = "d", extra: Record<string, unknown> = {}) => ({ available, detail, ...extra });
const NOT_SET = "LinkedIn sign-in isn't set up on this JobPilot server yet. A JobPilot admin needs to add LinkedIn developer app credentials.";
const caps = (o: Partial<Record<string, ReturnType<typeof cap>>> = {}) => ({
  identity_auth: cap(false, NOT_SET, { state: "not_configured" }), account_linked: cap(false, "Not linked."), profile_access: cap(false, "None."),
  listings: cap(false, "No jobs in JobPilot yet.", { count: 0 }), source: cap(true, "Paste a job link, use the clipper, or forward job-alert e-mails."),
  job_retrieval: cap(false, "Partner-only."), application_handoff: cap(true, "Apply Workspace."), native_handoff: cap(true, "Opens the original job."),
  assisted_submission: cap(false, "Forbidden by the portal's rules."), application_submission: cap(false, "No API."), profile_guidance: cap(true, "A checklist."),
  reconnect_required: cap(false, "No."), ...o,
});
const BASE = ["open", "import", "prepare", "browse"] as Portal["actions"];
const portal = (p: Portal["portal"], name: string, o: Partial<Portal> = {}): Portal => ({
  portal: p, name, url: { linkedin: "https://www.linkedin.com/jobs/", naukri: "https://www.naukri.com/", indeed: "https://in.indeed.com/" }[p],
  kind: p === "naukri" ? "native" : "oauth", summary: `${name} summary line.`, reason: p === "naukri" ? null : NOT_SET.replace(/LinkedIn/g, name),
  status: "not_configured", status_label: "Not configured", limited: false, setup_state: null,
  identity: null, scopes: { requested: p === "linkedin" ? ["openid", "profile", "email"] : [], granted: [] },
  actions: [...(p !== "indeed" ? ["optimize"] : []), ...BASE] as Portal["actions"], capabilities: caps() as Portal["capabilities"], ...o,
});
const naukri = portal("naukri", "Naukri", { status: "native_only", status_label: "Opens in browser",
  capabilities: caps({ identity_auth: cap(false, "Naukri offers no official sign-in for apps like JobPilot.", { state: "unavailable" }),
                       listings: cap(true, "1 Naukri job in your JobPilot feed.", { count: 1 }) }) as Portal["capabilities"] });
const ready = (): Portal => portal("linkedin", "LinkedIn", { status: "not_linked", status_label: "Ready to connect", reason: null,
  actions: ["connect", "optimize", ...BASE], capabilities: caps({ identity_auth: cap(true, "Sign In with LinkedIn", { state: "available" }) }) as Portal["capabilities"] });
const linked: Portal = portal("linkedin", "LinkedIn", {
  status: "linked", status_label: "Connected", reason: null, actions: ["check", "reconnect", "disconnect", "optimize", ...BASE],
  identity: { status: "linked", status_detail: null, name: "Test Candidate", email: "test.candidate@example.com", email_verified: true, has_picture: true,
              scopes: ["email", "openid", "profile"], linked_at: "2026-11-23T10:00:00Z", last_validated_at: "2026-11-23T10:00:00Z",
              access_expires_at: "2027-01-22T10:00:00Z", can_refresh: false },
  scopes: { requested: ["openid", "profile", "email"], granted: ["email", "openid", "profile"] },
  capabilities: caps({ identity_auth: cap(true, "Sign In with LinkedIn", { state: "available" }), account_linked: cap(true, "Linked as Test Candidate."),
                       profile_access: cap(true, "Name, E-mail address.", { fields: ["E-mail address", "Name"] }) }) as Portal["capabilities"],
});
const REVIEW = { portal: "linkedin", name: "LinkedIn", completeness: 50, source: "Built from your confirmed JobPilot profile.",
  items: [{ key: "headline", label: "Headline", state: "improve", existing: "Analyst", suggestion: "Senior Analyst at Alpha | Excel", why: "Mention the role.", copy: true, done_at: null }] };
const setupRow = (o: Partial<SetupRow> = {}): SetupRow => ({
  provider: "linkedin", name: "LinkedIn", product: "Sign In with LinkedIn using OpenID Connect",
  links: { console: "https://www.linkedin.com/developers/apps", docs: "https://learn.microsoft.com/x" }, state: "not_configured", configured: false,
  problem: "Not set up on this JobPilot server: an admin needs to add LinkedIn developer app credentials (Set up LinkedIn in Portal Connections, or LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET).",
  source: null, editable: true, client_id: null, has_secret: false, redirect_uri: "https://jobs.example.test/oauth-callback.html", redirect_from: "PUBLIC_APP_URL",
  redirect_problem: null, scopes: ["openid", "profile", "email"], simulated: false, pkce: false, env_names: ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"],
  last_test: null, updated_at: null, ...o,
});
const NAUKRI_JOB = { user_job_id: 41, status: "new", job: { title: "Accounts Receivable Analyst", company: "Acme Health", location: "Bengaluru", platform: "Naukri" } };

let rows: Portal[] = [];
let setup: SetupRow[] = [];
const mockLocation = () => {
  const assign = vi.fn();
  vi.spyOn(window, "location", "get").mockReturnValue({ ...window.location, href: "http://localhost:5199/#/settings?tab=portals", assign } as Location);
  return assign;
};
const card = (p: string) => screen.findByTestId(`portal-${p}`);
const actionRow = (el: HTMLElement) => el.querySelector("[data-actions]") as HTMLElement;

describe("Portal Connections overview", () => {
  beforeEach(() => {
    auth.role = "user";
    rows = [portal("linkedin", "LinkedIn"), naukri, portal("indeed", "Indeed")];
    setup = [setupRow(), setupRow({ provider: "indeed", name: "Indeed", product: "3-legged OAuth (Indeed Partner Console)", links: { console: "https://docs.indeed.com/getstarted/partner-console" },
                                    scopes: ["email", "offline_access"], pkce: true, env_names: ["INDEED_CLIENT_ID", "INDEED_CLIENT_SECRET"] })];
    api.get.mockImplementation(async (url: string) => ({
      data: url === "/portals" ? rows : url === "/admin/portals" ? setup : url === "/integrations/email" ? { enabled: false, has_password: false }
        : url === "/jobs" ? { items: [NAUKRI_JOB], total: 1 } : url.startsWith("/jobs/") ? NAUKRI_JOB : REVIEW,
    }));
    api.put.mockImplementation(async () => ({ data: { ...REVIEW, completeness: 100, items: [{ ...REVIEW.items[0], done_at: "2026-11-21T10:00:00Z" }] } }));
    sessionStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows three compact cards with logo, one line, real status and at most three actions; no capability wall", async () => {
    wrap(<PortalConnections />);
    const list = await screen.findByTestId("portal-connections");
    expect([...list.querySelectorAll("[data-testid^=portal-]")].map((e) => e.getAttribute("data-testid"))).toEqual(["portal-linkedin", "portal-naukri", "portal-indeed"]);
    expect(screen.getByText(/never asks for a portal password or OTP/)).toBeInTheDocument();
    for (const [p, label] of [["linkedin", "Not configured"], ["naukri", "Opens in browser"], ["indeed", "Not configured"]]) {
      const el = await card(p);
      expect(el.querySelector(`[data-logo=${p}]`)).not.toBeNull();
      expect(within(el).getByText(label)).toBeInTheDocument();
      expect(actionRow(el).querySelectorAll("button, a").length).toBeLessThanOrEqual(3);
      expect(el.querySelectorAll("[data-cap]").length).toBe(0);  // details live in the side panel
    }
    // One reason, said once per card.
    expect(within(await card("linkedin")).getAllByText(/admin needs to add/)).toHaveLength(1);
  });

  it("a candidate without configured sign-in gets no Connect or setup button, only what works", async () => {
    wrap(<PortalConnections />);
    const li = await card("linkedin");
    expect(within(li).queryByRole("button", { name: /Connect/ })).toBeNull();
    expect(within(li).queryByRole("button", { name: /Set up/ })).toBeNull();
    expect(within(li).getByRole("button", { name: "Import LinkedIn job" })).toBeInTheDocument();
    const open = within(li).getByRole("link", { name: /Open LinkedIn/ });
    expect(open).toHaveAttribute("href", "https://www.linkedin.com/jobs/");
    expect(open).toHaveAttribute("target", "_blank");
    expect(api.get).not.toHaveBeenCalledWith("/admin/portals");
  });

  it("every visible button in the cards opens a real flow", async () => {
    wrap(<PortalConnections />);
    for (const p of ["linkedin", "naukri", "indeed"]) {
      const el = await card(p);
      for (const link of within(el).queryAllByRole("link")) {
        expect(link.getAttribute("href")).toMatch(/^https:\/\//);
        expect(link).toHaveAttribute("rel", "noopener noreferrer");
      }
      const buttons = within(el).getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);
      for (const b of buttons) {
        fireEvent.click(b);
        const dialog = await screen.findByRole("dialog");
        expect(dialog.textContent!.length).toBeGreaterThan(20);
        fireEvent.keyDown(dialog, { key: "Escape" });
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      }
    }
  });

  it("Capabilities & limitations groups the details in a side panel that takes and gives back focus", async () => {
    wrap(<PortalConnections />);
    const trigger = within(await card("indeed")).getByRole("button", { name: /Capabilities & limitations/ });
    trigger.focus();
    fireEvent.click(trigger);
    const sheet = await screen.findByRole("dialog");
    await waitFor(() => expect(sheet.contains(document.activeElement)).toBe(true));
    expect(within(sheet).getAllByRole("region").map((r) => r.getAttribute("aria-label"))).toEqual(
      expect.arrayContaining(["Account", "Discovery", "Applications", "Profile improvement"]));
    expect(within(sheet).getByText("Indeed job API").closest("dt")).toHaveTextContent("not available");
    expect(within(sheet).getByText("Open the original posting").closest("dt")).toHaveTextContent("available");
    fireEvent.keyDown(sheet, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("Connect goes to the portal's own sign-in page in this tab and remembers which portal", async () => {
    rows[0] = ready();
    const assign = mockLocation();
    api.post.mockResolvedValue({ data: { authorization_url: "https://www.linkedin.com/oauth/v2/authorization?state=s" } });
    wrap(<PortalConnections />);
    const li = await card("linkedin");
    expect(within(li).getByText("Ready to connect")).toBeInTheDocument();
    fireEvent.click(within(li).getByRole("button", { name: "Connect with LinkedIn" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://www.linkedin.com/oauth/v2/authorization?state=s"));
    expect(api.post).toHaveBeenCalledWith("/portals/linkedin/connect");
    expect(JSON.parse(sessionStorage.getItem("jobpilot.oauthPending")!)).toEqual({ portal: "linkedin", purpose: "link" });
  });

  it("a failed sign-in shows the cause on that card with Try again", async () => {
    rows[0] = ready();
    sessionStorage.setItem("jobpilot.oauthReturn", JSON.stringify({ state: "st", error: "access_denied" }));
    sessionStorage.setItem("jobpilot.oauthPending", JSON.stringify({ portal: "linkedin", purpose: "link" }));
    api.post.mockRejectedValue(new Error("You cancelled on LinkedIn. Nothing was linked."));
    wrap(<PortalConnections />);
    const li = await card("linkedin");
    expect(await within(li).findByText("Connection failed")).toBeInTheDocument();
    expect(within(li).getByRole("alert")).toHaveTextContent("You cancelled on LinkedIn");
    expect(within(li).getByRole("button", { name: "Try again" })).toBeEnabled();
  });

  it("connected: shows verified provider data; Manage connection checks, and disconnects after confirming", async () => {
    rows[0] = linked;
    api.post.mockResolvedValue({ data: linked });
    const notLinked = ready();
    api.delete.mockResolvedValue({ data: { detail: "LinkedIn is disconnected and JobPilot deleted its access tokens.", portal: notLinked } });
    wrap(<PortalConnections />);
    const li = await card("linkedin");
    expect(within(li).getByText("Connected")).toBeInTheDocument();
    expect(within(li).getByTestId("identity-linkedin")).toHaveTextContent("Test Candidate · test.candidate@example.com");
    fireEvent.click(within(li).getByRole("button", { name: "Manage connection" }));
    const sheet = await screen.findByRole("dialog");
    expect(within(sheet).getByTestId("identity-linkedin")).toHaveTextContent("verified by LinkedIn");
    expect(within(sheet).getByTestId("identity-linkedin")).toHaveTextContent("Permissions you granted:emailopenidprofile");
    fireEvent.click(within(sheet).getByRole("button", { name: /Check connection/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/portals/linkedin/check"));
    expect(within(sheet).getByRole("button", { name: /Reconnect/ })).toBeInTheDocument();
    fireEvent.click(within(sheet).getByRole("button", { name: /Disconnect/ }));
    expect(api.delete).not.toHaveBeenCalled(); // asks first
    fireEvent.click(within(screen.getByRole("group", { name: "Disconnect LinkedIn" })).getByRole("button", { name: /Disconnect/ }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/portals/linkedin/connection"));
    expect(await within(screen.getByTestId("portal-linkedin")).findByText("Ready to connect")).toBeInTheDocument();
  });

  it("a check the portal can't answer shows Temporarily unavailable, not a broken link", async () => {
    rows[0] = linked;
    api.post.mockRejectedValue(Object.assign(new Error("LinkedIn returned an error (503)."), { isAxiosError: true, response: { status: 502 } }));
    wrap(<PortalConnections />);
    fireEvent.click(within(await card("linkedin")).getByRole("button", { name: "Manage connection" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: /Check connection/ }));
    expect(await within(screen.getByTestId("portal-linkedin")).findByText("Temporarily unavailable")).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(within(screen.getByTestId("portal-linkedin")).getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });

  it("simulated and limited links are labelled; a simulated one never claims LinkedIn verified it", async () => {
    rows[0] = { ...linked, simulated: true, status_label: "Connected (simulated)", identity: { ...linked.identity!, simulated: true } };
    rows[2] = { ...portal("indeed", "Indeed"), status: "linked", status_label: "Connected with limited permissions", limited: true, reason: null,
                actions: ["check", "reconnect", "disconnect", ...BASE], scopes: { requested: ["email", "offline_access"], granted: ["email"] },
                identity: { ...linked.identity!, name: null, scopes: ["email"] } };
    wrap(<PortalConnections />);
    const li = await card("linkedin");
    expect(within(li).getByText("Connected (simulated)")).toBeInTheDocument();
    expect(within(li).getByTestId("simulated-linkedin")).toHaveTextContent("This is not your LinkedIn account");
    fireEvent.click(within(li).getByRole("button", { name: "Manage connection" }));
    expect(within(await screen.findByRole("dialog")).getByTestId("identity-linkedin")).not.toHaveTextContent("verified by");
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const ind = await card("indeed");
    expect(within(ind).getByText("Connected with limited permissions")).toBeInTheDocument();
    fireEvent.click(within(ind).getByRole("button", { name: "Manage connection" }));
    expect(await within(await screen.findByRole("dialog")).findByText(/Not granted: offline_access/)).toBeInTheDocument();
  });

  it("finishes a sign-in left by the callback page exactly once; an unattributed refusal shows plainly", async () => {
    sessionStorage.setItem("jobpilot.oauthReturn", JSON.stringify({ state: "st", code: "c0de" }));
    api.post.mockImplementation(async () => { rows = [linked, naukri, rows[2]]; return { data: linked }; });
    const first = wrap(<PortalConnections />);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/portals/oauth/complete", { state: "st", code: "c0de" }));
    expect(sessionStorage.getItem("jobpilot.oauthReturn")).toBeNull();
    expect(await screen.findByTestId("identity-linkedin")).toBeInTheDocument();
    first.unmount();
    api.post.mockClear();
    sessionStorage.setItem("jobpilot.oauthReturn", JSON.stringify({ state: "other" }));
    api.post.mockRejectedValue(new Error("This sign-in was started from a different JobPilot account. Nothing was linked."));
    wrap(<PortalConnections />);
    expect(await screen.findByRole("alert")).toHaveTextContent("different JobPilot account");
    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it("the profile checklist opens in a panel with a suggestion, copy and mark done", async () => {
    wrap(<PortalConnections />);
    fireEvent.click(within(await card("linkedin")).getByRole("button", { name: /Profile checklist/ }));
    const item = await screen.findByTestId("item-headline");
    expect(item).toHaveTextContent("Senior Analyst at Alpha | Excel");
    fireEvent.click(within(item).getByRole("button", { name: /Mark done/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/portals/linkedin/review/headline", { done: true }));
    expect(await within(screen.getByTestId("item-headline")).findByText("Done")).toBeInTheDocument();
    expect(within(await card("indeed")).queryByRole("button", { name: /Profile checklist/ })).toBeNull();
  });
});

describe("Naukri hand-off, guided import and preparing an application", () => {
  beforeEach(() => {
    auth.role = "user";
    rows = [portal("linkedin", "LinkedIn"), naukri, portal("indeed", "Indeed")];
    api.get.mockImplementation(async (url: string) => ({
      data: url === "/portals" ? rows : url === "/integrations/email" ? { enabled: false, has_password: false }
        : url === "/jobs" ? { items: [NAUKRI_JOB], total: 1 } : url.startsWith("/jobs/") ? NAUKRI_JOB : REVIEW,
    }));
    sessionStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("Naukri never pretends to connect: Open Naukri opens naukri.com in a new tab and says how to come back", async () => {
    wrap(<PortalConnections />);
    const nk = await card("naukri");
    expect(within(nk).queryByRole("button", { name: /Connect|Set up|Reconnect/ })).toBeNull();
    const open = within(nk).getByRole("link", { name: /Open Naukri/ });
    expect(open).toHaveAttribute("href", "https://www.naukri.com/");
    expect(open).toHaveAttribute("target", "_blank");
    fireEvent.click(open);
    const back = within(nk).getByTestId("naukri-return");
    expect(back).toHaveTextContent("Copy its link");
    fireEvent.click(within(back).getByRole("button", { name: "import it" }));
    expect(await screen.findByTestId("guided-import")).toHaveTextContent("Import a Naukri link");
  });

  it("imports a Naukri link step by step: check, recognise, details, review, save, then prepare the application", async () => {
    const URL_ = "https://www.naukri.com/job-listings-ar-analyst-acme-120325001234";
    api.post.mockImplementation(async (url: string) => {
      if (url === "/jobs/import/preview") return { data: { recognized: true, platform: "Naukri", job_id: "120325001234", url: URL_, existing: null, detail: "Naukri job 120325001234." } };
      if (url === "/jobs/import") return { data: { run: { duplicates: 0 }, user_job_ids: [41], errors: [] } };
      throw new Error(`unexpected ${url}`);
    });
    wrap(<PortalConnections />);
    fireEvent.click(within(await card("naukri")).getByRole("button", { name: "Import Naukri job" }));
    const dlg = await screen.findByTestId("guided-import");
    fireEvent.change(within(dlg).getByLabelText("Job link"), { target: { value: "not a link" } });
    fireEvent.click(within(dlg).getByRole("button", { name: /Check link/ }));
    expect(await within(dlg).findByRole("alert")).toHaveTextContent("doesn't look like a link");
    expect(api.post).not.toHaveBeenCalled();
    fireEvent.change(within(dlg).getByLabelText("Job link"), { target: { value: URL_ } });
    fireEvent.click(within(dlg).getByRole("button", { name: /Check link/ }));
    expect(await within(dlg).findByTestId("link-recognised")).toHaveTextContent("Naukri job 120325001234 recognised");
    fireEvent.click(within(dlg).getByRole("button", { name: /Add details/ }));
    fireEvent.change(within(dlg).getByLabelText("Job title (required)"), { target: { value: "Accounts Receivable Analyst" } });
    fireEvent.change(within(dlg).getByLabelText("Company"), { target: { value: "Acme Health" } });
    fireEvent.click(within(dlg).getByRole("button", { name: "Review" }));
    const review = within(dlg).getByTestId("import-review");
    expect(review).toHaveTextContent("PortalNaukri");
    expect(review).toHaveTextContent("Job ID120325001234");
    expect(api.post).toHaveBeenCalledTimes(1);  // nothing saved before confirming
    fireEvent.click(within(dlg).getByRole("button", { name: "Save & score" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/jobs/import", expect.objectContaining({ url: URL_, platform: null, title: "Accounts Receivable Analyst", company: "Acme Health" })));
    expect(await within(dlg).findByTestId("import-done")).toHaveTextContent("Added to your jobs and scored");
    fireEvent.click(within(dlg).getByRole("button", { name: /Prepare application/ }));
    expect(await screen.findByRole("dialog", { name: "Apply Workspace" })).toHaveTextContent("Accounts Receivable Analyst");
    expect(api.get).toHaveBeenCalledWith("/jobs/41");
  });

  it("an unrecognised link can still be entered by hand, without saving the unknown link", async () => {
    api.post.mockImplementation(async (url: string) => (url === "/jobs/import/preview"
      ? { data: { recognized: false, platform: null, job_id: null, url: null, existing: null, detail: "That isn't a LinkedIn, Indeed or Naukri job link JobPilot recognises." } }
      : { data: { run: { duplicates: 0 }, user_job_ids: [41], errors: [] } }));
    wrap(<PortalConnections />);
    fireEvent.click(within(await screen.findByTestId("find-jobs")).getByRole("button", { name: /Import a link/ }));
    const dlg = await screen.findByTestId("guided-import");
    fireEvent.change(within(dlg).getByLabelText("Job link"), { target: { value: "https://careers.example.com/job/1" } });
    fireEvent.click(within(dlg).getByRole("button", { name: /Check link/ }));
    expect(await within(dlg).findByTestId("link-unrecognised")).toHaveTextContent("isn't a LinkedIn, Indeed or Naukri job link");
    fireEvent.click(within(dlg).getByRole("button", { name: "Enter details manually" }));
    fireEvent.change(within(dlg).getByLabelText("Portal"), { target: { value: "Indeed" } });
    fireEvent.change(within(dlg).getByLabelText("Job title (required)"), { target: { value: "AR Analyst" } });
    fireEvent.click(within(dlg).getByRole("button", { name: "Review" }));
    expect(within(dlg).getByTestId("import-review")).toHaveTextContent("LinkNot saved");
    fireEvent.click(within(dlg).getByRole("button", { name: "Save & score" }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/jobs/import", expect.objectContaining({ url: null, platform: "Indeed", title: "AR Analyst" })));
  });

  it("a link already in your feed goes straight to preparing the application", async () => {
    api.post.mockResolvedValue({ data: { recognized: true, platform: "Naukri", job_id: "1", url: "https://www.naukri.com/x-1", detail: "",
                                         existing: { user_job_id: 41, title: "Accounts Receivable Analyst", company: "Acme Health" } } });
    wrap(<PortalConnections />);
    fireEvent.click(within(await card("naukri")).getByRole("button", { name: "Import Naukri job" }));
    const dlg = await screen.findByTestId("guided-import");
    fireEvent.change(within(dlg).getByLabelText("Job link"), { target: { value: "https://www.naukri.com/x-1" } });
    fireEvent.click(within(dlg).getByRole("button", { name: /Check link/ }));
    expect(await within(dlg).findByText(/Already in your jobs/)).toBeInTheDocument();
    fireEvent.click(within(dlg).getByRole("button", { name: /Prepare application/ }));
    expect(await screen.findByRole("dialog", { name: "Apply Workspace" })).toBeInTheDocument();
  });

  it("Prepare application lists that portal's jobs and opens the Apply Workspace with the one picked", async () => {
    wrap(<PortalConnections />);
    fireEvent.click(within(await card("naukri")).getByRole("button", { name: "Prepare application" }));
    const sheet = await screen.findByTestId("prepare-sheet");
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/jobs", expect.objectContaining({ params: expect.any(URLSearchParams) })));
    const params = api.get.mock.calls.find((c) => c[0] === "/jobs")![1].params as URLSearchParams;
    expect(params.get("platform")).toBe("Naukri");
    fireEvent.click(await within(sheet).findByRole("button", { name: /Prepare/ }));
    expect(await screen.findByRole("dialog", { name: "Apply Workspace" })).toHaveTextContent("Accounts Receivable Analyst");
  });

  it("Find or import jobs: browse by portal, clipper and alert e-mail setup open the existing flows", async () => {
    wrap(<PortalConnections />);
    const find = await screen.findByTestId("find-jobs");
    fireEvent.click(within(find).getByRole("button", { name: "Naukri · 1" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/discover?platform=Naukri");
    fireEvent.click(within(find).getByRole("button", { name: "Set up the clipper" }));
    expect(await screen.findByText("Clip to JobPilot", { exact: false })).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(within(find).getByRole("button", { name: "Connect your mailbox" }));
    expect(await screen.findByText("Job-alert emails")).toBeInTheDocument();
    expect(within(find).getByTestId("next-steps")).toHaveTextContent("choose a resume");
  });
});

describe("Admin setup (LinkedIn, Indeed)", () => {
  beforeEach(() => {
    auth.role = "admin";
    rows = [{ ...portal("linkedin", "LinkedIn"), setup_state: "not_configured", actions: ["optimize", ...BASE, "setup"],
              reason: "LinkedIn sign-in isn't set up on this JobPilot server yet. Set it up with your developer app's credentials." },
            naukri, { ...portal("indeed", "Indeed"), setup_state: "not_configured", actions: [...BASE, "setup"] }];
    setup = [setupRow(), setupRow({ provider: "indeed", name: "Indeed", product: "3-legged OAuth (Indeed Partner Console)", links: { console: "https://docs.indeed.com/getstarted/partner-console" },
                                    scopes: ["email", "offline_access"], pkce: true, env_names: ["INDEED_CLIENT_ID", "INDEED_CLIENT_SECRET"] })];
    api.get.mockImplementation(async (url: string) => ({
      data: url === "/portals" ? rows : url === "/admin/portals" ? setup : url === "/integrations/email" ? { enabled: false, has_password: false } : REVIEW,
    }));
    sessionStorage.clear();
  });
  afterEach(() => vi.restoreAllMocks());

  it("walks an admin through LinkedIn setup: developer app, product, the configured callback URL, masked credentials", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    api.put.mockImplementation(async (_url: string, body: Record<string, string>) => ({
      data: setupRow({ state: "ready_to_test", configured: true, problem: null, source: "admin", client_id: body.client_id, has_secret: true }),
    }));
    wrap(<PortalConnections />);
    fireEvent.click(within(await card("linkedin")).getByRole("button", { name: "Set up LinkedIn" }));
    const sheet = await screen.findByTestId("setup-sheet");
    expect(await within(sheet).findByRole("link", { name: /Open LinkedIn Developers/ })).toHaveAttribute("href", "https://www.linkedin.com/developers/apps");
    expect(sheet).toHaveTextContent("Company Page");
    expect(sheet).toHaveTextContent("Sign In with LinkedIn using OpenID Connect");
    const cb = within(sheet).getByTestId("callback-url") as HTMLInputElement;
    expect(cb.value).toBe("https://jobs.example.test/oauth-callback.html");
    expect(cb).toHaveAttribute("readonly");
    fireEvent.click(within(sheet).getByRole("button", { name: /Copy/ }));
    expect(writeText).toHaveBeenCalledWith("https://jobs.example.test/oauth-callback.html");
    expect(within(sheet).getByRole("button", { name: /Test connection/ })).toBeDisabled();  // nothing to test yet
    const secret = within(sheet).getByLabelText("Client Secret") as HTMLInputElement;
    expect(secret.type).toBe("password");
    fireEvent.change(within(sheet).getByLabelText("Client ID"), { target: { value: "86abc123" } });
    fireEvent.change(secret, { target: { value: "s3cr3t-value" } });
    fireEvent.click(within(sheet).getByRole("button", { name: /Save credentials/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/admin/portals/linkedin/credentials", { client_id: "86abc123", client_secret: "s3cr3t-value" }));
    await waitFor(() => expect((within(sheet).getByLabelText("Client Secret") as HTMLInputElement).value).toBe(""));
    expect(sheet.textContent).not.toContain("s3cr3t-value");
    expect(await within(sheet).findByText("Ready to test")).toBeInTheDocument();
    expect(within(sheet).getByRole("button", { name: /Test connection/ })).toBeEnabled();
  });

  it("without a known public address it says what to set instead of inventing localhost", async () => {
    setup[0] = setupRow({ redirect_uri: null, redirect_from: null, redirect_problem: "The server doesn't know its public address: set PUBLIC_APP_URL (or LINKEDIN_REDIRECT_URI)." });
    mockLocation();
    wrap(<PortalConnections />);
    fireEvent.click(within(await card("linkedin")).getByRole("button", { name: "Set up LinkedIn" }));
    const sheet = await screen.findByTestId("setup-sheet");
    expect(await within(sheet).findByText(/doesn't know its public address/)).toBeInTheDocument();
    expect(within(sheet).queryByTestId("callback-url")).toBeNull();
  });

  it("Test connection runs the real sign-in and shows the verified result when it comes back", async () => {
    setup[0] = setupRow({ state: "ready_to_test", configured: true, problem: null, source: "admin", client_id: "86abc123", has_secret: true });
    const assign = mockLocation();
    api.post.mockResolvedValue({ data: { authorization_url: "https://www.linkedin.com/oauth/v2/authorization?state=t" } });
    const first = wrap(<PortalConnections />);
    fireEvent.click(within(await card("linkedin")).getByRole("button", { name: "Set up LinkedIn" }));
    fireEvent.click(await within(await screen.findByTestId("setup-sheet")).findByRole("button", { name: /Test connection/ }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://www.linkedin.com/oauth/v2/authorization?state=t"));
    expect(api.post).toHaveBeenCalledWith("/admin/portals/linkedin/test");
    expect(JSON.parse(sessionStorage.getItem("jobpilot.oauthPending")!)).toEqual({ portal: "linkedin", purpose: "test" });
    first.unmount();
    // Back from LinkedIn.
    sessionStorage.setItem("jobpilot.oauthReturn", JSON.stringify({ state: "t", code: "c" }));
    const test = { provider: "linkedin", status: "verified", simulated: false, at: "2026-11-23T12:00:00Z", detail: "Signed in with LinkedIn, verified the ID token and account. Nothing was linked or kept." };
    setup[0] = { ...setup[0], state: "verified", last_test: test as SetupRow["last_test"] };
    api.post.mockResolvedValue({ data: { ...rows[0], setup_test: test } });
    wrap(<PortalConnections />);
    const sheet = await screen.findByTestId("setup-sheet");
    expect(await within(sheet).findByTestId("last-test")).toHaveTextContent("Verified with the real LinkedIn");
    expect(within(sheet).getByTestId("scope-status")).toHaveTextContent("confirmed by a real sign-in");
  });

  it("a server on the local simulator can't be 'tested', and env-set credentials aren't editable here", async () => {
    setup[0] = setupRow({ state: "simulated", configured: true, problem: null, source: "env", editable: false, client_id: "sim-linkedin-client", has_secret: true, simulated: true });
    rows[0] = { ...ready(), simulated: true, status_label: "Ready to connect (simulated)", setup_state: "simulated", actions: ["connect", "optimize", ...BASE, "setup"] };
    wrap(<PortalConnections />);
    const li = await card("linkedin");
    expect(within(li).getByRole("button", { name: "Connect with LinkedIn (simulated)" })).toBeInTheDocument();
    fireEvent.click(within(li).getByRole("button", { name: /^Setup$/ }));
    const sheet = await screen.findByTestId("setup-sheet");
    expect(await within(sheet).findByTestId("test-simulated")).toHaveTextContent("local simulator");
    expect(within(sheet).getByRole("button", { name: /Test connection/ })).toBeDisabled();
    expect(within(sheet).getByTestId("env-credentials")).toHaveTextContent("environment");
    expect(within(sheet).queryByLabelText("Client Secret")).toBeNull();
  });

  it("Indeed setup explains partner approval, the Partner Console and the scopes", async () => {
    wrap(<PortalConnections />);
    fireEvent.click(within(await card("indeed")).getByRole("button", { name: "Set up Indeed" }));
    const sheet = await screen.findByTestId("setup-sheet");
    expect(await within(sheet).findByRole("link", { name: /Partner Console/ })).toHaveAttribute("href", "https://docs.indeed.com/getstarted/partner-console");
    expect(sheet).toHaveTextContent("approval isn't automatic");
    expect(within(sheet).getByLabelText("Scopes JobPilot requests")).toHaveTextContent("emailoffline_access");
    expect(sheet).toHaveTextContent("employer_access");
    expect(within(sheet).getByTestId("scope-status")).toHaveTextContent("not verified yet");
  });

  it("a refused app shows Provider authorization required to the admin with Review setup", async () => {
    rows[0] = { ...rows[0], status: "authorization_required", status_label: "Provider authorization required", setup_state: "authorization_required",
                reason: "LinkedIn refused JobPilot's app in the last test, so connecting won't work yet. Check the app in setup, then test again." };
    wrap(<PortalConnections />);
    const li = await card("linkedin");
    expect(within(li).getByText("Provider authorization required")).toBeInTheDocument();
    expect(within(li).queryByRole("button", { name: /Connect/ })).toBeNull();
    expect(within(li).getByRole("button", { name: "Review setup" })).toBeInTheDocument();
  });
});

describe("oauth-callback.js (the registered redirect page)", () => {
  const code = callbackScript;
  const run = (search: string) => {
    const store = new Map<string, string>();
    const win = { location: { search, replace: vi.fn() }, sessionStorage: { setItem: (k: string, v: string) => store.set(k, v) } };
    new Function("window", code)(win);
    return { store, replace: win.location.replace };
  };

  it("keeps only the OAuth response fields and returns to a fixed page", () => {
    const { store, replace } = run("?code=abc&state=xyz&iss=https%3A%2F%2Fsecure.indeed.com&next=https://evil.example&token=t");
    expect(JSON.parse(store.get("jobpilot.oauthReturn")!)).toEqual({ code: "abc", state: "xyz", iss: "https://secure.indeed.com" });
    expect(replace).toHaveBeenCalledWith("./#/settings?tab=portals");
  });

  it("stores nothing without a state, and still goes back", () => {
    const { store, replace } = run("?code=abc");
    expect(store.size).toBe(0);
    expect(replace).toHaveBeenCalledWith("./#/settings?tab=portals");
  });
});
