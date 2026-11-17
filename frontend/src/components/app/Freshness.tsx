import { Archive, CircleCheck, CircleHelp, Clock, TimerOff } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Freshness, JobListing } from "@/types/api";

const tone: Record<Freshness["state"], string> = {
  open: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  unconfirmed: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  unchecked: "bg-muted text-muted-foreground",
  expired: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  closed: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};
const icon = { open: CircleCheck, unconfirmed: Clock, unchecked: CircleHelp, expired: TimerOff, closed: Archive };

/** Is the job still open, and how JobPilot knows. Older API responses without `freshness` fall back to closed_at. */
export function freshnessOf(j: JobListing): Freshness | null {
  if (j.freshness) return j.freshness;
  if (j.closed_at) return { state: "closed", label: "No longer listed", detail: "The employer's job board no longer lists this job.", checked_at: j.closed_at };
  return null;
}

export function FreshnessBadge({ job, className }: { job: JobListing; className?: string }) {
  const f = freshnessOf(job);
  if (!f) return null;
  const Icon = icon[f.state];
  return (
    <span data-testid="freshness-badge" data-state={f.state} title={f.detail}
          className={cn("inline-flex cursor-help items-center gap-1 rounded px-1.5 py-0.5 text-xs", tone[f.state], className)}>
      <Icon className="size-3" aria-hidden /> {f.label}
    </span>
  );
}
