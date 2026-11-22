import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn(), previewFile: vi.fn() }));

import { ProfileForm } from "@/components/app/forms";
import type { EditableProfile, ProfileResponse, ProfileReview } from "@/types/api";

const wrap = (ui: ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

const base: EditableProfile = {
  full_name: "Test Candidate", email: "t@example.com", phone: "+91 9000000000", location: "Bengaluru, Karnataka", headline: "Finance Analyst",
  summary: null, skills: ["Excel"], experience: [{ title: "Analyst", company: "Beta", start: "2020-06", end: null, is_current: true, bullets: [] }],
  education: [], certifications: [], projects: [], achievements: [], languages: [],
};
const profile = (review: ProfileReview, over: Partial<ProfileResponse> = {}): ProfileResponse => ({
  has_resume: true, resume: null, parsed: base, confirmed: base, confirmed_at: "2026-11-01T00:00:00Z", experience: null, parse_warnings: [],
  verified_facts: {}, review, ...over,
});
const f = (key: string, state: string, extra: object = {}) => ({ key, label: key, group: "x", state, ...extra }) as ProfileReview["fields"][number];

describe("Profile review after a resume is read", () => {
  beforeEach(() => { api.put.mockReset(); api.put.mockResolvedValue({ data: profile({ status: "confirmed", parsed_at: null, confirmed_at: null, pending: 0, fields: [] }) }); });

  it("says nothing is used until saved, and marks extracted and missing fields", () => {
    const review: ProfileReview = { status: "unconfirmed", parsed_at: "2026-11-21T00:00:00Z", confirmed_at: null, pending: 2,
      fields: [f("full_name", "extracted"), f("phone", "missing", { detail: "Not found on your resume. Add it yourself." })] };
    wrap(<ProfileForm profile={profile(review, { confirmed: null, confirmed_at: null })} />);
    expect(screen.getByTestId("profile-review-banner")).toHaveTextContent("Nothing here is used for matching or applications until you save");
    expect(screen.getByTestId("state-full_name")).toHaveTextContent("From resume");
    expect(screen.getByTestId("state-phone")).toHaveTextContent("Missing");
    expect(screen.getByText("Not found on your resume. Add it yourself.")).toBeInTheDocument();
  });

  it("offers a newer resume's values without changing anything until the user takes one and saves", async () => {
    const review: ProfileReview = { status: "needs_review", parsed_at: "2026-11-21T00:00:00Z", confirmed_at: "2026-11-01T00:00:00Z", pending: 2,
      fields: [f("location", "conflict", { extracted: "Hyderabad, Telangana", confirmed: "Bengaluru, Karnataka" }),
               f("experience", "conflict", { extracted: [{ title: "Lead Analyst", company: "Gamma Corp", start: "2024-04", end: null, is_current: true, bullets: [] }] }),
               f("full_name", "confirmed")] };
    wrap(<ProfileForm profile={profile(review)} />);
    expect(screen.getByTestId("profile-review-banner")).toHaveTextContent("Nothing was changed");
    const loc = screen.getByLabelText(/^Location/) as HTMLInputElement;
    expect(loc.value).toBe("Bengaluru, Karnataka");
    expect(screen.queryByTestId("state-full_name")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Use this/ }));
    expect(loc.value).toBe("Hyderabad, Telangana");
    expect(screen.queryByRole("button", { name: /Use this/ })).toBeNull();  // taken: the suggestion goes away
    fireEvent.click(within(screen.getByTestId("suggest-experience")).getByRole("button", { name: /Add it/ }));
    expect(screen.queryByTestId("suggest-experience")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Save profile/ }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const sent = api.put.mock.calls[0][1] as EditableProfile;
    expect(sent.location).toBe("Hyderabad, Telangana");
    expect(sent.experience.map((r) => r.company)).toEqual(["Beta", "Gamma Corp"]);
  });

  it("shows nothing extra for a confirmed profile", () => {
    wrap(<ProfileForm profile={profile({ status: "confirmed", parsed_at: null, confirmed_at: null, pending: 0, fields: [f("location", "confirmed")] })} />);
    expect(screen.queryByTestId("profile-review-banner")).toBeNull();
    expect(screen.queryByTestId("state-location")).toBeNull();
  });
});
