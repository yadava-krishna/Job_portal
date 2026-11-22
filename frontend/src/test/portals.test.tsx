import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn(), previewFile: vi.fn() }));

import { PortalConnections } from "@/components/settings/PortalConnections";

const wrap = (ui: ReactNode) =>
  render(<MemoryRouter><QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider></MemoryRouter>);

const cap = (available: boolean, detail = "d") => ({ available, detail });
const portal = (p: string, name: string, guidance: boolean) => ({
  portal: p, name, url: `https://${p}.example`, actions: [...(guidance ? ["optimize"] : []), "open", "import"],
  capabilities: { source: cap(true), profile_guidance: cap(guidance), account_connection: cap(false, `${name} offers no approved connection.`),
                  application_handoff: cap(true), assisted_submission: cap(false) },
});
const REVIEW = { portal: "linkedin", name: "LinkedIn", completeness: 50, source: "Built from your confirmed JobPilot profile.",
  items: [{ key: "headline", label: "Headline", state: "improve", existing: "Analyst", suggestion: "Senior Analyst at Alpha | Excel", why: "Mention the role.", copy: true, done_at: null }] };

describe("Portal Connections", () => {
  beforeEach(() => {
    api.get.mockImplementation(async (url: string) => ({ data: url === "/portals" ? [portal("linkedin", "LinkedIn", true), portal("indeed", "Indeed", false)] : REVIEW }));
    api.put.mockImplementation(async () => ({ data: { ...REVIEW, completeness: 100, items: [{ ...REVIEW.items[0], done_at: "2026-11-21T10:00:00Z" }] } }));
  });

  it("never offers a Connect button, says each portal isn't connected, and offers only working actions", async () => {
    wrap(<PortalConnections />);
    expect(screen.getByText(/never signs in to a portal for you/)).toBeInTheDocument();
    const li = await screen.findByTestId("portal-linkedin");
    expect(within(li).getByText(/offers no approved connection/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^connect/i })).toBeNull();
    expect(within(li).getByRole("button", { name: /Optimize profile/ })).toBeInTheDocument();
    const indeed = screen.getByTestId("portal-indeed");
    expect(within(indeed).queryByRole("button", { name: /Optimize profile/ })).toBeNull();
    expect(within(indeed).getByRole("button", { name: /Import job link/ })).toBeInTheDocument();
    expect(within(indeed).getByText("Account connection").parentElement).toHaveTextContent("not available");
  });

  it("shows the checklist with existing text, a suggestion, copy, and mark done", async () => {
    wrap(<PortalConnections />);
    fireEvent.click(within(await screen.findByTestId("portal-linkedin")).getByRole("button", { name: /Optimize profile/ }));
    const item = await screen.findByTestId("item-headline");
    expect(item).toHaveTextContent("Now: Analyst");
    expect(item).toHaveTextContent("Suggested: Senior Analyst at Alpha | Excel");
    fireEvent.click(within(item).getByRole("button", { name: /Mark done/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/portals/linkedin/review/headline", { done: true }));
    expect(await within(screen.getByTestId("item-headline")).findByText("Done")).toBeInTheDocument();
  });
});
