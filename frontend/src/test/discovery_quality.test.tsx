import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JobCard } from "@/components/app/JobCard";
import { MatchBreakdown } from "@/features/growth/MatchBreakdown";
import type { MatchBreakdown as Breakdown } from "@/features/growth/types";
import type { UserJob } from "@/types/api";

const job = (over: Partial<UserJob["job"]> = {}, item: Partial<UserJob> = {}): UserJob => ({
  user_job_id: 7, status: "new", is_saved: false, match_score: 82, match_category: "good", matching_skills: [], missing_skills: [],
  eligibility_status: "ELIGIBLE", scoring_method: "rule_based", discovered_at: new Date().toISOString(), saved_at: null, dismissed_at: null,
  application_id: null, application_status: null, ...item,
  job: {
    id: 3, platform: "Himalayas", external_job_id: "x", company: "Acme", title: "AR Analyst", location: "Remote - USA", work_mode: "Remote",
    employment_type: "Full-time", experience_required: null, salary_range: "$80K – $110K • Offers Equity", job_url: "https://himalayas.app/jobs/x",
    posted_at: "2026-11-15", posted_at_source: "platform_api", posted_label: "Yesterday", description_preview: "Collections.",
    has_full_description: true, source: "himalayas", posted_at_confidence: "verified", first_seen_at: null, last_verified_at: null,
    closed_at: null, industry: null, department: null, sources: [], location_normalized: "Remote (United States)", remote_scope: ["US"],
    remote_scope_label: "United States", salary_label: "USD 80k–110k a year (assumed)",
    freshness: { state: "open", label: "Open", detail: "Confirmed 2 hours ago: listed on the Himalayas feed.", checked_at: null }, ...over,
  },
});
const noop = { onView: vi.fn(), onSave: vi.fn(), onApply: vi.fn(), onDismiss: vi.fn() };

describe("discovery quality on the job card", () => {
  it("shows the normalised location, salary and an honest freshness badge, keeping the posted text on hover", () => {
    render(<JobCard item={job()} actions={noop} />);
    expect(screen.getByText("Remote (United States)")).toBeInTheDocument();
    expect(screen.getByText("Remote (United States)").closest("span")).toHaveAttribute("title", "As posted: Remote - USA");
    expect(screen.getByText("USD 80k–110k a year (assumed)")).toBeInTheDocument();
    const badge = screen.getByTestId("freshness-badge");
    expect(badge).toHaveAttribute("data-state", "open");
    expect(badge).toHaveAttribute("title", expect.stringContaining("Himalayas feed"));
  });

  it("closed and unchecked jobs say so, and older responses without freshness still show closed", () => {
    const { rerender } = render(<JobCard item={job({ freshness: { state: "unchecked", label: "Check on the site", detail: "This site does not allow automated checks", checked_at: null } })} actions={noop} />);
    expect(screen.getByTestId("freshness-badge")).toHaveTextContent("Check on the site");
    rerender(<JobCard item={job({ freshness: undefined, closed_at: "2026-11-10T00:00:00Z" })} actions={noop} />);
    expect(screen.getByTestId("freshness-badge")).toHaveAttribute("data-state", "closed");
  });

  it("lists the same role's other listings and opens one", () => {
    const onViewId = vi.fn();
    const item = job({}, { similar: [{ user_job_id: 9, location: "Pune, India", match_score: 70 }, { user_job_id: 10, location: "Mumbai, India", match_score: 60 }] });
    render(<JobCard item={item} actions={{ ...noop, onViewId }} />);
    const box = screen.getByTestId("similar-listings");
    expect(box).toHaveTextContent("Also listed 2 more times");
    fireEvent.click(within(box).getByText("Pune, India"));
    expect(onViewId).toHaveBeenCalledWith(9);
  });
});

describe("match breakdown", () => {
  const b: Breakdown = {
    matched: [{ name: "required_skills", label: "Required skills", detail: "4 of 5 required skills found", score: 80, weight: 30 }],
    partial: [{ name: "experience", label: "Experience", detail: "requires 5+ years, candidate has 4.0", score: 70 - 20, weight: 20 }],
    not_matched: [{ name: "location_work_mode", label: "Location & work mode", detail: "remote, but only for candidates in United States", score: 10, weight: 10 }],
    not_evaluated: [{ name: "salary", label: "Salary", detail: "the salary is in USD and your minimum is in INR; JobPilot does not convert currencies", score: null, weight: 5 }],
    summary: "1 of 3 checks match, 1 partly, 1 don't. 1 couldn't be checked, so they don't count either way.",
    skills: { matched: [], missing: [], missing_optional: [] },
  };

  it("groups every check and explains the ones that couldn't be made", () => {
    render(<MatchBreakdown breakdown={b} />);
    expect(screen.getByText(b.summary)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "What matches" })).getByText("Required skills")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Doesn't match" })).getByText(/only for candidates in United States/)).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Couldn't be checked" })).getByText(/does not convert currencies/)).toBeInTheDocument();
  });
});
