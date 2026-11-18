import { stageLabels, statusLabels } from "@/lib/format";
import type { AppEvent } from "@/types/api";

const LABELS: Record<string, string> = {
  PREPARED: "Application prepared",
  REPREPARED: "Prepared again",
  OPENED_EXTERNAL: "Application form opened",
  REOPENED_LISTING: "Listing opened again",
  SUBMISSION_CONFIRMED: "Confirmed as sent",
  RETURNED_UNDECIDED: "Came back without confirming",
  NOT_SUBMITTED: "Marked as not sent",
  FAILED: "Marked as failed",
  WITHDRAWN: "Withdrawn",
  RESUME_SELECTED: "Resume chosen",
  FOLLOW_UP_SET: "Follow-up reminder changed",
  INTERVIEW_ADDED: "Interview added",
  OFFER_RECORDED: "Offer recorded",
  APPLY_STATE: "Smart Apply progress",
};

/** Smart Apply (browser extension) progress states, as the backend names them (apply_state_service.LABELS). */
export const APPLY_STATE_LABELS: Record<string, string> = {
  draft: "Draft", ready_to_fill: "Ready to fill", filling: "Filling", needs_information: "Needs information",
  ready_for_review: "Ready for review", reviewed: "Reviewed", submission_authorized: "Submission authorised",
  submission_pending: "Submission pending", submitted_confirmed: "Submitted (confirmed)",
  submission_uncertain: "Submission uncertain: please check", failed: "Failed", cancelled: "Cancelled",
};

/** A history line in plain words: "Moved to Interview" rather than "stage changed". */
export function eventLabel(e: AppEvent): string {
  if (e.event_type === "APPLY_STATE" && e.to_status && APPLY_STATE_LABELS[e.to_status]) return `Smart Apply: ${APPLY_STATE_LABELS[e.to_status]}`;
  if (e.event_type === "STAGE_CHANGED") return `Moved to ${stageLabels[e.to_status ?? ""] ?? e.to_status ?? "a new stage"}`;
  const known = LABELS[e.event_type];
  if (known) return known;
  if (statusLabels[e.event_type]) return statusLabels[e.event_type];
  const words = e.event_type.replace(/^CLI_/, "").replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Follow-up reminder state for a card: due (today or overdue), upcoming, or none. */
export function followUpState(followUpAt: string | null | undefined, now = new Date()): "due" | "upcoming" | null {
  if (!followUpAt) return null;
  const d = new Date(followUpAt);
  const endOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  return d < endOfToday ? "due" : "upcoming";
}

export function daysSince(iso: string | null | undefined, now = new Date()): number | null {
  if (!iso) return null;
  return Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 86_400_000));
}

/** The detail line under a history entry, without internal codes. */
export function eventDetail(e: AppEvent): string | null {
  const d = e.details?.trim();
  if (!d) return null;
  // The extension's default detail repeats the state label already shown in the line itself.
  if (e.event_type === "APPLY_STATE" && e.to_status && APPLY_STATE_LABELS[e.to_status] === d) return null;
  if (e.event_type === "FOLLOW_UP_SET") {
    if (d === "cleared") return "Reminder removed";
    const when = new Date(d);
    return Number.isNaN(when.getTime()) ? d : `Remind me on ${when.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}`;
  }
  const src = /^source=(\w+)(?:; reference=(.+))?$/.exec(d);
  if (src) {
    const known: Record<string, string> = { user_confirmed: "You confirmed it in JobPilot", extension: "Confirmed by Smart Apply", email: "Found in a confirmation email" };
    const how = known[src[1]] ?? `Source: ${src[1].replaceAll("_", " ")}`;
    return src[2] ? `${how} · reference ${src[2]}` : how;
  }
  return d;
}
