// The side panel for one portal: its linked account (check, reconnect, disconnect), what it can and can't do grouped
// by Account / Discovery / Applications / Profile improvement, or its profile checklist.
import { useState } from "react";
import { Check, CircleAlert, Copy, Loader2, LogIn, RefreshCw, Unlink, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { LoadingState } from "@/components/app/common";
import { Chip } from "@/features/apply/parts";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PortalLogo } from "./PortalLogo";
import type { usePortalActions } from "./hooks";
import { when, type CapKey, type Portal } from "./types";

export type SheetView = "details" | "checklist";

const GROUPS = (name: string): { title: string; caps: [CapKey, string][] }[] => [
  { title: "Account", caps: [["identity_auth", "Official sign-in"], ["account_linked", "Linked identity"], ["profile_access", "Basic profile access"]] },
  { title: "Discovery", caps: [["listings", "Jobs already in JobPilot"], ["source", "Import jobs you find"], ["job_retrieval", `${name} job API`]] },
  { title: "Applications", caps: [["application_handoff", "Prepare application"], ["native_handoff", "Open the original posting"],
    ["assisted_submission", `Autofill on ${name}`], ["application_submission", `Submit through ${name}'s API`]] },
  { title: "Profile improvement", caps: [["profile_guidance", "Profile checklist"]] },
];

export function PortalSheet({ p, view, onClose, actions }: {
  p: Portal | null; view: SheetView; onClose: () => void; actions: ReturnType<typeof usePortalActions> | null;
}) {
  return (
    <Sheet open={!!p} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-lg" data-testid="portal-sheet">
        {p && (
          <>
            <SheetHeader className="pr-12">
              <div className="flex items-center gap-3">
                <PortalLogo portal={p.portal} className="size-9" />
                <div className="min-w-0">
                  <SheetTitle className="font-display text-[17px] font-bold text-heading">
                    {view === "checklist" ? `${p.name} profile checklist` : `${p.name}: capabilities & limitations`}
                  </SheetTitle>
                  <SheetDescription className="text-xs">
                    {view === "checklist" ? `Built from your confirmed JobPilot profile. JobPilot never edits your ${p.name} profile.`
                      : "What works today, and what doesn't, with the reason."}
                  </SheetDescription>
                </div>
              </div>
            </SheetHeader>
            <div className="space-y-5 px-4 pb-6">
              {view === "checklist" ? <PortalChecklist portal={p.portal} /> : (
                <>
                  {p.kind === "oauth" && actions && <AccountBlock p={p} actions={actions} />}
                  {GROUPS(p.name).map((g) => (
                    <section key={g.title} aria-label={g.title}>
                      <h3 className="mb-2 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase">{g.title}</h3>
                      <dl className="divide-y divide-border/70 rounded-xl ring-1 ring-border">
                        {g.caps.map(([k, label]) => {
                          const c = p.capabilities[k];
                          return (
                            <div key={k} className="flex gap-2.5 px-3 py-2.5" data-cap={k}>
                              {c.available ? <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden /> : <X className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />}
                              <div className="min-w-0">
                                <dt className={cn("text-[13px] font-medium", c.available ? "text-heading" : "text-muted-foreground")}>
                                  {label}<span className="sr-only">{c.available ? ": available" : ": not available"}</span>
                                </dt>
                                <dd className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{c.detail}</dd>
                              </div>
                            </div>
                          );
                        })}
                      </dl>
                    </section>
                  ))}
                </>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function AccountBlock({ p, actions }: { p: Portal; actions: ReturnType<typeof usePortalActions> }) {
  const [confirming, setConfirming] = useState(false);
  const id = p.identity;
  const has = (a: Portal["actions"][number]) => p.actions.includes(a);
  const missing = p.scopes.requested.filter((s) => !p.scopes.granted.includes(s));
  return (
    <section aria-label="Your account" className="rounded-xl bg-paper-sunk/60 p-3.5 ring-1 ring-border" data-testid={`account-${p.portal}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-heading">Your {p.name} account</h3>
        <Chip tone={p.status === "linked" ? (p.limited ? "warn" : "ok") : p.status === "not_linked" ? "check" : p.status === "not_configured" ? "neutral" : "warn"}>{p.status_label}</Chip>
      </div>
      {id ? (
        <div className="mt-2.5 space-y-2 text-xs" data-testid={`identity-${p.portal}`}>
          {id.simulated && (
            <p className="font-medium text-caution" data-testid={`simulated-${p.portal}`}>
              Simulated test account from a local test server. This is not your {p.name} account.
            </p>
          )}
          <div className="flex items-center gap-2.5">
            <span aria-hidden className="grid size-9 place-items-center rounded-full bg-card font-display text-[13px] font-bold text-heading ring-1 ring-border">
              {(id.name || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase()}
            </span>
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium text-foreground">{id.name || "Name not shared"}</p>
              {id.email && <p className="truncate text-muted-foreground">{id.email}{id.email_verified && !id.simulated ? ` · verified by ${p.name}` : ""}</p>}
            </div>
          </div>
          {id.status === "reconnect_required" && <p className="font-medium text-caution">{p.reason}</p>}
          <p className="text-muted-foreground">Linked {when(id.linked_at)} · last checked {when(id.last_validated_at)}
            {id.access_expires_at && id.status === "linked" && <> · access {id.can_refresh ? "renews automatically" : `until ${when(id.access_expires_at)}`}</>}</p>
          {id.scopes.length > 0 && (
            <p className="flex flex-wrap items-center gap-1 text-muted-foreground">Permissions you granted:
              {id.scopes.map((s) => <code key={s} className="rounded bg-card px-1.5 py-0.5 text-[11px] text-foreground ring-1 ring-border">{s}</code>)}
            </p>
          )}
          {p.limited && missing.length > 0 && (
            <p className="text-caution">Not granted: {missing.join(", ")}. Reconnect and allow them to share more.</p>
          )}
          {id.has_picture && <p className="text-muted-foreground">{p.name} shared a profile photo. JobPilot doesn't load it, so no image is fetched from {p.name}.</p>}
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted-foreground">{p.reason ?? (p.status === "not_linked" ? `No ${p.name} account linked yet.` : p.capabilities.identity_auth.detail)}</p>
      )}
      {confirming ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-card px-3 py-2 text-xs ring-1 ring-border" role="group" aria-label={`Disconnect ${p.name}`}>
          <span>Disconnect {p.name}? JobPilot deletes its access tokens.</span>
          <Button size="xs" variant="destructive" disabled={actions.busy} onClick={() => actions.disconnect.mutate(undefined, { onSuccess: () => setConfirming(false) })}>
            {actions.disconnect.isPending ? <Loader2 className="animate-spin" /> : <Unlink />} Disconnect
          </Button>
          <Button size="xs" variant="ghost" disabled={actions.busy} onClick={() => setConfirming(false)}>Keep it</Button>
        </div>
      ) : (has("check") || has("reconnect") || has("disconnect") || has("connect")) && (
        <div className="mt-3 flex flex-wrap gap-2">
          {has("connect") && (
            <Button size="sm" disabled={actions.busy} onClick={() => actions.connect.mutate()}>
              {actions.connect.isPending ? <Loader2 className="animate-spin" /> : <LogIn />} Connect with {p.name}{p.simulated ? " (simulated)" : ""}
            </Button>
          )}
          {has("check") && (
            <Button size="sm" variant="outline" disabled={actions.busy} onClick={() => actions.check.mutate()}>
              {actions.check.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} Check connection
            </Button>
          )}
          {has("reconnect") && (
            <Button size="sm" variant={p.status === "reconnect_required" ? "default" : "outline"} disabled={actions.busy} onClick={() => actions.connect.mutate()}>
              <LogIn /> Reconnect{p.simulated ? " (simulated)" : ""}
            </Button>
          )}
          {has("disconnect") && <Button size="sm" variant="outline" disabled={actions.busy} onClick={() => setConfirming(true)}><Unlink /> Disconnect</Button>}
        </div>
      )}
    </section>
  );
}

interface ReviewItem { key: string; label: string; state: "ok" | "improve" | "missing"; existing: string | null; suggestion: string | null; why: string; copy: boolean; done_at: string | null }
interface Review { portal: string; name: string; items: ReviewItem[]; completeness: number; source: string }

export function PortalChecklist({ portal }: { portal: string }) {
  const qc = useQueryClient();
  const review = useQuery({ queryKey: ["portal-review", portal], queryFn: async () => (await api.get<Review>(`/portals/${portal}/review`)).data, retry: false });
  const mark = useMutation({
    mutationFn: async ({ key, done }: { key: string; done: boolean }) => (await api.put<Review>(`/portals/${portal}/review/${key}`, { done })).data,
    onSuccess: (data) => qc.setQueryData(["portal-review", portal], data),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (review.isLoading) return <LoadingState />;
  if (review.isError) {
    return (
      <p role="alert" className="flex items-start gap-2 rounded-xl bg-caution-tint px-3 py-2.5 text-sm text-caution ring-1 ring-caution/25">
        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />{errorMessage(review.error)}
      </p>
    );
  }
  const r = review.data!;
  return (
    <div data-testid={`checklist-${portal}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{r.source}</p>
        <span className="readout text-xs font-medium text-heading" aria-label={`${r.completeness}% complete`}>{r.completeness}% done</span>
      </div>
      <ol className="space-y-2">
        {r.items.map((it) => (
          <li key={it.key} className="rounded-lg bg-card p-3 ring-1 ring-border/70" data-testid={`item-${it.key}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <span className="text-[13px] font-semibold text-heading">{it.label}</span>
                {it.done_at ? <Chip tone="ok">Done</Chip> : it.state === "ok" ? <Chip tone="ok">Looks good</Chip>
                  : <Chip tone="warn">{it.state === "missing" ? "Missing" : "Can improve"}</Chip>}
              </div>
              <Button size="xs" variant="ghost" disabled={mark.isPending} aria-pressed={!!it.done_at}
                      onClick={() => mark.mutate({ key: it.key, done: !it.done_at })}>
                {mark.isPending && mark.variables?.key === it.key ? <Loader2 className="animate-spin" /> : <Check />} {it.done_at ? "Mark not done" : "Mark done"}
              </Button>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{it.why}</p>
            {it.existing && <p className="mt-1.5 text-xs"><span className="text-muted-foreground">Now: </span><span className="whitespace-pre-line break-words">{it.existing}</span></p>}
            {it.suggestion && it.suggestion !== it.existing && (
              <div className="mt-1.5 flex items-start gap-2 rounded-md bg-route-tint/50 px-2.5 py-1.5 text-xs">
                <p className="min-w-0 flex-1 whitespace-pre-line break-words"><span className="text-muted-foreground">Suggested: </span>{it.suggestion}</p>
              </div>
            )}
            {it.copy && it.suggestion && (
              <Button size="xs" variant="outline" className="mt-1.5"
                      onClick={() => navigator.clipboard?.writeText(it.suggestion!).then(() => toast.success("Copied. Paste it on the portal."), () => toast.error("Couldn't copy. Select the text instead."))}>
                <Copy /> Copy
              </Button>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
