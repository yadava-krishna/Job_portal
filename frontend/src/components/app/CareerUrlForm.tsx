import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { Globe, Search, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";

interface AnalysisResult {
  url: string;
  company_name: string;
  detected_ats: string | null;
  ats_token: string | null;
  has_json_ld: boolean;
  json_ld_count: number;
  discovered_feed_url: string | null;
  discovered_sitemap_url: string | null;
  jobs_count: number;
  errors: string[];
}

interface CareerUrlFormProps {
  onSuccess?: () => void;
}

export function CareerUrlForm({ onSuccess }: CareerUrlFormProps) {
  const [url, setUrl] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await api.post<AnalysisResult>("/companies/career-url", {
        url: url.trim(),
        company_name: companyName.trim() || undefined,
      });
      setResult(res.data);
      if (res.data.jobs_count > 0 && onSuccess) {
        onSuccess();
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to analyze career URL. Ensure the address is public and https.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-xs">
      <div className="flex items-center gap-2 mb-3">
        <Globe className="h-5 w-5 text-primary" />
        <h3 className="font-semibold text-foreground text-base">Add Company Career URL</h3>
      </div>
      <p className="text-xs text-muted-foreground mb-4">
        Paste any employer careers page. JobPilot checks for ATS embeds, Schema.org JSON-LD, RSS feeds, and sitemaps.
      </p>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <input
              type="url"
              placeholder="https://company.com/careers"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <input
              type="text"
              placeholder="Company name (optional)"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-hidden focus:ring-2 focus:ring-ring"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || !url.trim()}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Scanning & Discovering...
            </>
          ) : (
            <>
              <Search className="h-4 w-4" />
              Analyze & Discover Jobs
            </>
          )}
        </button>
      </form>

      {error && (
        <div className="mt-4 flex items-start gap-2 rounded-lg bg-destructive/10 p-3 text-xs text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="mt-4 rounded-lg border border-border bg-muted/40 p-3 space-y-2 text-xs">
          <div className="flex items-center justify-between font-medium text-foreground">
            <span>Results for {result.company_name}</span>
            <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-3.5 w-3.5" /> {result.jobs_count} jobs found
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-muted-foreground">
            <div>
              <span className="font-medium text-foreground">ATS Platform: </span>
              {result.detected_ats ? (
                <span className="capitalize text-primary font-semibold">{result.detected_ats}</span>
              ) : (
                "None detected"
              )}
            </div>
            <div>
              <span className="font-medium text-foreground">Structured JSON-LD: </span>
              {result.has_json_ld ? `${result.json_ld_count} postings` : "None"}
            </div>
            {result.discovered_feed_url && (
              <div className="col-span-2 truncate">
                <span className="font-medium text-foreground">Feed: </span>
                <span className="font-mono">{result.discovered_feed_url}</span>
              </div>
            )}
            {result.discovered_sitemap_url && (
              <div className="col-span-2 truncate">
                <span className="font-medium text-foreground">Sitemap: </span>
                <span className="font-mono">{result.discovered_sitemap_url}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
