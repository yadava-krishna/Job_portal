import { useEffect, useState } from "react";
import { CheckCircle2, Copy, Download, KeyRound, Loader2, Puzzle, Unplug } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/settings/primitives";
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
    <div className="space-y-5">
      <Panel title={<span className="flex items-center gap-2"><Puzzle className="size-4 text-route" aria-hidden /> Smart Apply browser extension</span>}
             description={<>
            Click <strong>Apply with Smart Apply</strong> on a job in JobPilot and the employer's form opens and fills itself from your
            profile, then shows a review of the form exactly as it is filled.
            On Greenhouse, Lever and Ashby you can submit from the review once you authorise that application; on Workday, iCIMS,
            SuccessFactors and other employer sites (allowed one by one) it fills and you submit on the page. It never runs on
            LinkedIn, Naukri or Indeed, and never asks for your JobPilot password.
          </>}>
        <div className="space-y-5 text-sm">
          <div data-testid="smart-apply-here" aria-live="polite" className={here?.connected ? "flex items-start gap-2.5 rounded-xl bg-success-tint p-3.5 ring-1 ring-success/30 animate-in fade-in-0 duration-200" : "rounded-xl bg-paper-sunk/70 p-3.5 ring-1 ring-border"}>
            {here === undefined && <span className="flex items-center gap-2 text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Checking this browser…</span>}
            {here?.connected && <><CheckCircle2 className="jp-bump mt-0.5 size-4 shrink-0 text-success" /><span><strong>All set in this browser</strong> (version {here.version}). Use Apply with Smart Apply on any Greenhouse, Lever or Ashby job.</span></>}
            {here && !here.connected && <span><strong>Installed, not connected yet.</strong> Create a connection code below and type it into the extension.</span>}
            {here === null && <span className="text-muted-foreground"><strong className="text-foreground">Not installed in this browser yet.</strong> Download it and follow the four steps below.</span>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" render={<a href={`${import.meta.env.BASE_URL}downloads/jobpilot-smart-apply-2.4.0.zip`} download />}>
              <Download /> Download the extension (.zip, 70 KB)
            </Button>
            <span className="text-xs text-muted-foreground"><span className="readout">Version 2.4.0</span> · Chrome, Edge or Brave</span>
          </div>
          <ol className="list-decimal space-y-2 pl-5 leading-relaxed text-muted-foreground marker:font-semibold marker:text-route" data-testid="extension-install-steps">
            <li>Unzip the download (right-click it → <strong className="text-foreground">Extract Here</strong>, or <strong className="text-foreground">Extract All</strong> on Windows). You get a folder called <strong className="text-foreground">jobpilot-smart-apply-2.4.0</strong> with a file named manifest.json inside. Keep it somewhere you won't delete, because Chrome loads the extension from it every time.</li>
            <li>Open <span className="font-mono text-foreground">chrome://extensions</span>, switch on <strong className="text-foreground">Developer mode</strong> (top right), click <strong className="text-foreground">Load unpacked</strong> and select the <strong className="text-foreground">jobpilot-smart-apply-2.4.0</strong> folder (the one with manifest.json directly inside). Chrome says "Manifest file is missing"? You picked a folder one level too high or too low.</li>
            <li>Pin <strong className="text-foreground">JobPilot Smart Apply</strong> from the puzzle-piece menu.</li>
            <li>Create a connection code below and type it into the extension within 5 minutes (already installed an older version? Download this one, unzip it over the same folder, and click the reload arrow on the extension in chrome://extensions). The code works once; the browser stays connected for 90 days, or until you disconnect it here.</li>
          </ol>
          {code ? (
            <div className="rounded-xl bg-lavender/60 p-5 text-center ring-1 ring-violet/25 animate-in fade-in-0 zoom-in-95 duration-200">
              <div className="text-xs text-muted-foreground">Connection code</div>
              <div className="readout my-1 text-3xl font-semibold tracking-[0.2em] text-heading" aria-live="polite">{code.code}</div>
              <div className="readout text-xs text-muted-foreground">Expires in {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")} · single use</div>
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => { void navigator.clipboard.writeText(code.code); toast.success("Copied"); }}><Copy /> Copy</Button>
            </div>
          ) : (
            <Button onClick={newCode} disabled={create.isPending}>{create.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />} Create connection code</Button>
          )}
        </div>
      </Panel>

      <Panel title="Connected browsers"
             description="Each connection can only fill forms and record applications for your account. Disconnecting takes effect immediately.">
        <div className="space-y-2 text-sm">
          {devices.isLoading && <Loader2 className="animate-spin" />}
          {devices.data?.length === 0 && <p className="rounded-xl bg-paper-sunk/70 p-3.5 text-muted-foreground ring-1 ring-border">No browser is connected.</p>}
          {devices.data?.map((d) => (
            <div key={d.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl p-3.5 ring-1 ring-border">
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
        </div>
      </Panel>
    </div>
  );
}
