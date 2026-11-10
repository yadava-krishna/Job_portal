import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Loader2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ClipperCard, PlatformsForm, PreferencesForm, ProfileForm, ResumeUpload } from "@/components/app/forms";
import { Brand } from "@/layouts/AppLayout";
import { useAuth } from "@/contexts/AuthContext";
import { qk, useOnboarding, usePlatforms, usePreferences, useProfile } from "@/services/queries";
import { cn } from "@/lib/utils";

const steps = ["Resume", "Review profile", "Job preferences", "Job portals", "Confirm"];

export function OnboardingPage() {
  const status = useOnboarding();
  const profile = useProfile();
  const prefs = usePreferences();
  const platforms = usePlatforms();
  const { refreshUser } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [manual, setManual] = useState(false);

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

  return (
    <div className="min-h-dvh bg-muted/30">
      <header className="border-b bg-background px-4 py-3 sm:px-6"><Brand /></header>
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">Set up your job search</h1>
        <p className="mt-1 text-sm text-muted-foreground">A few minutes now makes every match score more accurate.</p>
        <ol className="my-6 grid grid-cols-5 gap-2">
          {steps.map((s, i) => (
            <li key={s} className="flex flex-col items-center gap-1 text-center">
              <button type="button" onClick={() => i <= step && setStep(i)} disabled={i > step}
                      className={cn("flex size-8 items-center justify-center rounded-full border text-sm font-semibold", i < step ? "border-primary bg-primary text-primary-foreground" : i === step ? "border-primary text-primary" : "text-muted-foreground")}>
                {i < step ? <Check className="size-4" /> : i + 1}
              </button>
              <span className={cn("hidden text-xs sm:block", i === step ? "font-medium" : "text-muted-foreground")}>{s}</span>
            </li>
          ))}
        </ol>

        <Card>
          {step === 0 && (
            <>
              <CardHeader><CardTitle>Upload your resume</CardTitle><CardDescription>We read your PDF to pre-fill your profile. Nothing is invented; you review everything next.</CardDescription></CardHeader>
              <CardContent className="space-y-4">
                <ResumeUpload profile={profile.data} onUploaded={() => setStep(1)} />
                {profile.data?.has_resume && <div className="flex justify-end"><Button onClick={() => setStep(1)}>Continue</Button></div>}
                {!profile.data?.has_resume && (
                  <div className="rounded-lg border border-dashed p-4 text-sm">
                    <p className="font-medium">No resume yet?</p>
                    <p className="mt-1 text-muted-foreground">Students and early-career candidates can build a profile by hand: your education, projects and skills. You can make a resume from it later in Resume Studio.</p>
                    <Button variant="outline" size="sm" className="mt-3" onClick={() => { setManual(true); setStep(1); }}>Create my profile without a resume</Button>
                  </div>
                )}
              </CardContent>
            </>
          )}
          {step === 1 && (
            <>
              <CardHeader><CardTitle>{manual ? "Create your profile" : "Review your profile"}</CardTitle><CardDescription>{manual ? "Add what is true today: education, projects and skills count; you don't need work experience. Only what you enter here is used." : "Correct anything the parser got wrong. Only confirmed details are used for matching and screening answers."}</CardDescription></CardHeader>
              <CardContent>{profile.data ? <ProfileForm profile={profile.data} manual={manual || !profile.data.has_resume} submitLabel="Confirm profile & continue" onSaved={() => setStep(2)} /> : <Loader2 className="animate-spin" />}</CardContent>
            </>
          )}
          {step === 2 && (
            <>
              <CardHeader><CardTitle>What are you looking for?</CardTitle><CardDescription>Choose one or more domains and roles. You can change these any time.</CardDescription></CardHeader>
              <CardContent><PreferencesForm initial={prefs.data?.is_configured ? prefs.data : undefined} suggestedTitles={titles} submitLabel="Save & continue" onSaved={() => setStep(3)} /></CardContent>
            </>
          )}
          {step === 3 && (
            <>
              <CardHeader><CardTitle>Choose job portals</CardTitle><CardDescription>Enable each platform and pick how jobs reach JobPilot. Nothing is scraped and nothing is submitted for you.</CardDescription></CardHeader>
              <CardContent className="space-y-6"><PlatformsForm submitLabel="Save & continue" onSaved={() => setStep(4)} /><ClipperCard /></CardContent>
            </>
          )}
          {step === 4 && (
            <>
              <CardHeader><CardTitle>All set</CardTitle><CardDescription>Here's what JobPilot will use.</CardDescription></CardHeader>
              <CardContent className="space-y-3 text-sm">
                <Summary label="Resume" value={profile.data?.resume?.original_filename ?? (status.data?.completed ? "None yet: profile created by hand" : undefined)} />
                <Summary label="Experience" value={profile.data?.experience?.years_months} />
                <Summary label="Skills" value={profile.data?.confirmed?.skills.slice(0, 12).join(", ")} />
                <Summary label="Roles" value={prefs.data?.job_titles.join(", ")} />
                <Summary label="Locations" value={prefs.data?.locations.join(", ")} />
                <Summary label="Minimum match" value={prefs.data ? `${prefs.data.min_match_score}%` : undefined} />
                <Summary label="Portals" value={platforms.data?.filter((p) => p.enabled).map((p) => p.platform).join(", ")} />
                <div className="flex justify-end pt-2"><Button onClick={finish} disabled={!status.data?.completed}>Start discovering jobs</Button></div>
                {!status.data?.completed && <p className="text-right text-xs text-muted-foreground">Complete the earlier steps first.</p>}
              </CardContent>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function Summary({ label, value }: { label: string; value?: string | null }) {
  return <div className="grid grid-cols-[8rem_1fr] gap-2 border-b pb-2 last:border-0"><span className="text-muted-foreground">{label}</span><span className="font-medium">{value || "—"}</span></div>;
}
