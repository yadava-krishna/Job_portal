import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bookmark, BookmarkCheck, ExternalLink, FileText, Loader2, MessagesSquare, Send } from "lucide-react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { PlatformBadge, SkillChips } from "@/components/app/common";
import { CompanyMark } from "@/components/app/JobCard";
import { useAddDescription, useAnalysis, useJob, useJobAction } from "@/services/queries";
import { errorMessage } from "@/lib/api";
import { formatDate, postedDisplay, scoreTone, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EligibilityBox, ScoreDimensions } from "@/features/growth/ScoreDimensions";
import { MatchBreakdown } from "@/features/growth/MatchBreakdown";
import { FreshnessBadge, freshnessOf } from "@/components/app/Freshness";
import type { AnalysisV2 } from "@/features/growth/types";

const componentNames: Record<string, string> = {
  core_skills: "Skills",
  experience: "Experience",
  responsibilities: "Responsibilities",
  education: "Education",
  location: "Location & preferences",
};

const barTone = { excellent: "bg-route", good: "bg-route-bright", moderate: "bg-[#C9B99A]", low: "bg-muted-foreground/40", none: "bg-muted" };
const scoreWords = { excellent: "Strong match", good: "Good match", moderate: "Partial match", low: "Weak match", none: "Not scored" } as const;

/** The one Job Description view used everywhere "View full JD" appears: a modal with a fixed header and action bar,
 *  and the full description scrolling inside it, so the list behind keeps its place. */
export function JobDetailModal({ userJobId, onOpenChange, onApply, onOpenJob }: {
  userJobId: number | null; onOpenChange: (open: boolean) => void; onApply: (id: number) => void; onOpenJob?: (id: number) => void;
}) {
  const job = useJob(userJobId);
  const analysis = useAnalysis(userJobId);
  const addDesc = useAddDescription();
  const action = useJobAction();
  const [desc, setDesc] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const d = job.data;
  const a = analysis.data as AnalysisV2 | undefined;
  const dims = a?.dimensions ?? [];
  const tone = scoreTone(d?.match_score);
  const posted = d ? postedDisplay(d.job) : null;

  const sections = d ? ([
    ["overview", "Overview", true],
    ["responsibilities", "Responsibilities", (d.responsibilities ?? []).length > 0],
    ["requirements", "Requirements", (d.required_skills ?? []).length > 0 || (d.education_requirements ?? []).length > 0 || (d.mandatory_qualifications ?? []).length > 0],
    ["preferred", "Preferred", (d.preferred_skills ?? []).length > 0],
    ["match", "Match & eligibility", true],
    ["description", "Full description", true],
  ] as const).filter(([, , show]) => show) : [];
  const jump = (id: string) => {
    const el = scroller.current?.querySelector<HTMLElement>(`[data-section="${id}"]`);
    if (el && scroller.current) scroller.current.scrollTo({ top: el.offsetTop - 12, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  };
  const toggleSave = () => d && action.mutate({ id: d.user_job_id, action: d.is_saved ? "unsave" : "save" }, {
    onSuccess: () => { toast.success(d.is_saved ? "Off your list" : "On your radar ✨"); void job.refetch(); }, onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <Dialog open={userJobId != null} onOpenChange={onOpenChange}>
      <DialogContent data-testid="jd-modal"
                     className="flex h-dvh max-h-dvh w-full max-w-full flex-col gap-0 overflow-hidden rounded-none p-0 sm:h-[88vh] sm:max-h-[88vh] sm:max-w-[960px] sm:rounded-[22px]">
        {!d ? (
          <div className="space-y-3 p-8" role="status" aria-label="Loading job">
            <DialogTitle className="sr-only">Loading job</DialogTitle>
            {job.isError ? <p className="text-sm text-destructive">This job couldn't be loaded. {errorMessage(job.error)}</p>
              : <><Skeleton className="h-8 w-2/3" /><Skeleton className="h-4 w-1/2" /><Skeleton className="h-64 w-full" /></>}
          </div>
        ) : (
          <>
            {/* header: fixed */}
            <header className="border-b px-5 pt-5 pb-3 sm:px-7 sm:pt-6">
              <div className="flex items-start gap-4 pr-8">
                <CompanyMark name={d.job.company || "?"} className="size-12 text-base" />
                <div className="min-w-0 flex-1">
                  <DialogTitle className="font-display text-[22px] leading-tight font-bold tracking-[-0.02em] text-heading sm:text-[26px]">{d.job.title}</DialogTitle>
                  <DialogDescription className="mt-1 text-[14px]">
                    <span className="font-medium text-foreground">{d.job.company}</span>
                    {" · "}{d.job.location_normalized || d.job.location || "Location not stated"}
                    {d.job.work_mode && !(d.job.work_mode === "Remote" && (d.job.location_normalized ?? "").startsWith("Remote")) ? ` · ${d.job.work_mode}` : ""}
                    {(d.job.salary_label || d.job.salary_range) ? ` · ${d.job.salary_label || d.job.salary_range}` : ""}
                  </DialogDescription>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5"><PlatformBadge platform={d.job.platform} /><FreshnessBadge job={d.job} />
                    {posted && <span className="text-xs text-muted-foreground" title={posted.title}>{posted.text} · {posted.badge.toLowerCase()}</span>}
                  </div>
                </div>
                <div className="hidden text-right sm:block" aria-label={d.match_score == null ? "Not scored" : `${Math.round(d.match_score)} percent match`}>
                  <div className={cn("readout text-[34px] leading-none font-semibold", tone === "excellent" ? "text-route" : "text-heading")}>
                    {d.match_score == null ? "–" : Math.round(d.match_score)}<span className="text-base text-muted-foreground">%</span>
                  </div>
                  <div className={cn("eyebrow mt-1 text-[10px]", tone === "excellent" && "text-route")}>{scoreWords[tone]}</div>
                </div>
              </div>
              <nav aria-label="Sections" className="-mx-1 mt-4 flex gap-1 overflow-x-auto">
                {sections.map(([id, label]) => (
                  <button key={id} type="button" onClick={() => jump(id)}
                          className="shrink-0 rounded-full px-3 py-1 text-[13px] font-medium text-muted-foreground transition-colors duration-150 hover:bg-lavender hover:text-violet focus-visible:outline-2 focus-visible:outline-ring">
                    {label}
                  </button>
                ))}
              </nav>
            </header>

            {/* body: the only part that scrolls */}
            <div ref={scroller} className="relative flex-1 space-y-8 overflow-y-auto overscroll-contain px-5 py-6 sm:px-7">
              <section data-section="overview">
                <h3 className="eyebrow mb-3">Overview</h3>
                <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2" aria-label="Job provenance">
                  <Fact label="Posting date"><span title={postedDisplay(d.job).title}>{postedDisplay(d.job).text} <span className="text-xs text-muted-foreground">({postedDisplay(d.job).badge.toLowerCase()})</span></span></Fact>
                  <Fact label="Found by JobPilot">{formatDate(d.job.first_seen_at, true)}{d.job.last_verified_at ? ` · still listed ${timeAgo(d.job.last_verified_at)}` : ""}</Fact>
                  {freshnessOf(d.job) && <Fact label="Still open?"><span data-testid="freshness-detail">{freshnessOf(d.job)!.detail}</span></Fact>}
                  <Fact label="Experience">{d.job.experience_required || "Not stated"}</Fact>
                  {(d.job.salary_label || d.job.salary_range) && (
                    <Fact label="Salary">{d.job.salary_label || d.job.salary_range}
                      {d.job.salary_label?.includes("(assumed)") && <span className="block text-xs text-muted-foreground">The posting doesn't say per year; a figure this size is read as yearly.</span>}
                    </Fact>
                  )}
                  {d.job.location && d.job.location_normalized && d.job.location !== d.job.location_normalized && <Fact label="Location as posted">{d.job.location}</Fact>}
                  {d.job.remote_scope_label && <Fact label="Remote, open to">{d.job.remote_scope_label}</Fact>}
                  {(d.job.industry || d.job.department) && <Fact label="Team">{[d.job.industry, d.job.department].filter(Boolean).join(" · ")}</Fact>}
                  {(d.similar?.length ?? 0) > 0 && (
                    <Fact label="Also listed">
                      <span className="flex flex-wrap gap-1.5">{d.similar!.map((x) => (
                        <button key={x.user_job_id} type="button" disabled={!onOpenJob} onClick={() => onOpenJob?.(x.user_job_id)}
                                className="rounded-full border px-2 py-0.5 text-xs hover:bg-muted disabled:cursor-default">{x.location || "location not stated"}</button>
                      ))}</span>
                    </Fact>
                  )}
                  <Fact label="Seen on">
                    <span className="flex flex-wrap gap-x-3 gap-y-1">
                      {(d.job.sources.length ? d.job.sources : [{ source: d.job.source, platform: d.job.platform, url: d.job.job_url, first_seen_at: "" }]).map((s) => (
                        s.url ? <a key={s.source + s.url} href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-route underline-offset-2 hover:underline">{s.platform ?? s.source}<ExternalLink className="size-3" /></a>
                          : <span key={s.source}>{s.platform ?? s.source}</span>
                      ))}
                    </span>
                  </Fact>
                </dl>
              </section>

              {(d.responsibilities ?? []).length > 0 && (
                <section data-section="responsibilities">
                  <h3 className="eyebrow mb-3">Responsibilities</h3>
                  <ul className="list-disc space-y-1.5 pl-5 text-[15px] leading-relaxed marker:text-violet">{(d.responsibilities ?? []).map((r) => <li key={r}>{r}</li>)}</ul>
                </section>
              )}

              {((d.required_skills ?? []).length > 0 || (d.education_requirements ?? []).length > 0 || (d.mandatory_qualifications ?? []).length > 0) && (
                <section data-section="requirements" className="space-y-3">
                  <h3 className="eyebrow">Requirements</h3>
                  {(d.required_skills ?? []).length > 0 && <SkillChips skills={d.required_skills} tone="neutral" max={40} />}
                  {(d.education_requirements ?? []).length > 0 && <p className="text-sm"><span className="font-medium">Education:</span> {(d.education_requirements ?? []).join(", ")}{(d.mandatory_qualifications ?? []).length ? ` (mandatory: ${(d.mandatory_qualifications ?? []).join(", ")})` : ""}</p>}
                </section>
              )}

              {(d.preferred_skills ?? []).length > 0 && (
                <section data-section="preferred" className="space-y-3">
                  <h3 className="eyebrow">Preferred qualifications</h3>
                  <SkillChips skills={d.preferred_skills} tone="neutral" max={40} />
                </section>
              )}

              <section data-section="match">
                <h3 className="eyebrow mb-3">Match & eligibility</h3>
                {!a ? <Skeleton className="h-32 w-full" /> : a.overall_score == null ? (
                  <p className="text-sm text-muted-foreground">Not scored yet. Confirm your profile in Settings first.</p>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-muted-foreground">{a.disclaimer || "A match score is a guide to which jobs to read first, not proof a job suits you. Check the description yourself."}</p>
                    {a.eligibility && <EligibilityBox eligibility={a.eligibility} reasons={a.eligibility_reasons} />}
                    {a.breakdown && <MatchBreakdown breakdown={a.breakdown} />}
                    {dims.length > 0 ? <ScoreDimensions dimensions={dims} /> : a.components.map((c) => (
                      <div key={c.name}>
                        <div className="flex justify-between text-sm"><span className="font-medium">{componentNames[c.name] ?? c.name} <span className="text-muted-foreground">({c.weight.toFixed(0)}%)</span></span><span className="tabular-nums">{c.score.toFixed(0)}</span></div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted"><div className={cn("h-full rounded-full", barTone[scoreTone(c.score)])} style={{ width: `${c.score}%` }} /></div>
                        <p className="mt-1 text-xs text-muted-foreground">{c.evidence}</p>
                      </div>
                    ))}
                    {a.recommendation && <p className="rounded-xl bg-lavender p-3 text-sm text-heading">{a.recommendation}</p>}
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div><h4 className="mb-1 text-sm font-medium">Why it fits</h4><ul className="list-disc space-y-1 pl-4 text-sm text-muted-foreground">{a.reasons_for.length ? a.reasons_for.map((r) => <li key={r}>{r}</li>) : <li>—</li>}</ul></div>
                      <div><h4 className="mb-1 text-sm font-medium">Gaps</h4><ul className="list-disc space-y-1 pl-4 text-sm text-muted-foreground">{a.reasons_against.length ? a.reasons_against.map((r) => <li key={r}>{r}</li>) : <li>None identified</li>}</ul></div>
                    </div>
                    <div className="space-y-2">
                      <div><h4 className="mb-1 text-sm font-medium">Matching skills</h4><SkillChips skills={a.matching_skills} tone="match" max={30} /></div>
                      {(a.missing_skills.length > 0 || a.missing_optional_skills.length > 0) && (
                        <div><h4 className="mb-1 text-sm font-medium">Missing skills</h4><SkillChips skills={[...a.missing_skills, ...a.missing_optional_skills.map((s) => `${s} (optional)`)]} tone="missing" max={30} /></div>
                      )}
                    </div>
                    {!a.eligibility && a.eligibility_status && a.eligibility_status !== "ELIGIBLE" && (
                      <div className="rounded-xl bg-caution-tint p-3 text-sm text-caution">
                        <strong>Eligibility: {a.eligibility_status.replace("_", " ").toLowerCase()}</strong>
                        <ul className="mt-1 list-disc pl-4">{a.eligibility_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                      </div>
                    )}
                    {(a.unknown_dimensions?.length ?? 0) > 0 && (
                      <p className="text-xs text-muted-foreground">Not enough information for: {dims.filter((x) => a.unknown_dimensions!.includes(x.name)).map((x) => x.label).join(", ") || a.unknown_dimensions!.join(", ")}. These are left out, so they neither help nor hurt the score.</p>
                    )}
                    <p className="text-xs text-muted-foreground">Scored by {a.scoring_method} · confidence {a.confidence}. {a.notes.join(" ")}</p>
                    {a.score_version && <p className="text-[11px] text-muted-foreground/80">Score version {a.score_version}</p>}
                  </div>
                )}
              </section>

              <section data-section="description">
                <h3 className="eyebrow mb-3">Complete job description</h3>
                {d.description && !d.description_is_snippet ? (
                  <div className="max-w-[72ch] whitespace-pre-wrap text-[15px] leading-[1.7]">{d.description}</div>
                ) : (
                  <div className="space-y-2">
                    {d.description && <div className="whitespace-pre-wrap rounded-lg border bg-card p-4 text-sm text-muted-foreground">{d.description}<p className="mt-2 text-xs">(snippet only)</p></div>}
                    <p className="text-sm text-muted-foreground">Paste the full description from the original listing to get an accurate score.</p>
                    <Textarea rows={8} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Paste the complete job description…" />
                    <Button size="sm" disabled={desc.trim().length < 80 || addDesc.isPending} onClick={() => addDesc.mutate({ id: d.user_job_id, description: desc }, {
                      onSuccess: () => { setDesc(""); toast.success("Description saved and job re-scored. Fresh numbers, fr."); void analysis.refetch(); },
                      onError: (e) => toast.error(errorMessage(e)),
                    })}>
                      {addDesc.isPending && <Loader2 className="animate-spin" />} Save description & re-score
                    </Button>
                  </div>
                )}
                {(d.verification_flags ?? []).length > 0 && <ul className="mt-2 list-disc pl-5 text-xs text-caution">{(d.verification_flags ?? []).map((f) => <li key={f}>{f}</li>)}</ul>}
              </section>
            </div>

            {/* actions: fixed */}
            <footer className="flex flex-wrap items-center gap-2 border-t bg-background/80 px-5 py-3 backdrop-blur sm:px-7">
              {d.job.job_url && (
                <a href={d.job.job_url} target="_blank" rel="noopener noreferrer" className={buttonVariants({ variant: "ghost", size: "sm" })}>
                  <ExternalLink /> Open original listing
                </a>
              )}
              <Link to={`/studio?job=${d.user_job_id}`} className={buttonVariants({ variant: "ghost", size: "sm" })}><FileText /> Tailor a resume</Link>
              <Link to={`/interview-prep?job=${d.user_job_id}`} className={buttonVariants({ variant: "ghost", size: "sm" })}><MessagesSquare /> Prepare for interview</Link>
              <div className="ml-auto flex gap-2">
                <Button variant="outline" onClick={toggleSave} disabled={action.isPending} aria-pressed={d.is_saved}>
                  {d.is_saved ? <BookmarkCheck className="text-violet" /> : <Bookmark />} {d.is_saved ? "Saved" : "Save"}
                </Button>
                <Button onClick={() => onApply(d.user_job_id)} disabled={!d.job.job_url} className="px-5"><Send /> {d.application_id ? "Continue application" : "Apply"}</Button>
              </div>
            </footer>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Kept for existing imports: the JD now opens as a modal everywhere. */
export const JobDetailSheet = JobDetailModal;

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}
