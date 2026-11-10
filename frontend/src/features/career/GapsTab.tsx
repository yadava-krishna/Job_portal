import { useState } from "react";
import { BookOpen, Loader2, RefreshCw, Target } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useGaps, useRefreshGaps, useSendFeedback } from "./hooks";
import { stateLabel } from "./format";
import { GapStatusBadge, SeverityBadge } from "./labels";
import type { Gap } from "./types";

function GapMeta({ gap }: { gap: Gap }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <SeverityBadge severity={gap.severity} />
      <GapStatusBadge status={gap.status} />
      <span>Your level: {stateLabel(gap.evidence_state)}</span>
      {gap.job_count > 0 && <span>· asked for in {gap.job_count} of your matches</span>}
      {gap.rejection_count > 0 && <span>· linked to {gap.rejection_count} rejection(s)</span>}
    </div>
  );
}

export function GapsTab({ onLearn }: { onLearn: (gapId: number) => void }) {
  const gaps = useGaps();
  const refresh = useRefreshGaps();
  const d = gaps.data;

  const refreshButton = (
    <Button variant="outline" size="sm" disabled={refresh.isPending}
            onClick={() => refresh.mutate(undefined, { onSuccess: () => toast.success("Gaps updated from your latest matches"), onError: (e) => toast.error(errorMessage(e)) })}>
      {refresh.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} Refresh gaps
    </Button>
  );

  if (gaps.isLoading) return <div className="space-y-3"><Skeleton className="h-36" /><Skeleton className="h-24" /></div>;
  if (gaps.isError) return <EmptyState title="Couldn't load your skill gaps">{errorMessage(gaps.error)}</EmptyState>;
  if (!d || !d.gaps.length) {
    return (
      <EmptyState icon={<Target className="size-8" />} title="No skill gaps yet">
        Gaps are worked out from the jobs you match. Once you have a few matches, refresh to see which skills would help most.
        <div className="mt-4 flex justify-center">{refreshButton}</div>
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">Skills that keep coming up in jobs you match, and how strong your evidence for them is.</p>
        {refreshButton}
      </div>

      {d.best && (
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader>
            <CardDescription className="text-xs font-medium uppercase tracking-wide text-primary">Best gap to work on next</CardDescription>
            <CardTitle className="text-lg">{d.best.skill}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <GapMeta gap={d.best} />
            <p className="text-sm">{d.best.explanation}</p>
            <div className="rounded-lg border bg-background p-3 text-sm"><span className="font-medium">Next action: </span>{d.best.next_action}</div>
            <Button onClick={() => onLearn(d.best!.id)}><BookOpen /> Find ways to learn this</Button>
          </CardContent>
        </Card>
      )}

      {d.alternatives.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Or pick one of these instead</h3>
          <div className="grid gap-3 md:grid-cols-3">
            {d.alternatives.slice(0, 3).map((g) => (
              <Card key={g.id} className="gap-2 p-4">
                <div className="font-medium">{g.skill}</div>
                <GapMeta gap={g} />
                <p className="text-xs text-muted-foreground">{g.next_action}</p>
                <Button variant="outline" size="sm" className="mt-1 w-fit" onClick={() => onLearn(g.id)}>Learn this</Button>
              </Card>
            ))}
          </div>
        </section>
      )}

      <section className="space-y-2">
        <h3 className="text-sm font-medium">All gaps ({d.gaps.length})</h3>
        <ul className="divide-y rounded-xl border">
          {d.gaps.map((g) => (
            <li key={g.id} className={cn("space-y-1.5 p-4", g.status === "closed" && "opacity-70")}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{g.skill}</span>
                {g.status !== "closed" && <Button variant="ghost" size="sm" onClick={() => onLearn(g.id)}>Learn</Button>}
              </div>
              <GapMeta gap={g} />
              <p className="text-sm text-muted-foreground">{g.explanation}</p>
              <p className="text-sm"><span className="font-medium">Next action: </span>{g.next_action}</p>
            </li>
          ))}
        </ul>
      </section>

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
  if (done) return <p className="text-xs text-muted-foreground">Thanks, your answer helps us improve these suggestions.</p>;
  return (
    <Card className="gap-3 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">{question}</span>
        <div className="flex gap-1" role="group" aria-label="Rating from 1 (not helpful) to 5 (very helpful)">
          {[1, 2, 3, 4, 5].map((n) => (
            <Button key={n} type="button" size="icon-sm" variant={rating === n ? "default" : "outline"} aria-pressed={rating === n}
                    aria-label={`${n} out of 5`} onClick={() => setRating(n)}>{n}</Button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">1 = not helpful, 5 = very helpful</span>
      </div>
      {rating != null && (
        <div className="space-y-2">
          <Textarea aria-label="Comment (optional)" placeholder="Anything we should know? (optional)" value={comment} maxLength={2000} onChange={(e) => setComment(e.target.value)} />
          <Button size="sm" disabled={send.isPending}
                  onClick={() => send.mutate({ topic, rating, comment: comment.trim() || null }, { onSuccess: () => setDone(true), onError: (e) => toast.error(errorMessage(e)) })}>
            Send
          </Button>
        </div>
      )}
    </Card>
  );
}
