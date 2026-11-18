import { useEffect, useState } from "react";
import { Copy, KeyRound, Loader2, Plus, RefreshCw, ScrollText, Trash2, Users } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { NativeSelect, PageHeader } from "@/components/app/common";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Chip, Panel, StatusDot, table, type Tone } from "@/features/growth/ui";
import { BackgroundJobsPanel, ProductMetricsPanel, SystemPanel } from "@/features/growth/AdminOps";
import { OpsHealthPanel } from "@/features/growth/OpsHealth";

type Tab = "metrics" | "users" | "invites" | "audit" | "jobs" | "health" | "product" | "system";
const TABS: { key: Tab; label: string }[] = [
  { key: "metrics", label: "Metrics" }, { key: "users", label: "Users" }, { key: "invites", label: "Invites" }, { key: "audit", label: "Audit" },
  { key: "jobs", label: "Background jobs" }, { key: "health", label: "Health" }, { key: "product", label: "Product metrics" },
  { key: "system", label: "System" },
];
const roleTone: Record<string, Tone> = { admin: "violet", mentor: "route", user: "muted" };
const roleLabel = (r: string) => ROLES.find((x) => x.value === r)?.label ?? r;
const detail = (err: unknown, fallback: string) =>
  (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail?.toString() || fallback;
const ROLES = [
  { value: "user", label: "Candidate" }, { value: "mentor", label: "Mentor" }, { value: "admin", label: "Admin" },
];

interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  role: string;
  created_at: string;
  applications_count: number;
  jobs_count: number;
}

interface Invite {
  id: number;
  code: string;
  email: string | null;
  role: string;
  max_uses: number;
  used_count: number;
  expires_at: string;
  created_at: string;
}

interface SystemMetrics {
  total_users: number;
  active_users: number;
  total_jobs: number;
  total_applications: number;
  total_interviews: number;
  total_offers: number;
  active_sources: number;
  server_time: string;
}

interface AuditLog {
  id: number;
  actor_id: number | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  ip: string | null;
  created_at: string;
}

export function AdminPage() {
  const [tab, setTab] = useState<Tab>("metrics");
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);

  // Invite modal state
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"user" | "mentor" | "admin">("user");
  const [createdInviteCode, setCreatedInviteCode] = useState<string | null>(null);

  const fetchMetrics = async () => {
    try {
      const res = await api.get<SystemMetrics>("/admin/metrics");
      setMetrics(res.data);
    } catch {}
  };

  const fetchUsers = async () => {
    try {
      const res = await api.get<AdminUser[]>("/admin/users");
      setUsers(res.data);
    } catch {}
  };

  const fetchInvites = async () => {
    try {
      const res = await api.get<Invite[]>("/admin/invites");
      setInvites(res.data);
    } catch {}
  };

  const fetchAudit = async () => {
    try {
      const res = await api.get<AuditLog[]>("/admin/audit-log");
      setAuditLogs(res.data);
    } catch {}
  };

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchMetrics(), fetchUsers(), fetchInvites(), fetchAudit()]).finally(() => setLoading(false));
  }, []);

  const handleToggleActive = async (userId: number, currentActive: boolean) => {
    try {
      await api.put(`/admin/users/${userId}/status`, { is_active: !currentActive });
      toast.success(currentActive ? "Account deactivated" : "Account activated");
      fetchUsers();
    } catch (err) {
      toast.error(detail(err, "Action failed"));
    }
  };

  const handleRoleChange = async (userId: number, currentRole: string, newRole: string) => {
    if (newRole === currentRole) return;
    if (!confirm(`Are you sure you want to change user role to ${newRole}?`)) return;
    try {
      await api.put(`/admin/users/${userId}/role`, { role: newRole });
      toast.success(`Role changed to ${roleLabel(newRole)}`);
      fetchUsers();
    } catch (err) {
      toast.error(detail(err, "Action failed"));
    }
  };

  const handleCreateInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await api.post<Invite>("/admin/invites", {
        email: inviteEmail.trim() || undefined,
        role: inviteRole,
        max_uses: 1,
        expires_days: 7,
      });
      setCreatedInviteCode(res.data.code);
      setInviteEmail("");
      fetchInvites();
    } catch (err) {
      toast.error(detail(err, "Failed to generate invite"));
    }
  };

  const handleRevokeInvite = async (inviteId: number) => {
    if (!confirm("Revoke this invite code?")) return;
    try {
      await api.delete(`/admin/invites/${inviteId}`);
      toast.success("Invite revoked");
      fetchInvites();
    } catch (err) {
      toast.error(detail(err, "Couldn't revoke the invite"));
    }
  };

  const refreshButton = (onClick: () => void) => (
    <Button variant="ghost" size="sm" onClick={onClick} disabled={loading} className="text-muted-foreground">
      <RefreshCw className={cn(loading && "animate-spin")} /> Refresh
    </Button>
  );
  const now = Date.now();

  return (
    <>
      <PageHeader eyebrow="Admin" title="Admin console"
                  description="System metrics, users, invites, audit log, background jobs, operational health, product metrics and server status." />

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="gap-0">
        <div className="-mx-1 mb-4 overflow-x-auto px-1 pb-1">
          <TabsList>
            {TABS.map((t) => <TabsTrigger key={t.key} value={t.key} className="flex-none">{t.label}</TabsTrigger>)}
          </TabsList>
        </div>
      </Tabs>

      <div key={tab} className="animate-in fade-in-0 slide-in-from-bottom-1 duration-200">
      {tab === "metrics" && (metrics ? (
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl bg-border ring-1 ring-border lg:grid-cols-4">
          {[
            { label: "Registered users", value: metrics.total_users, sub: <StatusDot tone="success">{metrics.active_users} active accounts</StatusDot> },
            { label: "Jobs collected (all users)", value: metrics.total_jobs, sub: <>{metrics.active_sources} active sources</> },
            { label: "Applications", value: metrics.total_applications, sub: <>{metrics.total_interviews} interviews scheduled</> },
            { label: "Offers", value: metrics.total_offers, sub: <>Across all candidates</> },
          ].map((m) => (
            <div key={m.label} className="bg-card px-5 py-4">
              <dt className="text-xs font-medium text-muted-foreground">{m.label}</dt>
              <dd className="readout mt-1 text-[26px] leading-tight font-semibold text-heading">{m.value.toLocaleString()}</dd>
              <dd className="mt-0.5 text-xs text-muted-foreground">{m.sub}</dd>
            </div>
          ))}
        </dl>
      ) : loading ? <Loader2 className="animate-spin text-muted-foreground" /> : <p className="text-sm text-muted-foreground">Metrics couldn't be loaded.</p>)}

      {tab === "users" && (
        <Panel title="User accounts" icon={<Users />} count={users.length} actions={refreshButton(fetchUsers)} bodyClassName="px-0 pb-0 pt-3 sm:px-0">
          <div className={table.wrap}>
            <table className={cn(table.table, "min-w-[760px]")}>
              <thead className={table.thead}>
                <tr><th className={table.th}>User</th><th className={table.th}>Role</th><th className={table.th}>Status</th>
                  <th className={cn(table.th, "text-right")}>Jobs / Apps</th><th className={table.th}>Created</th><th className={cn(table.th, "text-right")}>Actions</th></tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className={table.tr}>
                    <td className={table.td}>
                      <div className="font-medium text-foreground">{u.full_name || "Unnamed"}</div>
                      <div className="readout text-[11.5px] text-muted-foreground">#{u.id} · {u.email}</div>
                    </td>
                    <td className={table.td}><Chip tone={roleTone[u.role] ?? "muted"}>{roleLabel(u.role)}</Chip></td>
                    <td className={table.td}><StatusDot tone={u.is_active ? "success" : "danger"} className="font-medium">{u.is_active ? "Active" : "Disabled"}</StatusDot></td>
                    <td className={cn(table.td, "readout text-right")}>{u.jobs_count.toLocaleString()} / {u.applications_count}</td>
                    <td className={cn(table.td, "text-muted-foreground")}>{formatDate(u.created_at)}</td>
                    <td className={cn(table.td, "text-right")}>
                      <div className="inline-flex items-center gap-1.5">
                        <Button size="xs" variant="outline" onClick={() => handleToggleActive(u.id, u.is_active)}>{u.is_active ? "Deactivate" : "Activate"}</Button>
                        <NativeSelect ariaLabel={`Role for ${u.email}`} value={u.role} onChange={(v) => handleRoleChange(u.id, u.role, v)}
                                      className="h-6 rounded-full px-2 text-[11.5px]" options={ROLES} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {tab === "invites" && (
        <div className="space-y-4">
          <Panel title="Create a registration invite" icon={<Plus />} description="Single use, valid for 7 days. Add an e-mail to restrict who can use it.">
            <form onSubmit={handleCreateInvite} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_14rem_auto]">
              <Input type="email" aria-label="Restrict to e-mail (optional)" placeholder="Candidate e-mail (optional restriction)" value={inviteEmail}
                     onChange={(e) => setInviteEmail(e.target.value)} />
              <NativeSelect ariaLabel="Role" value={inviteRole} onChange={(v) => setInviteRole(v as "user" | "mentor" | "admin")}
                            options={[{ value: "user", label: "Candidate (user)" }, { value: "mentor", label: "Mentor (mentor)" }, { value: "admin", label: "Administrator (admin)" }]} />
              <Button type="submit" className="h-10"><KeyRound /> Generate code</Button>
            </form>
            {createdInviteCode && (
              <div role="status" className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-success-tint px-3 py-2 text-[13px] animate-in fade-in-0 slide-in-from-top-1 duration-200">
                <div className="text-success">
                  <span className="font-semibold">Invite code created: </span>
                  <span className="readout ml-1 text-[15px] font-bold">{createdInviteCode}</span>
                </div>
                <Button size="xs" variant="outline" onClick={() => { void navigator.clipboard.writeText(createdInviteCode); toast.success("Copied"); }}>
                  <Copy /> Copy
                </Button>
              </div>
            )}
          </Panel>

          <Panel title="Recent invites" icon={<KeyRound />} count={invites.length} bodyClassName="px-0 pb-0 pt-3 sm:px-0">
            <div className={table.wrap}>
              <table className={cn(table.table, "min-w-[620px]")}>
                <thead className={table.thead}>
                  <tr><th className={table.th}>Code</th><th className={table.th}>Restricted to</th><th className={table.th}>Role</th>
                    <th className={table.th}>Status</th><th className={cn(table.th, "text-right")}>Uses</th><th className={table.th}>Expires</th><th className={cn(table.th, "text-right")}>Actions</th></tr>
                </thead>
                <tbody>
                  {invites.map((inv) => {
                    const expired = new Date(inv.expires_at).getTime() < now;
                    const used = inv.used_count >= inv.max_uses;
                    return (
                      <tr key={inv.id} className={table.tr}>
                        <td className={cn(table.td, "readout font-medium")}>{inv.code}</td>
                        <td className={cn(table.td, "text-muted-foreground")}>{inv.email ?? "Anyone"}</td>
                        <td className={table.td}><Chip tone={roleTone[inv.role] ?? "muted"}>{roleLabel(inv.role)}</Chip></td>
                        <td className={table.td}>
                          <StatusDot tone={used ? "muted" : expired ? "caution" : "route"}>{used ? "Used" : expired ? "Expired" : "Open"}</StatusDot>
                        </td>
                        <td className={cn(table.td, "readout text-right")}>{inv.used_count} / {inv.max_uses}</td>
                        <td className={cn(table.td, "text-muted-foreground")}>{formatDate(inv.expires_at)}</td>
                        <td className={cn(table.td, "text-right")}>
                          <Button size="icon-xs" variant="ghost" className="text-muted-foreground hover:text-destructive" onClick={() => handleRevokeInvite(inv.id)}
                                  title="Revoke code" aria-label={`Revoke invite ${inv.code}`}><Trash2 /></Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      {tab === "audit" && (
        <Panel title="Security audit trail" icon={<ScrollText />} count={auditLogs.length} actions={refreshButton(fetchAudit)} bodyClassName="px-0 pb-0 pt-3 sm:px-0">
          <div className={table.wrap}>
            <table className={cn(table.table, "min-w-[680px]")}>
              <thead className={table.thead}>
                <tr><th className={table.th}>Time</th><th className={table.th}>Actor</th><th className={table.th}>Action</th><th className={table.th}>Target</th><th className={table.th}>IP address</th></tr>
              </thead>
              <tbody>
                {auditLogs.map((log) => (
                  <tr key={log.id} className={table.tr}>
                    <td className={cn(table.td, "readout whitespace-nowrap text-[11.5px] text-muted-foreground")}>{formatDate(log.created_at, true)}</td>
                    <td className={cn(table.td, "readout")}>{log.actor_id != null ? `User #${log.actor_id}` : "System"}</td>
                    <td className={table.td}><code className="rounded-md bg-paper-sunk px-1.5 py-0.5 font-mono text-[11.5px] text-heading">{log.action}</code></td>
                    <td className={cn(table.td, "text-muted-foreground")}>{log.target_type ?? "—"} {log.target_id ? `(#${log.target_id})` : ""}</td>
                    <td className={cn(table.td, "readout text-[11.5px] text-muted-foreground")}>{log.ip || "unknown"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {tab === "jobs" && <BackgroundJobsPanel />}
      {tab === "health" && <OpsHealthPanel />}
      {tab === "product" && <ProductMetricsPanel />}
      {tab === "system" && <SystemPanel />}
      </div>
    </>
  );
}
