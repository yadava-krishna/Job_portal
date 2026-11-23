import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, BadgeCheck, Check, CheckCircle2, CircleHelp, Copy, Download, ExternalLink, Eye, FileText, Loader2, MousePointerClick, Puzzle, Wand2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field } from "@/components/app/common";
import { CompanyMark } from "@/components/app/JobCard";
import { downloadFile, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApplicationAction, useApplyOptions, useApplyPackage, useApplyWorkspace } from "@/services/queries";
import { ResumeVersionPicker } from "@/features/studio/ResumePicker";
import type { AttachResult } from "@/features/studio/api";
import { ApplyStatePill, StatusPill } from "@/features/applications/pills";
import { AnswersEditor } from "@/features/apply/AnswersEditor";
import { ResumeChooser } from "@/features/apply/ResumeChooser";
import { ChecksList, CopyReadyPanel, DestinationLine, DestinationSuggestions, ProfileSummary, ReadinessStrip, RecoveryNotice } from "@/features/apply/Overview";
import { actionLabel } from "@/features/apply/copy";
import type { ApplicationDetail, ApplyPackage, HandoffOut, PackageOut, UserJob } from "@/types/api";
import { cn } from "@/lib/utils";
import { canSmartApply, smartApplyStart, smartApplyStatus, type SmartApplyStatus } from "@/lib/smartApply";

type Step = "preparing" | "review" | "returned" | "done" | "error";

const checkIcon = {
  PASS: <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />,
  CHECK: <CircleHelp className="mt-0.5 size-4 shrink-0 text-violet" />,
  WARN: <AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />,
  ACTION: <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />,
};

/** A package response from a backend that has the Apply Workspace (older ones answer without it). */
function packageOf(data: unknown): PackageOut | null {
  const d = data as Partial<PackageOut> | undefined;
  return d?.package && Array.isArray(d.package.answers) && d.package.readiness && d.package.destination ? (d as PackageOut) : null;
}

/** Where to start when the workspace opens: the saved state decides, so reopening resumes instead of starting over. */
function initialStep(app: ApplicationDetail, pkg: ApplyPackage | null): Step {
  if (app.status === "SUBMITTED" || pkg?.action === "done") return "done";
  if (pkg?.action === "resolve_uncertain") return "returned";
  if (pkg?.action === "resume") return "review";
  return app.status === "OPENED" || app.status === "CONFIRMATION_PENDING" ? "returned" : "review";
}

/** How the submission is known: the employer's page (seen by Smart Apply) or the user's own word. */
function evidenceOf(app: ApplicationDetail, confirmedNow: boolean): "employer" | "user" | null {
  if (app.apply_state === "submitted_confirmed" || app.confirmation?.source === "employer_page") return "employer";
  if (app.apply_state === "user_reported" || app.confirmation?.source === "user_reported" || confirmedNow) return "user";
  return null;
}

/**
 * The Apply Workspace. The user always submits on the employer's (or the job site's) own form:
 * prepare → review the package (answers, resume, destination) → open or autofill the form → come back → confirm (or not).
 * Opening the form is never treated as applying, and nothing is ever submitted for the user.
 * Talks to an older backend without the package endpoint by falling back to the plain package view.
 */
export function ApplyDialog({ item, onClose }: { item: UserJob | null; onClose: () => void }) {
  const action = useApplicationAction();
  const ws = useApplyWorkspace();
  const [step, setStep] = useState<Step>("preparing");
  const [app, setApp] = useState<ApplicationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reference, setReference] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [studioResume, setStudioResume] = useState<AttachResult | null>(null);
  // How the employer form was opened in this visit (display only), and whether the user confirmed here just now.
  const [via, setVia] = useState<"smart" | "hand" | null>(null);
  const [confirmedNow, setConfirmedNow] = useState(false);
  const [unsavedAnswers, setUnsavedAnswers] = useState(0);
  const openedRef = useRef(false);
  const initialised = useRef(false);

  const pkgQuery = useApplyPackage(app?.id);
  const pkgOut = packageOf(pkgQuery.data);
  const pkg = pkgOut?.package ?? null;
  const legacy = !!app && !pkg && (pkgQuery.isError || (pkgQuery.isSuccess && !pkgOut));
  const options = useApplyOptions(legacy ? app?.id : null);

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
    setVia(null);
    setConfirmedNow(false);
    setUnsavedAnswers(0);
    openedRef.current = false;
    initialised.current = false;
    action.mutate({ kind: "prepare", userJobId: item.user_job_id }, {
      onSuccess: (a) => setApp(a),
      onError: (e) => { setError(errorMessage(e)); setStep("error"); },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.user_job_id]);

  // The package carries the freshest application (after a resume choice, a hand-off...). A copy cached from an
  // earlier visit is ignored until it has been fetched again: the extension may have changed the application since.
  const pkgFresh = pkgQuery.isFetchedAfterMount;
  const pkgApp = pkgFresh ? pkgOut?.application : undefined;
  useEffect(() => { if (pkgApp && pkgApp.id) setApp(pkgApp); }, [pkgApp]);

  // First load: start where the application stands (recovery after a closed tab, a restart, an uncertain outcome).
  useEffect(() => {
    if (!app || initialised.current) return;
    if ((pkg && pkgFresh) || legacy) {
      initialised.current = true;
      setStep(initialStep(app, pkg));
    }
  }, [app, pkg, pkgFresh, legacy]);

  // When the user comes back to this tab after opening the form, refresh (Smart Apply may already have recorded the
  // submission from the employer's thank-you page) and otherwise ask for the outcome.
  useEffect(() => {
    const onFocus = () => {
      if (!openedRef.current || step !== "review" || !item) return;
      setStep("returned");
      void pkgQuery.refetch();
      action.mutate({ kind: "prepare", userJobId: item.user_job_id }, {
        onSuccess: (a) => { setApp(a); if (a.status === "SUBMITTED") setStep("done"); },
      });
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, item?.user_job_id]);

  const onDirty = useCallback((n: number) => setUnsavedAnswers(n), []);

  if (!item) return null;
  const busy = action.isPending || ws.isPending;
  const locked = app?.status === "SUBMITTED";

  // ---- legacy (no package endpoint) ----
  const hostedUrl = options.data?.hosted_form_url ?? null;
  const openListing = (url: string | null = item.job.job_url) => {
    if (!app || !url) return;
    // Open synchronously in the click handler (pop-up blockers), then record the event.
    window.open(url, "_blank", "noopener,noreferrer");
    openedRef.current = true;
    setVia((v) => v ?? "hand");
    action.mutate({ kind: "open", id: app.id }, {
      onSuccess: (a) => setApp(a),
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  // ---- where the form is, and whether Smart Apply can fill it ----
  const destUrl = pkg ? (pkg.destination.url ?? item.job.job_url) : (hostedUrl ?? item.job.job_url);
  const smart = pkg ? canSmartApply(destUrl) && pkg.capabilities.autofill : canSmartApply(destUrl);
  const smartReady = smart && !!ext?.connected;
  const autofillAction = !!pkg && (pkg.action === "review_autofill" || pkg.action === "resume");
  // On LinkedIn, Indeed and Naukri you upload the resume yourself: choose which one before the job opens.
  const nativeNeedsResume = !!pkg && pkg.action === "open_native" && !!pkg.readiness.resume_choice_needed;

  /** Manual and native paths: the page opens in the click itself (pop-up blockers), then the hand-off is recorded. */
  const openEmployerPage = () => {
    if (!app || !destUrl) return;
    window.open(destUrl, "_blank", "noopener,noreferrer");
    openedRef.current = true;
    setVia("hand");
    ws.mutate({ kind: "handoff", id: app.id, smart: false }, { onError: (e) => toast.error(errorMessage(e)) });
  };

  const startSmartApply = async () => {
    if (!app || !destUrl) return;
    setStarting(true);
    try {
      let url = destUrl;
      if (pkg) url = ((await ws.mutateAsync({ kind: "handoff", id: app.id, smart: true })) as HandoffOut).url || destUrl;
      await smartApplyStart(url, item.user_job_id, app.id);
      openedRef.current = true;
      setVia("smart");
      toast.success("Opened the form. Smart Apply is filling it now: check every answer in its panel, then submit there.");
    } catch (e) {
      toast.error(errorMessage(e, "Smart Apply couldn't open this form."));
    } finally {
      setStarting(false);
    }
  };

  const primary = () => {
    if (!pkg) return;
    switch (pkg.action) {
      case "review_autofill":
      case "resume":
        if (smartReady) void startSmartApply();
        else openEmployerPage();
        return;
      case "continue_employer":
      case "open_native":
        openEmployerPage();
        return;
      case "resolve_uncertain":
        setStep("returned");
        return;
      case "done":
        setStep("done");
    }
  };

  const confirm = (submitted: boolean) => {
    if (!app) return;
    action.mutate({ kind: "confirm", id: app.id, submitted, reference_id: reference, confirmation_text: confirmation }, {
      onSuccess: (a) => {
        setApp(a);
        void pkgQuery.refetch();
        if (submitted) { setConfirmedNow(true); setStep("done"); toast.success("Application sent. Big move."); }
        else { toast("Left as not applied. You can apply later."); onClose(); }
      },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  const later = () => {
    if (!app) return;
    action.mutate({ kind: "pending", id: app.id }, { onSuccess: () => { toast("Saved as confirmation pending. We'll ask again later."); onClose(); } });
  };

  const uncertain = pkg?.action === "resolve_uncertain" || app?.apply_state === "submission_uncertain";
  const usedSmart = via === "smart" || (!!app?.apply_state && via !== "hand" && app.apply_mode !== "manual_handoff" && app.apply_state !== "form_opened");
  const position = step === "done" ? 3 : step === "returned" ? 2 : step === "review" && via ? 1 : 0;
  const platform = pkg?.destination.platform_name || item.job.platform;
  const evidence = app ? evidenceOf(app, confirmedNow) : null;
  const score = pkg?.job.match_score ?? item.match_score;

  return (
    <Dialog open={!!item} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className={cn("flex max-h-[92dvh] flex-col gap-0 overflow-hidden p-0", pkg ? "sm:max-w-[880px]" : "sm:max-w-[760px]")}>
        <header className="border-b px-4 pt-5 pb-4 sm:px-6">
          <div className="flex items-start gap-3 pr-8">
            <CompanyMark name={item.job.company || "?"} className="size-10 text-[13px]" />
            <div className="min-w-0 flex-1">
              <DialogTitle className="font-display text-[19px] leading-tight font-bold tracking-[-0.02em] text-heading sm:text-[21px]">
                <span className="sr-only">Apply: </span>{item.job.title}
              </DialogTitle>
              <DialogDescription className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px]">
                <span className="font-medium text-foreground">{item.job.company}</span>
                {!pkg && <><span aria-hidden>·</span>{item.job.platform}</>}
                {score != null && <><span aria-hidden>·</span><span className="readout" title="Match score">{Math.round(score)}% match</span></>}
                {app && <StatusPill status={app.status} className="ml-1" />}
                {app && pkg && <ApplyStatePill state={app.apply_state} label={app.apply_state_label} />}
              </DialogDescription>
              {pkg && <DestinationLine dest={pkg.destination} source={pkg.job.source ?? item.job.platform} />}
            </div>
          </div>
          <ApplyRoute position={position} step={step} smart={usedSmart || (smartReady && autofillAction)} />
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6">
          <p aria-live="polite" className="sr-only">{caption(step, via, platform, uncertain)}</p>

          {step === "preparing" && (
            <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> Preparing your application package…</div>
          )}
          {step === "error" && <p role="alert" className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}

          {app && pkg && step === "review" && (
            <div className="space-y-6 animate-in fade-in-0 slide-in-from-bottom-1 duration-[260ms]">
              {pkg.action === "resume" && <RecoveryNotice app={app} />}
              <ReadinessStrip readiness={pkg.readiness} />
              <DestinationSuggestions appId={app.id} dest={pkg.destination} locked={locked} />
              <ChecksList conflicts={pkg.conflicts} eligibility={pkg.eligibility} />
              <AnswersEditor appId={app.id} answers={pkg.answers} locked={locked} onDirtyChange={onDirty} />
              <ResumeChooser appId={app.id} resume={pkg.resume} locked={locked} uploadOn={pkg.action === "open_native" ? platform : undefined} />
              <ProfileSummary pkg={pkg} onSettings={onClose} />
              {app.cover_letter && pkg.action !== "open_native" && <CoverLetter text={app.cover_letter} />}
              {pkg.action === "open_native" && <CopyReadyPanel pkg={pkg} coverLetter={app.cover_letter} />}
              {smart && autofillAction && <SmartApplyCard message={pkg.capabilities.summary} smart={smart} ext={ext} onClose={onClose} />}
              <NextStep pkg={pkg} smartReady={smartReady && autofillAction} platform={platform} />
            </div>
          )}

          {app && legacy && step === "review" && (
            <LegacyReview app={app} setApp={setApp} studioResume={studioResume} setStudioResume={setStudioResume}
                          message={options.data?.message} smart={smart} smartReady={smartReady} ext={ext} platform={item.job.platform} onClose={onClose} />
          )}

          {app && step === "returned" && (
            <div className="space-y-4 animate-in fade-in-0 slide-in-from-bottom-1 duration-[260ms]">
              {uncertain ? (
                <div role="note" className="rounded-xl bg-caution-tint/60 px-4 py-3 text-[13px] ring-1 ring-caution/25" data-testid="ws-uncertain">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="font-semibold text-heading">We can't tell if this application went through</div>
                    <ApplyStatePill state={app.apply_state} label={app.apply_state_label} />
                  </div>
                  <p className="mt-1 text-foreground/80">
                    The form was submitted (or nearly), but no confirmation from the employer was seen. Check the employer's page or your
                    email for a confirmation, then tell us below. JobPilot will not submit it again.
                  </p>
                </div>
              ) : usedSmart ? <SmartApplyProgress state={app.apply_state} label={app.apply_state_label} platform={platform} /> : (
                <div className="rounded-xl bg-route-tint/60 px-4 py-3 text-[13px] ring-1 ring-route/20">
                  <div className="font-semibold text-heading">Waiting on you</div>
                  <p className="mt-0.5 text-foreground/80">Finish the form on {platform} and press submit there. Then tell us how it went. Nothing is marked as applied until you say so.</p>
                </div>
              )}
              {uncertain ? (
                destUrl && (
                  <Button variant="ghost" size="sm" className="-mt-2 text-route" onClick={() => window.open(destUrl, "_blank", "noopener,noreferrer")}>
                    <ExternalLink /> Open the page to check
                  </Button>
                )
              ) : pkg ? (
                <Button variant="ghost" size="sm" className="-mt-2 text-route" onClick={openEmployerPage} disabled={busy || !destUrl}><ExternalLink /> Reopen the employer's page</Button>
              ) : (
                <Button variant="ghost" size="sm" className="-mt-2 text-route" onClick={() => openListing(hostedUrl ?? item.job.job_url)} disabled={busy}><ExternalLink /> Reopen listing</Button>
              )}
              {pkg && !uncertain && !usedSmart && <CopyReadyPanel pkg={pkg} coverLetter={app.cover_letter} defaultOpen={pkg.action === "open_native"} />}
              <div>
                <h3 className="font-display text-[16px] font-bold text-heading">Did you submit the application on {platform}?</h3>
                <p className="text-xs text-muted-foreground">If the confirmation page showed a reference, add it. It helps when you follow up.</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Application / reference ID (optional)" htmlFor="ref"><Input id="ref" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="e.g. shown on the confirmation page" /></Field>
                <Field label="Confirmation message (optional)" htmlFor="conf"><Textarea id="conf" rows={2} value={confirmation} onChange={(e) => setConfirmation(e.target.value)} placeholder="e.g. Your application was sent to …" /></Field>
              </div>
            </div>
          )}

          {app && step === "done" && (
            <div className="flex flex-col items-center gap-2 py-6 text-center animate-in fade-in-0 zoom-in-[0.98] duration-[280ms]" data-testid="ws-done">
              <span className="jp-bump flex size-14 items-center justify-center rounded-full bg-success-tint text-success ring-8 ring-success-tint/50"><CheckCircle2 className="size-7" /></span>
              <h3 className="mt-2 font-display text-[22px] font-extrabold tracking-[-0.02em] text-heading">
                {confirmedNow ? "Application sent. Big move." : evidence === "employer" ? "Submitted and confirmed" : "Already submitted"}
              </h3>
              {evidence === "employer" && (
                <p className="inline-flex items-center gap-1.5 rounded-full bg-success-tint px-3 py-1 text-[13px] font-medium text-success"><BadgeCheck className="size-4" aria-hidden /> Confirmed by the employer's page</p>
              )}
              {evidence === "user" && (
                <p className="inline-flex items-center gap-1.5 rounded-full bg-paper-sunk px-3 py-1 text-[13px] font-medium text-heading ring-1 ring-border">Recorded from your confirmation (not independently verified)</p>
              )}
              <p className="max-w-md text-sm text-muted-foreground">
                Recorded as submitted{app.submitted_at ? <> on <span className="readout text-foreground">{formatDate(app.submitted_at, true)}</span></> : ""}.
                {app.reference_id ? <> Reference: <span className="readout text-foreground">{app.reference_id}</span>.</> : ""} You can track its progress under Applications.
              </p>
            </div>
          )}
        </div>

        <DialogFooter className="m-0 grid grid-cols-2 gap-2 rounded-none border-t bg-card px-4 py-3 sm:flex sm:flex-wrap sm:items-center sm:px-6">
          {step === "review" && pkg && (
            <>
              <Button variant="ghost" onClick={onClose} className="max-sm:order-last sm:mr-auto">Close</Button>
              {unsavedAnswers > 0 && <span className="col-span-2 text-xs text-caution sm:order-none" role="status">{unsavedAnswers} answer{unsavedAnswers === 1 ? "" : "s"} not saved yet</span>}
              <Button variant="outline" onClick={() => setStep("returned")}>I already applied</Button>
              {smartReady && autofillAction && (
                <Button variant="outline" onClick={openEmployerPage} disabled={busy || starting || !destUrl}><ExternalLink /> Apply by hand</Button>
              )}
              <Button className="max-sm:order-first max-sm:col-span-2" onClick={primary}
                      disabled={busy || starting || (!destUrl && pkg.action !== "resolve_uncertain" && pkg.action !== "done") || nativeNeedsResume}
                      title={nativeNeedsResume ? "Choose the resume you'll upload first" : undefined} data-testid="workspace-primary">
                {starting ? <Loader2 className="animate-spin" /> : smartReady && autofillAction ? <Wand2 /> : <ExternalLink />}
                {actionLabel(pkg.action, pkg.destination, smartReady)}
              </Button>
            </>
          )}
          {step === "review" && legacy && (
            <>
              <Button variant="ghost" onClick={onClose} className="max-sm:order-last sm:mr-auto">Close</Button>
              <Button variant="outline" onClick={() => setStep("returned")}>I already applied</Button>
              {smartReady ? (
                <>
                  <Button variant="outline" onClick={() => openListing(destUrl)} disabled={busy || starting}><ExternalLink /> Apply by hand</Button>
                  <Button className="max-sm:order-first max-sm:col-span-2" onClick={startSmartApply} disabled={busy || starting} data-testid="smart-apply-start">
                    {starting ? <Loader2 className="animate-spin" /> : <Wand2 />} Apply with Smart Apply
                  </Button>
                </>
              ) : hostedUrl ? (
                <>
                  <Button variant="outline" onClick={() => openListing()} disabled={busy || !item.job.job_url}><ExternalLink /> Employer's listing</Button>
                  <Button className="max-sm:order-first max-sm:col-span-2" onClick={() => openListing(hostedUrl)} disabled={busy}><ExternalLink /> Open Greenhouse application form</Button>
                </>
              ) : (
                <Button className="max-sm:order-first max-sm:col-span-2" onClick={() => openListing()} disabled={busy || !item.job.job_url}><ExternalLink /> Open original listing</Button>
              )}
            </>
          )}
          {step === "returned" && (
            <>
              {!uncertain && (
                <Button variant="ghost" className="max-sm:order-last max-sm:col-span-2 sm:mr-auto" onClick={() => { openedRef.current = false; setVia(null); setStep("review"); }} disabled={busy}><ArrowLeft /> Back to package</Button>
              )}
              {uncertain && <Button variant="ghost" className="max-sm:order-last max-sm:col-span-2 sm:mr-auto" onClick={onClose}>Close</Button>}
              <Button variant="outline" onClick={later} disabled={busy}>Not sure yet</Button>
              <Button variant="outline" onClick={() => confirm(false)} disabled={busy}><XCircle /> {uncertain ? "Not submitted" : "I didn't apply"}</Button>
              <Button className="max-sm:order-first max-sm:col-span-2" onClick={() => confirm(true)} disabled={busy}>{action.isPending ? <Loader2 className="animate-spin" /> : <CheckCircle2 />} Yes, I submitted it</Button>
            </>
          )}
          {(step === "done" || step === "error") && <Button className="max-sm:col-span-2" onClick={onClose}>Done</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function caption(step: Step, via: "smart" | "hand" | null, platform: string, uncertain: boolean): string {
  switch (step) {
    case "preparing": return "Preparing your application package.";
    case "review": return via ? "The employer's form is open in a new tab." : "Package ready. Check it, then open the employer's form.";
    case "returned":
      if (uncertain) return "We can't tell if the application went through. Tell us what happened.";
      return via === "smart" ? "Waiting for your review in the Smart Apply panel. You press submit yourself." : `Waiting for you to finish on ${platform} and confirm.`;
    case "done": return "Recorded as submitted.";
    default: return "Something went wrong preparing the package.";
  }
}

function CoverLetter({ text }: { text: string }) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between"><h3 className="eyebrow">Cover letter (from your resume facts)</h3>
        <Button size="sm" variant="ghost" onClick={() => { void navigator.clipboard.writeText(text); toast.success("Copied"); }}><Copy /> Copy</Button></div>
      <div className="max-h-40 overflow-y-auto rounded-xl bg-paper-sunk p-3 text-[13px] whitespace-pre-wrap">{text}</div>
    </section>
  );
}

/** What happens when the primary button is pressed, in one line. */
function NextStep({ pkg, smartReady, platform }: { pkg: ApplyPackage; smartReady: boolean; platform: string }) {
  const text = smartReady
    ? <>Next: <strong>{actionLabel(pkg.action, pkg.destination, true)}</strong> opens the form and fills it. Check every answer in the Smart Apply panel, submit on {platform} yourself, then come back here.</>
    : pkg.action === "open_native"
      ? <>Next: open the job on <strong>{platform}</strong> in this browser (if you're signed in there already, you stay signed in; JobPilot never sees your {platform} password),
          upload {pkg.readiness.resume_choice_needed ? "the resume you choose above" : "the resume you chose"}, paste your answers from the list above, submit there, then come back here and confirm.</>
      : <>Next: open the employer's form, complete the application <strong>on {platform}</strong>, then come back here and confirm.</>;
  return (
    <p className="flex gap-2 rounded-xl bg-paper-sunk px-3 py-2.5 text-[13px]">
      <MousePointerClick className="mt-0.5 size-4 shrink-0 text-route" aria-hidden />
      <span>{text} Opening the form does not mark it as applied, and JobPilot never submits for you.</span>
    </p>
  );
}

/** The plain package view, for a backend without the Apply Workspace. */
function LegacyReview({ app, setApp, studioResume, setStudioResume, message, smart, smartReady, ext, platform, onClose }: {
  app: ApplicationDetail; setApp: (a: ApplicationDetail) => void; studioResume: AttachResult | null; setStudioResume: (r: AttachResult) => void;
  message: string | undefined; smart: boolean; smartReady: boolean; ext: SmartApplyStatus | null | undefined; platform: string; onClose: () => void;
}) {
  return (
    <div className="space-y-5 animate-in fade-in-0 slide-in-from-bottom-1 duration-[260ms]">
      {app.checklist.length > 0 && (
        <section>
          <h3 className="eyebrow mb-2">Checklist</h3>
          <ul className="grid gap-x-5 gap-y-1.5 sm:grid-cols-2">
            {app.checklist.map((c, i) => (
              <li key={i} className="flex gap-2 text-[13px]">{checkIcon[c.status]}<span><span className="font-medium">{c.check}</span>{c.detail && <span className="text-muted-foreground">: {c.detail}</span>}</span></li>
            ))}
          </ul>
        </section>
      )}
      {app.screening_answers.length > 0 && (
        <section>
          <h3 className="eyebrow mb-2">Screening questions and prepared answers</h3>
          <div className="divide-y divide-border/70 rounded-xl ring-1 ring-border">
            {app.screening_answers.map((s) => (
              <div key={s.question} className="flex flex-col gap-1 px-3 py-2.5 text-[13px] sm:flex-row sm:justify-between sm:gap-4">
                <span className="font-medium">{s.question}</span>
                {s.status === "NEEDS_CANDIDATE_INPUT"
                  ? <span className="self-start rounded-full bg-caution-tint px-2 py-0.5 text-xs font-medium text-caution sm:self-auto">Needs your input</span>
                  : <span className="text-muted-foreground sm:max-w-[55%] sm:text-right">{s.answer}</span>}
              </div>
            ))}
          </div>
          {app.needs_candidate_input.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Answers marked "Needs your input" are never guessed. Add verified answers in Settings → Verified answers.</p>}
        </section>
      )}
      <section className="space-y-2 rounded-xl p-3 text-sm ring-1 ring-border">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-2"><FileText className="size-4 shrink-0 text-muted-foreground" /> Resume for this application: <span className="truncate font-medium">{app.resume_used ?? "none uploaded"}</span></span>
          {app.resume_used && (
            <Button size="sm" variant="ghost" onClick={() => {
              const path = studioResume?.resume_export_id ? `/studio/exports/${studioResume.resume_export_id}/download` : "/profile/resume";
              downloadFile(path, studioResume ? "resume.pdf" : app.resume_used ?? "resume.pdf").catch((e) => toast.error(errorMessage(e)));
            }}><Download /> Download</Button>
          )}
        </div>
        <ResumeVersionPicker applicationId={app.id} initialVersionId={app.resume_version_id ?? null}
                             onAttached={(r) => { setStudioResume(r); setApp({ ...app, resume_used: r.resume_used ?? app.resume_used }); }} />
      </section>
      {app.cover_letter && <CoverLetter text={app.cover_letter} />}
      {message != null && <SmartApplyCard message={message} smart={smart} ext={ext} onClose={onClose} />}
      <p className="flex gap-2 rounded-xl bg-paper-sunk px-3 py-2.5 text-[13px]">
        <MousePointerClick className="mt-0.5 size-4 shrink-0 text-route" aria-hidden />
        <span>
          {smartReady
            ? <>Next: click <strong>Apply with Smart Apply</strong>, check the filled form, submit it on {platform}, then come back here. If Smart Apply saw the employer's thank-you page, it's already recorded for you.</>
            : <>Next: open the original listing, complete the application <strong>on {platform}</strong>, then come back here and confirm.</>}
          {" "}Opening the form does not mark it as applied.
        </span>
      </p>
    </div>
  );
}

/** The apply journey as a route: package → employer form → your review and submit → confirmed. */
function ApplyRoute({ position, step, smart }: { position: number; step: Step; smart: boolean }) {
  const labels = ["Package ready", "Employer form", smart ? "Smart Apply fills, you review" : "You fill & submit", "Confirmed"];
  const done = step === "done";
  const failed = step === "error";
  return (
    <ol aria-label="Apply progress" className="relative mt-4 grid grid-cols-4" data-testid="apply-route">
      <span aria-hidden className="absolute top-[9px] right-[12.5%] left-[12.5%] border-t-2 border-dashed border-border" />
      <span aria-hidden className={cn("absolute top-[9px] left-[12.5%] h-0.5 w-[75%] origin-left rounded-full transition-transform duration-300 ease-[cubic-bezier(.65,0,.35,1)]", done ? "bg-success" : "bg-route")}
            style={{ transform: `scaleX(${position / 3})` }} />
      {labels.map((l, i) => {
        const past = i < position || (done && i === 3);
        const current = i === position && !done;
        return (
          <li key={l} aria-current={current ? "step" : undefined} className="relative flex flex-col items-center gap-1.5 px-1 text-center">
            <span className={cn("relative z-10 flex size-5 items-center justify-center rounded-full transition-[background-color,box-shadow,transform] duration-[260ms] ease-[cubic-bezier(.2,0,0,1)]",
              past ? (done ? "bg-success text-white" : "bg-route text-primary-foreground")
                : current ? (failed ? "bg-card ring-2 ring-destructive" : "scale-110 bg-card ring-2 ring-route shadow-[0_0_0_5px_color-mix(in_oklab,var(--route)_18%,transparent)]")
                  : "bg-card ring-1 ring-border")}>
              {past ? <Check className="size-3" strokeWidth={3} /> : current && <span className={cn("size-2 rounded-full", failed ? "bg-destructive" : "bg-route", step === "preparing" && "animate-pulse")} />}
            </span>
            <span className={cn("text-[11.5px] leading-tight transition-colors duration-200 sm:text-[12px]",
              current ? "font-semibold text-heading" : past ? "font-medium text-foreground" : "text-muted-foreground")}>{l}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** What happens in the Smart Apply tab, with where it stands now. Smart Apply fills; only the user submits. */
function SmartApplyProgress({ state, label, platform }: { state: string | null | undefined; label: string | null | undefined; platform: string }) {
  const at = !state || state === "draft" || state === "ready_to_fill" || state === "form_opened" || state === "filling" ? 0
    : state === "submission_pending" || state === "submission_authorized" || state === "submission_uncertain" ? 2 : 1;
  const warn = state === "submission_uncertain" || state === "needs_information" || state === "failed" || state === "interrupted";
  const items = [
    { icon: Wand2, text: "Smart Apply fills the form from your profile, resume attached" },
    { icon: Eye, text: "You check every answer in the Smart Apply panel" },
    { icon: MousePointerClick, text: `You submit on ${platform} when you're happy. Nothing is sent without your click` },
  ];
  return (
    <div className="rounded-xl bg-route-tint/60 px-4 py-3 ring-1 ring-route/20">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[13px] font-semibold text-heading">{at === 0 ? "Smart Apply is filling the form" : at === 1 ? "Waiting for your review in the Smart Apply panel" : "Waiting for the employer's confirmation"}</div>
        <ApplyStatePill state={state} label={label} />
      </div>
      <ol className="mt-2 space-y-1.5">
        {items.map(({ icon: Icon, text }, i) => (
          <li key={i} className={cn("flex items-center gap-2 text-[13px] transition-colors duration-200", i === at ? "font-medium text-heading" : i < at ? "text-foreground/70" : "text-muted-foreground")}>
            <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-full transition-[background-color] duration-200",
              i < at ? "bg-route text-primary-foreground" : i === at ? (warn ? "bg-caution-tint text-caution ring-1 ring-caution/30" : "bg-card text-route ring-2 ring-route") : "bg-card text-muted-foreground ring-1 ring-border")}>
              {i < at ? <Check className="size-3.5" strokeWidth={3} /> : <Icon className="size-3.5" />}
            </span>
            {text}
          </li>
        ))}
      </ol>
      <p className="mt-2 text-xs text-muted-foreground">If Smart Apply sees the employer's thank-you page, it records the submission for you. Otherwise, tell us below.</p>
    </div>
  );
}

const EXT_ZIP = `${import.meta.env.BASE_URL}downloads/jobpilot-smart-apply-2.4.0.zip`;

/** Where Smart Apply stands in this browser, and the one next step to make one-click applying work. */
function SmartApplyCard({ message, smart, ext, onClose }: { message: string; smart: boolean; ext: SmartApplyStatus | null | undefined; onClose: () => void }) {
  const ready = smart && !!ext?.connected;
  const tone = ready ? "bg-route-tint/70 ring-route/25" : smart ? "bg-lavender/60 ring-violet/20" : "bg-paper-sunk ring-border";
  return (
    <section className={cn("flex gap-2.5 rounded-xl p-3 text-[13px] ring-1", tone)} data-testid="smart-apply-card">
      {ready ? <Wand2 className="mt-0.5 size-4 shrink-0 text-route" /> : <Puzzle className={cn("mt-0.5 size-4 shrink-0", smart ? "text-violet" : "text-muted-foreground")} />}
      <div className="space-y-1">
        <p className={smart ? "text-xs text-muted-foreground" : undefined}>{message}</p>
        {smart && ready && (
          <p><strong>Smart Apply is ready.</strong> The form opens in a new tab and fills itself
            from your profile, with your resume attached. Check every answer in the panel, then submit. Nothing is sent without your click.</p>
        )}
        {smart && ext === undefined && <p className="flex items-center gap-2"><Loader2 className="size-3.5 animate-spin" /> Checking for Smart Apply in this browser…</p>}
        {smart && ext && !ext.connected && (
          <p><strong>Smart Apply is installed but not connected.</strong> Connect it once and this form will fill itself.{" "}
            <a href="#/settings?tab=extension" className="font-medium text-route underline underline-offset-2" onClick={onClose}>Connect it now</a>
            {" "}Or continue on the employer's site and fill it by hand.</p>
        )}
        {smart && ext === null && (
          <>
            <p><strong>Apply in one click with Smart Apply.</strong> This form can be filled for you. Install the free browser extension once (two minutes), or continue on the employer's site and fill it by hand.</p>
            <div className="flex flex-wrap items-center gap-2 pt-1" data-testid="apply-extension-cta">
              <Button size="xs" variant="outline" render={<a href={EXT_ZIP} download />}><Download /> Get the Smart Apply extension</Button>
              <a href="#/settings?tab=extension" className="text-xs font-medium text-route underline underline-offset-2" onClick={onClose}>How to set it up</a>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
