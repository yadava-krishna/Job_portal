import { AlertTriangle, BadgeCheck, CheckCircle2, CircleDashed, Download, ExternalLink, History, Loader2, Lock, ShieldCheck, Undo2, UserCheck, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { downloadFile, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApplyWorkspace } from "@/services/queries";
import type { ApplicationDetail, ApplyPackage, PackageConflict, PackageDestination, PackageEligibility, PackageProfileRow, PackageReadiness } from "@/types/api";
import { hostOf } from "./copy";
import { Chip, CopyButton, WsSection } from "./parts";

/** "Apply on Greenhouse · job-boards.greenhouse.io" with how JobPilot knows it, in the dialog header. */
export function DestinationLine({ dest, source }: { dest: PackageDestination; source: string | null }) {
  const host = hostOf(dest.url);
  return (
    <div className="mt-1.5 space-y-1 text-[12.5px]" data-testid="ws-destination">
      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-muted-foreground">
        {source && <span>Found on <span className="font-medium text-foreground">{source}</span></span>}
        {source && <span aria-hidden>→</span>}
        <span>Apply on <span className="font-medium text-foreground">{dest.platform_name || "the employer's site"}</span>
          {host && <span className="readout ml-1 text-muted-foreground">{host}</span>}</span>
        {dest.verified && <Chip tone="ok"><BadgeCheck aria-hidden /> Verified employer posting</Chip>}
        {dest.confirmed_by_user && <Chip tone="check"><UserCheck aria-hidden /> You confirmed this</Chip>}
      </div>
      {dest.evidence.length > 0 && (
        <details className="group text-xs text-muted-foreground">
          <summary className="w-fit cursor-pointer rounded-md text-route underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none">
            How we know where to apply
          </summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">{dest.evidence.map((e) => <li key={e}>{e}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

/** Profile, resume, known questions and the employer's form: what's ready, said honestly. */
export function ReadinessStrip({ readiness }: { readiness: PackageReadiness }) {
  const chips: { ok: boolean; label: string; unknown?: boolean }[] = [
    { ok: readiness.profile, label: readiness.profile ? "Profile ready" : "Profile incomplete" },
    { ok: readiness.resume, label: readiness.resume ? "Resume chosen" : readiness.resume_choice_needed ? "Choose your resume" : "No resume yet" },
    { ok: readiness.known_questions, label: readiness.known_questions ? "Known questions answered" : "Known questions need answers" },
    { ok: readiness.form_inspected, unknown: !readiness.form_inspected,
      label: readiness.form_inspected ? "Employer form inspected" : "Employer form not inspected yet" },
  ];
  const tone = readiness.level === "blocked" ? "ring-destructive/25 bg-destructive/5" : readiness.level === "needs_input" ? "ring-caution/25 bg-caution-tint/40"
    : "ring-route/20 bg-route-tint/50";
  return (
    <section aria-label="Readiness" className={cn("space-y-2 rounded-xl px-3.5 py-3 ring-1", tone)} data-testid="ws-readiness">
      <ul className="flex flex-wrap gap-1.5">
        {chips.map((c) => (
          <li key={c.label}>
            <Chip tone={c.ok ? "ok" : c.unknown ? "neutral" : readiness.level === "blocked" ? "fail" : "warn"}>
              {c.ok ? <CheckCircle2 aria-hidden /> : c.unknown ? <CircleDashed aria-hidden /> : <AlertTriangle aria-hidden />}{c.label}
            </Chip>
          </li>
        ))}
      </ul>
      <p className="text-[13px] text-heading">{readiness.summary}</p>
      {(readiness.needs_input > 0 || readiness.to_check > 0 || (readiness.other_unanswered ?? 0) > 0) && (
        <p className="readout text-xs text-muted-foreground">
          {readiness.needs_input} need{readiness.needs_input === 1 ? "s" : ""} your answer · {readiness.to_check} to check
          {(readiness.other_unanswered ?? 0) > 0 && <> · {readiness.other_unanswered} other unanswered</>}
        </p>
      )}
    </section>
  );
}

/** Picking up an application that was left half-way. Never offers to submit again. */
export function RecoveryNotice({ app }: { app: ApplicationDetail }) {
  return (
    <div role="note" className="flex gap-2.5 rounded-xl bg-lavender/60 px-3.5 py-3 text-[13px] ring-1 ring-violet/20" data-testid="ws-recovery">
      <History className="mt-0.5 size-4 shrink-0 text-violet" aria-hidden />
      <div>
        <p className="font-semibold text-heading">You started this application{app.apply_state_at ? <> on <span className="readout">{formatDate(app.apply_state_at, true)}</span></> : ""}.</p>
        <p className="text-foreground/80">
          {app.apply_state_label ? <>Last step: {app.apply_state_label}. </> : null}
          Everything you prepared is saved below. Resuming opens the form again so you can fill and check it; nothing is submitted for you.
        </p>
      </div>
    </div>
  );
}

export function ChecksList({ conflicts, eligibility }: { conflicts: PackageConflict[]; eligibility: PackageEligibility[] }) {
  const elig = eligibility.filter((e) => e.status !== "ok");
  const ok = eligibility.filter((e) => e.status === "ok");
  if (!conflicts.length && !eligibility.length) return null;
  return (
    <WsSection title="Worth a look before you apply" testId="ws-checks">
      <ul className="space-y-1.5">
        {elig.map((e) => (
          <li key={e.label} className={cn("flex gap-2 rounded-lg px-3 py-2 text-[13px] ring-1",
            e.status === "fail" ? "bg-destructive/5 ring-destructive/20" : "bg-caution-tint/40 ring-caution/20")}>
            {e.status === "fail" ? <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-label="Problem" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" aria-label="Warning" />}
            <span><span className="font-medium">{e.label}</span>: {e.detail}</span>
          </li>
        ))}
        {conflicts.map((c) => (
          <li key={c.key} className="flex gap-2 rounded-lg bg-caution-tint/40 px-3 py-2 text-[13px] ring-1 ring-caution/20">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" aria-label="Doesn't add up" />
            <span><span className="font-medium">{c.label}</span>: {c.detail}</span>
          </li>
        ))}
        {ok.map((e) => (
          <li key={e.label} className="flex gap-2 px-3 py-1 text-[13px] text-muted-foreground">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
            <span><span className="font-medium text-foreground">{e.label}</span>: {e.detail}</span>
          </li>
        ))}
      </ul>
    </WsSection>
  );
}

/** The same job on the employer's own application form, offered only as a suggestion the user confirms. */
export function DestinationSuggestions({ appId, dest, locked }: { appId: number; dest: PackageDestination; locked: boolean }) {
  const ws = useApplyWorkspace();
  if (!dest.suggestions.length && !dest.confirmed_by_user) return null;
  const busy = ws.isPending;
  return (
    <WsSection title="Apply on the employer's own site?" testId="ws-suggestions">
      <p className="text-[13px] text-muted-foreground">
        This listing is on a site JobPilot can't fill for you. The employer may have posted the same job on their own application form.
        JobPilot never swaps in a different job without your say-so: only confirm if it's the same role.
      </p>
      {dest.confirmed_by_user && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-route-tint/50 px-3 py-2.5 text-[13px] ring-1 ring-route/20">
          <span className="flex items-center gap-1.5"><UserCheck className="size-4 text-route" aria-hidden /> You confirmed the employer's posting is the same job.</span>
          <Button size="sm" variant="outline" disabled={busy || locked}
                  onClick={() => ws.mutate({ kind: "clear-destination", id: appId }, {
                    onSuccess: () => toast("Back to the original listing."), onError: (e) => toast.error(errorMessage(e)),
                  })}>
            <Undo2 /> Use the original listing instead
          </Button>
        </div>
      )}
      <ul className="space-y-2">
        {dest.suggestions.map((s) => (
          <li key={s.url} className="rounded-xl p-3 text-[13px] ring-1 ring-border">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="font-semibold text-heading">{s.title}</div>
                <div className="text-muted-foreground">{s.company}{s.location ? ` · ${s.location}` : ""} · on {s.platform_name}{s.posted_at ? ` · posted ${formatDate(s.posted_at)}` : ""}</div>
              </div>
              <Chip tone={s.strength === "strong" ? "ok" : "check"}>{s.strength === "strong" ? "Strong match" : "Possible match"}</Chip>
            </div>
            <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
              {s.evidence.map((e) => <li key={e} className="flex items-center gap-1"><CheckCircle2 className="size-3 text-success" aria-hidden />{e}</li>)}
            </ul>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" disabled={busy || locked}
                      onClick={() => ws.mutate({ kind: "destination", id: appId, url: s.url }, {
                        onSuccess: () => toast.success("Got it. You'll apply on the employer's site."), onError: (e) => toast.error(errorMessage(e)),
                      })}>
                {busy && ws.variables?.kind === "destination" ? <Loader2 className="animate-spin" /> : <ShieldCheck />} Same job: apply on the employer's site
              </Button>
              <Button size="sm" variant="ghost" render={<a href={s.url} target="_blank" rel="noopener noreferrer" />}><ExternalLink /> Look at it first</Button>
            </div>
          </li>
        ))}
      </ul>
    </WsSection>
  );
}

function ProfileGroup({ title, rows, onSettings }: { title: string; rows: PackageProfileRow[]; onSettings: () => void }) {
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold text-heading">{title}</h4>
      <dl className="space-y-1">
        {rows.map((r) => (
          <div key={r.key} className="flex items-baseline justify-between gap-3 text-[13px]">
            <dt className="shrink-0 text-muted-foreground">{r.label}</dt>
            <dd className="min-w-0 truncate text-right font-medium" title={r.value != null ? String(r.value) : undefined}>
              {r.value != null && r.value !== "" ? String(r.value)
                : <a href="#/settings?tab=profile" onClick={onSettings} className="font-normal text-route underline underline-offset-2">Not set: edit in Settings</a>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** Read-only: what forms get from the profile. Changes are made in Settings. */
export function ProfileSummary({ pkg, onSettings }: { pkg: ApplyPackage; onSettings: () => void }) {
  const elsewhere = pkg.missing.filter((m) => m.where !== "this_application");
  const here = pkg.missing.filter((m) => m.where === "this_application");
  return (
    <WsSection title="Your details on the form" testId="ws-profile"
               aside={<a href="#/settings?tab=profile" onClick={onSettings} className="font-medium text-route underline underline-offset-2">Edit in Settings</a>}>
      {(elsewhere.length > 0 || here.length > 0) && (
        <div className="rounded-lg bg-caution-tint/40 px-3 py-2 text-[13px] ring-1 ring-caution/20">
          <span className="font-medium">Still missing:</span>{" "}
          {[...elsewhere.map((m) => m.label), ...here.map((m) => `${m.label} (answer below)`)].join(", ")}
        </div>
      )}
      <div className="grid gap-4 rounded-xl p-3 ring-1 ring-border sm:grid-cols-3">
        <ProfileGroup title="Personal" rows={pkg.profile.personal} onSettings={onSettings} />
        <ProfileGroup title="Professional" rows={pkg.profile.professional} onSettings={onSettings} />
        <ProfileGroup title="Links" rows={pkg.profile.links} onSettings={onSettings} />
      </div>
    </WsSection>
  );
}

/**
 * Everything prepared, one copy button each: for sites JobPilot doesn't fill (LinkedIn, Indeed, Naukri, employer sites).
 */
export function CopyReadyPanel({ pkg, coverLetter, defaultOpen = true }: { pkg: ApplyPackage; coverLetter?: string | null; defaultOpen?: boolean }) {
  const answers = pkg.answers.filter((a) => a.answer && a.sensitivity !== "never");
  const profile = [...pkg.profile.personal, ...pkg.profile.professional, ...pkg.profile.links].filter((r) => r.value != null && r.value !== "");
  const resume = pkg.resume;
  const download = () => {
    if (!resume.id) return;
    downloadFile(`/profile/resumes/${resume.id}/file`, resume.name ?? "resume.pdf").catch((e) => toast.error(errorMessage(e)));
  };
  return (
    <details open={defaultOpen} className="group rounded-xl bg-paper-sunk/70 ring-1 ring-border" data-testid="ws-copy-panel">
      <summary className="cursor-pointer list-none rounded-xl px-3.5 py-2.5 text-[13px] font-semibold text-heading focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none">
        Copy-ready answers for {pkg.destination.platform_name || "the form"}
        <span className="ml-2 font-normal text-muted-foreground">Paste them into the form. JobPilot doesn't fill this site.</span>
      </summary>
      <div className="space-y-3 px-3.5 pb-3.5">
        {resume.kind === "upload" && (
          <div className="flex items-center justify-between gap-2 text-[13px]">
            <span className="min-w-0 truncate">Resume: <span className="font-medium">{resume.name}</span></span>
            <Button size="sm" variant="outline" onClick={download}><Download /> Download</Button>
          </div>
        )}
        {resume.kind === "studio" && <p className="text-[13px] text-muted-foreground">Resume: <span className="font-medium text-foreground">{resume.name}</span>. Download it from the Resume section above.</p>}
        {answers.length > 0 && (
          <ul className="divide-y divide-border/70 rounded-lg bg-card ring-1 ring-border">
            {answers.map((a) => (
              <li key={a.question} className="flex items-center gap-2 px-3 py-1.5 text-[13px]">
                <span className="min-w-0 flex-1">
                  <span className="block text-xs text-muted-foreground">{a.question}</span>
                  <span className="font-medium break-words">{a.answer}</span>
                </span>
                {a.sensitivity === "private" && <Lock className="size-3.5 shrink-0 text-muted-foreground" aria-label="Private answer" />}
                <CopyButton text={a.answer ?? ""} label={a.question} />
              </li>
            ))}
          </ul>
        )}
        {profile.length > 0 && (
          <ul className="grid gap-x-4 sm:grid-cols-2">
            {profile.map((r) => (
              <li key={r.key} className="flex items-center gap-2 py-0.5 text-[13px]">
                <span className="w-28 shrink-0 text-xs text-muted-foreground">{r.label}</span>
                <span className="min-w-0 flex-1 truncate font-medium">{String(r.value)}</span>
                <CopyButton text={String(r.value)} label={r.label} />
              </li>
            ))}
          </ul>
        )}
        {coverLetter && (
          <div className="flex items-center justify-between gap-2 text-[13px]">
            <span>Cover letter (from your resume facts)</span>
            <CopyButton text={coverLetter} label="cover letter" />
          </div>
        )}
      </div>
    </details>
  );
}
