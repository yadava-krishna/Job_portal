import { useState } from "react";
import { AlertTriangle, Download, Loader2, LogOut, Server, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ConnectionSettingsDialog } from "@/components/app/ConnectionSettings";
import { useAuth } from "@/contexts/AuthContext";
import { useConnection } from "@/contexts/ConnectionContext";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DetailRow, Panel } from "./primitives";

const STATE_LABEL: Record<string, string> = {
  online: "Online", degraded: "Partly working", offline: "Offline", checking: "Checking…", resolving: "Checking…", unconfigured: "No address set",
};

/** Sign out, export, delete; and the backend address this portal talks to. */
export function AccountSection() {
  const { user, logout } = useAuth();
  const conn = useConnection();
  const [open, setOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    try {
      setExporting(true);
      await downloadFile("/account/export", "jobpilot-my-data.json");
      toast.success("Account data exported successfully");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password) return toast.error("Enter your password to confirm");
    try {
      setDeleting(true);
      await api.post("/account/delete", { password });
      toast.success("Account deleted");
      await logout();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleting(false);
    }
  };

  const online = conn.state === "online";
  return (
    <div className="space-y-5">
      <Panel title="Account">
        <dl className="divide-y">
          <DetailRow label="Email">{user?.email}</DetailRow>
          <DetailRow label="Member since"><span className="readout">{formatDate(user?.created_at)}</span></DetailRow>
        </dl>
        <div className="mt-4 flex flex-wrap gap-2 border-t pt-4">
          <Button variant="outline" onClick={() => void logout()}><LogOut /> Sign out</Button>
          <Button variant="outline" onClick={handleExport} disabled={exporting}>
            {exporting ? <Loader2 className="animate-spin" /> : <Download />} Export my data (JSON)
          </Button>
        </div>
      </Panel>

      <Panel title="Backend connection" description="The backend runs on the portal owner's machine."
             actions={<Button variant="outline" size="sm" onClick={() => setOpen(true)}><Server /> Change address</Button>}>
        <dl className="divide-y">
          <DetailRow label="Address"><span className="readout text-[13px] break-all">{conn.baseUrl}</span></DetailRow>
          <DetailRow label="Status">
            <span className="inline-flex items-center gap-2">
              <span aria-hidden className={cn("size-2 rounded-full", online ? "bg-success" : conn.state === "offline" ? "bg-destructive" : "bg-caution")} />
              {STATE_LABEL[conn.state] ?? conn.state}
            </span>
          </DetailRow>
          <DetailRow label="Version"><span className="readout">{conn.health?.version ?? "—"}</span></DetailRow>
        </dl>
      </Panel>

      <Panel tone="danger" title="Delete account"
             description="Permanently removes your resumes, applications, tracked events and notes. Export your data first if you want a copy.">
        <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
          <Trash2 /> Delete account...
        </Button>
      </Panel>

      <ConnectionSettingsDialog open={open} onOpenChange={setOpen} />

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="size-5" /> Permanently delete account
            </DialogTitle>
            <DialogDescription>
              This action cannot be undone. All your resumes, applications, tracked events, and notes will be permanently removed.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleDelete} className="space-y-3">
            <div className="space-y-1.5">
              <label htmlFor="delete-password" className="block text-sm font-medium">Enter your password to confirm</label>
              <Input
                id="delete-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                required
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDeleteOpen(false)}>Cancel</Button>
              <Button type="submit" variant="destructive" disabled={deleting}>
                {deleting ? <Loader2 className="animate-spin size-4" /> : null} Delete everything
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
