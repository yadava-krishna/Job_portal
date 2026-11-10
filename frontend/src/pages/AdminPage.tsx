import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ShieldAlert, CheckCircle2, XCircle, Plus, Copy, Trash2, RefreshCw } from "lucide-react";

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
  const [tab, setTab] = useState<"metrics" | "users" | "invites" | "audit">("metrics");
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);

  // Invite modal state
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"user" | "admin">("user");
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
      fetchUsers();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Action failed");
    }
  };

  const handleRoleChange = async (userId: number, currentRole: string) => {
    const newRole = currentRole === "admin" ? "user" : "admin";
    if (!confirm(`Are you sure you want to change user role to ${newRole}?`)) return;
    try {
      await api.put(`/admin/users/${userId}/role`, { role: newRole });
      fetchUsers();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Action failed");
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
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to generate invite");
    }
  };

  const handleRevokeInvite = async (inviteId: number) => {
    if (!confirm("Revoke this invite code?")) return;
    try {
      await api.delete(`/admin/invites/${inviteId}`);
      fetchInvites();
    } catch {}
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <ShieldAlert className="h-6 w-6 text-primary" /> Admin Operations Center
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            System metrics, user directory, registration invites, and security audit log.
          </p>
        </div>

        <div className="flex rounded-lg border border-border bg-card p-1">
          {(["metrics", "users", "invites", "audit"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                tab === t ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* METRICS TAB */}
      {tab === "metrics" && metrics && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="text-xs font-medium text-muted-foreground">Registered Users</div>
              <div className="text-2xl font-bold text-foreground mt-2">{metrics.total_users}</div>
              <div className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 font-medium">
                {metrics.active_users} active accounts
              </div>
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="text-xs font-medium text-muted-foreground">Global Jobs Ingested</div>
              <div className="text-2xl font-bold text-foreground mt-2">{metrics.total_jobs}</div>
              <div className="text-xs text-muted-foreground mt-1">{metrics.active_sources} active sources</div>
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="text-xs font-medium text-muted-foreground">Total Applications</div>
              <div className="text-2xl font-bold text-foreground mt-2">{metrics.total_applications}</div>
              <div className="text-xs text-muted-foreground mt-1">{metrics.total_interviews} interviews scheduled</div>
            </div>

            <div className="rounded-xl border border-border bg-card p-5">
              <div className="text-xs font-medium text-muted-foreground">Employment Offers</div>
              <div className="text-2xl font-bold text-foreground mt-2">{metrics.total_offers}</div>
              <div className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 font-medium">Pipeline conversions</div>
            </div>
          </div>
        </div>
      )}

      {/* USERS TAB */}
      {tab === "users" && (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">User Accounts ({users.length})</h3>
            <button
              onClick={fetchUsers}
              disabled={loading}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/50 border-b border-border text-muted-foreground uppercase text-[10px]">
                <tr>
                  <th className="px-4 py-3">ID / User</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Jobs / Apps</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-foreground">
                {users.map((u) => (
                  <tr key={u.id} className="hover:bg-muted/20">
                    <td className="px-4 py-3">
                      <div className="font-medium">{u.full_name || "Unnamed"}</div>
                      <div className="text-muted-foreground font-mono text-[11px]">{u.email}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase ${
                          u.role === "admin"
                            ? "bg-primary/20 text-primary"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {u.role}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1 font-medium">
                        {u.is_active ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                        ) : (
                          <XCircle className="h-3.5 w-3.5 text-destructive" />
                        )}
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {u.jobs_count} / {u.applications_count}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(u.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <button
                        onClick={() => handleToggleActive(u.id, u.is_active)}
                        className="rounded px-2 py-1 border border-border text-[11px] hover:bg-muted font-medium"
                      >
                        {u.is_active ? "Deactivate" : "Activate"}
                      </button>
                      <button
                        onClick={() => handleRoleChange(u.id, u.role)}
                        className="rounded px-2 py-1 border border-border text-[11px] hover:bg-muted font-medium"
                      >
                        {u.role === "admin" ? "Demote" : "Make Admin"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* INVITES TAB */}
      {tab === "invites" && (
        <div className="space-y-6">
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
              <Plus className="h-4 w-4" /> Generate Registration Invite
            </h3>
            <form onSubmit={handleCreateInvite} className="grid gap-3 sm:grid-cols-3">
              <input
                type="email"
                placeholder="Candidate Email (optional restriction)"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                className="rounded-lg border border-input bg-background px-3 py-2 text-xs"
              />
              <select
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as any)}
                className="rounded-lg border border-input bg-background px-3 py-2 text-xs"
              >
                <option value="user">Candidate Role (user)</option>
                <option value="admin">Administrator Role (admin)</option>
              </select>
              <button
                type="submit"
                className="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground hover:bg-primary/90"
              >
                Generate Code
              </button>
            </form>

            {createdInviteCode && (
              <div className="mt-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 flex items-center justify-between text-xs text-emerald-800 dark:text-emerald-300">
                <div>
                  <span className="font-semibold">Invite code created: </span>
                  <span className="font-mono text-sm ml-2 font-bold">{createdInviteCode}</span>
                </div>
                <button
                  onClick={() => navigator.clipboard.writeText(createdInviteCode)}
                  className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2.5 py-1 text-white hover:bg-emerald-700"
                >
                  <Copy className="h-3 w-3" /> Copy
                </button>
              </div>
            )}
          </div>

          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="p-4 border-b border-border">
              <h3 className="text-sm font-semibold text-foreground">Recent Invites ({invites.length})</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/50 border-b border-border text-muted-foreground uppercase text-[10px]">
                  <tr>
                    <th className="px-4 py-3">Code / Restrict</th>
                    <th className="px-4 py-3">Role</th>
                    <th className="px-4 py-3">Uses</th>
                    <th className="px-4 py-3">Expires</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border text-foreground">
                  {invites.map((inv) => (
                    <tr key={inv.id} className="hover:bg-muted/20">
                      <td className="px-4 py-3">
                        <span className="font-mono font-medium">{inv.code}</span>
                        {inv.email && <span className="ml-2 text-muted-foreground">({inv.email})</span>}
                      </td>
                      <td className="px-4 py-3 uppercase text-[10px] font-semibold">{inv.role}</td>
                      <td className="px-4 py-3 font-mono">{inv.used_count} / {inv.max_uses}</td>
                      <td className="px-4 py-3 text-muted-foreground">{new Date(inv.expires_at).toLocaleDateString()}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleRevokeInvite(inv.id)}
                          className="rounded p-1 text-destructive hover:bg-destructive/10"
                          title="Revoke code"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* AUDIT LOG TAB */}
      {tab === "audit" && (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <div className="p-4 border-b border-border">
            <h3 className="text-sm font-semibold text-foreground">Security Audit Trail</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/50 border-b border-border text-muted-foreground uppercase text-[10px]">
                <tr>
                  <th className="px-4 py-3">Timestamp</th>
                  <th className="px-4 py-3">Actor</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Target</th>
                  <th className="px-4 py-3">IP Address</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border text-foreground">
                {auditLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-muted/20">
                    <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-mono">User #{log.actor_id ?? "system"}</td>
                    <td className="px-4 py-3 font-semibold text-primary">{log.action}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {log.target_type} {log.target_id ? `(#${log.target_id})` : ""}
                    </td>
                    <td className="px-4 py-3 font-mono text-[11px] text-muted-foreground">{log.ip || "unknown"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
