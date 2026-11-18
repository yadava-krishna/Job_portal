import { Check, CircleHelp, Minus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { BreakdownItem, MatchBreakdown as Breakdown } from "@/features/growth/types";

const groups = [
  { key: "matched", title: "What matches", Icon: Check, tone: "text-route" },
  { key: "partial", title: "Partly matches", Icon: Minus, tone: "text-caution" },
  { key: "not_matched", title: "Doesn't match", Icon: X, tone: "text-destructive" },
  { key: "not_evaluated", title: "Couldn't be checked", Icon: CircleHelp, tone: "text-muted-foreground" },
] as const;

function Row({ item }: { item: BreakdownItem }) {
  return (
    <li className="text-sm">
      <span className="font-medium">{item.label}</span>
      {item.score != null && <span className="ml-1 tabular-nums text-xs text-muted-foreground">{Math.round(item.score)}/100</span>}
      <span className="block text-xs text-muted-foreground first-letter:uppercase">{item.detail}</span>
    </li>
  );
}

/** Plain-language explanation of a match: every line is a scored dimension's own evidence. */
export function MatchBreakdown({ breakdown }: { breakdown: Breakdown }) {
  return (
    <div data-testid="match-breakdown" className="space-y-3 rounded-lg border p-3">
      <p className="text-sm font-medium">{breakdown.summary}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        {groups.map(({ key, title, Icon, tone }) => {
          const items = breakdown[key];
          if (!items.length) return null;
          return (
            <section key={key} aria-label={title}>
              <h4 className={cn("mb-1 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide", tone)}>
                <Icon className="size-3.5" aria-hidden /> {title}
              </h4>
              <ul className="space-y-1.5">{items.map((i) => <Row key={i.name} item={i} />)}</ul>
            </section>
          );
        })}
      </div>
      {breakdown.not_evaluated.length > 0 && (
        <p className="text-xs text-muted-foreground">Checks that couldn't be made are left out of the score, so missing information neither helps nor hurts.</p>
      )}
    </div>
  );
}
