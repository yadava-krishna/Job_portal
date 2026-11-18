import { useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, CircleHelp, Copy, Download, ExternalLink, FileText, Loader2, Puzzle, Wand2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, StatusBadge } from "@/components/app/common";
import { downloadFile, errorMessage } from "@/lib/api";
import { useApplicationAction, useApplyOptions } from "@/services/queries";
import { ResumeVersionPicker } from "@/features/studio/ResumePicker";
import type { AttachResult } from "@/features/studio/api";
import type { ApplicationDetail, UserJob } from "@/types/api";
import { cn } from "@/lib/utils";
import { canSmartApply, smartApplyStart, smartApplyStatus, type SmartApplyStatus } from "@/lib/smartApply";

type Step = "preparing" | "review" | "returned" | "done" | "error";

const checkIcon = {
  PASS: <CheckCircle2 className="size-4 text-emerald-600" />,
  CHECK: <CircleHelp className="size-4 text-sky-600" />,
  WARN: <AlertTriangle className="size-4 text-amber-600" />,
  ACTION: <AlertTriangle className="size-4 text-rose-600" />,
};

/**
 * Apply flow. The user always submits on the original platform:
 * prepare → review package → open listing in a new tab → come back → confirm (or not).
 * Opening the listing is never treated as applying.
 */
export function ApplyDialog({ item, onClose }: { item: UserJob | null; onClose: () => void }) {
  const action = useApplicationAction();
  const [step, setStep] = useState<Step>("preparing");
  const [app, setApp] = useState<ApplicationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reference, setReference] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [studioResume, setStudioResume] = useState<AttachResult | null>(null);
  const openedRef = useRef(false);
  const options = useApplyOptions(app?.id);
  // Smart Apply: undefined while checking, null when not installed in this browser.
  const [ext, setExt] = useState<SmartApplyStatus | null | undefined>(undefined);
  const [starting, setStarting] = useState(false);
  useEffect(() => {
    if (!item) return;
    const check = () => { smartApplyStatus().then(setExt).catch(() => setExt(null)); };
    check();
    window.addEventListener("focus", check);  // picks up an install or a connection made in another tab
    return () => window.removeEventListener("focus", check);
  }, [item]);

  useEffect(() => {
    if (!item) return;
    setStep("preparing");
    setApp(null);
    setError(null);
    setReference("");
    setConfirmation("");
    setStudioResume(null);
    openedRef.current = false;
    action.mutate({ kind: "prepare", userJobId: item.user_job_id }, {
      onSuccess: (a) => {
        setApp(a);
        setStep(a.status === "SUBMITTED" ? "done" : a.status === "OPENED" || a.status === "CONFIRMATION_PENDING" ? "returned" : "review");
      },
      onError: (e) => { setError(errorMessage(e)); setStep("error"); },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.user_job_id]);

  // When the user comes back to this tab after opening the listing, refresh the application (Smart Apply may already
  // have recorded the submission from the employer's thank-you page) and otherwise ask for the outcome.
  useEffect(() => {
    const onFocus = () => {
      if (!openedRef.current || step !== "review" || !item) return;
      setStep("returned");
      action.mutate({ kind: "prepare", userJobId: item.user_job_id }, {
        onSuccess: (a) => { setApp(a); if (a.status === "SUBMITTED") setStep("done"); },
      });
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, item?.user_job_id]);

  if (!item) return null;
  const busy = action.isPending;

  const hostedUrl = options.data?.hosted_form_url ?? null;
  const openListing = (url: string | null = item.job.job_url) => {
    if (!app || !url) return;
    // Open synchronously in the click handler (pop-up blockers), then record the event.
    window.open(url, "_blank", "noopener,noreferrer");
    openedRef.current = true;
    action.mutate({ kind: "open", id: app.id }, {
      onSuccess: (a) => setApp(a),
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  const formTarget = hostedUrl ?? item.job.job_url;
  const smart = canSmartApply(formTarget);
  const smartReady = smart && !!ext?.connected;
  const startSmartApply = async () => {
    if (!app || !formTarget) return;
    setStarting(true);
    try {
      await smartApplyStart(formTarget, item.user_job_id);
      openedRef.current = true;
      toast.success("Opened the form. Smart Apply is filling it now: check every answer in its panel, then submit there.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Smart Apply couldn't open this form.");
    } finally {
      setStarting(false);
    }
  };

  const confirm = (submitted: boolean) => {
    if (!app) return;
    action.mutate({ kind: "confirm", id: app.id, submitted, reference_id: reference, confirmation_text: confirmation }, {
      onSuccess: (a) => {
        setApp(a);
        if (submitted) { setStep("done"); toast.success("Marked as applied"); }
        else { toast("Left as not applied. You can apply later."); onClose(); }
      },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  const later = () => {
    if (!app) return;
    action.mutate({ kind: "pending", id: app.id }, { onSuccess: () => { toast("Saved as confirmation pending"); onClose(); } });
  };

  return (
    <Dialog open={!!item} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Apply: {item.job.title}</DialogTitle>
          <DialogDescription>{item.job.company} · {item.job.platform}{app && <> · <StatusBadge status={app.status} /></>}</DialogDescription>
        </DialogHeader>

        <Steps step={step} />

        {step === "preparing" && <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> Preparing your application package…</div>}
        {step === "error" && <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}

        {app && step === "review" && (
          <div className="space-y-5">
            <section>
              <h3 className="mb-2 text-sm font-semibold">Checklist</h3>
              <ul className="space-y-1.5">
                {app.checklist.map((c, i) => (
                  <li key={i} className="flex gap-2 text-sm">{checkIcon[c.status]}<span><span className="font-medium">{c.check}</span>{c.detail && <span className="text-muted-foreground">: {c.detail}</span>}</span></li>
                ))}
              </ul>
            </section>
            <section>
              <h3 className="mb-2 text-sm font-semibold">Screening questions and prepared answers</h3>
              <div className="divide-y rounded-lg border">
                {app.screening_answers.map((s) => (
                  <div key={s.question} className="flex flex-col gap-1 p-3 text-sm sm:flex-row sm:justify-between">
                    <span className="font-medium">{s.question}</span>
                    <span className={cn("sm:max-w-[55%] sm:text-right", s.status === "NEEDS_CANDIDATE_INPUT" ? "font-medium text-rose-600" : "text-muted-foreground")}>
                      {s.status === "NEEDS_CANDIDATE_INPUT" ? "Needs your input" : s.answer}
                    </span>
                  </div>
                ))}
              </div>
              {app.needs_candidate_input.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Answers marked "Needs your input" are never guessed. Add verified answers in Settings → Verified answers.</p>}
            </section>
            <section className="space-y-2 rounded-lg border p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="flex items-center gap-2"><FileText className="size-4" /> Resume for this application: <span className="font-medium">{app.resume_used ?? "none uploaded"}</span></span>
                {app.resume_used && (
                  <Button size="sm" variant="ghost" onClick={() => {
                    const path = studioResume?.resume_export_id ? `/studio/exports/${studioResume.resume_export_id}/download` : "/profile/resume";
                    downloadFile(path, studioResume ? "resume.pdf" : app.resume_used ?? "resume.pdf").catch((e) => toast.error(errorMessage(e)));
                  }}>Download</Button>
                )}
              </div>
              <ResumeVersionPicker applicationId={app.id}
                                   initialVersionId={(app as unknown as { resume_version_id?: number | null }).resume_version_id ?? null}
                                   onAttached={(r) => { setStudioResume(r); setApp({ ...app, resume_used: r.resume_used ?? app.resume_used }); }} />
            </section>
            {app.cover_letter && (
              <section>
                <div className="mb-2 flex items-center justify-between"><h3 className="text-sm font-semibold">Cover letter (from your resume facts)</h3>
                  <Button size="sm" variant="ghost" onClick={() => { void navigator.clipboard.writeText(app.cover_letter ?? ""); toast.success("Copied"); }}><Copy /> Copy</Button></div>
                <div className="max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg border bg-muted/40 p-3 text-sm">{app.cover_letter}</div>
              </section>
            )}
            {options.data && (
              <SmartApplyCard message={options.data.message} smart={smart} ext={ext} onClose={onClose} />
            )}
            <p className="rounded-lg bg-muted p-3 text-sm">
              {smartReady
                ? <>Next: click <strong>Apply with Smart Apply</strong>, check the filled form, submit it on {item.job.platform}, then come back here. If Smart Apply saw the employer's thank-you page, it's already recorded for you.</>
                : <>Next: open the original listing, complete the application <strong>on {item.job.platform}</strong>, then come back here and confirm.</>}
              {" "}Opening the form does not mark it as applied.
            </p>
          </div>
        )}

        {app && step === "returned" && (
          <div className="space-y-4">
            <p className="text-sm">Did you submit the application on {item.job.platform}?</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Application / reference ID (optional)" htmlFor="ref"><Input id="ref" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. shown on the confirmation page" /></Field>
              <Field label="Confirmation message (optional)" htmlFor="conf"><Textarea id="conf" rows={2} value={confirmation} onChange={(e) => setConfirmation(e.target.value)} placeholder="e.g. Your application was sent to …" /></Field>
            </div>
          </div>
        )}

        {app && step === "done" && (
          <div className="flex items-start gap-3 rounded-lg bg-emerald-50 p-4 text-sm text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100">
            <CheckCircle2 className="mt-0.5 size-5 shrink-0" />
            <div>Recorded as applied{app.submitted_at ? ` on ${new Date(app.submitted_at).toLocaleString()}` : ""}.{app.reference_id ? ` Reference: ${app.reference_id}.` : ""} You can track its progress under Applications.</div>
          </div>
        )}

        <DialogFooter className="flex-wrap gap-2">
          {step === "review" && (
            <>
              <Button variant="outline" onClick={onClose}>Close</Button>
              <Button variant="outline" onClick={() => setStep("returned")}>I already applied</Button>
              {smartReady ? (
                <>
                  <Button variant="outline" onClick={() => openListing(formTarget)} disabled={busy || starting}><ExternalLink /> Apply by hand</Button>
                  <Button onClick={startSmartApply} disabled={busy || starting} data-testid="smart-apply-start">
                    {starting ? <Loader2 className="animate-spin" /> : <Wand2 />} Apply with Smart Apply
                  </Button>
                </>
              ) : hostedUrl ? (
                <>
                  <Button variant="outline" onClick={() => openListing()} disabled={busy || !item.job.job_url}><ExternalLink /> Employer's listing</Button>
                  <Button onClick={() => openListing(hostedUrl)} disabled={busy}><ExternalLink /> Open Greenhouse application form</Button>
                </>
              ) : (
                <Button onClick={() => openListing()} disabled={busy || !item.job.job_url}><ExternalLink /> Open original listing</Button>
              )}
            </>
          )}
          {step === "returned" && (
            <>
              <Button variant="ghost" className="mr-auto" onClick={() => { openedRef.current = false; setStep("review"); }} disabled={busy}><ArrowLeft /> Back to package</Button>
              <Button variant="outline" onClick={() => openListing(hostedUrl ?? item.job.job_url)} disabled={busy}><ExternalLink /> Reopen listing</Button>
              <Button variant="outline" onClick={later} disabled={busy}>Not sure yet</Button>
              <Button variant="outline" onClick={() => confirm(false)} disabled={busy}><XCircle /> I didn't apply</Button>
              <Button onClick={() => confirm(true)} disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Yes, I submitted it</Button>
            </>
          )}
          {(step === "done" || step === "error") && <Button onClick={onClose}>Done</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Steps({ step }: { step: Step }) {
  const order = ["review", "returned", "done"];
  const idx = step === "preparing" ? 0 : Math.max(0, order.indexOf(step));
  const labels = ["Review package", "Apply on platform & confirm", "Applied"];
  return (
    <ol className="flex items-center gap-2 text-xs">
      {labels.map((l, i) => (
        <li key={l} className="flex items-center gap-2">
          <span className={cn("flex size-5 items-center justify-center rounded-full border text-[10px] font-semibold", i <= idx ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground")}>{i + 1}</span>
          <span className={cn(i <= idx ? "font-medium" : "text-muted-foreground")}>{l}</span>
          {i < labels.length - 1 && <span className="h-px w-4 bg-border" />}
        </li>
      ))}
    </ol>
  );
}

const EXT_ZIP = `${import.meta.env.BASE_URL}downloads/jobpilot-smart-apply-2.1.0.zip`;

/** Where Smart Apply stands in this browser, and the one next step to make one-click applying work. */
function SmartApplyCard({ message, smart, ext, onClose }: { message: string; smart: boolean; ext: SmartApplyStatus | null | undefined; onClose: () => void }) {
  const ready = smart && !!ext?.connected;
  const tone = ready ? "border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100"
    : smart ? "border-sky-300 bg-sky-50 text-sky-950 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-100" : "";
  return (
    <section className={cn("flex gap-2 rounded-lg border p-3 text-sm", tone)} data-testid="smart-apply-card">
      {ready ? <Wand2 className="mt-0.5 size-4 shrink-0" /> : <Puzzle className="mt-0.5 size-4 shrink-0" />}
      <div className="space-y-1">
        <p className={smart ? "text-xs opacity-80" : undefined}>{message}</p>
        {smart && ready && (
          <p><strong>Smart Apply is ready.</strong> Click <strong>Apply with Smart Apply</strong>: the form opens in a new tab and fills itself
            from your profile, with your resume attached. Check every answer in the panel, then submit. Nothing is sent without your click.</p>
        )}
        {smart && ext === undefined && <p className="flex items-center gap-2"><Loader2 className="size-3.5 animate-spin" /> Checking for Smart Apply in this browser…</p>}
        {smart && ext && !ext.connected && (
          <p><strong>Smart Apply is installed but not connected.</strong> Connect it once and this form will fill itself.{" "}
            <a href="#/settings?tab=extension" className="underline underline-offset-2" onClick={onClose}>Connect it now</a></p>
        )}
        {smart && ext === null && (
          <>
            <p><strong>Apply in one click with Smart Apply.</strong> This form can be filled for you. Install the free browser extension once (two minutes), then use <strong>Apply with Smart Apply</strong>.</p>
            <div className="flex flex-wrap items-center gap-2 pt-1" data-testid="apply-extension-cta">
              <Button size="xs" variant="outline" render={<a href={EXT_ZIP} download />}><Download /> Get the Smart Apply extension</Button>
              <a href="#/settings?tab=extension" className="text-xs underline underline-offset-2" onClick={onClose}>How to set it up</a>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
