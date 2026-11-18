import { useEffect, useState } from "react";
import { CheckCircle2, Copy, Download, KeyRound, Loader2, Puzzle, Unplug } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { errorMessage } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import { useCreatePairingCode, useDisconnectDevice, useExtensionDevices } from "@/services/queries";
import type { PairingCode } from "@/types/api";
import { smartApplyStatus, type SmartApplyStatus } from "@/lib/smartApply";

/** Connect the "JobPilot Smart Apply" browser extension with a one-time code, and disconnect browsers. */
export function ExtensionSettings() {
  const devices = useExtensionDevices();
  const create = useCreatePairingCode();
  const disconnect = useDisconnectDevice();
  const [code, setCode] = useState<PairingCode | null>(null);
  const [left, setLeft] = useState(0);
  const [here, setHere] = useState<SmartApplyStatus | null | undefined>(undefined);  // Smart Apply in this browser

  useEffect(() => {
    const check = () => { smartApplyStatus().then(setHere).catch(() => setHere(null)); };
    check();
    const t = window.setInterval(check, 4000);  // updates as soon as the code is typed into the extension
    window.addEventListener("focus", check);
    return () => { window.clearInterval(t); window.removeEventListener("focus", check); };
  }, []);

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
          <CardTitle className="flex items-center gap-2"><Puzzle className="size-5" /> Smart Apply browser extension</CardTitle>
          <CardDescription>
            Click <strong>Apply with Smart Apply</strong> on a job in JobPilot and the employer's form opens and fills itself from your
            profile, then shows a review of the form exactly as it is filled.
            On Greenhouse, Lever and Ashby you can submit from the review once you authorise that application; on Workday, iCIMS,
            SuccessFactors and other employer sites (allowed one by one) it fills and you submit on the page. It never runs on
            LinkedIn, Naukri or Indeed, and never asks for your JobPilot password.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div data-testid="smart-apply-here" className={here?.connected ? "flex items-center gap-2 rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100" : "rounded-lg border p-3"}>
            {here === undefined && <span className="flex items-center gap-2 text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Checking this browser…</span>}
            {here?.connected && <><CheckCircle2 className="size-4 shrink-0" /><span><strong>All set in this browser</strong> (version {here.version}). Use Apply with Smart Apply on any Greenhouse, Lever or Ashby job.</span></>}
            {here && !here.connected && <span><strong>Installed, not connected yet.</strong> Create a connection code below and type it into the extension.</span>}
            {here === null && <span className="text-muted-foreground"><strong className="text-foreground">Not installed in this browser yet.</strong> Download it and follow the four steps below.</span>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" render={<a href={`${import.meta.env.BASE_URL}downloads/jobpilot-smart-apply-2.1.0.zip`} download />}>
              <Download /> Download the extension (.zip, 70 KB)
            </Button>
            <span className="text-xs text-muted-foreground">Version 2.1.0 · Chrome, Edge or Brave</span>
          </div>
          <ol className="list-decimal space-y-1 pl-5 text-muted-foreground" data-testid="extension-install-steps">
            <li>Unzip the download (right-click it → <strong className="text-foreground">Extract Here</strong>). You get a folder called <strong className="text-foreground">JobPilot-Smart-Apply</strong>; keep it somewhere you won't delete, because Chrome loads the extension from it every time.</li>
            <li>Open <span className="font-mono text-foreground">chrome://extensions</span>, switch on <strong className="text-foreground">Developer mode</strong> (top right), click <strong className="text-foreground">Load unpacked</strong> and select the <strong className="text-foreground">JobPilot-Smart-Apply</strong> folder itself (not the .zip, and not your Downloads folder).</li>
            <li>Pin <strong className="text-foreground">JobPilot Smart Apply</strong> from the puzzle-piece menu.</li>
            <li>Create a connection code below and type it into the extension within 5 minutes (already installed an older version? Download this one, unzip it over the same folder, and click the reload arrow on the extension in chrome://extensions). The code works once; the browser stays connected for 90 days, or until you disconnect it here.</li>
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
