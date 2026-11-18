import { useState, type KeyboardEvent, type ReactNode } from "react";
import { AlertTriangle, Loader2, RotateCw, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/lib/api";
import { scoreTone, statusLabels, stageLabels, toneClasses, toneStroke } from "@/lib/format";

export function ScoreRing({ score, size = 52, label = true }: { score: number | null | undefined; size?: number; label?: boolean }) {
  const tone = scoreTone(score);
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  const pct = score == null ? 0 : Math.max(0, Math.min(100, score));
  return (
    <div className="relative inline-flex shrink-0 items-center justify-center" style={{ width: size, height: size }}
         aria-label={score == null ? "Not scored" : `Match ${pct.toFixed(0)} percent`} role="img">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} className="stroke-muted fill-none" strokeWidth={4} />
        <circle cx={size / 2} cy={size / 2} r={r} className={cn("fill-none transition-all", toneStroke[tone])} strokeWidth={4}
                strokeDasharray={c} strokeDashoffset={c - (pct / 100) * c} strokeLinecap="round" />
      </svg>
      {label && <span className="absolute text-sm font-semibold tabular-nums">{score == null ? "–" : Math.round(pct)}</span>}
    </div>
  );
}

export function ScoreBadge({ score, category }: { score: number | null | undefined; category?: string | null }) {
  const tone = scoreTone(score);
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", toneClasses[tone])}>
      {score == null ? "Not scored" : `${Math.round(score)}%`}
      {category && <span className="hidden sm:inline">· {category.replace(" match", "")}</span>}
    </span>
  );
}

/** Job sources are labels, not outcomes: one neutral style, so no source ever reads as "success" or "error". */
const platformColors: Record<string, string> = {};

export function PlatformBadge({ platform }: { platform: string }) {
  return <span className={cn("rounded-full px-2 py-px text-[11px] font-medium ring-1 ring-inset", platformColors[platform] ?? "bg-paper-sunk text-muted-foreground ring-border")}>{platform}</span>;
}

const statusTone: Record<string, string> = {
  PREPARED: "bg-paper-sunk text-heading",
  OPENED: "bg-caution-tint text-caution",
  CONFIRMATION_PENDING: "bg-caution-tint text-caution",
  SUBMITTED: "bg-success-tint text-success",
  FAILED: "bg-destructive/10 text-destructive",
  WITHDRAWN: "bg-muted text-muted-foreground",
};

export function StatusBadge({ status }: { status: string }) {
  return <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", statusTone[status] ?? "bg-muted")}>{statusLabels[status] ?? status}</span>;
}

export function StageBadge({ stage }: { stage: string | null }) {
  if (!stage) return null;
  return <Badge variant="outline" className="capitalize">{stageLabels[stage] ?? stage}</Badge>;
}

export function SkillChips({ skills, tone, max = 6 }: { skills: string[]; tone: "match" | "missing" | "neutral"; max?: number }) {
  if (!skills.length) return null;
  const cls = tone === "match"
    ? "bg-route-tint text-route ring-route/20"
    : tone === "missing"
      ? "bg-caution-tint text-caution ring-caution/20"
      : "bg-muted text-foreground ring-border";
  return (
    <div className="flex flex-wrap gap-1.5">
      {skills.slice(0, max).map((s) => (
        <span key={s} className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", cls)}>{s}</span>
      ))}
      {skills.length > max && <span className="text-xs text-muted-foreground">+{skills.length - max}</span>}
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex animate-in flex-col items-center justify-center rounded-2xl border border-dashed bg-card/60 px-6 py-12 text-center duration-300 fade-in-0">
      {icon && <div className="mb-3 flex size-12 items-center justify-center rounded-2xl bg-lavender text-violet [&_svg]:size-6">{icon}</div>}
      <h3 className="font-display text-[17px] font-bold text-heading">{title}</h3>
      {children && <div className="mt-1 max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

/** Shared loading state: announced to screen readers, same look on every page. */
export function LoadingState({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div role="status" aria-live="polite" className={cn("flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

/** Shared error state: says what failed, why (from the server when it said), and offers a retry. */
export function ErrorState({ title = "This couldn't be loaded", error, onRetry, className }: {
  title?: string; error?: unknown; onRetry?: () => void; className?: string;
}) {
  return (
    <div role="alert" className={cn("flex flex-col items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm", className)}>
      <div className="flex items-center gap-2 font-medium text-destructive"><AlertTriangle className="size-4" aria-hidden /> {title}</div>
      {error != null && <p className="text-muted-foreground">{errorMessage(error)}</p>}
      {onRetry && <Button size="sm" variant="outline" onClick={onRetry}><RotateCw aria-hidden /> Try again</Button>}
    </div>
  );
}

export function PageHeader({ title, description, actions, eyebrow }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mt-1 mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="eyebrow mb-1.5">{eyebrow}</div>}
        <h1 className="font-display text-[26px] leading-[1.15] font-extrabold tracking-[-0.03em] sm:text-[30px]">{title}</h1>
        {description && <div className="mt-1 max-w-3xl text-[14px] leading-relaxed text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

/** Free-text tag input: Enter or comma adds, Backspace removes the last tag. */
export function TagInput({ value, onChange, placeholder, suggestions = [], id }: {
  value: string[]; onChange: (v: string[]) => void; placeholder?: string; suggestions?: string[]; id?: string;
}) {
  const [draft, setDraft] = useState("");
  const add = (raw: string) => {
    const items = raw.split(",").map((s) => s.trim()).filter(Boolean);
    const next = [...value];
    for (const it of items) if (!next.some((v) => v.toLowerCase() === it.toLowerCase())) next.push(it);
    onChange(next);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      if (draft.trim()) add(draft);
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };
  const unused = suggestions.filter((s) => !value.some((v) => v.toLowerCase() === s.toLowerCase())).slice(0, 8);
  return (
    <div className="space-y-2">
      <div data-guard-value={JSON.stringify(value)} className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-lg border bg-background px-2 py-1.5 focus-within:ring-3 focus-within:ring-ring/50">
        {value.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-0.5 text-sm">
            {v}
            <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(value.filter((x) => x !== v))} className="text-muted-foreground hover:text-foreground">
              <X className="size-3" />
            </button>
          </span>
        ))}
        <Input id={id} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey} onBlur={() => draft.trim() && add(draft)}
               placeholder={value.length ? "" : placeholder} className="h-7 min-w-32 flex-1 border-0 px-1 shadow-none focus-visible:ring-0" />
      </div>
      {unused.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {unused.map((s) => (
            <button key={s} type="button" onClick={() => add(s)} className="rounded-md border border-dashed px-2 py-0.5 text-xs text-muted-foreground hover:border-solid hover:text-foreground">
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Field({ label, htmlFor, hint, children, className }: { label: string; htmlFor?: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="text-sm font-medium">{label}</label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function NativeSelect({ value, onChange, options, id, className, ariaLabel }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; id?: string; className?: string; ariaLabel?: string;
}) {
  return (
    <select id={id} aria-label={ariaLabel} value={value} onChange={(e) => onChange(e.target.value)}
            className={cn("h-10 rounded-xl border bg-card px-3 text-sm outline-none transition-colors hover:border-foreground/25 focus-visible:ring-3 focus-visible:ring-ring/50", className)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
