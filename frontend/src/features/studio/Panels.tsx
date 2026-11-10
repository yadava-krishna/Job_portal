import { useState, type ReactNode } from "react";
import { AlertCircle, AlertTriangle, ArrowRight, Check, CircleHelp, GitBranch, Info, Lightbulb, Loader2, RefreshCw, RotateCcw, X } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, NativeSelect } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  useStudioFeedback, useStudioSuggestions, useStudioTemplates, useStudioVersions,
  type Density, type FeedbackIssue, type IssueLevel, type PageSize, type Section, type StudioSettings, type Suggestion, type TemplateKey, type Version, type VersionSummary,
} from "./api";
import { JobPicker, TemplatePicker, VersionStatusBadge } from "./parts";

// ---------------- design: template + layout settings ----------------

const FONT_SIZES = [9, 9.5, 10, 10.5, 11, 11.5, 12];

export function DesignPanel({ templateKey, settings, readOnly, onTemplate, onSettings }: {
  templateKey: TemplateKey; settings: StudioSettings; readOnly: boolean;
  onTemplate: (k: TemplateKey) => void; onSettings: (s: StudioSettings) => void;
}) {
  const templates = useStudioTemplates();
  const list = Array.isArray(templates.data) ? templates.data : [];
  return (
    <fieldset disabled={readOnly} className="min-w-0 space-y-4">
      <legend className="sr-only">Design</legend>
      <div className="space-y-1.5">
        <span className="text-sm font-medium">Template</span>
        <p className="text-xs text-muted-foreground">Switching template keeps all your content.</p>
        {templates.isLoading ? <Loader2 className="animate-spin" /> : <TemplatePicker templates={list} value={templateKey} onChange={onTemplate} disabled={readOnly} compact />}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Font size" htmlFor="st-font">
          <NativeSelect id="st-font" className="w-full" value={String(settings.font_size ?? 10.5)} onChange={(v) => onSettings({ ...settings, font_size: Number(v) })}
                        options={FONT_SIZES.map((f) => ({ value: String(f), label: `${f} pt` }))} />
        </Field>
        <Field label="Spacing" htmlFor="st-density">
          <NativeSelect id="st-density" className="w-full" value={settings.density ?? "normal"} onChange={(v) => onSettings({ ...settings, density: v as Density })}
                        options={[{ value: "compact", label: "Compact" }, { value: "normal", label: "Normal" }, { value: "relaxed", label: "Relaxed" }]} />
        </Field>
        <Field label="Page size" htmlFor="st-page">
          <NativeSelect id="st-page" className="w-full" value={settings.page_size ?? "A4"} onChange={(v) => onSettings({ ...settings, page_size: v as PageSize })}
                        options={[{ value: "A4", label: "A4" }, { value: "LETTER", label: "US Letter" }]} />
        </Field>
      </div>
      {templateKey === "international" && (
        <Field label="Work authorisation / relocation line (optional)" htmlFor="st-mobility" hint="Shown under your contact details, e.g. “EU Blue Card eligible · open to relocate to Germany”. Only add what is true.">
          <Input id="st-mobility" maxLength={200} value={settings.mobility_line ?? ""} onChange={(e) => onSettings({ ...settings, mobility_line: e.target.value })} />
        </Field>
      )}
    </fieldset>
  );
}

// ---------------- check (feedback) ----------------

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
                  How many of these layout and wording checks pass. It is not a prediction of whether you'll be shortlisted or hired.
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
  if (s.kind === "add_skill") return sec.heading;
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
                      <span className="font-medium">{s.kind === "rewrite" ? "Reword" : s.kind === "reorder" ? "Reorder bullets" : "Add skill"}</span>
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
