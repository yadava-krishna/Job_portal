// Admin only (the backend enforces it): set up LinkedIn or Indeed sign-in for this JobPilot server, step by step.
// The client secret is write-only: it's sent once, stored encrypted on the backend, and never comes back to any browser.
// "Test connection" runs the real sign-in on the portal's own page; a server using the local simulator can't be tested.
import { useId, useState } from "react";
import { Check, CircleAlert, Copy, ExternalLink, KeyRound, Loader2, ShieldCheck, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Field, LoadingState } from "@/components/app/common";
import { Chip, type ChipTone } from "@/features/apply/parts";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PortalLogo } from "./PortalLogo";
import { leaveForSignIn, when, type SetupRow, type SetupState } from "./types";

const STATE: Record<SetupState, [string, ChipTone]> = {
  not_configured: ["Not configured", "neutral"], simulated: ["Local simulator", "warn"], ready_to_test: ["Ready to test", "check"],
  verified: ["Verified", "ok"], authorization_required: ["Provider authorization required", "warn"], failed: ["Test failed", "fail"],
};

const useSetupRows = (enabled: boolean) =>
  useQuery({ queryKey: ["portal-setup"], enabled, queryFn: async () => (await api.get<SetupRow[]>("/admin/portals")).data });

export function SetupSheet({ provider, onClose }: { provider: "linkedin" | "indeed" | null; onClose: () => void }) {
  const rows = useSetupRows(!!provider);
  const row = rows.data?.find((r) => r.provider === provider) ?? null;
  return (
    <Sheet open={!!provider} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-xl" data-testid="setup-sheet">
        {provider && (
          <SheetHeader className="pr-12">
            <div className="flex items-center gap-3">
              <PortalLogo portal={provider} className="size-9" />
              <div className="min-w-0">
                <SheetTitle className="font-display text-[17px] font-bold text-heading">Set up {provider === "linkedin" ? "LinkedIn" : "Indeed"} sign-in</SheetTitle>
                <SheetDescription className="text-xs">For JobPilot admins. Candidates only ever see “Connect”, never these settings.</SheetDescription>
              </div>
              {row && <Chip tone={STATE[row.state][1]} className="ml-auto">{STATE[row.state][0]}</Chip>}
            </div>
          </SheetHeader>
        )}
        <div className="px-4 pb-6">
          {rows.isLoading ? <LoadingState /> : rows.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(rows.error)}</p>
            : row && <Steps row={row} />}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Step({ n, title, done, children }: { n: number; title: string; done?: boolean; children: React.ReactNode }) {
  return (
    <li className="relative pl-10" data-step={n}>
      <span aria-hidden className={cn("absolute top-0 left-0 grid size-7 place-items-center rounded-full text-xs font-bold ring-1",
        done ? "bg-success-tint text-success ring-success/25" : "bg-paper-sunk text-heading ring-border")}>
        {done ? <Check className="size-3.5" /> : n}
      </span>
      <h3 className="pt-1 text-[13.5px] font-semibold text-heading">{title}{done && <span className="sr-only"> (done)</span>}</h3>
      <div className="mt-1.5 space-y-2 text-xs leading-relaxed text-muted-foreground">{children}</div>
    </li>
  );
}

function Steps({ row }: { row: SetupRow }) {
  const li = row.provider === "linkedin";
  const tested = row.last_test?.status === "verified" && !row.last_test.simulated;
  return (
    <>
    {row.last_test && <LastTest row={row} />}
    <ol className="space-y-6 border-l border-dashed border-border/80 pl-0 [&>li]:-ml-px" data-testid={`setup-steps-${row.provider}`}>
      <Step n={1} title={li ? "Create a LinkedIn developer app" : "Register in Indeed's Partner Console"} done={row.configured}>
        {li ? (
          <p>Create an app for JobPilot. LinkedIn asks you to associate it with a LinkedIn Company Page you manage; a simple page for your
            organisation is enough.</p>
        ) : (
          <p>Indeed's job-seeker sign-in is for registered partners. Creating OAuth credentials starts a review by Indeed, and approval isn't
            automatic: until Indeed approves the app, sign-in is refused.</p>
        )}
        <a href={row.links.console} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-route underline-offset-4 hover:underline">
          <ExternalLink className="size-3.5" aria-hidden /> {li ? "Open LinkedIn Developers" : "Open Indeed Partner Console docs"}
        </a>
      </Step>
      <Step n={2} title={li ? "Add the OpenID Connect product" : "Create 3-legged OAuth credentials"} done={tested}>
        {li ? (
          <p>On the app's <b className="text-foreground">Products</b> tab, request <b className="text-foreground">{row.product}</b>. It grants only
            the <code>openid profile email</code> scopes: name, photo and e-mail. Nothing else on LinkedIn is opened up.</p>
        ) : (
          <p>Choose 3-legged OAuth for a job-seeker app. JobPilot asks only for these scopes and refuses <code>employer_access</code>:</p>
        )}
        <div className="flex flex-wrap items-center gap-1.5" aria-label="Scopes JobPilot requests">
          {row.scopes.map((s) => <code key={s} className="rounded bg-paper-sunk px-1.5 py-0.5 text-[11px] text-foreground ring-1 ring-border">{s}</code>)}
          {row.pkce && <Chip tone="neutral">PKCE S256</Chip>}
        </div>
        <p data-testid="scope-status">
          Approval: {tested ? <span className="font-medium text-success">confirmed by a real sign-in on {when(row.last_test!.at)}</span>
            : row.state === "authorization_required" ? <span className="font-medium text-caution">{row.name} refused the app in the last test</span>
            : "not verified yet. Run the test in step 5."}
        </p>
        {li && row.links.docs && (
          <a href={row.links.docs} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-route underline-offset-4 hover:underline">
            <ExternalLink className="size-3.5" aria-hidden /> LinkedIn's sign-in guide
          </a>
        )}
      </Step>
      <Step n={3} title="Register the callback URL" done={tested}>
        <CallbackUrl row={row} />
      </Step>
      <Step n={4} title="Add the app's credentials" done={row.configured}>
        <Credentials key={row.client_id ?? ""} row={row} />
      </Step>
      <Step n={5} title={`Test with the real ${row.name}`} done={tested}>
        <TestConnection row={row} />
      </Step>
    </ol>
    </>
  );
}

function CallbackUrl({ row }: { row: SetupRow }) {
  const id = useId();
  if (!row.redirect_uri || row.redirect_problem) {
    const here = new URL(".", window.location.href).href.replace(/\/$/, "");
    return (
      <div role="alert" className="space-y-1.5 rounded-lg bg-caution-tint px-3 py-2 text-caution ring-1 ring-caution/25">
        <p className="flex items-start gap-1.5"><CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />{row.redirect_problem}</p>
        <p className="text-foreground">This page is served from <code>{here}</code>. If that's the address people use, set <code>PUBLIC_APP_URL={here}</code> on the
          backend and restart it; the callback becomes <code>{here}/oauth-callback.html</code>.</p>
      </div>
    );
  }
  return (
    <>
      <p>Add this exact URL under {row.provider === "linkedin" ? <>the app's <b className="text-foreground">Auth</b> tab → Authorized redirect URLs</> : "the app's redirect URL allowlist"}.</p>
      <div className="flex items-center gap-2">
        <label htmlFor={id} className="sr-only">Callback URL</label>
        <Input id={id} readOnly value={row.redirect_uri} className="h-8 font-mono text-xs" onFocus={(e) => e.currentTarget.select()} data-testid="callback-url" />
        <Button size="sm" variant="outline" onClick={() => navigator.clipboard?.writeText(row.redirect_uri!).then(() => toast.success("Callback URL copied."), () => toast.error("Couldn't copy. Select the text instead."))}>
          <Copy /> Copy
        </Button>
      </div>
      <p>From this server's {row.redirect_from} setting.</p>
    </>
  );
}

function Credentials({ row }: { row: SetupRow }) {
  const qc = useQueryClient();
  const [clientId, setClientId] = useState(row.client_id ?? "");
  const [secret, setSecret] = useState("");
  const [removing, setRemoving] = useState(false);
  const after = (r: SetupRow) => {
    qc.setQueryData<SetupRow[]>(["portal-setup"], (old) => old?.map((x) => (x.provider === r.provider ? r : x)));
    void qc.invalidateQueries({ queryKey: ["portals"] });
    setSecret("");
  };
  const save = useMutation({
    mutationFn: async () => (await api.put<SetupRow>(`/admin/portals/${row.provider}/credentials`, { client_id: clientId.trim(), ...(secret ? { client_secret: secret } : {}) })).data,
    onSuccess: (r) => { after(r); toast.success(`${row.name} credentials saved. Next: test the sign-in.`); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: async () => (await api.delete<SetupRow>(`/admin/portals/${row.provider}/credentials`)).data,
    onSuccess: (r) => { after(r); setRemoving(false); toast.success(`${row.name} credentials removed. Connect is off for everyone.`); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (row.source === "env") {
    return (
      <div className="space-y-1.5" data-testid="env-credentials">
        <p className="flex items-center gap-1.5 text-foreground"><ShieldCheck className="size-3.5 text-success" aria-hidden />
          Set in the server's environment ({row.env_names.join(", ")}), which takes precedence. Change them there and restart the backend.</p>
        <p>Client ID: <code className="text-foreground">{row.client_id || "missing"}</code> · Client Secret: {row.has_secret ? "set" : <span className="text-caution">missing</span>}</p>
      </div>
    );
  }
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }} data-testid="credentials-form">
      <p>Copy both from the app's <b className="text-foreground">Auth</b> {row.provider === "indeed" ? "credentials page" : "tab"}. The secret is stored encrypted on
        the backend and is never shown again, not even to admins. Or set {row.env_names.join(" and ")} on the server instead.</p>
      <Field label="Client ID" htmlFor={`cid-${row.provider}`}>
        <Input id={`cid-${row.provider}`} value={clientId} onChange={(e) => setClientId(e.target.value)} autoComplete="off" spellCheck={false} className="font-mono text-xs" />
      </Field>
      <Field label="Client Secret" htmlFor={`cs-${row.provider}`} hint={row.has_secret ? "A secret is saved. Leave this empty to keep it." : undefined}>
        <Input id={`cs-${row.provider}`} type="password" value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="new-password" spellCheck={false}
               placeholder={row.has_secret ? "••••••••••••  (saved)" : ""} className="font-mono text-xs" />
      </Field>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" size="sm" disabled={save.isPending || !clientId.trim() || (!secret && !row.has_secret)}>
          {save.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />} Save credentials
        </Button>
        {row.client_id && !removing && <Button type="button" size="sm" variant="ghost" onClick={() => setRemoving(true)}><Trash2 /> Remove</Button>}
        {removing && (
          <span role="group" aria-label="Remove credentials" className="flex flex-wrap items-center gap-2 rounded-lg bg-paper-sunk px-2.5 py-1.5 ring-1 ring-border">
            Remove them? Candidates can't connect until new ones are saved.
            <Button type="button" size="xs" variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>Remove</Button>
            <Button type="button" size="xs" variant="ghost" onClick={() => setRemoving(false)}>Keep</Button>
          </span>
        )}
      </div>
    </form>
  );
}

function TestConnection({ row }: { row: SetupRow }) {
  const test = useMutation({
    mutationFn: async () => (await api.post<{ authorization_url: string }>(`/admin/portals/${row.provider}/test`)).data,
    onSuccess: (d) => leaveForSignIn(d.authorization_url, { portal: row.provider, purpose: "test" }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <>
      {row.simulated ? (
        <p role="note" className="rounded-lg bg-caution-tint px-3 py-2 text-caution ring-1 ring-caution/25" data-testid="test-simulated">
          This server signs in to {row.name} with the local simulator (OAUTH_DEV_ENDPOINTS), so a test here can't prove anything about the real {row.name}.
          Remove that setting to test for real.
        </p>
      ) : (
        <p>Signs you in on {row.name}'s own page and checks the answer end to end (ID token, account, permissions). Nothing is linked to your
          account and no token is kept.</p>
      )}
      <Button size="sm" disabled={!row.configured || row.simulated || test.isPending} onClick={() => test.mutate()}>
        {test.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Test connection
      </Button>
      {!row.configured && <p>{row.problem}</p>}
    </>
  );
}

function LastTest({ row }: { row: SetupRow }) {
  const t = row.last_test!;
  return (
    <div data-testid="last-test" role="status" className={cn("mb-5 rounded-xl px-3.5 py-2.5 text-sm ring-1",
      t.status === "verified" ? "bg-success-tint text-success ring-success/25" : t.status === "cancelled" ? "bg-paper-sunk text-foreground ring-border" : "bg-caution-tint text-caution ring-caution/25")}>
      <p className="font-semibold">
        {t.status === "verified" ? `Verified with ${t.simulated ? "the local simulator (not the real " + row.name + ")" : "the real " + row.name}`
          : t.status === "cancelled" ? "Last test was cancelled" : t.status === "authorization_required" ? `${row.name} refused the app` : "Last test failed"} · {when(t.at)}
      </p>
      {t.detail && <p className="mt-0.5 text-xs leading-relaxed">{t.detail}</p>}
    </div>
  );
}
