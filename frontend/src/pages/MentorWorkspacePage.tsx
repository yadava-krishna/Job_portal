import { useState } from "react";
import { Check, Eye, Loader2, Lock, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

export function MentorWorkspacePage() {
  const { user } = useAuth();
  const isMentor = user?.role === "mentor";
  const list = useCandidates(isMentor);
  const [selected, setSelected] = useState<number | null>(null);

  if (!isMentor) {
    return (
      <>
        <PageHeader title="Mentoring" />
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
      <PageHeader title="Mentoring" description="People who invited you to follow their job search." />
      <p className="mb-4 flex items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-sm"><Eye className="size-4 shrink-0" /> Candidates chose what to share; every view is logged.</p>
      {list.isLoading ? <Skeleton className="h-64" /> : !list.data?.length ? (
        <EmptyState title="No candidates yet">When someone invites you using your account e-mail ({user?.email}), they appear here.</EmptyState>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
          <nav aria-label="Candidates" className="space-y-1">
            {list.data.map((c) => (
              <button key={c.assignment_id} onClick={() => setSelected(c.assignment_id)}
                      className={cn("w-full rounded-lg border px-3 py-2 text-left text-sm", current === c.assignment_id ? "border-primary bg-primary/5" : "hover:bg-muted")}>
                <div className="font-medium">{c.candidate_name}</div>
                <div className="text-xs text-muted-foreground">since {formatDate(c.since)} · {c.scopes.length} area(s) shared</div>
              </button>
            ))}
          </nav>
          {current != null && <CandidateView key={current} assignmentId={current} />}
        </div>
      )}
    </>
  );
}

function CandidateView({ assignmentId }: { assignmentId: number }) {
  const q = useCandidate(assignmentId);
  const act = useMentorWorkspaceAction(assignmentId);
  const c = q.data;
  if (q.isLoading) return <Skeleton className="h-96" />;
  if (!c) return <EmptyState title="Couldn't open this candidate">{errorMessage(q.error)}</EmptyState>;
  const onError = (e: unknown) => toast.error(errorMessage(e));

  return (
    <div className="min-w-0 space-y-5">
      <div>
        <h2 className="text-lg font-semibold">{c.candidate_name ?? "Candidate"}</h2>
        <div className="mt-1 flex flex-wrap gap-1 text-xs">
          <span className="text-muted-foreground">Shared with you:</span>
          {c.scopes.map((s) => <span key={s} className="rounded-md bg-muted px-1.5 py-0.5">{scopeLabels[s]?.label ?? s}</span>)}
        </div>
      </div>

      <SharedSections c={c} />

      <Card>
        <CardHeader><CardTitle className="text-base">Notes</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <NoteComposer busy={act.isPending} onSave={(body, visibility, reset) => act.mutate({ kind: "note", body, visibility }, { onSuccess: reset, onError })} />
          <NotesList notes={c.notes} showVisibility />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">1-on-1 sessions</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {c.sessions.length === 0 ? <p className="text-xs text-muted-foreground">No sessions yet.</p> : (
            <ul className="space-y-2">{c.sessions.map((s) => <SessionItem key={s.id} s={s} />)}</ul>
          )}
          <SessionForm submitLabel="Schedule" busy={act.isPending}
                       onSubmit={(v, reset) => act.mutate({ kind: "session", ...v }, { onSuccess: () => { reset(); toast.success("Session scheduled"); }, onError })} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Recommend an action</CardTitle></CardHeader>
        <CardContent>
          {c.scopes.includes("actions") ? (
            <ActionForm withReason submitLabel="Recommend" busy={act.isPending}
                        onSubmit={(v, reset) => act.mutate({ kind: "action", ...v }, { onSuccess: () => { reset(); toast.success("Added to their action list"); }, onError })} />
          ) : <p className="text-sm text-muted-foreground">{c.candidate_name ?? "This candidate"} hasn't shared their action plan, so you can't add actions. Suggest it in a shared note instead.</p>}
        </CardContent>
      </Card>
    </div>
  );
}

/** Only the parts the candidate shared are present in the summary; render exactly those. */
function SharedSections({ c }: { c: CandidateSummary }) {
  return (
    <>
      {c.profile_completeness && (
        <Card className="gap-2 p-4">
          <div className="flex items-center justify-between text-sm"><span className="font-medium">Profile</span><span className="tabular-nums">{c.profile_completeness.percent}% complete</span></div>
          <Progress value={c.profile_completeness.percent} />
          {c.profile_completeness.missing.length > 0 && <p className="text-xs text-muted-foreground">Missing: {c.profile_completeness.missing.map((m) => m.replaceAll("_", " ")).join(", ")}</p>}
        </Card>
      )}
      {c.funnel && <FunnelView data={c.funnel} title="Results so far" />}
      {c.diagnoses && c.diagnoses.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2">{c.diagnoses.map((d) => <DiagnosisCard key={d.rule} d={d} />)}</div>
      )}
      {c.gaps && (
        <Card>
          <CardHeader><CardTitle className="text-base">Skill gaps</CardTitle></CardHeader>
          <CardContent>
            {c.gaps.length === 0 ? <p className="text-xs text-muted-foreground">No open gaps.</p> : (
              <ul className="divide-y text-sm">
                {c.gaps.map((g) => (
                  <li key={g.id} className="py-2">
                    <div className="flex justify-between gap-2"><span className="font-medium">{g.skill}</span><span className="text-xs text-muted-foreground">{g.job_count} job(s) · {g.rejection_count} rejection(s)</span></div>
                    <p className="text-xs text-muted-foreground">{g.explanation}</p>
                    {g.next_action && <p className="text-xs">Next: {g.next_action}</p>}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}
      {c.actions && (
        <Card>
          <CardHeader><CardTitle className="text-base">Their open actions</CardTitle></CardHeader>
          <CardContent>
            {c.actions.length === 0 ? <p className="text-xs text-muted-foreground">No open actions.</p> : (
              <ul className="divide-y">{c.actions.map((a) => <li key={a.id} className="py-2"><ActionLine a={a} /></li>)}</ul>
            )}
          </CardContent>
        </Card>
      )}
      {c.applications && (
        <Card className="overflow-x-auto p-0">
          <div className="px-4 pt-4 text-base font-medium">Applications ({c.applications.length})</div>
          {c.applications.length === 0 ? <p className="p-4 text-xs text-muted-foreground">None yet.</p> : (
            <table className="mt-2 w-full text-sm">
              <thead className="border-y bg-muted/50 text-left text-xs text-muted-foreground"><tr><th className="px-4 py-1.5 font-medium">Job</th><th className="px-4 py-1.5 font-medium">Company</th><th className="px-4 py-1.5 font-medium">Status</th></tr></thead>
              <tbody className="divide-y">
                {c.applications.map((a) => (
                  <tr key={a.id}><td className="px-4 py-1.5">{a.title}</td><td className="px-4 py-1.5">{a.company}</td><td className="px-4 py-1.5"><span className="flex flex-wrap gap-1"><StatusBadge status={a.status} /><StageBadge stage={a.stage} /></span></td></tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
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
        <div className="flex rounded-lg border p-0.5 text-xs" role="radiogroup" aria-label="Who can see this note">
          {(["shared", "private"] as const).map((v) => (
            <button key={v} type="button" role="radio" aria-checked={visibility === v} onClick={() => setVisibility(v)}
                    className={cn("inline-flex items-center gap-1 rounded-md px-2 py-1", visibility === v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}>
              {v === "shared" ? <><Users className="size-3" /> Shared with candidate</> : <><Lock className="size-3" /> Private (only you)</>}
            </button>
          ))}
        </div>
        <Button size="sm" disabled={!body.trim() || busy} onClick={() => onSave(body.trim(), visibility, () => setBody(""))}>{busy && <Loader2 className="animate-spin" />} Add note</Button>
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
                    onClick={() => patch.mutate({ id: s.id, status: "done", summary: summary.trim() || undefined }, { onSuccess: () => { setClosing(false); toast.success("Marked done"); }, onError: (e) => toast.error(errorMessage(e)) })}>
              <Check /> Mark done
            </Button>
          </div>
        </div>
      ) : <Button size="xs" variant="outline" onClick={() => setClosing(true)}>Mark done</Button>
    ) : undefined} />
  );
}
