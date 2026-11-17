import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowRight, Bookmark, CalendarClock, FileText, Hourglass, Radar, Send, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";
import { ErrorState, ScoreBadge, StageBadge } from "@/components/app/common";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { itemLink, useOverview } from "./queries";
import type { Overview, OverviewItem, OverviewJob } from "./types";

function Panel({ title, icon: Icon, count, action, children, className, tone }: {
  title: string; icon: React.ElementType; count?: number; action?: ReactNode; children: ReactNode; className?: string;
  tone?: "attention";
}) {
  const id = `panel-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <Card className={cn("gap-0 p-0", tone === "attention" && count ? "border-amber-500/40" : "", className)} role="region" aria-labelledby={id}>
      <div className="flex items-center justify-between gap-2 border-b px-4 py-2.5">
        <h2 id={id} className="flex items-center gap-2 text-sm font-semibold">
          <Icon className={cn("size-4", tone === "attention" && count ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground")} aria-hidden />
          {title}
          {count != null && <span className="rounded-full bg-muted px-1.5 text-xs font-medium tabular-nums text-muted-foreground">{count}</span>}
        </h2>
        {action}
      </div>
      <div className="px-4 py-2">{children}</div>
    </Card>
  );
}

function More({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="inline-flex items-center gap-1 rounded text-xs font-medium text-primary hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
      {children} <ArrowRight className="size-3" aria-hidden />
    </Link>
  );
}

function Quiet({ children }: { children: ReactNode }) {
  return <p className="py-2 text-sm text-muted-foreground">{children}</p>;
}

const rowLink = "-mx-2 flex items-center justify-between gap-3 rounded-md px-2 py-1.5 hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-ring";

function JobRow({ j }: { j: OverviewJob }) {
  const closed = j.freshness === "closed" || j.freshness === "expired";
  return (
    <li>
      <Link to={`/discover?job=${j.user_job_id}`} className={rowLink}>
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium">{j.title}</span>
          <span className="block truncate text-xs text-muted-foreground">
            {[j.company, j.location, j.salary].filter(Boolean).join(" · ")}
            {closed && <span className="ml-1 text-amber-700 dark:text-amber-400">· no longer open</span>}
            {j.eligibility_status === "INELIGIBLE" && <span className="ml-1 text-rose-700 dark:text-rose-400">· eligibility issue</span>}
          </span>
        </span>
        <ScoreBadge score={j.match_score} />
      </Link>
    </li>
  );
}

function ItemRow({ i, showDue }: { i: OverviewItem; showDue?: boolean }) {
  return (
    <li>
      <Link to={itemLink(i)} className={rowLink}>
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium" title={i.title}>{i.title}</span>
          {(i.detail || (showDue && i.due)) && (
            <span className="block truncate text-xs text-muted-foreground">
              {[showDue && i.due ? formatDate(i.due, i.kind === "interview") : null, i.detail].filter(Boolean).join(" · ")}
            </span>
          )}
        </span>
      </Link>
    </li>
  );
}

const discoveryText: Record<Overview["discovery"]["state"], string> = {
  never_run: "Discovery hasn't run yet.",
  running: "A discovery run is in progress.",
  ok: "All sources answered on the last run.",
  partial: "Some sources had problems on the last run.",
  failed: "The last discovery run failed.",
  not_configured: "The last scheduled run had no sources set up. Add a saved search or companies under Searches.",
};

const resumeText: Record<Overview["resume"]["state"], string> = {
  missing: "No resume built yet",
  not_exported: "Built, not exported yet",
  ready: "Ready to use",
};

/** The dashboard's first screen: only things the user can act on, each one linking straight to it. */
export function ActionCentre() {
  const q = useOverview();
  if (q.isLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-3" role="status" aria-label="Loading your dashboard">
        {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-40" />)}
      </div>
    );
  }
  if (q.isError || !q.data) return <ErrorState title="Your dashboard couldn't be loaded" error={q.error} onRetry={() => void q.refetch()} />;
  const o = q.data;
  const d = o.discovery;
  return (
    <div className="grid gap-4 lg:grid-cols-3" data-testid="action-centre">
      <Panel title="New matching jobs" icon={Sparkles} count={o.new_jobs.count} className="lg:col-span-2"
             action={<More to="/discover">Open job feed</More>}>
        {o.new_jobs.top.length ? (
          <ul className="divide-y divide-border/60">{o.new_jobs.top.map((j) => <JobRow key={j.user_job_id} j={j} />)}</ul>
        ) : (
          <Quiet>No new jobs scoring {Math.round(o.new_jobs.min_score)}% or more in the last {o.new_jobs.days} days that you haven't opened. <Link className="text-primary underline" to="/discover">Run discovery</Link> or lower your minimum score in Settings.</Quiet>
        )}
      </Panel>

      <Panel title="Needs your attention" icon={AlertCircle} count={o.attention.length} tone="attention">
        {o.attention.length ? (
          <ul className="divide-y divide-border/60">{o.attention.slice(0, 6).map((i, n) => <ItemRow key={`${i.kind}-${n}`} i={i} />)}</ul>
        ) : <Quiet>Nothing is waiting on you.</Quiet>}
        {o.attention.length > 6 && <div className="pb-1 pt-2"><More to="/applied">{o.attention.length - 6} more</More></div>}
      </Panel>

      <Panel title="Coming up" icon={CalendarClock} count={o.upcoming.length}>
        {o.upcoming.length ? (
          <ul className="divide-y divide-border/60">{o.upcoming.slice(0, 5).map((i, n) => <ItemRow key={`${i.kind}-${n}`} i={i} showDue />)}</ul>
        ) : <Quiet>No interviews or offer deadlines in the next 14 days.</Quiet>}
      </Panel>

      <Panel title="Saved jobs" icon={Bookmark} count={o.saved.count} action={o.saved.count ? <More to="/saved">All saved</More> : undefined}>
        {o.saved.no_longer_open > 0 && (
          <p className="pt-1 text-xs text-amber-700 dark:text-amber-400">{o.saved.no_longer_open} saved {o.saved.no_longer_open === 1 ? "job is" : "jobs are"} no longer open.</p>
        )}
        {o.saved.top.length ? (
          <ul className="divide-y divide-border/60">{o.saved.top.slice(0, 3).map((j) => <JobRow key={j.user_job_id} j={j} />)}</ul>
        ) : <Quiet>Save jobs from the feed to come back to them.</Quiet>}
      </Panel>

      <Panel title="Recently submitted" icon={Send} count={o.recent_submitted.length} action={<More to="/applied">Applications</More>}>
        {o.recent_submitted.length ? (
          <ul className="divide-y divide-border/60">
            {o.recent_submitted.map((a) => (
              <li key={a.application_id}>
                <Link to={`/applied?app=${a.application_id}`} className={rowLink}>
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{a.title}</span>
                    <span className="block truncate text-xs text-muted-foreground">{a.company} · {timeAgo(a.submitted_at)}</span>
                  </span>
                  <StageBadge stage={a.stage} />
                </Link>
              </li>
            ))}
          </ul>
        ) : <Quiet>Applications you confirm as sent appear here.</Quiet>}
      </Panel>

      <Panel title="Resume" icon={FileText} action={<More to="/studio">Resume Studio</More>}>
          <dl className="grid grid-cols-[6.5rem_1fr] gap-x-2 gap-y-1 py-1 text-sm">
            <dt className="text-muted-foreground">Status</dt>
            <dd className={cn("font-medium", o.resume.state !== "ready" && "text-amber-700 dark:text-amber-400")}>{resumeText[o.resume.state]}</dd>
            {o.resume.latest && <><dt className="text-muted-foreground">Latest</dt><dd className="truncate">{o.resume.latest.name} · {timeAgo(o.resume.latest.updated_at)}</dd></>}
            <dt className="text-muted-foreground">Profile</dt>
            <dd>{o.resume.profile_confirmed ? "Confirmed" : <Link className="text-primary underline" to="/settings">Confirm your details</Link>}</dd>
          </dl>
      </Panel>
      <Panel title="Discovery" icon={Radar} action={<More to="/searches">Searches</More>} className={o.waiting.length ? "" : "lg:col-span-2"}>
          <div className="space-y-1 py-1 text-sm" aria-live="polite">
            <p className={cn(d.state === "failed" || d.state === "partial" ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground")}>{discoveryText[d.state]}</p>
            {d.last_run && <p className="text-xs text-muted-foreground">Last run {timeAgo(d.last_run.started_at)} · {d.last_run.jobs_found} found, {d.last_run.jobs_new} new</p>}
            {d.problems.slice(0, 3).map((p) => <p key={p.source} className="truncate text-xs" title={p.message ?? undefined}><Hourglass className="mr-1 inline size-3" aria-hidden />{p.label}: {p.message ?? p.status}</p>)}
          </div>
      </Panel>

      {o.waiting.length > 0 && (
        <Panel title="Waiting on them" icon={Hourglass} count={o.waiting.length}>
          <ul className="divide-y divide-border/60">{o.waiting.slice(0, 4).map((i, n) => <ItemRow key={`w-${n}`} i={i} />)}</ul>
        </Panel>
      )}
    </div>
  );
}
