import { formatDate, stageLabels } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ApplicationDetail } from "@/types/api";
import { APPLY_STATE_LABELS } from "./events";

type Tone = "done" | "current" | "upcoming" | "success" | "warn" | "stop";
interface Waypoint { key: string; label: string; at?: string | null; note?: string | null; tone: Tone; sub?: { label: string; at: string; current: boolean; warn: boolean }[] }

const FORWARD = ["screening", "assessment", "interview", "offer"] as const;
const CONFIRM_SOURCE: Record<string, string> = { user_confirmed: "You confirmed it", extension: "Confirmed by Smart Apply", email: "Found in a confirmation email" };

/** The application's route: prepared → opened (with Smart Apply progress) → submitted → each stage reached. */
function journeyOf(d: ApplicationDetail): Waypoint[] {
  const events = [...d.events].sort((a, b) => a.created_at.localeCompare(b.created_at));
  const lastAt = (pred: (e: (typeof events)[number]) => boolean) => [...events].reverse().find(pred)?.created_at ?? null;
  const submitted = d.status === "SUBMITTED" || !!d.submitted_at;
  const opened = !!d.opened_at || d.status !== "PREPARED";
  const smart = events.filter((e) => e.event_type === "APPLY_STATE" && e.to_status);
  const pts: Waypoint[] = [];

  pts.push({ key: "prepared", label: "Package prepared", at: d.created_at, tone: "done", note: d.resume_used ? `Resume: ${d.resume_used}` : null });
  pts.push({
    key: "opened", label: "Employer form opened", at: d.opened_at ?? lastAt((e) => e.event_type === "OPENED_EXTERNAL"), tone: opened ? "done" : "upcoming",
    sub: smart.map((e, i) => ({ label: APPLY_STATE_LABELS[e.to_status!] ?? e.to_status!, at: e.created_at,
      current: !submitted && i === smart.length - 1, warn: e.to_status === "submission_uncertain" || e.to_status === "needs_information" || e.to_status === "failed" })),
  });

  if (d.status === "FAILED") pts.push({ key: "failed", label: "Marked as failed", at: lastAt((e) => e.to_status === "FAILED"), tone: "stop" });
  else if (d.status === "WITHDRAWN" && !submitted) pts.push({ key: "withdrawn", label: "Withdrawn", at: lastAt((e) => e.to_status === "WITHDRAWN"), tone: "stop" });
  else if (d.status === "CONFIRMATION_PENDING") pts.push({ key: "submitted", label: "Did you submit it?", note: "Waiting for you to confirm", tone: "warn" });
  else pts.push({
    key: "submitted", label: submitted ? "Submitted" : "Submit on the employer's form", at: d.submitted_at, tone: submitted ? "success" : "upcoming",
    note: submitted ? [CONFIRM_SOURCE[d.confirmation_source ?? ""], d.reference_id ? `Ref ${d.reference_id}` : null].filter(Boolean).join(" · ") || null : null,
  });

  if (submitted) {
    const stage = d.stage ?? "applied";
    const reachedIdx = FORWARD.indexOf(stage as (typeof FORWARD)[number]);
    const stageAt = (s: string) => lastAt((e) => e.event_type === "STAGE_CHANGED" && e.to_status === s);
    const ended = stage === "rejected" || stage === "withdrawn" || stage === "archived" || d.status === "WITHDRAWN";
    FORWARD.forEach((s, i) => {
      const at = stageAt(s);
      const reached = i <= reachedIdx || (ended && !!at);
      if (ended && !reached) return;
      if (s === "assessment" && !at && stage !== "assessment") return;  // optional step: only shown once it happened
      pts.push({ key: s, label: stageLabels[s], at, tone: reached ? (s === "offer" ? "success" : "done") : "upcoming" });
    });
    if (ended) {
      const s = d.status === "WITHDRAWN" ? "withdrawn" : stage;
      pts.push({ key: s, label: stageLabels[s], at: stageAt(s) ?? lastAt((e) => e.to_status === "WITHDRAWN"), tone: "stop" });
    }
  }

  // The last waypoint that happened is where the application stands now.
  let cur = -1;
  pts.forEach((p, i) => { if (p.tone !== "upcoming") cur = i; });
  if (cur >= 0 && pts[cur].tone === "done") pts[cur] = { ...pts[cur], tone: "current" };
  return pts;
}

const dot: Record<Tone, string> = {
  done: "size-2.5 bg-route",
  current: "size-3.5 bg-route ring-4 ring-route/20",
  upcoming: "size-2.5 bg-card ring-1 ring-border",
  success: "size-3 bg-success ring-4 ring-success/15",
  warn: "size-3 bg-caution ring-4 ring-caution/20",
  stop: "size-3 bg-destructive/80 ring-4 ring-destructive/15",
};

export function JourneyTimeline({ app }: { app: ApplicationDetail }) {
  const pts = journeyOf(app);
  return (
    <ol className="relative" aria-label="Application timeline" data-testid="application-journey">
      {pts.map((p, i) => {
        const next = pts[i + 1];
        const solid = next && next.tone !== "upcoming";
        const strong = p.tone === "current" || p.tone === "success" || p.tone === "warn" || p.tone === "stop";
        return (
          <li key={p.key} className="relative pb-4 pl-7 last:pb-0" aria-current={p.tone === "current" ? "step" : undefined}>
            {next && <span aria-hidden className={cn("absolute top-3.5 bottom-0 left-[8.5px] w-0 border-l-2", solid ? "border-route" : "border-dashed border-border")} />}
            <span aria-hidden className="absolute top-1 left-0 flex size-[19px] items-center justify-center">
              <span className={cn("rounded-full transition-[transform,background-color] duration-300 ease-[cubic-bezier(.2,0,0,1)]", dot[p.tone])} />
            </span>
            <div className={cn("text-[13px] leading-snug", strong ? "font-semibold text-heading" : p.tone === "upcoming" ? "text-muted-foreground" : "font-medium text-foreground",
              p.tone === "success" && "text-success", p.tone === "warn" && "text-caution", p.tone === "stop" && "text-destructive")}>{p.label}</div>
            {p.at && <div className="readout text-[11.5px] text-muted-foreground">{formatDate(p.at, true)}</div>}
            {p.note && <div className="text-[11.5px] text-muted-foreground">{p.note}</div>}
            {!!p.sub?.length && (
              <ul className="mt-1.5 space-y-1 rounded-lg bg-card px-2.5 py-2 ring-1 ring-border" aria-label="Smart Apply progress">
                <li className="eyebrow text-[10px]">Smart Apply</li>
                {p.sub.map((s, j) => (
                  <li key={j} className={cn("flex items-baseline gap-1.5 text-[12px]", s.current ? "font-semibold text-heading" : "text-muted-foreground")}>
                    <span aria-hidden className={cn("size-1.5 shrink-0 translate-y-[-1px] rounded-full", s.warn ? "bg-caution" : s.current ? "bg-route" : "bg-route/40")} />
                    <span className={cn("min-w-0 flex-1", s.warn && "text-caution")}>{s.label}</span>
                    <span className="readout shrink-0 text-[10.5px] font-normal">{new Date(s.at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</span>
                  </li>
                ))}
              </ul>
            )}
          </li>
        );
      })}
    </ol>
  );
}
