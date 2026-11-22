// Settings -> Portal Connections. For LinkedIn, Naukri and Indeed: what JobPilot can do (jobs in, profile guidance,
// application hand-off), what it can't (no account connection exists, no automation on the portals), and the actions
// that actually work. There is no Connect button because there is nothing approved to connect to.
import { useState } from "react";
import { Check, Copy, ExternalLink, Link2, Loader2, Sparkles, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/app/common";
import { Panel } from "@/components/settings/primitives";
import { Chip } from "@/features/apply/parts";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

type Cap = { available: boolean; detail: string; status?: string };
interface Portal {
  portal: "linkedin" | "naukri" | "indeed"; name: string; url: string; actions: ("optimize" | "open" | "import")[];
  capabilities: Record<"source" | "profile_guidance" | "account_connection" | "application_handoff" | "assisted_submission", Cap>;
}
interface ReviewItem { key: string; label: string; state: "ok" | "improve" | "missing"; existing: string | null; suggestion: string | null; why: string; copy: boolean; done_at: string | null }
interface Review { portal: string; name: string; items: ReviewItem[]; completeness: number; source: string }

const CAP_LABELS: [keyof Portal["capabilities"], string][] = [
  ["source", "Jobs into JobPilot"], ["profile_guidance", "Profile checklist"], ["application_handoff", "Apply with JobPilot's help"],
  ["account_connection", "Account connection"], ["assisted_submission", "Automatic filling or submitting"],
];

export function PortalConnections() {
  const portals = useQuery({ queryKey: ["portals"], queryFn: async () => (await api.get<Portal[]>("/portals")).data, staleTime: 3_600_000 });
  const [open, setOpen] = useState<string | null>(null);
  const navigate = useNavigate();
  return (
    // The section's own heading reads "Portal Connections" (Settings header), so the panel carries only the promise.
    <Panel description={null}>
      <p className="mb-4 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
        Finding jobs never needs a portal login, and JobPilot never signs in to a portal for you.
      </p>
      {portals.isLoading ? <LoadingState /> : portals.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(portals.error)}</p> : (
        <ul className="space-y-3" data-testid="portal-connections">
          {portals.data!.map((p) => (
            <li key={p.portal} className="rounded-xl ring-1 ring-border" data-testid={`portal-${p.portal}`}>
              <div className="flex flex-wrap items-start justify-between gap-3 p-4">
                <div className="min-w-0">
                  <h4 className="flex items-center gap-2 font-display text-[15px] font-bold text-heading">
                    {p.name}<Chip tone="neutral" title="JobPilot has no approved way to connect to your account here">Not connected</Chip>
                  </h4>
                </div>
                <div className="flex flex-wrap gap-2">
                  {p.actions.includes("optimize") && (
                    <Button size="sm" variant={open === p.portal ? "secondary" : "default"} aria-expanded={open === p.portal}
                            onClick={() => setOpen((o) => (o === p.portal ? null : p.portal))}><Sparkles /> Optimize profile</Button>
                  )}
                  <Button size="sm" variant="outline" render={<a href={p.url} target="_blank" rel="noopener noreferrer" />}><ExternalLink /> Open {p.name}</Button>
                  <Button size="sm" variant="outline" onClick={() => navigate("/discover?add=1")}><Link2 /> Import job link</Button>
                </div>
              </div>
              <dl className="grid gap-x-4 gap-y-2 border-t px-4 py-3 sm:grid-cols-2 lg:grid-cols-3">
                {CAP_LABELS.map(([k, label]) => (
                  <div key={k} className="min-w-0" title={p.capabilities[k].detail}>
                    <dt className="flex items-center gap-1.5 text-xs font-medium">
                      {p.capabilities[k].available ? <Check className="size-3.5 text-success" aria-hidden /> : <X className="size-3.5 text-muted-foreground" aria-hidden />}
                      <span className={cn(!p.capabilities[k].available && "text-muted-foreground")}>{label}</span>
                      <span className="sr-only">{p.capabilities[k].available ? ": available" : ": not available"}</span>
                    </dt>
                    <dd className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{p.capabilities[k].detail}</dd>
                  </div>
                ))}
              </dl>
              {open === p.portal && <PortalChecklist portal={p.portal} />}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function PortalChecklist({ portal }: { portal: string }) {
  const qc = useQueryClient();
  const review = useQuery({ queryKey: ["portal-review", portal], queryFn: async () => (await api.get<Review>(`/portals/${portal}/review`)).data, retry: false });
  const mark = useMutation({
    mutationFn: async ({ key, done }: { key: string; done: boolean }) => (await api.put<Review>(`/portals/${portal}/review/${key}`, { done })).data,
    onSuccess: (data) => qc.setQueryData(["portal-review", portal], data),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (review.isLoading) return <div className="border-t p-4"><LoadingState /></div>;
  if (review.isError) return <p role="alert" className="border-t p-4 text-sm text-caution">{errorMessage(review.error)}</p>;
  const r = review.data!;
  return (
    <div className="border-t bg-paper-sunk/50 p-4" data-testid={`checklist-${portal}`}>
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
