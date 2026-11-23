// Settings -> Portal Connections: three cards (LinkedIn, Naukri, Indeed) with each portal's real state and the actions
// that work for it, "Find or import jobs" below them, and side panels for details, the profile checklist, preparing an
// application, and (admins only) setting up LinkedIn/Indeed sign-in. The capability model and every rule behind it live
// on the backend (portal_service); this page never shows a button the server can't honour.
import { useCallback, useEffect, useRef, useState } from "react";
import { CircleAlert, Loader2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/app/common";
import { ApplyDialog } from "@/components/app/ApplyDialog";
import { GuidedImportDialog } from "@/components/app/ImportDialog";
import { Panel } from "@/components/settings/primitives";
import { api, errorMessage } from "@/lib/api";
import type { JobDetail, UserJob } from "@/types/api";
import { FindJobs } from "./portals/FindJobs";
import { usePortalActions, type SetTransient, type Transient } from "./portals/hooks";
import { PortalSheet } from "./portals/PortalSheet";
import { PrepareSheet } from "./portals/PrepareSheet";
import { ProviderCard, type CardIntent } from "./portals/ProviderCard";
import { SetupSheet } from "./portals/SetupSheet";
import { PLATFORM, RETURN_KEY, takePending, useIsAdmin, type Portal, type PortalKey } from "./portals/types";

export type { Portal } from "./portals/types";

/** Back from LinkedIn/Indeed (oauth-callback.html left the answer in this tab): finish it, once. */
function useOAuthReturn(handlers: {
  linked: (p: Portal) => Promise<void>; tested: (p: Portal) => void; failed: (message: string, portal: PortalKey | null, test: boolean) => void;
}) {
  const [busy, setBusy] = useState(() => { try { return !!sessionStorage.getItem(RETURN_KEY); } catch { return false; } });
  const ran = useRef(false);
  const h = useRef(handlers);
  useEffect(() => { h.current = handlers; });
  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    let raw: string | null = null;
    try { raw = sessionStorage.getItem(RETURN_KEY); sessionStorage.removeItem(RETURN_KEY); } catch { /* storage blocked */ }
    const pending = takePending();
    let body: Record<string, string> | null = null;
    try { body = raw ? JSON.parse(raw) : null; } catch { /* unreadable: nothing to finish */ }
    if (!body) { void Promise.resolve().then(() => setBusy(false)); return; }
    api.post<Portal>("/portals/oauth/complete", body)
      .then(async ({ data }) => { if (data.setup_test) h.current.tested(data); else await h.current.linked(data); })
      .catch((e) => h.current.failed(errorMessage(e), pending?.portal ?? null, pending?.purpose === "test"))
      .finally(() => setBusy(false));
  }, []);
  return busy;
}

type OpenPanel = { kind: "details" | "checklist" | "prepare"; portal: PortalKey } | { kind: "setup"; portal: "linkedin" | "indeed" } | null;

export function PortalConnections() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const isAdmin = useIsAdmin();
  const portals = useQuery({ queryKey: ["portals"], queryFn: async () => (await api.get<Portal[]>("/portals")).data, staleTime: 60_000 });
  const [transient, setTransientMap] = useState<Partial<Record<PortalKey, Transient>>>({});
  const [panel, setPanel] = useState<OpenPanel>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [importFor, setImportFor] = useState<{ platform: "LinkedIn" | "Naukri" | "Indeed" | null } | null>(null);
  const [applyJob, setApplyJob] = useState<UserJob | null>(null);

  const setTransient: SetTransient = useCallback((portal, t) => setTransientMap((m) => ({ ...m, [portal]: t ?? undefined })), []);
  const replace = useCallback((row: Portal) => qc.setQueryData<Portal[]>(["portals"], (old) => old?.map((p) => (p.portal === row.portal ? row : p))), [qc]);
  // The first list request may have left before the link was made (and an in-flight first load is reused, not
  // refetched): drop it, show the new row, then load the list again.
  const fresh = useCallback(async (row: Portal) => {
    await qc.cancelQueries({ queryKey: ["portals"] });
    replace(row);
    await qc.invalidateQueries({ queryKey: ["portals"] });
  }, [qc, replace]);

  const finishing = useOAuthReturn({
    linked: async (row) => { await fresh(row); toast.success(`${row.name} connected${row.identity?.simulated ? " (simulated, not your real account)" : ""}${row.identity?.name ? ` as ${row.identity.name}` : ""}.`); },
    tested: (row) => {
      const t = row.setup_test!;
      void qc.invalidateQueries({ queryKey: ["portal-setup"] });
      void fresh(row);
      if (t.status === "verified") toast.success(`${row.name} sign-in verified${t.simulated ? " (simulated)" : ""}. Nothing was linked.`);
      setPanel({ kind: "setup", portal: t.provider as "linkedin" | "indeed" });
    },
    failed: (message, portal, test) => {
      if (test && (portal === "linkedin" || portal === "indeed")) {
        void qc.invalidateQueries({ queryKey: ["portal-setup"] });
        void qc.invalidateQueries({ queryKey: ["portals"] });
        toast.error(message);
        setPanel({ kind: "setup", portal });
      } else if (portal) {
        setTransient(portal, { kind: "failed", message });
      } else {
        setProblem(message);
      }
    },
  });

  const prepare = useCallback(async (userJobId: number) => {
    try { setApplyJob((await api.get<JobDetail>(`/jobs/${userJobId}`)).data); }
    catch (e) { toast.error(errorMessage(e)); }
  }, []);

  const rows = portals.data ?? [];
  const intent = (p: Portal, i: CardIntent) => {
    if (i === "import") setImportFor({ platform: PLATFORM[p.portal] });
    else if (i === "setup") setPanel({ kind: "setup", portal: p.portal as "linkedin" | "indeed" });
    else setPanel({ kind: i, portal: p.portal });
  };
  const current = panel && panel.kind !== "setup" ? rows.find((p) => p.portal === panel.portal) ?? null : null;

  return (
    // The section's own heading reads "Portal Connections" (Settings header), so the panel carries only the promise.
    <Panel description={null}>
      <p className="mb-4 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
        Sign-in goes through each portal's own page, so JobPilot never asks for a portal password or OTP. Applying always happens on the portal,
        by you. JobPilot gets you there prepared.
      </p>
      {finishing && <p role="status" className="mb-3 flex items-center gap-2 text-sm"><Loader2 className="size-4 animate-spin" /> Finishing the sign-in…</p>}
      {problem && (
        <div role="alert" className="mb-3 flex items-start gap-2 rounded-xl bg-caution-tint px-3 py-2.5 text-sm text-caution ring-1 ring-caution/25">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden /><span className="flex-1">{problem}</span>
          <Button size="icon-sm" variant="ghost" aria-label="Dismiss" onClick={() => setProblem(null)}><X /></Button>
        </div>
      )}
      {portals.isLoading ? <LoadingState /> : portals.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(portals.error)}</p> : (
        <>
          <ul className="space-y-3" data-testid="portal-connections">
            {rows.map((p) => (
              <CardWithActions key={p.portal} p={p} transient={transient[p.portal] ?? null} isAdmin={isAdmin} onRow={replace}
                               setTransient={setTransient} onIntent={(i) => intent(p, i)} />
            ))}
          </ul>
          <FindJobs portals={rows} onImport={() => setImportFor({ platform: null })} />
        </>
      )}
      {current && panel && (panel.kind === "details" || panel.kind === "checklist") && (
        <SheetWithActions p={current} view={panel.kind} onClose={() => setPanel(null)} onRow={replace} setTransient={setTransient} />
      )}
      <PrepareSheet p={panel?.kind === "prepare" ? current : null} onClose={() => setPanel(null)}
                    onPick={(j) => { setPanel(null); setApplyJob(j); }}
                    onImport={() => { const pl = current ? PLATFORM[current.portal] : null; setPanel(null); setImportFor({ platform: pl }); }} />
      {isAdmin && <SetupSheet provider={panel?.kind === "setup" ? panel.portal : null} onClose={() => setPanel(null)} />}
      <GuidedImportDialog open={!!importFor} onOpenChange={(o) => { if (!o) { setImportFor(null); void qc.invalidateQueries({ queryKey: ["portals"] }); } }} platform={importFor?.platform ?? null}
                          onPrepare={(id) => void prepare(id)} onView={(id) => navigate(`/discover?job=${id}`)} />
      <ApplyDialog item={applyJob} onClose={() => { setApplyJob(null); void qc.invalidateQueries({ queryKey: ["portals"] }); }} />
    </Panel>
  );
}

function CardWithActions({ p, transient, isAdmin, onRow, setTransient, onIntent }: {
  p: Portal; transient: Transient | null; isAdmin: boolean; onRow: (r: Portal) => void; setTransient: SetTransient; onIntent: (i: CardIntent) => void;
}) {
  const actions = usePortalActions(p, onRow, setTransient);
  return <ProviderCard p={p} transient={transient} actions={actions} isAdmin={isAdmin} onIntent={onIntent} />;
}

function SheetWithActions({ p, view, onClose, onRow, setTransient }: {
  p: Portal; view: "details" | "checklist"; onClose: () => void; onRow: (r: Portal) => void; setTransient: SetTransient;
}) {
  const actions = usePortalActions(p, onRow, setTransient);
  return <PortalSheet p={p} view={view} onClose={onClose} actions={actions} />;
}
