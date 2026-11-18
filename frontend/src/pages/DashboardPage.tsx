import { Activity, Bookmark, Briefcase, Clock, Gauge, Search, Server, Sparkles } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PlatformBadge } from "@/components/app/common";
import { ActionCentre, HomeHero } from "@/features/dashboard/ActionCentre";
import { eventLabel } from "@/features/applications/events";
import { useConnection } from "@/contexts/ConnectionContext";
import { useAuth } from "@/contexts/AuthContext";
import { formatDate, timeAgo } from "@/lib/format";
import { useActivity, useAnalytics, useSummary } from "@/services/queries";
import { useCareerSnapshot } from "@/features/career/hooks";
import { CareerSnapshotCard, WhatHappensNext } from "@/features/career/SnapshotCard";

export function StatCard({ label, value, icon: Icon, hint }: { label: string; value: React.ReactNode; icon: React.ElementType; hint?: string }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3">
      <div className="flex items-center justify-between text-xs text-muted-foreground">{label}<Icon className="size-3.5" aria-hidden /></div>
      <div className="readout text-[24px] leading-none font-semibold text-heading">{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const conn = useConnection();
  const summary = useSummary();
  const activity = useActivity();
  const analytics = useAnalytics(30);
  const snapshot = useCareerSnapshot();
  const s = summary.data;
  // Progressive disclosure: tracker sections only once there are applications. If the snapshot can't load,
  // fall back to the full dashboard rather than hiding anything.
  const showTracker = snapshot.isError || !!snapshot.data?.show.tracker;

  const backendCard = (
    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2"><Server className="size-4" /> Backend status</CardTitle></CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row label="Connection" value={<span className="flex items-center gap-2"><span className="size-2 rounded-full bg-success" /> Online</span>} />
        <Row label="Database" value={conn.health?.database.connected ? "Connected" : "Unavailable"} />
        <Row label="Version" value={conn.health?.version ?? "—"} />
        <Row label="Daily discovery" value={conn.health?.scheduler.running ? `Next ${formatDate(conn.health.scheduler.next_run, true)}` : "Not scheduled"} />
        <Row label="Last check" value={conn.lastOnlineAt ? timeAgo(new Date(conn.lastOnlineAt).toISOString()) : "—"} />
        {s?.last_discovery_run && <Row label="Last discovery" value={`${timeAgo(s.last_discovery_run.started_at)} · ${s.last_discovery_run.jobs_new} new`} />}
      </CardContent>
    </Card>
  );

  return (
    <>
      <HomeHero firstName={user?.full_name?.split(" ")[0]} />
      <div className="mb-6"><ActionCentre /></div>
      {(snapshot.data || snapshot.isLoading) && <div className="eyebrow mb-3">Your career</div>}
      <div className="mb-6">
        {snapshot.data ? <CareerSnapshotCard snapshot={snapshot.data} /> : snapshot.isLoading ? <Skeleton className="h-56" /> : null}
      </div>
      {snapshot.data && !showTracker && (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2"><WhatHappensNext /></div>
          {backendCard}
        </div>
      )}
      {showTracker && <>
      <div className="eyebrow mb-3">Your numbers</div>
      {!s ? (
        <Skeleton className="h-20 rounded-2xl" />
      ) : (
        <div className="grid grid-cols-2 divide-border rounded-2xl bg-card ring-1 ring-border sm:grid-cols-3 lg:grid-cols-6 lg:divide-x">
          <StatCard label="Discovered" value={s.total_discovered} icon={Search} hint={`${s.discovered_today} today`} />
          <StatCard label="Shortlisted" value={s.total_shortlisted} icon={Sparkles} />
          <StatCard label="Applied" value={s.total_applied} icon={Briefcase} hint={`${s.applied_today} today`} />
          <StatCard label="Saved" value={s.total_saved} icon={Bookmark} />
          <StatCard label="Pending" value={s.pending_applications} icon={Clock} hint="prepared or opened" />
          <StatCard label="Avg. match" value={s.average_match_score != null ? `${s.average_match_score}%` : "—"} icon={Gauge} />
        </div>
      )}

      <details className="group mt-4 rounded-2xl bg-card ring-1 ring-border open:pb-4">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded-2xl px-5 py-3.5 text-sm font-semibold text-heading transition-colors hover:bg-paper-sunk [&::-webkit-details-marker]:hidden">
          Trends, platforms and activity
          <span className="text-xs font-normal text-muted-foreground group-open:hidden">Show</span><span className="hidden text-xs font-normal text-muted-foreground group-open:inline">Hide</span>
        </summary>
        <div className="animate-in px-4 duration-200 fade-in-0 slide-in-from-top-1">
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Last 30 days</CardTitle><CardDescription>Jobs discovered and applications submitted per day</CardDescription></CardHeader>
          <CardContent className="h-64">
            {analytics.data ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={analytics.data.series} margin={{ left: -20, right: 8 }}>
                  <CartesianGrid strokeDasharray="2 4" vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={11} />
                  <YAxis allowDecimals={false} fontSize={11} />
                  <Tooltip />
                  <Area type="monotone" dataKey="discovered" name="Discovered" stroke="var(--chart-2)" fill="var(--chart-2)" fillOpacity={0.12} />
                  <Area type="monotone" dataKey="applied" name="Applied" stroke="var(--chart-1)" fill="var(--chart-1)" fillOpacity={0.22} />
                </AreaChart>
              </ResponsiveContainer>
            ) : <Skeleton className="h-full" />}
          </CardContent>
        </Card>

        {backendCard}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>By platform</CardTitle></CardHeader>
          <CardContent>
            {s && s.platforms.length > 0 ? (
              <table className="w-full text-sm">
                <thead className="text-left text-muted-foreground"><tr><th className="pb-2 font-medium">Platform</th><th className="pb-2 text-right font-medium">Discovered</th><th className="pb-2 text-right font-medium">Shortlisted</th><th className="pb-2 text-right font-medium">Applied</th><th className="pb-2 text-right font-medium">Avg. match</th></tr></thead>
                <tbody className="divide-y">{s.platforms.map((p) => (
                  <tr key={p.platform}><td className="py-2"><PlatformBadge platform={p.platform} /></td><td className="py-2 text-right tabular-nums">{p.discovered}</td><td className="py-2 text-right tabular-nums">{p.shortlisted}</td><td className="py-2 text-right tabular-nums">{p.applied}</td><td className="py-2 text-right tabular-nums">{p.average_score ?? "—"}</td></tr>
                ))}</tbody>
              </table>
            ) : <p className="text-sm text-muted-foreground">No jobs yet.</p>}
            {analytics.data && (
              <div className="mt-6">
                <h4 className="mb-2 text-sm font-medium">Funnel</h4>
                <div className="space-y-1.5">
                  {analytics.data.funnel.map((f) => {
                    const max = Math.max(1, analytics.data!.funnel[0].count);
                    return (
                      <div key={f.stage} className="grid grid-cols-[6rem_1fr_3rem] items-center gap-2 text-sm">
                        <span className="text-muted-foreground">{f.stage}</span>
                        <div className="h-2 rounded-full bg-muted"><div className="h-2 rounded-full bg-primary" style={{ width: `${(f.count / max) * 100}%` }} /></div>
                        <span className="text-right tabular-nums">{f.count}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Activity className="size-4" /> Recent activity</CardTitle></CardHeader>
          <CardContent>
            {activity.data?.length ? (
              <ul className="space-y-3">
                {activity.data.slice(0, 12).map((a, i) => (
                  <li key={i} className="text-sm">
                    <div className="font-medium">{a.kind === "discovery" ? "Discovery run" : `${a.title} · ${a.company}`}</div>
                    <div className="text-xs text-muted-foreground">
                      {a.kind === "discovery" ? a.details : eventLabel({ id: i, event_type: a.event_type, from_status: null, to_status: a.to_status ?? null, details: null, created_at: a.at })} · {timeAgo(a.at)}
                    </div>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted-foreground">Nothing yet today.</p>}
          </CardContent>
        </Card>
      </div>
        </div>
      </details>
      </>}
    </>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="flex justify-between gap-3"><span className="text-muted-foreground">{label}</span><span className="text-right font-medium">{value}</span></div>;
}
