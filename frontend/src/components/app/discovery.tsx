import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Bell, CheckCircle2, CircleSlash, Loader2, Radar, SearchX, Settings2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatDate, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useMarkNotifications, useNotifications } from "@/services/queries";
import type { DiscoveryRun, SourceHealth, SourceResult, SourceResultStatus } from "@/types/api";

const resultTone: Record<SourceResultStatus, [string, string]> = {
  ok: ["Found jobs", "text-emerald-700 dark:text-emerald-300"],
  empty: ["Reached, no matches", "text-sky-700 dark:text-sky-300"],
  partial: ["Partly failed", "text-amber-700 dark:text-amber-300"],
  failed: ["Failed", "text-rose-700 dark:text-rose-300"],
  not_configured: ["Not configured", "text-muted-foreground"],
  disabled: ["Turned off", "text-muted-foreground"],
  pending: ["Running", "text-muted-foreground"],
};

const runStatusText: Record<DiscoveryRun["status"], string> = {
  running: "Running",
  completed: "Completed",
  partial: "Completed with problems",
  failed: "Could not run",
};

function StatusIcon({ status }: { status: string }) {
  if (status === "ok" || status === "completed") return <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />;
  if (status === "empty") return <SearchX className="size-4 shrink-0 text-sky-600" />;
  if (status === "partial" || status === "degraded") return <AlertTriangle className="size-4 shrink-0 text-amber-600" />;
  if (status === "failed" || status === "failing") return <XCircle className="size-4 shrink-0 text-rose-600" />;
  if (status === "running" || status === "pending") return <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />;
  return <CircleSlash className="size-4 shrink-0 text-muted-foreground" />;
}

function resultCounts(r: SourceResult): string {
  const parts: string[] = [];
  if (r.boards_ok || r.boards_failed) parts.push(`${r.boards_ok ?? 0} board${r.boards_ok === 1 ? "" : "s"} read${r.boards_failed ? `, ${r.boards_failed} failed` : ""}`);
  if (r.listings_checked) parts.push(`${r.listings_checked} listings checked`);
  if (r.status === "ok" || r.status === "empty" || r.status === "partial") parts.push(`${r.found} matched · ${r.new} new · ${r.duplicates} already in feed`);
  return parts.join(" · ");
}

/** The outcome of one discovery run: never a bare "0 jobs". */
const PROBLEM_STATUSES = ["failed", "partial"];

export function RunSummary({ run, compact = false }: { run: DiscoveryRun; compact?: boolean }) {
  const [showAll, setShowAll] = useState(false);
  const all = Object.entries(run.source_results ?? {});
  const problems = all.filter(([, r]) => PROBLEM_STATUSES.includes(r.status));
  const results = showAll ? all : problems;
  return (
    <div className="space-y-2" data-testid="run-summary">
      <div className="flex items-start gap-2">
        <StatusIcon status={run.status} />
        <div className="min-w-0 text-sm">
          <span className="font-medium">{runStatusText[run.status]}</span>
          {run.completed_at && <span className="text-muted-foreground"> · {timeAgo(run.completed_at)}</span>}
          {run.summary && <p className="text-muted-foreground">{run.summary}</p>}
        </div>
      </div>
      {!compact && results.length > 0 && (
        <ul className="divide-y rounded-lg border text-sm">
          {results.map(([key, r]) => (
            <li key={key} className="flex items-start gap-2 px-3 py-2">
              <StatusIcon status={r.status} />
              <div className="min-w-0">
                <span className="font-medium">{r.label}</span> <span className={cn("text-xs", resultTone[r.status]?.[1])}>{resultTone[r.status]?.[0] ?? r.status}</span>
                {resultCounts(r) && <div className="text-xs text-muted-foreground">{resultCounts(r)}</div>}
                {r.message && <div className="text-xs text-muted-foreground">{r.message}</div>}
              </div>
            </li>
          ))}
        </ul>
      )}
      {!compact && all.length > problems.length && (
        <button type="button" onClick={() => setShowAll(!showAll)} className="text-xs font-medium text-primary underline-offset-2 hover:underline">
          {showAll ? "Hide source details" : `Show all ${all.length} sources${problems.length ? "" : " (all fine)"}`}
        </button>
      )}
    </div>
  );
}

const connectionText: Record<SourceHealth["connection"], string> = {
  ok: "Connected",
  degraded: "Some problems",
  failing: "Failing",
  unknown: "Not checked yet",
  not_configured: "Not configured",
  disabled: "Turned off",
};

export function SourceHealthList({ sources }: { sources: SourceHealth[] }) {
  return (
    <ul className="divide-y rounded-lg border" data-testid="source-health">
      {sources.map((s) => (
        <li key={s.key} className="grid gap-1 px-3 py-3 text-sm sm:grid-cols-[1fr_auto] sm:gap-4">
          <div className="min-w-0 space-y-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <StatusIcon status={s.connection} />
              <span className="font-medium">{s.label}</span>
              <span className="text-xs text-muted-foreground">{connectionText[s.connection]}</span>
              {!s.enabled && s.configured && <span className="rounded bg-muted px-1.5 text-xs text-muted-foreground">not used by your searches</span>}
            </div>
            {s.missing && <p className="flex items-start gap-1 text-xs text-amber-800 dark:text-amber-300"><Settings2 className="mt-0.5 size-3 shrink-0" />{s.missing}</p>}
            {s.last_error && <p className="text-xs text-rose-700 dark:text-rose-300">Last error: {s.last_error}</p>}
            {s.last_run?.message && s.last_run.message !== s.missing && <p className="text-xs text-muted-foreground">Last run: {s.last_run.message}</p>}
            {s.boards && s.boards.total > 0 && (
              <p className="text-xs text-muted-foreground">
                {s.boards.total} company board{s.boards.total === 1 ? "" : "s"}: {s.boards.ok} OK{s.boards.failing ? `, ${s.boards.failing} failing` : ""}{s.boards.unchecked ? `, ${s.boards.unchecked} not checked yet` : ""}
              </p>
            )}
          </div>
          <dl className="grid grid-cols-[auto_auto] gap-x-3 text-xs text-muted-foreground sm:text-right">
            <dt>Jobs in your feed</dt><dd className="font-medium text-foreground">{s.jobs_in_feed}</dd>
            {s.kind !== "manual" && <><dt>Last attempt</dt><dd title={s.last_attempt_at ?? undefined}>{s.last_attempt_at ? timeAgo(s.last_attempt_at) : "never"}</dd></>}
            {s.kind !== "manual" && <><dt>Last success</dt><dd title={s.last_success_at ? formatDate(s.last_success_at, true) : undefined}>{s.last_success_at ? timeAgo(s.last_success_at) : "never"}</dd></>}
            {s.last_run && <><dt>Latest run</dt><dd>{resultTone[s.last_run.status]?.[0] ?? s.last_run.status}{s.last_run.found ? ` · ${s.last_run.found} matched` : ""}</dd></>}
          </dl>
        </li>
      ))}
    </ul>
  );
}

/** Why the feed is empty, from the latest run and the active filters. Never a silent blank page. */
export function FeedEmptyState({ lastRun, filtered, running, onRun, onClearFilters }: {
  lastRun: DiscoveryRun | null | undefined; filtered: boolean; running: boolean; onRun: () => void; onClearFilters: () => void;
}) {
  const navigate = useNavigate();
  let title: string;
  let body: ReactNode;
  if (filtered) {
    title = "No jobs match these filters";
    body = <>Your feed has jobs, but none pass the current filters. <Button variant="link" className="h-auto p-0" onClick={onClearFilters}>Clear filters</Button></>;
  } else if (running) {
    title = "Discovery is running";
    body = "Fetching listings from company job boards and matching them against your resume. Jobs appear here as soon as it finishes.";
  } else if (!lastRun) {
    title = "Discovery hasn't run yet";
    body = "JobPilot searches the official job boards of verified employers for roles matching your resume and preferences.";
  } else if (lastRun.status === "failed") {
    title = "The last discovery run could not search anything";
    body = lastRun.summary ?? "No source was available.";
  } else {
    title = "No matching jobs found yet";
    body = <>{lastRun.summary ?? "The sources were reached but nothing matched."} You can broaden your job titles or locations in <Button variant="link" className="h-auto p-0" onClick={() => navigate("/settings")}>Settings</Button>, or add companies in <Button variant="link" className="h-auto p-0" onClick={() => navigate("/searches")}>Searches</Button>.</>;
  }
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center" data-testid="feed-empty">
      {running ? <Loader2 className="size-8 animate-spin text-muted-foreground" /> : <Radar className="size-8 text-muted-foreground" />}
      <h3 className="font-semibold">{title}</h3>
      <p className="max-w-xl text-sm text-muted-foreground">{body}</p>
      {!filtered && !running && <Button onClick={onRun}><Radar /> Run discovery now</Button>}
      <p className="max-w-xl text-xs text-muted-foreground">You can also clip jobs you find on LinkedIn, Indeed or Naukri, or paste a job link with <strong>Add job</strong>.</p>
    </div>
  );
}

export function NotificationBell() {
  const notes = useNotifications();
  const mark = useMarkNotifications();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open]);
  const unread = notes.data?.unread ?? 0;
  return (
    <div ref={ref} className="relative">
      <Button size="icon-sm" variant="ghost" onClick={() => setOpen((o) => !o)} aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"} aria-expanded={open}>
        <Bell />
        {unread > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-4 rounded-full bg-primary px-1 text-[10px] leading-4 font-semibold text-primary-foreground">{unread > 99 ? "99+" : unread}</span>}
      </Button>
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border bg-popover p-2 text-popover-foreground shadow-lg" role="dialog" aria-label="Notifications">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && <Button size="sm" variant="ghost" onClick={() => mark.mutate(undefined)}>Mark all read</Button>}
          </div>
          {!notes.data?.items.length ? <p className="px-2 py-4 text-sm text-muted-foreground">Nothing yet. New high matches from your searches appear here.</p> : (
            <ul className="max-h-96 overflow-y-auto">
              {notes.data.items.map((n) => (
                <li key={n.id}>
                  <button type="button" onClick={() => { if (!n.read_at) mark.mutate(n.id); setOpen(false); if (n.link) navigate(n.link); }}
                          className={cn("w-full rounded-lg px-2 py-2 text-left text-sm hover:bg-muted", !n.read_at && "bg-primary/5")}>
                    <div className={cn(!n.read_at && "font-medium")}>{n.title}</div>
                    {n.body && <div className="text-xs text-muted-foreground">{n.body}</div>}
                    <div className="text-xs text-muted-foreground">{timeAgo(n.created_at)}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
