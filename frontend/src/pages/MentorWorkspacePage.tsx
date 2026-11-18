import { useState } from "react";
import { Briefcase, CalendarClock, Check, Eye, Lightbulb, ListChecks, ListPlus, Loader2, Lock, MessageSquare, Target, UserRound, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, PageHeader, StageBadge, StatusBadge } from "@/components/app/common";
import { useAuth } from "@/contexts/AuthContext";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCandidate, useCandidates, useMentorWorkspaceAction, usePatchSession } from "@/features/growth/queries";
import { FunnelView } from "@/features/growth/applications";
import { ActionForm, ActionLine, DiagnosisCard, NotesList, SessionForm, SessionRow } from "@/features/growth/mentor";
import { scopeLabels, type CandidateSummary, type MentorSession } from "@/features/growth/types";
import { Chip, Note, Panel, table } from "@/features/growth/ui";
import { SeverityBadge } from "@/features/career/labels";

export function MentorWorkspacePage() {
  const { user } = useAuth();
  const isMentor = user?.role === "mentor";
  const list = useCandidates(isMentor);
  const [selected, setSelected] = useState<number | null>(null);

  if (!isMentor) {
    return (
      <>
        <PageHeader eyebrow="Mentoring" title="My mentees" />
        <EmptyState icon={<Users className="size-8" />} title="This page is for mentors">
          It's where mentors see the candidates who chose to share their progress with them. If you'd like to be a mentor, ask the JobPilot owner to give your
          account the mentor role. To get help from a mentor yourself, use the Mentor page.
        </EmptyState>
      </>
    );
  }

  const current = selected ?? list.data?.[0]?.assignment_id ?? null;
  return (
    <>
      <PageHeader eyebrow="Mentoring" title={<>Your mentees, <em>at a glance</em>.</>} description="People who invited you to follow their job search." />
      <Note tone="muted" icon={<Eye />} className="mb-4 w-fit text-[13px]">Candidates chose what to share; every view is logged.</Note>
      {list.isLoading ? <Skeleton className="h-64 rounded-2xl" /> : !list.data?.length ? (
        <EmptyState icon={<Users className="size-8" />} title="No mentees yet">When someone invites you using your account e-mail ({user?.email}), they appear here.</EmptyState>
      ) : (
        <div className="space-y-4">
          <nav aria-label="Candidates" className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
            {list.data.map((c) => {
              const on = current === c.assignment_id;
              return (
                <button key={c.assignment_id} onClick={() => setSelected(c.assignment_id)} aria-current={on ? "true" : undefined}
                        className={cn("flex shrink-0 items-center gap-2.5 rounded-2xl bg-card py-2 pr-4 pl-2 text-left ring-1 transition-[box-shadow,background-color] duration-150",
                          on ? "ring-2 ring-route/45 shadow-[var(--shadow-raised)]" : "ring-border hover:bg-paper-sunk/60")}>
                  <span aria-hidden className={cn("flex size-8 items-center justify-center rounded-full font-display text-[12px] font-bold", on ? "bg-route text-primary-foreground" : "bg-lavender text-violet")}>
                    {initials(c.candidate_name)}
                  </span>
                  <span>
                    <span className="block text-[13.5px] font-semibold text-heading">{c.candidate_name}</span>
                    <span className="block text-xs text-muted-foreground">since {formatDate(c.since)} · {c.scopes.length} area(s) shared</span>
                  </span>
                </button>
              );
            })}
          </nav>
          {current != null && <CandidateView key={current} assignmentId={current} />}
        </div>
      )}
    </>
  );
}

const initials = (name: string | null) => (name ?? "?").split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase();

function CandidateView({ assignmentId }: { assignmentId: number }) {
  const q = useCandidate(assignmentId);
  const act = useMentorWorkspaceAction(assignmentId);
  const c = q.data;
  if (q.isLoading) return <Skeleton className="h-96 rounded-2xl" />;
  if (!c) return <EmptyState title="Couldn't open this candidate">{errorMessage(q.error)}</EmptyState>;
  const onError = (e: unknown) => toast.error(errorMessage(e));

  return (
    <div className="min-w-0 space-y-4 animate-in fade-in-0 duration-200">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5">
        <h2 className="font-display text-[20px] font-bold tracking-[-0.02em]">{c.candidate_name ?? "Candidate"}</h2>
        <div className="flex flex-wrap items-center gap-1 text-xs">
          <span className="text-muted-foreground">Shared with you:</span>
          {c.scopes.map((s) => <Chip key={s} tone="violet">{scopeLabels[s]?.label ?? s}</Chip>)}
        </div>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-4"><SharedSections c={c} /></div>
        <div className="space-y-4">
          <Panel title="Notes" icon={<MessageSquare />} count={c.notes.length || undefined}>
            <div className="space-y-3">
              <NoteComposer busy={act.isPending} onSave={(body, visibility, reset) => act.mutate({ kind: "note", body, visibility }, { onSuccess: reset, onError })} />
              <NotesList notes={c.notes} showVisibility />
            </div>
          </Panel>

          <Panel title="1-on-1 sessions" icon={<CalendarClock />} count={c.sessions.length || undefined}>
            <div className="space-y-3">
              {c.sessions.length === 0 ? <p className="text-xs text-muted-foreground">No sessions yet.</p> : (
                <ul className="space-y-2">{c.sessions.map((s) => <SessionItem key={s.id} s={s} />)}</ul>
              )}
              <SessionForm submitLabel="Schedule" busy={act.isPending}
                           onSubmit={(v, reset) => act.mutate({ kind: "session", ...v }, { onSuccess: () => { reset(); toast.success("Session scheduled"); }, onError })} />
            </div>
          </Panel>

          <Panel title="Recommend an action" icon={<ListPlus />}>
            {c.scopes.includes("actions") ? (
              <ActionForm withReason submitLabel="Recommend" busy={act.isPending}
                          onSubmit={(v, reset) => act.mutate({ kind: "action", ...v }, { onSuccess: () => { reset(); toast.success("Added to their action list"); }, onError })} />
            ) : <p className="text-[13px] text-muted-foreground">{c.candidate_name ?? "This candidate"} hasn't shared their action plan, so you can't add actions. Suggest it in a shared note instead.</p>}
          </Panel>
        </div>
      </div>
    </div>
  );
}

/** Only the parts the candidate shared are present in the summary; render exactly those. */
function SharedSections({ c }: { c: CandidateSummary }) {
  return (
    <>
      {c.profile_completeness && (
        <Panel title="Profile" icon={<UserRound />} actions={<span className="readout text-[13px] font-semibold text-heading">{c.profile_completeness.percent}% complete</span>}>
          <Progress value={c.profile_completeness.percent} />
          {c.profile_completeness.missing.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Missing: {c.profile_completeness.missing.map((m) => m.replaceAll("_", " ")).join(", ")}</p>}
        </Panel>
      )}
      {c.funnel && <FunnelView data={c.funnel} title="Results so far" />}
      {c.diagnoses && c.diagnoses.length > 0 && (
        <Panel title="What the AI mentor noticed" icon={<Lightbulb />} bodyClassName="pt-1">
          <div className="divide-y divide-border/70">{c.diagnoses.map((d) => <DiagnosisCard key={d.rule} d={d} />)}</div>
        </Panel>
      )}
      {c.gaps && (
        <Panel title="Skill gaps" icon={<Target />} count={c.gaps.length || undefined} bodyClassName="px-0 pb-1 sm:px-0">
          {c.gaps.length === 0 ? <p className="px-4 pb-3 text-xs text-muted-foreground sm:px-5">No open gaps.</p> : (
            <ul className="divide-y divide-border/70 text-[13px]">
              {c.gaps.map((g) => (
                <li key={g.id} className="space-y-0.5 px-4 py-2.5 sm:px-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5"><span className="font-semibold text-heading">{g.skill}</span><SeverityBadge severity={g.severity} /></span>
                    <span className="text-xs text-muted-foreground"><span className="readout">{g.job_count}</span> job(s) · <span className="readout">{g.rejection_count}</span> rejection(s)</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{g.explanation}</p>
                  {g.next_action && <p className="text-xs">Next: {g.next_action}</p>}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}
      {c.actions && (
        <Panel title="Their open actions" icon={<ListChecks />} count={c.actions.length || undefined} bodyClassName="px-0 pb-1 sm:px-0">
          {c.actions.length === 0 ? <p className="px-4 pb-3 text-xs text-muted-foreground sm:px-5">No open actions.</p> : (
            <ul className="divide-y divide-border/70">{c.actions.map((a) => <li key={a.id} className="px-4 py-2.5 sm:px-5"><ActionLine a={a} /></li>)}</ul>
          )}
        </Panel>
      )}
      {c.applications && (
        <Panel title="Applications" icon={<Briefcase />} count={c.applications.length} bodyClassName="px-0 pb-0 sm:px-0">
          {c.applications.length === 0 ? <p className="px-4 pb-3 text-xs text-muted-foreground sm:px-5">None yet.</p> : (
            <div className={table.wrap}>
              <table className={table.table}>
                <thead className={table.thead}><tr><th className={table.th}>Job</th><th className={table.th}>Company</th><th className={table.th}>Status</th></tr></thead>
                <tbody>
                  {c.applications.map((a) => (
                    <tr key={a.id} className={table.tr}><td className={cn(table.td, "font-medium")}>{a.title}</td><td className={table.td}>{a.company}</td><td className={table.td}><span className="flex flex-wrap gap-1"><StatusBadge status={a.status} /><StageBadge stage={a.stage} /></span></td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}
    </>
  );
}

function NoteComposer({ onSave, busy }: { onSave: (body: string, visibility: "shared" | "private", reset: () => void) => void; busy: boolean }) {
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState<"shared" | "private">("shared");
  return (
    <div className="space-y-2">
      <Textarea aria-label="New note" rows={2} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write a note…" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex rounded-full bg-paper-sunk p-0.5 text-xs ring-1 ring-border/70" role="radiogroup" aria-label="Who can see this note">
          {(["shared", "private"] as const).map((v) => (
            <button key={v} type="button" role="radio" aria-checked={visibility === v} onClick={() => setVisibility(v)}
                    className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-1 transition-colors duration-150", visibility === v ? "bg-card text-foreground shadow-[var(--shadow-raised)]" : "text-muted-foreground hover:text-foreground")}>
              {v === "shared" ? <><Users className="size-3" /> Shared with candidate</> : <><Lock className="size-3" /> Private (only you)</>}
            </button>
          ))}
        </div>
        <Button size="sm" className="ml-auto" disabled={!body.trim() || busy} onClick={() => onSave(body.trim(), visibility, () => setBody(""))}>{busy && <Loader2 className="animate-spin" />} Add note</Button>
      </div>
    </div>
  );
}

function SessionItem({ s }: { s: MentorSession }) {
  const patch = usePatchSession();
  const [closing, setClosing] = useState(false);
  const [summary, setSummary] = useState("");
  return (
    <SessionRow s={s} actions={s.status === "scheduled" ? (
      closing ? (
        <div className="w-full space-y-2 sm:w-72">
          <Textarea aria-label="Session summary" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="What you agreed (the candidate sees this)" />
          <div className="flex justify-end gap-2">
            <Button size="xs" variant="outline" onClick={() => setClosing(false)}>Cancel</Button>
            <Button size="xs" disabled={patch.isPending}
                    onClick={() => patch.mutate({ id: s.id, status: "done", summary: summary.trim() || undefined }, { onSuccess: () => { setClosing(false); toast.success("Marked done. W."); }, onError: (e) => toast.error(errorMessage(e)) })}>
              <Check /> Mark done
            </Button>
          </div>
        </div>
      ) : <Button size="xs" variant="outline" onClick={() => setClosing(true)}>Mark done</Button>
    ) : undefined} />
  );
}
