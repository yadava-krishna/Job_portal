import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn(), previewFile: vi.fn() }));

import { StudioPage } from "@/pages/StudioPage";
import type { Section, Suggestion, Version, VersionSummary } from "@/features/studio/api";

const summary = (over: Partial<VersionSummary>): VersionSummary => ({
  id: 1, name: "AR analyst", template_key: "ats_simple", template_name: "ATS Simple", ats_safe: true, status: "draft", locked_at: null,
  revision: 3, settings: { font_size: 10.5, density: "normal", page_size: "A4" }, target_job_id: null, parent_id: null,
  created_at: "2026-11-01T10:00:00Z", updated_at: "2026-11-09T10:00:00Z", checksum: "abc", ...over,
});

const sections: Section[] = [
  { id: 10, type: "header", heading: "Contact", visible: true, blocks: [
    { id: 11, type: "contact", source_profile_ref: "profile:contact", visible: true, bullets: [],
      content: { name: "Asha Rao", headline: "AR analyst", email: "asha@example.com", phone: null, location: "Pune", links: [] } }] },
  { id: 20, type: "experience", heading: "Experience", visible: true, blocks: [
    { id: 21, type: "entry", source_profile_ref: "experience:0", visible: true,
      content: { title: "AR Executive", organization: "Acme", start: "2022", end: null, current: true },
      bullets: [{ id: 22, text: "Responsible for reconciling 400 accounts monthly", evidence_refs: ["experience:0"], source: "profile", approved: true }] }] },
  { id: 30, type: "skills", heading: "Skills", visible: true, blocks: [
    { id: 31, type: "skill_group", source_profile_ref: "profile:skills", visible: true, bullets: [], content: { label: null, items: ["Excel", "SAP"] } }] },
];

const version = (over: Partial<Version> = {}): Version => ({ ...summary({}), sections, ...over });

const rewrite: Suggestion = {
  id: "w1-0-0", kind: "rewrite", where: { section: 1, block: 0, bullet: 0 },
  before: "Responsible for reconciling 400 accounts monthly", after: "Reconciled 400 accounts monthly",
  evidence: "supported", reason: "Same facts, stronger opening verb.",
};

function routeGets(map: Record<string, unknown>) {
  api.get.mockImplementation(async (url: string) => {
    if (url.endsWith("/preview.pdf")) return { data: new Blob(["%PDF"]), headers: { "x-page-count": "1" } };
    if (url === "/jobs") return { data: { items: [], total: 0, hidden_unknown_dates: 0, page: 1, page_size: 100 } };
    if (url === "/studio/templates") return { data: [] };
    if (url in map) return { data: map[url] };
    throw new Error(`unexpected GET ${url}`);
  });
}

const renderAt = (path: string) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/studio" element={<StudioPage />} />
          <Route path="/studio/:id" element={<StudioPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

describe("resume studio list", () => {
  it("lists versions with template, status and where each was copied from", async () => {
    routeGets({ "/studio/versions": [
      summary({ id: 2, name: "AR analyst — Stripe", status: "locked", parent_id: 1, template_name: "Modern Professional", ats_safe: false }),
      summary({ id: 1, name: "AR analyst" }),
    ] });
    renderAt("/studio");
    const row = (await screen.findByRole("link", { name: "AR analyst — Stripe" })).closest("tr")!;
    expect(within(row).getByText("Locked — used in an application")).toBeInTheDocument();
    expect(within(row).getByText("Modern Professional")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "AR analyst" })).toHaveAttribute("href", "/studio/1");
    expect(within(row).getByRole("button", { name: "Delete AR analyst — Stripe" })).toBeDisabled();
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("explains that a new resume is built from the confirmed profile when there are none", async () => {
    routeGets({ "/studio/versions": [] });
    renderAt("/studio");
    expect(await screen.findByText(/starts from your confirmed profile/)).toBeInTheDocument();
  });
});

describe("resume studio editor", () => {
  it("shows a read-only banner for a locked version and disables editing", async () => {
    routeGets({ "/studio/versions/2": version({ id: 2, status: "locked", locked_at: "2026-11-08T10:00:00Z" }), "/studio/versions": [] });
    renderAt("/studio/2");
    expect(await screen.findByText(/kept exactly as sent\. Make a copy to edit\./)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Make a copy/ }).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Resume name")).toBeDisabled();
    expect(screen.getByLabelText("Job title")).toBeDisabled();
    expect(screen.getByLabelText("Bullet 1")).toBeDisabled();
    expect(screen.getByLabelText("Full name")).toBeDisabled();
    expect(screen.getByText("from profile")).toBeInTheDocument();
  });

  it("accepting a rewrite suggestion updates the bullet, marks it as not from the profile and autosaves", async () => {
    routeGets({ "/studio/versions/1": version(), "/studio/versions": [], "/studio/versions/1/suggestions": [rewrite] });
    api.put.mockImplementation(async (_url: string, body: { revision: number }) => ({ data: { ...version(), revision: body.revision + 1 } }));
    renderAt("/studio/1");
    expect(await screen.findByLabelText("Bullet 1")).toHaveValue(rewrite.before);

    fireEvent.click(screen.getByRole("tab", { name: "Suggestions" }));
    expect(await screen.findByText(rewrite.after!)).toBeInTheDocument();
    expect(screen.getByText("Backed by your profile")).toBeInTheDocument();
    expect(api.put).not.toHaveBeenCalled();  // suggest-only: nothing is applied until accepted
    fireEvent.click(screen.getByRole("button", { name: /Accept/ }));
    await waitFor(() => expect(screen.queryByRole("button", { name: /Accept/ })).toBeNull());

    fireEvent.click(screen.getByRole("tab", { name: "Content" }));
    expect(await screen.findByLabelText("Bullet 1")).toHaveValue(rewrite.after);
    expect(screen.getByText("not from your profile")).toBeInTheDocument();

    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1), { timeout: 3000 });
    const [url, body] = api.put.mock.calls[0] as [string, { revision: number; sections: Section[] }];
    expect(url).toBe("/studio/versions/1");
    expect(body.revision).toBe(3);
    const bullet = body.sections[1].blocks[0].bullets[0];
    expect(bullet).toMatchObject({ text: rewrite.after, source: "suggestion" });
    expect(bullet).not.toHaveProperty("_k");
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });
});
