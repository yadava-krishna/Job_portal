import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
    <div>
      <div className="mb-1 flex items-center gap-2">
        <Globe className="size-4 text-violet" aria-hidden />
        <h4 className="font-display text-[15px] font-bold tracking-[-0.01em] text-heading">Scan any careers page</h4>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Paste any employer careers page. JobPilot checks for ATS embeds, Schema.org JSON-LD, RSS feeds, and sitemaps.
      </p>

      <form onSubmit={handleSubmit} className="space-y-2.5">
        <div className="grid gap-2 sm:grid-cols-3">
          <Input type="url" placeholder="https://company.com/careers" value={url} onChange={(e) => setUrl(e.target.value)} required
                 aria-label="Careers page URL to scan" className="sm:col-span-2" />
          <Input type="text" placeholder="Company name (optional)" value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                 aria-label="Company name (optional)" />
        </div>
        <Button type="submit" variant="outline" disabled={loading || !url.trim()}>
          {loading ? <><Loader2 className="animate-spin" /> Scanning the page…</> : <><Search /> Scan for jobs</>}
        </Button>
      </form>

      {error && (
        <div role="alert" className="mt-3 flex items-start gap-2 rounded-xl bg-destructive/10 p-3 text-xs text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="mt-3 space-y-2 rounded-xl bg-paper-sunk p-3 text-xs animate-in fade-in-0 slide-in-from-top-1 duration-200">
          <div className="flex flex-wrap items-center justify-between gap-2 font-medium text-foreground">
            <span>Results for {result.company_name}</span>
            <span className={result.jobs_count > 0 ? "inline-flex items-center gap-1 text-success" : "inline-flex items-center gap-1 text-muted-foreground"}>
              {result.jobs_count > 0 && <CheckCircle2 className="size-3.5" />} <span className="readout">{result.jobs_count}</span> jobs found
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-muted-foreground">
            <div>
              <span className="font-medium text-foreground">ATS platform: </span>
              {result.detected_ats ? <span className="font-semibold text-route capitalize">{result.detected_ats}</span> : "None detected"}
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
