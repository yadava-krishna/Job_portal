import { ArrowDown, BadgeCheck, Briefcase, FileText, FolderGit2, GraduationCap, MapPin, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/contexts/AuthContext";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ProfileResponse } from "@/types/api";

/** What makes a profile strong for matching, with the action that fixes each gap. Only checks data we actually have. */
function strength(p: ProfileResponse) {
  const prof = p.confirmed ?? p.parsed;
  const checks: [boolean, string][] = [
    [p.has_resume, "Upload a resume"],
    [!!prof?.headline, "Add a headline"],
    [!!prof?.summary && prof.summary.length > 40, "Write a short summary"],
    [(prof?.skills.length ?? 0) >= 5, "List at least 5 skills"],
    [(prof?.experience.length ?? 0) > 0 || (prof?.projects.length ?? 0) > 0, "Add experience or a project"],
    [(prof?.education.length ?? 0) > 0, "Add your education"],
    [!!prof?.location, "Add your location"],
    [!!(prof?.linkedin_url || prof?.github_url || prof?.portfolio_url || prof?.website_url), "Add a profile or portfolio link"],
    [!!p.confirmed_at, "Confirm your profile"],
  ];
  const done = checks.filter(([ok]) => ok).length;
  return { percent: Math.round((done / checks.length) * 100), missing: checks.filter(([ok]) => !ok).map(([, label]) => label) };
}

function Ring({ percent }: { percent: number }) {
  const r = 30;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative size-[76px] shrink-0" role="img" aria-label={`Profile strength ${percent} percent`}>
      <svg viewBox="0 0 76 76" className="-rotate-90">
        <circle cx="38" cy="38" r={r} fill="none" strokeWidth="7" className="stroke-card/70" />
        <circle cx="38" cy="38" r={r} fill="none" strokeWidth="7" strokeLinecap="round" stroke="url(#pw-ring)"
                strokeDasharray={c} strokeDashoffset={c - (percent / 100) * c} className="jp-ring" style={{ ["--c" as string]: `${c}` }} />
        <defs><linearGradient id="pw-ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--route)" /><stop offset="1" stopColor="var(--route-bright)" /></linearGradient></defs>
      </svg>
      <span className="readout absolute inset-0 flex items-center justify-center text-[17px] font-semibold text-heading">{percent}<span className="text-[11px] text-muted-foreground">%</span></span>
    </div>
  );
}

/** The top of "Resume & profile": a warm hello, how strong the profile is, and the one or two things worth doing next. */
export function ProfileWelcome({ profile, loading, onEdit }: { profile?: ProfileResponse; loading?: boolean; onEdit: () => void }) {
  const { user } = useAuth();
  if (loading || !profile) return <Skeleton className="h-[220px] rounded-[22px]" />;
  const prof = profile.confirmed ?? profile.parsed;
  const name = prof?.full_name || user?.full_name || "";
  const first = name.split(" ")[0];
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("") || "·";
  const s = strength(profile);
  const skills = prof?.skills ?? [];
  const stats: [React.ElementType, string, string][] = [
    [Briefcase, profile.experience?.years_months || "—", "experience"],
    [Sparkles, String(skills.length), skills.length === 1 ? "skill" : "skills"],
    [FolderGit2, String(prof?.projects.length ?? 0), (prof?.projects.length ?? 0) === 1 ? "project" : "projects"],
    [GraduationCap, String(prof?.education.length ?? 0), "education"],
  ];

  return (
    <section aria-label="Your profile at a glance" className="jp-item relative isolate overflow-hidden rounded-[22px] ring-1 ring-border">
      <div aria-hidden className="absolute inset-0 -z-10 bg-gradient-to-br from-route-tint via-lavender/70 to-peach/60" />
      <svg aria-hidden viewBox="0 0 600 200" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 -z-10 h-full w-full opacity-50">
        <path d="M330 170 L420 130 L500 140 L610 60" fill="none" stroke="var(--route)" strokeWidth="1.4" strokeDasharray="2 7" strokeLinecap="round" />
        <circle cx="420" cy="130" r="4" fill="var(--route)" opacity=".5" /><circle cx="500" cy="140" r="4" fill="var(--route)" opacity=".5" />
      </svg>

      <div className="grid gap-5 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div className="flex min-w-0 items-start gap-4">
          <div className="relative shrink-0">
            <span className="flex size-[68px] items-center justify-center rounded-[20px] bg-gradient-to-br from-route to-route-bright font-display text-[24px] font-extrabold text-white shadow-[var(--shadow-raised)]" aria-hidden>{initials}</span>
            {profile.confirmed_at && <BadgeCheck className="absolute -right-1.5 -bottom-1.5 size-6 rounded-full bg-card fill-success-tint p-0.5 text-success" aria-label="Profile confirmed" />}
          </div>
          <div className="min-w-0">
            <h3 className="font-display text-[24px] leading-tight font-extrabold tracking-[-0.03em] text-heading sm:text-[26px]">
              Hey{first ? <>, <em className="not-italic text-violet">{first}</em></> : null}. This is you on paper.
            </h3>
            <p className="mt-1 text-[14px] text-foreground/75">
              {prof?.headline || "Add a headline so matches know what you're aiming for."}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-foreground/70">
              {prof?.location && <span className="inline-flex items-center gap-1.5"><MapPin className="size-3.5" aria-hidden />{prof.location}</span>}
              {profile.resume && <span className="inline-flex items-center gap-1.5"><FileText className="size-3.5" aria-hidden />{profile.resume.original_filename} · {timeAgo(profile.resume.uploaded_at)}</span>}
              <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium", profile.confirmed_at ? "bg-success-tint text-success" : "bg-caution-tint text-caution")}>
                {profile.confirmed_at ? "Confirmed · used for matching" : "Needs your review before matching"}
              </span>
            </div>
            {skills.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                {skills.slice(0, 8).map((k) => <span key={k} className="rounded-full bg-card/85 px-2.5 py-0.5 text-xs font-medium text-route ring-1 ring-route/15">{k}</span>)}
                {skills.length > 8 && <span className="text-xs text-muted-foreground">+{skills.length - 8} more</span>}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4 rounded-2xl bg-card/75 p-4 ring-1 ring-white/60 backdrop-blur-sm lg:w-[320px]">
          <Ring percent={s.percent} />
          <div className="min-w-0">
            <div className="text-[13px] font-semibold text-heading">{s.percent >= 90 ? "Looking sharp." : s.percent >= 60 ? "Nearly there." : "Let's build this up."}</div>
            <p className="text-[12px] text-muted-foreground">Profile strength for matching</p>
            {s.missing.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-[12px]">
                {s.missing.slice(0, 2).map((m) => <li key={m} className="flex items-center gap-1.5 text-foreground/80"><span className="size-1.5 rounded-full bg-coral" aria-hidden />{m}</li>)}
              </ul>
            )}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-white/50 bg-card/55 px-5 py-3.5 backdrop-blur-sm sm:px-6">
        {stats.map(([Icon, value, label]) => (
          <div key={label} className="flex items-center gap-2">
            <Icon className="size-4 text-violet" aria-hidden />
            <span className="readout text-[14px] font-semibold text-heading">{value}</span>
            <span className="text-[12px] text-muted-foreground">{label}</span>
          </div>
        ))}
        <Button size="sm" variant="ink" onClick={onEdit} className="ml-auto"><ArrowDown /> Edit details</Button>
      </div>
    </section>
  );
}
