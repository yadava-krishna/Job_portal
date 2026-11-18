import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Activity, ChevronLeft, ChevronRight, ExternalLink, Keyboard, LayoutGrid, Rows3, Link2, Loader2, MapPin, MoreHorizontal, Plus, Radar, RefreshCw, Search, SlidersHorizontal, X } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ApplyDialog } from "@/components/app/ApplyDialog";
import { EmptyState, NativeSelect, PageHeader, PlatformBadge } from "@/components/app/common";
import { ImportDialog } from "@/components/app/ImportDialog";
import { JobCard, JobTile } from "@/components/app/JobCard";
import { JobDetailSheet } from "@/components/app/JobDetailSheet";
import { errorMessage } from "@/lib/api";
import { takeClip, type ClippedJob } from "@/lib/clipper";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/format";
import { firstSight } from "@/lib/seenOnce";
import { pollRun, useDiscover, useInvalidateWork, useJobAction, useJobs, useSavedSearches, useSearchLinks, useSourceHealth, type JobQuery } from "@/services/queries";
import { FeedEmptyState } from "@/components/app/discovery";
import type { UserJob } from "@/types/api";

const PLATFORMS = ["LinkedIn", "Indeed", "Naukri", "Greenhouse", "Lever", "Ashby", "SmartRecruiters", "Recruitee", "Adzuna",
                   "Remotive", "Himalayas", "RemoteOK", "Arbeitnow"];
const POSTED: [NonNullable<JobQuery["posted"]>, string][] = [
  ["any", "Any date"], ["today", "Posted today"], ["24h", "24 hours"], ["3d", "3 days"], ["7d", "7 days"], ["30d", "30 days"], ["range", "Date range"],
];
const PAGE_SIZE = 24;
const EMPTY_QUERY: JobQuery = { view: "feed", posted: "any", sort: "score", platform: [], kind: "jobs" };

/** Shared list + JD sheet + apply dialog, used by Discover and Saved. */
export function JobWorkspace({ query, emptyTitle, emptyBody, toolbar, empty, initialDetailId = null, onShowUnknownDates, sortControl }: {
  query: JobQuery; emptyTitle: string; emptyBody?: React.ReactNode; toolbar?: React.ReactNode;
  /** Shown beside the result count. */
  sortControl?: React.ReactNode;
  /** Replaces the generic empty state (Discover explains *why* the feed is empty). */
  empty?: React.ReactNode;
  initialDetailId?: number | null;
  onShowUnknownDates?: () => void;
}) {
  // Pages of 24 (fills a 2- or 3-column grid evenly). A new search or filter starts again at page 1.
  const qKey = JSON.stringify({ ...query, page: undefined });
  const [page, setPage] = useState(1);
  const [seenKey, setSeenKey] = useState(qKey);
  if (qKey !== seenKey) { setSeenKey(qKey); setPage(1); }
  const jobs = useJobs({ ...query, page, page_size: PAGE_SIZE });
  const [view, setViewState] = useState<"grid" | "list">(() => { try { return localStorage.getItem("jobpilot.jobView") === "list" ? "list" : "grid"; } catch { return "grid"; } });
  const setView = (v: "grid" | "list") => { setViewState(v); try { localStorage.setItem("jobpilot.jobView", v); } catch { /* preference only */ } };
  const listTop = useRef<HTMLDivElement>(null);
  const totalPages = jobs.data ? Math.max(1, Math.ceil(jobs.data.total / PAGE_SIZE)) : 1;
  const goTo = (p: number) => {
    setPage(p); setCursor(0);
    listTop.current?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  };
  // The cascade plays for results not yet seen this session (new search, filter or page); coming back shows them at once.
  const feedKey = `${qKey}|${page}|${view}`;
  const [animate] = useState(() => firstSight(feedKey));
  const [lastKey, setLastKey] = useState(feedKey);
  const [play, setPlay] = useState(animate);
  if (feedKey !== lastKey) { setLastKey(feedKey); setPlay(firstSight(feedKey)); }
  const action = useJobAction();
  const [detailId, setDetailId] = useState<number | null>(initialDetailId);
  const [seenLink, setSeenLink] = useState(initialDetailId);
  if (initialDetailId !== seenLink) { setSeenLink(initialDetailId); if (initialDetailId != null) setDetailId(initialDetailId); }  // a new ?job= link while already here
  const [applyItem, setApplyItem] = useState<UserJob | null>(null);
  const [cursor, setCursor] = useState(0);
  const items = jobs.data?.items ?? [];

  const act = {
    onView: (j: UserJob) => setDetailId(j.user_job_id),
    onViewId: (id: number) => setDetailId(id),
    onSave: (j: UserJob) => action.mutate({ id: j.user_job_id, action: j.is_saved ? "unsave" : "save" }, {
      onSuccess: () => toast.success(j.is_saved ? "Off your list. No hard feelings." : "On your radar ✨"), onError: (e) => toast.error(errorMessage(e)),
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
      <div ref={listTop} className="mb-3 flex scroll-mt-20 flex-wrap items-center justify-between gap-3 px-1 text-[13px] text-muted-foreground">
        <span className="flex items-center gap-2"><span><span className="readout text-foreground">{jobs.data ? jobs.data.total : "…"}</span> {jobs.data?.total === 1 ? "job" : "jobs"}</span>{sortControl}{jobs.isFetching && <Loader2 className="inline size-3 animate-spin" />}</span>
        <span className="flex items-center gap-3">
        <span className="hidden items-center gap-1.5 text-xs xl:flex"><Keyboard className="size-3.5" /> <kbd className="readout">j</kbd>/<kbd className="readout">k</kbd> move · <kbd className="readout">o</kbd> open · <kbd className="readout">s</kbd> save · <kbd className="readout">a</kbd> apply · <kbd className="readout">d</kbd> dismiss</span>
        <span role="radiogroup" aria-label="Layout" className="flex gap-0.5 rounded-full bg-paper-sunk p-0.5">
          {([["grid", LayoutGrid, "Grid"], ["list", Rows3, "List"]] as const).map(([v, Icon, label]) => (
            <button key={v} type="button" role="radio" aria-checked={view === v} onClick={() => setView(v)} title={`${label} view`}
                    className={cn("flex h-7 items-center gap-1 rounded-full px-2.5 text-xs font-medium transition-[background,color,box-shadow] duration-200",
                      view === v ? "bg-card text-heading shadow-[var(--shadow-raised)]" : "text-muted-foreground hover:text-foreground")}>
              <Icon className="size-3.5" aria-hidden />{label}
            </button>
          ))}
        </span>
        </span>
      </div>
      {!!jobs.data?.hidden_unknown_dates && (
        <p className="mb-3 rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground" data-testid="hidden-unknown-dates">
          {jobs.data.hidden_unknown_dates} job{jobs.data.hidden_unknown_dates === 1 ? " is" : "s are"} hidden by the date filter because the source didn't publish a posting date.
          {onShowUnknownDates && <> <Button variant="link" className="h-auto p-0" onClick={onShowUnknownDates}>Show them (labelled “Posting date unknown”)</Button></>}
        </p>
      )}
      {jobs.isLoading ? (
        view === "grid"
          ? <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[330px] rounded-[20px]" />)}</div>
          : <div className="flex flex-col gap-2.5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-32 rounded-2xl" />)}</div>
      ) : jobs.isError ? (
        <p className="text-sm text-destructive">{errorMessage(jobs.error)}</p>
      ) : items.length === 0 ? (
        empty ?? <EmptyState icon={<Search className="size-8" />} title={emptyTitle}>{emptyBody}</EmptyState>
      ) : (
        <>
          {view === "grid" ? (
            <div key={`grid-${page}`} className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-3", !play && "jp-static")}>
              {items.map((it, i) => (
                <div key={it.user_job_id} data-job-index={i} onMouseEnter={() => setCursor(i)} className="min-w-0">
                  <JobTile item={it} index={i} active={i === cursor} actions={act} disabled={action.isPending} />
                </div>
              ))}
            </div>
          ) : (
            <div key={`list-${page}`} className={cn("flex flex-col gap-2.5", !play && "jp-static")}>
              {items.map((it, i) => (
                <div key={it.user_job_id} data-job-index={i} onMouseEnter={() => setCursor(i)} className="jp-item" style={{ ["--i" as string]: Math.min(i, 12) }}>
                  <JobCard item={it} active={i === cursor} actions={act} disabled={action.isPending} />
                </div>
              ))}
            </div>
          )}
          {jobs.data && totalPages > 1 && <Pager page={page} totalPages={totalPages} total={jobs.data.total} pageSize={PAGE_SIZE} onPage={goTo} busy={jobs.isFetching} />}
        </>
      )}
      <JobDetailSheet userJobId={detailId} onOpenChange={(o) => !o && setDetailId(null)} onOpenJob={setDetailId}
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
      const done = await pollRun(run.id, (r) => setRunning(r.status === "running" ? r.summary ?? "Connecting to sources…" : null), 900_000);  // a full run checks ~200 boards and can take 8 minutes
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

  const setKind = (kind: "jobs" | "internships") => { const next = { ...draft, kind }; setDraft(next); setQuery({ ...next, page: 1 }); };
  const ADVANCED: (keyof JobQuery)[] = ["domain", "experience", "company", "skill", "salary_min_lpa", "application_status", "industry", "employment_type",
    "confidence", "saved_search_id", "country", "seniority", "sponsorship", "eligibility", "include_closed", "group_similar", "min_score", "platform"];
  const activeCount = ADVANCED.filter((k) => { const v = query[k]; return Array.isArray(v) ? v.length > 0 : v !== undefined && v !== null && v !== ""; }).length;
  const toolbar = (
    <section className="mb-4 rounded-2xl bg-card p-2.5 ring-1 ring-border" aria-label="Search and filter jobs">
      <form onSubmit={submit} className="flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <KindTabs query={query} onChange={setKind} />
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input value={draft.q ?? ""} onChange={(e) => set("q", e.target.value)} placeholder="Role, company or skill" aria-label="Search jobs"
                   className="h-10 rounded-full bg-background pr-11 pl-10 transition-[box-shadow,border-color] duration-150 focus-visible:shadow-[0_0_0_4px_color-mix(in_oklab,var(--route)_14%,transparent)]" />
            <Button type="submit" size="icon-sm" className="absolute top-1/2 right-1 -translate-y-1/2" aria-label="Search" title="Search (Enter)"><Search /></Button>
          </div>
          <div className="relative">
            <MapPin className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input value={draft.location ?? ""} onChange={(e) => set("location", e.target.value)} placeholder="Location" aria-label="Location" className="h-10 w-[120px] rounded-full bg-background pl-9" />
          </div>
          <NativeSelect className="h-10 w-[112px] rounded-full px-3" ariaLabel="Work mode" value={draft.work_mode?.[0] ?? ""} onChange={(v) => { const next = { ...draft, work_mode: v ? [v] : [] }; setDraft(next); setQuery({ ...next, page: 1 }); }}
                        options={[{ value: "", label: "Any mode" }, { value: "Remote", label: "Remote" }, { value: "Hybrid", label: "Hybrid" }, { value: "On-site", label: "On-site" }]} />
          <NativeSelect className="h-10 w-[124px] rounded-full px-3" ariaLabel="Posted" value={draft.posted ?? "any"} onChange={(v) => { const pv = v as NonNullable<JobQuery["posted"]>; set("posted", pv); if (pv === "range") setShowFilters(true); else setQuery({ ...draft, posted: pv, page: 1 }); }}
                        options={POSTED.map(([v, l]) => ({ value: v, label: v === "any" ? "Any date" : l }))} />
          {(searches.data?.length ?? 0) > 0 && (
            <NativeSelect className="h-10 w-[140px] rounded-full px-3" ariaLabel="Saved view" value={draft.saved_search_id ? String(draft.saved_search_id) : ""}
                          onChange={(v) => { const next = { ...draft, saved_search_id: v ? Number(v) : undefined }; setDraft(next); setQuery({ ...next, page: 1 }); }}
                          options={[{ value: "", label: "All searches" }, ...(searches.data ?? []).map((x) => ({ value: String(x.id), label: x.name }))]} />
          )}
          <Button type="button" variant="outline" className={cn("h-10", activeCount > 0 && "border-route/40 bg-route-tint text-route")} onClick={() => setShowFilters((x) => !x)} aria-expanded={showFilters}>
            <SlidersHorizontal /> Filters{activeCount > 0 && <span className="readout rounded-full bg-route px-1.5 text-[11px] text-primary-foreground">{activeCount}</span>}
          </Button>
        </div>
        {activeCount > 0 && !showFilters && (
          <div className="flex flex-wrap items-center gap-1.5 px-1 text-xs">
            {(query.platform ?? []).map((p) => (
              <button key={p} type="button" onClick={() => togglePlatform(p)} className="inline-flex items-center gap-1 rounded-full bg-route-tint px-2.5 py-1 font-medium text-route">{p} <X className="size-3" aria-hidden /><span className="sr-only">Remove</span></button>
            ))}
            {activeCount - (query.platform?.length ? 1 : 0) > 0 && <span className="text-muted-foreground">+ {activeCount - (query.platform?.length ? 1 : 0)} more filter{activeCount - (query.platform?.length ? 1 : 0) === 1 ? "" : "s"}</span>}
            <button type="button" className="ml-1 font-medium text-route underline-offset-2 hover:underline" onClick={() => { setDraft(EMPTY_QUERY); setQuery(EMPTY_QUERY); }}>Reset</button>
          </div>
        )}
        {showFilters && (
          <div className="animate-in space-y-3 border-t px-1.5 pt-3 duration-200 fade-in-0 slide-in-from-top-1">
            <div>
              <div className="eyebrow mb-2">Sources</div>
              <div className="flex flex-wrap items-center gap-1.5">
                {PLATFORMS.map((p) => (
                  <button key={p} type="button" onClick={() => togglePlatform(p)} aria-pressed={draft.platform?.includes(p)}
                          className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors", draft.platform?.includes(p) ? "border-route bg-route text-white" : "bg-card hover:bg-muted")}>
                    {p}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div className="eyebrow mb-2">Posted</div>
              <div className="flex flex-wrap items-center gap-1.5">
                {POSTED.map(([v, l]) => (
                  <button key={v} type="button" onClick={() => { set("posted", v); if (v !== "range") setQuery({ ...draft, posted: v, page: 1 }); }} aria-pressed={draft.posted === v}
                          className={cn("rounded-full border px-3 py-1 text-xs font-medium", draft.posted === v ? "border-route bg-route-tint text-route" : "bg-card hover:bg-muted")}>
                    {l}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
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
          <div className="grid animate-in gap-3 px-1.5 pb-1.5 duration-200 fade-in-0 slide-in-from-top-1 sm:grid-cols-2 lg:grid-cols-4">
            <Input value={draft.domain ?? ""} onChange={(e) => set("domain", e.target.value)} placeholder="Domain (e.g. finance)" aria-label="Domain" />
            <Input type="number" min={0} step={0.5} value={draft.experience ?? ""} onChange={(e) => set("experience", e.target.value === "" ? undefined : Number(e.target.value))} placeholder="Your years of experience" aria-label="Experience" />
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
            <Input value={draft.country ?? ""} maxLength={2} onChange={(e) => set("country", e.target.value.toUpperCase() || undefined)}
                   placeholder="Country code (e.g. GB)" aria-label="Country code" />
            <NativeSelect ariaLabel="Seniority" value={draft.seniority ?? ""} onChange={(v) => set("seniority", v || undefined)}
                          options={[{ value: "", label: "Any seniority" }, ...["Intern", "Entry", "Mid", "Senior", "Lead", "Manager"].map((s) => ({ value: s.toLowerCase(), label: s }))]} />
            <NativeSelect ariaLabel="Visa sponsorship" value={draft.sponsorship?.[0] ?? ""} onChange={(v) => set("sponsorship", v ? [v as "verified"] : [])}
                          options={[{ value: "", label: "Any sponsorship" }, { value: "verified", label: "Sponsorship stated" },
                                    { value: "inferred", label: "Sponsorship likely" }, { value: "none", label: "No sponsorship" }, { value: "unknown", label: "Not mentioned" }]} />
            <NativeSelect ariaLabel="Eligibility" value={draft.eligibility?.[0] ?? ""} onChange={(v) => set("eligibility", v ? [v as "pass"] : [])}
                          options={[{ value: "", label: "Any eligibility" }, { value: "pass", label: "I'm eligible" }, { value: "unknown", label: "Eligibility unknown" }, { value: "fail", label: "Not eligible" }]} />
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!draft.include_closed} onChange={(e) => set("include_closed", e.target.checked || undefined)} className="accent-primary" />
              Show closed and expired jobs
            </label>
            <label className="flex items-center gap-2 text-sm" title="By default the same role at the same company (other cities, re-posts) is shown once, with the rest listed on the card">
              <input type="checkbox" checked={draft.group_similar === false} onChange={(e) => set("group_similar", e.target.checked ? false : undefined)} className="accent-primary" />
              Show every listing separately
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
    </section>
  );

  return (
    <>
      <PageHeader
        title={<>Fresh roles, <em>just dropped</em></>}
        description={(lastRun || running) ? (
          <span data-testid="discovery-status" className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="relative flex size-2">
              {running && <span className="absolute inset-0 animate-ping rounded-full bg-route/60" />}
              <span className={cn("relative size-2 rounded-full", running ? "bg-route" : lastRun?.status === "failed" ? "bg-destructive" : lastRun?.status === "partial" ? "bg-caution" : "bg-success")} />
            </span>
            <span className="sr-only">Latest discovery</span>
            {running ? <span>{running}</span> : lastRun && (
              <span>Last scan {timeAgo(lastRun.completed_at ?? lastRun.started_at)} · <span className="readout">{lastRun.jobs_found}</span> found, <span className="readout">{lastRun.jobs_new}</span> new
                {lastRun.status !== "completed" && <> · <button type="button" className="font-medium text-caution underline-offset-2 hover:underline" onClick={() => navigate("/searches?tab=sources")}>some sources had trouble</button></>}
              </span>
            )}
          </span>
        ) : "Scored against your confirmed profile. Best matches first."}
        actions={<>
          <Button variant="outline" onClick={runDiscovery} disabled={discover.isPending || !!running}>{running ? <Loader2 className="animate-spin" /> : <RefreshCw />} Run discovery now</Button>
          <Button variant="ink" onClick={() => { setClip(null); setImportOpen(true); }}><Plus /> Add job</Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="outline" size="icon" aria-label="More job tools" />}><MoreHorizontal /></DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-52">
              <DropdownMenuItem onClick={() => setLinksOpen(true)}><Link2 /> Search links</DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate("/searches")}><Radar /> Saved searches</DropdownMenuItem>
              <DropdownMenuItem onClick={() => navigate("/searches?tab=sources")}><Activity /> Source health</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </>}
      />
      <JobWorkspace query={query} toolbar={toolbar}
                    sortControl={<NativeSelect className="h-7 rounded-full border-transparent bg-transparent px-2 text-[13px] text-foreground hover:bg-muted" ariaLabel="Sort" value={draft.sort ?? "score"}
                                               onChange={(v) => { const next = { ...draft, sort: v as JobQuery["sort"] }; setDraft(next); setQuery({ ...next, page: 1 }); }}
                                               options={[{ value: "score", label: "best match first" }, { value: "posted", label: "newest first" }, { value: "discovered", label: "recently added" }]} />} emptyTitle="No jobs match yet" initialDetailId={initialJob}
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

/** Jobs and internships are separate lists, each with its own count for the current filters. */
function KindTabs({ query, onChange }: { query: JobQuery; onChange: (k: "jobs" | "internships") => void }) {
  const jobs = useJobs({ ...query, kind: "jobs", page: 1, page_size: 1 });
  const interns = useJobs({ ...query, kind: "internships", page: 1, page_size: 1 });
  const active = query.kind === "internships" ? "internships" : "jobs";
  const tabs = [["jobs", "Jobs", jobs.data?.total], ["internships", "Internships", interns.data?.total]] as const;
  return (
    <div role="tablist" aria-label="Jobs or internships" className="flex w-fit shrink-0 gap-0.5 rounded-full bg-paper-sunk p-1">
      {tabs.map(([k, label, n]) => (
        <button key={k} type="button" role="tab" aria-selected={active === k} onClick={() => onChange(k)} data-testid={`kind-${k}`}
                className={cn("flex h-8 items-center gap-1.5 rounded-full px-3.5 text-[13px] font-medium transition-[background,color,box-shadow] duration-200",
                              active === k ? "bg-card text-foreground shadow-[var(--shadow-raised)]" : "text-muted-foreground hover:text-foreground")}>
          {label}
          {n !== undefined && <span className={cn("rounded-full px-1.5 text-xs tabular-nums", active === k ? "bg-route-tint text-route" : "bg-card")}>{n}</span>}
        </button>
      ))}
    </div>
  );
}

export function SavedPage() {
  return (
    <>
      <PageHeader title={<>On your <em>radar</em></>} description="Jobs you bookmarked. Shoot your shot when you're ready, or let them go." />
      <JobWorkspace query={{ view: "saved", sort: "score" }} emptyTitle="Nothing saved yet" emptyBody="Use Save on any job card to keep it here." />
    </>
  );
}

/** Page controls: where you are, previous / next, and a short run of page numbers. */
function Pager({ page, totalPages, total, pageSize, onPage, busy }: { page: number; totalPages: number; total: number; pageSize: number; onPage: (p: number) => void; busy?: boolean }) {
  const nums: (number | "…")[] = [];
  for (let p = 1; p <= totalPages; p++) {
    if (p === 1 || p === totalPages || Math.abs(p - page) <= 1) nums.push(p);
    else if (nums[nums.length - 1] !== "…") nums.push("…");
  }
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <nav aria-label="Pages" className="mt-6 flex flex-col items-center justify-between gap-3 rounded-2xl bg-card px-4 py-3 ring-1 ring-border sm:flex-row">
      <span className="text-[13px] text-muted-foreground">Showing <span className="readout text-foreground">{from}–{to}</span> of <span className="readout text-foreground">{total}</span></span>
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="sm" onClick={() => onPage(page - 1)} disabled={page <= 1 || busy}><ChevronLeft /> Previous</Button>
        {nums.map((n, i) => n === "…"
          ? <span key={`gap-${i}`} className="px-1.5 text-muted-foreground" aria-hidden>…</span>
          : <button key={n} type="button" onClick={() => onPage(n)} aria-current={n === page ? "page" : undefined} disabled={busy && n !== page}
                    className={cn("readout size-8 rounded-full text-[13px] transition-[background,color,transform] duration-200 active:scale-95",
                      n === page ? "bg-route text-primary-foreground shadow-[var(--shadow-raised)]" : "text-foreground hover:bg-muted")}>{n}</button>)}
        <Button variant="ghost" size="sm" onClick={() => onPage(page + 1)} disabled={page >= totalPages || busy}>Next <ChevronRight /></Button>
      </div>
    </nav>
  );
}
