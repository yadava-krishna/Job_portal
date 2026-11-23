import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Info, Loader2, RefreshCw, Sparkles, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { fetchPreview, useStudioLayout, type StudioSettings } from "./api";

/**
 * The live preview is the real exported PDF (rendered by the backend), so page breaks and layout are exactly what
 * the employer receives. It refreshes ~1 s after each successful save (keyed by the saved revision).
 */
export function PreviewPane({ versionId, revision, templateName, onApplySettings, readOnly }: {
  versionId: number; revision: number; templateName?: string; onApplySettings?: (s: Partial<StudioSettings>) => void; readOnly?: boolean;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [pages, setPages] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const urlRef = useRef<string | null>(null);
  const lastNonce = useRef(0);
  // Brief highlight when a re-rendered preview lands, so it's obvious the paper caught up with the edit.
  const [fresh, setFresh] = useState(false);
  const freshTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(freshTimer.current), []);

  useEffect(() => {
    let cancelled = false;
    // First load and manual refresh are immediate; refreshes after a save wait ~1 s.
    const delay = urlRef.current && lastNonce.current === nonce ? 1000 : 0;
    lastNonce.current = nonce;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const { blob, pages: n, revision: rev } = await fetchPreview(versionId);
        // A PDF of an older revision (a slow response overtaken by a save) is never shown as current.
        if (cancelled || (rev != null && rev < revision)) return;
        const next = typeof URL.createObjectURL === "function" ? URL.createObjectURL(blob) : null;
        if (urlRef.current) {
          URL.revokeObjectURL(urlRef.current);
          setFresh(true);
          clearTimeout(freshTimer.current);
          freshTimer.current = setTimeout(() => setFresh(false), 1400);
        }
        urlRef.current = next;
        setUrl(next);
        setPages(n);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(errorMessage(e, "Couldn't render the preview"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, delay);
    return () => { cancelled = true; clearTimeout(t); };
  }, [versionId, revision, nonce]);

  // Revoke the last blob URL when leaving the editor.
  useEffect(() => () => { if (urlRef.current) URL.revokeObjectURL(urlRef.current); urlRef.current = null; }, []);

  return (
    <div className="flex h-full min-h-[70dvh] flex-col overflow-hidden rounded-2xl bg-card ring-1 ring-border lg:min-h-0">
      <div className="flex shrink-0 items-center gap-2 border-b px-3.5 py-2 text-xs">
        <span className={cn("size-2 rounded-full transition-colors duration-300", loading ? "bg-caution" : error ? "bg-destructive" : "bg-route")} aria-hidden />
        <span className="font-display text-[13px] font-bold text-heading">Live preview</span>
        <span className="truncate text-muted-foreground">{templateName ? `${templateName} · ` : ""}{pages != null ? `${pages} page${pages === 1 ? "" : "s"}` : "—"}</span>
        <span className="ml-auto flex shrink-0 items-center gap-1 text-muted-foreground" aria-live="polite">
          {loading ? <><Loader2 className="size-3 animate-spin" /> Updating…</>
            : fresh ? <span className="inline-flex items-center gap-1 font-medium text-violet animate-in fade-in-0 duration-200"><Sparkles className="size-3" /> Updated</span> : null}
        </span>
        <Button size="icon-xs" variant="ghost" aria-label="Refresh preview" onClick={() => setNonce((n) => n + 1)} disabled={loading}><RefreshCw /></Button>
      </div>
      <LayoutBar versionId={versionId} revision={revision} onApply={readOnly ? undefined : onApplySettings} />
      <div className="relative min-h-0 flex-1 bg-paper-sunk p-2.5 sm:p-3">
        {error ? (
          <div className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{error}</div>
        ) : url ? (
          <iframe title="Resume preview (PDF)" src={url}
                  className={cn("h-full min-h-[60dvh] w-full rounded-lg bg-white shadow-[var(--shadow-raised)] ring-1 transition-[box-shadow,opacity] duration-300 ease-[cubic-bezier(.2,0,0,1)] lg:min-h-0",
                    fresh ? "ring-2 ring-violet/60" : "ring-border", loading && "opacity-80")} />
        ) : (
          <div className="flex h-full min-h-[50dvh] flex-col items-center justify-center gap-2 rounded-lg border border-dashed text-sm text-muted-foreground lg:min-h-0">
            {loading ? <><Loader2 className="animate-spin" /> Rendering PDF…</> : "No preview yet"}
          </div>
        )}
      </div>
    </div>
  );
}

/** Page count, how full each page is, and layout warnings. Fit suggestions change settings only when clicked. */
function LayoutBar({ versionId, revision, onApply }: { versionId: number; revision: number; onApply?: (s: Partial<StudioSettings>) => void }) {
  const layout = useStudioLayout(versionId, revision);
  const r = layout.data;
  if (!r) return null;
  const warnings = r.warnings.filter((w) => w.level === "warning");
  const infos = r.warnings.filter((w) => w.level === "info");
  return (
    <div className="shrink-0 space-y-1.5 border-b px-3.5 py-2 text-xs" aria-live="polite">
      <div className="flex flex-wrap items-center gap-2">
        <span className="readout font-medium text-foreground" data-testid="layout-pages">{r.pages} page{r.pages === 1 ? "" : "s"}</span>
        <span className="flex items-center gap-1" aria-label="How full each page is">
          {r.page_fill.map((f, i) => (
            <span key={i} title={`Page ${i + 1}: about ${Math.round(f * 100)}% full`} className="flex h-[18px] w-3.5 items-end overflow-hidden rounded-[3px] bg-paper-sunk ring-1 ring-border">
              <span className={cn("w-full transition-[height] duration-300", f < 0.2 && r.pages > 1 ? "bg-caution" : "bg-route/60")} style={{ height: `${Math.max(6, Math.round(f * 100))}%` }} />
            </span>
          ))}
        </span>
        {!warnings.length && <span className="font-medium text-success">Layout looks good</span>}
      </div>
      {warnings.map((w) => <p key={w.message} className="flex gap-1.5 text-caution"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{w.message}</p>)}
      {infos.map((w) => <p key={w.message} className="flex gap-1.5 text-muted-foreground"><Info className="mt-0.5 size-3.5 shrink-0" />{w.message}</p>)}
      {onApply && r.fit_suggestions.map((s) => (
        <div key={s.label} className="flex flex-wrap items-center gap-2 rounded-lg bg-lavender/50 px-2 py-1.5 dark:bg-lavender/10">
          <Wand2 className="size-3.5 shrink-0 text-violet" aria-hidden />
          <span className="min-w-0 flex-1 text-foreground/80">{s.label} fits it on {s.pages} page{s.pages === 1 ? "" : "s"} without removing anything.</span>
          <Button size="xs" variant="outline" className="bg-card" onClick={() => onApply(s.settings)}>Apply</Button>
        </div>
      ))}
    </div>
  );
}
