import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn(), put: vi.fn() }));
vi.mock("@/lib/api", () => ({ api, errorMessage: (e: unknown) => String(e), downloadFile: vi.fn(), previewFile: vi.fn() }));

import { AnswerBank, NotificationSettings, ResumeVersions } from "@/components/app/ProfileExtras";

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
  it("adds and edits saved answers", () => {
    const onChange = vi.fn();
    const { rerender } = render(<AnswerBank facts={{}} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /Add an answer/ }));
    expect(onChange).toHaveBeenCalledWith({ custom_answers: [{ question: "", answer: "" }] });
    rerender(<AnswerBank facts={{ custom_answers: [{ question: "", answer: "" }] }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Answer 1"), { target: { value: "Yes" } });
    expect(onChange).toHaveBeenLastCalledWith({ custom_answers: [{ question: "", answer: "Yes" }] });
  });
});

describe("notification preferences", () => {
  it("saves delivery, threshold and sources; e-mail is shown as unavailable", async () => {
    api.get.mockResolvedValue({ data: { new_matches: true, delivery: "immediate", min_score: null, sources: [], email: "off" } });
    api.put.mockImplementation(async (_u: string, body: unknown) => ({ data: body }));
    wrap(<NotificationSettings />);
    expect(await screen.findByText(/E-mail delivery is not available yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Lever" }));
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/notifications/preferences",
      { new_matches: true, delivery: "immediate", min_score: 75, sources: ["lever"], email: "off" }));
  });
});
