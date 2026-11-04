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

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background p-6" role="alert" aria-live="assertive">
      <div className="w-full max-w-lg text-center">
        <div className="mx-auto mb-6 flex size-16 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
          {unconfigured ? <PlugZap className="size-8" /> : <ServerOff className="size-8" />}
        </div>
        <h1 className="text-3xl font-bold tracking-tight">JOB PORTAL OFFLINE</h1>
        <p className="mt-3 text-muted-foreground">
          {unconfigured
            ? "No backend address is configured for this portal yet."
            : degraded
              ? "The job portal backend is running, but its database is not available on the host machine."
              : "The job portal backend is currently not running on the host machine."}
        </p>
        <p className="mt-1 text-muted-foreground">Please try again when the service is online.</p>

        <dl className="mx-auto mt-8 grid max-w-sm grid-cols-[auto_1fr] gap-x-4 gap-y-2 rounded-xl border bg-card p-4 text-left text-sm">
          <dt className="text-muted-foreground">Connection</dt>
          <dd className="flex items-center gap-2 font-medium">
            <span className={`size-2 rounded-full ${c.state === "checking" ? "animate-pulse bg-amber-500" : "bg-destructive"}`} />
            {c.state === "checking" ? "Checking…" : unconfigured ? "Not configured" : degraded ? "Backend degraded" : "Offline"}
          </dd>
          <dt className="text-muted-foreground">Last connected</dt>
          <dd>{c.lastOnlineAt ? `${timeAgo(new Date(c.lastOnlineAt).toISOString())} (${formatDate(new Date(c.lastOnlineAt).toISOString(), true)})` : "Not during this visit"}</dd>
          <dt className="text-muted-foreground">Last check</dt>
          <dd>{c.lastCheckedAt ? timeAgo(new Date(c.lastCheckedAt).toISOString()) : "—"}</dd>
          {c.lastError && (<><dt className="text-muted-foreground">Detail</dt><dd className="break-words">{c.lastError}</dd></>)}
          <dt className="text-muted-foreground">Backend</dt>
          <dd className="truncate" title={c.baseUrl ?? ""}>{c.baseUrl ?? "—"}</dd>
        </dl>

        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Button onClick={retry} disabled={retrying}>
            {retrying ? <Loader2 className="animate-spin" /> : <RefreshCw />} Retry connection
          </Button>
          <Button variant="outline" onClick={() => setSettingsOpen(true)}>
            <Settings2 /> Backend address
          </Button>
        </div>
        <p className="mt-4 text-xs text-muted-foreground">Checking automatically every few seconds. The portal reconnects on its own.</p>
      </div>
      <ConnectionSettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
