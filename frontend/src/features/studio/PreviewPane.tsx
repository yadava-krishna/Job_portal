import { useEffect, useRef, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api";
import { fetchPreview } from "./api";

/**
 * The live preview is the real exported PDF (rendered by the backend), so page breaks and layout are exactly what
 * the employer receives. It refreshes ~1 s after each successful save (keyed by the saved revision).
 */
export function PreviewPane({ versionId, revision, templateName }: { versionId: number; revision: number; templateName?: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [pages, setPages] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const urlRef = useRef<string | null>(null);
  const lastNonce = useRef(0);

  useEffect(() => {
    let cancelled = false;
    // First load and manual refresh are immediate; refreshes after a save wait ~1 s.
    const delay = urlRef.current && lastNonce.current === nonce ? 1000 : 0;
    lastNonce.current = nonce;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const { blob, pages: n } = await fetchPreview(versionId);
        if (cancelled) return;
        const next = typeof URL.createObjectURL === "function" ? URL.createObjectURL(blob) : null;
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
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
    <div className="flex h-full min-h-[70dvh] flex-col overflow-hidden rounded-xl border bg-muted/40">
      <div className="flex items-center gap-2 border-b bg-card px-3 py-1.5 text-xs">
        <span className="font-medium">Preview</span>
        <span className="text-muted-foreground">{templateName ? `${templateName} · ` : ""}{pages != null ? `${pages} page${pages === 1 ? "" : "s"}` : "—"}</span>
        <span className="ml-auto flex items-center gap-1 text-muted-foreground" aria-live="polite">
          {loading && <><Loader2 className="size-3 animate-spin" /> Updating…</>}
        </span>
        <Button size="icon-xs" variant="ghost" aria-label="Refresh preview" onClick={() => setNonce((n) => n + 1)} disabled={loading}><RefreshCw /></Button>
      </div>
      {error ? (
        <div className="m-3 rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</div>
      ) : url ? (
        <iframe title="Resume preview (PDF)" src={url} className="w-full flex-1 bg-white" />
      ) : (
        <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
          {loading ? <><Loader2 className="animate-spin" /> Rendering PDF…</> : "No preview yet"}
        </div>
      )}
    </div>
  );
}
