import { useState, type ReactNode } from "react";
import { firstSight } from "@/lib/seenOnce";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowRight, Bookmark, CalendarClock, FileText, Hourglass, Radar, Send } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { ErrorState, StageBadge } from "@/components/app/common";
import { DawnScene } from "@/components/app/DawnScene";
import { CompanyMark } from "@/components/app/JobCard";
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
  const hot = tone === "attention" && !!count;
  return (
    <section className={cn("jp-item flex flex-col rounded-2xl bg-card ring-1", hot ? "ring-caution/40" : "ring-border", className)}
             role="region" aria-labelledby={id}>
      <div className="flex items-center justify-between gap-2 px-5 pt-4 pb-2">
        <h2 id={id} className="flex items-center gap-2.5 font-sans text-[15px] font-semibold tracking-normal">
          <span className={cn("flex size-7 items-center justify-center rounded-full", hot ? "bg-caution-tint text-caution" : "bg-paper-sunk text-muted-foreground")}>
            <Icon className="size-[15px]" aria-hidden />
          </span>
          {title}
          {count != null && <span className="readout rounded-full bg-paper-sunk px-2 py-0.5 text-[11px] text-muted-foreground">{count}</span>}
        </h2>
        {action}
      </div>
      <div className="flex-1 px-3 pb-3">{children}</div>
    </section>
  );
}

function More({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="group inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium text-route hover:bg-route-tint focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
      {children} <ArrowRight className="size-3 transition-transform group-hover:translate-x-0.5" aria-hidden />
    </Link>
  );
}

function Quiet({ children }: { children: ReactNode }) {
  return <p className="px-2 py-2 text-sm leading-relaxed text-muted-foreground">{children}</p>;
}

const rowLink = "flex items-center justify-between gap-3 rounded-xl px-2.5 py-2 transition-colors hover:bg-paper-sunk focus-visible:outline-2 focus-visible:outline-ring";

function Monogram({ name, className }: { name: string; className?: string }) {
  return <CompanyMark name={name} className={className} />;
}

function JobRow({ j }: { j: OverviewJob }) {
  const closed = j.freshness === "closed" || j.freshness === "expired";
  return (
    <li>
      <Link to={`/discover?job=${j.user_job_id}`} className={rowLink}>
        <Monogram name={j.company} className="size-9 text-[12px]" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{j.title}</span>
          <span className="block truncate text-xs text-muted-foreground">
            {[j.company, j.location, j.salary].filter(Boolean).join(" · ")}
            {closed && <span className="ml-1 text-caution">· no longer open</span>}
            {j.eligibility_status === "INELIGIBLE" && <span className="ml-1 text-destructive">· eligibility issue</span>}
          </span>
        </span>
        {j.match_score != null && <span className="readout text-sm text-route">{Math.round(j.match_score)}%</span>}
      </Link>
    </li>
  );
}

function ItemRow({ i, showDue }: { i: OverviewItem; showDue?: boolean }) {
  const when = showDue && i.due ? new Date(i.due) : null;
  return (
    <li>
      <Link to={itemLink(i)} className={rowLink}>
        {when && !Number.isNaN(when.getTime()) && (
          <span className="flex w-11 shrink-0 flex-col items-center rounded-xl bg-paper-sunk py-1 leading-none" aria-hidden>
            <span className="readout text-[10px] text-muted-foreground uppercase">{when.toLocaleString("en", { month: "short" })}</span>
            <span className="font-display text-lg font-medium">{when.getDate()}</span>
          </span>
        )}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium" title={i.title}>{i.title}</span>
          {(i.detail || (showDue && i.due)) && (
            <span className="block truncate text-xs text-muted-foreground">
              {[showDue && i.due ? formatDate(i.due, i.kind === "interview") : null, i.detail].filter(Boolean).join(" · ")}
            </span>
          )}
        </span>
        <ArrowRight className="size-3.5 shrink-0 text-muted-foreground/60" aria-hidden />
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

/** The top of Home: a slim band with the greeting and one sentence saying what today holds. */
export function HomeHero({ firstName }: { firstName?: string | null }) {
  const q = useOverview();
  const o = q.data;
  const parts: string[] = [];
  if (o) {
    if (o.attention.length) parts.push(`${o.attention.length} ${o.attention.length === 1 ? "thing needs" : "things need"} you`);
    if (o.new_jobs.count) parts.push(`${o.new_jobs.count} fresh ${o.new_jobs.count === 1 ? "match" : "matches"}`);
    if (o.upcoming.length) parts.push(`${o.upcoming.length} coming up`);
  }
  const line = !o ? "\u00a0" : parts.length ? `${parts.join(" · ")}. Time to lock in.` : "Inbox-zero energy. You're all caught up; new matches land as discovery runs.";
  const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });
  return (
    <section className="relative isolate mb-4 overflow-hidden rounded-2xl ring-1 ring-border" aria-label="Today">
      <div className="absolute inset-0 -z-10"><DawnScene /></div>
      <div className="flex flex-col gap-3 px-6 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <div className="min-w-0">
          <div className="eyebrow mb-1.5 text-heading/60">{today}</div>
          <h1 className="font-display text-[28px] leading-tight font-extrabold tracking-[-0.03em] sm:text-[32px]">
            Hey{firstName ? <>, <em>{firstName}</em></> : null}. We're so back.
          </h1>
          <p className="mt-1 text-[14px] text-foreground/75">{line}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Link to="/discover" className={buttonVariants()}>See your matches <ArrowRight /></Link>
          <Link to="/applied" className={cn(buttonVariants({ variant: "outline" }), "bg-card/80 backdrop-blur")}>Applications</Link>
        </div>
      </div>
    </section>
  );
}

function MatchRow({ j, rank }: { j: OverviewJob; rank: number }) {
  const closed = j.freshness === "closed" || j.freshness === "expired";
  return (
    <li className="jp-item" style={{ ["--i" as string]: rank + 1 }}>
      <Link to={`/discover?job=${j.user_job_id}`}
            className="group flex items-center gap-3.5 rounded-xl px-3 py-2.5 transition-colors duration-150 hover:bg-paper-sunk focus-visible:outline-2 focus-visible:outline-ring">
        <Monogram name={j.company} className="size-10 text-[13px]" />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate font-display text-[15px] font-bold tracking-[-0.01em] text-heading">{j.title}</span>
            {rank === 0 && <span className="shrink-0 rounded-full bg-peach px-2 py-px text-[10.5px] font-semibold text-coral-ink">Top pick</span>}
          </span>
          <span className="block truncate text-[13px] text-muted-foreground">
            {[j.company, j.location, j.salary].filter(Boolean).join(" · ")}
            {closed && <span className="ml-1 text-caution">· no longer open</span>}
            {j.eligibility_status === "INELIGIBLE" && <span className="ml-1 text-destructive">· eligibility issue</span>}
          </span>
        </span>
        {j.match_score != null && <span className="readout text-[17px] font-semibold text-route">{Math.round(j.match_score)}<span className="text-[12px] text-muted-foreground">%</span></span>}
        <ArrowRight className="size-4 shrink-0 text-muted-foreground/50 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-route" aria-hidden />
      </Link>
    </li>
  );
}

/** Home below the greeting: fresh matches and what needs you, above the fold; the rest in one compact row. */
export function ActionCentre() {
  const q = useOverview();
  const [play] = useState(() => firstSight("home"));
  if (q.isLoading) {
    return (
      <div className="space-y-4" role="status" aria-label="Loading your dashboard">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3"><Skeleton className="h-80 rounded-2xl lg:col-span-2" /><Skeleton className="h-80 rounded-2xl" /></div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-36 rounded-2xl" />)}</div>
      </div>
    );
  }
  if (q.isError || !q.data) return <ErrorState title="Your dashboard couldn't be loaded" error={q.error} onRetry={() => void q.refetch()} />;
  const o = q.data;
  const d = o.discovery;
  const top = o.new_jobs.top.slice(0, 5);
  return (
    <div className={cn("space-y-4", !play && "jp-static")} data-testid="action-centre">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section role="region" aria-labelledby="panel-new-matching-jobs" className="jp-item rounded-2xl bg-card ring-1 ring-border lg:col-span-2">
          <div className="flex flex-wrap items-end justify-between gap-3 px-5 pt-4 pb-1">
            <div>
              <div id="panel-new-matching-jobs" className="eyebrow mb-1">New matching jobs{o.new_jobs.count ? ` · ${o.new_jobs.count}` : ""}</div>
              <h2 className="font-display text-[20px] leading-tight font-extrabold">{top.length ? <>Fresh roles, <em>just dropped</em></> : "Nothing new just yet. Stay tuned."}</h2>
            </div>
            <More to="/discover">All matches</More>
          </div>
          <div className="px-2 pb-2">
            {top.length ? (
              <ul>{top.map((j, i) => <MatchRow key={j.user_job_id} j={j} rank={i} />)}</ul>
            ) : (
              <Quiet>No new jobs scoring {Math.round(o.new_jobs.min_score)}% or more in the last {o.new_jobs.days} days that you haven't opened. <Link className="font-medium text-route underline underline-offset-2" to="/discover">Run discovery</Link> or lower your minimum score in Settings.</Quiet>
            )}
          </div>
        </section>

        <div className="flex flex-col gap-4">
          <Panel title="Needs your attention" icon={AlertCircle} count={o.attention.length} tone="attention">
            {o.attention.length ? (
              <ul>{o.attention.slice(0, 4).map((i, n) => <ItemRow key={`${i.kind}-${n}`} i={i} />)}</ul>
            ) : <Quiet>Nothing is waiting on you.</Quiet>}
            {o.attention.length > 4 && <div className="px-2 pt-1"><More to="/applied">{o.attention.length - 4} more</More></div>}
          </Panel>
          <Panel title="Coming up" icon={CalendarClock} count={o.upcoming.length}>
            {o.upcoming.length ? (
              <ul>{o.upcoming.slice(0, 3).map((i, n) => <ItemRow key={`${i.kind}-${n}`} i={i} showDue />)}</ul>
            ) : <Quiet>No interviews or offer deadlines in the next 14 days.</Quiet>}
          </Panel>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Panel title="Submitted" icon={Send} count={o.recent_submitted.length} action={<More to="/applied">All</More>}>
          {o.recent_submitted.length ? (
            <ul>
              {o.recent_submitted.slice(0, 3).map((a) => (
                <li key={a.application_id}>
                  <Link to={`/applied?app=${a.application_id}`} className={rowLink}>
                    <span className="min-w-0 flex-1">
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

        <Panel title="Saved jobs" icon={Bookmark} count={o.saved.count} action={o.saved.count ? <More to="/saved">All</More> : undefined}>
          {o.saved.no_longer_open > 0 && (
            <p className="px-2.5 pt-1 text-xs text-caution">{o.saved.no_longer_open} saved {o.saved.no_longer_open === 1 ? "job is" : "jobs are"} no longer open.</p>
          )}
          {o.saved.top.length ? (
            <ul>{o.saved.top.slice(0, 2).map((j) => <JobRow key={j.user_job_id} j={j} />)}</ul>
          ) : <Quiet>Save jobs from the feed to come back to them.</Quiet>}
        </Panel>

        <Panel title="Resume" icon={FileText} action={<More to="/studio">Resumes</More>}>
          <dl className="grid grid-cols-[4.5rem_1fr] gap-x-2 gap-y-1.5 px-2.5 py-1 text-sm">
            <dt className="text-muted-foreground">Status</dt>
            <dd className={cn("font-medium", o.resume.state === "ready" ? "text-success" : "text-caution")}>{resumeText[o.resume.state]}</dd>
            {o.resume.latest && <><dt className="text-muted-foreground">Latest</dt><dd className="truncate">{o.resume.latest.name} · {timeAgo(o.resume.latest.updated_at)}</dd></>}
            <dt className="text-muted-foreground">Profile</dt>
            <dd>{o.resume.profile_confirmed ? "Confirmed" : <Link className="text-route underline underline-offset-2" to="/settings">Confirm your details</Link>}</dd>
          </dl>
        </Panel>

        <Panel title="Discovery" icon={Radar} action={<More to="/searches">Searches</More>}>
          <div className="space-y-1 px-2.5 py-1 text-sm" aria-live="polite">
            <p className={cn(d.state === "failed" || d.state === "partial" ? "text-caution" : "text-muted-foreground")}>{discoveryText[d.state]}</p>
            {d.last_run && <p className="text-xs text-muted-foreground">Last run {timeAgo(d.last_run.started_at)} · <span className="readout">{d.last_run.jobs_found}</span> found, <span className="readout">{d.last_run.jobs_new}</span> new</p>}
            {d.problems.slice(0, 3).map((p) => <p key={p.source} className="truncate text-xs" title={p.message ?? undefined}><Hourglass className="mr-1 inline size-3" aria-hidden />{p.label}: {p.message ?? p.status}</p>)}
          </div>
        </Panel>
      </div>

      {o.waiting.length > 0 && (
        <Panel title="Waiting on them" icon={Hourglass} count={o.waiting.length}>
          <ul className="grid gap-x-4 sm:grid-cols-2 lg:grid-cols-3">{o.waiting.slice(0, 6).map((i, n) => <ItemRow key={`w-${n}`} i={i} />)}</ul>
        </Panel>
      )}
    </div>
  );
}
