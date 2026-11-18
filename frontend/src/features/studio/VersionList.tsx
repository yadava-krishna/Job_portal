import { useState, type FormEvent } from "react";
import { Copy, FileText, Loader2, Lock, Plus, Trash2 } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, LoadingState, PageHeader } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCloneVersion, useCreateVersion, useDeleteVersion, useStudioTemplates, useStudioVersions, type TemplateKey, type VersionSummary } from "./api";
import { templateName } from "./templateCopy";
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
    onSuccess: (n) => { toast.success("Copy made. Same energy, new version."); navigate(`/studio/${n.id}`); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = () => {
    if (!toDelete) return;
    del.mutate(toDelete.id, {
      onSuccess: () => { toast.success("Version deleted. Gone, reduced to atoms."); setToDelete(null); },
      onError: (e) => { toast.error(errorMessage(e)); setToDelete(null); },
    });
  };

  const drafts = list.filter((v) => v.status === "draft").length;
  const locked = list.filter((v) => v.status === "locked").length;

  return (
    <>
      <PageHeader title={<>Resume <em>Studio</em></>} description="Your resume glow-up lab. Make a version for each job from your confirmed profile; each one keeps its own content, design and history."
                  actions={<Button onClick={() => setCreating(true)}><Plus /> New resume</Button>} />
      {versions.isLoading ? <LoadingState /> : versions.isError ? (
        <p className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{errorMessage(versions.error, "Couldn't load your resume versions")}</p>
      ) : !list.length ? (
        <div className="flex flex-col items-center rounded-2xl bg-card px-6 py-14 text-center ring-1 ring-border">
          <span className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-lavender text-violet"><FileText className="size-7" /></span>
          <h2 className="font-display text-[20px] font-extrabold tracking-[-0.02em] text-heading">No resumes yet. Let's build your first one.</h2>
          <p className="mt-2 max-w-lg text-sm text-muted-foreground">
            A new resume starts from your confirmed profile (experience, education, skills) so nothing is invented.
            You can then reword, reorder and hide things for a specific job, and export PDF or Word.
          </p>
          <div className="mt-5"><Button onClick={() => setCreating(true)}><Plus /> New resume</Button></div>
        </div>
      ) : (
        <>
          <p className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted-foreground">
            <span><span className="readout font-medium text-foreground">{list.length}</span> version{list.length === 1 ? "" : "s"}</span>
            <span aria-hidden>·</span><span><span className="readout">{drafts}</span> editable</span>
            {locked > 0 && <><span aria-hidden>·</span><span className="inline-flex items-center gap-1"><Lock className="size-3 text-caution" aria-hidden /><span className="readout">{locked}</span> kept as sent</span></>}
          </p>
          <div className="overflow-x-auto rounded-2xl bg-card ring-1 ring-border">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="border-b text-left">
                <tr>{["Name", "Template", "Status", "Updated", "Copied from", ""].map((h, i) => <th key={i} className="eyebrow px-4 py-2.5 font-normal">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y">
                {list.map((v) => {
                  const parent = v.parent_id ? byId.get(v.parent_id) : null;
                  return (
                    <tr key={v.id} className="group/row transition-colors duration-150 hover:bg-paper-sunk/60">
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-3">
                          <span aria-hidden className={cn("flex size-9 shrink-0 items-center justify-center rounded-xl", v.status === "locked" ? "bg-caution-tint text-caution" : "bg-route-tint text-route")}>
                            {v.status === "locked" ? <Lock className="size-4" /> : <FileText className="size-4" />}
                          </span>
                          <Link to={`/studio/${v.id}`} className="font-display text-[14.5px] font-bold text-heading decoration-route/40 underline-offset-4 hover:underline">{v.name}</Link>
                        </span>
                      </td>
                      <td className="px-4 py-3"><span className="flex flex-wrap items-center gap-2">{templateName(v.template_key, v.template_name)}<AtsBadge safe={v.ats_safe} /></span></td>
                      <td className="px-4 py-3 whitespace-nowrap"><VersionStatusBadge status={v.status} /></td>
                      <td className="px-4 py-3 text-[13px] whitespace-nowrap text-muted-foreground">{timeAgo(v.updated_at)}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {v.parent_id ? parent ? <Link to={`/studio/${parent.id}`} className="hover:text-foreground hover:underline">{parent.name}</Link> : <span>a deleted version</span> : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="outline" render={<Link to={`/studio/${v.id}`} />}>{v.status === "locked" ? "View" : "Edit"}</Button>
                          <Button size="icon-sm" variant="ghost" aria-label={`Make a copy of ${v.name}`} title="Make a copy" onClick={() => copy(v)} disabled={clone.isPending}><Copy /></Button>
                          <Button size="icon-sm" variant="ghost" aria-label={`Delete ${v.name}`} disabled={v.status === "locked"} className="hover:text-destructive"
                                  title={v.status === "locked" ? "Kept as a record of a submitted application" : "Delete"} onClick={() => setToDelete(v)}><Trash2 /></Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
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
      onSuccess: (v) => { onOpenChange(false); toast.success("Resume created from your profile. Let's tailor it."); navigate(`/studio/${v.id}`); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>New resume</DialogTitle>
          <DialogDescription>We fill it in from your confirmed profile. Edit anything you like afterwards; your profile stays as it is.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" htmlFor="nr-name" hint="Only you see this, e.g. “AR analyst — Stripe”.">
              <Input id="nr-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Target job (optional)" htmlFor="nr-job" hint="Pick a job and the checks and suggestions get tailored to it.">
              <JobPicker id="nr-job" value={job} onChange={setJob} />
            </Field>
          </div>
          <div className="space-y-1.5">
            <span className="text-sm font-medium">Template</span>
            {templates.isLoading ? <LoadingState /> : (
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
