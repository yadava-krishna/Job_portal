import { cn } from "@/lib/utils";
import { scoreTone } from "@/lib/format";
import type { Eligibility, ScoreDimension } from "./types";

const barTone = { excellent: "bg-route", good: "bg-violet", moderate: "bg-caution", low: "bg-destructive/70", none: "bg-muted" };

const eligibilityTone: Record<Eligibility, string> = {
  pass: "border-success/30 bg-success-tint text-success",
  fail: "border-destructive/30 bg-destructive/10 text-destructive",
  unknown: "border-caution/30 bg-caution-tint text-caution",
};
const eligibilityHint: Record<Eligibility, string> = {
  pass: "Nothing in the listing rules you out.",
  fail: "The listing has a hard requirement you don't meet. The match score below doesn't change that.",
  unknown: "The listing doesn't say enough to tell. Check the requirements yourself.",
};

/** The 8 versioned score dimensions. Unknown dimensions show "unknown" instead of a number and carry no weight. */
export function ScoreDimensions({ dimensions }: { dimensions: ScoreDimension[] }) {
  return (
    <ul className="space-y-3" aria-label="Score breakdown">
      {dimensions.map((d) => {
        const unknown = d.status === "unknown" || d.score == null;
        return (
          <li key={d.name} data-testid={`dimension-${d.name}`}>
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span className="font-medium">
                {d.label}{" "}
                <span className="text-xs font-normal text-muted-foreground" title={`Default weight ${d.base_weight.toFixed(0)}%`}>
                  ({d.weight.toFixed(0)}% of score{d.weight !== d.base_weight ? `, normally ${d.base_weight.toFixed(0)}%` : ""})
                </span>
              </span>
              {unknown ? <span className="text-xs font-medium text-muted-foreground italic">unknown</span> : <span className="tabular-nums">{d.score!.toFixed(0)}</span>}
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
              {!unknown && <div className={cn("h-full rounded-full", barTone[scoreTone(d.score)])} style={{ width: `${d.score}%` }} />}
            </div>
            {d.evidence && <p className="mt-1 text-xs text-muted-foreground">{d.evidence}</p>}
          </li>
        );
      })}
    </ul>
  );
}

export function EligibilityBox({ eligibility, reasons }: { eligibility: Eligibility; reasons: string[] }) {
  return (
    <div className={cn("rounded-lg border p-3 text-sm", eligibilityTone[eligibility])} data-testid="eligibility">
      <strong>Eligibility: {eligibility}</strong>
      <span className="ml-1">· {eligibilityHint[eligibility]}</span>
      {reasons.length > 0 && <ul className="mt-1 list-disc pl-4">{reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
    </div>
  );
}
