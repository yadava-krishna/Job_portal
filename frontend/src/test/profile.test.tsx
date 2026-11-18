import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn(), patch: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn(), previewFile: vi.fn() }));

import { AnswerBank, NotificationSettings, NotificationTypeSettings, ResumeVersions } from "@/components/app/ProfileExtras";

const wrap = (ui: ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));

describe("resume versions", () => {
  it("lists versions, marks the default and lets another become default; the default cannot be deleted", async () => {
    api.get.mockResolvedValue({ data: [
      { id: 2, original_filename: "Resume - AR.pdf", size_bytes: 2048, page_count: 1, sha256: "", uploaded_at: "2026-11-05T10:00:00Z", is_active: true },
      { id: 1, original_filename: "Resume - FP&A.pdf", size_bytes: 2048, page_count: 2, sha256: "", uploaded_at: "2026-11-01T10:00:00Z", is_active: false },
    ] });
    api.post.mockResolvedValue({ data: [] });
    wrap(<ResumeVersions />);
    expect(await screen.findByText("Default")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(1);  // only the non-default one
    fireEvent.click(screen.getByRole("button", { name: /Make default/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/profile/resumes/1/default"));
  });
});

describe("answer bank", () => {
  it("adds and edits saved answers, and marks one-job answers so they are only suggested", () => {
    const onChange = vi.fn();
    const { rerender } = render(<AnswerBank facts={{}} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /Add an answer/ }));
    expect(onChange).toHaveBeenCalledWith({ custom_answers: [{ question: "", answer: "", applies_to: "any" }] });
    rerender(<AnswerBank facts={{ custom_answers: [{ question: "", answer: "", applies_to: "any" }] }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Answer 1"), { target: { value: "Yes" } });
    expect(onChange).toHaveBeenLastCalledWith({ custom_answers: [{ question: "", answer: "Yes", applies_to: "any" }] });
    fireEvent.change(screen.getByLabelText("Use answer 1 for"), { target: { value: "one_job" } });
    expect(onChange).toHaveBeenLastCalledWith({ custom_answers: [{ question: "", answer: "", applies_to: "one_job" }] });
    rerender(<AnswerBank facts={{ custom_answers: [{ question: "Why us?", answer: "x", applies_to: "one_job", updated_at: "2026-11-16T10:00:00Z" }] }} onChange={onChange} />);
    expect(screen.getByLabelText("Note for answer 1")).toBeInTheDocument();
    expect(screen.getByText(/^Saved /)).toBeInTheDocument();
  });
});

const ALL_ON = { new_match: true, follow_up_due: true, interview_upcoming: true, application_incomplete: true, listing_closed: true, discovery_failed: true };
const PREFS = { new_matches: true, delivery: "immediate", min_score: null, sources: [], email: "off", kinds: ALL_ON };

describe("notification preferences", () => {
  it("saves delivery, threshold and sources (only those fields); e-mail is shown as unavailable", async () => {
    api.get.mockResolvedValue({ data: PREFS });
    api.patch.mockImplementation(async (_u: string, body: object) => ({ data: { ...PREFS, ...body } }));
    wrap(<NotificationSettings />);
    expect(await screen.findByText(/E-mail delivery is not available yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lever" }));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/notifications/preferences",
      { delivery: "immediate", min_score: 75, sources: ["lever"] }));
  });
});

describe("alert type switches", () => {
  it("shows one switch per type with a description, and saves a change straight away", async () => {
    api.get.mockResolvedValue({ data: { ...PREFS, kinds: { ...ALL_ON, discovery_failed: false } } });
    let release: () => void = () => {};
    api.patch.mockImplementation((_u: string, body: { kinds: object }) =>
      new Promise((resolve) => { release = () => resolve({ data: { ...PREFS, kinds: { ...ALL_ON, discovery_failed: false, ...body.kinds } } }); }));
    wrap(<NotificationTypeSettings />);
    expect(screen.getByRole("status")).toHaveTextContent(/Loading your alert settings/);

    const switches = await screen.findAllByRole("switch");
    expect(switches).toHaveLength(6);
    expect(screen.getByRole("switch", { name: "Job search problems" })).not.toBeChecked();
    const closed = screen.getByRole("switch", { name: "Closed listings" });
    expect(closed).toBeChecked();
    expect(closed).toHaveAccessibleDescription("A job you saved or started applying for is no longer open.");

    fireEvent.click(closed);
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/notifications/preferences", { kinds: { listing_closed: false } }));
    expect(screen.getByLabelText("Saving")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Closed listings" })).not.toBeChecked();  // shown at once, while saving
    release();
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Closed listings" })).not.toBeChecked();
    expect(screen.getByRole("switch", { name: "Job search problems" })).not.toBeChecked();  // other switches untouched
  });

  it("puts the switch back and says why when saving fails", async () => {
    api.get.mockResolvedValue({ data: PREFS });
    api.patch.mockRejectedValue("The server is offline");
    wrap(<NotificationTypeSettings />);
    fireEvent.click(await screen.findByRole("switch", { name: "Interview reminders" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't save this change: The server is offline");
    expect(screen.getByRole("switch", { name: "Interview reminders" })).toBeChecked();
  });

  it("shows an error with a retry when the settings can't be loaded, and a note for an older server", async () => {
    api.get.mockRejectedValueOnce("Network Error");
    wrap(<NotificationTypeSettings />);
    expect(await screen.findByText("Your alert settings couldn't be loaded")).toBeInTheDocument();
    api.get.mockResolvedValue({ data: { ...PREFS, kinds: undefined } });
    fireEvent.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByText(/need a newer JobPilot server/)).toBeInTheDocument();
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
  });
});
