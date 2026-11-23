import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, FileUp, Loader2, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Field, NativeSelect } from "@/components/app/common";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
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

// ---- Guided import of one job link (Portal Connections) ---------------------------------------------------------------
// The same import as "Add a job" above (POST /jobs/import, same validation), in steps: paste the link, see what JobPilot
// recognises from the link itself (portal, job ID, already in your feed?), add the details from the listing, review,
// save, then continue to the Apply Workspace. JobPilot never downloads the portal's page.

type Portal = "LinkedIn" | "Naukri" | "Indeed";
interface Preview { recognized: boolean; platform: Portal | null; job_id: string | null; url: string | null; detail: string;
  existing: { user_job_id: number; title: string; company: string } | null }
const HOMES: Record<Portal, string> = { LinkedIn: "https://www.linkedin.com/jobs/", Naukri: "https://www.naukri.com/", Indeed: "https://in.indeed.com/" };

function basicUrlProblem(raw: string): string | null {
  if (!raw.trim()) return "Paste the job's link first.";
  try {
    const u = new URL(raw.trim());
    return u.protocol === "https:" || u.protocol === "http:" ? null : "That isn't a web link. Copy it from the browser's address bar.";
  } catch {
    return "That doesn't look like a link. Copy it from the browser's address bar (it starts with https://).";
  }
}

export function GuidedImportDialog({ open, onOpenChange, platform, onPrepare, onView }: {
  open: boolean; onOpenChange: (o: boolean) => void; platform?: Portal | null;
  onPrepare: (userJobId: number) => void; onView: (userJobId: number) => void;
}) {
  const [step, setStep] = useState<"link" | "details" | "review" | "done">("link");
  const [url, setUrl] = useState("");
  const [urlProblem, setUrlProblem] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [manualPlatform, setManualPlatform] = useState<Portal>(platform ?? "LinkedIn");
  const [form, setForm] = useState<Form>(empty);
  const [result, setResult] = useState<{ id: number; duplicate: boolean } | null>(null);
  const importJob = useImportJob();
  const check = useMutation({
    mutationFn: async (link: string) => (await api.post<Preview>("/jobs/import/preview", { url: link })).data,
    onSuccess: (p) => setPreview(p),
    onError: (e) => setUrlProblem(errorMessage(e)),
  });

  useEffect(() => {
    if (!open) return;
    setStep("link"); setUrl(""); setUrlProblem(null); setPreview(null); setForm(empty); setResult(null);
    setManualPlatform(platform ?? "LinkedIn");
    importJob.reset(); check.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, platform]);

  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const recognised = preview?.recognized ? preview : null;
  const where = recognised?.platform ?? (preview ? manualPlatform : platform ?? null);
  const submitLink = () => {
    const bad = basicUrlProblem(url);
    setUrlProblem(bad);
    setPreview(null);
    if (!bad) check.mutate(url.trim());
  };
  const save = () => {
    const body: Record<string, unknown> = {
      url: recognised?.url ?? null, platform: recognised ? null : manualPlatform,
      title: form.title.trim() || null, company: form.company.trim() || null, location: form.location.trim() || null,
      description: form.description.trim() || null, posted_date: form.posted_date.trim() || null, salary: form.salary.trim() || null,
      experience: form.experience.trim() || null, work_mode: form.work_mode || null, screening_questions: [],
      posted_date_source: "user", captured_via: "form",
    };
    importJob.mutate(body, {
      onSuccess: (r) => {
        if (r.user_job_ids[0]) { setResult({ id: r.user_job_ids[0], duplicate: r.run.duplicates > 0 }); setStep("done"); }
        else toast.error(r.errors[0] ?? "JobPilot couldn't save this job.");
      },
    });
  };
  const words = form.description.trim() ? form.description.trim().split(/\s+/).length : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-xl" data-testid="guided-import">
        <DialogHeader>
          <DialogTitle>{step === "done" ? "Job saved" : `Import a ${platform ?? "job"} link`}</DialogTitle>
          <DialogDescription>
            {step === "link" ? "JobPilot reads the link only. It never downloads the page or signs in anywhere for you."
              : step === "details" ? "Copy these from the listing you have open. The full description gives the most accurate match."
              : step === "review" ? "Check what will be saved. Nothing is saved until you confirm."
              : "Scored against your profile. Continue to the Apply Workspace when you're ready."}
          </DialogDescription>
        </DialogHeader>
        <ol className="flex gap-1.5" aria-label="Progress">
          {(["link", "details", "review", "done"] as const).map((s, i) => (
            <li key={s} aria-current={s === step ? "step" : undefined}
                className={cn("h-1 flex-1 rounded-full", ["link", "details", "review", "done"].indexOf(step) >= i ? "bg-route" : "bg-border")}>
              <span className="sr-only">{["Link", "Details", "Review", "Saved"][i]}</span>
            </li>
          ))}
        </ol>

        {step === "link" && (
          <div className="space-y-3">
            <ol className="list-decimal space-y-1 pl-5 text-sm marker:font-semibold marker:text-route">
              <li>Open a job on {platform ? <a href={HOMES[platform]} target="_blank" rel="noopener noreferrer" className="font-medium text-route underline-offset-4 hover:underline">{platform}</a> : "LinkedIn, Indeed or Naukri"} in another tab.</li>
              <li>Copy its link from the address bar.</li>
              <li>Paste it here and check it.</li>
            </ol>
            <form className="flex items-start gap-2" onSubmit={(e) => { e.preventDefault(); submitLink(); }}>
              <div className="min-w-0 flex-1">
                <label htmlFor="gi-url" className="sr-only">Job link</label>
                <Input id="gi-url" value={url} onChange={(e) => { setUrl(e.target.value); setUrlProblem(null); }} inputMode="url" autoFocus
                       placeholder={platform === "Naukri" ? "https://www.naukri.com/job-listings-…" : platform === "Indeed" ? "https://in.indeed.com/viewjob?jk=…" : "https://www.linkedin.com/jobs/view/…"}
                       aria-invalid={!!urlProblem} aria-describedby={urlProblem ? "gi-url-problem" : undefined} />
              </div>
              <Button type="submit" disabled={check.isPending}>{check.isPending ? <Loader2 className="animate-spin" /> : <Search />} Check link</Button>
            </form>
            {urlProblem && <p id="gi-url-problem" role="alert" className="text-sm text-destructive">{urlProblem}</p>}
            {preview && (preview.recognized ? (
              <div className="rounded-xl bg-success-tint/60 p-3 text-sm ring-1 ring-success/25" data-testid="link-recognised">
                <p className="flex items-center gap-1.5 font-medium text-success"><CheckCircle2 className="size-4" aria-hidden /> {preview.platform} job{preview.job_id ? ` ${preview.job_id}` : ""} recognised</p>
                {platform && preview.platform !== platform && <p className="mt-1 text-xs text-foreground">That's a {preview.platform} link, not {platform}. That's fine: it's saved as {preview.platform}.</p>}
                {preview.existing ? (
                  <div className="mt-2 space-y-2">
                    <p className="text-foreground">Already in your jobs: <b>{preview.existing.title || "Untitled"}</b>{preview.existing.company ? ` at ${preview.existing.company}` : ""}.</p>
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" onClick={() => { onOpenChange(false); onPrepare(preview.existing!.user_job_id); }}>Prepare application <ArrowRight /></Button>
                      <Button size="sm" variant="outline" onClick={() => setStep("details")}>Add details anyway</Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="mt-1 text-xs text-muted-foreground">{preview.detail}</p>
                    <Button size="sm" className="mt-2" onClick={() => setStep("details")}>Add details <ArrowRight /></Button>
                  </>
                )}
              </div>
            ) : (
              <div role="alert" className="rounded-xl bg-caution-tint p-3 text-sm text-caution ring-1 ring-caution/25" data-testid="link-unrecognised">
                <p>{preview.detail}</p>
                <Button size="sm" variant="outline" className="mt-2" onClick={() => setStep("details")}>Enter details manually</Button>
              </div>
            ))}
          </div>
        )}

        {step === "details" && (
          <div className="space-y-3">
            {!recognised && (
              <Field label="Portal" htmlFor="gi-platform" hint="The link wasn't recognised, so it isn't saved. Pick where the job is listed.">
                <NativeSelect id="gi-platform" value={manualPlatform} onChange={(v) => setManualPlatform(v as Portal)} className="w-full"
                              options={(["LinkedIn", "Naukri", "Indeed"] as const).map((x) => ({ value: x, label: x }))} />
              </Field>
            )}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Job title (required)" htmlFor="gi-title"><Input id="gi-title" value={form.title} onChange={set("title")} /></Field>
              <Field label="Company" htmlFor="gi-company"><Input id="gi-company" value={form.company} onChange={set("company")} /></Field>
              <Field label="Location" htmlFor="gi-loc"><Input id="gi-loc" value={form.location} onChange={set("location")} placeholder="Bengaluru" /></Field>
              <Field label="Experience" htmlFor="gi-exp"><Input id="gi-exp" value={form.experience} onChange={set("experience")} placeholder="3-6 years" /></Field>
            </div>
            <Field label="Job description" htmlFor="gi-desc" hint="Paste the whole description from the listing.">
              <Textarea id="gi-desc" rows={7} value={form.description} onChange={set("description")} />
            </Field>
            <DialogFooter>
              <Button variant="outline" onClick={() => setStep("link")}>Back</Button>
              <Button onClick={() => setStep("review")} disabled={!form.title.trim()}>Review</Button>
            </DialogFooter>
          </div>
        )}

        {step === "review" && (
          <div className="space-y-3">
            <dl className="divide-y rounded-xl text-sm ring-1 ring-border" data-testid="import-review">
              {([
                ["Portal", where], ["Job ID", recognised?.job_id ?? "None (no recognised link)"], ["Link", recognised?.url ?? "Not saved"],
                ["Title", form.title], ["Company", form.company || "Not given"], ["Location", form.location || "Not given"],
                ["Description", words ? `${words} words` : "None"],
              ] as const).map(([k, v]) => (
                <div key={k} className="flex gap-3 px-3 py-2"><dt className="w-24 shrink-0 text-muted-foreground">{k}</dt><dd className="min-w-0 break-words">{v}</dd></div>
              ))}
            </dl>
            {!words && <p className="text-xs text-caution">Without the description, the match score is a rough guess. You can add it later.</p>}
            {importJob.isError && <p role="alert" className="text-sm text-destructive">{errorMessage(importJob.error)}</p>}
            <DialogFooter>
              <Button variant="outline" onClick={() => setStep("details")} disabled={importJob.isPending}>Back</Button>
              <Button onClick={save} disabled={importJob.isPending}>
                {importJob.isPending ? <><Loader2 className="animate-spin" /> Saving and scoring…</> : "Save & score"}
              </Button>
            </DialogFooter>
          </div>
        )}

        {step === "done" && result && (
          <div className="space-y-3" data-testid="import-done">
            <p className="flex items-center gap-1.5 text-sm font-medium text-success"><CheckCircle2 className="size-4" aria-hidden />
              {result.duplicate ? "It was already in your jobs, so it was updated with these details." : "Added to your jobs and scored."}</p>
            <DialogFooter className="sm:justify-between">
              <Button variant="ghost" onClick={() => { setStep("link"); setUrl(""); setPreview(null); setForm(empty); setResult(null); importJob.reset(); }}>Import another</Button>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => { onOpenChange(false); onView(result.id); }}>View in Discover</Button>
                <Button onClick={() => { onOpenChange(false); onPrepare(result.id); }}>Prepare application <ArrowRight /></Button>
              </div>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
