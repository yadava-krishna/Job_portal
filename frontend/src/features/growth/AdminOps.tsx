import { useState } from "react";
import { HardDrive, Loader2, Play, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAdminJobs, useProductMetrics, useRunJob, useSystemStatus } from "./queries";
import type { JobRunResult } from "./types";

const panel = "rounded-xl border border-border bg-card overflow-hidden";
const head = "p-4 border-b border-border flex items-center justify-between gap-2";
const th = "px-4 py-3";
const thead = "bg-muted/50 border-b border-border text-muted-foreground uppercase text-[10px]";

const statusTone: Record<string, string> = {
  ok: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  running: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  failed: "bg-destructive/15 text-destructive",
  error: "bg-destructive/15 text-destructive",
  blocked: "bg-amber-500/20 text-amber-800 dark:text-amber-300",
  skipped: "bg-muted text-muted-foreground",
};

export function JobStatusBadge({ status }: { status: string | null }) {
  return (
    <span className={cn("rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase", status ? statusTone[status] ?? "bg-muted text-muted-foreground" : "bg-muted text-muted-foreground")}>
      {status ?? "never run"}
    </span>
  );
}

export function BackgroundJobsPanel() {
  const jobs = useAdminJobs();
  const run = useRunJob();
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<JobRunResult | null>(null);

  const runNow = (name: string) => {
    if (!confirm(`Run "${name}" now? It runs once, in addition to its normal schedule.`)) return;
    setRunning(name);
    setResult(null);
    run.mutate(name, {
      onSuccess: (r) => { setResult(r); toast[r.status === "ok" ? "success" : "error"](`${r.name}: ${r.status}`); },
      onError: (e) => toast.error(errorMessage(e)),
      onSettled: () => setRunning(null),
    });
  };

  return (
    <div className="space-y-4">
      {result && (
        <div className={cn("rounded-lg border p-3 text-xs", result.status === "ok" ? "border-emerald-500/30 bg-emerald-500/10" : "border-destructive/30 bg-destructive/10")}>
          <div className="font-semibold">Run #{result.id} of {result.name}: {result.status} after {result.attempts} attempt(s)</div>
          {result.error && <div className="mt-1 font-mono text-destructive">{result.error}</div>}
          {result.details != null && <pre className="mt-1 max-h-40 overflow-auto font-mono text-[11px] text-muted-foreground">{JSON.stringify(result.details, null, 2)}</pre>}
        </div>
      )}
      <div className={panel}>
        <div className={head}>
          <h3 className="text-sm font-semibold text-foreground">Background jobs ({jobs.data?.length ?? 0})</h3>
          <button onClick={() => void jobs.refetch()} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
            <RefreshCw className={cn("h-3.5 w-3.5", jobs.isFetching && "animate-spin")} /> Refresh
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className={thead}>
              <tr><th className={th}>Job</th><th className={th}>Schedule</th><th className={th}>Owner</th><th className={th}>Last status</th><th className={th}>Last success</th><th className={th}>Last error</th><th className={`${th} text-right`}>Actions</th></tr>
            </thead>
            <tbody className="divide-y divide-border text-foreground">
              {jobs.isLoading && <tr><td colSpan={7} className="px-4 py-6"><Loader2 className="animate-spin" /></td></tr>}
              {jobs.error && <tr><td colSpan={7} className="px-4 py-6 text-destructive">{errorMessage(jobs.error)}</td></tr>}
              {jobs.data?.map((j) => (
                <tr key={j.name} className="hover:bg-muted/20 align-top">
                  <td className="px-4 py-3"><div className="font-mono font-medium">{j.name}</div><div className="text-muted-foreground">{j.description}</div></td>
                  <td className="px-4 py-3 font-mono whitespace-nowrap">{j.schedule}</td>
                  <td className="px-4 py-3">{j.owner}</td>
                  <td className="px-4 py-3"><JobStatusBadge status={j.last_status} />{j.last_started_at && <div className="mt-1 text-[11px] text-muted-foreground">{formatDate(j.last_started_at, true)}</div>}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{j.last_ok_at ? formatDate(j.last_ok_at, true) : "—"}</td>
                  <td className="px-4 py-3 max-w-xs"><span className="line-clamp-3 font-mono text-[11px] text-destructive" title={j.last_error ?? ""}>{j.last_error ?? ""}</span></td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => runNow(j.name)} disabled={running != null}
                            className="inline-flex items-center gap-1 rounded px-2 py-1 border border-border text-[11px] hover:bg-muted font-medium disabled:opacity-50">
                      {running === j.name ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} Run now
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const northStarLabels: Record<string, string> = {
  applications_submitted: "Applications submitted",
  application_to_interview_pct: "Application → interview",
  interview_to_offer_pct: "Interview → offer",
  offers: "Offers",
  gap_closure_pct: "Skill gaps closed",
  resume_reuse_pct: "Applications with a tracked resume",
  weekly_active_candidates: "Weekly active candidates",
  reflections_completed: "Reflections completed",
  onboarding_activation_pct: "Finished onboarding",
};

export function ProductMetricsPanel() {
  const [days, setDays] = useState(30);
  const m = useProductMetrics(days);
  const d = m.data;
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Period</span>
        {[7, 30, 90].map((n) => (
          <button key={n} onClick={() => setDays(n)} className={cn("rounded-md border px-2 py-1", days === n ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>{n} days</button>
        ))}
      </div>
      {m.isLoading ? <Loader2 className="animate-spin" /> : !d ? <p className="text-sm text-destructive">{errorMessage(m.error)}</p> : (
        <>
          {d.note && <p className="text-xs text-muted-foreground">{d.note}</p>}
          <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {Object.entries(d.north_star).map(([k, v]) => (
              <div key={k} className="rounded-xl border border-border bg-card p-4">
                <div className="text-xs font-medium text-muted-foreground">{northStarLabels[k] ?? k.replaceAll("_", " ")}</div>
                <div className="text-xl font-bold text-foreground mt-1 tabular-nums">{v == null ? "—" : k.endsWith("_pct") ? `${v}%` : v}</div>
              </div>
            ))}
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <div className={panel}>
              <div className={head}><h3 className="text-sm font-semibold">Events (last {d.days} days)</h3></div>
              <table className="w-full text-left text-xs">
                <thead className={thead}><tr><th className={th}>Event</th><th className={`${th} text-right`}>Count</th><th className={`${th} text-right`}>Users</th><th className={`${th} text-right`}>Failed</th></tr></thead>
                <tbody className="divide-y divide-border">
                  {Object.entries(d.events).map(([name, e]) => (
                    <tr key={name} className="hover:bg-muted/20">
                      <td className="px-4 py-2 font-mono">{name}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{e.count}</td>
                      <td className="px-4 py-2 text-right tabular-nums">{e.users}</td>
                      <td className={cn("px-4 py-2 text-right tabular-nums", e.failed > 0 && "text-destructive font-semibold")}>{e.failed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="space-y-6">
              <div className={panel}>
                <div className={head}><h3 className="text-sm font-semibold">AI costs</h3></div>
                {d.ai_costs.length === 0 ? <p className="p-4 text-xs text-muted-foreground">No AI calls in this period.</p> : (
                  <table className="w-full text-left text-xs">
                    <thead className={thead}><tr><th className={th}>Purpose</th><th className={`${th} text-right`}>Calls</th><th className={`${th} text-right`}>Cost (USD)</th></tr></thead>
                    <tbody className="divide-y divide-border">
                      {d.ai_costs.map((c) => <tr key={c.purpose}><td className="px-4 py-2">{c.purpose}</td><td className="px-4 py-2 text-right tabular-nums">{c.calls}</td><td className="px-4 py-2 text-right tabular-nums">${c.cost_usd.toFixed(4)}</td></tr>)}
                      <tr className="font-semibold"><td className="px-4 py-2">Total</td><td className="px-4 py-2 text-right tabular-nums">{d.ai_costs.reduce((a, c) => a + c.calls, 0)}</td><td className="px-4 py-2 text-right tabular-nums">${d.ai_costs.reduce((a, c) => a + c.cost_usd, 0).toFixed(4)}</td></tr>
                    </tbody>
                  </table>
                )}
              </div>
              <div className={panel}>
                <div className={head}><h3 className="text-sm font-semibold">Research feedback</h3></div>
                {d.feedback.length === 0 ? <p className="p-4 text-xs text-muted-foreground">No feedback yet.</p> : (
                  <table className="w-full text-left text-xs">
                    <thead className={thead}><tr><th className={th}>Topic</th><th className={`${th} text-right`}>Responses</th><th className={`${th} text-right`}>Avg rating</th></tr></thead>
                    <tbody className="divide-y divide-border">
                      {d.feedback.map((f) => <tr key={f.topic}><td className="px-4 py-2">{f.topic.replaceAll("_", " ")}</td><td className="px-4 py-2 text-right tabular-nums">{f.responses}</td><td className="px-4 py-2 text-right tabular-nums">{f.average_rating ?? "—"}</td></tr>)}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function diskTone(pct: number): string {
  if (pct >= 90) return "bg-destructive";
  if (pct >= 80) return "bg-orange-500";
  if (pct >= 70) return "bg-amber-400";
  return "bg-emerald-500";
}

export function SystemPanel() {
  const s = useSystemStatus();
  const d = s.data;
  if (s.isLoading) return <Loader2 className="animate-spin" />;
  if (!d) return <p className="text-sm text-destructive">{errorMessage(s.error)}</p>;
  const b = d.backup;
  const known = b.status !== "unknown" && b.status !== "unreadable";
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="rounded-xl border border-border bg-card p-5 space-y-3">
        <div className="flex items-center justify-between text-xs font-medium text-muted-foreground"><span>Disk used</span><HardDrive className="h-4 w-4" /></div>
        <div className="text-2xl font-bold tabular-nums">{d.disk.used_percent}%</div>
        <div className="h-2 overflow-hidden rounded-full bg-muted"><div className={cn("h-full rounded-full", diskTone(d.disk.used_percent))} style={{ width: `${Math.min(100, d.disk.used_percent)}%` }} /></div>
        <p className="text-xs text-muted-foreground">
          {d.disk.free_gb} GB free.{" "}
          {d.disk.used_percent >= 90 ? "Critical: free space now or uploads and backups will fail."
            : d.disk.used_percent >= 80 ? "High: clean up old backups and exports soon."
              : d.disk.used_percent >= 70 ? "Warning: keep an eye on it." : "Healthy."}
        </p>
      </div>
      <div className="rounded-xl border border-border bg-card p-5 space-y-2">
        <div className="text-xs font-medium text-muted-foreground">Last backup</div>
        <div className="flex items-center gap-2"><JobStatusBadge status={b.status} />{b.at && <span className="text-sm">{formatBackupTime(b.at)}</span>}</div>
        {known ? (
          <dl className="grid grid-cols-[10rem_1fr] gap-y-1 text-xs">
            {b.folder && <><dt className="text-muted-foreground">Folder</dt><dd className="font-mono">{b.folder}</dd></>}
            {b.size_kb != null && <><dt className="text-muted-foreground">Size</dt><dd>{(b.size_kb / 1024).toFixed(1)} MB</dd></>}
            {b.encrypted != null && <><dt className="text-muted-foreground">Encrypted</dt><dd className={cn(!b.encrypted && "text-amber-700 dark:text-amber-300")}>{b.encrypted ? "Yes" : "No (set BACKUP_PASSPHRASE)"}</dd></>}
            {b.offhost != null && <><dt className="text-muted-foreground">Copied off this machine</dt><dd className={cn(b.offhost !== "yes" && "text-amber-700 dark:text-amber-300")}>{b.offhost === "yes" ? "Yes" : "No (only on this machine)"}</dd></>}
            {b.error && <><dt className="text-muted-foreground">Error</dt><dd className="font-mono text-destructive">{b.error}</dd></>}
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground">
            {b.note ?? "The backup status file couldn't be read."} Until a backup has run, there is no copy of the database to restore from if this machine fails.
          </p>
        )}
      </div>
    </div>
  );
}

// backup.sh writes compact UTC timestamps like 20261110T031500Z.
function formatBackupTime(at: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(at);
  return formatDate(m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z` : at, true);
}
