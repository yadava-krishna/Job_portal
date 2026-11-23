import { useState, type ReactNode } from "react";
import { AlertCircle, AlertTriangle, ArrowRight, Check, CircleHelp, GitBranch, Info, Lightbulb, Loader2, RefreshCw, RotateCcw, X } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, LoadingState, NativeSelect } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { fontLabel } from "./templateCopy";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  useStudioFeedback, useStudioSuggestions, useStudioTemplates, useStudioVersions,
  type DateFormat, type FeedbackIssue, type IssueLevel, type IssueWhere, type SuggestionCategory, type HeadingStyle, type PageSize, type Section, type StudioSettings, type Suggestion, type TemplateKey, type Version, type VersionSummary,
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
  const [picked, setPicked] = useState<string | null>(null);
  const accent = String(v("accent") ?? "");
  return (
    <fieldset disabled={readOnly} className="min-w-0 space-y-6">
      <legend className="sr-only">Design</legend>
      <DesignGroup title="Template" hint="Switching keeps all your content. Fonts, colour and headings reset to the new template's defaults.">
        {templates.isLoading ? <LoadingState /> : <TemplatePicker templates={list} value={templateKey} onChange={onTemplate} disabled={readOnly} compact />}
      </DesignGroup>

      <DesignGroup title="Text">
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Font" htmlFor="st-family" className="sm:col-span-3">
            <NativeSelect id="st-family" className="w-full" value={String(v("font_family") ?? "")} onChange={(x) => set({ font_family: x })}
                          options={(tpl?.fonts ?? []).map((f) => ({ value: f.key, label: fontLabel(f.key, f.label) }))} />
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
        {tpl?.ats_safe && <p className="text-xs text-muted-foreground">Safe for online forms: text stays at {minSize} pt or larger, and only fonts that job-site resume readers handle well are offered.</p>}
      </DesignGroup>

      <DesignGroup title="Page">
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
      </DesignGroup>

      <DesignGroup title="Style">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Section headings" htmlFor="st-heading">
            <NativeSelect id="st-heading" className="w-full" value={String(v("heading_style") ?? "caps_rule")} onChange={(x) => set({ heading_style: x as HeadingStyle })}
                          options={(tpl?.heading_styles ?? ["caps_rule", "accent", "underline", "plain"]).map((h) => ({ value: h, label: HEADING_LABELS[h] }))} />
          </Field>
          <div className="space-y-1.5">
            <span className="text-sm font-medium" id="st-accent-label">Accent colour</span>
            <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-labelledby="st-accent-label">
              {ACCENTS.map((c) => {
                const on = accent.toLowerCase() === c;
                return (
                  // Swatches show the resume's own ink colours (document content, not interface colours).
                  <button key={c} type="button" role="radio" aria-checked={on} aria-label={`Accent ${c}`} onClick={() => { setPicked(c); set({ accent: c }); }}
                          className={cn("relative size-7 rounded-full ring-offset-2 ring-offset-card transition-shadow duration-150 focus-visible:outline-2 focus-visible:outline-ring",
                            on ? "ring-2 ring-violet" : "ring-1 ring-border hover:ring-foreground/30")} style={{ background: c }}>
                    {on && <Check key={picked} aria-hidden className={cn("absolute inset-0 m-auto size-3.5 text-white", picked === c && "jp-bump")} />}
                  </button>
                );
              })}
              <label className="relative flex h-7 items-center gap-1.5 rounded-full px-2 text-xs text-muted-foreground ring-1 ring-border hover:ring-foreground/30">
                <span className="size-4 rounded-full ring-1 ring-border" style={{ background: accent || "#111827" }} aria-hidden />
                Custom
                <input type="color" aria-label="Custom accent colour" value={accent || "#111827"} onChange={(e) => set({ accent: e.target.value })}
                       className="absolute inset-0 cursor-pointer opacity-0" />
              </label>
            </div>
            <p className="text-xs text-muted-foreground">Colours too light to read on white are not used.</p>
          </div>
        </div>
        <Button size="xs" variant="ghost" className="-ml-2 text-muted-foreground" onClick={() => onSettings({ page_size: settings.page_size, mobility_line: settings.mobility_line })}>
          <RotateCcw /> Reset to template defaults
        </Button>
      </DesignGroup>

      {templateKey === "international" && (
        <Field label="Work authorisation / relocation line (optional)" htmlFor="st-mobility" hint="Shown under your contact details, e.g. “EU Blue Card eligible · open to relocate to Germany”. Only add what is true.">
          <Input id="st-mobility" maxLength={200} value={settings.mobility_line ?? ""} onChange={(e) => set({ mobility_line: e.target.value })} />
        </Field>
      )}
    </fieldset>
  );
}

function DesignGroup({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-2.5 border-t pt-5 first:border-t-0 first:pt-0">
      <div>
        <h3 className="font-display text-[14px] font-bold tracking-[-0.01em] text-heading">{title}</h3>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </section>
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
  error: { label: "Must fix", icon: <AlertCircle className="size-4" />, cls: "text-destructive" },
  warning: { label: "Worth fixing", icon: <AlertTriangle className="size-4" />, cls: "text-caution" },
  suggestion: { label: "Suggestions", icon: <Lightbulb className="size-4" />, cls: "text-violet" },
  info: { label: "For your information", icon: <Info className="size-4" />, cls: "text-muted-foreground" },
};
const kindChip: Record<string, [string, string]> = {
  format: ["Format", "bg-paper-sunk text-foreground/75 ring-1 ring-inset ring-border"],
  accuracy: ["Accuracy", "bg-destructive/10 text-destructive"],
  job: ["Job", "bg-route-tint text-route"],
  writing: ["Writing", "bg-lavender text-violet"],
};

function whereLabel(i: FeedbackIssue): string | null {
  const w = i.where;
  if (!w) return null;
  const parts = [w.section.charAt(0).toUpperCase() + w.section.slice(1)];
  if (i.entry && w.section !== "header") parts.push(i.entry);
  else if (w.block != null) parts.push(`item ${w.block + 1}`);
  if (w.bullet != null) parts.push(`bullet ${w.bullet + 1}`);
  else if (w.field && !["bullet", "text", "items"].includes(w.field)) parts.push(w.field === "organization" ? "employer" : w.field);
  return parts.join(" · ");
}

/** One of the three separate evaluations. They measure different things and are never averaged. */
function ScoreCard({ title, value, unit = "", caption, method, tone, testId }: {
  title: string; value: number | null | undefined; unit?: string; caption: string; method: string; tone: "route" | "violet" | "caution"; testId: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div data-testid={testId} className="flex min-w-0 flex-1 basis-44 flex-col rounded-2xl bg-card p-3 ring-1 ring-border">
      <span className="text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{title}</span>
      <span className={cn("readout mt-0.5 text-2xl font-semibold", tone === "route" ? "text-route" : tone === "violet" ? "text-violet" : "text-caution")}>
        {value == null ? "—" : `${value}${unit}`}
      </span>
      <span className="text-xs text-muted-foreground">{caption}</span>
      <button type="button" className="mt-1.5 self-start text-[11px] font-medium text-route underline-offset-2 hover:underline" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide how it's worked out" : "How it's worked out"}
      </button>
      {open && <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{method}</p>}
    </div>
  );
}

function IssueRow({ i, onGoTo }: { i: FeedbackIssue; onGoTo?: (w: IssueWhere) => void }) {
  const [open, setOpen] = useState(false);
  const place = whereLabel(i);
  const more = Boolean(i.why || i.evidence || i.fix);
  return (
    <li className="bg-card px-3 py-2.5 text-sm" data-issue={i.id ?? i.code}>
      <div className="flex items-start gap-2">
        {i.kind && <span className={cn("mt-px shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase", kindChip[i.kind]?.[1] ?? kindChip.writing[1])}
          title={KIND_HELP[i.kind]}>{kindChip[i.kind]?.[0] ?? "Writing"}</span>}
        <span className="min-w-0 flex-1">
          {i.message}{(i.count ?? 1) > 1 && <span className="readout ml-1 text-xs text-muted-foreground">×{i.count}</span>}
          {place && <span className="mt-0.5 block text-xs text-muted-foreground">{place}</span>}
        </span>
        <span className="flex shrink-0 gap-1">
          {more && <Button size="xs" variant="ghost" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Less" : "Details"}</Button>}
          {i.where && onGoTo && <Button size="xs" variant="outline" onClick={() => onGoTo(i.where as IssueWhere)}>Go to <ArrowRight /></Button>}
        </span>
      </div>
      {open && (
        <dl className="mt-2 grid gap-1 rounded-lg bg-paper-sunk p-2.5 text-xs">
          {i.why && <><dt className="font-semibold text-heading">Why it matters</dt><dd className="text-muted-foreground">{i.why}</dd></>}
          {i.evidence && <><dt className="mt-1 font-semibold text-heading">Evidence</dt><dd className="break-words text-muted-foreground">{i.evidence}</dd></>}
          {i.fix && <><dt className="mt-1 font-semibold text-heading">How to fix it</dt><dd className="text-muted-foreground">{i.fix}</dd></>}
        </dl>
      )}
    </li>
  );
}

export function CheckPanel({ versionId, jobId, onJob, revision, onGoTo }: {
  versionId: number; jobId: number | null; onJob: (j: number | null) => void; revision: number; onGoTo?: (w: IssueWhere) => void;
}) {
  // Keyed by the saved revision: every save re-checks the new revision's exported PDF, and an answer for an older
  // revision is never shown as current.
  const fb = useStudioFeedback(versionId, jobId, true, revision);
  const issues = fb.data?.issues ?? [];
  const sc = fb.data?.scores;
  const quality = sc?.resume_quality.score ?? fb.data?.readiness;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Check against a job (optional)" htmlFor="ck-job" className="min-w-56 flex-1">
          <JobPicker id="ck-job" value={jobId} onChange={onJob} emptyLabel="General check (no job)" />
        </Field>
        <Button size="sm" variant="outline" onClick={() => void fb.refetch()} disabled={fb.isFetching}>
          {fb.isFetching ? <Loader2 className="animate-spin" /> : <RefreshCw />} Re-check
        </Button>
      </div>
      {fb.isLoading ? <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> Checking the exported PDF…</div>
        : fb.isError ? <p className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{errorMessage(fb.error, "Couldn't run the check")}</p>
          : fb.data && (
            <>
              <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground" data-testid="check-revision">
                <Check className="size-3.5 text-success" aria-hidden />
                Checked revision {fb.data.revision ?? revision}: the exported PDF, {fb.data.pages != null ? `${fb.data.pages} page${fb.data.pages === 1 ? "" : "s"}` : "pages unknown"}, the same file the preview shows.
              </p>
              <div className="flex flex-wrap gap-2.5" aria-label="Three separate evaluations">
                {sc?.job_match && <ScoreCard testId="score-job-match" title="Job Match" value={sc.job_match.score} unit="%" tone="route"
                  caption="Your verified profile vs this job" method={sc.job_match.method} />}
                <ScoreCard testId="score-quality" title="Resume Quality" value={quality} unit="/100" tone="violet"
                  caption="This PDF's build, wording and readability" method={sc?.resume_quality.method ?? fb.data.score_method ?? ""} />
                {sc?.alignment && <ScoreCard testId="score-alignment" title="Resume–Job Alignment" value={sc.alignment.score} unit="%" tone="caution"
                  caption={sc.alignment.score == null ? (sc.alignment.note ?? "") : `${sc.alignment.matched.length} of the job's skills printed on this resume`} method={sc.alignment.method} />}
              </div>
              {sc?.job_match ? (
                <p className="rounded-xl bg-paper-sunk p-3 text-xs leading-relaxed text-muted-foreground">
                  <strong className="text-heading">Why these differ:</strong> Job Match looks at everything you've verified about yourself, so it stays the same while you edit.
                  Resume Quality only checks how this document is built and read. Alignment counts what this resume actually shows for the job.
                  A strong match with a lower quality score means the fit is there and the document needs fixing. None of these is an ATS score or predicts hiring.
                </p>
              ) : <p className="text-xs text-muted-foreground">Pick a job above to see Job Match and Resume–Job Alignment next to Resume Quality.</p>}
              {sc?.alignment && (sc.alignment.addable.length > 0 || sc.alignment.gaps.length > 0) && (
                <div className="grid gap-2 text-xs sm:grid-cols-2">
                  {sc.alignment.addable.length > 0 && <p className="rounded-xl bg-route-tint/50 p-2.5"><strong className="text-heading">In your profile, not on this resume:</strong> {sc.alignment.addable.map((a) => a.skill).join(", ")}</p>}
                  {sc.alignment.gaps.length > 0 && <p className="rounded-xl bg-paper-sunk p-2.5"><strong className="text-heading">No evidence yet (never added for you):</strong> {sc.alignment.gaps.map((a) => a.skill).join(", ")}</p>}
                </div>
              )}
              {!issues.length ? <p className="flex items-center gap-2 rounded-xl bg-success-tint p-3 text-sm font-medium text-success"><Check className="size-4" /> No issues found. Clean.</p> : (
                (Object.keys(levelMeta) as IssueLevel[]).map((lvl) => {
                  const group = issues.filter((i) => i.level === lvl);
                  if (!group.length) return null;
                  return (
                    <section key={lvl} aria-label={levelMeta[lvl].label}>
                      <h3 className={cn("mb-1.5 flex items-center gap-1.5 text-[13px] font-semibold", levelMeta[lvl].cls)}>{levelMeta[lvl].icon} {levelMeta[lvl].label} <span className="readout font-normal">({group.length})</span>
                        {lvl === "info" && <span className="font-normal text-muted-foreground">: notes don't lower Resume Quality</span>}</h3>
                      <ul className="divide-y overflow-hidden rounded-xl ring-1 ring-border">
                        {group.map((i, n) => <IssueRow key={i.id ?? `${i.code}-${n}`} i={i} onGoTo={onGoTo} />)}
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

const CATEGORY_ORDER: SuggestionCategory[] = ["structure", "writing", "emphasize", "confirm", "gap"];
const CATEGORY_TITLE: Record<SuggestionCategory, string> = {
  structure: "A · Structural fixes", writing: "B · Writing and clarity", emphasize: "C · Verified experience to emphasise",
  confirm: "D · Missing information only you can confirm", gap: "E · Requirements you can't evidence yet",
};

function suggestionTarget(s: Suggestion, sections: Section[]): string {
  if (s.where_label) return s.where_label;
  if (!s.where) return "";
  const sec = sections[s.where.section];
  if (!sec) return "";
  if (s.kind === "add_skill" || s.kind === "reorder_entries") return sec.heading;
  const b = sec.blocks[s.where.block];
  const title = b?.type === "entry" ? [b.content.title, b.content.organization].filter(Boolean).join(" — ") : "";
  return [sec.heading, title, s.where.bullet != null ? `bullet ${s.where.bullet + 1}` : ""].filter(Boolean).join(" · ");
}

const KIND_TITLE: Record<Suggestion["kind"], string> = {
  rewrite: "Reword", reorder: "Reorder bullets", reorder_skills: "Reorder skills", reorder_entries: "Reorder projects", add_skill: "Add skill",
  edit_field: "Fix characters", confirm: "Add missing detail", gap: "Requirement",
};

export function SuggestionsPanel({ versionId, jobId, onJob, sections, readOnly, onAccept, onGoTo, handled: handledProp, onHandledChange, revision }: {
  versionId: number; jobId: number | null; onJob: (j: number | null) => void; sections: Section[]; readOnly: boolean;
  onAccept: (s: Suggestion) => boolean;
  onGoTo?: (w: IssueWhere) => void;
  /** Optional: keep accepted/dismissed suggestions in the parent so they stay hidden across tab switches. */
  handled?: Set<string>; onHandledChange?: (h: Set<string>) => void;
  revision?: number;
}) {
  const sug = useStudioSuggestions(versionId, jobId, true, revision);
  const [localHandled, setLocalHandled] = useState<Set<string>>(new Set());
  const handled = handledProp ?? localHandled;
  const setHandled = (next: Set<string>) => (onHandledChange ? onHandledChange(next) : setLocalHandled(next));
  const all = Array.isArray(sug.data) ? sug.data : [];
  const list = all.filter((s) => !handled.has(s.id));
  const done = (id: string) => setHandled(new Set(handled).add(id));
  const refresh = () => { setHandled(new Set()); void sug.refetch(); };
  const goTo = (s: Suggestion) => {
    if (!s.where || !onGoTo) return;
    const sec = sections[s.where.section];
    if (sec) onGoTo({ section: sec.type, block: s.where.block, bullet: s.where.bullet ?? null, field: s.where.field ?? (s.where.bullet != null ? "bullet" : null) });
  };
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">Suggestions use only facts already in your verified profile. Nothing changes unless you accept it, and Undo takes it back.</p>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Tailor for a job (optional)" htmlFor="sg-job" className="min-w-56 flex-1">
          <JobPicker id="sg-job" value={jobId} onChange={onJob} emptyLabel="General suggestions (no job)" />
        </Field>
        <Button size="sm" variant="outline" onClick={refresh} disabled={sug.isFetching}>{sug.isFetching ? <Loader2 className="animate-spin" /> : <RefreshCw />} Refresh</Button>
      </div>
      {sug.isLoading ? <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> Looking for improvements…</div>
        : sug.isError ? <p className="rounded-xl bg-destructive/10 p-3 text-sm text-destructive">{errorMessage(sug.error, "Couldn't load suggestions")}</p>
          : !list.length ? (
            <div className="rounded-2xl bg-paper-sunk px-4 py-8 text-center">
              <p className="font-display text-[15px] font-bold text-heading">{all.length ? "All caught up. Love that for you." : "No suggestions right now."}</p>
              <p className="mt-1 text-xs text-muted-foreground">{all.length ? "Refresh to see the ones you dismissed again." : jobId == null ? "Pick a job to get job-specific ones." : "This version already reads well for that job."}</p>
            </div>
          ) : CATEGORY_ORDER.map((cat) => {
            const group = list.filter((s) => (s.category ?? "writing") === cat);
            if (!group.length) return null;
            return (
              <section key={cat} aria-label={CATEGORY_TITLE[cat]} className="space-y-2">
                <h3 className="text-[13px] font-semibold text-heading">{CATEGORY_TITLE[cat]} <span className="readout font-normal text-muted-foreground">({group.length})</span></h3>
                <ul className="space-y-2.5">
                  {group.map((s) => {
                    const applicable = !["confirm", "gap"].includes(s.kind);
                    return (
                      <li key={s.id} className="rounded-2xl bg-card p-3 text-sm ring-1 ring-border animate-in fade-in-0 duration-200" aria-label={`Suggestion: ${s.reason}`} data-suggestion={s.id}>
                        <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs">
                          <span className="font-semibold text-heading">{KIND_TITLE[s.kind] ?? s.kind}</span>
                          <span className="text-muted-foreground">{suggestionTarget(s, sections)}</span>
                          <span className={cn("ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium",
                            s.kind === "gap" ? "bg-paper-sunk text-muted-foreground" : s.evidence === "supported" ? "bg-success-tint text-success" : "bg-caution-tint text-caution")}>
                            {s.kind === "gap" ? "No evidence in your profile" : s.kind === "confirm" ? "Only you can add this" : s.evidence === "supported" ? "Backed by your verified data" : "Not verified, check it's true"}
                          </span>
                        </div>
                        {(s.kind === "rewrite" || s.kind === "edit_field") && (
                          <div className="grid items-center gap-1.5 sm:grid-cols-[1fr_auto_1fr]">
                            <p className="rounded-lg bg-paper-sunk p-2 break-words text-muted-foreground line-through decoration-muted-foreground/40">{s.before}</p>
                            <ArrowRight className="hidden size-4 text-muted-foreground sm:block" aria-hidden />
                            <p className="rounded-lg bg-lavender/60 p-2 break-words text-foreground dark:bg-lavender/15">{s.after}</p>
                          </div>
                        )}
                        {s.kind === "reorder" && s.where && (() => {
                          const b = sections[s.where.section]?.blocks[s.where.block];
                          const top = b && s.order?.length ? b.bullets[s.order[0]]?.text : null;
                          return top ? <p className="text-xs">Move to the top: <span className="italic">“{top}”</span></p> : null;
                        })()}
                        {s.kind === "add_skill" && <p>Add <span className="rounded-full bg-route-tint px-2 py-0.5 font-medium text-route">{s.skill ?? s.after}</span> to your skills.</p>}
                        {s.kind === "reorder_skills" && <p className="text-xs">New order: <span className="font-medium">{s.after}</span>{(s.order?.length ?? 0) > 6 ? "…" : ""}</p>}
                        {s.kind === "reorder_entries" && s.where && (() => {
                          const b = sections[s.where.section]?.blocks[s.order?.[0] ?? -1];
                          const t = b?.type === "entry" ? b.content.title : null;
                          return t ? <p className="text-xs">Move to the top: <span className="font-medium">{t}</span></p> : null;
                        })()}
                        <p className="mt-2 text-xs text-foreground/85">{s.reason}</p>
                        {(s.why || s.effect) && (
                          <dl className="mt-1.5 grid gap-x-3 gap-y-0.5 text-xs sm:grid-cols-[auto_1fr]">
                            {s.why && <><dt className="font-medium text-heading">Why</dt><dd className="text-muted-foreground">{s.why}</dd></>}
                            {s.effect && <><dt className="font-medium text-heading">Effect</dt><dd className="text-muted-foreground">{s.effect}</dd></>}
                          </dl>
                        )}
                        <div className="mt-2.5 flex flex-wrap justify-end gap-1.5">
                          <Button size="xs" variant="ghost" onClick={() => done(s.id)}><X /> {s.kind === "gap" ? "Got it" : "Ignore"}</Button>
                          {s.kind === "gap" && <Button size="xs" variant="outline" render={<Link to="/career?tab=gaps" />}>See ways to build it</Button>}
                          {s.where && onGoTo && <Button size="xs" variant="outline" onClick={() => goTo(s)}>Go to <ArrowRight /></Button>}
                          {applicable && <Button size="xs" disabled={readOnly} onClick={() => { if (onAccept(s)) done(s.id); }}><Check /> Accept</Button>}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            );
          })}
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
    <li key={v.id} className="flex flex-wrap items-center gap-2 bg-card px-3 py-2.5 text-sm">
      <div className="min-w-0 flex-1">
        <Link to={`/studio/${v.id}`} className="font-medium text-heading decoration-route/40 underline-offset-4 hover:underline">{v.name}</Link>
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
        <h3 className="mb-1.5 flex items-center gap-1.5 text-[13px] font-semibold text-heading"><GitBranch className="size-4 text-violet" /> This version's history</h3>
        <ul className="divide-y overflow-hidden rounded-xl ring-1 ring-border">
          <li className="flex items-center gap-2 bg-lavender/40 px-3 py-2.5 text-sm dark:bg-lavender/10">
            <span className="size-2 shrink-0 rounded-full bg-violet" aria-hidden />
            <span className="font-medium text-heading">{version.name}</span> <span className="readout text-xs text-muted-foreground">(open now · revision {version.revision})</span>
          </li>
          {chain.map((v, i) => row(v, i === 0 ? "Copied from" : "Earlier"))}
          {children.map((v) => row(v, "Copy of this"))}
        </ul>
        {!chain.length && <p className="mt-1 text-xs text-muted-foreground">This version was created from your profile.</p>}
      </section>
      {others.length > 0 && (
        <section aria-label="Other versions">
          <h3 className="mb-1.5 text-[13px] font-semibold text-heading">Other versions</h3>
          <ul className="divide-y overflow-hidden rounded-xl ring-1 ring-border">{others.map((v) => row(v))}</ul>
        </section>
      )}
    </div>
  );
}
