// Connect, check and disconnect for one portal, shared by its card and its details panel. Results the backend confirms
// replace the portal's row; failures become a visible card state with the cause and a way to recover.
import { useMutation } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api";
import { leaveForSignIn, type Portal, type PortalKey } from "./types";

export type Transient = { kind: "connecting" | "failed" | "unavailable"; message?: string };
export type SetTransient = (portal: PortalKey, t: Transient | null) => void;

export function usePortalActions(p: Portal, onRow: (row: Portal) => void, setTransient: SetTransient) {
  const connect = useMutation({
    mutationFn: async () => (await api.post<{ authorization_url: string }>(`/portals/${p.portal}/connect`)).data,
    onMutate: () => setTransient(p.portal, { kind: "connecting" }),
    // The portal's own sign-in page, in this tab: you come back to Portal Connections afterwards.
    onSuccess: (d) => leaveForSignIn(d.authorization_url, { portal: p.portal, purpose: "link" }),
    onError: (e) => setTransient(p.portal, { kind: "failed", message: errorMessage(e) }),
  });
  const check = useMutation({
    mutationFn: async () => (await api.post<Portal>(`/portals/${p.portal}/check`)).data,
    onSuccess: (row) => {
      onRow(row);
      setTransient(p.portal, null);
      if (row.status === "linked") toast.success(`${p.name} connection works.`);
      else toast.warning(row.reason || "Reconnect required.");
    },
    // 502: the portal is down or answered oddly. The link is kept; it's only temporarily unavailable.
    onError: (e) => (isAxiosError(e) && e.response?.status === 502
      ? setTransient(p.portal, { kind: "unavailable", message: errorMessage(e) })
      : toast.error(errorMessage(e))),
  });
  const disconnect = useMutation({
    mutationFn: async () => (await api.delete<{ detail: string; portal: Portal }>(`/portals/${p.portal}/connection`)).data,
    onSuccess: (d) => { onRow(d.portal); setTransient(p.portal, null); toast.success(d.detail, { duration: 10_000 }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return { connect, check, disconnect, busy: connect.isPending || check.isPending || disconnect.isPending };
}
