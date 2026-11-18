import { useState, type ReactNode } from "react";
import { AlertTriangle, Check, Columns2, Lock, Rows3, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/app/common";
import { cn } from "@/lib/utils";
import { useJobs } from "@/services/queries";
import type { StudioTemplate, TemplateKey, VersionStatus } from "./api";
import { FORM_FRIENDLY_HELP, PRINT_FIRST_HELP, templateDescription, templateName } from "./templateCopy";

export function VersionStatusBadge({ status }: { status: VersionStatus }) {
  if (status === "locked") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-caution-tint px-2 py-0.5 text-xs font-medium text-caution">
        <Lock className="size-3" /> Locked — used in an application
      </span>
    );
  }
  if (status === "archived") return <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">Archived</span>;
  return <span className="rounded-full bg-paper-sunk px-2 py-0.5 text-xs font-medium text-heading ring-1 ring-inset ring-border">Draft</span>;
}

export function AtsBadge({ safe }: { safe: boolean }) {
  return safe ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-route-tint px-2 py-0.5 text-[11px] font-medium text-route" title={FORM_FRIENDLY_HELP}>
      <ShieldCheck className="size-3" aria-hidden /> Safe for online forms
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-caution-tint px-2 py-0.5 text-[11px] font-medium text-caution" title={PRINT_FIRST_HELP}>
      Best for email &amp; print
    </span>
  );
}

/** Template cards as a radio group (keyboard: Tab to the group, click/Enter/Space on a card). The chosen card gets a
 *  ring and a one-shot check-mark pop so the switch registers before the preview re-renders. */
export function TemplatePicker({ templates, value, onChange, disabled, compact }: {
  templates: StudioTemplate[]; value: TemplateKey; onChange: (k: TemplateKey) => void; disabled?: boolean; compact?: boolean;
}) {
  const [bump, setBump] = useState(0);
  return (
    <div role="radiogroup" aria-label="Template" className={cn("grid gap-2", compact ? "sm:grid-cols-2" : "sm:grid-cols-2 lg:grid-cols-3")}>
      {templates.map((t) => {
        const on = t.key === value;
        const Cols = t.columns === 1 ? Rows3 : Columns2;
        return (
          <button key={t.key} type="button" role="radio" aria-checked={on} disabled={disabled}
                  onClick={() => { if (!on) setBump((n) => n + 1); onChange(t.key); }}
                  className={cn("group/tpl relative rounded-xl bg-card p-3 text-left text-sm outline-none ring-1 transition-[box-shadow,background-color] duration-200 ease-[cubic-bezier(.2,0,0,1)] focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60",
                    on ? "bg-lavender/40 ring-2 ring-violet/70 dark:bg-lavender/10" : "ring-border hover:ring-route/30 hover:shadow-[var(--shadow-raised)]")}>
            <div className="flex items-start gap-2.5">
              <span aria-hidden className={cn("mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors duration-200",
                on ? "bg-violet text-white" : "bg-paper-sunk text-muted-foreground group-hover/tpl:text-route")}>
                {on ? <Check key={bump} className={cn("size-4", bump > 0 && "jp-bump")} /> : <Cols className="size-4" />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                  <span className={cn("font-medium", on && "text-heading")}>{templateName(t.key, t.name)}</span>
                  <AtsBadge safe={t.ats_safe} />
                </div>
                <p className="mt-1 text-xs leading-snug text-muted-foreground">{templateDescription(t)}</p>
                {!compact && <p className="readout mt-1.5 text-[11px] text-muted-foreground">{t.columns === 1 ? "Single column" : `${t.columns} columns`} · up to {t.max_pages} page{t.max_pages > 1 ? "s" : ""}</p>}
              </div>
            </div>
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
          <DialogTitle className="flex items-center gap-2"><AlertTriangle className="size-5 text-caution" /> {title}</DialogTitle>
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
