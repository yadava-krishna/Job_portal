import { stageLabels, statusLabels } from "@/lib/format";
import { cn } from "@/lib/utils";
import { APPLY_STATE_LABELS } from "./events";
import type { Application, Stage } from "@/types/api";

/** Token colours per pipeline stage. Green is kept for the one confirmed good outcome (offer). */
const stageTone: Record<string, string> = {
  applied: "bg-paper-sunk text-heading ring-border",
  screening: "bg-lavender text-violet ring-violet/20",
  assessment: "bg-lavender text-violet ring-violet/20",
  interview: "bg-route-tint text-route ring-route/25",
  offer: "bg-success-tint text-success ring-success/25",
  rejected: "bg-destructive/10 text-destructive ring-destructive/20",
  withdrawn: "bg-muted text-muted-foreground ring-border",
  archived: "bg-muted text-muted-foreground ring-border",
};

const statusTone: Record<string, string> = {
  PREPARED: "bg-paper-sunk text-heading ring-border",
  OPENED: "bg-caution-tint text-caution ring-caution/20",
  CONFIRMATION_PENDING: "bg-caution-tint text-caution ring-caution/25",
  SUBMITTED: "bg-success-tint text-success ring-success/20",
  FAILED: "bg-destructive/10 text-destructive ring-destructive/20",
  WITHDRAWN: "bg-muted text-muted-foreground ring-border",
};

const pill = "inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

export function StagePill({ stage, className }: { stage: Stage | string | null | undefined; className?: string }) {
  if (!stage) return null;
  return <span className={cn(pill, stageTone[stage] ?? stageTone.archived, className)}>{stageLabels[stage] ?? stage}</span>;
}

export function StatusPill({ status, className }: { status: string; className?: string }) {
  return <span className={cn(pill, statusTone[status] ?? "bg-muted text-muted-foreground ring-border", className)}>{statusLabels[status] ?? status}</span>;
}

/** Stage for a submitted application, status otherwise: whichever says more about where it stands. */
export function WherePill({ app }: { app: Application }) {
  if (app.status === "SUBMITTED") return <StagePill stage={app.stage ?? "applied"} />;
  return <StatusPill status={app.status} />;
}

/** States that are not Smart Apply's own observations: the user opened the page, or told us the outcome. */
const USER_SIDE_STATES = new Set(["form_opened", "user_reported"]);

/** Apply progress, precise: the backend's state label (or ours for a known state), coloured by whether it needs you. */
export function ApplyStatePill({ state, label, className }: { state: string | null | undefined; label: string | null | undefined; className?: string }) {
  const text = label || (state ? APPLY_STATE_LABELS[state] : null);
  if (!text) return null;
  const tone = state === "submitted_confirmed" ? "bg-success-tint text-success ring-success/20"
    : state === "submission_uncertain" || state === "needs_information" || state === "interrupted" ? "bg-caution-tint text-caution ring-caution/25"
      : state === "failed" ? "bg-destructive/10 text-destructive ring-destructive/20"
        : state === "user_reported" ? "bg-paper-sunk text-heading ring-border"
          : "bg-route-tint text-route ring-route/20";
  const userSide = !!state && USER_SIDE_STATES.has(state);
  return (
    <span className={cn(pill, tone, className)} title={userSide ? "Where this application stands" : "Smart Apply progress from the browser extension"}>
      {userSide ? text : <>Smart Apply · {text}</>}
    </span>
  );
}

/** How we know a submitted application reached the employer. Only employer/receipt evidence gets the confirmed tone. */
export function EvidencePill({ app, className }: { app: Pick<Application, "confirmation_type" | "confirmation_type_label">; className?: string }) {
  const t = app.confirmation_type;
  if (!t) return null;
  const text = app.confirmation_type_label || (t === "employer_confirmed" ? "Confirmed by the employer's page" : t === "receipt_confirmed" ? "Receipt e-mail found" : "You told JobPilot (not verified)");
  const tone = t === "user_reported" ? "bg-paper-sunk text-muted-foreground ring-border" : "bg-success-tint text-success ring-success/20";
  return (
    <span data-testid="evidence-pill" className={cn(pill, tone, className)}
          title={t === "user_reported" ? "You marked this as applied. JobPilot has not seen a confirmation from the employer." : "JobPilot saw independent evidence that the employer received it."}>
      {text}
    </span>
  );
}
