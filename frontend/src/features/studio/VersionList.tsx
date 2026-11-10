import { useState, type FormEvent } from "react";
import { Copy, FileText, Loader2, Plus, Trash2 } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { EmptyState, Field, PageHeader } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useCloneVersion, useCreateVersion, useDeleteVersion, useStudioTemplates, useStudioVersions, type TemplateKey, type VersionSummary } from "./api";
import { AtsBadge, ConfirmDialog, JobPicker, TemplatePicker, VersionStatusBadge } from "./parts";

export function VersionList() {
  const versions = useStudioVersions();
  const clone = useCloneVersion();
  const del = useDeleteVersion();
  const navigate = useNavigate();
  // Arriving from a job ("Tailor a resume" in the job details) opens the new-resume dialog targeted at that job.
  const [params] = useSearchParams();
  const jobParam = Number(params.get("job")) || null;
  const [creating, setCreating] = useState(jobParam !== null);
  const [toDelete, setToDelete] = useState<VersionSummary | null>(null);
  const list = Array.isArray(versions.data) ? versions.data : [];
  const byId = new Map(list.map((v) => [v.id, v]));

  const copy = (v: VersionSummary) => clone.mutate({ id: v.id }, {
    onSuccess: (n) => { toast.success("Copy created"); navigate(`/studio/${n.id}`); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = () => {
    if (!toDelete) return;
    del.mutate(toDelete.id, {
      onSuccess: () => { toast.success("Version deleted"); setToDelete(null); },
      onError: (e) => { toast.error(errorMessage(e)); setToDelete(null); },
    });
  };

  return (
    <>
      <PageHeader title="Resume Studio" description="Tailored resume versions built from your confirmed profile. Each version keeps its own content, template and history."
                  actions={<Button size="sm" onClick={() => setCreating(true)}><Plus /> New resume</Button>} />
      {versions.isLoading ? <Loader2 className="animate-spin" /> : versions.isError ? (
        <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{errorMessage(versions.error, "Couldn't load your resume versions")}</p>
      ) : !list.length ? (
        <EmptyState icon={<FileText className="size-8" />} title="No resume versions yet">
          A new resume starts from your confirmed profile (experience, education, skills) so nothing is invented.
          You can then reword, reorder and hide things for a specific job, and export PDF or Word.
          <div className="mt-4"><Button size="sm" onClick={() => setCreating(true)}><Plus /> New resume</Button></div>
        </EmptyState>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="border-b bg-muted/50 text-left text-muted-foreground">
              <tr>{["Name", "Template", "Status", "Updated", "Copied from", ""].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y">
              {list.map((v) => {
                const parent = v.parent_id ? byId.get(v.parent_id) : null;
                return (
                  <tr key={v.id} className="hover:bg-muted/30">
                    <td className="px-3 py-2 font-medium"><Link to={`/studio/${v.id}`} className="hover:underline">{v.name}</Link></td>
                    <td className="px-3 py-2"><span className="flex items-center gap-2">{v.template_name}<AtsBadge safe={v.ats_safe} /></span></td>
                    <td className="px-3 py-2"><VersionStatusBadge status={v.status} /></td>
                    <td className="px-3 py-2 whitespace-nowrap text-muted-foreground">{timeAgo(v.updated_at)}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {v.parent_id ? parent ? <Link to={`/studio/${parent.id}`} className="hover:underline">{parent.name}</Link> : <span>a deleted version</span> : "—"}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex justify-end gap-1">
                        <Button size="xs" variant="outline" render={<Link to={`/studio/${v.id}`} />}>{v.status === "locked" ? "View" : "Edit"}</Button>
                        <Button size="icon-xs" variant="ghost" aria-label={`Make a copy of ${v.name}`} onClick={() => copy(v)} disabled={clone.isPending}><Copy /></Button>
                        <Button size="icon-xs" variant="ghost" aria-label={`Delete ${v.name}`} disabled={v.status === "locked"}
                                title={v.status === "locked" ? "Kept as a record of a submitted application" : undefined} onClick={() => setToDelete(v)}><Trash2 /></Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
      <NewResumeDialog open={creating} onOpenChange={setCreating} initialJob={jobParam} />
      <ConfirmDialog open={!!toDelete} title="Delete this resume version?" confirmLabel="Delete version" busy={del.isPending}
                     onConfirm={remove} onCancel={() => setToDelete(null)}>
        "{toDelete?.name}" and its exported files will be removed. This can't be undone. Your profile is not affected.
      </ConfirmDialog>
    </>
  );
}

export function NewResumeDialog({ open, onOpenChange, initialJob = null }: { open: boolean; onOpenChange: (o: boolean) => void; initialJob?: number | null }) {
  const templates = useStudioTemplates();
  const create = useCreateVersion();
  const navigate = useNavigate();
  const [name, setName] = useState("My resume");
  const [template, setTemplate] = useState<TemplateKey>("ats_simple");
  const [job, setJob] = useState<number | null>(initialJob);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate({ name: name.trim() || "My resume", template_key: template, target_user_job_id: job }, {
      onSuccess: (v) => { onOpenChange(false); toast.success("Resume created from your profile"); navigate(`/studio/${v.id}`); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>New resume</DialogTitle>
          <DialogDescription>It is filled from your confirmed profile. You can change everything afterwards; your profile itself is not changed.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" htmlFor="nr-name" hint="Only you see this, e.g. “AR analyst — Stripe”.">
              <Input id="nr-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Target job (optional)" htmlFor="nr-job" hint="Used for job-specific checks and suggestions.">
              <JobPicker id="nr-job" value={job} onChange={setJob} />
            </Field>
          </div>
          <div className="space-y-1.5">
            <span className="text-sm font-medium">Template</span>
            {templates.isLoading ? <Loader2 className="animate-spin" /> : (
              <TemplatePicker templates={Array.isArray(templates.data) ? templates.data : []} value={template} onChange={setTemplate} />
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={create.isPending}>{create.isPending && <Loader2 className="animate-spin" />} Create resume</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
