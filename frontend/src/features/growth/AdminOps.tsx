import { useState } from "react";
import { HardDrive, Loader2, Play, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAdminJobs, useProductMetrics, useRunJob, useSystemStatus } from "./queries";
import type { BackgroundJob as AdminJob, JobRunResult } from "./types";

const panel = "rounded-xl border border-border bg-card overflow-hidden";
const head = "p-4 border-b border-border flex items-center justify-between gap-2";
const th = "px-4 py-3";
const thead = "bg-muted/50 border-b border-border text-muted-foreground uppercase text-[10px]";

const statusTone: Record<string, string> = {
  ok: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  running: "bg-sky-500/15 text-sky-700 dark:text-sky-300",
  partial: "bg-amber-500/20 text-amber-800 dark:text-amber-300",
  failed: "bg-destructive/15 text-destructive",
  error: "bg-destructive/15 text-destructive",
  blocked: "bg-amber-500/20 text-amber-800 dark:text-amber-300",
  skipped: "bg-muted text-muted-foreground",
  interrupted: "bg-amber-500/20 text-amber-800 dark:text-amber-300",
};

export function JobStatusBadge({ status }: { status: string | null }) {
  return (
    <span className={cn("inline-block whitespace-nowrap rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase", status ? statusTone[status] ?? "bg-muted text-muted-foreground" : "bg-muted text-muted-foreground")}>
      {status ?? "never run"}
    </span>
  );
}

const TRIGGER_LABEL: Record<string, string> = { schedule: "on schedule", scheduled: "on schedule", catch_up: "catch-up after downtime", manual: "run by an admin", replay: "run by an admin" };
const humanize = (name: string) => name.charAt(0).toUpperCase() + name.slice(1).replaceAll("_", " ");

function LastRun({ j }: { j: AdminJob }) {
  return (
    <div className="space-y-1">
      <JobStatusBadge status={j.last_status} />
      {j.last_started_at && <div className="text-[11px] text-muted-foreground">{formatDate(j.last_started_at, true)}</div>}
      {j.last_trigger && <div className="text-[11px] text-muted-foreground">{TRIGGER_LABEL[j.last_trigger] ?? j.last_trigger}</div>}
      {j.runs_with && j.last_trigger && <div className="text-[11px] text-muted-foreground">as part of {humanize(j.runs_with)}</div>}
    </div>
  );
}

function RunButton({ j, running, onRun }: { j: AdminJob; running: string | null; onRun: (name: string) => void }) {
  return (
    <button onClick={() => onRun(j.name)} disabled={running != null}
            className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md border border-border px-2.5 py-1.5 text-[11px] font-medium hover:bg-muted disabled:opacity-50">
      {running === j.name ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} Run now
    </button>
  );
}

export function BackgroundJobsPanel() {
  const jobs = useAdminJobs();
  const run = useRunJob();
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<JobRunResult | null>(null);

  const runNow = (name: string) => {
    if (!confirm(`Run "${humanize(name)}" now? It runs once, in addition to its normal schedule.`)) return;
    setRunning(name);
    setResult(null);
    run.mutate(name, {
      onSuccess: (r) => { setResult(r); toast[r.status === "ok" ? "success" : "error"](`${humanize(r.name)}: ${r.status}`); void jobs.refetch(); },
      onError: (e) => toast.error(errorMessage(e)),
      onSettled: () => setRunning(null),
    });
  };
  const list = jobs.data ?? [];
  const problems = list.filter((j) => j.last_status && ["failed", "error", "blocked", "partial", "interrupted"].includes(j.last_status)).length;
  const never = list.filter((j) => !j.last_status).length;

  return (
    <div className="space-y-4">
      {result && (
        <div className={cn("rounded-lg border p-3 text-xs", result.status === "ok" ? "border-emerald-500/30 bg-emerald-500/10" : "border-destructive/30 bg-destructive/10")}>
          <div className="font-semibold">{humanize(result.name)}: {result.status} after {result.attempts} attempt(s)</div>
          {result.error && <div className="mt-1 whitespace-pre-wrap break-words font-mono text-destructive">{result.error}</div>}
          {result.details != null && <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] text-muted-foreground">{JSON.stringify(result.details, null, 2)}</pre>}
        </div>
      )}
      <div className={panel}>
        <div className={head}>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Background jobs ({list.length})</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {problems ? `${problems} need attention. ` : "No problems. "}
              {never ? `${never} haven't run yet. ` : ""}
              Jobs missed while this machine was off run once, a few minutes after it starts.
            </p>
          </div>
          <button onClick={() => void jobs.refetch()} className="inline-flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
            <RefreshCw className={cn("h-3.5 w-3.5", jobs.isFetching && "animate-spin")} /> Refresh
          </button>
        </div>
        {jobs.isLoading && <div className="p-6"><Loader2 className="animate-spin" /></div>}
        {jobs.error && <div className="p-6 text-sm text-destructive">{errorMessage(jobs.error)}</div>}

        {/* Wide screens: a table whose columns all fit; errors get a full-width line under their job. */}
        <table className="hidden w-full table-fixed text-left text-xs md:table">
          <colgroup><col className="w-[38%]" /><col className="w-[20%]" /><col className="w-[17%]" /><col className="w-[15%]" /><col className="w-[10%]" /></colgroup>
          <thead className={thead}>
            <tr><th className={th}>Job</th><th className={th}>When it runs</th><th className={th}>Last run</th><th className={th}>Last success</th><th className={`${th} text-right`}>Action</th></tr>
          </thead>
          <tbody className="text-foreground">
            {list.map((j) => (
              <JobRows key={j.name} j={j} running={running} onRun={runNow} />
            ))}
          </tbody>
        </table>

        {/* Phones: one card per job. */}
        <ul className="divide-y divide-border md:hidden">
          {list.map((j) => (
            <li key={j.name} className="space-y-2 p-4 text-xs">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold">{humanize(j.name)}</div>
                  <div className="text-muted-foreground">{j.description}</div>
                </div>
                <RunButton j={j} running={running} onRun={runNow} />
              </div>
              <div className="text-muted-foreground">Runs: {j.schedule}</div>
              <LastRun j={j} />
              {j.last_ok_at && <div className="text-muted-foreground">Last success: {formatDate(j.last_ok_at, true)}</div>}
              {j.last_error && <ErrorNote text={j.last_error} />}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** A job's last error: the first line or so, with the full text (often a long database message) one click away. */
function ErrorNote({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const short = text.length > 220 ? `${text.slice(0, 220).trimEnd()}…` : text;
  return (
    <div className="rounded-md bg-destructive/10 px-3 py-2 text-[11px] text-destructive">
      <span className="font-semibold">Last error: </span>
      <span className="whitespace-pre-wrap break-words font-mono">{open ? text : short}</span>
      {text.length > 220 && (
        <button type="button" onClick={() => setOpen(!open)} className="ml-2 font-medium underline underline-offset-2">
          {open ? "Show less" : "Show full error"}
        </button>
      )}
    </div>
  );
}

function JobRows({ j, running, onRun }: { j: AdminJob; running: string | null; onRun: (name: string) => void }) {
  return (
    <>
      <tr className={cn("align-top hover:bg-muted/20", !j.last_error && "border-b border-border")}>
        <td className="px-4 py-3">
          <div className="font-medium">{humanize(j.name)}</div>
          <div className="text-muted-foreground">{j.description}</div>
          <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">{j.name} · {j.owner}</div>
        </td>
        <td className="break-words px-4 py-3 text-muted-foreground">{j.schedule}</td>
        <td className="px-4 py-3"><LastRun j={j} /></td>
        <td className="px-4 py-3 text-muted-foreground">{j.last_ok_at ? formatDate(j.last_ok_at, true) : "—"}</td>
        <td className="px-4 py-3 text-right"><RunButton j={j} running={running} onRun={onRun} /></td>
      </tr>
      {j.last_error && (
        <tr className="border-b border-border">
          <td colSpan={5} className="px-4 pb-3 pt-0"><ErrorNote text={j.last_error} /></td>
        </tr>
      )}
    </>
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
