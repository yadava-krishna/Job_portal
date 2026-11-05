import { useState } from "react";
import { ExternalLink, Loader2, Send } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { PlatformBadge, ScoreBadge, SkillChips } from "@/components/app/common";
import { useAddDescription, useAnalysis, useJob } from "@/services/queries";
import { errorMessage } from "@/lib/api";
import { formatDate, postedDisplay, scoreTone, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

const componentNames: Record<string, string> = {
  core_skills: "Skills",
  experience: "Experience",
  responsibilities: "Responsibilities",
  education: "Education",
  location: "Location & preferences",
};

const barTone = { excellent: "bg-emerald-500", good: "bg-sky-500", moderate: "bg-amber-500", low: "bg-rose-500", none: "bg-muted" };

export function JobDetailSheet({ userJobId, onOpenChange, onApply }: {
  userJobId: number | null; onOpenChange: (open: boolean) => void; onApply: (id: number) => void;
}) {
  const job = useJob(userJobId);
  const analysis = useAnalysis(userJobId);
  const addDesc = useAddDescription();
  const [desc, setDesc] = useState("");
  const d = job.data;
  const a = analysis.data;

  return (
    <Sheet open={userJobId != null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
        {!d ? (
          <div className="space-y-3 p-6"><Skeleton className="h-7 w-2/3" /><Skeleton className="h-4 w-1/2" /><Skeleton className="h-40 w-full" /></div>
        ) : (
          <>
            <SheetHeader className="border-b pb-4">
              <div className="flex items-center gap-2"><PlatformBadge platform={d.job.platform} /><ScoreBadge score={d.match_score} category={d.match_category} /></div>
              <SheetTitle className="text-xl">{d.job.title}</SheetTitle>
              <SheetDescription>
                {d.job.company} · {d.job.location ?? "Location not stated"}{d.job.work_mode ? ` · ${d.job.work_mode}` : ""}
              </SheetDescription>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 pt-1 text-sm" aria-label="Job provenance">
                <dt className="text-muted-foreground">Posting date</dt>
                <dd title={postedDisplay(d.job).title}>{postedDisplay(d.job).text} <span className="text-xs text-muted-foreground">({postedDisplay(d.job).badge.toLowerCase()})</span></dd>
                <dt className="text-muted-foreground">Found by JobPilot</dt>
                <dd>{formatDate(d.job.first_seen_at, true)}{d.job.last_verified_at ? ` · still listed ${timeAgo(d.job.last_verified_at)}` : ""}</dd>
                {d.job.closed_at && <><dt className="text-muted-foreground">No longer listed</dt><dd>since {formatDate(d.job.closed_at, true)}</dd></>}
                <dt className="text-muted-foreground">Seen on</dt>
                <dd className="flex flex-wrap gap-x-3 gap-y-1">
                  {(d.job.sources.length ? d.job.sources : [{ source: d.job.source, platform: d.job.platform, url: d.job.job_url, first_seen_at: "" }]).map((s) => (
                    s.url ? <a key={s.source + s.url} href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">{s.platform ?? s.source}<ExternalLink className="size-3" /></a>
                      : <span key={s.source}>{s.platform ?? s.source}</span>
                  ))}
                </dd>
              </dl>
              <div className="flex flex-wrap gap-2 pt-2">
                {d.job.job_url && (
                  <Button size="sm" variant="outline" render={<a href={d.job.job_url} target="_blank" rel="noopener noreferrer" />}>
                    <ExternalLink /> Original listing
                  </Button>
                )}
                <Button size="sm" onClick={() => onApply(d.user_job_id)} disabled={!d.job.job_url}><Send /> {d.application_id ? "Continue application" : "Apply"}</Button>
              </div>
            </SheetHeader>

            <div className="space-y-6 px-4 pb-8">
              <section>
                <h3 className="mb-2 font-semibold">Matching analysis</h3>
                {!a ? <Skeleton className="h-32 w-full" /> : a.overall_score == null ? (
                  <p className="text-sm text-muted-foreground">Not scored yet. Confirm your profile in Settings first.</p>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-muted-foreground">A match score is a guide to which jobs to read first, not proof a job suits you. Check the description yourself.</p>
                    {a.components.map((c) => (
                      <div key={c.name}>
                        <div className="flex justify-between text-sm"><span className="font-medium">{componentNames[c.name] ?? c.name} <span className="text-muted-foreground">({c.weight.toFixed(0)}%)</span></span><span className="tabular-nums">{c.score.toFixed(0)}</span></div>
                        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted"><div className={cn("h-full rounded-full", barTone[scoreTone(c.score)])} style={{ width: `${c.score}%` }} /></div>
                        <p className="mt-1 text-xs text-muted-foreground">{c.evidence}</p>
                      </div>
                    ))}
                    {a.recommendation && <p className="rounded-lg bg-muted p-3 text-sm">{a.recommendation}</p>}
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
                    {a.eligibility_status && a.eligibility_status !== "ELIGIBLE" && (
                      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
                        <strong>Eligibility: {a.eligibility_status.replace("_", " ").toLowerCase()}</strong>
                        <ul className="mt-1 list-disc pl-4">{a.eligibility_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                      </div>
                    )}
                    <p className="text-xs text-muted-foreground">Scored by {a.scoring_method} · confidence {a.confidence}. {a.notes.join(" ")}</p>
                  </div>
                )}
              </section>

              {(d.required_skills.length > 0 || d.education_requirements.length > 0) && (
                <section className="space-y-3">
                  <Separator />
                  <h3 className="font-semibold">Required qualifications</h3>
                  {d.required_skills.length > 0 && <div><h4 className="mb-1 text-sm font-medium">Required skills</h4><SkillChips skills={d.required_skills} tone="neutral" max={40} /></div>}
                  {d.preferred_skills.length > 0 && <div><h4 className="mb-1 text-sm font-medium">Preferred skills</h4><SkillChips skills={d.preferred_skills} tone="neutral" max={40} /></div>}
                  {d.education_requirements.length > 0 && <p className="text-sm"><span className="font-medium">Education:</span> {d.education_requirements.join(", ")}{d.mandatory_qualifications.length ? ` (mandatory: ${d.mandatory_qualifications.join(", ")})` : ""}</p>}
                </section>
              )}

              {d.responsibilities.length > 0 && (
                <section>
                  <Separator className="mb-3" />
                  <h3 className="mb-2 font-semibold">Responsibilities</h3>
                  <ul className="list-disc space-y-1 pl-5 text-sm">{d.responsibilities.map((r) => <li key={r}>{r}</li>)}</ul>
                </section>
              )}

              <section>
                <Separator className="mb-3" />
                <h3 className="mb-2 font-semibold">Complete job description</h3>
                {d.description && !d.description_is_snippet ? (
                  <div className="whitespace-pre-wrap rounded-lg border bg-card p-4 text-sm leading-relaxed">{d.description}</div>
                ) : (
                  <div className="space-y-2">
                    {d.description && <div className="whitespace-pre-wrap rounded-lg border bg-card p-4 text-sm text-muted-foreground">{d.description}<p className="mt-2 text-xs">(snippet only)</p></div>}
                    <p className="text-sm text-muted-foreground">Paste the full description from the original listing to get an accurate score.</p>
                    <Textarea rows={8} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Paste the complete job description…" />
                    <Button size="sm" disabled={desc.trim().length < 80 || addDesc.isPending} onClick={() => addDesc.mutate({ id: d.user_job_id, description: desc }, {
                      onSuccess: () => { setDesc(""); toast.success("Description saved and job re-scored"); void analysis.refetch(); },
                      onError: (e) => toast.error(errorMessage(e)),
                    })}>
                      {addDesc.isPending && <Loader2 className="animate-spin" />} Save description & re-score
                    </Button>
                  </div>
                )}
                {d.verification_flags.length > 0 && <ul className="mt-2 list-disc pl-5 text-xs text-amber-700 dark:text-amber-300">{d.verification_flags.map((f) => <li key={f}>{f}</li>)}</ul>}
              </section>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
