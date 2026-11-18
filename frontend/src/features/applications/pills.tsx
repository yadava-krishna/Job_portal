import { stageLabels, statusLabels } from "@/lib/format";
import { cn } from "@/lib/utils";
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

/** Smart Apply progress, precise: the extension's state label, coloured by whether it needs you. */
export function ApplyStatePill({ state, label, className }: { state: string | null | undefined; label: string | null | undefined; className?: string }) {
  if (!label) return null;
  const tone = state === "submitted_confirmed" ? "bg-success-tint text-success ring-success/20"
    : state === "submission_uncertain" || state === "needs_information" ? "bg-caution-tint text-caution ring-caution/25"
      : state === "failed" ? "bg-destructive/10 text-destructive ring-destructive/20"
        : "bg-route-tint text-route ring-route/20";
  return <span className={cn(pill, tone, className)} title="Smart Apply progress from the browser extension">Smart Apply · {label}</span>;
}
