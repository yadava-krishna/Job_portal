import { Bookmark, BookmarkCheck, Briefcase, CalendarDays, EyeOff, FileText, IndianRupee, MapPin, Send, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PlatformBadge, ScoreRing, SkillChips, StatusBadge } from "@/components/app/common";
import { cn } from "@/lib/utils";
import type { UserJob } from "@/types/api";

export interface JobCardActions {
  onView: (j: UserJob) => void;
  onSave: (j: UserJob) => void;
  onApply: (j: UserJob) => void;
  onDismiss: (j: UserJob) => void;
}

export function JobCard({ item, active, actions, disabled }: { item: UserJob; active?: boolean; actions: JobCardActions; disabled?: boolean }) {
  const j = item.job;
  const dismissed = item.status === "dismissed";
  const applied = item.status === "applied";
  return (
    <Card className={cn("gap-3 p-4 transition-shadow hover:shadow-md", active && "ring-2 ring-primary")} data-active={active || undefined}>
      <div className="flex items-start gap-3">
        <ScoreRing score={item.match_score} />
        <div className="min-w-0 flex-1">
          <button type="button" onClick={() => actions.onView(item)} className="text-left">
            <h3 className="line-clamp-2 font-semibold leading-snug hover:underline">{j.title || "Untitled role"}</h3>
          </button>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{j.company || "Unknown company"}</span>
            <PlatformBadge platform={j.platform} />
            {item.application_status && <StatusBadge status={item.application_status} />}
            {item.eligibility_status === "INELIGIBLE" && <span className="rounded bg-rose-100 px-1.5 py-0.5 text-xs text-rose-800 dark:bg-rose-950 dark:text-rose-200">Not eligible</span>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm text-muted-foreground sm:grid-cols-2">
        <span className="flex items-center gap-1.5"><MapPin className="size-3.5" />{j.location || "Location not stated"}{j.work_mode ? ` · ${j.work_mode}` : ""}</span>
        <span className="flex items-center gap-1.5" title={j.posted_at_source ?? "unknown"}><CalendarDays className="size-3.5" />{j.posted_label}</span>
        <span className="flex items-center gap-1.5"><Briefcase className="size-3.5" />{j.experience_required || "Experience not stated"}</span>
        <span className="flex items-center gap-1.5"><IndianRupee className="size-3.5" />{j.salary_range || "Salary not disclosed"}</span>
      </div>

      {(item.matching_skills.length > 0 || item.missing_skills.length > 0) && (
        <div className="space-y-1.5">
          <SkillChips skills={item.matching_skills} tone="match" max={5} />
          <SkillChips skills={item.missing_skills} tone="missing" max={4} />
        </div>
      )}

      {j.description_preview
        ? <p className="line-clamp-3 text-sm text-muted-foreground">{j.description_preview}</p>
        : <p className="text-sm italic text-muted-foreground">No description yet. Open the job to paste it for an accurate score.</p>}

      <div className="flex flex-wrap gap-2 pt-1">
        <Button size="sm" variant="outline" onClick={() => actions.onView(item)}><FileText /> View full JD</Button>
        <Button size="sm" variant="outline" onClick={() => actions.onSave(item)} disabled={disabled} aria-pressed={item.is_saved}>
          {item.is_saved ? <BookmarkCheck className="text-primary" /> : <Bookmark />} {item.is_saved ? "Saved" : "Save"}
        </Button>
        <Button size="sm" onClick={() => actions.onApply(item)} disabled={disabled || !j.job_url}>
          <Send /> {applied ? "View application" : item.application_id ? "Continue" : "Apply"}
        </Button>
        {!applied && (
          <Button size="sm" variant="ghost" onClick={() => actions.onDismiss(item)} disabled={disabled}>
            {dismissed ? <><Undo2 /> Restore</> : <><EyeOff /> Dismiss</>}
          </Button>
        )}
      </div>
    </Card>
  );
}
