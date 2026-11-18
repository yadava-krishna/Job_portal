import { useState } from "react";
import { Banknote, Bookmark, BookmarkCheck, Briefcase, Copy, EyeOff, FileText, MapPin, MoreHorizontal, Send, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { PlatformBadge, StatusBadge } from "@/components/app/common";
import { FreshnessBadge } from "@/components/app/Freshness";
import { postedDisplay, scoreTone, seenOn, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { UserJob } from "@/types/api";

export interface JobCardActions {
  onView: (j: UserJob) => void;
  onSave: (j: UserJob) => void;
  onApply: (j: UserJob) => void;
  onDismiss: (j: UserJob) => void;
  /** Open another listing of the same role (a city or re-post grouped onto this card). */
  onViewId?: (userJobId: number) => void;
}

const scoreWords: Record<ReturnType<typeof scoreTone>, string> = {
  excellent: "Strong match", good: "Good match", moderate: "Partial match", low: "Weak match", none: "Not scored",
};
const scoreColour: Record<ReturnType<typeof scoreTone>, string> = {
  excellent: "text-route", good: "text-violet", moderate: "text-heading/70", low: "text-muted-foreground", none: "text-muted-foreground",
};

/** A company monogram in a soft tile, tinted from the name so neighbouring rows are easy to tell apart. */
export function CompanyMark({ name, className }: { name: string; className?: string }) {
  const letters = name.replace(/[^A-Za-z0-9 ]/g, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "·";
  const tints = ["bg-route-tint text-route", "bg-lavender text-violet", "bg-peach text-coral-ink", "bg-paper-sunk text-heading"];
  const tint = tints[[...name].reduce((n, ch) => n + ch.charCodeAt(0), 0) % tints.length];
  return <span aria-hidden className={cn("flex shrink-0 items-center justify-center rounded-xl font-display font-bold", tint, className)}>{letters}</span>;
}

function Meta({ icon: Icon, children, title }: { icon: React.ElementType; children: React.ReactNode; title?: string }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <Icon className="size-3.5 shrink-0 text-muted-foreground/80" aria-hidden /><span className="truncate" title={title}>{children}</span>
    </span>
  );
}

/** One job in a list: scannable in a glance, every action within reach, nothing repeated. */
export function JobCard({ item, active, actions, disabled }: { item: UserJob; active?: boolean; actions: JobCardActions; disabled?: boolean }) {
  const j = item.job;
  const dismissed = item.status === "dismissed";
  const applied = item.status === "applied";
  const posted = postedDisplay(j);
  const platforms = seenOn(j);
  const tone = scoreTone(item.match_score);
  const ineligible = item.eligibility_status === "INELIGIBLE" || item.eligibility === "fail";
  const place = `${j.location_normalized || j.location || "Location not stated"}${j.work_mode && !(j.work_mode === "Remote" && (j.location_normalized ?? "").startsWith("Remote")) ? ` · ${j.work_mode}` : ""}`;
  const have = item.matching_skills;
  const total = have.length + item.missing_skills.length;
  const [bumped, setBumped] = useState(false);

  return (
    <article data-active={active || undefined} data-saved={item.is_saved || undefined}
             className={cn("group/job relative rounded-2xl bg-card px-4 py-3.5 ring-1 transition-[box-shadow,background-color,transform] duration-150 sm:px-5",
               "hover:-translate-y-px hover:shadow-[var(--shadow-raised)] hover:ring-route/25",
               active ? "ring-2 ring-route/45 shadow-[var(--shadow-raised)]" : "ring-border", dismissed && "opacity-65")}>
      {active && <span aria-hidden className="absolute top-4 bottom-4 left-0 w-[3px] rounded-r-full bg-route" />}
      <div className="flex gap-3.5 sm:gap-4">
        <CompanyMark name={j.company || "?"} className="mt-0.5 size-11 text-[14px]" />
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <button type="button" onClick={() => actions.onView(item)} className="max-w-full rounded text-left focus-visible:outline-2 focus-visible:outline-ring">
                <h3 className="truncate font-display text-[16.5px] leading-snug font-bold tracking-[-0.015em] text-heading decoration-route/40 underline-offset-4 group-hover/job:underline">{j.title || "Untitled role"}</h3>
              </button>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted-foreground">
                <span className="font-medium text-foreground">{j.company || "Unknown company"}</span>
                <span aria-hidden>·</span>
                <span title={posted.title}>{posted.text}</span>
                <span data-testid="posted-confidence" className={cn("rounded-full px-1.5 py-px text-[9.5px] font-semibold tracking-wide uppercase",
                  posted.badge === "Verified" ? "bg-success-tint text-success" : posted.badge === "Estimated" ? "bg-caution-tint text-caution" : "bg-muted text-muted-foreground")}>
                  {posted.badge}
                </span>
                <span aria-hidden>·</span>
                <span title={j.first_seen_at ?? item.discovered_at}>Found {timeAgo(item.discovered_at)}</span>
                {platforms.map((p) => <PlatformBadge key={p} platform={p} />)}
                <FreshnessBadge job={j} />
              </div>
            </div>
            <div className="shrink-0 text-right" aria-label={item.match_score == null ? "Not scored" : `${Math.round(item.match_score)} percent match`}>
              <div className={cn("readout text-[22px] leading-none font-semibold", scoreColour[tone])}>
                <span>{item.match_score == null ? "–" : Math.round(item.match_score)}</span>{item.match_score != null && <span className="text-[13px] text-muted-foreground">%</span>}
              </div>
              <div className={cn("mt-1 text-[11px] font-medium", tone === "excellent" ? "text-route" : "text-muted-foreground")}>{scoreWords[tone]}</div>
            </div>
            <Button variant="ghost" size="icon-sm" className={cn("-mt-0.5 -mr-1 shrink-0", item.is_saved ? "text-violet" : "text-muted-foreground")}
                    onClick={() => { setBumped(true); actions.onSave(item); }} disabled={disabled} aria-pressed={item.is_saved}
                    aria-label={item.is_saved ? "Saved" : "Save"} title={item.is_saved ? "Saved · click to remove" : "Save for later  (s)"}>
              {item.is_saved ? <BookmarkCheck className={cn(bumped && "jp-bump")} fill="currentColor" fillOpacity={0.15} /> : <Bookmark className={cn(bumped && "jp-bump")} />}
            </Button>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-foreground/80">
            <Meta icon={MapPin} title={j.location && j.location !== j.location_normalized ? `As posted: ${j.location}` : undefined}>{place}</Meta>
            <Meta icon={Briefcase}>{j.experience_required || "Experience not stated"}</Meta>
            <Meta icon={Banknote} title={j.salary_range && j.salary_label ? `As posted: ${j.salary_range}` : undefined}>{j.salary_label || j.salary_range || "Salary not disclosed"}</Meta>
            {item.application_status && <StatusBadge status={item.application_status} />}
            {ineligible && (
              <span data-testid="not-eligible-badge" className="cursor-help rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive"
                    title={item.eligibility_reasons?.length ? `Why: ${item.eligibility_reasons.join("; ")}` : "Open the job to see why"}>Not eligible</span>
            )}
            {j.sponsorship_signal === "verified" && <span data-testid="sponsorship-badge" className="rounded-full bg-lavender px-2 py-0.5 text-xs text-violet" title="The posting says visa sponsorship is offered">Visa sponsorship</span>}
            {j.sponsorship_signal === "inferred" && <span className="rounded-full bg-lavender px-2 py-0.5 text-xs text-violet" title="Relocation is mentioned; sponsorship isn't stated">Relocation mentioned</span>}
            {j.sponsorship_signal === "none" && <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground" title="The posting says sponsorship isn't offered">No sponsorship</span>}
            {j.seniority && <span className="rounded-full border px-2 py-0.5 text-xs capitalize text-muted-foreground">{j.seniority}</span>}
          </div>

          {(item.similar?.length ?? 0) > 0 && (
            <div data-testid="similar-listings" className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <Copy className="size-3.5" aria-hidden />
              <span>Also listed {item.similar!.length === 1 ? "once more" : `${item.similar!.length} more times`}:</span>
              {item.similar!.slice(0, 4).map((s) => (
                <button key={s.user_job_id} type="button" onClick={() => actions.onViewId?.(s.user_job_id)} disabled={!actions.onViewId}
                        className="rounded-full border px-2 py-0.5 hover:bg-muted disabled:cursor-default">{s.location || "location not stated"}</button>
              ))}
              {item.similar!.length > 4 && <span>+{item.similar!.length - 4} more</span>}
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs">
              {total > 0 ? (
                <>
                  <span className="mr-0.5 text-muted-foreground">You match <span className="readout font-medium text-foreground">{have.length}/{total}</span> skills</span>
                  {have.slice(0, 3).map((s) => <span key={s} className="rounded-full bg-route-tint px-2 py-0.5 font-medium text-route">{s}</span>)}
                  {have.length > 3 && <span className="text-muted-foreground" title={have.slice(3).join(", ")}>+{have.length - 3} more</span>}
                  {item.missing_skills.length > 0 && <span className="rounded-full bg-peach px-2 py-0.5 font-medium text-coral-ink" title={`To learn: ${item.missing_skills.join(", ")}`}>to learn: {item.missing_skills[0]}{item.missing_skills.length > 1 ? ` +${item.missing_skills.length - 1}` : ""}</span>}
                </>
              ) : !j.description_preview ? (
                <span className="text-muted-foreground italic">No description yet. Open the job to paste it for an accurate score.</span>
              ) : <span className="line-clamp-1 text-muted-foreground">{j.description_preview}</span>}
            </div>
            <div className="ml-auto flex items-center gap-1.5">
              <Button size="sm" variant="ghost" onClick={() => actions.onView(item)}><FileText /> View full JD</Button>
              <Button size="sm" className="px-4" onClick={() => actions.onApply(item)} disabled={disabled || !j.job_url}>
                <Send /> {applied ? "View application" : item.application_id ? "Continue" : "Apply"}
              </Button>
              {!applied && (
                <DropdownMenu>
                  <DropdownMenuTrigger render={<Button size="icon-sm" variant="ghost" aria-label="More actions" className="text-muted-foreground" />}><MoreHorizontal /></DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="min-w-44">
                    <DropdownMenuItem onClick={() => actions.onDismiss(item)} disabled={disabled}>
                      {dismissed ? <><Undo2 /> Restore</> : <><EyeOff /> Not for me (dismiss)</>}
                    </DropdownMenuItem>
                    {j.job_url && <DropdownMenuItem onClick={() => window.open(j.job_url!, "_blank", "noopener,noreferrer")}><FileText /> Open original listing</DropdownMenuItem>}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

const scoreBar: Record<ReturnType<typeof scoreTone>, string> = {
  excellent: "bg-gradient-to-r from-route to-route-bright", good: "bg-route-bright/70", moderate: "bg-heading/30", low: "bg-muted-foreground/30", none: "bg-muted",
};

/** The square job tile used in the Discover and Saved grids: everything needed to decide, in one glance. */
export function JobTile({ item, active, actions, disabled, index = 0 }: { item: UserJob; active?: boolean; actions: JobCardActions; disabled?: boolean; index?: number }) {
  const j = item.job;
  const dismissed = item.status === "dismissed";
  const applied = item.status === "applied";
  const posted = postedDisplay(j);
  const platforms = seenOn(j);
  const tone = scoreTone(item.match_score);
  const ineligible = item.eligibility_status === "INELIGIBLE" || item.eligibility === "fail";
  const place = `${j.location_normalized || j.location || "Location not stated"}${j.work_mode && !(j.work_mode === "Remote" && (j.location_normalized ?? "").startsWith("Remote")) ? ` · ${j.work_mode}` : ""}`;
  const have = item.matching_skills;
  const total = have.length + item.missing_skills.length;
  const pct = item.match_score == null ? 0 : Math.max(4, Math.min(100, item.match_score));
  const [bumped, setBumped] = useState(false);

  return (
    <article data-active={active || undefined} data-saved={item.is_saved || undefined} style={{ ["--i" as string]: Math.min(index, 12) }}
             className={cn("jp-item group/job relative flex h-full flex-col overflow-hidden rounded-[20px] bg-card ring-1 transition-[transform,box-shadow] duration-200 ease-[cubic-bezier(.2,0,0,1)]",
               "hover:-translate-y-1 hover:shadow-[var(--shadow-overlay)] hover:ring-route/30",
               active ? "ring-2 ring-route/50 shadow-[var(--shadow-raised)]" : "ring-border", dismissed && "opacity-65")}>
      {/* soft header: company, source, save */}
      <div className="relative bg-gradient-to-br from-route-tint via-card to-lavender/60 px-4 pt-4 pb-3">
        <svg viewBox="0 0 200 40" preserveAspectRatio="none" aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-10 w-full opacity-40">
          <path d="M-4 34 L60 22 L120 26 L204 6" fill="none" stroke="var(--route)" strokeWidth="0.8" strokeDasharray="1 4" strokeLinecap="round" />
        </svg>
        <div className="relative flex items-start gap-3">
          <CompanyMark name={j.company || "?"} className="size-11 text-[14px] shadow-sm ring-1 ring-white/70" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-semibold">{j.company || "Unknown company"}</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
              <span title={j.first_seen_at ?? item.discovered_at}>Found {timeAgo(item.discovered_at)}</span>
              {platforms.slice(0, 1).map((p) => <PlatformBadge key={p} platform={p} />)}
              {platforms.length > 1 && <span title={platforms.join(", ")}>+{platforms.length - 1}</span>}
            </div>
          </div>
          <Button variant="ghost" size="icon-sm" className={cn("-mt-1 -mr-1 shrink-0 bg-card/70 backdrop-blur", item.is_saved ? "text-violet" : "text-muted-foreground")}
                  onClick={() => { setBumped(true); actions.onSave(item); }} disabled={disabled} aria-pressed={item.is_saved}
                  aria-label={item.is_saved ? "Saved" : "Save"} title={item.is_saved ? "Saved · click to remove" : "Save for later  (s)"}>
            {item.is_saved ? <BookmarkCheck className={cn(bumped && "jp-bump")} fill="currentColor" fillOpacity={0.15} /> : <Bookmark className={cn(bumped && "jp-bump")} />}
          </Button>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-3 px-4 pt-3 pb-4">
        <button type="button" onClick={() => actions.onView(item)} className="rounded text-left focus-visible:outline-2 focus-visible:outline-ring">
          <h3 className="line-clamp-2 min-h-[2.6em] font-display text-[17px] leading-snug font-bold tracking-[-0.015em] text-heading decoration-route/40 underline-offset-4 group-hover/job:underline">{j.title || "Untitled role"}</h3>
        </button>

        {/* match meter */}
        <div aria-label={item.match_score == null ? "Not scored" : `${Math.round(item.match_score)} percent match`}>
          <div className="flex items-baseline justify-between gap-2">
            <span className={cn("readout text-[24px] leading-none font-semibold", scoreColour[tone])}>
              <span>{item.match_score == null ? "–" : Math.round(item.match_score)}</span>{item.match_score != null && <span className="text-[13px] text-muted-foreground">%</span>}
            </span>
            <span className={cn("text-[12px] font-medium", tone === "excellent" ? "text-route" : "text-muted-foreground")}>{scoreWords[tone]}{total > 0 && <> · {have.length}/{total} skills</>}</span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
            <div className={cn("jp-meter h-full rounded-full", scoreBar[tone])} style={{ width: `${pct}%` }} />
          </div>
        </div>

        <dl className="grid grid-cols-1 gap-1.5 text-[13px] text-foreground/85">
          <Meta icon={MapPin} title={j.location && j.location !== j.location_normalized ? `As posted: ${j.location}` : undefined}>{place}</Meta>
          <div className="flex min-w-0 flex-wrap gap-x-4 gap-y-1.5">
            <Meta icon={Briefcase}>{j.experience_required || "Experience not stated"}</Meta>
            <Meta icon={Banknote} title={j.salary_range && j.salary_label ? `As posted: ${j.salary_range}` : undefined}>{j.salary_label || j.salary_range || "Salary not disclosed"}</Meta>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-muted-foreground">
            <span title={posted.title}>{posted.text}</span>
            <span className={cn("rounded-full px-1.5 py-px text-[9.5px] font-semibold tracking-wide uppercase",
              posted.badge === "Verified" ? "bg-success-tint text-success" : posted.badge === "Estimated" ? "bg-caution-tint text-caution" : "bg-muted text-muted-foreground")}>{posted.badge}</span>
            <FreshnessBadge job={j} />
          </div>
        </dl>

        {(ineligible || item.application_status || j.sponsorship_signal === "verified") && (
          <div className="flex flex-wrap gap-1.5 text-xs">
            {item.application_status && <StatusBadge status={item.application_status} />}
            {ineligible && <span className="cursor-help rounded-full bg-destructive/10 px-2 py-0.5 font-medium text-destructive" title={item.eligibility_reasons?.length ? `Why: ${item.eligibility_reasons.join("; ")}` : "Open the job to see why"}>Not eligible</span>}
            {j.sponsorship_signal === "verified" && <span className="rounded-full bg-lavender px-2 py-0.5 text-violet">Visa sponsorship</span>}
          </div>
        )}

        {total > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {have.slice(0, 3).map((s) => <span key={s} className="rounded-full bg-route-tint px-2 py-0.5 font-medium text-route">{s}</span>)}
            {have.length > 3 && <span className="text-muted-foreground" title={have.slice(3).join(", ")}>+{have.length - 3}</span>}
            {item.missing_skills.length > 0 && <span className="rounded-full bg-peach px-2 py-0.5 font-medium text-coral-ink" title={`To learn: ${item.missing_skills.join(", ")}`}>learn {item.missing_skills[0]}</span>}
          </div>
        ) : !j.description_preview && <p className="text-xs text-muted-foreground italic">No description yet. Open it to paste one for an accurate score.</p>}

        <div className="mt-auto flex items-center gap-1.5 border-t pt-3">
          <Button size="sm" variant="ghost" className="-ml-2" onClick={() => actions.onView(item)}><FileText /> View full JD</Button>
          <Button size="sm" className="ml-auto px-4" onClick={() => actions.onApply(item)} disabled={disabled || !j.job_url}>
            <Send /> {applied ? "View" : item.application_id ? "Continue" : "Apply"}
          </Button>
          {!applied && (
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button size="icon-sm" variant="ghost" aria-label="More actions" className="text-muted-foreground" />}><MoreHorizontal /></DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-44">
                <DropdownMenuItem onClick={() => actions.onDismiss(item)} disabled={disabled}>{dismissed ? <><Undo2 /> Restore</> : <><EyeOff /> Not for me (dismiss)</>}</DropdownMenuItem>
                {j.job_url && <DropdownMenuItem onClick={() => window.open(j.job_url!, "_blank", "noopener,noreferrer")}><FileText /> Open original listing</DropdownMenuItem>}
                {(item.similar?.length ?? 0) > 0 && actions.onViewId && item.similar!.slice(0, 4).map((s) => (
                  <DropdownMenuItem key={s.user_job_id} onClick={() => actions.onViewId?.(s.user_job_id)}><Copy /> Also in {s.location || "another location"}</DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    </article>
  );
}
