import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Archive, Loader2, Play, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusDot, type DotTone } from "@/components/app/discovery";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

interface SourceConnector {
  source_id: string;
  name: string;
  domain: string;
  category: string;
  access_method: string;
  permission_status: string;
  is_discoverable: boolean;
  status: string;
  rate_limit_rpm: number;
  last_success_at: string | null;
  last_error: string | null;
  jobs_discovered: number;
}

export function SourcesPanel() {
  const [sources, setSources] = useState<SourceConnector[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; text: string }>>({});

  const loadSources = async () => {
    try {
      setLoading(true);
      const res = await api.get<SourceConnector[]>("/discovery/connectors");
      setSources(res.data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSources();
  }, []);

  const handleTest = async (sourceId: string) => {
    setTestingId(sourceId);
    try {
      const res = await api.post(`/discovery/connectors/${sourceId}/test`);
      setTestResult((prev) => ({
        ...prev,
        [sourceId]: { ok: true, text: `Found ${res.data.jobs_found} jobs` },
      }));
    } catch (err: any) {
      setTestResult((prev) => ({
        ...prev,
        [sourceId]: { ok: false, text: err.response?.data?.detail || "Test failed" },
      }));
    } finally {
      setTestingId(null);
    }
  };

  const statusMeta = (status: string): [DotTone, string, string] => {
    switch (status) {
      case "ok": return ["healthy", "Healthy", "text-success"];
      case "degraded": return ["attention", "Degraded", "text-caution"];
      case "failing": return ["failing", "Failing", "text-destructive"];
      default: return ["idle", status === "unknown" ? "Not checked" : status.replace(/_/g, " "), "text-muted-foreground"];
    }
  };

  const [reapMessage, setReapMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const handleReap = async () => {
    try {
      const res = await api.post("/discovery/reap-expired?max_age_days=60");
      setReapMessage({ ok: true, text: `Archived ${res.data.reaped_count} expired postings` });
      setTimeout(() => setReapMessage(null), 4000);
    } catch {
      setReapMessage({ ok: false, text: "Failed to clean stale postings" });
      setTimeout(() => setReapMessage(null), 3000);
    }
  };

  return (
    <section className="rounded-2xl bg-card ring-1 ring-border">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 font-display text-[15px] font-bold tracking-[-0.01em] text-heading">
            Discovery connectors
            {sources.length > 0 && <span className="readout rounded-full bg-paper-sunk px-2 py-px text-[11px] font-medium text-muted-foreground ring-1 ring-inset ring-border">{sources.length}</span>}
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">Verified job sources reached through APIs, sitemaps and feeds.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {reapMessage && (
            <span role="status" className={cn("text-xs font-medium", reapMessage.ok ? "text-success" : "text-destructive")}>{reapMessage.text}</span>
          )}
          <Button size="sm" variant="outline" onClick={handleReap} title="Scan for listings older than 60 days and mark them expired">
            <Archive /> Archive stale (60d+)
          </Button>
          <Button size="sm" variant="ghost" onClick={loadSources} disabled={loading}>
            <RefreshCw className={cn(loading && "animate-spin")} /> Refresh
          </Button>
        </div>
      </div>

      {loading && !sources.length ? (
        <div className="flex items-center gap-2 px-4 py-6 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Loading connectors…</div>
      ) : !sources.length ? (
        <p className="px-4 py-6 text-sm text-muted-foreground">No connectors reported.</p>
      ) : (
        <ul className="divide-y">
          {sources.map((src) => {
            const [tone, label, cls] = statusMeta(src.status);
            const result = testResult[src.source_id];
            return (
              <li key={src.source_id} className="grid gap-x-4 gap-y-2 px-4 py-3 text-sm sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] sm:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="font-medium text-foreground">{src.name}</span>
                    <span className="font-mono text-[11px] text-muted-foreground">{src.domain}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1.5 text-[10.5px]">
                    <span className="rounded-full bg-lavender px-2 py-px font-medium text-violet uppercase">{src.category.replace(/_/g, " ")}</span>
                    <span className="rounded-full bg-paper-sunk px-2 py-px text-muted-foreground ring-1 ring-inset ring-border">{src.access_method.toUpperCase()}</span>
                    <span className="readout rounded-full bg-paper-sunk px-2 py-px text-muted-foreground ring-1 ring-inset ring-border">{src.rate_limit_rpm} req/min</span>
                  </div>
                </div>
                <div className="min-w-0 text-xs">
                  <div className="flex items-center gap-1.5">
                    <StatusDot tone={tone} />
                    <span className={cn("font-medium capitalize", cls)}>{label}</span>
                  </div>
                  <div className="mt-0.5 text-muted-foreground">
                    <span className="readout font-semibold text-foreground">{src.jobs_discovered}</span> discovered
                    {src.last_success_at && <> · last OK {timeAgo(src.last_success_at)}</>}
                  </div>
                  {src.last_error && <div className="mt-0.5 truncate text-caution" title={src.last_error}>{src.last_error}</div>}
                </div>
                <div className="flex items-center gap-2 sm:justify-end">
                  {result && (
                    <span className={cn("text-[11px] font-medium", result.ok ? "text-success" : "text-destructive")}>{result.text}</span>
                  )}
                  <Button size="xs" variant="outline" onClick={() => handleTest(src.source_id)} disabled={testingId === src.source_id}>
                    {testingId === src.source_id ? <Loader2 className="animate-spin" /> : <Play />} Test
                  </Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
