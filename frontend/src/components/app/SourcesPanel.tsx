import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Database, ShieldCheck, Play, CheckCircle2, AlertTriangle, XCircle, RefreshCw } from "lucide-react";

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
  const [testResult, setTestResult] = useState<Record<string, string>>({});

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
        [sourceId]: `Found ${res.data.jobs_found} jobs`,
      }));
    } catch (err: any) {
      setTestResult((prev) => ({
        ...prev,
        [sourceId]: err.response?.data?.detail || "Test failed",
      }));
    } finally {
      setTestingId(null);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "ok":
        return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
      case "degraded":
        return <AlertTriangle className="h-4 w-4 text-amber-500" />;
      case "failing":
        return <XCircle className="h-4 w-4 text-destructive" />;
      default:
        return <ShieldCheck className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const [reapMessage, setReapMessage] = useState<string | null>(null);

  const handleReap = async () => {
    try {
      const res = await api.post("/discovery/reap-expired?max_age_days=60");
      setReapMessage(`Archived ${res.data.reaped_count} expired postings`);
      setTimeout(() => setReapMessage(null), 4000);
    } catch {
      setReapMessage("Failed to clean stale postings");
      setTimeout(() => setReapMessage(null), 3000);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Database className="h-5 w-5 text-primary" /> Multi-Source Discovery Connectors
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Active verified job sources discovered via Scrapling, APIs, sitemaps, and feeds.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {reapMessage && (
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
              {reapMessage}
            </span>
          )}
          <button
            onClick={handleReap}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted/50"
            title="Scan for listings older than 60 days and mark them expired"
          >
            Archive Stale (60d+)
          </button>
          <button
            onClick={loadSources}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted/50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sources.map((src) => (
          <div key={src.source_id} className="rounded-xl border border-border bg-card p-4 shadow-xs space-y-3 flex flex-col justify-between">
            <div>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h4 className="font-medium text-sm text-foreground">{src.name}</h4>
                  <p className="text-xs text-muted-foreground font-mono">{src.domain}</p>
                </div>
                <div className="flex items-center gap-1.5 text-xs font-medium capitalize">
                  {getStatusIcon(src.status)}
                  <span>{src.status}</span>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
                <span className="rounded-md bg-secondary px-2 py-0.5 text-secondary-foreground font-medium uppercase">
                  {src.category.replace("_", " ")}
                </span>
                <span className="rounded-md bg-muted px-2 py-0.5 text-muted-foreground">
                  {src.access_method.toUpperCase()}
                </span>
                <span className="rounded-md bg-muted px-2 py-0.5 text-muted-foreground">
                  {src.rate_limit_rpm} req/min
                </span>
              </div>
            </div>

            <div className="pt-2 border-t border-border flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                <strong className="text-foreground">{src.jobs_discovered}</strong> discovered
              </span>

              <div className="flex items-center gap-2">
                {testResult[src.source_id] && (
                  <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    {testResult[src.source_id]}
                  </span>
                )}
                <button
                  onClick={() => handleTest(src.source_id)}
                  disabled={testingId === src.source_id}
                  className="inline-flex items-center gap-1 rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary hover:bg-primary/20 disabled:opacity-50"
                >
                  <Play className={`h-3 w-3 ${testingId === src.source_id ? "animate-spin" : ""}`} />
                  Test
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
