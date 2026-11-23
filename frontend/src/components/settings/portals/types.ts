// Portal Connections data, as GET /portals (every user) and GET /admin/portals (admins) return it.
import { useAuth } from "@/contexts/AuthContext";

export type PortalKey = "linkedin" | "naukri" | "indeed";
export type CapKey = "identity_auth" | "account_linked" | "profile_access" | "listings" | "source" | "job_retrieval"
  | "application_handoff" | "native_handoff" | "assisted_submission" | "application_submission" | "profile_guidance" | "reconnect_required";
export type Action = "connect" | "reconnect" | "check" | "disconnect" | "optimize" | "open" | "import" | "prepare" | "browse" | "setup";
export type Status = "linked" | "not_linked" | "not_configured" | "reconnect_required" | "authorization_required" | "native_only";
export type Cap = { available: boolean; detail: string; state?: string; fields?: string[]; count?: number };

export interface Identity {
  status: "linked" | "reconnect_required"; status_detail: string | null; simulated?: boolean; name: string | null; email: string | null;
  email_verified: boolean | null; has_picture: boolean; scopes: string[]; linked_at: string | null; last_validated_at: string | null;
  access_expires_at: string | null; can_refresh: boolean;
}

export interface SetupTest { status: "verified" | "authorization_required" | "cancelled" | "failed"; detail: string | null; simulated: boolean; at: string | null }

export interface Portal {
  portal: PortalKey; name: string; url: string; kind: "oauth" | "native"; simulated?: boolean; summary: string; reason: string | null;
  status: Status; status_label: string; limited: boolean; identity: Identity | null;
  setup_state: SetupState | null; scopes: { requested: string[]; granted: string[] }; actions: Action[];
  capabilities: Record<CapKey, Cap>;
  /** Only on the answer to an admin's setup test (POST /portals/oauth/complete). */
  setup_test?: SetupTest & { provider: PortalKey };
}

export type SetupState = "not_configured" | "simulated" | "ready_to_test" | "verified" | "authorization_required" | "failed";

export interface SetupRow {
  provider: "linkedin" | "indeed"; name: string; product: string; links: { console: string; docs?: string };
  state: SetupState; configured: boolean; problem: string | null; source: "env" | "admin" | null; editable: boolean;
  client_id: string | null; has_secret: boolean; redirect_uri: string | null; redirect_from: string | null; redirect_problem: string | null;
  scopes: string[]; simulated: boolean; pkce: boolean; env_names: string[]; last_test: SetupTest | null; updated_at: string | null;
}

/** The platform name stored on jobs (and used by the Discover platform filter). */
export const PLATFORM: Record<PortalKey, "LinkedIn" | "Naukri" | "Indeed"> = { linkedin: "LinkedIn", naukri: "Naukri", indeed: "Indeed" };

export function useIsAdmin(): boolean {
  return useAuth().user?.role === "admin";
}

export const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "never");

// The provider's sign-in happens in this tab. oauth-callback.html leaves the provider's answer under RETURN_KEY; which
// portal it was for (and whether it was an admin's setup test) is remembered under PENDING_KEY before leaving.
export const RETURN_KEY = "jobpilot.oauthReturn";
export const PENDING_KEY = "jobpilot.oauthPending";
export interface Pending { portal: PortalKey; purpose: "link" | "test" }

export function leaveForSignIn(url: string, pending: Pending) {
  try { sessionStorage.setItem(PENDING_KEY, JSON.stringify(pending)); } catch { /* storage blocked: the result still arrives */ }
  window.location.assign(url);
}

export function takePending(): Pending | null {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    sessionStorage.removeItem(PENDING_KEY);
    return raw ? (JSON.parse(raw) as Pending) : null;
  } catch { return null; }
}
