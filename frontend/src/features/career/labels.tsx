import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { SKILL_STATES, stateLabel } from "./format";
import type { Eligibility, SkillState } from "./types";

const pill = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";
const green = "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:ring-emerald-900";
const red = "bg-rose-50 text-rose-800 ring-rose-200 dark:bg-rose-950/40 dark:text-rose-200 dark:ring-rose-900";
const amber = "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900";
const sky = "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-950/40 dark:text-sky-200 dark:ring-sky-900";
const muted = "bg-muted text-muted-foreground ring-border";

/** pass / fail / unknown. Anything that is not an explicit pass or fail is shown as "unknown", never as a pass. */
export function EligibilityBadge({ value }: { value: Eligibility | string | undefined }) {
  if (value === "pass") return <span className={cn(pill, green)} title="You meet the job's hard requirements">Eligible</span>;
  if (value === "fail") return <span className={cn(pill, red)} title="A hard requirement isn't met">Not eligible</span>;
  return <span className={cn(pill, muted)} title="We couldn't confirm eligibility from the posting">unknown</span>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  const map: Record<string, [string, string]> = { high: ["High impact", red], medium: ["Medium impact", amber], low: ["Low impact", muted] };
  const [label, cls] = map[severity] ?? [severity, muted];
  return <span className={cn(pill, cls)}>{label}</span>;
}

export function GapStatusBadge({ status }: { status: string }) {
  const map: Record<string, [string, string]> = {
    open: ["Not started", muted], in_progress: ["In progress", sky], closed: ["Closed", green], ignored: ["Set aside", muted],
  };
  const [label, cls] = map[status] ?? [status, muted];
  return <span className={cn(pill, cls)}>{label}</span>;
}

export function ConfidenceBadge({ confidence }: { confidence: string }) {
  if (confidence === "verified") return <span className={cn(pill, green)}>Checked by a person</span>;
  if (confidence === "stale") return <span className={cn(pill, amber)}>Needs review</span>;
  return <span className={cn(pill, muted)}>Not yet checked by a person</span>;
}

export function FreeBadge() {
  return <span className={cn(pill, green)}>Free</span>;
}

/** The six-step skill progression with the current step highlighted. */
export function StateStepper({ state, supports }: { state: SkillState; supports?: SkillState }) {
  const current = SKILL_STATES.findIndex((s) => s.key === state);
  const ceiling = supports ? SKILL_STATES.findIndex((s) => s.key === supports) : -1;
  return (
    <ol className="flex flex-wrap items-center gap-1" aria-label={`Progress: ${stateLabel(state)}`}>
      {SKILL_STATES.map((s, i) => (
        <li key={s.key} className="flex items-center gap-1">
          <span
            aria-current={i === current ? "step" : undefined}
            title={i <= ceiling ? "Your evidence supports this step" : undefined}
            className={cn(
              "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium",
              i < current && "bg-primary/10 text-primary",
              i === current && "bg-primary text-primary-foreground",
              i > current && "bg-muted text-muted-foreground",
            )}
          >
            {i < current && <Check className="size-3" />}
            {s.label}
          </span>
          {i < SKILL_STATES.length - 1 && <span className="h-px w-2 bg-border" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}
