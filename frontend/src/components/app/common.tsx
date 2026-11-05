import { useState, type KeyboardEvent, type ReactNode } from "react";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
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

const platformColors: Record<string, string> = {
  LinkedIn: "bg-[#0a66c2]/10 text-[#0a66c2] dark:text-sky-300",
  Indeed: "bg-[#2557a7]/10 text-[#2557a7] dark:text-blue-300",
  Naukri: "bg-[#4a90e2]/10 text-[#275df5] dark:text-blue-300",
  Adzuna: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  Greenhouse: "bg-lime-500/10 text-lime-800 dark:text-lime-300",
  Lever: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
  Ashby: "bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300",
  SmartRecruiters: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  Recruitee: "bg-orange-500/10 text-orange-700 dark:text-orange-300",
};

export function PlatformBadge({ platform }: { platform: string }) {
  return <span className={cn("rounded-md px-1.5 py-0.5 text-xs font-medium", platformColors[platform] ?? "bg-muted text-muted-foreground")}>{platform}</span>;
}

const statusTone: Record<string, string> = {
  PREPARED: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200",
  OPENED: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  CONFIRMATION_PENDING: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200",
  SUBMITTED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  FAILED: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  WITHDRAWN: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
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
    ? "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:ring-emerald-900"
    : tone === "missing"
      ? "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900"
      : "bg-muted text-foreground ring-border";
  return (
    <div className="flex flex-wrap gap-1">
      {skills.slice(0, max).map((s) => (
        <span key={s} className={cn("rounded-md px-1.5 py-0.5 text-xs ring-1 ring-inset", cls)}>{s}</span>
      ))}
      {skills.length > max && <span className="text-xs text-muted-foreground">+{skills.length - max}</span>}
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-14 text-center">
      {icon && <div className="mb-3 text-muted-foreground">{icon}</div>}
      <h3 className="font-medium">{title}</h3>
      {children && <div className="mt-1 max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
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
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-lg border bg-background px-2 py-1.5 focus-within:ring-3 focus-within:ring-ring/50">
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
            className={cn("h-8 rounded-lg border bg-background px-2 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50", className)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
