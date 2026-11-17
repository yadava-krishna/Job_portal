import { useState, type ReactNode } from "react";
import { AlertCircle, AlertTriangle, ArrowRight, Check, CircleHelp, GitBranch, Info, Lightbulb, Loader2, RefreshCw, RotateCcw, X } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, LoadingState, NativeSelect } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  useStudioFeedback, useStudioSuggestions, useStudioTemplates, useStudioVersions,
  type DateFormat, type FeedbackIssue, type IssueLevel, type HeadingStyle, type PageSize, type Section, type StudioSettings, type Suggestion, type TemplateKey, type Version, type VersionSummary,
} from "./api";
import { JobPicker, TemplatePicker, VersionStatusBadge } from "./parts";

// ---------------- design: template + layout settings ----------------

const FONT_SIZES = [9, 9.5, 10, 10.5, 11, 11.5, 12];
const LINE_HEIGHTS = [1.15, 1.2, 1.25, 1.3, 1.4, 1.5];
const MARGINS = [12, 13, 14, 16, 18, 20, 22];
const SPACINGS: { value: number; label: string }[] = [
  { value: 0.75, label: "Compact" }, { value: 0.9, label: "Snug" }, { value: 1, label: "Normal" }, { value: 1.25, label: "Relaxed" }, { value: 1.5, label: "Airy" },
];
const HEADING_LABELS: Record<HeadingStyle, string> = {
  caps_rule: "Capitals with a line", accent: "Coloured", underline: "Capitals, coloured line", plain: "Plain bold", label_left: "In the left margin",
};
const ACCENTS = ["#111827", "#1e3a5f", "#1d4ed8", "#0f766e", "#6d28d9", "#7f1d1d", "#7c2d12"];

export function DesignPanel({ templateKey, settings, readOnly, onTemplate, onSettings }: {
  templateKey: TemplateKey; settings: StudioSettings; readOnly: boolean;
  onTemplate: (k: TemplateKey) => void; onSettings: (s: StudioSettings) => void;
}) {
  const templates = useStudioTemplates();
  const list = Array.isArray(templates.data) ? templates.data : [];
  const tpl = list.find((t) => t.key === templateKey);
  const d = tpl?.defaults ?? {};
  const v = <K extends keyof StudioSettings>(k: K): StudioSettings[K] => (settings[k] ?? d[k]) as StudioSettings[K];
  const set = (patch: Partial<StudioSettings>) => onSettings({ ...settings, ...patch });
  const minSize = tpl?.ats_safe ? 9.5 : 9;
  const nearest = (list: number[], x: number) => list.reduce((a, b) => (Math.abs(b - x) < Math.abs(a - x) ? b : a));
  return (
    <fieldset disabled={readOnly} className="min-w-0 space-y-5">
      <legend className="sr-only">Design</legend>
      <div className="space-y-1.5">
        <span className="text-sm font-medium">Template</span>
        <p className="text-xs text-muted-foreground">Switching template keeps all your content. Fonts, colour and headings reset to the new template's defaults.</p>
        {templates.isLoading ? <LoadingState /> : <TemplatePicker templates={list} value={templateKey} onChange={onTemplate} disabled={readOnly} compact />}
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-medium">Text</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Font" htmlFor="st-family" className="sm:col-span-3">
            <NativeSelect id="st-family" className="w-full" value={String(v("font_family") ?? "")} onChange={(x) => set({ font_family: x })}
                          options={(tpl?.fonts ?? []).map((f) => ({ value: f.key, label: f.label }))} />
          </Field>
          <Field label="Size" htmlFor="st-font">
            <NativeSelect id="st-font" className="w-full" value={String(nearest(FONT_SIZES, Number(v("font_size") ?? 10.5)))} onChange={(x) => set({ font_size: Number(x) })}
                          options={FONT_SIZES.filter((f) => f >= minSize).map((f) => ({ value: String(f), label: `${f} pt` }))} />
          </Field>
          <Field label="Line spacing" htmlFor="st-lh">
            <NativeSelect id="st-lh" className="w-full" value={String(nearest(LINE_HEIGHTS, Number(v("line_height") ?? 1.3)))} onChange={(x) => set({ line_height: Number(x) })}
                          options={LINE_HEIGHTS.map((f) => ({ value: String(f), label: f.toFixed(2) }))} />
          </Field>
          <Field label="Dates" htmlFor="st-date">
            <NativeSelect id="st-date" className="w-full" value={String(v("date_format") ?? "MMM YYYY")} onChange={(x) => set({ date_format: x as DateFormat })}
                          options={(tpl?.date_formats ?? ["MMM YYYY", "MM/YYYY", "YYYY"]).map((f) => ({ value: f, label: f === "MMM YYYY" ? "Jan 2024" : f === "MM/YYYY" ? "01/2024" : "2024" }))} />
          </Field>
        </div>
        {tpl?.ats_safe && <p className="text-xs text-muted-foreground">ATS-friendly template: text stays at {minSize} pt or larger and fonts are limited to ones applicant-tracking systems read reliably.</p>}
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-medium">Page</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Page size" htmlFor="st-page">
            <NativeSelect id="st-page" className="w-full" value={String(v("page_size") ?? "A4")} onChange={(x) => set({ page_size: x as PageSize })}
                          options={[{ value: "A4", label: "A4" }, { value: "LETTER", label: "US Letter" }]} />
          </Field>
          <Field label="Margins" htmlFor="st-margin">
            <NativeSelect id="st-margin" className="w-full" value={String(nearest(MARGINS, Number(v("margin_mm") ?? 16)))} onChange={(x) => set({ margin_mm: Number(x) })}
                          options={MARGINS.map((m) => ({ value: String(m), label: `${m} mm` }))} />
          </Field>
          <Field label="Section spacing" htmlFor="st-spacing">
            <NativeSelect id="st-spacing" className="w-full" value={String(nearest(SPACINGS.map((x) => x.value), Number(v("section_spacing") ?? 1)))}
                          onChange={(x) => set({ section_spacing: Number(x) })} options={SPACINGS.map((x) => ({ value: String(x.value), label: x.label }))} />
          </Field>
        </div>
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-medium">Style</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Section headings" htmlFor="st-heading">
            <NativeSelect id="st-heading" className="w-full" value={String(v("heading_style") ?? "caps_rule")} onChange={(x) => set({ heading_style: x as HeadingStyle })}
                          options={(tpl?.heading_styles ?? ["caps_rule", "accent", "underline", "plain"]).map((h) => ({ value: h, label: HEADING_LABELS[h] }))} />
          </Field>
          <div className="space-y-1.5">
            <span className="text-sm font-medium" id="st-accent-label">Accent colour</span>
            <div className="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-labelledby="st-accent-label">
              {ACCENTS.map((c) => (
                <button key={c} type="button" role="radio" aria-checked={v("accent") === c} aria-label={`Accent ${c}`} onClick={() => set({ accent: c })}
                        className={cn("size-6 rounded-full border-2 border-background ring-1 ring-border", v("accent") === c && "ring-2 ring-primary")} style={{ background: c }} />
              ))}
              <input type="color" aria-label="Custom accent colour" value={String(v("accent") ?? "#111827")} onChange={(e) => set({ accent: e.target.value })}
                     className="h-6 w-8 cursor-pointer rounded border bg-transparent" />
            </div>
            <p className="text-xs text-muted-foreground">Colours too light to read on white are not used.</p>
          </div>
        </div>
        <Button size="xs" variant="ghost" onClick={() => onSettings({ page_size: settings.page_size, mobility_line: settings.mobility_line })}>
          <RotateCcw /> Reset to template defaults
        </Button>
      </div>

      {templateKey === "international" && (
        <Field label="Work authorisation / relocation line (optional)" htmlFor="st-mobility" hint="Shown under your contact details, e.g. “EU Blue Card eligible · open to relocate to Germany”. Only add what is true.">
          <Input id="st-mobility" maxLength={200} value={settings.mobility_line ?? ""} onChange={(e) => set({ mobility_line: e.target.value })} />
        </Field>
      )}
    </fieldset>
  );
}

// ---------------- check (feedback) ----------------

const KIND_HELP: Record<string, string> = {
  format: "Objective check: contact details, dates, duplicates, characters, page layout and whether the exported PDF reads back correctly.",
  accuracy: "A figure that isn't in your confirmed profile. Keep only what you can back up.",
  writing: "Style advice. A matter of judgement, not a rule.",
  job: "How this resume covers the selected job's listed skills.",
};

const levelMeta: Record<IssueLevel, { label: string; icon: ReactNode; cls: string }> = {
  error: { label: "Must fix", icon: <AlertCircle className="size-4 text-rose-600" />, cls: "text-rose-700 dark:text-rose-300" },
  warning: { label: "Worth fixing", icon: <AlertTriangle className="size-4 text-amber-600" />, cls: "text-amber-800 dark:text-amber-300" },
  suggestion: { label: "Suggestions", icon: <Lightbulb className="size-4 text-sky-600" />, cls: "text-sky-800 dark:text-sky-300" },
  info: { label: "For your information", icon: <Info className="size-4 text-muted-foreground" />, cls: "text-muted-foreground" },
};

function whereLabel(w: FeedbackIssue["where"]): string | null {
  if (!w) return null;
  const parts = [w.section.charAt(0).toUpperCase() + w.section.slice(1)];
  if (w.block != null) parts.push(`item ${w.block + 1}`);
  if (w.bullet != null) parts.push(`bullet ${w.bullet + 1}`);
  return parts.join(" · ");
}

export function CheckPanel({ versionId, jobId, onJob, revision }: { versionId: number; jobId: number | null; onJob: (j: number | null) => void; revision: number }) {
  const fb = useStudioFeedback(versionId, jobId, true);
  const [checkedAt, setCheckedAt] = useState(revision);
  const outdated = fb.data && checkedAt !== revision;
  const recheck = () => { setCheckedAt(revision); void fb.refetch(); };
  const issues = fb.data?.issues ?? [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Check against a job (optional)" htmlFor="ck-job" className="min-w-56 flex-1">
          <JobPicker id="ck-job" value={jobId} onChange={onJob} emptyLabel="General check (no job)" />
        </Field>
        <Button size="sm" variant="outline" onClick={recheck} disabled={fb.isFetching}>
          {fb.isFetching ? <Loader2 className="animate-spin" /> : <RefreshCw />} Re-check
        </Button>
      </div>
      {fb.isLoading ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> Checking…</div>
        : fb.isError ? <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{errorMessage(fb.error, "Couldn't run the check")}</p>
          : fb.data && (
            <>
              {outdated && <p className="rounded-lg bg-muted p-2 text-xs">You've edited since this check. Re-check to update it.</p>}
              <div className="flex flex-wrap items-center gap-4 rounded-lg border p-3">
                <div>
                  <div className="text-2xl font-semibold tabular-nums">{fb.data.readiness}<span className="text-sm font-normal text-muted-foreground">/100</span></div>
                  <div className="text-xs text-muted-foreground">Checklist score</div>
                </div>
                <p className="max-w-sm flex-1 text-xs text-muted-foreground">
                  {fb.data.score_method ?? "How many of these layout and wording checks pass."} It is not a prediction of whether you'll be shortlisted or hired.
                </p>
                <div className="text-sm">{fb.data.pages != null ? `${fb.data.pages} page${fb.data.pages === 1 ? "" : "s"}` : "Pages unknown"}</div>
              </div>
              {!issues.length ? <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300"><Check className="size-4" /> No issues found.</p> : (
                (Object.keys(levelMeta) as IssueLevel[]).map((lvl) => {
                  const group = issues.filter((i) => i.level === lvl);
                  if (!group.length) return null;
                  return (
                    <section key={lvl} aria-label={levelMeta[lvl].label}>
                      <h3 className={cn("mb-1.5 flex items-center gap-1.5 text-sm font-semibold", levelMeta[lvl].cls)}>{levelMeta[lvl].icon} {levelMeta[lvl].label} ({group.length})</h3>
                      <ul className="divide-y rounded-lg border">
                        {group.map((i, n) => (
                          <li key={`${i.code}-${n}`} className="p-2 text-sm">
                            {i.kind && <span className={cn("mr-1.5 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                              i.kind === "format" ? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200" : i.kind === "accuracy" ? "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200"
                                : i.kind === "job" ? "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200" : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200")}
                              title={KIND_HELP[i.kind]}>{i.kind === "format" ? "Format" : i.kind === "accuracy" ? "Accuracy" : i.kind === "job" ? "Job" : "Writing"}</span>}
                            {i.message}
                            {whereLabel(i.where) && <span className="ml-1 text-xs text-muted-foreground">({whereLabel(i.where)})</span>}
                          </li>
                        ))}
                      </ul>
                    </section>
                  );
                })
              )}
              <p className="flex gap-1.5 text-xs text-muted-foreground"><CircleHelp className="mt-0.5 size-3.5 shrink-0" />{fb.data.note}</p>
            </>
          )}
    </div>
  );
}

// ---------------- suggestions (suggest-only) ----------------

function suggestionTarget(s: Suggestion, sections: Section[]): string {
  const sec = sections[s.where.section];
  if (!sec) return "";
  if (s.kind === "add_skill" || s.kind === "reorder_entries") return sec.heading;
  const b = sec.blocks[s.where.block];
  const title = b?.type === "entry" ? [b.content.title, b.content.organization].filter(Boolean).join(" — ") : "";
  return [sec.heading, title, s.where.bullet != null ? `bullet ${s.where.bullet + 1}` : ""].filter(Boolean).join(" · ");
}

export function SuggestionsPanel({ versionId, jobId, onJob, sections, readOnly, onAccept }: {
  versionId: number; jobId: number | null; onJob: (j: number | null) => void; sections: Section[]; readOnly: boolean;
  onAccept: (s: Suggestion) => boolean;
}) {
  const sug = useStudioSuggestions(versionId, jobId, true);
  const [handled, setHandled] = useState<Set<string>>(new Set());
  const list = (Array.isArray(sug.data) ? sug.data : []).filter((s) => !handled.has(s.id));
  const done = (id: string) => setHandled((h) => new Set(h).add(id));
  const refresh = () => { setHandled(new Set()); void sug.refetch(); };
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Suggestions use only facts already in your profile. Nothing changes unless you accept it.</p>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Tailor for a job (optional)" htmlFor="sg-job" className="min-w-56 flex-1">
          <JobPicker id="sg-job" value={jobId} onChange={onJob} emptyLabel="General suggestions (no job)" />
        </Field>
        <Button size="sm" variant="outline" onClick={refresh} disabled={sug.isFetching}>{sug.isFetching ? <Loader2 className="animate-spin" /> : <RefreshCw />} Refresh</Button>
      </div>
      {sug.isLoading ? <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> Looking for improvements…</div>
        : sug.isError ? <p className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{errorMessage(sug.error, "Couldn't load suggestions")}</p>
          : !list.length ? <p className="text-sm text-muted-foreground">No suggestions right now.{jobId == null && " Pick a job to get job-specific ones."}</p>
            : (
              <ul className="space-y-2">
                {list.map((s) => (
                  <li key={s.id} className="rounded-lg border p-2.5 text-sm" aria-label={`Suggestion: ${s.reason}`}>
                    <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                      <span className="font-medium">{s.kind === "rewrite" ? "Reword" : s.kind === "reorder" ? "Reorder bullets" : s.kind === "reorder_skills" ? "Reorder skills" : s.kind === "reorder_entries" ? "Reorder projects" : "Add skill"}</span>
                      <span className="text-muted-foreground">{suggestionTarget(s, sections)}</span>
                      <span className={cn("ml-auto rounded px-1.5 py-0.5 text-[11px] font-medium",
                        s.evidence === "supported" ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200" : "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200")}>
                        {s.evidence === "supported" ? "Backed by your profile" : "Not verified — check it's true"}
                      </span>
                    </div>
                    {s.kind === "rewrite" && (
                      <div className="grid items-center gap-1.5 sm:grid-cols-[1fr_auto_1fr]">
                        <p className="rounded bg-muted/60 p-1.5 text-muted-foreground line-through decoration-muted-foreground/40">{s.before}</p>
                        <ArrowRight className="hidden size-4 text-muted-foreground sm:block" aria-hidden />
                        <p className="rounded bg-emerald-50/60 p-1.5 dark:bg-emerald-950/30">{s.after}</p>
                      </div>
                    )}
                    {s.kind === "reorder" && (() => {
                      const b = sections[s.where.section]?.blocks[s.where.block];
                      const top = b && s.order?.length ? b.bullets[s.order[0]]?.text : null;
                      return top ? <p className="text-xs">Move to the top: <span className="italic">“{top}”</span></p> : null;
                    })()}
                    {s.kind === "add_skill" && <p>Add <span className="font-medium">{s.skill ?? s.after}</span> to your skills.</p>}
                    {s.kind === "reorder_skills" && <p className="text-xs">New order: <span className="font-medium">{s.after}</span>{(s.order?.length ?? 0) > 6 ? "…" : ""}</p>}
                    {s.kind === "reorder_entries" && (() => {
                      const b = sections[s.where.section]?.blocks[s.order?.[0] ?? -1];
                      const t = b?.type === "entry" ? b.content.title : null;
                      return t ? <p className="text-xs">Move to the top: <span className="font-medium">{t}</span></p> : null;
                    })()}
                    <p className="mt-1.5 text-xs text-muted-foreground">{s.reason}</p>
                    <div className="mt-2 flex justify-end gap-1.5">
                      <Button size="xs" variant="ghost" onClick={() => done(s.id)}><X /> Dismiss</Button>
                      <Button size="xs" disabled={readOnly} onClick={() => { if (onAccept(s)) done(s.id); }}><Check /> Accept</Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
    </div>
  );
}

// ---------------- history ----------------

export function HistoryPanel({ version, onRestore, restoring }: { version: Version; onRestore: (v: VersionSummary) => void; restoring: boolean }) {
  const versions = useStudioVersions();
  const all = Array.isArray(versions.data) ? versions.data : [];
  const byId = new Map(all.map((v) => [v.id, v]));
  const chain: VersionSummary[] = [];
  const seen = new Set<number>([version.id]);
  let pid = version.parent_id;
  while (pid != null && !seen.has(pid)) {
    seen.add(pid);
    const p = byId.get(pid);
    if (!p) break;
    chain.push(p);
    pid = p.parent_id;
  }
  const children = all.filter((v) => v.parent_id === version.id);
  const others = all.filter((v) => !seen.has(v.id) && v.parent_id !== version.id);

  const row = (v: VersionSummary, note?: string) => (
    <li key={v.id} className="flex flex-wrap items-center gap-2 p-2 text-sm">
      <div className="min-w-0 flex-1">
        <Link to={`/studio/${v.id}`} className="font-medium hover:underline">{v.name}</Link>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          {note && <span>{note} ·</span>}{v.template_name} · updated {timeAgo(v.updated_at)} <VersionStatusBadge status={v.status} />
        </div>
      </div>
      <Button size="xs" variant="outline" onClick={() => onRestore(v)} disabled={restoring}><RotateCcw /> Restore as new copy</Button>
    </li>
  );

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">Older versions are never changed. Restoring makes a new editable copy of that version.</p>
      <section aria-label="This version's history">
        <h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold"><GitBranch className="size-4" /> This version's history</h3>
        <ul className="divide-y rounded-lg border">
          <li className="p-2 text-sm">
            <span className="font-medium">{version.name}</span> <span className="text-xs text-muted-foreground">(open now · revision {version.revision})</span>
          </li>
          {chain.map((v, i) => row(v, i === 0 ? "Copied from" : "Earlier"))}
          {children.map((v) => row(v, "Copy of this"))}
        </ul>
        {!chain.length && <p className="mt-1 text-xs text-muted-foreground">This version was created from your profile.</p>}
      </section>
      {others.length > 0 && (
        <section aria-label="Other versions">
          <h3 className="mb-1.5 text-sm font-semibold">Other versions</h3>
          <ul className="divide-y rounded-lg border">{others.map((v) => row(v))}</ul>
        </section>
      )}
    </div>
  );
}
