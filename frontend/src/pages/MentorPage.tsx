import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CalendarClock, CheckCircle2, ChevronDown, Compass, Lightbulb, ListChecks, Loader2, MessageSquare, NotebookPen, ShieldCheck, UserPlus, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, Field, LoadingState, PageHeader } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  consentRequired, useAddAction, useCandidateNote, useGrantConsent, useInviteMentor, useMentorNotes, useMentorPlan, useMyMentors,
  usePatchAction, usePatchSession, useReflect, useReflections, useRequestSession, useRevokeMentor,
} from "@/features/growth/queries";
import { ActionForm, ActionLine, DiagnosisCard, NotesList, SessionForm, SessionRow } from "@/features/growth/mentor";
import { SCOPES, scopeLabels, type ConsentRequired, type MentorAssignment, type Reflection, type Scope } from "@/features/growth/types";
import { Chip, Panel } from "@/features/growth/ui";

export function MentorPage() {
  return (
    <>
      <PageHeader eyebrow="Plan & mentor" title={<>Small steps, <em>big W's</em>.</>}
                  description="A plan built from your own activity, a weekly check-in, and people you choose to share your progress with." />
      <div className="space-y-8">
        <YourPlan />
        <YourMentors />
      </div>
    </>
  );
}

function SectionHead({ id, title, children }: { id: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-3">
      <h2 id={id} className="font-display text-[19px] font-bold tracking-[-0.02em]">{title}</h2>
      {children && <p className="max-w-3xl text-[13px] text-muted-foreground">{children}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- plan

function YourPlan() {
  const plan = useMentorPlan();
  const patch = usePatchAction();
  const add = useAddAction();
  const p = plan.data;

  if (plan.isLoading) return <Skeleton className="h-72 rounded-2xl" />;
  if (!p) return <EmptyState title="Couldn't load your plan">{errorMessage(plan.error)}</EmptyState>;
  const open = p.actions.filter((a) => !a.completed_at).length;

  return (
    <section aria-labelledby="plan-h">
      <SectionHead id="plan-h" title="Your plan">{p.note}</SectionHead>

      {p.next_step && (
        <div className="mb-4 flex flex-col gap-3 rounded-2xl bg-card p-4 ring-1 ring-route/25 shadow-[var(--shadow-raised)] sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div className="flex min-w-0 items-start gap-3">
            <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-route-tint text-route"><Compass className="size-4.5" /></span>
            <div className="min-w-0">
              <div className="eyebrow text-route">Next step</div>
              <div className="font-display text-[16px] font-bold text-heading">{p.next_step.label}</div>
              <p className="text-[13px] text-muted-foreground">{p.next_step.reason}</p>
            </div>
          </div>
          {p.next_step.link && <Button className="shrink-0 self-start sm:self-center" render={<Link to={p.next_step.link} />}>Go <ArrowRight /></Button>}
        </div>
      )}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_23rem]">
        <div className="min-w-0 space-y-4">
          <Panel title="Actions" icon={<ListChecks />} count={open || undefined} bodyClassName="px-0 pb-0 sm:px-0"
                 description="Tick off what you've done. Dismiss anything that doesn't fit your situation.">
            {p.actions.length === 0 ? <p className="px-4 pb-3 text-sm text-muted-foreground sm:px-5">No open actions. Add your own below.</p> : (
              <ul className="divide-y divide-border/70">
                {p.actions.map((a) => (
                  <li key={a.id} className="flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-paper-sunk/40 sm:px-5">
                    <Checkbox className="mt-0.5" aria-label={`Mark "${a.title}" done`} checked={!!a.completed_at} disabled={patch.isPending}
                              onCheckedChange={(c) => patch.mutate({ id: a.id, done: !!c }, { onSuccess: () => c && toast.success("Checked off. Nice."), onError: (e) => toast.error(errorMessage(e)) })} />
                    <div className="min-w-0 flex-1"><ActionLine a={a} /></div>
                    <Button size="icon-xs" variant="ghost" className="text-muted-foreground" aria-label={`Dismiss "${a.title}"`} disabled={patch.isPending}
                            onClick={() => patch.mutate({ id: a.id, dismissed: true }, { onError: (e) => toast.error(errorMessage(e)) })}><X /></Button>
                  </li>
                ))}
              </ul>
            )}
            <div className="border-t border-border/70 bg-paper-sunk/40 px-4 py-3 sm:px-5">
              <h3 className="mb-1.5 text-xs font-semibold text-heading">Add your own</h3>
              <ActionForm busy={add.isPending} onSubmit={(v, reset) => add.mutate(v, { onSuccess: () => { reset(); toast.success("Added to your plan. Let's cook."); }, onError: (e) => toast.error(errorMessage(e)) })} />
            </div>
          </Panel>

          {p.diagnoses.length > 0 && (
            <Panel title="What we noticed" icon={<Lightbulb />} description="Patterns in your own activity, with how sure we are and what they can't see." bodyClassName="pt-1">
              <div className="divide-y divide-border/70">{p.diagnoses.map((d) => <DiagnosisCard key={d.rule} d={d} />)}</div>
            </Panel>
          )}
        </div>

        <div className="space-y-4">
          <ReflectionForm key={String(p.reflection_due)} prominent={p.reflection_due} last={p.last_reflection} />
          <PastReflections />
        </div>
      </div>
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
      <div className="flex items-start gap-2.5 rounded-2xl bg-card px-4 py-3 text-[13px] ring-1 ring-border">
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
        <p className="text-muted-foreground">
          <span className="font-medium text-foreground">This week's reflection is done</span>{last ? ` (${formatDate(last.created_at)})` : ""}.{" "}
          <button className="font-medium text-route underline-offset-4 hover:underline" onClick={() => setOpen(true)}>Update it</button>
        </p>
      </div>
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
    <Panel title="Weekly reflection" icon={<NotebookPen />} className={cn(prominent && "ring-2 ring-violet/30")}
           description={prominent ? "Two minutes, once a week. It's the habit that makes the plan useful." : "Change this week's answers."}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="What happened this week?" htmlFor="rf-outcome"><Textarea id="rf-outcome" rows={2} value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="Applications, replies, interviews, things you learned" /></Field>
        <Field label="What got in the way?" htmlFor="rf-obstacle"><Textarea id="rf-obstacle" rows={2} value={obstacle} onChange={(e) => setObstacle(e.target.value)} /></Field>
        <Field label="One thing you'll do next week" htmlFor="rf-next" hint={prominent ? "This is added to your actions as a high priority, due in a week." : undefined}>
          <Input id="rf-next" value={next} onChange={(e) => setNext(e.target.value)} placeholder="e.g. Apply to 3 jobs scoring 70+" />
        </Field>
        <div className="space-y-1.5" role="group" aria-label="Mood">
          <span className="text-sm font-medium">How are you feeling? <span className="font-normal text-muted-foreground">(optional)</span></span>
          <div className="flex flex-wrap items-center gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" aria-pressed={mood === n} onClick={() => setMood(mood === n ? null : n)}
                      className={cn("readout size-8 rounded-full text-xs ring-1 transition-colors duration-150", mood === n ? "bg-violet text-primary-foreground ring-violet" : "ring-border hover:bg-muted")}>{n}</button>
            ))}
            <span className="ml-1 text-xs text-muted-foreground">1 = rough, 5 = great</span>
          </div>
        </div>
        <div className="flex justify-end gap-2">
          {!prominent && <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>Cancel</Button>}
          <Button type="submit" size="sm" disabled={reflect.isPending}>{reflect.isPending && <Loader2 className="animate-spin" />} Save reflection</Button>
        </div>
      </form>
    </Panel>
  );
}

function PastReflections() {
  const list = useReflections();
  if (!list.data?.length) return null;
  return (
    <details className="group rounded-2xl bg-card ring-1 ring-border">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-[13px] font-medium text-heading sm:px-5">
        <span>Past reflections <span className="readout ml-1 rounded-full bg-paper-sunk px-1.5 text-[11px] font-medium text-muted-foreground">{list.data.length}</span></span>
        <ChevronDown className="size-4 text-muted-foreground transition-transform duration-200 group-open:rotate-180" aria-hidden />
      </summary>
      <ul className="divide-y divide-border/70 border-t border-border/70">
        {list.data.map((r) => (
          <li key={r.id} className="space-y-0.5 px-4 py-2.5 text-[13px] sm:px-5">
            <div className="text-xs text-muted-foreground">Week of {formatDate(r.week_start)}{r.mood ? <> · mood <span className="readout">{r.mood}/5</span></> : ""}</div>
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
    <section aria-labelledby="mentors-h">
      <SectionHead id="mentors-h" title="Your mentors">
        Invite someone with a mentor account (a career coach, a senior colleague) to follow your progress. They see only the parts you tick,
        never your resume file, passwords or messages. Every time they look, it's logged. You can stop sharing at any time.
      </SectionHead>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_23rem]">
        <div className="min-w-0 space-y-4">
          <InviteMentor />
          {data.isLoading ? <Skeleton className="h-24 rounded-2xl" /> : active.length === 0 ? (
            <p className="px-1 text-sm text-muted-foreground">You're not sharing with anyone right now.</p>
          ) : (
            <div className="grid gap-4 xl:grid-cols-2">{active.map((m) => <MentorCard key={m.id} m={m} />)}</div>
          )}
          {past.length > 0 && (
            <p className="px-1 text-xs text-muted-foreground">No longer shared with: {past.map((m) => `${m.mentor_name} (since ${formatDate(m.revoked_at)})`).join(", ")}</p>
          )}
        </div>
        <Panel title="Upcoming 1-on-1s" icon={<CalendarClock />} count={upcoming.length || undefined}>
          {upcoming.length === 0 ? <p className="text-[13px] text-muted-foreground">Nothing booked. Request a session from a mentor's card.</p> : (
            <ul className="space-y-2">
              {upcoming.map((s) => (
                <SessionRow key={s.id} s={s} who={nameOf(s.assignment_id)} actions={
                  <Button size="xs" variant="ghost" disabled={patch.isPending}
                          onClick={() => confirm("Cancel this session?") && patch.mutate({ id: s.id, status: "cancelled" }, { onError: (e) => toast.error(errorMessage(e)) })}>Cancel</Button>
                } />
              ))}
            </ul>
          )}
        </Panel>
      </div>
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
    <Panel title="Invite a mentor" icon={<UserPlus />}>
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Mentor's e-mail" htmlFor="mentor-email" className="min-w-56 flex-1">
            <Input id="mentor-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="their account e-mail" />
          </Field>
          <Button type="submit" className="h-10" disabled={invite.isPending}>{invite.isPending ? <Loader2 className="animate-spin" /> : <UserPlus />} Invite</Button>
        </div>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">What they can see</legend>
          <div className="grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
            {SCOPES.map((s) => (
              <label key={s} className={cn("flex cursor-pointer items-start gap-2 rounded-xl px-2.5 py-2 text-[13px] ring-1 transition-colors duration-150",
                scopes.includes(s) ? "bg-lavender/50 ring-violet/30" : "ring-border/70 hover:bg-paper-sunk/60")}>
                <Checkbox className="mt-0.5" checked={scopes.includes(s)} onCheckedChange={() => toggle(s)} />
                <span>{scopeLabels[s].label}<span className="block text-xs text-muted-foreground">{scopeLabels[s].hint}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
      </form>
      {consent && (
        <div role="alert" className="mt-3 rounded-xl bg-caution-tint p-3 text-[13px] animate-in fade-in-0 slide-in-from-top-1 duration-200">
          <p className="flex items-center gap-1.5 font-medium text-caution"><ShieldCheck className="size-4" aria-hidden /> {consent.message}</p>
          <p className="mt-1 text-foreground/85">{consent.text}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" onClick={allow} disabled={grant.isPending || invite.isPending}>
              {(grant.isPending || invite.isPending) ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Allow sharing with mentors I invite
            </Button>
            <Button size="sm" variant="outline" onClick={() => setConsent(null)}>Not now</Button>
          </div>
        </div>
      )}
    </Panel>
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
    <article className="space-y-3 rounded-2xl bg-card p-4 ring-1 ring-border">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-lavender font-display text-[13px] font-bold text-violet">
            {m.mentor_name.split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
          </span>
          <div className="min-w-0">
            <div className="font-semibold text-heading">{m.mentor_name}</div>
            <div className="truncate text-xs text-muted-foreground">{m.mentor_email} · sharing since {formatDate(m.consented_at)}</div>
          </div>
        </div>
        <Button size="xs" variant="outline" onClick={onRevoke} disabled={revoke.isPending}>Revoke</Button>
      </div>
      <div className="flex flex-wrap gap-1">
        {m.scopes.map((s) => <Chip key={s} tone="muted">{scopeLabels[s]?.label ?? s}</Chip>)}
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Button size="xs" variant="ghost" onClick={() => setShowNotes(!showNotes)}><MessageSquare /> {showNotes ? "Hide notes" : "Notes"}</Button>
        <Button size="xs" variant="ghost" onClick={() => setRequesting(!requesting)}><CalendarClock /> {requesting ? "Cancel request" : "Request a session"}</Button>
      </div>
      {requesting && (
        <SessionForm submitLabel="Send request" busy={request.isPending}
                     onSubmit={(v, reset) => request.mutate(v, { onSuccess: () => { reset(); setRequesting(false); toast.success("Session requested"); }, onError: (e) => toast.error(errorMessage(e)) })} />
      )}
      {showNotes && <NotesThread assignmentId={m.id} />}
    </article>
  );
}

function NotesThread({ assignmentId }: { assignmentId: number }) {
  const notes = useMentorNotes(assignmentId);
  const add = useCandidateNote(assignmentId);
  const [body, setBody] = useState("");
  return (
    <div className="space-y-2 border-t border-border/70 pt-3">
      <p className="text-xs text-muted-foreground">Shared notes between you and this mentor.</p>
      {notes.isLoading ? <LoadingState /> : <NotesList notes={notes.data ?? []} />}
      <div className="flex gap-2">
        <Textarea aria-label="New note" rows={2} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write a note…" />
        <Button size="sm" className="self-end" disabled={!body.trim() || add.isPending}
                onClick={() => add.mutate(body.trim(), { onSuccess: () => setBody(""), onError: (e) => toast.error(errorMessage(e)) })}>Add</Button>
      </div>
    </div>
  );
}
