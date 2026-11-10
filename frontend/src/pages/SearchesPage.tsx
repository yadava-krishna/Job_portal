import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Activity, Building2, ExternalLink, Loader2, Pencil, Play, Plus, Radar, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, Field, NativeSelect, PageHeader, PlatformBadge, TagInput } from "@/components/app/common";
import { RunSummary, SourceHealthList } from "@/components/app/discovery";
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
  { id: "adzuna_api", label: "Adzuna", hint: "Needs the server's Adzuna API key" },
];
const ATS_LABEL: Record<string, string> = { greenhouse: "Greenhouse", lever: "Lever", ashby: "Ashby", smartrecruiters: "SmartRecruiters", recruitee: "Recruitee" };
const WORK_MODES: WorkMode[] = ["Remote", "Hybrid", "On-site"];
const EMPLOYMENT: EmploymentType[] = ["Full-time", "Part-time", "Contract", "Internship", "Temporary"];
const INDUSTRIES = ["Fintech", "SaaS", "AI", "E-commerce", "Data & Analytics", "Cybersecurity", "Healthcare", "AdTech", "Media", "Travel"];

const emptyCriteria: SearchCriteria = {
  keywords: [], exclude_keywords: [], locations: [], remote_ok: true, industries: [], experience_years: null, employment_types: [],
  work_modes: [], company_ids: [], use_watchlist: true, include_suggested: true, related_titles: true, sources: ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee"],
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
        <label key={o.id} className={cn("flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium",
          value.includes(o.id) ? "border-primary bg-primary/10 text-primary" : "hover:bg-muted")}>
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

function SearchCard({ s, onEdit }: { s: SavedSearch; onEdit: () => void }) {
  const run = useRunSearch();
  const del = useDeleteSearch();
  const invalidate = useInvalidateWork();
  const navigate = useNavigate();
  const [progress, setProgress] = useState<string | null>(null);
  const last = s.last_run;

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
    <Card className="gap-3 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold">{s.name}
            {s.origin === "starter" && <span className="ml-2 rounded bg-primary/10 px-1.5 py-0.5 text-xs font-normal text-primary" title="Created automatically from your preferences; titles and locations follow your preferences.">From your profile</span>}
            {!s.enabled && <span className="ml-1 rounded bg-muted px-1.5 py-0.5 text-xs font-normal text-muted-foreground">Paused</span>}</h3>
          <p className="text-sm text-muted-foreground">{criteriaSummary(s)}</p>
          <div className="mt-1 flex flex-wrap gap-1">{s.criteria.sources.map((src) => <PlatformBadge key={src} platform={src === "adzuna_api" ? "Adzuna" : ATS_LABEL[src]} />)}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={runNow} disabled={run.isPending || !!progress}>{progress ? <Loader2 className="animate-spin" /> : <Play />} Run now</Button>
          <Button size="sm" variant="outline" onClick={() => navigate(`/discover?search=${s.id}`)}><Search /> View matches</Button>
          <Button size="sm" variant="ghost" onClick={onEdit} aria-label={`Edit ${s.name}`}><Pencil /></Button>
          <Button size="sm" variant="ghost" aria-label={`Delete ${s.name}`} onClick={() => { if (confirm(`Delete "${s.name}"? Jobs it found stay in your feed.`)) del.mutate(s.id, { onError: (e) => toast.error(errorMessage(e)) }); }}><Trash2 /></Button>
        </div>
      </div>
      <div className="grid gap-x-6 gap-y-1 text-sm text-muted-foreground sm:grid-cols-3">
        <span>Schedule: <strong className="text-foreground">{s.schedule === "manual" ? "manual" : s.schedule}</strong>{s.next_run_at ? ` · next ${formatDate(s.next_run_at, true)}` : ""}</span>
        <span>Last run: {s.last_run_at ? timeAgo(s.last_run_at) : "never"}</span>
        {last && last.status !== "running" && <span>{last.jobs_found} matched · {last.jobs_new} new · {last.jobs_matched} shortlisted</span>}
      </div>
      {progress && <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> {progress}</p>}
      {last && !progress && last.status !== "running" && <RunSummary run={last} compact={last.status === "completed"} />}
    </Card>
  );
}

function SearchesTab() {
  const searches = useSavedSearches();
  const [editing, setEditing] = useState<SavedSearch | null>(null);
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => { setEditing(null); setOpen(true); }}><Plus /> New search</Button></div>
      {searches.isLoading ? <Skeleton className="h-32" /> : !searches.data?.length ? (
        <EmptyState icon={<Radar className="size-8" />} title="No saved searches yet">
          Create one to scan your companies' official job boards on a schedule. New matches are scored against your resume and land in Discover.
        </EmptyState>
      ) : searches.data.map((s) => <SearchCard key={s.id} s={s} onEdit={() => { setEditing(s); setOpen(true); }} />)}
      {open && <SearchDialog open={open} initial={editing} onClose={() => setOpen(false)} />}
    </div>
  );
}

// ---- companies --------------------------------------------------------------------------------------------

const statusText: Record<string, [string, string]> = {
  ok: ["Board OK", "text-emerald-700 dark:text-emerald-300"],
  empty: ["No open jobs", "text-muted-foreground"],
  not_found: ["Board not found", "text-rose-700 dark:text-rose-300"],
  error: ["Couldn't reach board", "text-amber-700 dark:text-amber-300"],
};

function CompanyRow({ c }: { c: Company }) {
  const unwatch = useUnwatchCompany();
  const [label, tone] = c.last_status ? statusText[c.last_status] : ["Not checked yet", "text-muted-foreground"];
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
      <div className="min-w-0">
        <span className="font-medium">{c.name}</span> <PlatformBadge platform={ATS_LABEL[c.ats]} />
        {c.industry && <span className="ml-1 text-xs text-muted-foreground">{c.industry}</span>}
        <div className={cn("text-xs", tone)} title={c.last_error ?? undefined}>
          {label}{c.job_count != null && c.last_status === "ok" ? ` · ${c.job_count} open jobs` : ""}{c.last_fetched_at ? ` · checked ${timeAgo(c.last_fetched_at)}` : ""}
        </div>
      </div>
      <div className="flex gap-1">
        <Button size="sm" variant="ghost" render={<a href={c.board_url} target="_blank" rel="noopener noreferrer" />} aria-label={`Open ${c.name} job board`}><ExternalLink /></Button>
        <Button size="sm" variant="ghost" aria-label={`Stop watching ${c.name}`} onClick={() => unwatch.mutate(c.id, { onError: (e) => toast.error(errorMessage(e)) })}><Trash2 /></Button>
      </div>
    </li>
  );
}

function DirectoryList({ items, empty }: { items: DirectoryCompany[] | undefined; empty: string }) {
  const watch = useWatchCompany();
  if (!items) return <Skeleton className="h-24" />;
  if (!items.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y rounded-lg border">
      {items.map((d) => (
        <li key={`${d.ats}:${d.token}`} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
          <span className="min-w-0">{d.name} <PlatformBadge platform={ATS_LABEL[d.ats]} />{d.industry && <span className="ml-1 text-xs text-muted-foreground">{d.industry}</span>}</span>
          {d.watched ? <span className="text-xs text-muted-foreground">Watching</span> : (
            <Button size="sm" variant="outline" disabled={watch.isPending}
                    onClick={() => watch.mutate({ ats: d.ats, token: d.token, name: d.name }, { onSuccess: () => toast.success(`Watching ${d.name}`), onError: (e) => toast.error(errorMessage(e)) })}>
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

  const addUrl = (e: FormEvent) => {
    e.preventDefault();
    watch.mutate({ url }, { onSuccess: (c) => { toast.success(`Watching ${c.name} (${c.job_count ?? 0} open jobs)`); setUrl(""); }, onError: (err) => toast.error(errorMessage(err)) });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
        <CareerUrlForm onSuccess={() => void watchlist.refetch()} />
        <Card className="gap-3 p-4">
          <h3 className="font-semibold">Add a company by its careers page or job-board link</h3>
          <form onSubmit={addUrl} className="flex gap-2">
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.company.com/careers or https://jobs.lever.co/company" aria-label="Careers page or job board URL" required />
            <Button type="submit" disabled={watch.isPending}>{watch.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Add</Button>
          </form>
          <p className="text-xs text-muted-foreground">Paste the company's careers page and JobPilot finds the job board it uses, or paste a Greenhouse, Lever, Ashby, SmartRecruiters or Recruitee link directly. The board is checked through the provider's official API before it's added. Careers sites on other systems (for example Workday) can't be searched automatically.</p>
        </Card>
        <Card className="gap-3 p-4">
          <h3 className="font-semibold">Your watchlist ({watchlist.data?.length ?? 0})</h3>
          {watchlist.isLoading ? <Skeleton className="h-24" /> : !watchlist.data?.length
            ? <p className="text-sm text-muted-foreground">No companies yet. Add suggested ones or search the directory.</p>
            : <ul className="divide-y rounded-lg border">{watchlist.data.map((c) => <CompanyRow key={c.id} c={c} />)}</ul>}
        </Card>
      </div>
      <div className="space-y-4">
        <Card className="gap-3 p-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-semibold">Suggested employers hiring in India</h3>
            {unwatched.length > 0 && (
              <Button size="sm" variant="outline" disabled={watchMany.isPending}
                      onClick={() => watchMany.mutate(unwatched.map((s) => ({ ats: s.ats, token: s.token })), { onSuccess: (r) => toast.success(`Watching ${r.length} companies`), onError: (e) => toast.error(errorMessage(e)) })}>
                Watch all ({unwatched.length})
              </Button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto"><DirectoryList items={suggested.data} empty="No suggestions." /></div>
        </Card>
        <Card className="gap-3 p-4">
          <h3 className="font-semibold">Search the company directory</h3>
          <div className="flex gap-2">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Company name" aria-label="Search companies" />
            <NativeSelect ariaLabel="Job board type" value={ats} onChange={setAts} options={[{ value: "", label: "All boards" }, { value: "greenhouse", label: "Greenhouse" }, { value: "lever", label: "Lever" }, { value: "ashby", label: "Ashby" }, { value: "smartrecruiters", label: "SmartRecruiters" }, { value: "recruitee", label: "Recruitee" }]} />
          </div>
          {q.trim().length >= 2 && <div className="max-h-80 overflow-y-auto"><DirectoryList items={directory.data} empty="No matches. Try the company's careers-page link instead." /></div>}
          <p className="text-xs text-muted-foreground">Directory data includes board lists from JobSync (MIT licence). Some boards may have moved; JobPilot checks each one before adding it.</p>
        </Card>
      </div>
    </div>
  );
}

function SourcesTab() {
  const health = useSourceHealth();
  if (health.isLoading) return <Skeleton className="h-64" />;
  if (health.isError || !health.data) return <p className="text-sm text-destructive">{errorMessage(health.error)}</p>;
  const d = health.data;
  return (
    <div className="space-y-6">
      <Card className="gap-3 p-4">
        <h3 className="font-semibold">Latest discovery run</h3>
        {d.last_run ? <RunSummary run={d.last_run} /> : <p className="text-sm text-muted-foreground">Discovery hasn't run yet. Use “Run discovery now” on Discover.</p>}
      </Card>
      <Card className="gap-3 p-4">
        <div>
          <h3 className="font-semibold">Discovery health</h3>
          <p className="text-sm text-muted-foreground">{d.enabled_searches} of {d.saved_searches} saved searches enabled. LinkedIn, Indeed and Naukri are never scraped: use the clipper, job links or their alert emails.</p>
        </div>
        <SourceHealthList sources={d.sources} />
      </Card>
      <SourcesPanel />
    </div>
  );
}

export function SearchesPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "searches";
  return (
    <>
      <PageHeader title="Searches & companies"
                  description="Saved searches scan employers' official job boards (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee) and, optionally, Adzuna. Nothing is applied for you." />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: String(v) }, { replace: true })}>
        <TabsList>
          <TabsTrigger value="searches"><Radar className="size-4" /> Saved searches</TabsTrigger>
          <TabsTrigger value="companies"><Building2 className="size-4" /> Companies</TabsTrigger>
          <TabsTrigger value="sources"><Activity className="size-4" /> Source health</TabsTrigger>
        </TabsList>
        <TabsContent value="sources" className="pt-4"><SourcesTab /></TabsContent>
        <TabsContent value="searches" className="pt-4"><SearchesTab /></TabsContent>
        <TabsContent value="companies" className="pt-4"><CompaniesTab /></TabsContent>
      </Tabs>
    </>
  );
}
