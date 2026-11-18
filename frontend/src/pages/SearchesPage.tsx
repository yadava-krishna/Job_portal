import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Activity, Building2, CalendarClock, Check, ExternalLink, Loader2, Pause, Pencil, Play, Plus, Radar, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, Field, NativeSelect, PageHeader, PlatformBadge, TagInput } from "@/components/app/common";
import { RunSummary, SourceHealthList, StatusDot, statusTone, type DotTone } from "@/components/app/discovery";
import { CompanyMark } from "@/components/app/JobCard";
import { CareerUrlForm } from "@/components/app/CareerUrlForm";
import { SourcesPanel } from "@/components/app/SourcesPanel";
import { errorMessage } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  pollRun, useCompanyDirectory, useDeleteSearch, useInvalidateWork, usePreferences, useRunSearch, useSavedSearches, useSaveSearch,
  useSourceHealth, useSuggestedCompanies, useUnwatchCompany, useWatchCompany, useWatchlist, useWatchMany,
} from "@/services/queries";
import type { Company, DirectoryCompany, EmploymentType, SavedSearch, SavedSearchInput, SearchCriteria, SearchSource, WorkMode } from "@/types/api";

const SOURCES: { id: SearchSource; label: string; hint: string }[] = [
  { id: "greenhouse", label: "Greenhouse", hint: "Employer job boards" },
  { id: "lever", label: "Lever", hint: "Employer job boards" },
  { id: "ashby", label: "Ashby", hint: "Employer job boards" },
  { id: "smartrecruiters", label: "SmartRecruiters", hint: "Employer job boards" },
  { id: "recruitee", label: "Recruitee", hint: "Employer careers sites" },
  { id: "remote_feeds", label: "Remote job feeds", hint: "Remotive, Himalayas, RemoteOK, Arbeitnow (remote jobs open to India)" },
  { id: "adzuna_api", label: "Adzuna", hint: "Needs the server's Adzuna API key" },
];
const ATS_LABEL: Record<string, string> = { greenhouse: "Greenhouse", lever: "Lever", ashby: "Ashby", smartrecruiters: "SmartRecruiters", recruitee: "Recruitee" };
const WORK_MODES: WorkMode[] = ["Remote", "Hybrid", "On-site"];
const EMPLOYMENT: EmploymentType[] = ["Full-time", "Part-time", "Contract", "Internship", "Temporary"];
const INDUSTRIES = ["Fintech", "SaaS", "AI", "E-commerce", "Data & Analytics", "Cybersecurity", "Healthcare", "AdTech", "Media", "Travel"];

const emptyCriteria: SearchCriteria = {
  keywords: [], exclude_keywords: [], locations: [], remote_ok: true, industries: [], experience_years: null, employment_types: [],
  work_modes: [], company_ids: [], use_watchlist: true, include_suggested: true, related_titles: true, sources: ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "remote_feeds"],
  max_age_days: null,
};

function toggle<T>(list: T[], item: T): T[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

function Checks<T extends string>({ options, value, onChange, label }: { options: readonly T[] | { id: T; label: string }[]; value: T[]; onChange: (v: T[]) => void; label: string }) {
  const opts = (options as (T | { id: T; label: string })[]).map((o) => (typeof o === "string" ? { id: o, label: o } : o));
  return (
    <fieldset className="flex flex-wrap gap-2" aria-label={label}>
      {opts.map((o) => (
        <label key={o.id} className={cn("flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
          value.includes(o.id) ? "border-route/40 bg-route-tint text-route" : "bg-card hover:bg-muted")}>
          <input type="checkbox" className="sr-only" checked={value.includes(o.id)} onChange={() => onChange(toggle(value, o.id))} />
          {o.label}
        </label>
      ))}
    </fieldset>
  );
}

// ---- saved searches ------------------------------------------------------------------------------------

function SearchDialog({ open, initial, onClose }: { open: boolean; initial: SavedSearch | null; onClose: () => void }) {
  const prefs = usePreferences();
  const watchlist = useWatchlist();
  const save = useSaveSearch();
  const run = useRunSearch();
  const navigate = useNavigate();
  const [form, setForm] = useState<SavedSearchInput>(() => initial
    ? { name: initial.name, criteria: initial.criteria, schedule: initial.schedule, min_match_score: initial.min_match_score, enabled: initial.enabled }
    : { name: "", criteria: emptyCriteria, schedule: "daily", min_match_score: null, enabled: true });
  const c = form.criteria;
  const setC = <K extends keyof SearchCriteria>(k: K, v: SearchCriteria[K]) => setForm((f) => ({ ...f, criteria: { ...f.criteria, [k]: v } }));

  const submit = (e: FormEvent, andRun: boolean) => {
    e.preventDefault();
    if (!c.sources.length) return toast.error("Choose at least one source.");
    save.mutate({ id: initial?.id, body: form }, {
      onSuccess: (saved) => {
        toast.success(initial ? "Search updated" : "Search saved");
        onClose();
        if (andRun) run.mutate(saved.id, { onSuccess: () => { toast("Search started. Results appear in Discover."); navigate(`/discover?search=${saved.id}`); } });
      },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{initial ? "Edit saved search" : "New saved search"}</DialogTitle>
          <DialogDescription>Scans the official job boards of your companies (and Adzuna, if enabled). Empty fields fall back to your job preferences.</DialogDescription>
        </DialogHeader>
        <form onSubmit={(e) => submit(e, false)} className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" htmlFor="ss-name" className="sm:col-span-2">
            <Input id="ss-name" required maxLength={100} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. AR roles in Bengaluru" />
          </Field>
          <Field label="Job titles or keywords" htmlFor="ss-kw" hint={c.keywords.length ? "A job matches if its title contains every word of one entry." : `Empty: uses your preferred titles${prefs.data?.job_titles?.length ? ` (${prefs.data.job_titles.slice(0, 3).join(", ")})` : ""}.`}>
            <TagInput id="ss-kw" value={c.keywords} onChange={(v) => setC("keywords", v)} placeholder="Accounts Receivable, AR Analyst…" suggestions={prefs.data?.job_titles ?? []} />
          </Field>
          <label className="flex items-start gap-2 text-sm sm:col-span-2"><input type="checkbox" className="mt-1 accent-primary" checked={c.related_titles} onChange={(e) => setC("related_titles", e.target.checked)} />
            <span>Also match related titles <span className="text-muted-foreground">(e.g. “Collections Analyst” or “Accountant” for an Accounts Receivable role). They're ranked by your match score.</span></span></label>
          <Field label="Exclude titles containing" htmlFor="ss-ex">
            <TagInput id="ss-ex" value={c.exclude_keywords} onChange={(v) => setC("exclude_keywords", v)} placeholder="Intern, Director…" />
          </Field>
          <Field label="Locations" htmlFor="ss-loc" hint="Cities (aliases like Bangalore/Bengaluru are understood) or “India”. Empty: your preferred locations.">
            <TagInput id="ss-loc" value={c.locations} onChange={(v) => setC("locations", v)} placeholder="Bengaluru, Hyderabad…" suggestions={prefs.data?.locations ?? []} />
          </Field>
          <Field label="Industries" htmlFor="ss-ind" hint="Applies where the company's industry is known.">
            <TagInput id="ss-ind" value={c.industries} onChange={(v) => setC("industries", v)} placeholder="Fintech…" suggestions={INDUSTRIES} />
          </Field>
          <Field label="Your years of experience" htmlFor="ss-exp" hint="Skips roles needing much more, or far less, experience.">
            <Input id="ss-exp" type="number" min={0} max={60} step={0.5} value={c.experience_years ?? ""} onChange={(e) => setC("experience_years", e.target.value === "" ? null : Number(e.target.value))} />
          </Field>
          <Field label="Skip postings older than (days)" htmlFor="ss-age" hint="Jobs with unknown posting dates are kept and labelled.">
            <Input id="ss-age" type="number" min={1} max={365} value={c.max_age_days ?? ""} onChange={(e) => setC("max_age_days", e.target.value === "" ? null : Number(e.target.value))} />
          </Field>
          <Field label="Work mode" className="sm:col-span-2" hint="None selected: any.">
            <div className="flex flex-wrap items-center gap-3">
              <Checks label="Work mode" options={WORK_MODES} value={c.work_modes} onChange={(v) => setC("work_modes", v)} />
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-primary" checked={c.remote_ok} onChange={(e) => setC("remote_ok", e.target.checked)} /> Include remote roles open to India</label>
            </div>
          </Field>
          <Field label="Employment type" className="sm:col-span-2" hint="None selected: any.">
            <Checks label="Employment type" options={EMPLOYMENT} value={c.employment_types} onChange={(v) => setC("employment_types", v)} />
          </Field>
          <Field label="Sources" className="sm:col-span-2">
            <Checks label="Sources" options={SOURCES.map((s) => ({ id: s.id, label: `${s.label} · ${s.hint}` }))} value={c.sources} onChange={(v) => setC("sources", v)} />
          </Field>
          <Field label="Companies" className="sm:col-span-2" hint={!watchlist.data?.length ? "Your watchlist is empty: add companies on the Companies tab." : undefined}>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-primary" checked={c.include_suggested} onChange={(e) => setC("include_suggested", e.target.checked)} /> JobPilot's suggested employers (verified boards, hiring in India)</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-primary" checked={c.use_watchlist} onChange={(e) => setC("use_watchlist", e.target.checked)} /> All companies on my watchlist ({watchlist.data?.length ?? 0})</label>
            {!c.use_watchlist && (
              <div className="mt-2 grid max-h-40 gap-1 overflow-y-auto rounded-lg border p-2 sm:grid-cols-2">
                {(watchlist.data ?? []).map((co) => (
                  <label key={co.id} className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-primary" checked={c.company_ids.includes(co.id)} onChange={() => setC("company_ids", toggle(c.company_ids, co.id))} /> {co.name} <span className="text-xs text-muted-foreground">{ATS_LABEL[co.ats]}</span></label>
                ))}
              </div>
            )}
          </Field>
          <Field label="Schedule" htmlFor="ss-sched">
            <NativeSelect id="ss-sched" value={form.schedule} onChange={(v) => setForm({ ...form, schedule: v as SavedSearchInput["schedule"] })}
                          options={[{ value: "daily", label: "Daily" }, { value: "weekly", label: "Weekly" }, { value: "manual", label: "Only when I run it" }]} className="w-full" />
          </Field>
          <Field label="Notify me at match ≥ (%)" htmlFor="ss-min" hint={`Empty: your preference (${prefs.data?.min_match_score ?? 70}%).`}>
            <Input id="ss-min" type="number" min={0} max={100} value={form.min_match_score ?? ""} onChange={(e) => setForm({ ...form, min_match_score: e.target.value === "" ? null : Number(e.target.value) })} />
          </Field>
          <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" className="accent-primary" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> Enabled (scheduled runs happen only when enabled)</label>
          <DialogFooter className="sm:col-span-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="outline" disabled={save.isPending}>Save</Button>
            <Button type="button" disabled={save.isPending} onClick={(e) => submit(e as unknown as FormEvent, true)}>{save.isPending ? <Loader2 className="animate-spin" /> : <Play />} Save & run now</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function criteriaSummary(s: SavedSearch): string {
  const c = s.criteria;
  const parts = [c.keywords.length ? c.keywords.join(", ") : "Your preferred titles", c.locations.length ? c.locations.join(", ") : "your locations"];
  if (c.industries.length) parts.push(c.industries.join(", "));
  if (c.include_suggested) parts.push("suggested employers");
  return parts.join(" · ");
}

function scheduleText(s: SavedSearch): string {
  if (!s.enabled) return "Not scheduled";
  return s.schedule === "manual" ? "Runs when you start it" : s.schedule === "daily" ? "Runs daily" : "Runs weekly";
}

const sourceLabel = (src: SearchSource) => (src === "adzuna_api" ? "Adzuna" : src === "remote_feeds" ? "Remote feeds" : ATS_LABEL[src]);

function SearchRow({ s, onEdit }: { s: SavedSearch; onEdit: () => void }) {
  const run = useRunSearch();
  const del = useDeleteSearch();
  const invalidate = useInvalidateWork();
  const navigate = useNavigate();
  const [progress, setProgress] = useState<string | null>(null);
  const last = s.last_run;
  const lastTone = progress ? "active" : last ? statusTone(last.status) : "idle";

  const runNow = () => run.mutate(s.id, {
    onSuccess: async (r) => {
      setProgress("Checking job boards…");
      const done = await pollRun(r.id, (x) => setProgress(x.status === "running" ? x.summary ?? "Checking job boards…" : null), 300_000);
      setProgress(null);
      void invalidate();
      if (done.status === "failed") toast.error(done.summary ?? "The search could not run.");
      else if (done.jobs_found === 0) toast.info(done.summary ?? "Nothing matched right now.");
      else toast.success(`${done.jobs_new} new job${done.jobs_new === 1 ? "" : "s"}, ${done.duplicates} already in your feed`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <li className={cn("group/search px-4 py-3.5 transition-colors duration-150 hover:bg-paper-sunk/50 sm:px-5", !s.enabled && "bg-paper-sunk/30")}>
      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <div className="flex min-w-0 flex-1 gap-3.5">
          <span aria-hidden className={cn("mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl", s.enabled ? "bg-route-tint text-route" : "bg-muted text-muted-foreground")}>
            {s.enabled ? <Radar className="size-[18px]" /> : <Pause className="size-[18px]" />}
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="flex flex-wrap items-center gap-x-2 gap-y-1 font-display text-[15.5px] font-bold tracking-[-0.01em] text-heading">
              {s.name}
              {s.origin === "starter" && <span className="rounded-full bg-lavender px-2 py-0.5 font-sans text-[11px] font-medium text-violet" title="Created automatically from your preferences; titles and locations follow your preferences.">From your profile</span>}
              {!s.enabled && <span className="rounded-full bg-muted px-2 py-0.5 font-sans text-[11px] font-medium text-muted-foreground">Paused</span>}
            </h3>
            <p className="mt-0.5 truncate text-[13px] text-muted-foreground" title={criteriaSummary(s)}>{criteriaSummary(s)}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5"><CalendarClock className="size-3.5" aria-hidden />{scheduleText(s)}{s.enabled && s.next_run_at ? ` · next ${formatDate(s.next_run_at, true)}` : ""}</span>
              <span className="inline-flex items-center gap-1.5" title={last?.summary ?? undefined}>
                <StatusDot tone={lastTone} />
                {progress ? "Running now" : s.last_run_at ? `Last run ${timeAgo(s.last_run_at)}` : "Never run"}
              </span>
              {last && last.status !== "running" && !progress && (
                <span><span className="readout font-medium text-foreground">{last.jobs_found}</span> matched · <span className="readout font-medium text-foreground">{last.jobs_new}</span> new · <span className="readout font-medium text-foreground">{last.jobs_matched}</span> shortlisted</span>
              )}
              <span className="flex flex-wrap items-center gap-1" title={s.criteria.sources.map(sourceLabel).join(", ")}>
                {s.criteria.sources.slice(0, 3).map((src) => <PlatformBadge key={src} platform={sourceLabel(src)} />)}
                {s.criteria.sources.length > 3 && <span className="text-muted-foreground">+{s.criteria.sources.length - 3} more</span>}
              </span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 sm:pl-[3.375rem] md:pl-0">
          <Button size="sm" variant="secondary" onClick={runNow} disabled={run.isPending || !!progress}>{progress ? <Loader2 className="animate-spin" /> : <Play />} Run now</Button>
          <Button size="sm" variant="ghost" onClick={() => navigate(`/discover?search=${s.id}`)}><Search /> View matches</Button>
          <Button size="icon-sm" variant="ghost" onClick={onEdit} aria-label={`Edit ${s.name}`} title="Edit"><Pencil /></Button>
          <Button size="icon-sm" variant="ghost" className="hover:text-destructive" aria-label={`Delete ${s.name}`} title="Delete"
                  onClick={() => { if (confirm(`Delete "${s.name}"? Jobs it found stay in your feed.`)) del.mutate(s.id, { onError: (e) => toast.error(errorMessage(e)) }); }}><Trash2 /></Button>
        </div>
      </div>
      {progress && <p className="mt-2 flex items-center gap-2 text-sm text-route sm:pl-[3.375rem] animate-in fade-in-0 duration-200"><Loader2 className="size-4 animate-spin" /> {progress}</p>}
      {last && !progress && last.status !== "running" && last.status !== "completed" && (
        <div className="mt-2.5 rounded-xl bg-paper-sunk p-3 md:ml-[3.375rem]"><RunSummary run={last} /></div>
      )}
    </li>
  );
}

function SearchesTab() {
  const searches = useSavedSearches();
  const [editing, setEditing] = useState<SavedSearch | null>(null);
  const [open, setOpen] = useState(false);
  const list = searches.data ?? [];
  const active = list.filter((s) => s.enabled).length;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] text-muted-foreground">
          {list.length ? <><span className="readout font-medium text-foreground">{active}</span> of <span className="readout">{list.length}</span> searches running on a schedule. New matches land in Discover.</> : "Searches run on a schedule and send new matches to Discover."}
        </p>
        <Button onClick={() => { setEditing(null); setOpen(true); }}><Plus /> New search</Button>
      </div>
      {searches.isLoading ? <Skeleton className="h-40 rounded-2xl" /> : !list.length ? (
        <EmptyState icon={<Radar className="size-8" />} title="No saved searches yet. Let's set one up.">
          Create one to scan your companies' official job boards on a schedule. New matches are scored against your resume and land in Discover.
        </EmptyState>
      ) : (
        <ul className="divide-y overflow-hidden rounded-2xl bg-card ring-1 ring-border">
          {list.map((s) => <SearchRow key={s.id} s={s} onEdit={() => { setEditing(s); setOpen(true); }} />)}
        </ul>
      )}
      {open && <SearchDialog open={open} initial={editing} onClose={() => setOpen(false)} />}
    </div>
  );
}

// ---- companies --------------------------------------------------------------------------------------------

const statusText: Record<string, [string, DotTone, string]> = {
  ok: ["Board OK", "healthy", "text-success"],
  empty: ["No open jobs", "idle", "text-muted-foreground"],
  not_found: ["Board not found", "failing", "text-destructive"],
  error: ["Couldn't reach board", "attention", "text-caution"],
};

function Panel({ title, count, actions, children, className }: { title: ReactNode; count?: number; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("rounded-2xl bg-card ring-1 ring-border", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
        <h3 className="flex items-center gap-2 font-display text-[15px] font-bold tracking-[-0.01em] text-heading">
          {title}{count != null && <span className="readout rounded-full bg-paper-sunk px-2 py-px text-[11px] font-medium text-muted-foreground ring-1 ring-inset ring-border">{count}</span>}
        </h3>
        {actions}
      </div>
      {children}
    </section>
  );
}

function CompanyRow({ c }: { c: Company }) {
  const unwatch = useUnwatchCompany();
  const [label, tone, cls] = c.last_status ? statusText[c.last_status] : ["Not checked yet", "idle" as DotTone, "text-muted-foreground"];
  return (
    <li className="flex items-center gap-3 px-4 py-2.5 text-sm transition-colors duration-150 hover:bg-paper-sunk/50">
      <CompanyMark name={c.name} className="size-9 text-[12px]" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="font-medium text-foreground">{c.name}</span> <PlatformBadge platform={ATS_LABEL[c.ats]} />
          {c.industry && <span className="text-xs text-muted-foreground">{c.industry}</span>}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-xs" title={c.last_error ?? undefined}>
          <StatusDot tone={tone} />
          <span className={cn("font-medium", cls)}>{label}</span>
          <span className="text-muted-foreground">
            {c.job_count != null && c.last_status === "ok" ? <> · <span className="readout">{c.job_count}</span> open jobs</> : ""}{c.last_fetched_at ? ` · checked ${timeAgo(c.last_fetched_at)}` : ""}
          </span>
        </div>
      </div>
      <div className="flex shrink-0 gap-0.5">
        <Button size="icon-sm" variant="ghost" render={<a href={c.board_url} target="_blank" rel="noopener noreferrer" />} aria-label={`Open ${c.name} job board`} title="Open job board"><ExternalLink /></Button>
        <Button size="icon-sm" variant="ghost" className="hover:text-destructive" aria-label={`Stop watching ${c.name}`} title="Stop watching" onClick={() => unwatch.mutate(c.id, { onError: (e) => toast.error(errorMessage(e)) })}><Trash2 /></Button>
      </div>
    </li>
  );
}

function DirectoryList({ items, empty }: { items: DirectoryCompany[] | undefined; empty: string }) {
  const watch = useWatchCompany();
  if (!items) return <div className="p-4"><Skeleton className="h-24 rounded-xl" /></div>;
  if (!items.length) return <p className="px-4 py-6 text-center text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y">
      {items.map((d) => (
        <li key={`${d.ats}:${d.token}`} className="flex items-center gap-3 px-4 py-2.5 text-sm transition-colors duration-150 hover:bg-paper-sunk/50">
          <CompanyMark name={d.name} className="size-8 text-[11px]" />
          <span className="min-w-0 flex-1">
            <span className="font-medium">{d.name}</span> <PlatformBadge platform={ATS_LABEL[d.ats]} />{d.industry && <span className="ml-1 text-xs text-muted-foreground">{d.industry}</span>}
          </span>
          {d.watched ? <span className="inline-flex items-center gap-1 text-xs font-medium text-violet"><Check className="size-3.5" aria-hidden /> Watching</span> : (
            <Button size="sm" variant="outline" disabled={watch.isPending}
                    onClick={() => watch.mutate({ ats: d.ats, token: d.token, name: d.name }, { onSuccess: () => toast.success(`Watching ${d.name}. On your radar ✨`), onError: (e) => toast.error(errorMessage(e)) })}>
              <Plus /> Watch
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}

function CompaniesTab() {
  const watchlist = useWatchlist();
  const suggested = useSuggestedCompanies();
  const watch = useWatchCompany();
  const watchMany = useWatchMany();
  const [url, setUrl] = useState("");
  const [q, setQ] = useState("");
  const [ats, setAts] = useState("");
  const directory = useCompanyDirectory(q, ats);
  const unwatched = (suggested.data ?? []).filter((s) => !s.watched);
  const searching = q.trim().length >= 2;
  const list = watchlist.data ?? [];
  const problems = list.filter((c) => c.last_status === "not_found" || c.last_status === "error").length;

  const addUrl = (e: FormEvent) => {
    e.preventDefault();
    watch.mutate({ url }, { onSuccess: (c) => { toast.success(`Watching ${c.name} (${c.job_count ?? 0} open jobs)`); setUrl(""); }, onError: (err) => toast.error(errorMessage(err)) });
  };

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        <Panel title="Your watchlist" count={list.length}
               actions={list.length > 0 && <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><StatusDot tone={problems ? "attention" : "healthy"} />{problems ? `${problems} board${problems === 1 ? "" : "s"} need${problems === 1 ? "s" : ""} attention` : "All boards reachable"}</span>}>
          <div className="space-y-2 border-b p-3">
            <form onSubmit={addUrl} className="flex gap-2">
              <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.company.com/careers or https://jobs.lever.co/company" aria-label="Careers page or job board URL" required />
              <Button type="submit" disabled={watch.isPending}>{watch.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Add</Button>
            </form>
            <p className="px-1 text-[11.5px] leading-relaxed text-muted-foreground">Paste the company's careers page and JobPilot finds the job board it uses, or paste a Greenhouse, Lever, Ashby, SmartRecruiters or Recruitee link directly. The board is checked through the provider's official API before it's added. Careers sites on other systems (for example Workday) can't be searched automatically.</p>
          </div>
          {watchlist.isLoading ? <div className="p-4"><Skeleton className="h-24 rounded-xl" /></div> : !list.length
            ? <p className="px-4 py-8 text-center text-sm text-muted-foreground"><span className="block font-medium text-foreground">No companies yet.</span>Add suggested ones or search the directory.</p>
            : <ul className="max-h-[26rem] divide-y overflow-y-auto">{list.map((c) => <CompanyRow key={c.id} c={c} />)}</ul>}
        </Panel>
        <section className="rounded-2xl bg-card p-4 ring-1 ring-border"><CareerUrlForm onSuccess={() => void watchlist.refetch()} /></section>
      </div>
      <Panel title={searching ? "Company directory" : "Suggested employers hiring in India"} count={searching ? directory.data?.length : suggested.data?.length}
             actions={!searching && unwatched.length > 0 && (
               <Button size="sm" variant="outline" disabled={watchMany.isPending}
                       onClick={() => watchMany.mutate(unwatched.map((s) => ({ ats: s.ats, token: s.token })), { onSuccess: (r) => toast.success(`Watching ${r.length} companies`), onError: (e) => toast.error(errorMessage(e)) })}>
                 Watch all ({unwatched.length})
               </Button>
             )}>
        <div className="flex gap-2 border-b p-3">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the company directory" aria-label="Search companies" className="pl-9" />
          </div>
          <NativeSelect ariaLabel="Job board type" value={ats} onChange={setAts} options={[{ value: "", label: "All boards" }, { value: "greenhouse", label: "Greenhouse" }, { value: "lever", label: "Lever" }, { value: "ashby", label: "Ashby" }, { value: "smartrecruiters", label: "SmartRecruiters" }, { value: "recruitee", label: "Recruitee" }]} />
        </div>
        <div className="max-h-[30rem] overflow-y-auto">
          {searching
            ? <DirectoryList items={directory.data} empty="No matches. Try the company's careers-page link instead." />
            : <DirectoryList items={suggested.data} empty="No suggestions." />}
        </div>
        <p className="border-t px-4 py-2.5 text-[11px] text-muted-foreground">Directory data includes board lists from JobSync (MIT licence). Some boards may have moved; JobPilot checks each one before adding it.</p>
      </Panel>
    </div>
  );
}

function SourcesTab() {
  const health = useSourceHealth();
  if (health.isLoading) return <Skeleton className="h-64 rounded-2xl" />;
  if (health.isError || !health.data) return <p className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{errorMessage(health.error)}</p>;
  const d = health.data;
  const count = (tone: DotTone) => d.sources.filter((s) => statusTone(s.connection) === tone).length;
  const healthy = count("healthy"), attention = count("attention"), failing = count("failing");
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Panel title="Latest discovery run">
          <div className="p-4">{d.last_run ? <RunSummary run={d.last_run} /> : <p className="text-sm text-muted-foreground">Discovery hasn't run yet. Use “Run discovery now” on Discover.</p>}</div>
        </Panel>
        <Panel title="At a glance">
          <div className="grid grid-cols-3 divide-x">
            {([["healthy", healthy, "Healthy"], ["attention", attention, "Need attention"], ["failing", failing, "Failing"]] as const).map(([tone, n, label]) => (
              <div key={tone} className="px-4 py-3.5">
                <div className="readout text-[24px] leading-none font-semibold text-heading">{n}</div>
                <div className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground"><StatusDot tone={n ? tone : "idle"} />{label}</div>
              </div>
            ))}
          </div>
          <p className="border-t px-4 py-2.5 text-xs text-muted-foreground"><span className="readout">{d.enabled_searches}</span> of <span className="readout">{d.saved_searches}</span> saved searches enabled. LinkedIn, Indeed and Naukri are never scraped: use the clipper, job links or their alert emails.</p>
        </Panel>
      </div>
      <section className="space-y-2">
        <h3 className="flex items-center gap-2 px-1 font-display text-[15px] font-bold tracking-[-0.01em] text-heading">
          Discovery health <span className="readout rounded-full bg-paper-sunk px-2 py-px text-[11px] font-medium text-muted-foreground ring-1 ring-inset ring-border">{d.sources.length}</span>
        </h3>
        <SourceHealthList sources={d.sources} />
      </section>
      <SourcesPanel />
    </div>
  );
}

export function SearchesPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "searches";
  const searches = useSavedSearches();
  const watchlist = useWatchlist();
  return (
    <>
      <PageHeader title={<>Searches <em>&</em> companies</>}
                  description="Saved searches scan employers' official job boards (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee), public remote-job feeds (Remotive, Himalayas, RemoteOK, Arbeitnow) and, optionally, Adzuna. Nothing is applied for you." />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: String(v) }, { replace: true })}>
        <TabsList className="max-w-full justify-start overflow-x-auto">
          <TabsTrigger value="searches"><Radar className="size-4" /> Saved searches<TabCount n={searches.data?.length} /></TabsTrigger>
          <TabsTrigger value="companies"><Building2 className="size-4" /> Companies<TabCount n={watchlist.data?.length} /></TabsTrigger>
          <TabsTrigger value="sources"><Activity className="size-4" /> Source health</TabsTrigger>
        </TabsList>
        <TabsContent value="sources" className="pt-3"><SourcesTab /></TabsContent>
        <TabsContent value="searches" className="pt-3"><SearchesTab /></TabsContent>
        <TabsContent value="companies" className="pt-3"><CompaniesTab /></TabsContent>
      </Tabs>
    </>
  );
}

function TabCount({ n }: { n: number | undefined }) {
  if (!n) return null;
  return <span aria-hidden className="readout ml-0.5 rounded-full bg-paper-sunk px-1.5 text-[10.5px] leading-[18px] font-semibold text-muted-foreground ring-1 ring-inset ring-border">{n}</span>;
}
