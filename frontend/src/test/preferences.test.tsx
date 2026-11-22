import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn(), previewFile: vi.fn() }));

import { PreferencesSheet } from "@/components/app/PreferencesSheet";
import { PreferencesForm, defaultPreferences } from "@/components/app/forms";

const wrap = (ui: ReactNode) =>
  render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider></MemoryRouter>);

const PREFS = { ...defaultPreferences, job_titles: ["AR Analyst"], is_configured: true };

describe("Job preferences", () => {
  let rescore = { requested_at: "2026-11-21T10:00:00Z", rescored_at: "2026-11-21T09:00:00Z", pending: true };
  beforeEach(() => {
    rescore = { requested_at: new Date().toISOString(), rescored_at: "2026-11-21T09:00:00Z", pending: true };
    api.get.mockImplementation(async (url: string) => ({ data: url === "/preferences/rescore" ? rescore : url === "/preferences" ? PREFS : [] }));
    api.put.mockImplementation(async () => ({ data: PREFS }));
  });

  it("explains what the experience range and weights do", () => {
    wrap(<PreferencesForm initial={PREFS} />);
    expect(screen.getByText(/Your experience range helps JobPilot prioritize roles that match your career level/)).toBeInTheDocument();
    expect(screen.getByText(/These weights control how much each factor contributes to your match score/)).toBeInTheDocument();
    expect(screen.getByText(/marked not eligible and shown last, not hidden/)).toBeInTheDocument();
  });

  it("after saving, says scores are updating, then that they're updated", async () => {
    wrap(<PreferencesForm initial={PREFS} />);
    fireEvent.click(screen.getByRole("button", { name: /Save preferences/ }));
    expect(await screen.findByTestId("rescore-pending")).toHaveTextContent("Jobs show their old scores until it's done");
    rescore = { ...rescore, rescored_at: new Date(Date.now() + 1000).toISOString(), pending: false };
    await waitFor(() => expect(screen.getByTestId("rescore-done")).toHaveTextContent("Match scores updated"), { timeout: 4000 });
  });

  it("opens from Discover with the same form, and closes straight away when nothing was changed", async () => {
    // (The save / discard / keep-editing prompt reacts only to real, trusted input: checked in the browser walkthrough.)
    const onOpenChange = vi.fn();
    wrap(<PreferencesSheet open onOpenChange={onOpenChange} />);
    expect(await screen.findByTestId("preferences-sheet")).toBeInTheDocument();
    expect(await screen.findByLabelText("Minimum experience")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save preferences/ })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Close" })[0]);
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(screen.queryByTestId("unsaved-dialog")).toBeNull();
  });
});
