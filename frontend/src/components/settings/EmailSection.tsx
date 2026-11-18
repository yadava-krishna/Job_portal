import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Field } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useEmailIntegration, useSaveEmail } from "@/services/queries";
import { FieldGroup, Panel } from "./primitives";

/** Read the user's own job-alert e-mails over IMAP (read-only). */
export function EmailSection() {
  const { data } = useEmailIntegration();
  const save = useSaveEmail();
  const [f, setF] = useState({ enabled: false, imap_host: "imap.gmail.com", imap_port: 993, username: "", password: "", folder: "INBOX", lookback_days: 2 });
  useEffect(() => { if (data) setF((x) => ({ ...x, ...data, username: data.username ?? "", password: "" })); }, [data]);
  return (
    <Panel title="Job-alert emails"
           description={<>
             Read your own LinkedIn, Indeed and Naukri alert emails (read-only) to discover jobs, and detect "application sent" confirmations.
             Use an app password (for Gmail: Google Account → Security → App passwords). It is stored encrypted.
           </>}
           actions={
             <div className="flex items-center gap-2 text-[13px] font-medium">
               <span aria-hidden className="hidden w-6 text-right text-muted-foreground sm:inline">{f.enabled ? "On" : "Off"}</span>
               <Switch checked={f.enabled} onCheckedChange={(c) => setF({ ...f, enabled: !!c })} aria-label="Enable alert emails" />
             </div>
           }>
      <div className="space-y-6">
        <FieldGroup title="Mailbox">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Email address" htmlFor="e-user"><Input id="e-user" autoComplete="off" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
            <Field label="App password" htmlFor="e-pass" hint={data?.has_password ? "A password is stored. Leave empty to keep it." : undefined}>
              <Input id="e-pass" type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
            </Field>
          </div>
        </FieldGroup>
        <FieldGroup title="Server" hint="The defaults work for Gmail. Change them only for another provider.">
          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_7rem] md:grid-cols-[minmax(0,1fr)_7rem_minmax(0,10rem)_8rem]">
            <Field label="IMAP server" htmlFor="e-host"><Input id="e-host" value={f.imap_host} onChange={(e) => setF({ ...f, imap_host: e.target.value })} /></Field>
            <Field label="Port" htmlFor="e-port"><Input id="e-port" type="number" className="readout" value={f.imap_port} onChange={(e) => setF({ ...f, imap_port: Number(e.target.value) })} /></Field>
            <Field label="Folder" htmlFor="e-folder"><Input id="e-folder" value={f.folder} onChange={(e) => setF({ ...f, folder: e.target.value })} /></Field>
            <Field label="Look back (days)" htmlFor="e-days"><Input id="e-days" type="number" className="readout" min={1} max={14} value={f.lookback_days} onChange={(e) => setF({ ...f, lookback_days: Number(e.target.value) })} /></Field>
          </div>
        </FieldGroup>
        <div data-save-bar className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {data?.last_checked_at ? <>Last checked {timeAgo(data.last_checked_at)}{data.last_error ? <span className="text-destructive"> · {data.last_error}</span> : ""}</> : "Not checked yet."}
          </p>
          <Button onClick={() => save.mutate({ ...f, password: f.password || null }, { onSuccess: () => { toast.success("Saved. Locked in."); setF((x) => ({ ...x, password: "" })); }, onError: (e) => toast.error(errorMessage(e)) })} disabled={save.isPending}>
            {save.isPending && <Loader2 className="animate-spin" />} Save
          </Button>
        </div>
      </div>
    </Panel>
  );
}
