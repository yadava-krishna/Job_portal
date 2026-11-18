import { AlertTriangle, CheckCircle2, Database, HardDrive, Loader2, OctagonAlert, Puzzle, RefreshCw, Users } from "lucide-react";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { JobStatusBadge } from "./AdminOps";
import { useOpsHealth } from "./queries";
import type { DiskHealth, OpsHealth, SourceRow } from "./types";
import { StatusDot, table, type Tone } from "./ui";

const panel = "min-w-0 rounded-2xl bg-card ring-1 ring-border overflow-hidden";
const head = "px-4 py-3 sm:px-5 flex items-center justify-between gap-2";
const thead = table.thead;
const th = "px-3 py-2 font-medium whitespace-nowrap first:pl-5 last:pr-5";
const td = "px-3 py-2 first:pl-5 last:pr-5";
const muted = "text-muted-foreground";

const levelTone: Record<string, Tone> = { ok: "success", warning: "caution", high: "caution", critical: "danger", unknown: "muted" };
const levelBar: Record<string, string> = { ok: "bg-success", warning: "bg-caution", high: "bg-caution", critical: "bg-destructive" };
const levelText: Record<string, string> = {
  ok: "text-success", warning: "text-caution", high: "text-caution", critical: "text-destructive", unknown: "text-muted-foreground",
};
const sourceTone: Record<SourceRow["state"], string> = {
  failing: "failed", stale: "partial", degraded: "partial", ok: "ok", idle: "skipped", disabled: "skipped",
};

function bytes(n: number | null | undefined): string {
  if (n == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v >= 10 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`;
}

function ago(hours: number | null | undefined): string {
  if (hours == null) return "never";
  if (hours < 1) return "under an hour ago";
  if (hours < 48) return `${Math.round(hours)} h ago`;
  return `${Math.round(hours / 24)} days ago`;
}

function NotAvailable({ note }: { note?: string }) {
  return <p className={cn("text-xs", muted)}>{note ?? "Not available."}</p>;
}

function Card({ title, icon, children, className }: { title: string; icon?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("min-w-0 rounded-2xl bg-card p-4 ring-1 ring-border space-y-3 sm:px-5", className)}>
      <h3 className="flex items-center gap-2 font-display text-[14px] font-bold text-heading">
        {icon && <span aria-hidden className="flex size-6 items-center justify-center rounded-lg bg-paper-sunk [&_svg]:size-3.5">{icon}</span>}<span>{title}</span>
      </h3>
      {children}
    </section>
  );
}

function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="min-w-0">
      <dt className={cn("truncate text-[11px]", muted)}>{label}</dt>
      <dd className={cn("readout text-[14px] font-semibold text-heading", tone)}>{value}</dd>
    </div>
  );
}

function DiskRow({ d }: { d: DiskHealth }) {
  if (!d.available) return <div className="text-xs"><div className="font-medium">{d.label}</div><NotAvailable note={d.note} /></div>;
  const pct = d.used_percent ?? 0;
  return (
    <div className="space-y-1 text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-medium">{d.label}</span>
        <StatusDot tone={levelTone[d.level ?? "ok"] ?? "muted"} className={cn("readout font-semibold", levelText[d.level ?? "ok"])}>{pct}%</StatusDot>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className={cn("h-full rounded-full", levelBar[d.level ?? "ok"])} style={{ width: `${Math.min(100, pct)}%` }} /></div>
      <div className={muted}>{d.free_gb} GB free of {d.total_gb} GB · <span className="font-mono">{d.path}</span></div>
      {d.note && <div className="text-caution">{d.note}</div>}
    </div>
  );
}

function DatabaseCard({ db }: { db: OpsHealth["database"] }) {
  return (
    <Card title="Database" icon={<Database/>}>
      {!db.available ? <NotAvailable note={db.note} /> : (
        <>
          <dl className="grid grid-cols-3 gap-3">
            <Stat label="Size" value={bytes(db.size_bytes)} />
            <Stat label="Response" value={db.latency_ms != null ? `${db.latency_ms} ms` : "—"} />
            <Stat label="Connections" value={db.connections ?? "—"} />
          </dl>
          <div className={cn("text-[11px]", muted)}>
            {db.dialect === "postgresql" ? `PostgreSQL ${db.server_version ?? ""}` : db.dialect} · migration <span className="font-mono">{db.migration ?? "unknown"}</span>
          </div>
          {db.largest_tables && db.largest_tables.length > 0 ? (
            <table className="w-full text-left text-[11px]">
              <thead className={muted}><tr><th className="py-1 font-medium">Largest tables</th><th className="py-1 text-right font-medium">Rows (est.)</th><th className="py-1 text-right font-medium">Size</th></tr></thead>
              <tbody className="divide-y divide-border/70">
                {db.largest_tables.map((t) => (
                  <tr key={t.table}><td className="py-1 font-mono">{t.table}</td><td className="py-1 text-right readout">{t.rows_estimate.toLocaleString()}</td><td className="py-1 text-right readout">{bytes(t.bytes)}</td></tr>
                ))}
              </tbody>
            </table>
          ) : db.note && <NotAvailable note={db.note} />}
        </>
      )}
    </Card>
  );
}

function BackupsCard({ b }: { b: OpsHealth["backups"] }) {
  return (
    <Card title="Backups" icon={<HardDrive/>}>
      {!b.available ? <NotAvailable note={b.note} /> : (
        <>
          <dl className="grid grid-cols-3 gap-3">
            <Stat label="Newest" value={b.newest ? ago(b.newest.age_hours) : "none"} tone={levelText[b.level]} />
            <Stat label="Size" value={bytes(b.newest?.size_bytes)} />
            <Stat label="Kept" value={`${b.count ?? 0} (${b.daily_count ?? 0} daily)`} />
          </dl>
          {b.newest && <div className={cn("text-[11px]", muted)}><span className="font-mono">{b.newest.name}</span> · {formatDate(b.newest.at, true)}</div>}
          {b.last_status && <div className="flex items-center gap-2 text-[11px]"><span className={muted}>Last attempt</span><JobStatusBadge status={b.last_status} /></div>}
          {b.note ? <p className={cn("text-xs font-medium", levelText[b.level])}>{b.note}</p>
            : <p className={cn("text-xs", muted)}>Warns when the newest backup is older than {b.stale_after_hours ?? 26} hours.</p>}
        </>
      )}
    </Card>
  );
}

function SourcesTable({ rows }: { rows: SourceRow[] }) {
  return (
    <div className={panel}>
      <div className={head}><h3 className="font-display text-[15px] font-bold text-heading">Sources</h3><span className={cn("text-[11px]", muted)}>last 7 days of discovery runs</span></div>
      {rows.length === 0 ? <p className={cn("p-4 text-xs", muted)}>No source has run yet.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead className={thead}><tr><th className={th}>Source</th><th className={th}>State</th><th className={th}>Last success</th><th className={`${th} text-right`}>Failed / runs</th><th className={th}>Last error</th></tr></thead>
            <tbody className="divide-y divide-border/70">
              {rows.map((s) => (
                <tr key={s.key} className="align-top transition-colors hover:bg-paper-sunk/50">
                  <td className={td}><div className="font-medium">{s.name}</div><div className="font-mono text-[10px] text-muted-foreground">{s.key}</div></td>
                  <td className={td}><JobStatusBadge status={sourceTone[s.state]} /><div className="mt-0.5 text-[10px] text-muted-foreground">{s.state}</div></td>
                  <td className={cn(td, muted)}>{s.last_success_at ? ago(s.hours_since_success) : "never"}</td>
                  <td className={cn(td, "text-right readout", s.failures_7d > 0 && "font-semibold text-destructive")}>{s.failures_7d} / {s.runs_7d}</td>
                  <td className={cn(td, "max-w-[22rem] break-words font-mono text-[11px] text-muted-foreground")}>
                    {s.last_failure ?? s.last_error ?? "—"}
                    {s.last_failed_at && <div className="font-sans text-[10px]">{formatDate(s.last_failed_at, true)}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function FreshnessTable({ rows }: { rows: OpsHealth["source_freshness"] }) {
  return (
    <div className={panel}>
      <div className={head}><h3 className="font-display text-[15px] font-bold text-heading">Source freshness</h3><span className={cn("text-[11px]", muted)}>open jobs only</span></div>
      {rows.length === 0 ? <p className={cn("p-4 text-xs", muted)}>No open jobs yet.</p> : (
        <table className="w-full text-left text-xs">
          <thead className={thead}><tr><th className={th}>Source</th><th className={`${th} text-right`}>Open jobs</th><th className={th}>Last confirmed listed</th><th className={th}>Newest found</th></tr></thead>
          <tbody className="divide-y divide-border/70">
            {rows.map((r) => (
              <tr key={r.source} className="transition-colors hover:bg-paper-sunk/50">
                <td className={cn(td, "font-mono")}>{r.source}</td>
                <td className={cn(td, "text-right readout")}>{r.open_jobs.toLocaleString()}</td>
                <td className={cn(td, r.hours_since_verified != null && r.hours_since_verified > 72 ? "text-caution" : muted)}>{r.last_verified_at ? ago(r.hours_since_verified) : "not re-checkable"}</td>
                <td className={cn(td, muted)}>{formatDate(r.newest_discovered_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function FailuresPanel({ d }: { d: OpsHealth }) {
  const jobs = d.background_jobs;
  const disc = d.discovery;
  const wf = d.workflows;
  return (
    <div className={panel}>
      <div className={head}><h3 className="font-display text-[15px] font-bold text-heading">Failed workflows</h3><span className={cn("text-[11px]", muted)}>last 7 days</span></div>
      <dl className="grid grid-cols-2 gap-3 border-y border-border/70 bg-paper-sunk/40 px-5 py-3 sm:grid-cols-4">
        <Stat label="Background job failures" value={jobs.failed_count} tone={jobs.failed_count ? "text-destructive" : undefined} />
        <Stat label="Discovery runs failed" value={`${disc.failed} of ${Object.values(disc.by_status).reduce((a, n) => a + n, 0)}`} tone={disc.failed ? "text-destructive" : undefined} />
        <Stat label="Smart Apply failed / unconfirmed" value={`${wf.apply_failed} / ${wf.apply_uncertain}`} tone={wf.apply_failed + wf.apply_uncertain ? "text-caution" : undefined} />
        <Stat label="Stuck (still running)" value={`${jobs.stuck.length} jobs · ${disc.stuck_running} runs`} tone={jobs.stuck.length + disc.stuck_running ? "text-caution" : undefined} />
      </dl>
      {jobs.recent.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead className={thead}><tr><th className={th}>Background job</th><th className={th}>When</th><th className={th}>Status</th><th className={th}>Error</th></tr></thead>
            <tbody className="divide-y divide-border/70">
              {jobs.recent.map((r, i) => (
                <tr key={`${r.name}-${r.started_at}-${i}`} className="align-top transition-colors hover:bg-paper-sunk/50">
                  <td className={cn(td, "font-mono")}>{r.name}</td>
                  <td className={cn(td, muted, "whitespace-nowrap")}>{formatDate(r.started_at, true)}</td>
                  <td className={td}><JobStatusBadge status={r.status} /><div className="text-[10px] text-muted-foreground">{r.attempts} attempt(s)</div></td>
                  <td className={cn(td, "max-w-[26rem] break-words font-mono text-[11px] text-destructive")}>{r.error ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(disc.failure_types.length > 0 || wf.run_errors.length > 0) && (
        <div className="grid gap-4 px-5 py-4 text-xs sm:grid-cols-2">
          {disc.failure_types.length > 0 && (
            <div>
              <div className={cn("mb-1 text-[11px] font-medium", muted)}>Why discovery runs failed</div>
              <ul className="space-y-0.5">{disc.failure_types.map((f) => <li key={f.type} className="flex justify-between gap-2"><span className="font-mono">{f.type}</span><span className="readout">{f.count}</span></li>)}</ul>
            </div>
          )}
          {wf.run_errors.length > 0 && (
            <div>
              <div className={cn("mb-1 text-[11px] font-medium", muted)}>Errors recorded during runs</div>
              <ul className="space-y-0.5">{wf.run_errors.map((e) => <li key={`${e.type}-${e.platform}`} className="flex justify-between gap-2"><span className="font-mono">{e.type}{e.platform ? ` · ${e.platform}` : ""}</span><span className="readout">{e.count}</span></li>)}</ul>
            </div>
          )}
        </div>
      )}
      {jobs.failed_count === 0 && disc.failed === 0 && wf.run_errors.length === 0 && <p className={cn("px-5 py-4 text-xs", muted)}>No failures in the last 7 days.</p>}
    </div>
  );
}

function ActivityCard({ a }: { a: OpsHealth["user_activity"] }) {
  return (
    <Card title="User activity (counts only)" icon={<Users/>}>
      {a.available === false ? <NotAvailable note={a.note} /> : (
        <dl className="grid grid-cols-3 gap-3">
          <Stat label="Accounts" value={`${a.active_accounts ?? 0} / ${a.accounts ?? 0}`} />
          <Stat label="Signed in, 24 h" value={a.logins_24h ?? 0} />
          <Stat label="Signed in, 7 days" value={a.logins_7d ?? 0} />
          <Stat label="Active, 7 days" value={a.active_users_7d ?? 0} />
          <Stat label="New, 7 days" value={a.signups_7d ?? 0} />
          <Stat label="Signed in, 30 days" value={a.logins_30d ?? 0} />
          <Stat label="Discovery runs, 7 days" value={a.discovery_runs_7d ?? 0} />
          <Stat label="Applied, 7 days" value={a.applications_submitted_7d ?? 0} />
        </dl>
      )}
    </Card>
  );
}

function ExtensionCard({ e }: { e: OpsHealth["extension"] }) {
  return (
    <Card title="Browser extension" icon={<Puzzle/>}>
      {e.available === false ? <NotAvailable note={e.note} /> : (
        <>
          <dl className="grid grid-cols-3 gap-3">
            <Stat label="Connected devices" value={e.connected_devices ?? 0} />
            <Stat label="Used, 24 h" value={e.used_24h ?? 0} />
            <Stat label="Used, 7 days" value={e.used_7d ?? 0} />
            <Stat label="Idle 30+ days" value={e.unused_30d ?? 0} />
            <Stat label="Expired tokens" value={e.expired ?? 0} tone={e.expired ? "text-caution" : undefined} />
            <Stat label="Current version" value={e.bundled_version ?? "not available"} />
          </dl>
          {e.note && <p className={cn("text-xs", muted)}>{e.note}</p>}
        </>
      )}
    </Card>
  );
}

export function OpsHealthPanel() {
  const q = useOpsHealth();
  const d = q.data;
  if (q.isLoading) return <Loader2 className="animate-spin" />;
  if (!d) return <p className="text-sm text-destructive">{errorMessage(q.error)}</p>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className={cn("text-xs", muted)}>Checked {formatDate(d.generated_at, true)}. Anything this server can't see says "not available".</p>
        <button onClick={() => void q.refetch()} className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
          <RefreshCw className={cn("size-3.5", q.isFetching && "animate-spin")} /> Refresh
        </button>
      </div>

      {d.attention.length === 0 ? (
        <div className="flex items-center gap-2 rounded-xl bg-success-tint px-3 py-2 text-xs font-medium text-success">
          <CheckCircle2 className="size-4" aria-hidden /> Nothing needs attention.
        </div>
      ) : (
        <ul className="space-y-1">
          {d.attention.map((a) => (
            <li key={a.text} className={cn("flex items-start gap-2 rounded-xl px-3 py-2 text-xs font-medium",
              a.level === "critical" ? "bg-destructive/10 text-destructive" : "bg-caution-tint text-caution")}>
              {a.level === "critical" ? <OctagonAlert className="mt-px size-3.5 shrink-0" aria-hidden /> : <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />}
              <span className="sr-only">{a.level === "critical" ? "Critical:" : "Warning:"}</span> <span>{a.text}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Disk space" icon={<HardDrive/>}>
          {d.disks.length === 0 ? <NotAvailable /> : d.disks.map((x) => <DiskRow key={x.label} d={x} />)}
        </Card>
        <DatabaseCard db={d.database} />
        <BackupsCard b={d.backups} />
      </div>

      <FailuresPanel d={d} />
      <SourcesTable rows={d.sources} />
      <div className="grid gap-4 lg:grid-cols-2">
        <FreshnessTable rows={d.source_freshness} />
        <div className="space-y-4">
          <ActivityCard a={d.user_activity} />
          <ExtensionCard e={d.extension} />
        </div>
      </div>
    </div>
  );
}
