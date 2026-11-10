import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, CheckCircle2, ExternalLink, Eye, Loader2, Pause, Play, ShieldCheck, Square, Timer } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, Field, NativeSelect } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  backendMessage, ck, consentRequired, useCompleteSession, useGapDetail, useGaps, useLearningSessions, useSessionAction, useSetConsent,
  useStartSession,
} from "./hooks";
import { clock, isHttpsLink, minutes, stateLabel } from "./format";
import { FreeBadge } from "./labels";
import type { CompleteResult, ConsentRequired, LearningResource, LearningSession } from "./types";

const HEARTBEAT_MS = 30_000;
const ACTIVE_WINDOW_MS = 2 * 60_000;
const TRACKING_NOTE = "Tracking only while this session is open";

type StartBody = { resource_id?: number | null; gap_id?: number | null; skill?: string | null };

export function LearningTab({ gapId, onSelectGap }: { gapId: number | null; onSelectGap: (id: number) => void }) {
  const gaps = useGaps();
  const sessions = useLearningSessions();
  const start = useStartSession();
  const setConsent = useSetConsent();
  const [consent, setConsentPrompt] = useState<(ConsentRequired & { body: StartBody }) | null>(null);
  const [result, setResult] = useState<CompleteResult | null>(null);

  const openGaps = (gaps.data?.gaps ?? []).filter((g) => g.status !== "closed");
  const selected = gapId ?? gaps.data?.best?.id ?? openGaps[0]?.id ?? null;
  const detail = useGapDetail(selected);
  const current = sessions.data?.sessions.find((s) => s.status === "active" || s.status === "paused") ?? null;

  const startSession = (body: StartBody) => {
    setResult(null);
    start.mutate(body, {
      onSuccess: () => { setConsentPrompt(null); toast.success("Learning session started"); },
      onError: (err) => {
        const c = consentRequired(err);
        if (c) setConsentPrompt({ ...c, body });
        else toast.error(backendMessage(err));
      },
    });
  };

  const allowAndRetry = () => {
    if (!consent) return;
    const { body, consent: kind } = consent;
    setConsent.mutate({ kind, granted: true }, {
      onSuccess: () => { setConsentPrompt(null); startSession(body); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };

  return (
    <div className="space-y-6">
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><Eye className="size-3.5" /> {TRACKING_NOTE}. Opening a link alone is never counted as learning.</p>

      {consent && (
        <Card className="border-primary/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><ShieldCheck className="size-4" /> {consent.message}</CardTitle>
            <CardDescription>Learning sessions measure your time only with your permission. You can turn this off any time in Settings → Privacy & consent.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <blockquote className="rounded-lg border-l-4 border-primary/40 bg-muted/40 px-3 py-2 text-sm">{consent.text}</blockquote>
            <div className="flex flex-wrap gap-2">
              <Button onClick={allowAndRetry} disabled={setConsent.isPending || start.isPending}>
                {(setConsent.isPending || start.isPending) && <Loader2 className="animate-spin" />} Turn on learning tracking
              </Button>
              <Button variant="outline" onClick={() => setConsentPrompt(null)}>Not now</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {current && <ActiveSession key={current.id} session={current} onFinished={setResult} />}
      {result && (
        <div role="status" className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
          <div>
            <div className="font-medium">Session finished: {result.session.skill} is now "{result.skill_state_label}".</div>
            <div className="text-xs text-muted-foreground">
              {minutes(Math.floor(result.session.active_seconds / 60))} active, {minutes(Math.floor(result.session.idle_seconds / 60))} idle.
              Your evidence was saved under Skills & evidence.
            </div>
          </div>
        </div>
      )}

      {gaps.isLoading ? <Skeleton className="h-40" /> : openGaps.length === 0 ? (
        <EmptyState icon={<BookOpen className="size-8" />} title="Nothing to learn yet">Learning suggestions appear once JobPilot finds a skill gap in your matches.</EmptyState>
      ) : (
        <Card>
          <CardHeader className="gap-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <CardTitle>Learning resources</CardTitle>
                <CardDescription>Hand-picked, free where possible, from official or well-known sites.</CardDescription>
              </div>
              <Field label="Skill" htmlFor="learn-gap" className="sm:w-64">
                <NativeSelect id="learn-gap" value={selected ? String(selected) : ""} onChange={(v) => onSelectGap(Number(v))} className="w-full"
                              options={openGaps.map((g) => ({ value: String(g.id), label: g.skill }))} />
              </Field>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {detail.isLoading ? <Skeleton className="h-32" /> : detail.isError ? <p className="text-sm text-destructive">{errorMessage(detail.error)}</p> : detail.data && (
              <>
                <p className="text-sm text-muted-foreground">
                  Your level in {detail.data.skill}: <span className="font-medium text-foreground">{stateLabel(detail.data.evidence_state)}</span>.
                  Suggested level: <span className="font-medium text-foreground">{detail.data.learning.level_suggested}</span>.
                </p>
                {detail.data.learning.note && <p className="text-xs text-amber-700 dark:text-amber-400">{detail.data.learning.note}</p>}
                <ul className="space-y-2">
                  {detail.data.learning.resources.map((r) => (
                    <ResourceItem key={r.id} r={r} running={current?.resource_id === r.id && current.status === "active"}
                                  starting={start.isPending && start.variables?.resource_id === r.id}
                                  onStart={() => startSession({ resource_id: r.id, gap_id: detail.data!.id })} />
                  ))}
                </ul>
                <Button variant="outline" size="sm" disabled={start.isPending} onClick={() => startSession({ gap_id: detail.data!.id })}>
                  <Play /> Start a session for {detail.data.skill} without a specific resource
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}

      <SessionHistory loading={sessions.isLoading} data={sessions.data} />
    </div>
  );
}

function linkStatusText(r: LearningResource): string {
  if (r.link_status === "ok") return `Link checked ${formatDate(r.checked_at)}`;
  if (r.link_status === "unverifiable") return "Site blocks automated checks";
  return "Link not checked yet";
}

function ResourceItem({ r, running, starting, onStart }: { r: LearningResource; running: boolean; starting: boolean; onStart: () => void }) {
  return (
    <li className="rounded-lg border p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium underline-offset-2 hover:underline">
            {r.title} <ExternalLink className="size-3" />
          </a>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span>{r.provider}</span><span>· {r.type}</span><span>· {r.level}</span>
            {r.duration_minutes != null && <span>· about {minutes(r.duration_minutes)}</span>}
            {r.is_free && <FreeBadge />}
            <span className={cn(r.link_status === "ok" ? "text-emerald-700 dark:text-emerald-400" : "")}>· {linkStatusText(r)}</span>
          </div>
          <p className="text-xs text-muted-foreground">Why this: {r.relevance}</p>
        </div>
        {running ? <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary"><Timer className="size-3.5" /> In progress</span> : (
          <Button size="sm" className="shrink-0" disabled={starting} onClick={onStart}>{starting ? <Loader2 className="animate-spin" /> : <Play />} Start learning</Button>
        )}
      </div>
    </li>
  );
}

/** A running or paused session: visible timer, heartbeats while the page is visible, pause/resume/finish. */
function ActiveSession({ session, onFinished }: { session: LearningSession; onFinished: (r: CompleteResult) => void }) {
  const qc = useQueryClient();
  const { mutate } = useSessionAction();
  const pauseResume = useSessionAction();
  const [finishOpen, setFinishOpen] = useState(false);
  const running = session.status === "active";
  const lastInput = useRef(0);
  const [lastInputAt, setLastInputAt] = useState(() => Date.now());  // coarse copy of lastInput for rendering
  const [visible, setVisible] = useState(() => document.visibilityState === "visible");
  const [now, setNow] = useState(() => Date.now());

  // Re-base the visible clock whenever the server's totals change.
  const total = session.active_seconds + session.idle_seconds;
  const syncKey = `${total}:${session.status}`;
  const [base, setBase] = useState(() => ({ key: syncKey, at: now }));
  if (base.key !== syncKey) setBase({ key: syncKey, at: now });
  const shown = total + (running ? Math.max(0, (now - base.at) / 1000) : 0);
  const idleNow = now - lastInputAt >= ACTIVE_WINDOW_MS;

  useEffect(() => {
    if (!running) return;
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [running]);

  useEffect(() => {
    if (!running) return;
    const beat = (active: boolean) =>
      mutate({ id: session.id, action: "heartbeat", active }, { onError: () => void qc.invalidateQueries({ queryKey: ck.sessions }) });
    const markInput = () => {
      const t = Date.now();
      lastInput.current = t;
      setLastInputAt((prev) => (t - prev > 5_000 ? t : prev));
    };
    if (!lastInput.current) lastInput.current = Date.now();
    const inputEvents = ["pointermove", "pointerdown", "keydown", "scroll", "wheel", "touchstart"] as const;
    inputEvents.forEach((e) => window.addEventListener(e, markInput, { passive: true }));
    const isActive = () => Date.now() - lastInput.current < ACTIVE_WINDOW_MS;
    // Time since the last heartbeat (e.g. while this page was closed) is recorded as idle, never as learning.
    beat(false);
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") beat(isActive());
    }, HEARTBEAT_MS);
    const onVisibility = () => {
      const v = document.visibilityState === "visible";
      setVisible(v);
      // Leaving: count the visible stretch so far. Returning: the hidden stretch is idle time.
      beat(v ? false : isActive());
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
      inputEvents.forEach((e) => window.removeEventListener(e, markInput));
    };
  }, [running, session.id, mutate, qc]);

  const toggle = () => {
    const go = () => pauseResume.mutate({ id: session.id, action: running ? "pause" : "resume" }, { onError: (err) => toast.error(backendMessage(err)) });
    // Before pausing, record the stretch since the last heartbeat so it isn't lost.
    if (running) mutate({ id: session.id, action: "heartbeat", active: Date.now() - lastInput.current < ACTIVE_WINDOW_MS }, { onSettled: go });
    else go();
  };

  return (
    <Card className="border-primary/40">
      <CardContent className="space-y-3 pt-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-primary">{running ? "Learning session running" : "Learning session paused"}</div>
            <div className="text-lg font-semibold">{session.skill}</div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className={cn("font-mono text-3xl font-semibold tabular-nums", !running && "text-muted-foreground")} aria-label="Session time" role="timer">{clock(shown)}</div>
              <div className="text-xs text-muted-foreground">
                {minutes(Math.floor(session.active_seconds / 60))} active · {minutes(Math.floor(session.idle_seconds / 60))} idle
              </div>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={toggle} disabled={pauseResume.isPending}>{running ? <><Pause /> Pause</> : <><Play /> Resume</>}</Button>
          <Button size="sm" onClick={() => setFinishOpen(true)}><Square /> Finish</Button>
        </div>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Eye className="size-3.5" /> {TRACKING_NOTE}. Time counts as active only while this page is visible and you have used the mouse or keyboard in the last 2 minutes.
        </p>
        {running && !visible && <p className="text-xs text-amber-700 dark:text-amber-400">Not counting: this page is hidden.</p>}
        {running && visible && idleNow && <p className="text-xs text-amber-700 dark:text-amber-400">You seem idle. Move the mouse or type to keep counting active time.</p>}
      </CardContent>
      <FinishDialog session={session} open={finishOpen} onOpenChange={setFinishOpen} onFinished={onFinished} />
    </Card>
  );
}

function FinishDialog({ session, open, onOpenChange, onFinished }: {
  session: LearningSession; open: boolean; onOpenChange: (o: boolean) => void; onFinished: (r: CompleteResult) => void;
}) {
  const complete = useCompleteSession();
  const questions = [`In your own words, what is ${session.skill} used for?`, `What is one thing you can now do with ${session.skill}?`];
  const [notes, setNotes] = useState("");
  const [answers, setAnswers] = useState(["", ""]);
  const [helpful, setHelpful] = useState<boolean | null>(null);
  const [link, setLink] = useState("");
  const linkBad = link.trim() !== "" && !isHttpsLink(link);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (linkBad) return;
    const knowledge_check: Record<string, string> = {};
    questions.forEach((q, i) => { if (answers[i].trim()) knowledge_check[q] = answers[i].trim(); });
    complete.mutate({
      id: session.id,
      body: { notes: notes.trim() || null, knowledge_check, helpful, evidence_url: link.trim() || null, evidence_title: link.trim() ? `Project: ${session.skill}` : null },
    }, {
      onSuccess: (r) => { toast.success(`${r.session.skill} is now "${r.skill_state_label}"`); onOpenChange(false); onFinished(r); },
      onError: (err) => toast.error(backendMessage(err)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Finish this session</DialogTitle>
          <DialogDescription>A short check-in. Everything is optional; your answers are saved as evidence for {session.skill}.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <Field label="Notes" htmlFor="fin-notes"><Textarea id="fin-notes" value={notes} maxLength={5000} placeholder="What did you cover?" onChange={(e) => setNotes(e.target.value)} /></Field>
          {questions.map((q, i) => (
            <Field key={q} label={q} htmlFor={`fin-q${i}`}>
              <Input id={`fin-q${i}`} value={answers[i]} maxLength={1000} onChange={(e) => setAnswers(answers.map((a, j) => (j === i ? e.target.value : a)))} />
            </Field>
          ))}
          <div className="space-y-1.5">
            <span className="text-sm font-medium">Was this helpful?</span>
            <div className="flex gap-2" role="group" aria-label="Was this helpful?">
              <Button type="button" size="sm" variant={helpful === true ? "default" : "outline"} aria-pressed={helpful === true} onClick={() => setHelpful(helpful === true ? null : true)}>Yes</Button>
              <Button type="button" size="sm" variant={helpful === false ? "default" : "outline"} aria-pressed={helpful === false} onClick={() => setHelpful(helpful === false ? null : false)}>No</Button>
            </div>
          </div>
          <Field label="Project link (optional)" htmlFor="fin-link"
                 hint={linkBad ? <span className="text-destructive">Links must start with https://</span> : "If you built something, link it (must start with https://). It is saved as project evidence."}>
            <Input id="fin-link" type="url" value={link} placeholder="https://" aria-invalid={linkBad} onChange={(e) => setLink(e.target.value)} />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Keep going</Button>
            <Button type="submit" disabled={complete.isPending || linkBad}>{complete.isPending && <Loader2 className="animate-spin" />} Finish session</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const sessionStatus: Record<string, string> = { active: "Running", paused: "Paused", completed: "Finished" };

function SessionHistory({ loading, data }: { loading: boolean; data?: { sessions: LearningSession[]; stats: { days: number; sessions: number; completed: number; active_minutes: number; idle_minutes: number } } }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your learning sessions</CardTitle>
        {data && (
          <CardDescription>
            Last {data.stats.days} days: {data.stats.sessions} session(s), {data.stats.completed} finished, {minutes(data.stats.active_minutes)} active,
            {" "}{minutes(data.stats.idle_minutes)} idle.
          </CardDescription>
        )}
      </CardHeader>
      <CardContent>
        {loading ? <Skeleton className="h-20" /> : !data?.sessions.length ? <p className="text-sm text-muted-foreground">No sessions yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-muted-foreground">
                <tr><th className="pb-2 font-medium">Skill</th><th className="pb-2 font-medium">Started</th><th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 text-right font-medium">Active</th><th className="pb-2 text-right font-medium">Idle</th></tr>
              </thead>
              <tbody className="divide-y">
                {data.sessions.map((s) => (
                  <tr key={s.id}>
                    <td className="py-2">{s.skill}</td>
                    <td className="py-2 text-muted-foreground">{formatDate(s.started_at, true)}</td>
                    <td className="py-2">{sessionStatus[s.status] ?? s.status}</td>
                    <td className="py-2 text-right tabular-nums">{minutes(Math.floor(s.active_seconds / 60))}</td>
                    <td className="py-2 text-right tabular-nums">{minutes(Math.floor(s.idle_seconds / 60))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
