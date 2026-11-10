import { useEffect, useState } from "react";
import { AlertTriangle, Download, Loader2, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Field, NativeSelect, PageHeader } from "@/components/app/common";
import { ConnectionSettingsDialog } from "@/components/app/ConnectionSettings";
import { ExtensionSettings } from "@/components/app/ExtensionSettings";
import { AnswerBank, NotificationSettings, ResumeVersions } from "@/components/app/ProfileExtras";
import { ClipperCard, PlatformsForm, PreferencesForm, ProfileForm, ResumeUpload } from "@/components/app/forms";
import { useAuth } from "@/contexts/AuthContext";
import { useConnection } from "@/contexts/ConnectionContext";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import { useEmailIntegration, usePreferences, useProfile, useSaveEmail, useSaveFacts } from "@/services/queries";
import type { VerifiedFacts } from "@/types/api";

export function SettingsPage() {
  const profile = useProfile();
  const prefs = usePreferences();
  // Deep links such as #/settings?tab=answers (used by the browser extension's "update your profile" links).
  const [params] = useSearchParams();
  const tabs = ["profile", "preferences", "platforms", "answers", "email", "notifications", "extension", "account"];
  const initialTab = tabs.includes(params.get("tab") ?? "") ? params.get("tab")! : "profile";
  return (
    <>
      <PageHeader title="Profile & settings" description="Everything here is private to your account." />
      <Tabs defaultValue={initialTab}>
        <div className="overflow-x-auto pb-1">
          <TabsList>
            <TabsTrigger value="profile">Resume & profile</TabsTrigger>
            <TabsTrigger value="preferences">Job preferences</TabsTrigger>
            <TabsTrigger value="platforms">Platforms</TabsTrigger>
            <TabsTrigger value="answers">Verified answers</TabsTrigger>
            <TabsTrigger value="email">Alert emails</TabsTrigger>
            <TabsTrigger value="notifications">Notifications</TabsTrigger>
            <TabsTrigger value="extension">Browser extension</TabsTrigger>
            <TabsTrigger value="account">Account & connection</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="profile" className="space-y-6 pt-4">
          <Card>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div><CardTitle>Resume</CardTitle><CardDescription>Uploading a new resume re-parses it. Review your profile below afterwards.</CardDescription></div>
              {profile.data?.resume && <Button size="sm" variant="outline" onClick={() => downloadFile("/profile/resume", profile.data?.resume?.original_filename ?? "resume.pdf").catch((e) => toast.error(errorMessage(e)))}>Download current</Button>}
            </CardHeader>
            <CardContent><ResumeUpload profile={profile.data} /></CardContent>
          </Card>
          <ResumeVersions />
          <Card>
            <CardHeader><CardTitle>Candidate profile</CardTitle><CardDescription>Used for matching and for answering screening questions. Saving re-scores your open jobs.</CardDescription></CardHeader>
            <CardContent>{profile.data ? <ProfileForm profile={profile.data} /> : <Loader2 className="animate-spin" />}</CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="preferences" className="pt-4">
          <Card><CardContent className="pt-6">{prefs.data ? <PreferencesForm initial={prefs.data.is_configured ? prefs.data : undefined} /> : <Loader2 className="animate-spin" />}</CardContent></Card>
        </TabsContent>

        <TabsContent value="platforms" className="space-y-6 pt-4">
          <PlatformsForm />
          <ClipperCard />
        </TabsContent>

        <TabsContent value="answers" className="pt-4"><FactsForm facts={profile.data?.verified_facts} /></TabsContent>
        <TabsContent value="email" className="pt-4"><EmailForm /></TabsContent>
        <TabsContent value="extension" className="pt-4"><ExtensionSettings /></TabsContent>
        <TabsContent value="notifications" className="pt-4"><NotificationSettings /></TabsContent>
        <TabsContent value="account" className="pt-4"><AccountCard /></TabsContent>
      </Tabs>
    </>
  );
}

function FactsForm({ facts }: { facts?: VerifiedFacts }) {
  const save = useSaveFacts();
  const [f, setF] = useState<VerifiedFacts>({});
  useEffect(() => { if (facts) setF(facts); }, [facts]);
  const text = (k: keyof VerifiedFacts, label: string, ph: string) => (
    <Field label={label} htmlFor={`f-${k}`}><Input id={`f-${k}`} value={(f[k] as string | null | undefined) ?? ""} placeholder={ph} onChange={(e) => setF({ ...f, [k]: e.target.value || null })} /></Field>
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Verified screening answers</CardTitle>
        <CardDescription>Applications ask these often. JobPilot never guesses them: leave a field empty and it is shown as "needs your input".</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          {text("current_ctc", "Current CTC (optional, only if you want it shared)", "e.g. 6.5 LPA")}
          {text("expected_ctc", "Expected CTC", "e.g. 8-9 LPA")}
          {text("notice_period", "Notice period", "e.g. 30 days")}
          {text("earliest_start_date", "Earliest start date", "e.g. 1 Dec 2026")}
          {text("work_authorization", "Work authorization", "e.g. Indian citizen")}
          {text("shift_flexibility", "Shift flexibility", "e.g. Open to US shifts")}
          {text("relevant_experience", "Relevant experience", "e.g. 4 years in accounts receivable")}
          <Field label="Need visa sponsorship?">
            <NativeSelect value={f.requires_sponsorship == null ? "" : f.requires_sponsorship ? "yes" : "no"} onChange={(v) => setF({ ...f, requires_sponsorship: v === "" ? null : v === "yes" })}
                          options={[{ value: "", label: "Ask me each time" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }]} className="w-full" />
          </Field>
          <Field label="Willing to relocate?">
            <NativeSelect value={f.willing_to_relocate == null ? "" : f.willing_to_relocate ? "yes" : "no"} onChange={(v) => setF({ ...f, willing_to_relocate: v === "" ? null : v === "yes" })}
                          options={[{ value: "", label: "Ask me each time" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }]} className="w-full" />
          </Field>
        </div>
        <AnswerBank facts={f} onChange={setF} />
        <div className="flex justify-end"><Button onClick={() => save.mutate({ ...f, custom_answers: (f.custom_answers ?? []).filter((a) => a.question.trim() && a.answer.trim()) }, { onSuccess: () => toast.success("Saved"), onError: (e) => toast.error(errorMessage(e)) })} disabled={save.isPending}>Save answers</Button></div>
      </CardContent>
    </Card>
  );
}

function EmailForm() {
  const { data } = useEmailIntegration();
  const save = useSaveEmail();
  const [f, setF] = useState({ enabled: false, imap_host: "imap.gmail.com", imap_port: 993, username: "", password: "", folder: "INBOX", lookback_days: 2 });
  useEffect(() => { if (data) setF((x) => ({ ...x, ...data, username: data.username ?? "", password: "" })); }, [data]);
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>Job-alert emails</CardTitle>
          <CardDescription>
            Read your own LinkedIn, Indeed and Naukri alert emails (read-only) to discover jobs, and detect "application sent" confirmations.
            Use an app password (for Gmail: Google Account → Security → App passwords). It is stored encrypted.
          </CardDescription>
        </div>
        <Switch checked={f.enabled} onCheckedChange={(c) => setF({ ...f, enabled: !!c })} aria-label="Enable alert emails" />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="IMAP server" htmlFor="e-host"><Input id="e-host" value={f.imap_host} onChange={(e) => setF({ ...f, imap_host: e.target.value })} /></Field>
          <Field label="Port" htmlFor="e-port"><Input id="e-port" type="number" value={f.imap_port} onChange={(e) => setF({ ...f, imap_port: Number(e.target.value) })} /></Field>
          <Field label="Email address" htmlFor="e-user"><Input id="e-user" autoComplete="off" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
          <Field label="App password" htmlFor="e-pass" hint={data?.has_password ? "A password is stored. Leave empty to keep it." : undefined}>
            <Input id="e-pass" type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          </Field>
          <Field label="Folder" htmlFor="e-folder"><Input id="e-folder" value={f.folder} onChange={(e) => setF({ ...f, folder: e.target.value })} /></Field>
          <Field label="Look back (days)" htmlFor="e-days"><Input id="e-days" type="number" min={1} max={14} value={f.lookback_days} onChange={(e) => setF({ ...f, lookback_days: Number(e.target.value) })} /></Field>
        </div>
        {data?.last_checked_at && <p className="text-xs text-muted-foreground">Last checked {timeAgo(data.last_checked_at)}{data.last_error ? ` · ${data.last_error}` : ""}</p>}
        <div className="flex justify-end">
          <Button onClick={() => save.mutate({ ...f, password: f.password || null }, { onSuccess: () => { toast.success("Saved"); setF((x) => ({ ...x, password: "" })); }, onError: (e) => toast.error(errorMessage(e)) })} disabled={save.isPending}>Save</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function AccountCard() {
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

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card>
        <CardHeader><CardTitle>Account</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex justify-between"><span className="text-muted-foreground">Email</span><span>{user?.email}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Member since</span><span>{formatDate(user?.created_at)}</span></div>
          <div className="flex flex-wrap gap-2 pt-2 border-t">
            <Button variant="outline" size="sm" onClick={() => void logout()}>Sign out</Button>
            <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
              {exporting ? <Loader2 className="animate-spin size-3.5" /> : <Download className="size-3.5" />} Export my data (JSON)
            </Button>
          </div>
          <div className="pt-3 border-t">
            <Button variant="ghost" size="sm" className="text-destructive hover:bg-destructive/10" onClick={() => setDeleteOpen(true)}>
              <Trash2 className="size-3.5" /> Delete account...
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Backend connection</CardTitle><CardDescription>The backend runs on the portal owner's machine.</CardDescription></CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between gap-2"><span className="text-muted-foreground">Address</span><span className="truncate">{conn.baseUrl}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Status</span><span>{conn.state}</span></div>
          <div className="flex justify-between"><span className="text-muted-foreground">Version</span><span>{conn.health?.version ?? "—"}</span></div>
          <Button variant="outline" className="mt-2" onClick={() => setOpen(true)}>Change address</Button>
        </CardContent>
      </Card>
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
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Enter your password to confirm:</label>
              <Input
                type="password"
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
