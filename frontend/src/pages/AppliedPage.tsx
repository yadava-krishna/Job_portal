import { useState } from "react";
import { BellRing, Calendar, ExternalLink, Send, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, ErrorState, LoadingState, NativeSelect, PageHeader } from "@/components/app/common";
import { CompanyMark } from "@/components/app/JobCard";
import { ApplyDialog } from "@/components/app/ApplyDialog";
import { downloadFile, errorMessage } from "@/lib/api";
import { formatDate, stageLabels, statusLabels } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApplicationAction, useApplications } from "@/services/queries";
import type { Application, Stage, UserJob } from "@/types/api";
import { RejectionDialog, RejectionLabel } from "@/features/growth/applications";
import { useReasonLabels } from "@/features/growth/queries";
import { PipelineBoard } from "@/features/applications/PipelineBoard";
import { ApplicationDetailDialog, type RejectTarget } from "@/features/applications/ApplicationDetail";
import { STRIP, StageStrip, stripKeyOf, type StripKey } from "@/features/applications/StageStrip";
import { ApplyStatePill, EvidencePill, WherePill } from "@/features/applications/pills";
import { daysSince, followUpState } from "@/features/applications/events";
import type { RejectionResult } from "@/features/growth/types";

type WithRejection = { rejection_reason?: string | null; rejection_reason_known?: boolean | null };

const STAGES: Stage[] = ["applied", "screening", "assessment", "interview", "offer", "rejected"];
const MOVE_TO: Stage[] = [...STAGES, "archived"];
const STATUS_FILTERS = ["all", "PREPARED", "OPENED", "CONFIRMATION_PENDING", "SUBMITTED", "FAILED", "WITHDRAWN"];
const PENDING = ["PREPARED", "OPENED", "CONFIRMATION_PENDING"];
/** The list and board fill the space left under the header, strip and tabs, and scroll inside it on larger screens. */
const FILL = "lg:max-h-[max(22rem,calc(100dvh-20.5rem))]";

function asUserJob(a: Application): UserJob {
  return { user_job_id: a.user_job_id ?? 0, status: a.status === "SUBMITTED" ? "applied" : "shortlisted", is_saved: false, match_score: a.match_score,
    match_category: a.match_category, matching_skills: [], missing_skills: [], eligibility_status: null, scoring_method: null, discovered_at: a.created_at,
    saved_at: null, dismissed_at: null, application_id: a.id, application_status: a.status, job: a.job };
}

export function AppliedPage() {
  const [filter, setFilter] = useState("all");
  const [stage, setStage] = useState<StripKey | null>(null);
  const [view, setView] = useState<string>("list");
  const apps = useApplications(filter === "all" ? undefined : [filter]);
  const all = useApplications();
  const action = useApplicationAction();
  const [params, setParams] = useSearchParams();
  const linked = Number(params.get("app")) || null;  // /applied?app=12 opens that application (dashboard and notification links)
  const [detailId, setDetailIdState] = useState<number | null>(linked);
  const [seenLink, setSeenLink] = useState(linked);
  if (linked !== seenLink) { setSeenLink(linked); if (linked != null) setDetailIdState(linked); }  // a new ?app= link while already here
  const setDetailId = (id: number | null) => {
    setDetailIdState(id);
    if (id == null && params.has("app")) { params.delete("app"); setParams(params, { replace: true }); }
  };
  const [resume, setResume] = useState<UserJob | null>(null);
  const [rejecting, setRejecting] = useState<RejectTarget | null>(null);
  const [rejections, setRejections] = useState<Record<number, RejectionResult>>({});
  const reasonLabels = useReasonLabels();
  const rejectionOf = (a: Application) => {
    const r = rejections[a.id] ?? (a as Application & WithRejection);
    return { reason: r.rejection_reason ?? null, known: r.rejection_reason_known ?? null };
  };
  const toTarget = (a: Application): RejectTarget => ({ id: a.id, title: a.job.title, company: a.job.company });
  const everything = all.data ?? [];
  const submitted = everything.filter((a) => a.status === "SUBMITTED");
  const pending = everything.filter((a) => PENDING.includes(a.status));
  const rows = (apps.data ?? []).filter((a) => !stage || stripKeyOf(a) === stage);
  const boardFocus: Stage | null = stage === "closed" ? "rejected" : stage;

  const moveStage = (a: Application, to: Stage) => action.mutate({ kind: "stage", id: a.id, stage: to }, {
    onSuccess: () => toast.success(to === "offer" ? "Moved to Offer. Huge." : `Moved to ${stageLabels[to]}`), onError: (e) => toast.error(errorMessage(e)),
  });
  const pickStage = (k: StripKey | null) => { setStage(k); if (k && view === "pending") setView("list"); };

  return (
    <>
      <PageHeader
        title="Applications"
        description="Every shot you've taken and where it stands, from prepared to offer. Stay locked in."
        actions={
          <Button variant="outline" size="sm"
                  onClick={() => void downloadFile("/interviews/calendar.ics", "jobpilot-interviews.ics").catch((e) => toast.error(errorMessage(e)))}>
            <Calendar className="size-4" /> Interview calendar (.ics)
          </Button>
        }
      />

      {all.isError ? <ErrorState error={all.error} onRetry={() => void all.refetch()} className="mb-4" /> : <StageStrip apps={everything} value={stage} onChange={pickStage} />}

      <Tabs value={view} onValueChange={(v) => setView(String(v))} className="mt-4 gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <TabsList>
            <TabsTrigger value="list">List <Count n={rows.length} /></TabsTrigger>
            <TabsTrigger value="board">Board <Count n={submitted.length} /></TabsTrigger>
            <TabsTrigger value="pending">Pending <Count n={pending.length} tone={pending.length ? "warn" : undefined} /></TabsTrigger>
          </TabsList>
          {stage && view !== "pending" && (
            <button type="button" onClick={() => setStage(null)}
                    className="mr-auto inline-flex items-center gap-1 rounded-full bg-ink px-2.5 py-1 text-[12px] font-medium text-background animate-in fade-in-0 zoom-in-95 duration-200 hover:opacity-90">
              {STRIP.find((s) => s.key === stage)?.label} only <X className="size-3" aria-hidden /><span className="sr-only">Clear stage filter</span>
            </button>
          )}
          {view === "list" && (
            <label className="flex items-center gap-2 text-[13px] text-muted-foreground">
              Status
              <NativeSelect ariaLabel="Filter by status" value={filter} onChange={setFilter} className="h-8 rounded-full px-3 text-[13px]"
                            options={STATUS_FILTERS.map((s) => ({ value: s, label: s === "all" ? "All statuses" : statusLabels[s] }))} />
            </label>
          )}
          {view === "board" && <p className="hidden text-xs text-muted-foreground md:block">Drag a card to move it, or use its menu.</p>}
        </div>

        <TabsContent value="list">
          {apps.isLoading ? <LoadingState /> : apps.isError ? <ErrorState error={apps.error} onRetry={() => void apps.refetch()} /> : !rows.length ? (
            stage || filter !== "all"
              ? <EmptyState title="Nothing here rn">No applications match {stage ? `the ${stageLabels[stage] ?? "Closed"} stage` : "this status"}. <button type="button" className="font-medium text-route hover:underline" onClick={() => { setStage(null); setFilter("all"); }}>Show everything</button></EmptyState>
              : <EmptyState icon={<Send className="size-7" />} title="Your pipeline starts here">Use Apply on a job to prepare one. It shows up here once prepared, and counts as submitted only after you confirm.</EmptyState>
          ) : (
            <div className="overflow-hidden rounded-2xl bg-card ring-1 ring-border">
              <div className={cn("overflow-y-auto overscroll-contain", FILL)}>
                <div aria-hidden className="sticky top-0 z-10 hidden grid-cols-[minmax(0,1fr)_11rem_8rem_7rem_3.5rem_8.5rem] gap-3 border-b bg-paper-sunk/95 px-4 py-2 text-[11.5px] font-medium text-muted-foreground backdrop-blur md:grid">
                  <span>Role</span><span>Where it stands</span><span>Applied</span><span>Follow-up</span><span className="text-right">Match</span><span />
                </div>
                <ul className="divide-y divide-border/70">
                  {rows.map((a) => {
                    const days = daysSince(a.submitted_at);
                    const fu = followUpState(a.follow_up_at);
                    const rej = rejectionOf(a);
                    return (
                      <li key={a.id} className="group/row grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 px-4 py-2.5 transition-colors duration-150 hover:bg-paper-sunk/60 md:grid-cols-[minmax(0,1fr)_11rem_8rem_7rem_3.5rem_8.5rem]">
                        <div className="flex min-w-0 items-center gap-3">
                          <CompanyMark name={a.job.company || "?"} className="size-9 rounded-lg text-[12px]" />
                          <div className="min-w-0">
                            <button type="button" onClick={() => setDetailId(a.id)}
                                    className="block max-w-full truncate text-left text-[14px] font-semibold text-heading decoration-route/40 underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring">{a.job.title}</button>
                            <div className="truncate text-[12.5px] text-muted-foreground">{a.job.company} · {a.job.platform}{a.reference_id && <span className="readout"> · Ref {a.reference_id}</span>}</div>
                          </div>
                        </div>
                        <div className="flex min-w-0 flex-col items-end gap-1 md:items-start">
                          <WherePill app={a} />
                          {rej.reason && <RejectionLabel {...rej} labels={reasonLabels} />}
                          {a.status === "SUBMITTED" && <EvidencePill app={a} className="whitespace-normal" />}
                          {a.status !== "SUBMITTED" && <ApplyStatePill state={a.apply_state} label={a.apply_state_label} className="whitespace-normal" />}
                        </div>
                        <div className="readout text-[12.5px] text-muted-foreground max-md:col-span-2 max-md:inline">
                          {a.submitted_at ? <span title={formatDate(a.submitted_at, true)}><span className="text-foreground">{days === 0 ? "Today" : `${days}d ago`}</span><span className="text-muted-foreground"> · {new Date(a.submitted_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</span></span>
                            : <span className="font-sans">Not submitted</span>}
                        </div>
                        <div className="text-[12.5px] max-md:hidden">
                          {fu === "due" ? <span className="inline-flex items-center gap-1 rounded-full bg-caution-tint px-2 py-0.5 font-medium text-caution"><BellRing className="size-3" /> Due</span>
                            : fu === "upcoming" ? <span className="readout text-muted-foreground">{formatDate(a.follow_up_at!)}</span> : <span className="text-muted-foreground/60">—</span>}
                        </div>
                        <div className="readout text-right text-[13px] font-medium max-md:hidden">{a.match_score == null ? <span className="text-muted-foreground">–</span> : `${Math.round(a.match_score)}%`}</div>
                        <div className="flex items-center justify-end gap-1 max-md:col-span-2 max-md:justify-start">
                          {a.status !== "SUBMITTED" && a.status !== "WITHDRAWN" && <Button size="xs" className="px-2.5" onClick={() => setResume(asUserJob(a))}>Continue</Button>}
                          {a.status === "SUBMITTED" && !rej.reason && (
                            <Button size="xs" variant="ghost" className="text-muted-foreground transition-opacity md:opacity-0 md:group-hover/row:opacity-100 md:focus-visible:opacity-100" onClick={() => setRejecting(toTarget(a))}>Record rejection</Button>
                          )}
                          {a.job.job_url && <Button size="icon-xs" variant="ghost" aria-label="Open original listing" className="text-muted-foreground" render={<a href={a.job.job_url} target="_blank" rel="noopener noreferrer" />}><ExternalLink /></Button>}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="board">
          {all.isLoading ? <LoadingState /> : !submitted.length ? (
            <EmptyState title="No applications sent yet. Your first W is loading.">After you confirm a submission it lands here. Move it along as you hear back.</EmptyState>
          ) : (
            <PipelineBoard apps={submitted} stages={STAGES} moveTo={MOVE_TO} onMove={moveStage} onOpen={setDetailId} focus={boardFocus}
                           className={cn("max-h-[70dvh]", FILL)}
                           extra={(a) => rejectionOf(a).reason ? <RejectionLabel {...rejectionOf(a)} labels={reasonLabels} /> : null} />
          )}
        </TabsContent>

        <TabsContent value="pending">
          {all.isLoading ? <LoadingState /> : !pending.length ? (
            <EmptyState title="All caught up. Love that for you.">Prepared or opened applications you haven't confirmed yet wait here.</EmptyState>
          ) : (
            <div className="overflow-hidden rounded-2xl bg-card ring-1 ring-border">
              <p className="border-b bg-caution-tint/50 px-4 py-2 text-[12.5px] text-caution">
                Opening a form doesn't count as applying. Tell us how each one went so your numbers stay honest.
              </p>
              <ul className={cn("divide-y divide-border/70 overflow-y-auto", FILL)}>
                {pending.map((a) => (
                  <li key={a.id} className="flex flex-wrap items-center gap-3 px-4 py-3 sm:flex-nowrap">
                    <CompanyMark name={a.job.company || "?"} className="size-9 rounded-lg text-[12px]" />
                    <div className="min-w-0 flex-1">
                      <button type="button" onClick={() => setDetailId(a.id)} className="block max-w-full truncate text-left text-[14px] font-semibold text-heading hover:underline">{a.job.title}</button>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12.5px] text-muted-foreground">
                        {a.job.company}
                        <WherePill app={a} />
                        <ApplyStatePill state={a.apply_state} label={a.apply_state_label} />
                        <span className="readout">· prepared {formatDate(a.created_at)}</span>
                      </div>
                    </div>
                    <Button size="sm" onClick={() => setResume(asUserJob(a))}>{a.status === "PREPARED" ? "Continue" : "Confirm outcome"}</Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </TabsContent>
      </Tabs>

      <ApplicationDetailDialog id={detailId} onClose={() => setDetailId(null)} onReject={setRejecting}
                               rejection={detailId != null ? rejections[detailId] : undefined} reasonLabels={reasonLabels} />
      <ApplyDialog item={resume} onClose={() => setResume(null)} />
      <RejectionDialog app={rejecting} onClose={() => setRejecting(null)} onSaved={(r) => setRejections((m) => ({ ...m, [r.id]: r }))} />
    </>
  );
}

function Count({ n, tone }: { n: number; tone?: "warn" }) {
  return <span className={cn("readout ml-0.5 rounded-full px-1.5 text-[11px]", tone === "warn" ? "bg-caution-tint text-caution" : "bg-muted text-muted-foreground")}>{n}</span>;
}
