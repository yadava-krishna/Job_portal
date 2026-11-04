import { useEffect, useState } from "react";
import { FileUp, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Field, NativeSelect } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import type { ClippedJob } from "@/lib/clipper";
import { useImportFile, useImportJob } from "@/services/queries";

interface Form {
  url: string; title: string; company: string; location: string; description: string; posted_date: string;
  salary: string; experience: string; work_mode: string; questions: string;
}
const empty: Form = { url: "", title: "", company: "", location: "", description: "", posted_date: "", salary: "", experience: "", work_mode: "", questions: "" };

/** Add a job by pasting it, uploading a file, or reviewing a page captured by the browser clipper. */
export function ImportDialog({ open, onOpenChange, clip, onImported }: {
  open: boolean; onOpenChange: (o: boolean) => void; clip?: ClippedJob | null; onImported?: (userJobId: number) => void;
}) {
  const [form, setForm] = useState<Form>(empty);
  const [pageDate, setPageDate] = useState(false);
  const importJob = useImportJob();
  const importFile = useImportFile();
  const fromClipper = !!clip;

  useEffect(() => {
    if (!open) return;
    if (clip) {
      setForm({ ...empty, url: clip.url ?? "", title: clip.title ?? "", company: clip.company ?? "", location: clip.location ?? "",
                description: clip.description ?? "", posted_date: clip.posted_date ?? "", salary: clip.salary ?? "", experience: clip.experience ?? "" });
      setPageDate(clip.posted_date_source === "page" && !!clip.posted_date);
    } else {
      setForm(empty);
      setPageDate(false);
    }
  }, [open, clip]);

  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = () => {
    const body: Record<string, unknown> = {
      url: form.url.trim() || null, title: form.title.trim() || null, company: form.company.trim() || null,
      location: form.location.trim() || null, description: form.description.trim() || null, posted_date: form.posted_date.trim() || null,
      salary: form.salary.trim() || null, experience: form.experience.trim() || null, work_mode: form.work_mode || null,
      screening_questions: form.questions.split("\n").map((q) => q.trim()).filter(Boolean),
      posted_date_source: pageDate ? "page" : "user", captured_via: fromClipper ? "clipper" : "form",
    };
    importJob.mutate(body, {
      onSuccess: (r) => {
        const dup = r.run.duplicates > 0;
        toast.success(dup ? "This job is already in your feed (updated with any new details)" : "Job added and scored");
        onOpenChange(false);
        if (r.user_job_ids[0]) onImported?.(r.user_job_ids[0]);
      },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  const upload = (file: File | undefined) => {
    if (!file) return;
    importFile.mutate(file, {
      onSuccess: (r) => {
        toast.success(`${r.run.jobs_new} new, ${r.run.duplicates} already in your feed${r.errors.length ? `, ${r.errors.length} skipped` : ""}`);
        if (r.errors.length) r.errors.slice(0, 3).forEach((e) => toast.error(e));
        onOpenChange(false);
      },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{fromClipper ? "Review captured job" : "Add a job"}</DialogTitle>
          <DialogDescription>
            {fromClipper
              ? "Captured from the page you were viewing. Check the details, then save. It will be scored against your profile."
              : "Paste a LinkedIn, Indeed or Naukri job, or upload a file. The full description gives the most accurate match score."}
          </DialogDescription>
        </DialogHeader>
        <Tabs defaultValue="paste">
          {!fromClipper && (
            <TabsList><TabsTrigger value="paste">Paste details</TabsTrigger><TabsTrigger value="file">Upload file</TabsTrigger></TabsList>
          )}
          <TabsContent value="paste" className="space-y-3 pt-2">
            <Field label="Job URL" htmlFor="imp-url" hint="LinkedIn, Indeed or Naukri link (the platform and job ID are detected from it).">
              <Input id="imp-url" value={form.url} onChange={set("url")} placeholder="https://www.linkedin.com/jobs/view/…" />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Job title" htmlFor="imp-title"><Input id="imp-title" value={form.title} onChange={set("title")} /></Field>
              <Field label="Company" htmlFor="imp-company"><Input id="imp-company" value={form.company} onChange={set("company")} /></Field>
              <Field label="Location" htmlFor="imp-loc"><Input id="imp-loc" value={form.location} onChange={set("location")} placeholder="Bengaluru" /></Field>
              <Field label="Work mode" htmlFor="imp-mode">
                <NativeSelect id="imp-mode" value={form.work_mode} onChange={(v) => setForm((f) => ({ ...f, work_mode: v }))} className="w-full"
                              options={[{ value: "", label: "Not stated" }, { value: "Remote", label: "Remote" }, { value: "Hybrid", label: "Hybrid" }, { value: "On-site", label: "On-site" }]} />
              </Field>
              <Field label="Posted" htmlFor="imp-posted" hint={pageDate ? "Read from the listing page." : "YYYY-MM-DD, 'today' or '2 days ago'. Leave empty if unknown."}>
                <Input id="imp-posted" value={form.posted_date} onChange={(e) => { set("posted_date")(e); setPageDate(false); }} />
              </Field>
              <Field label="Experience" htmlFor="imp-exp"><Input id="imp-exp" value={form.experience} onChange={set("experience")} placeholder="3-6 years" /></Field>
              <Field label="Salary" htmlFor="imp-sal"><Input id="imp-sal" value={form.salary} onChange={set("salary")} placeholder="6-9 LPA" /></Field>
            </div>
            <Field label="Complete job description" htmlFor="imp-desc"><Textarea id="imp-desc" rows={9} value={form.description} onChange={set("description")} /></Field>
            <Field label="Screening questions shown on the application (one per line, optional)" htmlFor="imp-q">
              <Textarea id="imp-q" rows={3} value={form.questions} onChange={set("questions")} placeholder="What is your notice period?" />
            </Field>
          </TabsContent>
          <TabsContent value="file" className="space-y-3 pt-2">
            <p className="text-sm text-muted-foreground">JSON (list of jobs), CSV (columns: url, title, company, location, description, posted_date…) or TXT (Key: value lines, <code>---</code>, then the description; separate jobs with <code>===</code>). Max 2 MB.</p>
            <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed p-8 text-sm hover:bg-muted/50">
              {importFile.isPending ? <Loader2 className="animate-spin" /> : <FileUp className="size-6 text-muted-foreground" />}
              <span>Choose a .json, .csv or .txt file</span>
              <input type="file" accept=".json,.csv,.txt" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} />
            </label>
          </TabsContent>
        </Tabs>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={importJob.isPending || (!form.url.trim() && !form.title.trim())}>
            {importJob.isPending && <Loader2 className="animate-spin" />} Save & score
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
