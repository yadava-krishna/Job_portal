import { useState } from "react";
import { Loader2, PlugZap, RefreshCw, Settings2, ServerOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useConnection } from "@/contexts/ConnectionContext";
import { ConnectionSettingsDialog } from "@/components/app/ConnectionSettings";
import { formatDate, timeAgo } from "@/lib/format";

/** Full-screen state shown whenever the backend on the host machine is not reachable. */
export function OfflineScreen() {
  const c = useConnection();
  const [retrying, setRetrying] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const unconfigured = c.state === "unconfigured";
  const degraded = c.state === "degraded";

  const retry = async () => {
    setRetrying(true);
    c.retry();
    setTimeout(() => setRetrying(false), 1500);
  };

  const title = unconfigured ? "JobPilot isn't connected yet." : degraded ? "Almost there. The database is down." : "We can't reach JobPilot right now.";
  const cause = unconfigured
    ? "No backend address is configured for this portal yet."
    : degraded
      ? "The job portal backend is running, but its database is not available on the host machine."
      : "The job portal backend is currently not running on the host machine.";
  const checking = c.state === "checking";

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto bg-background p-4 sm:p-6" role="alert" aria-live="assertive">
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-lavender/70 to-transparent" />
      <div className="relative w-full max-w-lg rounded-3xl bg-card p-6 text-center ring-1 ring-border shadow-[var(--shadow-raised)] animate-in fade-in-0 zoom-in-95 duration-300 sm:p-8">
        <div className="mx-auto mb-5 flex size-14 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
          {unconfigured ? <PlugZap className="size-7" aria-hidden /> : <ServerOff className="size-7" aria-hidden />}
        </div>
        <div className="eyebrow mb-2 text-destructive">JOB PORTAL OFFLINE</div>
        <h1 className="font-display text-[26px] leading-tight font-extrabold tracking-[-0.03em] text-heading">{title}</h1>
        <p className="mt-2 text-[14px] text-muted-foreground">{cause}</p>
        <p className="mt-1 text-[14px] text-muted-foreground">Please try again when the service is online.</p>

        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Button size="lg" onClick={retry} disabled={retrying}>
            {retrying ? <Loader2 className="animate-spin" /> : <RefreshCw />} Retry connection
          </Button>
          <Button size="lg" variant="outline" onClick={() => setSettingsOpen(true)}>
            <Settings2 /> Backend address
          </Button>
        </div>

        <dl className="mt-6 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 rounded-2xl bg-paper-sunk/70 p-4 text-left text-[13px]">
          <dt className="text-muted-foreground">Connection</dt>
          <dd className="flex items-center gap-2 font-medium">
            <span aria-hidden className={`size-2 rounded-full ${checking ? "animate-pulse bg-caution" : "bg-destructive"}`} />
            {checking ? "Checking…" : unconfigured ? "Not configured" : degraded ? "Backend degraded" : "Offline"}
          </dd>
          <dt className="text-muted-foreground">Last connected</dt>
          <dd>{c.lastOnlineAt ? `${timeAgo(new Date(c.lastOnlineAt).toISOString())} (${formatDate(new Date(c.lastOnlineAt).toISOString(), true)})` : "Not during this visit"}</dd>
          <dt className="text-muted-foreground">Last check</dt>
          <dd>{c.lastCheckedAt ? timeAgo(new Date(c.lastCheckedAt).toISOString()) : "—"}</dd>
          {c.lastError && (<><dt className="text-muted-foreground">Detail</dt><dd className="break-words">{c.lastError}</dd></>)}
          <dt className="text-muted-foreground">Backend</dt>
          <dd className="readout truncate text-[12px]" title={c.baseUrl ?? ""}>{c.baseUrl ?? "—"}</dd>
        </dl>
        <p className="mt-4 text-xs text-muted-foreground">Checking automatically every few seconds. The portal reconnects on its own.</p>
      </div>
      <ConnectionSettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
