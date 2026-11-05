import { useEffect, useState } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, NativeSelect, PageHeader, PlatformBadge, ScoreBadge, StageBadge, StatusBadge } from "@/components/app/common";
import { ApplyDialog } from "@/components/app/ApplyDialog";
import { errorMessage } from "@/lib/api";
import { formatDate, stageLabels, statusLabels } from "@/lib/format";
import { useApplication, useApplicationAction, useApplications, useUpdateTracking } from "@/services/queries";
import type { Application, Stage, UserJob } from "@/types/api";

const STAGES: Stage[] = ["applied", "screening", "assessment", "interview", "offer", "rejected"];
const MOVE_TO: Stage[] = [...STAGES, "archived"];
const STATUS_FILTERS = ["all", "PREPARED", "OPENED", "CONFIRMATION_PENDING", "SUBMITTED", "FAILED", "WITHDRAWN"];

function asUserJob(a: Application): UserJob {
  return { user_job_id: a.user_job_id ?? 0, status: a.status === "SUBMITTED" ? "applied" : "shortlisted", is_saved: false, match_score: a.match_score,
    match_category: a.match_category, matching_skills: [], missing_skills: [], eligibility_status: null, scoring_method: null, discovered_at: a.created_at,
    saved_at: null, dismissed_at: null, application_id: a.id, application_status: a.status, job: a.job };
}

export function AppliedPage() {
  const [filter, setFilter] = useState("all");
  const apps = useApplications(filter === "all" ? undefined : [filter]);
  const all = useApplications();
  const action = useApplicationAction();
  const [detailId, setDetailId] = useState<number | null>(null);
  const [resume, setResume] = useState<UserJob | null>(null);
  const submitted = (all.data ?? []).filter((a) => a.status === "SUBMITTED");
  const pending = (all.data ?? []).filter((a) => ["PREPARED", "OPENED", "CONFIRMATION_PENDING"].includes(a.status));

  const moveStage = (a: Application, stage: Stage) => action.mutate({ kind: "stage", id: a.id, stage }, {
    onSuccess: () => toast.success(`Moved to ${stageLabels[stage]}`), onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader title="Applications" description="Everything you prepared or applied to, and where each application stands." />
      <Tabs defaultValue="list">
        <TabsList>
          <TabsTrigger value="list">All applications</TabsTrigger>
          <TabsTrigger value="board">Pipeline board ({submitted.length})</TabsTrigger>
          <TabsTrigger value="pending">Pending ({pending.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="list" className="pt-4">
          <div className="mb-3 flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Status</span>
            <NativeSelect ariaLabel="Filter by status" value={filter} onChange={setFilter} options={STATUS_FILTERS.map((s) => ({ value: s, label: s === "all" ? "All" : statusLabels[s] }))} />
          </div>
          {apps.isLoading ? <Loader2 className="animate-spin" /> : !apps.data?.length ? (
            <EmptyState title="No applications yet">Use Apply on a job to prepare one. It appears here once prepared and moves to Submitted after you confirm.</EmptyState>
          ) : (
            <Card className="overflow-x-auto p-0">
              <table className="w-full min-w-[820px] text-sm">
                <thead className="border-b bg-muted/50 text-left text-muted-foreground">
                  <tr>{["Company", "Job title", "Platform", "Applied on", "Status", "Stage", "Match", "Reference", ""].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y">
                  {apps.data.map((a) => (
                    <tr key={a.id} className="hover:bg-muted/30">
                      <td className="px-3 py-2 font-medium">{a.job.company}</td>
                      <td className="px-3 py-2"><button className="text-left hover:underline" onClick={() => setDetailId(a.id)}>{a.job.title}</button></td>
                      <td className="px-3 py-2"><PlatformBadge platform={a.job.platform} /></td>
                      <td className="px-3 py-2 whitespace-nowrap">{a.submitted_at ? formatDate(a.submitted_at) : <span className="text-muted-foreground">—</span>}</td>
                      <td className="px-3 py-2"><StatusBadge status={a.status} /></td>
                      <td className="px-3 py-2"><StageBadge stage={a.stage} /></td>
                      <td className="px-3 py-2"><ScoreBadge score={a.match_score} /></td>
                      <td className="px-3 py-2 font-mono text-xs">{a.reference_id ?? "—"}</td>
                      <td className="px-3 py-2">
                        <div className="flex justify-end gap-1">
                          {a.status !== "SUBMITTED" && a.status !== "WITHDRAWN" && <Button size="xs" onClick={() => setResume(asUserJob(a))}>Continue</Button>}
                          {a.job.job_url && <Button size="icon-xs" variant="ghost" aria-label="Open original listing" render={<a href={a.job.job_url} target="_blank" rel="noopener noreferrer" />}><ExternalLink /></Button>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="board" className="pt-4">
          {!submitted.length ? <EmptyState title="No submitted applications yet">After you confirm a submission it appears here. Move it along as you hear back.</EmptyState> : (
            <div className="grid gap-4 overflow-x-auto md:grid-cols-3 xl:grid-cols-6">
              {STAGES.map((stage) => {
                const col = submitted.filter((a) => (a.stage ?? "applied") === stage);
                return (
                  <div key={stage} className="min-w-56 rounded-xl bg-muted/50 p-3">
                    <div className="mb-3 flex items-center justify-between text-sm font-medium">{stageLabels[stage]}<span className="text-muted-foreground">{col.length}</span></div>
                    <div className="space-y-2">
                      {col.map((a) => (
                        <Card key={a.id} className="gap-2 p-3">
                          <button className="text-left text-sm font-medium hover:underline" onClick={() => setDetailId(a.id)}>{a.job.title}</button>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">{a.job.company} <PlatformBadge platform={a.job.platform} /></div>
                          <NativeSelect ariaLabel="Move to stage" value={a.stage ?? "applied"} onChange={(v) => moveStage(a, v as Stage)} className="h-7 w-full text-xs"
                                        options={MOVE_TO.map((s) => ({ value: s, label: stageLabels[s] }))} />
                        </Card>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </TabsContent>

        <TabsContent value="pending" className="pt-4">
          {!pending.length ? <EmptyState title="Nothing pending">Prepared or opened applications that you haven't confirmed appear here.</EmptyState> : (
            <div className="grid gap-3 md:grid-cols-2">
              {pending.map((a) => (
                <Card key={a.id} className="flex-row items-center justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{a.job.title}</div>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">{a.job.company} <StatusBadge status={a.status} /></div>
                  </div>
                  <Button size="sm" onClick={() => setResume(asUserJob(a))}>Continue</Button>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
      <ApplicationDetailDialog id={detailId} onClose={() => setDetailId(null)} />
      <ApplyDialog item={resume} onClose={() => setResume(null)} />
    </>
  );
}

function ApplicationDetailDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { data } = useApplication(id);
  const action = useApplicationAction();
  return (
    <Dialog open={id != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl">
        {!data ? <Loader2 className="animate-spin" /> : (
          <>
            <DialogHeader>
              <DialogTitle>{data.job.title}</DialogTitle>
              <DialogDescription>{data.job.company} · {data.job.platform} · <StatusBadge status={data.status} /></DialogDescription>
            </DialogHeader>
            <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1.5 text-sm">
              <dt className="text-muted-foreground">Prepared</dt><dd>{formatDate(data.created_at, true)}</dd>
              <dt className="text-muted-foreground">Submitted</dt><dd>{data.submitted_at ? formatDate(data.submitted_at, true) : "—"}</dd>
              <dt className="text-muted-foreground">Reference</dt><dd>{data.reference_id ?? "—"}</dd>
              <dt className="text-muted-foreground">How you applied</dt><dd>{data.submission_method ?? "—"}</dd>
              <dt className="text-muted-foreground">Resume used</dt><dd>{data.resume_used ?? "—"}</dd>
              {data.job.job_url && <><dt className="text-muted-foreground">Original listing</dt><dd><a className="underline" href={data.job.job_url} target="_blank" rel="noopener noreferrer">Open</a></dd></>}
            </dl>
            <TrackingForm id={data.id} notes={data.notes} followUp={data.follow_up_at ?? null} />
            <div>
              <h4 className="mb-2 text-sm font-medium">History</h4>
              <ol className="space-y-1.5 border-l pl-4 text-sm">
                {data.events.map((e) => (
                  <li key={e.id}><span className="font-medium">{e.event_type.replaceAll("_", " ").toLowerCase()}</span> <span className="text-muted-foreground">· {formatDate(e.created_at, true)}</span>{e.details && <div className="text-xs text-muted-foreground">{e.details}</div>}</li>
                ))}
              </ol>
            </div>
            {data.status !== "WITHDRAWN" && (
              <div className="flex justify-end gap-2">
                {data.status !== "SUBMITTED" && <Button variant="outline" size="sm" onClick={() => action.mutate({ kind: "fail", id: data.id, reason: "Marked failed by user" }, { onError: (e) => toast.error(errorMessage(e)) })}>Mark failed</Button>}
                <Button variant="outline" size="sm" onClick={() => action.mutate({ kind: "withdraw", id: data.id }, { onSuccess: () => toast("Withdrawn"), onError: (e) => toast.error(errorMessage(e)) })}>Withdraw</Button>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function TrackingForm({ id, notes, followUp }: { id: number; notes: string | null; followUp: string | null }) {
  const save = useUpdateTracking();
  const [n, setN] = useState(notes ?? "");
  const [f, setF] = useState(followUp ? followUp.slice(0, 10) : "");
  useEffect(() => { setN(notes ?? ""); setF(followUp ? followUp.slice(0, 10) : ""); }, [id, notes, followUp]);
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="grid gap-2 sm:grid-cols-[1fr_10rem]">
        <label className="text-sm"><span className="mb-1 block text-muted-foreground">Notes</span>
          <Textarea rows={2} value={n} onChange={(e) => setN(e.target.value)} placeholder="Contacts, interview prep, anything to remember" /></label>
        <label className="text-sm"><span className="mb-1 block text-muted-foreground">Follow up on</span>
          <Input type="date" value={f} onChange={(e) => setF(e.target.value)} /></label>
      </div>
      <div className="flex justify-end">
        <Button size="sm" variant="outline" disabled={save.isPending}
                onClick={() => save.mutate({ id, notes: n || null, follow_up_at: f ? `${f}T09:00:00` : null },
                  { onSuccess: () => toast.success("Saved"), onError: (e) => toast.error(errorMessage(e)) })}>Save notes</Button>
      </div>
    </div>
  );
}
