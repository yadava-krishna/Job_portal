import { useState } from "react";
import { ArrowRight, BookOpen, Loader2, RefreshCw, Target } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Panel } from "@/features/growth/ui";
import { useGaps, useRefreshGaps, useSendFeedback } from "./hooks";
import { stateLabel } from "./format";
import { GapStatusBadge, SeverityBadge } from "./labels";
import type { Gap } from "./types";

/** "Your level: Aware · asked for in 9 of your matches · linked to 1 rejection" */
function GapFacts({ gap, className }: { gap: Gap; className?: string }) {
  return (
    <span className={cn("text-xs text-muted-foreground", className)}>
      Your level: <span className="text-foreground/80">{stateLabel(gap.evidence_state)}</span>
      {gap.job_count > 0 && <> · asked for in <span className="readout text-foreground/80">{gap.job_count}</span> of your matches</>}
      {gap.rejection_count > 0 && <> · linked to <span className="readout text-foreground/80">{gap.rejection_count}</span> rejection(s)</>}
    </span>
  );
}

const GAPS_SHOWN = 10;

export function GapsTab({ onLearn }: { onLearn: (gapId: number) => void }) {
  const [showAllGaps, setShowAllGaps] = useState(false);
  const gaps = useGaps();
  const refresh = useRefreshGaps();
  const d = gaps.data;

  const refreshButton = (
    <Button variant="outline" size="sm" disabled={refresh.isPending}
            onClick={() => refresh.mutate(undefined, { onSuccess: () => toast.success("Gaps refreshed from your latest matches ✨"), onError: (e) => toast.error(errorMessage(e)) })}>
      {refresh.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} Refresh gaps
    </Button>
  );

  if (gaps.isLoading) return <div className="space-y-3"><Skeleton className="h-40 rounded-2xl" /><Skeleton className="h-64 rounded-2xl" /></div>;
  if (gaps.isError) return <EmptyState title="Couldn't load your skill gaps">{errorMessage(gaps.error)}</EmptyState>;
  if (!d || !d.gaps.length) {
    return (
      <EmptyState icon={<Target className="size-8" />} title="No skill gaps on the radar yet">
        Gaps are worked out from the jobs you match. Once you have a few matches, refresh to see which skills would help most.
        <div className="mt-4 flex justify-center">{refreshButton}</div>
      </EmptyState>
    );
  }

  const best = d.best;
  const alternatives = d.alternatives.slice(0, 3);
  const shown = showAllGaps ? d.gaps : d.gaps.slice(0, GAPS_SHOWN);

  return (
    <div className="space-y-4">
      {best && (
        <section aria-label="Best gap to work on next"
                 className="overflow-hidden rounded-2xl bg-card ring-1 ring-route/25 shadow-[var(--shadow-raised)]">
          <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,26rem)] lg:items-center">
            <div className="min-w-0 space-y-2">
              <div className="eyebrow text-route">Best gap to work on next</div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-display text-[24px] leading-tight font-extrabold tracking-[-0.025em]">{best.skill}</h2>
                <SeverityBadge severity={best.severity} />
                <GapStatusBadge status={best.status} />
              </div>
              <p className="text-[13.5px] text-foreground/85">{best.explanation}</p>
              <GapFacts gap={best} />
            </div>
            <div className="rounded-xl bg-paper-sunk p-3.5">
              <div className="text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">Next action</div>
              <p className="mt-1 text-[13.5px] font-medium text-foreground">{best.next_action}</p>
              <Button className="mt-3 w-full sm:w-auto" onClick={() => onLearn(best.id)}><BookOpen /> Find ways to learn this</Button>
            </div>
          </div>
          {alternatives.length > 0 && (
            <div className="border-t border-border/70 bg-paper-sunk/40 px-4 py-3 sm:px-5">
              <h3 className="mb-2 text-xs font-medium text-muted-foreground">Or pick one of these instead</h3>
              <ul className="grid gap-2 md:grid-cols-[repeat(auto-fill,minmax(17rem,1fr))]">
                {alternatives.map((g) => (
                  <li key={g.id} className="flex min-w-0 items-center gap-2 rounded-xl bg-card px-3 py-2 ring-1 ring-border/70">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5"><span className="text-[13.5px] font-semibold text-heading">{g.skill}</span><SeverityBadge severity={g.severity} /></div>
                      <p className="truncate text-xs text-muted-foreground" title={g.next_action}>{g.next_action}</p>
                    </div>
                    <Button variant="ghost" size="sm" className="shrink-0 text-route" onClick={() => onLearn(g.id)}>Learn this <ArrowRight /></Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <Panel title="All gaps" count={d.gaps.length} icon={<Target />} actions={refreshButton}
             description="Skills that keep coming up in jobs you match, highest impact first, and how strong your evidence for them is."
             bodyClassName="px-0 pb-1 sm:px-0">
        <ol className="divide-y divide-border/70">
          {shown.map((g, i) => (
            <li key={g.id} className={cn("grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-2 px-4 py-3 sm:grid-cols-[1.75rem_minmax(0,1fr)_auto] sm:px-5", g.status === "closed" && "opacity-70")}>
              <span className="readout pt-0.5 text-[13px] text-muted-foreground" aria-hidden>{String(i + 1).padStart(2, "0")}</span>
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="mr-0.5 font-semibold text-heading">{g.skill}</span>
                  <SeverityBadge severity={g.severity} />
                  <GapStatusBadge status={g.status} />
                </div>
                <GapFacts gap={g} className="block" />
                <p className="text-xs text-muted-foreground">{g.explanation} <span className="text-foreground/85">Next: {g.next_action}</span></p>
              </div>
              {g.status !== "closed" && (
                <Button variant="outline" size="sm" className="col-start-2 mt-2 w-fit sm:col-start-3 sm:mt-0 sm:self-center" onClick={() => onLearn(g.id)}>Learn</Button>
              )}
            </li>
          ))}
        </ol>
        {d.gaps.length > GAPS_SHOWN && (
          <div className="border-t border-border/70 px-3 py-1.5 sm:px-4">
            <Button variant="ghost" size="sm" onClick={() => setShowAllGaps(!showAllGaps)}>
              {showAllGaps ? "Show the top gaps only" : `Show all ${d.gaps.length} gaps`}
            </Button>
          </div>
        )}
      </Panel>

      <FeedbackPrompt topic="gap_usefulness" question="Is this list of gaps helpful?" />
    </div>
  );
}

/** Small optional "Is this helpful?" prompt (1-5 and a comment). */
export function FeedbackPrompt({ topic, question }: { topic: string; question: string }) {
  const send = useSendFeedback();
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [done, setDone] = useState(false);
  if (done) return <p className="px-1 text-xs text-muted-foreground">Thanks, your answer helps us improve these suggestions.</p>;
  return (
    <div className="space-y-3 rounded-2xl bg-paper-sunk/70 px-4 py-3 ring-1 ring-border/60">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-[13px] font-medium">{question}</span>
        <div className="flex gap-1" role="group" aria-label="Rating from 1 (not helpful) to 5 (very helpful)">
          {[1, 2, 3, 4, 5].map((n) => (
            <Button key={n} type="button" size="icon-sm" variant={rating === n ? "default" : "outline"} aria-pressed={rating === n}
                    aria-label={`${n} out of 5`} className="readout" onClick={() => setRating(n)}>{n}</Button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">1 = not helpful, 5 = very helpful</span>
      </div>
      {rating != null && (
        <div className="flex flex-col gap-2 animate-in fade-in-0 slide-in-from-top-1 duration-200 sm:flex-row sm:items-end">
          <Textarea aria-label="Comment (optional)" placeholder="Anything we should know? (optional)" value={comment} maxLength={2000} rows={2}
                    className="bg-card" onChange={(e) => setComment(e.target.value)} />
          <Button size="sm" disabled={send.isPending}
                  onClick={() => send.mutate({ topic, rating, comment: comment.trim() || null }, { onSuccess: () => setDone(true), onError: (e) => toast.error(errorMessage(e)) })}>
            Send
          </Button>
        </div>
      )}
    </div>
  );
}
