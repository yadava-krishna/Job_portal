import { cn } from "@/lib/utils";
import type { Application, Stage } from "@/types/api";

export type StripKey = "applied" | "screening" | "assessment" | "interview" | "offer" | "closed";

export const STRIP: { key: StripKey; label: string; hint: string }[] = [
  { key: "applied", label: "Applied", hint: "Submitted, no reply yet" },
  { key: "screening", label: "Screening", hint: "A recruiter is looking" },
  { key: "assessment", label: "Assessment", hint: "Test or take-home" },
  { key: "interview", label: "Interview", hint: "Interviews in progress" },
  { key: "offer", label: "Offer", hint: "Offer received" },
  { key: "closed", label: "Closed", hint: "Rejected, withdrawn or archived" },
];

const CLOSED: (Stage | null)[] = ["rejected", "withdrawn", "archived"];

/** Which strip bucket an application belongs to, or null while it isn't submitted yet. */
export function stripKeyOf(a: Application): StripKey | null {
  if (a.status === "WITHDRAWN" || CLOSED.includes(a.stage)) return "closed";
  if (a.status !== "SUBMITTED") return null;
  return (a.stage ?? "applied") as StripKey;
}

/**
 * The pipeline at a glance: one count per stage, in order, joined by the route line. Each stage is also a filter
 * for the list and board below (press again to clear).
 */
export function StageStrip({ apps, value, onChange }: { apps: Application[]; value: StripKey | null; onChange: (k: StripKey | null) => void }) {
  const counts = Object.fromEntries(STRIP.map((s) => [s.key, 0])) as Record<StripKey, number>;
  for (const a of apps) { const k = stripKeyOf(a); if (k) counts[k] += 1; }

  return (
    <div>
      <div role="group" aria-label="Filter by stage" data-testid="stage-strip"
           className="grid grid-cols-3 overflow-hidden rounded-2xl bg-card ring-1 ring-border sm:grid-cols-[repeat(5,minmax(0,1fr))_minmax(0,0.9fr)]">
        {STRIP.map((s, i) => {
          const active = value === s.key;
          const closed = s.key === "closed";
          const n = counts[s.key];
          return (
            <button key={s.key} type="button" aria-pressed={active} title={s.hint}
                    onClick={() => onChange(active ? null : s.key)}
                    className={cn("group/stage relative flex min-w-0 flex-col items-start gap-1 px-3.5 pt-2.5 pb-3 text-left outline-none transition-colors duration-200 ease-[cubic-bezier(.2,0,0,1)] sm:px-4",
                      "hover:bg-paper-sunk focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
                      "max-sm:border-l max-sm:[&:nth-child(3n+1)]:border-l-0 max-sm:[&:nth-child(-n+3)]:border-b sm:border-l sm:first:border-l-0",
                      closed && "sm:bg-paper-sunk/60",
                      active && "bg-route-tint hover:bg-route-tint")}>
              <span className="flex w-full items-center gap-1.5">
                <span aria-hidden className={cn("size-2 shrink-0 rounded-full transition-[transform,background-color] duration-200",
                  closed ? "bg-muted-foreground/50" : n > 0 ? "bg-route" : "bg-border", active && "scale-125")} />
                <span className={cn("truncate text-[12.5px] font-medium", active ? "text-route" : "text-muted-foreground group-hover/stage:text-foreground")}>{s.label}</span>
                {!closed && i < STRIP.length - 2 && <span aria-hidden className="ml-1 hidden h-px flex-1 bg-gradient-to-r from-route/35 to-border sm:block" />}
              </span>
              <span className={cn("readout text-[26px] leading-none font-semibold sm:text-[30px]",
                active ? "text-route" : n === 0 ? "text-muted-foreground/60" : s.key === "offer" ? "text-success" : "text-heading")}>{n}</span>
              <span aria-hidden className={cn("absolute inset-x-3 bottom-0 h-[3px] origin-left rounded-t-full bg-route transition-transform duration-[240ms] ease-[cubic-bezier(.2,0,0,1)]",
                active ? "scale-x-100" : "scale-x-0")} />
              <span className="sr-only">{n === 1 ? "application" : "applications"}{active ? ", filter on" : ""}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
