import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Compass, Loader2, MessageSquare, ShieldCheck, UserPlus, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, Field, PageHeader } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  consentRequired, useAddAction, useCandidateNote, useGrantConsent, useInviteMentor, useMentorNotes, useMentorPlan, useMyMentors,
  usePatchAction, usePatchSession, useReflect, useReflections, useRequestSession, useRevokeMentor,
} from "@/features/growth/queries";
import { ActionForm, ActionLine, DiagnosisCard, NotesList, SessionForm, SessionRow } from "@/features/growth/mentor";
import { SCOPES, scopeLabels, type ConsentRequired, type MentorAssignment, type Reflection, type Scope } from "@/features/growth/types";

export function MentorPage() {
  return (
    <>
      <PageHeader title="Mentor" description="A plan built from your own activity, a weekly check-in, and people you choose to share your progress with." />
      <div className="space-y-10">
        <YourPlan />
        <YourMentors />
      </div>
    </>
  );
}

// ---------------------------------------------------------------- plan

function YourPlan() {
  const plan = useMentorPlan();
  const patch = usePatchAction();
  const add = useAddAction();
  const p = plan.data;

  if (plan.isLoading) return <Skeleton className="h-72" />;
  if (!p) return <EmptyState title="Couldn't load your plan">{errorMessage(plan.error)}</EmptyState>;

  return (
    <section className="space-y-4" aria-labelledby="plan-h">
      <div>
        <h2 id="plan-h" className="text-lg font-semibold">Your plan</h2>
        <p className="text-sm text-muted-foreground">{p.note}</p>
      </div>

      {p.reflection_due && <ReflectionForm prominent last={p.last_reflection} />}

      {p.next_step && (
        <Card className="flex-row items-center justify-between gap-3 border-primary/30 p-4">
          <div className="flex min-w-0 items-start gap-3">
            <Compass className="mt-0.5 size-5 shrink-0 text-primary" />
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">Next step</div>
              <div className="font-medium">{p.next_step.label}</div>
              <p className="text-sm text-muted-foreground">{p.next_step.reason}</p>
            </div>
          </div>
          {p.next_step.link && <Button size="sm" render={<Link to={p.next_step.link} />}>Go <ArrowRight /></Button>}
        </Card>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {p.diagnoses.map((d) => <DiagnosisCard key={d.rule} d={d} />)}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Actions</CardTitle>
          <CardDescription>Tick off what you've done. Dismiss anything that doesn't fit your situation.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {p.actions.length === 0 ? <p className="text-sm text-muted-foreground">No open actions. Add your own below.</p> : (
            <ul className="divide-y">
              {p.actions.map((a) => (
                <li key={a.id} className="flex items-start gap-3 py-2">
                  <Checkbox className="mt-1" aria-label={`Mark "${a.title}" done`} checked={!!a.completed_at} disabled={patch.isPending}
                            onCheckedChange={(c) => patch.mutate({ id: a.id, done: !!c }, { onSuccess: () => c && toast.success("Nice, done."), onError: (e) => toast.error(errorMessage(e)) })} />
                  <div className="flex-1"><ActionLine a={a} /></div>
                  <Button size="icon-xs" variant="ghost" aria-label={`Dismiss "${a.title}"`} disabled={patch.isPending}
                          onClick={() => patch.mutate({ id: a.id, dismissed: true }, { onError: (e) => toast.error(errorMessage(e)) })}><X /></Button>
                </li>
              ))}
            </ul>
          )}
          <div>
            <h4 className="mb-1.5 text-xs font-semibold">Add your own</h4>
            <ActionForm busy={add.isPending} onSubmit={(v, reset) => add.mutate(v, { onSuccess: () => { reset(); toast.success("Added"); }, onError: (e) => toast.error(errorMessage(e)) })} />
          </div>
        </CardContent>
      </Card>

      {!p.reflection_due && <ReflectionForm last={p.last_reflection} />}
      <PastReflections />
    </section>
  );
}

function ReflectionForm({ prominent = false, last }: { prominent?: boolean; last: Reflection | null }) {
  const reflect = useReflect();
  const [open, setOpen] = useState(prominent);
  const [outcome, setOutcome] = useState("");
  const [obstacle, setObstacle] = useState("");
  const [next, setNext] = useState("");
  const [mood, setMood] = useState<number | null>(null);

  if (!open) {
    return (
      <p className="text-sm text-muted-foreground">
        This week's reflection is done{last ? ` (${formatDate(last.created_at)})` : ""}.{" "}
        <button className="font-medium text-foreground underline" onClick={() => setOpen(true)}>Update it</button>
      </p>
    );
  }
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if ([outcome, obstacle, next].some((v) => v.trim().length < 2)) return toast.error("Please fill in all three questions.");
    reflect.mutate({ outcome: outcome.trim(), obstacle: obstacle.trim(), next_action: next.trim(), mood }, {
      onSuccess: () => { toast.success(prominent ? "Reflection saved. Your next action is on your list." : "Reflection updated"); setOpen(false); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };
  return (
    <Card className={cn(prominent && "border-primary/50 ring-2 ring-primary/15")}>
      <CardHeader>
        <CardTitle className="text-base">Weekly reflection</CardTitle>
        <CardDescription>{prominent ? "Two minutes, once a week. It's the habit that makes the plan useful." : "Change this week's answers."}</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-3">
          <Field label="What happened this week?" htmlFor="rf-outcome"><Textarea id="rf-outcome" rows={2} value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="Applications, replies, interviews, things you learned" /></Field>
          <Field label="What got in the way?" htmlFor="rf-obstacle"><Textarea id="rf-obstacle" rows={2} value={obstacle} onChange={(e) => setObstacle(e.target.value)} /></Field>
          <Field label="One thing you'll do next week" htmlFor="rf-next" hint={prominent ? "This is added to your actions as a high priority, due in a week." : undefined}>
            <Input id="rf-next" value={next} onChange={(e) => setNext(e.target.value)} placeholder="e.g. Apply to 3 jobs scoring 70+" />
          </Field>
          <div className="flex flex-wrap items-center gap-1 text-sm" role="group" aria-label="Mood">
            <span className="mr-1 text-muted-foreground">How are you feeling? (optional)</span>
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" aria-pressed={mood === n} onClick={() => setMood(mood === n ? null : n)}
                      className={cn("size-7 rounded-md border text-xs", mood === n ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>{n}</button>
            ))}
            <span className="ml-1 text-xs text-muted-foreground">1 = rough, 5 = great</span>
          </div>
          <div className="flex justify-end gap-2">
            {!prominent && <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>Cancel</Button>}
            <Button type="submit" size="sm" disabled={reflect.isPending}>{reflect.isPending && <Loader2 className="animate-spin" />} Save reflection</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function PastReflections() {
  const list = useReflections();
  if (!list.data?.length) return null;
  return (
    <details className="rounded-xl border p-4">
      <summary className="cursor-pointer text-sm font-medium">Past reflections ({list.data.length})</summary>
      <ul className="mt-3 space-y-3">
        {list.data.map((r) => (
          <li key={r.id} className="text-sm">
            <div className="text-xs text-muted-foreground">Week of {formatDate(r.week_start)}{r.mood ? ` · mood ${r.mood}/5` : ""}</div>
            <p><span className="text-muted-foreground">Happened:</span> {r.outcome}</p>
            <p><span className="text-muted-foreground">In the way:</span> {r.obstacle}</p>
            <p><span className="text-muted-foreground">Next:</span> {r.next_action}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

// ---------------------------------------------------------------- human mentors

function YourMentors() {
  const data = useMyMentors();
  const patch = usePatchSession();
  const active = (data.data?.mentors ?? []).filter((m) => m.status === "active");
  const past = (data.data?.mentors ?? []).filter((m) => m.status !== "active");
  const upcoming = (data.data?.sessions ?? []).filter((s) => s.status === "scheduled")
    .sort((a, b) => (a.scheduled_at ?? "9").localeCompare(b.scheduled_at ?? "9"));
  const nameOf = (id?: number) => active.find((m) => m.id === id)?.mentor_name;

  return (
    <section className="space-y-4" aria-labelledby="mentors-h">
      <div>
        <h2 id="mentors-h" className="text-lg font-semibold">Your mentors</h2>
        <p className="text-sm text-muted-foreground">
          Invite someone with a mentor account (a career coach, a senior colleague) to follow your progress. They see only the parts you tick,
          never your resume file, passwords or messages. Every time they look, it's logged. You can stop sharing at any time.
        </p>
      </div>
      <InviteMentor />
      {data.isLoading ? <Skeleton className="h-24" /> : active.length === 0 ? (
        <p className="text-sm text-muted-foreground">You're not sharing with anyone right now.</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">{active.map((m) => <MentorCard key={m.id} m={m} />)}</div>
      )}
      {upcoming.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Upcoming 1-on-1s</CardTitle></CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {upcoming.map((s) => (
                <SessionRow key={s.id} s={s} who={nameOf(s.assignment_id)} actions={
                  <Button size="xs" variant="ghost" disabled={patch.isPending}
                          onClick={() => confirm("Cancel this session?") && patch.mutate({ id: s.id, status: "cancelled" }, { onError: (e) => toast.error(errorMessage(e)) })}>Cancel</Button>
                } />
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
      {past.length > 0 && (
        <p className="text-xs text-muted-foreground">No longer shared with: {past.map((m) => `${m.mentor_name} (since ${formatDate(m.revoked_at)})`).join(", ")}</p>
      )}
    </section>
  );
}

function InviteMentor() {
  const invite = useInviteMentor();
  const grant = useGrantConsent();
  const [email, setEmail] = useState("");
  const [scopes, setScopes] = useState<Scope[]>(["funnel", "gaps", "actions"]);
  const [consent, setConsent] = useState<ConsentRequired | null>(null);
  const toggle = (s: Scope) => setScopes((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  const send = () => invite.mutate({ mentor_email: email.trim(), scopes }, {
    onSuccess: () => { toast.success("Shared. They'll see you in their mentor workspace."); setEmail(""); setConsent(null); },
    onError: (err) => {
      const c = consentRequired(err);
      if (c) setConsent(c);
      else toast.error(errorMessage(err));
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!email.includes("@")) return toast.error("Enter your mentor's e-mail address.");
    if (!scopes.length) return toast.error("Choose at least one thing to share.");
    send();
  };
  const allow = () => grant.mutate(consent?.consent ?? "mentor_sharing", { onSuccess: () => send(), onError: (err) => toast.error(errorMessage(err)) });

  return (
    <Card className="gap-3 p-4">
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Mentor's e-mail" htmlFor="mentor-email" className="min-w-64 flex-1">
            <Input id="mentor-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="their account e-mail" />
          </Field>
          <Button type="submit" disabled={invite.isPending}>{invite.isPending ? <Loader2 className="animate-spin" /> : <UserPlus />} Invite</Button>
        </div>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">What they can see</legend>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {SCOPES.map((s) => (
              <label key={s} className="flex items-start gap-2 text-sm">
                <Checkbox className="mt-0.5" checked={scopes.includes(s)} onCheckedChange={() => toggle(s)} />
                <span>{scopeLabels[s].label}<span className="block text-xs text-muted-foreground">{scopeLabels[s].hint}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
      </form>
      {consent && (
        <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          <p className="font-medium">{consent.message}</p>
          <p className="mt-1">{consent.text}</p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={allow} disabled={grant.isPending || invite.isPending}>
              {(grant.isPending || invite.isPending) ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Allow sharing with mentors I invite
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConsent(null)}>Not now</Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function MentorCard({ m }: { m: MentorAssignment }) {
  const revoke = useRevokeMentor();
  const [showNotes, setShowNotes] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const request = useRequestSession(m.id);
  const onRevoke = () => {
    if (!confirm(`Stop sharing with ${m.mentor_name}? They will no longer see anything about you.`)) return;
    revoke.mutate(m.id, { onSuccess: () => toast.success("Sharing stopped"), onError: (e) => toast.error(errorMessage(e)) });
  };
  return (
    <Card className="gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium">{m.mentor_name}</div>
          <div className="truncate text-xs text-muted-foreground">{m.mentor_email} · sharing since {formatDate(m.consented_at)}</div>
        </div>
        <Button size="xs" variant="outline" onClick={onRevoke} disabled={revoke.isPending}>Revoke</Button>
      </div>
      <div className="flex flex-wrap gap-1">
        {m.scopes.map((s) => <span key={s} className="rounded-md bg-muted px-1.5 py-0.5 text-xs">{scopeLabels[s]?.label ?? s}</span>)}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button size="xs" variant="ghost" onClick={() => setShowNotes(!showNotes)}><MessageSquare /> {showNotes ? "Hide notes" : "Notes"}</Button>
        <Button size="xs" variant="ghost" onClick={() => setRequesting(!requesting)}>{requesting ? "Cancel request" : "Request a session"}</Button>
      </div>
      {requesting && (
        <SessionForm submitLabel="Send request" busy={request.isPending}
                     onSubmit={(v, reset) => request.mutate(v, { onSuccess: () => { reset(); setRequesting(false); toast.success("Session requested"); }, onError: (e) => toast.error(errorMessage(e)) })} />
      )}
      {showNotes && <NotesThread assignmentId={m.id} />}
    </Card>
  );
}

function NotesThread({ assignmentId }: { assignmentId: number }) {
  const notes = useMentorNotes(assignmentId);
  const add = useCandidateNote(assignmentId);
  const [body, setBody] = useState("");
  return (
    <div className="space-y-2 border-t pt-3">
      <p className="text-xs text-muted-foreground">Shared notes between you and this mentor.</p>
      {notes.isLoading ? <Loader2 className="animate-spin" /> : <NotesList notes={notes.data ?? []} />}
      <div className="flex gap-2">
        <Textarea aria-label="New note" rows={2} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write a note…" />
        <Button size="sm" className="self-end" disabled={!body.trim() || add.isPending}
                onClick={() => add.mutate(body.trim(), { onSuccess: () => setBody(""), onError: (e) => toast.error(errorMessage(e)) })}>Add</Button>
      </div>
    </div>
  );
}
