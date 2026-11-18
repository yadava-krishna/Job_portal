import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Check, Clock, FileText, Save, Search, Send, ShieldCheck } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { ClipperCard, PlatformsForm, PreferencesForm, ProfileForm, ResumeUpload } from "@/components/app/forms";
import { Brand } from "@/layouts/AppLayout";
import { useAuth } from "@/contexts/AuthContext";
import { qk, useOnboarding, usePlatforms, usePreferences, useProfile } from "@/services/queries";
import { cn } from "@/lib/utils";
import { LoadingState } from "@/components/app/common";
import type { PlatformInfo, Preferences, ProfileResponse } from "@/types/api";

const steps = ["Resume", "Review profile", "Job preferences", "Job portals", "Confirm"];

export function OnboardingPage() {
  const status = useOnboarding();
  const profile = useProfile();
  const prefs = usePreferences();
  const platforms = usePlatforms();
  const { refreshUser, user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [manual, setManual] = useState(false);
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const firstStep = useRef(true);
  // Keyboard and screen-reader users land on the new step instead of staying on the button they pressed.
  useEffect(() => {
    if (firstStep.current) { firstStep.current = false; return; }
    stepHeading.current?.focus();
  }, [step]);

  useEffect(() => {
    const s = status.data;
    if (!s) return;
    setStep((cur) => (cur > 0 ? cur : !s.resume_uploaded ? 0 : !s.profile_confirmed ? 1 : !s.preferences_saved ? 2 : !s.platforms_selected ? 3 : 4));
  }, [status.data]);

  const titles = Array.from(new Set([
    ...(profile.data?.confirmed?.headline ?? profile.data?.parsed?.headline ?? "").split(/\s+I\s+|\||,/).map((s) => s.trim()).filter((s) => s.length > 2 && s.length < 40),
    ...(profile.data?.confirmed?.experience ?? profile.data?.parsed?.experience ?? []).map((e) => e.title).filter(Boolean),
  ]));

  const finish = async () => {
    await qc.invalidateQueries({ queryKey: qk.onboarding });
    await refreshUser();
    navigate("/discover", { replace: true });
  };

  const meta = [
    { title: "Start with your resume", desc: "We read your PDF to pre-fill your profile. Nothing is invented; you review everything next." },
    manual
      ? { title: "Create your profile", desc: "Add what is true today: education, projects and skills count; you don't need work experience. Only what you enter here is used." }
      : { title: "Does this look right?", desc: "Correct anything the parser got wrong. Only confirmed details are used for matching and screening answers." },
    { title: "What are you looking for?", desc: "Choose one or more domains and roles. You can change these any time." },
    { title: "Where should we look?", desc: "Enable each platform and pick how jobs reach JobPilot. Nothing is scraped and nothing is submitted for you." },
    { title: "You're all set", desc: "Here's what JobPilot will use. Looking good." },
  ][step];
  const firstName = user?.full_name?.trim().split(/\s+/)[0];

  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
          <Brand />
          <div className="flex items-center gap-3">
            <span className="text-xs text-muted-foreground"><span className="readout font-medium text-foreground">{step + 1}</span>/<span className="readout">{steps.length}</span><span className="hidden sm:inline"> · saved after each step</span></span>
            {/* Also applies the stored light/dark preference, since this page sits outside the app layout. */}
            <ThemeToggle />
          </div>
        </div>
        <div aria-hidden className="absolute inset-x-0 -bottom-px h-0.5 bg-transparent">
          <div className="h-full bg-route transition-[width] duration-500 ease-[cubic-bezier(.2,0,0,1)]" style={{ width: `${((step + 1) / steps.length) * 100}%` }} />
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-4 pt-8 pb-16 sm:px-6">
        <div className="max-w-2xl">
          <div className="eyebrow mb-2">{firstName ? `Welcome, ${firstName}` : "Welcome to JobPilot"}</div>
          <h1 className={cn("font-display leading-[1.15] font-extrabold tracking-[-0.03em] text-heading", step === 0 ? "text-[28px] sm:text-[32px]" : "text-[22px] sm:text-[24px]")}>Let's set up your <em>job search</em></h1>
          {step === 0 && (
            <p className="mt-2 text-[14.5px] leading-relaxed text-muted-foreground">
              Five short steps, a few minutes. Each step is saved when you continue, so you can stop and pick up where you left off.
            </p>
          )}
        </div>

        <nav aria-label="Setup progress" className={cn("relative mb-8", step === 0 ? "mt-7" : "mt-5")}>
          <div aria-hidden className="absolute top-4 right-[10%] left-[10%] h-0.5 -translate-y-1/2 rounded-full bg-border">
            <div className="h-full rounded-full bg-route transition-[width] duration-500 ease-[cubic-bezier(.2,0,0,1)]" style={{ width: `${(step / (steps.length - 1)) * 100}%` }} />
          </div>
          <ol className="relative grid grid-cols-5">
            {steps.map((s, i) => (
              <li key={s} className="flex flex-col items-center gap-2 text-center">
                <button type="button" onClick={() => i <= step && setStep(i)} disabled={i > step}
                        aria-current={i === step ? "step" : undefined}
                        aria-label={`Step ${i + 1}: ${s}${i < step ? " (done)" : i === step ? " (current)" : ""}`}
                        className={cn("readout flex size-8 items-center justify-center rounded-full text-[13px] font-semibold transition-[background-color,box-shadow,color] duration-200 ease-[cubic-bezier(.2,0,0,1)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                                      i < step ? "bg-primary text-primary-foreground hover:bg-primary/90" : i === step ? "bg-card text-route ring-2 ring-route shadow-[0_0_0_5px_var(--route-tint)]" : "bg-card text-muted-foreground ring-1 ring-border")}>
                  {i < step ? <Check className="size-4" aria-hidden /> : i + 1}
                </button>
                <span className={cn("text-xs leading-tight", i === step ? "font-semibold text-heading" : "hidden text-muted-foreground sm:block")}>{s}</span>
              </li>
            ))}
          </ol>
        </nav>

        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <section key={step} className="min-w-0 rounded-2xl bg-card ring-1 ring-border animate-in fade-in-0 slide-in-from-bottom-1 duration-300">
            <div className="border-b px-5 py-4 sm:px-6">
              <div aria-hidden className="eyebrow mb-1">Step {step + 1} of {steps.length}</div>
              <h2 ref={stepHeading} tabIndex={-1} className="font-display text-[21px] font-extrabold tracking-[-0.02em] text-heading outline-none">
                <span className="sr-only">Step {step + 1} of {steps.length}: </span>{meta.title}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">{meta.desc}</p>
            </div>
            <div className="px-5 py-5 sm:px-6">
              {step === 0 && (
                <div className="space-y-4">
                  <ResumeUpload profile={profile.data} onUploaded={() => setStep(1)} />
                  {profile.data?.has_resume && <div className="flex justify-end"><Button onClick={() => setStep(1)}>Continue <ArrowRight /></Button></div>}
                  {!profile.data?.has_resume && (
                    <div className="rounded-xl bg-paper-sunk p-4 text-sm">
                      <p className="font-medium text-heading">No resume yet? No stress.</p>
                      <p className="mt-1 text-muted-foreground">Students and early-career candidates can build a profile by hand: your education, projects and skills. You can make a resume from it later in Resume Studio.</p>
                      <Button variant="outline" size="sm" className="mt-3" onClick={() => { setManual(true); setStep(1); }}>Create my profile without a resume</Button>
                    </div>
                  )}
                </div>
              )}
              {step === 1 && (profile.data ? <ProfileForm profile={profile.data} manual={manual || !profile.data.has_resume} submitLabel="Confirm profile & continue" onSaved={() => setStep(2)} /> : <LoadingState />)}
              {step === 2 && <PreferencesForm initial={prefs.data?.is_configured ? prefs.data : undefined} suggestedTitles={titles} submitLabel="Save & continue" onSaved={() => setStep(3)} />}
              {step === 3 && <div className="space-y-6"><PlatformsForm submitLabel="Save & continue" onSaved={() => setStep(4)} /><ClipperCard /></div>}
              {step === 4 && (
                <div className="space-y-5 text-sm">
                  <dl className="divide-y overflow-hidden rounded-xl ring-1 ring-border">
                    <Summary label="Resume" value={profile.data?.resume?.original_filename ?? (status.data?.completed ? "None yet: profile created by hand" : undefined)} />
                    <Summary label="Experience" value={profile.data?.experience?.years_months} />
                    <Summary label="Skills" value={profile.data?.confirmed?.skills.slice(0, 12).join(", ")} />
                    <Summary label="Roles" value={prefs.data?.job_titles.join(", ")} />
                    <Summary label="Locations" value={prefs.data?.locations.join(", ")} />
                    <Summary label="Minimum match" value={prefs.data ? `${prefs.data.min_match_score}%` : undefined} />
                    <Summary label="Portals" value={platforms.data?.filter((p) => p.enabled).map((p) => p.platform).join(", ")} />
                  </dl>
                  <div className="flex flex-col items-end gap-1.5">
                    <Button size="lg" onClick={finish} disabled={!status.data?.completed}><Search /> Start discovering jobs</Button>
                    {!status.data?.completed && <p className="text-xs text-muted-foreground">Complete the earlier steps first.</p>}
                  </div>
                </div>
              )}
            </div>
          </section>

          <aside className={cn("space-y-4 lg:sticky lg:top-20", (step === 1 || step === 2 || step === 3) && "hidden lg:block")}>
            {step === 0 && <Expectations />}
            {(step === 1 || step === 2 || step === 3) && <ProfilePreview profile={profile.data} prefs={prefs.data} platforms={platforms.data} />}
            {step === 4 && <NextSteps />}
          </aside>
        </div>
      </div>
    </div>
  );
}

function Summary({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-3 bg-card px-4 py-2.5 sm:grid-cols-[9rem_1fr]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={cn("font-medium", !value && "text-muted-foreground")}>{value || "—"}</dd>
    </div>
  );
}

function SideCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl bg-card p-4 ring-1 ring-border">
      <h3 className="eyebrow mb-3">{title}</h3>
      {children}
    </section>
  );
}

function Expectations() {
  const items: [ReactNode, string, string][] = [
    [<Clock key="Clock" className="size-4" />, "A few minutes", "Five short steps. Upload, review, choose roles, pick portals, confirm."],
    [<Save key="Save" className="size-4" />, "Saved as you go", "Each step is saved when you continue. Leave any time and come back here."],
    [<ShieldCheck key="ShieldCheck" className="size-4" />, "You stay in control", "Nothing is scraped and nothing is submitted for you."],
  ];
  return (
    <SideCard title="What to expect">
      <ul className="space-y-3.5">
        {items.map(([icon, title, body]) => (
          <li key={title} className="flex gap-3">
            <span aria-hidden className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-route-tint text-route">{icon}</span>
            <span className="text-sm"><span className="block font-medium text-heading">{title}</span><span className="text-muted-foreground">{body}</span></span>
          </li>
        ))}
      </ul>
    </SideCard>
  );
}

/** A live read-out of what's been confirmed so far; it refreshes as each step saves. */
function ProfilePreview({ profile, prefs, platforms }: { profile?: ProfileResponse; prefs?: Preferences; platforms?: PlatformInfo[] }) {
  const p = profile?.confirmed ?? profile?.parsed ?? null;
  const confirmed = !!profile?.confirmed_at;
  const initials = (p?.full_name ?? "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  const enabled = (platforms ?? []).filter((x) => x.enabled).map((x) => x.platform);
  const skills = p?.skills ?? [];
  return (
    <SideCard title="Your profile so far">
      {!p ? <p className="text-sm text-muted-foreground">Your details appear here as you go.</p> : (
        <div className="space-y-4 text-sm">
          <div className="flex items-center gap-3">
            <span aria-hidden className="flex size-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-route to-route-bright font-display text-[14px] font-bold text-white">{initials || "·"}</span>
            <div className="min-w-0">
              <div className="truncate font-display text-[15px] font-bold text-heading">{p.full_name || "Your name"}</div>
              {p.headline && <div className="line-clamp-2 text-xs text-muted-foreground">{p.headline}</div>}
            </div>
          </div>
          <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium", confirmed ? "bg-success-tint text-success" : "bg-caution-tint text-caution")}>
            {confirmed ? <><Check className="size-3" aria-hidden /> Profile confirmed</> : "Not confirmed yet"}
          </span>
          <PreviewRow label="Experience">{profile?.experience?.years_months || (p.experience.length ? `${p.experience.length} role${p.experience.length === 1 ? "" : "s"}` : null)}</PreviewRow>
          <PreviewRow label="Location">{p.location}</PreviewRow>
          <PreviewRow label="Skills">
            {skills.length > 0 && (
              <span className="flex flex-wrap gap-1">
                {skills.slice(0, 8).map((k) => <span key={k} className="rounded-full bg-route-tint px-2 py-0.5 text-[11.5px] font-medium text-route">{k}</span>)}
                {skills.length > 8 && <span className="px-1 text-xs text-muted-foreground">+{skills.length - 8}</span>}
              </span>
            )}
          </PreviewRow>
          {prefs?.is_configured && <>
            <PreviewRow label="Roles">{prefs.job_titles.join(", ")}</PreviewRow>
            <PreviewRow label="Where">{[...prefs.locations, ...prefs.work_modes].join(", ")}</PreviewRow>
            <PreviewRow label="Min. match"><span className="readout">{prefs.min_match_score}%</span></PreviewRow>
          </>}
          {enabled.length > 0 && <PreviewRow label="Portals">{enabled.join(", ")}</PreviewRow>}
        </div>
      )}
    </SideCard>
  );
}

function PreviewRow({ label, children }: { label: string; children: ReactNode }) {
  if (children == null || children === "" || children === false) return null;
  return (
    <div>
      <div className="mb-1 text-[11px] font-medium text-muted-foreground">{label}</div>
      <div className="text-foreground">{children}</div>
    </div>
  );
}

function NextSteps() {
  return (
    <SideCard title="What happens next">
      <ol className="space-y-3 text-sm">
        {([
          [<Search key="Search" className="size-4" />, "JobPilot searches the job boards for you. The first search takes a few minutes; you can keep using the app."],
          [<FileText key="FileText" className="size-4" />, "Build a resume in Resume Studio from the profile you just confirmed."],
          [<Send key="Send" className="size-4" />, "Apply: JobPilot fills in what it knows, and you review everything before anything is sent."],
        ] as [ReactNode, string][]).map(([icon, text], i) => (
          <li key={i} className="flex gap-3">
            <span aria-hidden className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-lavender text-violet">{icon}</span>
            <span className="pt-1 text-muted-foreground">{text}</span>
          </li>
        ))}
      </ol>
    </SideCard>
  );
}
