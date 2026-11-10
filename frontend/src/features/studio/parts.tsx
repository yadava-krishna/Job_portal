import type { ReactNode } from "react";
import { AlertTriangle, Lock, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/app/common";
import { cn } from "@/lib/utils";
import { useJobs } from "@/services/queries";
import type { StudioTemplate, TemplateKey, VersionStatus } from "./api";

export function VersionStatusBadge({ status }: { status: VersionStatus }) {
  if (status === "locked") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200">
        <Lock className="size-3" /> Locked — used in an application
      </span>
    );
  }
  if (status === "archived") return <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">Archived</span>;
  return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-200">Draft</span>;
}

export function AtsBadge({ safe }: { safe: boolean }) {
  return safe ? (
    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-800 ring-1 ring-inset ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-200 dark:ring-emerald-900">
      <ShieldCheck className="size-3" /> ATS-safe
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-inset ring-amber-200 dark:bg-amber-950/40 dark:text-amber-200 dark:ring-amber-900">
      Two-column
    </span>
  );
}

/** Template cards as a radio group (keyboard: Tab to the group, click/Enter/Space on a card). */
export function TemplatePicker({ templates, value, onChange, disabled, compact }: {
  templates: StudioTemplate[]; value: TemplateKey; onChange: (k: TemplateKey) => void; disabled?: boolean; compact?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label="Template" className={cn("grid gap-2", compact ? "sm:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-3")}>
      {templates.map((t) => {
        const on = t.key === value;
        return (
          <button key={t.key} type="button" role="radio" aria-checked={on} disabled={disabled} onClick={() => onChange(t.key)}
                  className={cn("rounded-lg border p-2.5 text-left text-sm outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60",
                    on ? "border-primary bg-primary/5 ring-1 ring-primary" : "hover:bg-muted/50")}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">{t.name}</span>
              <AtsBadge safe={t.ats_safe} />
            </div>
            <p className="mt-1 text-xs leading-snug text-muted-foreground">{t.description}</p>
            {!compact && <p className="mt-1 text-[11px] text-muted-foreground">{t.columns === 1 ? "Single column" : `${t.columns} columns`} · up to {t.max_pages} page{t.max_pages > 1 ? "s" : ""}</p>}
          </button>
        );
      })}
    </div>
  );
}

/** Pick one of the user's jobs (value is the user_job_id). */
export function JobPicker({ value, onChange, id, emptyLabel = "No specific job", className }: {
  value: number | null; onChange: (v: number | null) => void; id?: string; emptyLabel?: string; className?: string;
}) {
  const jobs = useJobs({ view: "all", sort: "score", page_size: 100 });
  const items = Array.isArray(jobs.data?.items) ? jobs.data.items : [];
  const options = [{ value: "", label: emptyLabel },
    ...items.map((j) => ({ value: String(j.user_job_id), label: `${j.job.title} — ${j.job.company}` }))];
  if (value != null && !items.some((j) => j.user_job_id === value)) options.push({ value: String(value), label: `Job #${value}` });
  return <NativeSelect id={id} value={value == null ? "" : String(value)} onChange={(v) => onChange(v ? Number(v) : null)} options={options} className={cn("w-full", className)} />;
}

export function ConfirmDialog({ open, title, children, confirmLabel = "Delete", onConfirm, onCancel, busy }: {
  open: boolean; title: string; children?: ReactNode; confirmLabel?: string; onConfirm: () => void; onCancel: () => void; busy?: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><AlertTriangle className="size-5 text-amber-600" /> {title}</DialogTitle>
          {children && <DialogDescription>{children}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
