import { Check, CheckCircle2, ChevronDown, ChevronsUp, ChevronUp, Circle, CircleDashed, CircleDot, CircleHelp, CircleMinus, Clock, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Chip } from "@/features/growth/ui";
import { SKILL_STATES, stateLabel } from "./format";
import type { Eligibility, SkillState } from "./types";

/** pass / fail / unknown. Anything that is not an explicit pass or fail is shown as "unknown", never as a pass. */
export function EligibilityBadge({ value }: { value: Eligibility | string | undefined }) {
  if (value === "pass") return <Chip tone="success" icon={<CheckCircle2 />} title="You meet the job's hard requirements">Eligible</Chip>;
  if (value === "fail") return <Chip tone="danger" icon={<XCircle />} title="A hard requirement isn't met">Not eligible</Chip>;
  return <Chip tone="muted" icon={<CircleHelp />} title="We couldn't confirm eligibility from the posting">unknown</Chip>;
}

/** How much closing a gap would help. The arrow icon carries the level, so it reads without colour. */
export function SeverityBadge({ severity }: { severity: string }) {
  if (severity === "high") return <Chip tone="coral" icon={<ChevronsUp />}>High impact</Chip>;
  if (severity === "medium") return <Chip tone="caution" icon={<ChevronUp />}>Medium impact</Chip>;
  if (severity === "low") return <Chip tone="muted" icon={<ChevronDown />}>Low impact</Chip>;
  return <Chip tone="muted">{severity}</Chip>;
}

export function GapStatusBadge({ status }: { status: string }) {
  if (status === "open") return <Chip tone="muted" icon={<Circle />}>Not started</Chip>;
  if (status === "in_progress") return <Chip tone="route" icon={<CircleDot />}>In progress</Chip>;
  if (status === "closed") return <Chip tone="success" icon={<CheckCircle2 />}>Closed</Chip>;
  if (status === "ignored") return <Chip tone="muted" icon={<CircleMinus />}>Set aside</Chip>;
  return <Chip tone="muted">{status}</Chip>;
}

export function ConfidenceBadge({ confidence }: { confidence: string }) {
  if (confidence === "verified") return <Chip tone="success" icon={<CheckCircle2 />}>Checked by a person</Chip>;
  if (confidence === "stale") return <Chip tone="caution" icon={<Clock />}>Needs review</Chip>;
  return <Chip tone="muted" icon={<CircleDashed />}>Not yet checked by a person</Chip>;
}

export function FreeBadge() {
  return <Chip tone="route">Free</Chip>;
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
              "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors duration-200",
              i < current && "bg-route-tint text-route",
              i === current && "bg-route text-primary-foreground",
              i > current && (i <= ceiling ? "bg-lavender text-violet" : "bg-muted text-muted-foreground"),
            )}
          >
            {i < current && <Check className="size-3" aria-hidden />}
            {s.label}
          </span>
          {i < SKILL_STATES.length - 1 && <span className={cn("h-px w-2", i < current ? "bg-route/40" : "bg-border")} aria-hidden />}
        </li>
      ))}
    </ol>
  );
}
