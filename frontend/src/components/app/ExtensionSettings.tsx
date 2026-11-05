import { useEffect, useState } from "react";
import { Copy, KeyRound, Loader2, Puzzle, Unplug } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import { useCreatePairingCode, useDisconnectDevice, useExtensionDevices } from "@/services/queries";
import type { PairingCode } from "@/types/api";

/** Connect the "Fill with JobPilot" browser extension with a one-time code, and disconnect browsers. */
export function ExtensionSettings() {
  const devices = useExtensionDevices();
  const create = useCreatePairingCode();
  const disconnect = useDisconnectDevice();
  const [code, setCode] = useState<PairingCode | null>(null);
  const [left, setLeft] = useState(0);

  useEffect(() => {
    if (!code) return;
    const tick = () => {
      const s = Math.max(0, Math.round((new Date(code.expires_at).getTime() - Date.now()) / 1000));
      setLeft(s);
      if (s === 0) { setCode(null); void devices.refetch(); }
    };
    tick();
    const t = window.setInterval(tick, 1000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const newCode = () => create.mutate(undefined, { onSuccess: setCode, onError: (e) => toast.error(errorMessage(e)) });

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Puzzle className="size-5" /> Fill with JobPilot</CardTitle>
          <CardDescription>
            The browser extension fills Greenhouse, Lever and Ashby application forms from your profile when you click Fill.
            You review every field and press Submit yourself. It never asks for your JobPilot password.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
            <li>Install the extension (see the installation guide in the extension folder).</li>
            <li>Create a connection code below and type it into the extension within 5 minutes.</li>
            <li>The code works once. The browser stays connected for 90 days, or until you disconnect it here.</li>
          </ol>
          {code ? (
            <div className="rounded-xl border bg-muted/40 p-4 text-center">
              <div className="text-xs text-muted-foreground">Connection code</div>
              <div className="my-1 font-mono text-3xl font-semibold tracking-[0.2em]" aria-live="polite">{code.code}</div>
              <div className="text-xs text-muted-foreground">Expires in {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")} · single use</div>
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => { void navigator.clipboard.writeText(code.code); toast.success("Copied"); }}><Copy /> Copy</Button>
            </div>
          ) : (
            <Button onClick={newCode} disabled={create.isPending}>{create.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />} Create connection code</Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Connected browsers</CardTitle>
          <CardDescription>Each connection can only fill forms and record applications for your account. Disconnecting takes effect immediately.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {devices.isLoading && <Loader2 className="animate-spin" />}
          {devices.data?.length === 0 && <p className="text-muted-foreground">No browser is connected.</p>}
          {devices.data?.map((d) => (
            <div key={d.id} className="flex items-center justify-between gap-3 rounded-lg border p-3">
              <div className="min-w-0">
                <div className="truncate font-medium">{d.name}</div>
                <div className="text-xs text-muted-foreground">
                  Connected {formatDate(d.created_at)} · last used {d.last_used_at ? timeAgo(d.last_used_at) : "never"} · expires {formatDate(d.expires_at)}
                </div>
              </div>
              <Button size="sm" variant="outline" disabled={disconnect.isPending}
                      onClick={() => disconnect.mutate(d.id, { onSuccess: () => toast.success(`${d.name} disconnected`), onError: (e) => toast.error(errorMessage(e)) })}>
                <Unplug /> Disconnect
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
