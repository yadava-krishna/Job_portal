import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ExternalLink, Keyboard, Link2, Loader2, Plus, Radar, RefreshCw, Search, SlidersHorizontal } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApplyDialog } from "@/components/app/ApplyDialog";
import { EmptyState, NativeSelect, PageHeader, PlatformBadge } from "@/components/app/common";
import { ImportDialog } from "@/components/app/ImportDialog";
import { JobCard } from "@/components/app/JobCard";
import { JobDetailSheet } from "@/components/app/JobDetailSheet";
import { errorMessage } from "@/lib/api";
import { takeClip, type ClippedJob } from "@/lib/clipper";
import { cn } from "@/lib/utils";
import { pollRun, useDiscover, useInvalidateWork, useJobAction, useJobs, useSavedSearches, useSearchLinks, useSourceHealth, type JobQuery } from "@/services/queries";
import { FeedEmptyState, RunSummary } from "@/components/app/discovery";
import type { UserJob } from "@/types/api";

const PLATFORMS = ["LinkedIn", "Indeed", "Naukri", "Greenhouse", "Lever", "Ashby", "SmartRecruiters", "Recruitee", "Adzuna"];
const POSTED: [NonNullable<JobQuery["posted"]>, string][] = [
  ["any", "Any date"], ["today", "Posted today"], ["24h", "24 hours"], ["3d", "3 days"], ["7d", "7 days"], ["30d", "30 days"], ["range", "Date range"],
];
const EMPTY_QUERY: JobQuery = { view: "feed", posted: "any", sort: "score", platform: [] };

/** Shared list + JD sheet + apply dialog, used by Discover and Saved. */
export function JobWorkspace({ query, emptyTitle, emptyBody, toolbar, empty, initialDetailId = null, onShowUnknownDates }: {
  query: JobQuery; emptyTitle: string; emptyBody?: React.ReactNode; toolbar?: React.ReactNode;
  /** Replaces the generic empty state (Discover explains *why* the feed is empty). */
  empty?: React.ReactNode;
  initialDetailId?: number | null;
  onShowUnknownDates?: () => void;
}) {
  const jobs = useJobs(query);
  const action = useJobAction();
  const [detailId, setDetailId] = useState<number | null>(initialDetailId);
  const [applyItem, setApplyItem] = useState<UserJob | null>(null);
  const [cursor, setCursor] = useState(0);
  const items = jobs.data?.items ?? [];

  const act = {
    onView: (j: UserJob) => setDetailId(j.user_job_id),
    onSave: (j: UserJob) => action.mutate({ id: j.user_job_id, action: j.is_saved ? "unsave" : "save" }, {
      onSuccess: () => toast.success(j.is_saved ? "Removed from saved" : "Saved"), onError: (e) => toast.error(errorMessage(e)),
    }),
    onApply: (j: UserJob) => setApplyItem(j),
    onDismiss: (j: UserJob) => action.mutate({ id: j.user_job_id, action: j.status === "dismissed" ? "restore" : "dismiss" }, {
      onSuccess: () => toast(j.status === "dismissed" ? "Restored" : "Dismissed", j.status === "dismissed" ? undefined : {
        action: { label: "Undo", onClick: () => action.mutate({ id: j.user_job_id, action: "restore" }) },
      }),
      onError: (e) => toast.error(errorMessage(e)),
    }),
  };

  // Keyboard shortcuts (j/k move, o open, s save, a apply, d dismiss) while no dialog is open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (detailId != null || applyItem) return;
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable=true]") || e.metaKey || e.ctrlKey || e.altKey) return;
      const cur = items[cursor];
      if (e.key === "j") setCursor((c) => Math.min(items.length - 1, c + 1));
      else if (e.key === "k") setCursor((c) => Math.max(0, c - 1));
      else if (!cur) return;
      else if (e.key === "o" || e.key === "Enter") act.onView(cur);
      else if (e.key === "s") act.onSave(cur);
      else if (e.key === "a") act.onApply(cur);
      else if (e.key === "d") act.onDismiss(cur);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  useEffect(() => {
    document.querySelector(`[data-job-index="${cursor}"]`)?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  return (
    <>
      {toolbar}
      <div className="mb-3 flex items-center justify-between text-sm text-muted-foreground">
        <span>{jobs.data ? `${jobs.data.total} job${jobs.data.total === 1 ? "" : "s"}` : "Loading…"} {jobs.isFetching && <Loader2 className="ml-1 inline size-3 animate-spin" />}</span>
        <span className="hidden items-center gap-1 md:flex"><Keyboard className="size-3.5" /> j/k move · o open · s save · a apply · d dismiss</span>
      </div>
      {!!jobs.data?.hidden_unknown_dates && (
        <p className="mb-3 rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground" data-testid="hidden-unknown-dates">
          {jobs.data.hidden_unknown_dates} job{jobs.data.hidden_unknown_dates === 1 ? " is" : "s are"} hidden by the date filter because the source didn't publish a posting date.
          {onShowUnknownDates && <> <Button variant="link" className="h-auto p-0" onClick={onShowUnknownDates}>Show them (labelled “Posting date unknown”)</Button></>}
        </p>
      )}
      {jobs.isLoading ? (
        <div className="grid gap-4 lg:grid-cols-2">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-56" />)}</div>
      ) : jobs.isError ? (
        <p className="text-sm text-destructive">{errorMessage(jobs.error)}</p>
      ) : items.length === 0 ? (
        empty ?? <EmptyState icon={<Search className="size-8" />} title={emptyTitle}>{emptyBody}</EmptyState>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {items.map((it, i) => (
            <div key={it.user_job_id} data-job-index={i} onMouseEnter={() => setCursor(i)}>
              <JobCard item={it} active={i === cursor} actions={act} disabled={action.isPending} />
            </div>
          ))}
        </div>
      )}
      <JobDetailSheet userJobId={detailId} onOpenChange={(o) => !o && setDetailId(null)}
                      onApply={(id) => { const it = items.find((x) => x.user_job_id === id); setDetailId(null); if (it) setApplyItem(it); }} />
      <ApplyDialog item={applyItem} onClose={() => setApplyItem(null)} />
    </>
  );
}

export function DiscoverPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const discover = useDiscover();
  const invalidate = useInvalidateWork();
  const links = useSearchLinks();
  const searches = useSavedSearches();
  const health = useSourceHealth();
  const initialJob = Number(new URLSearchParams(location.search).get("job")) || null;
  const [importOpen, setImportOpen] = useState(false);
  const [linksOpen, setLinksOpen] = useState(false);
  const [clip, setClip] = useState<ClippedJob | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [draft, setDraft] = useState<JobQuery>(() => {
    // Arriving from a saved search ("View matches") pre-filters the feed to what it found.
    const sid = Number(new URLSearchParams(location.search).get("search"));
    return sid ? { ...EMPTY_QUERY, saved_search_id: sid } : EMPTY_QUERY;
  });
  const [query, setQuery] = useState<JobQuery>(draft);

  // A job captured by the browser clipper arrives here for review.
  useEffect(() => {
    const c = takeClip();
    if (c) { setClip(c); setImportOpen(true); }
  }, [location.key]);

  const submit = (e?: FormEvent) => { e?.preventDefault(); setQuery({ ...draft, page: 1 }); };
  const set = <K extends keyof JobQuery>(k: K, v: JobQuery[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const togglePlatform = (p: string) => setDraft((d) => {
    const cur = d.platform ?? [];
    const next = cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p];
    const updated = { ...d, platform: next };
    setQuery({ ...updated, page: 1 });
    return updated;
  });

  const runDiscovery = () => discover.mutate(undefined, {
    onSuccess: async (run) => {
      setRunning("Connecting to sources…");
      const done = await pollRun(run.id, (r) => setRunning(r.status === "running" ? r.summary ?? "Connecting to sources…" : null), 300_000);
      setRunning(null);
      void invalidate();
      // Report what actually happened: a failure, a run that found nothing (and why), or the new jobs.
      if (done.status === "running") toast.warning("Discovery is taking longer than usual; results will appear when it finishes.");
      else if (done.status === "failed") toast.error(done.summary ?? "Discovery could not run.");
      else if (done.jobs_found === 0) toast.info(done.summary ?? "No listings matched your search right now.");
      else toast.success(`${done.jobs_new} new job${done.jobs_new === 1 ? "" : "s"}, ${done.duplicates} already in your feed${done.status === "partial" ? " (some sources had problems)" : ""}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  // First visit after onboarding: start discovery automatically, once, so a new user never meets a blank feed.
  useEffect(() => {
    if (!health.data || health.data.last_run || running || discover.isPending) return;
    try {
      if (sessionStorage.getItem("jobpilot:auto-discovery")) return;
      sessionStorage.setItem("jobpilot:auto-discovery", "1");
    } catch { /* storage unavailable: still run once per mount */ }
    runDiscovery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [health.data]);
  const lastRun = health.data?.last_run;
  const filtered = JSON.stringify({ ...query, page: undefined }) !== JSON.stringify({ ...EMPTY_QUERY, page: undefined });

  const grouped = useMemo(() => {
    const g: Record<string, typeof links.data> = {};
    (links.data ?? []).forEach((l) => { (g[l.platform] ??= []).push(l); });
    return g;
  }, [links.data]);

  const toolbar = (
    <Card className="mb-5 gap-3 p-4">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={draft.q ?? ""} onChange={(e) => set("q", e.target.value)} placeholder="Search title, company or description" className="pl-8" aria-label="Search jobs" />
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => setShowFilters((s) => !s)} aria-expanded={showFilters}><SlidersHorizontal /> Filters</Button>
            <Button type="submit"><Search /> Search</Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {PLATFORMS.map((p) => (
            <button key={p} type="button" onClick={() => togglePlatform(p)} aria-pressed={draft.platform?.includes(p)}
                    className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors", draft.platform?.includes(p) ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>
              {p}
            </button>
          ))}
          <span className="mx-1 h-4 w-px bg-border" />
          {POSTED.map(([v, l]) => (
            <button key={v} type="button" onClick={() => { set("posted", v); if (v !== "range") setQuery({ ...draft, posted: v, page: 1 }); }} aria-pressed={draft.posted === v}
                    className={cn("rounded-full border px-3 py-1 text-xs font-medium", draft.posted === v ? "border-primary bg-primary/10 text-primary" : "hover:bg-muted")}>
              {l}
            </button>
          ))}
        </div>
        {draft.posted !== "any" && draft.posted !== "today" && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={!!draft.include_estimated} onChange={(e) => { const next = { ...draft, include_estimated: e.target.checked || undefined }; setDraft(next); setQuery({ ...next, page: 1 }); }} className="accent-primary" />
            Include estimated dates (alert emails). Jobs with unknown posting dates are never counted as recent.
          </label>
        )}
        {draft.posted === "range" && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Input type="date" className="w-auto" value={draft.date_from ?? ""} onChange={(e) => set("date_from", e.target.value)} aria-label="Posted from" />
            <span>to</span>
            <Input type="date" className="w-auto" value={draft.date_to ?? ""} onChange={(e) => set("date_to", e.target.value)} aria-label="Posted to" />
          </div>
        )}
        {showFilters && (
          <div className="grid gap-3 border-t pt-3 sm:grid-cols-2 lg:grid-cols-5">
            <Input value={draft.domain ?? ""} onChange={(e) => set("domain", e.target.value)} placeholder="Domain (e.g. finance)" aria-label="Domain" />
            <Input value={draft.location ?? ""} onChange={(e) => set("location", e.target.value)} placeholder="Location" aria-label="Location" />
            <Input type="number" min={0} step={0.5} value={draft.experience ?? ""} onChange={(e) => set("experience", e.target.value === "" ? undefined : Number(e.target.value))} placeholder="Your years of experience" aria-label="Experience" />
            <NativeSelect ariaLabel="Work mode" value={draft.work_mode?.[0] ?? ""} onChange={(v) => set("work_mode", v ? [v] : [])}
                          options={[{ value: "", label: "Any work mode" }, { value: "Remote", label: "Remote" }, { value: "Hybrid", label: "Hybrid" }, { value: "On-site", label: "On-site" }]} />
            <Input value={draft.company ?? ""} onChange={(e) => set("company", e.target.value)} placeholder="Company" aria-label="Company" />
            <Input value={draft.skill ?? ""} onChange={(e) => set("skill", e.target.value)} placeholder="Skill (e.g. Excel)" aria-label="Skill" />
            <Input type="number" min={0} step={1} value={draft.salary_min_lpa ?? ""} onChange={(e) => set("salary_min_lpa", e.target.value === "" ? undefined : Number(e.target.value))}
                   placeholder="Min salary (LPA, when listed)" aria-label="Minimum salary in lakhs per annum" />
            <NativeSelect ariaLabel="Application status" value={draft.application_status?.[0] ?? ""} onChange={(v) => set("application_status", v ? [v] : [])}
                          options={[{ value: "", label: "Any application status" }, { value: "none", label: "Not applied" }, { value: "PREPARED", label: "Prepared" },
                                    { value: "OPENED", label: "Opened / in progress" }, { value: "SUBMITTED", label: "Applied" }]} />
            <Input value={draft.industry ?? ""} onChange={(e) => set("industry", e.target.value)} placeholder="Industry (e.g. Fintech)" aria-label="Industry" />
            <NativeSelect ariaLabel="Employment type" value={draft.employment_type?.[0] ?? ""} onChange={(v) => set("employment_type", v ? [v] : [])}
                          options={[{ value: "", label: "Any employment type" }, ...["Full-time", "Part-time", "Contract", "Internship", "Temporary"].map((t) => ({ value: t, label: t }))]} />
            <NativeSelect ariaLabel="Posting date confidence" value={draft.confidence?.[0] ?? ""} onChange={(v) => set("confidence", v ? [v as "verified"] : [])}
                          options={[{ value: "", label: "Any date confidence" }, { value: "verified", label: "Verified dates" }, { value: "estimated", label: "Estimated dates" }, { value: "unknown", label: "Unknown dates" }]} />
            <NativeSelect ariaLabel="Found by saved search" value={draft.saved_search_id ? String(draft.saved_search_id) : ""} onChange={(v) => set("saved_search_id", v ? Number(v) : undefined)}
                          options={[{ value: "", label: "Any saved search" }, ...(searches.data ?? []).map((s) => ({ value: String(s.id), label: s.name }))]} />
            <NativeSelect ariaLabel="Sort" value={draft.sort ?? "score"} onChange={(v) => set("sort", v as JobQuery["sort"])}
                          options={[{ value: "score", label: "Best match" }, { value: "posted", label: "Newest posting" }, { value: "discovered", label: "Recently added" }]} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!draft.include_closed} onChange={(e) => set("include_closed", e.target.checked || undefined)} className="accent-primary" />
              Show jobs no longer listed
            </label>
            <label className="flex items-center gap-3 text-sm sm:col-span-2 lg:col-span-2">
              <span className="shrink-0">Min match: <strong>{draft.min_score ?? 0}%</strong></span>
              <input type="range" min={0} max={100} step={5} value={draft.min_score ?? 0} onChange={(e) => set("min_score", Number(e.target.value) || undefined)} className="w-full accent-primary" aria-label="Minimum match score" />
            </label>
            <div className="flex gap-2 lg:col-span-2 lg:justify-end">
              <Button type="button" variant="ghost" onClick={() => { setDraft(EMPTY_QUERY); setQuery(EMPTY_QUERY); }}>Reset</Button>
              <Button type="submit">Apply filters</Button>
            </div>
          </div>
        )}
      </form>
    </Card>
  );

  return (
    <>
      <PageHeader
        title="Discover jobs"
        description="Jobs from employer job boards, your saved searches, alert emails and imports, scored against your confirmed profile."
        actions={<>
          <Button variant="outline" onClick={() => navigate("/searches")}><Radar /> Searches</Button>
          <Button variant="outline" onClick={() => setLinksOpen(true)}><Link2 /> Search links</Button>
          <Button variant="outline" onClick={runDiscovery} disabled={discover.isPending || !!running}>{running ? <Loader2 className="animate-spin" /> : <RefreshCw />} Run discovery now</Button>
          <Button onClick={() => { setClip(null); setImportOpen(true); }}><Plus /> Add job</Button>
        </>}
      />
      {(lastRun || running) && (
        <Card className="mb-5 gap-2 p-4" data-testid="discovery-status">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Latest discovery</h2>
            <Button size="sm" variant="ghost" onClick={() => navigate("/searches?tab=sources")}>Source health</Button>
          </div>
          {running ? <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> {running}</p>
            : lastRun && <RunSummary run={lastRun} compact={lastRun.status === "completed"} />}
        </Card>
      )}
      <JobWorkspace query={query} toolbar={toolbar} emptyTitle="No jobs match yet" initialDetailId={initialJob}
                    onShowUnknownDates={() => { const next = { ...draft, include_unknown_dates: true }; setDraft(next); setQuery({ ...next, page: 1 }); }}
                    empty={<FeedEmptyState lastRun={lastRun} filtered={filtered} running={!!running || discover.isPending} onRun={runDiscovery}
                                           onClearFilters={() => { setDraft(EMPTY_QUERY); setQuery(EMPTY_QUERY); }} />} />
      <ImportDialog open={importOpen} onOpenChange={(o) => { setImportOpen(o); if (!o) { setClip(null); if (location.pathname !== "/discover") navigate("/discover"); } }} clip={clip} />
      <Dialog open={linksOpen} onOpenChange={setLinksOpen}>
        <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Pre-filtered searches</DialogTitle>
            <DialogDescription>Built from your preferences. Open them, find jobs you like, then clip or add them here.</DialogDescription>
          </DialogHeader>
          {Object.keys(grouped).length === 0 && <p className="text-sm text-muted-foreground">Add job titles in your preferences and enable at least one platform.</p>}
          {Object.entries(grouped).map(([platform, ls]) => (
            <div key={platform} className="space-y-1">
              <PlatformBadge platform={platform} />
              <ul className="divide-y rounded-lg border">
                {(ls ?? []).map((l) => (
                  <li key={l.url}><a href={l.url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-muted">
                    <span>{l.title} <span className="text-muted-foreground">· {l.location}</span></span><ExternalLink className="size-3.5 shrink-0" /></a></li>
                ))}
              </ul>
            </div>
          ))}
        </DialogContent>
      </Dialog>
    </>
  );
}

export function SavedPage() {
  return (
    <>
      <PageHeader title="Saved jobs" description="Jobs you bookmarked. Apply when you're ready, or remove the bookmark." />
      <JobWorkspace query={{ view: "saved", sort: "score" }} emptyTitle="Nothing saved yet" emptyBody="Use Save on any job card to keep it here." />
    </>
  );
}
