import { useRef } from "react";
import { Download } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { ProfileWelcome } from "@/components/settings/ProfileWelcome";
import { useUnsavedGuard } from "@/components/settings/UnsavedGuard";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { LoadingState, PageHeader } from "@/components/app/common";
import { ExtensionSettings } from "@/components/app/ExtensionSettings";
import { NotificationSettings, NotificationTypeSettings, ResumeVersions } from "@/components/app/ProfileExtras";
import { ClipperCard, PlatformsForm, PreferencesForm, ProfileForm, ResumeUpload } from "@/components/app/forms";
import { AccountSection } from "@/components/settings/AccountSection";
import { AnswersSection } from "@/components/settings/AnswersSection";
import { EmailSection } from "@/components/settings/EmailSection";
import { PortalConnections } from "@/components/settings/PortalConnections";
import { SectionStatus } from "@/components/settings/SectionStatus";
import { SettingsNav } from "@/components/settings/SettingsNav";
import { sectionFor } from "@/components/settings/config";
import { Panel } from "@/components/settings/primitives";
import { CareerGoalsForm, PrivacyConsents } from "@/features/career/SettingsTabs";
import { downloadFile, errorMessage } from "@/lib/api";
import { usePreferences, useProfile } from "@/services/queries";

export function SettingsPage() {
  const profile = useProfile();
  const prefs = usePreferences();
  // Deep links such as #/settings?tab=answers (used by the browser extension's "update your profile" links).
  // The section follows the URL, so in-app links like /settings?tab=account also switch sections.
  const [params, setParams] = useSearchParams();
  const section = sectionFor(params.get("tab"));
  const tab = section.key;
  const top = useRef<HTMLDivElement>(null);
  const guard = useUnsavedGuard(tab);
  const setTab = (t: string) => { if (t !== tab) guard.confirm(() => switchTo(t)); };
  const switchTo = (t: string) => {
    setParams((p) => { const next = new URLSearchParams(p); next.set("tab", t); return next; }, { replace: true });
    // Coming from far down a long form: bring the new section's header into view.
    const el = top.current;
    if (el && el.getBoundingClientRect().top < 64) {
      const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: window.scrollY + el.getBoundingClientRect().top - 72, behavior: reduce ? "auto" : "smooth" });
    }
  };

  const attention: Record<string, string | undefined> = {
    profile: profile.data && (!profile.data.confirmed_at || profile.data.review?.status === "needs_review") ? "needs review" : undefined,
    preferences: prefs.data && !prefs.data.is_configured ? "not set up" : undefined,
  };

  return (
    <>
      <PageHeader title={<>Your setup, <em>your rules</em></>}
                  description="Tune how JobPilot finds jobs, fills applications and keeps you posted. Everything here stays private to your account, no cap." />
      <div className="xl:grid xl:grid-cols-[224px_minmax(0,1fr)] xl:gap-10">
        <SettingsNav active={tab} onSelect={setTab} attention={attention} />
        <div ref={top} className="min-w-0 scroll-mt-20">
          <div key={tab} className="animate-in fade-in-0 slide-in-from-bottom-4 duration-[340ms] ease-[cubic-bezier(.2,0,0,1)]">
            <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div className="min-w-0">
                <div className="eyebrow mb-1.5">{section.group}</div>
                <h2 className="font-display text-[22px] leading-tight font-extrabold tracking-[-0.025em] text-heading">{section.label}</h2>
                <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-muted-foreground">{section.description}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2 sm:pb-0.5">
                {guard.dirty && <span className="animate-in rounded-full bg-caution-tint px-2.5 py-1 text-xs font-medium text-caution duration-200 fade-in-0 zoom-in-95" role="status">Unsaved changes</span>}
                <SectionStatus section={tab} />
              </div>
            </header>
            <div ref={guard.bodyRef} key={guard.resetKey} data-dirty={guard.dirty || undefined}
                 className="data-[dirty]:[&_[data-save-bar]]:ring-2 data-[dirty]:[&_[data-save-bar]]:ring-caution/30">
              <SectionBody tab={tab} profile={profile} prefs={prefs} />
            </div>
          </div>
        </div>
      </div>
      {guard.dialog}
    </>
  );
}

function SectionBody({ tab, profile, prefs }: { tab: string; profile: ReturnType<typeof useProfile>; prefs: ReturnType<typeof usePreferences> }) {
  switch (tab) {
    case "profile":
      return (
        <div className="space-y-5">
          <ProfileWelcome profile={profile.data} loading={profile.isLoading}
                          onEdit={() => document.getElementById("candidate-profile")?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" })} />
          <Panel title="Resume" description="Uploading a new resume re-parses it. Review your profile below afterwards."
                 actions={profile.data?.resume && (
                   <Button size="sm" variant="outline" onClick={() => downloadFile("/profile/resume", profile.data?.resume?.original_filename ?? "resume.pdf").catch((e) => toast.error(errorMessage(e)))}>
                     <Download /> <span className="hidden sm:inline">Download current</span><span className="sm:hidden">Download</span>
                   </Button>
                 )}>
            <ResumeUpload profile={profile.data} />
          </Panel>
          <ResumeVersions />
          <p className="rounded-xl bg-paper-sunk/70 px-4 py-3 text-[13px] text-muted-foreground ring-1 ring-border/70">
            Also on LinkedIn or Naukri? <a href="#/settings?tab=portals" className="font-medium text-route hover:underline">Portal Connections</a> has
            a checklist for your profile there, built from the profile below.
          </p>
          <div id="candidate-profile" className="scroll-mt-20" />
          <Panel title="Candidate profile" description="Used for matching and for answering screening questions. Saving re-scores your open jobs.">
            {profile.data ? <ProfileForm profile={profile.data} /> : <LoadingState />}
          </Panel>
        </div>
      );
    case "career-goals":
      return <CareerGoalsForm />;
    case "preferences":
      return (
        <Panel>
          {prefs.data ? <PreferencesForm initial={prefs.data.is_configured ? prefs.data : undefined} /> : <LoadingState />}
        </Panel>
      );
    case "platforms":
      return (
        <div className="space-y-5">
          <Panel title="Job platforms" description="Switch a platform on, then choose how its jobs reach JobPilot.">
            <PlatformsForm />
          </Panel>
          <ClipperCard />
        </div>
      );
    case "portals":
      return <PortalConnections />;
    case "extension":
      return <ExtensionSettings />;
    case "answers":
      return <AnswersSection facts={profile.data?.verified_facts} />;
    case "email":
      return <EmailSection />;
    case "notifications":
      return <div className="space-y-5"><NotificationTypeSettings /><NotificationSettings /></div>;
    case "privacy":
      return <PrivacyConsents />;
    case "account":
      return <AccountSection />;
    default:
      return null;
  }
}
