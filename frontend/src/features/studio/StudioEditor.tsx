import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, ChevronDown, Copy, Download, FileText, Layers, Loader2, Lock, Redo2, RefreshCw, Undo2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/app/common";
import { downloadFile, errorMessage } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useJobs } from "@/services/queries";
import {
  applySuggestion, exportVersion, saveConflict, saveVersion, studioKeys, useCloneVersion, useStudioFeedback, useStudioSuggestions, useStudioTemplates,
  useStudioVersion, useStudioVersions, withKeys,
  type Suggestion, type Version, type VersionSummary,
} from "./api";
import { DocumentEditor } from "./DocumentEditor";
import { CheckPanel, DesignPanel, HistoryPanel, SuggestionsPanel } from "./Panels";
import { PreviewPane } from "./PreviewPane";
import { AtsBadge, VersionStatusBadge } from "./parts";
import { templateName as friendlyTemplateName } from "./templateCopy";

type SaveState = "idle" | "pending" | "saving" | "saved" | "error" | "conflict";
const AUTOSAVE_MS = 1200;
const HISTORY_LIMIT = 100;
const COALESCE_MS = 800;  // keystrokes within this window are one undo step

type Snapshot = Pick<Version, "name" | "template_key" | "settings" | "sections">;
const snap = (v: Version): Snapshot => ({ name: v.name, template_key: v.template_key, settings: v.settings, sections: v.sections });
/** Switching template resets the style choices to the new template's defaults (content is untouched). */
const styleReset = (s: Version["settings"]) => {
  const { font_family: _f, accent: _a, heading_style: _h, ...rest } = s ?? {};
  return rest;
};

export function StudioEditor({ id }: { id: number }) {
  const query = useStudioVersion(id);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const clone = useCloneVersion();
  const templates = useStudioTemplates();
  const jobs = useJobs({ view: "all", sort: "score", page_size: 100 });

  const [draft, setDraft] = useState<Version | null>(null);
  const [savedRevision, setSavedRevision] = useState(0);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [seq, setSeq] = useState(0);
  const [mobileView, setMobileView] = useState<"edit" | "preview">("edit");
  // undefined = not chosen yet → defaults to the version's target job.
  const [jobChoice, setJobId] = useState<number | null | undefined>(undefined);
  const [exporting, setExporting] = useState<"pdf" | "docx" | null>(null);
  const [exported, setExported] = useState<"pdf" | "docx" | null>(null);
  const exportedTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(exportedTimer.current), []);
  // Suggestions dismissed or accepted this session (kept here so switching tabs doesn't bring them back).
  const [handledSuggestions, setHandledSuggestions] = useState<Set<string>>(() => new Set());

  const draftRef = useRef<Version | null>(null);
  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);
  const lastPush = useRef<{ at: number; keys: string }>({ at: 0, keys: "" });
  const [, setHistoryTick] = useState(0);
  const seqRef = useRef(0);
  const savedSeqRef = useRef(0);
  const revisionRef = useRef(0);
  const inFlight = useRef<Promise<boolean> | null>(null);
  const blockedRef = useRef(false);  // conflict / locked: stop autosaving until reload
  const refetchRef = useRef(query.refetch);
  useEffect(() => { refetchRef.current = query.refetch; }, [query.refetch]);

  const reset = useCallback((v: Version) => {
    const next = { ...v, sections: withKeys(v.sections ?? []) };
    draftRef.current = next;
    revisionRef.current = v.revision;
    seqRef.current = 0;
    savedSeqRef.current = 0;
    blockedRef.current = false;
    past.current = [];
    future.current = [];
    setHistoryTick((t) => t + 1);
    setDraft(next);
    setSavedRevision(v.revision);
    setSeq(0);
    setSaveState("idle");
  }, []);

  // Load (or switch to another version). The local working copy is never replaced by background refetches.
  useEffect(() => {
    if (query.data && (!draftRef.current || draftRef.current.id !== query.data.id)) reset(query.data);
  }, [query.data, reset]);

  const targetUserJob = draft?.target_job_id ? jobs.data?.items?.find((j) => j.job.id === draft.target_job_id)?.user_job_id ?? null : null;
  const jobId = jobChoice === undefined ? targetUserJob : jobChoice;

  const readOnly = draft?.status === "locked";
  const versions = useStudioVersions();
  const versionList = Array.isArray(versions.data) ? versions.data : [];
  // Read-only views of the panels' caches (enabled: false never fetches; the panels run the checks when opened).
  const feedbackCache = useStudioFeedback(id, jobId, false);
  const suggestionsCache = useStudioSuggestions(id, jobId, false);

  const apply = (next: Version) => {
    draftRef.current = next;
    seqRef.current += 1;
    setDraft(next);
    setSeq(seqRef.current);
    if (!blockedRef.current) setSaveState("pending");
  };

  const update = (patch: Partial<Version>) => {
    if (!draftRef.current || readOnly) return;
    const keys = Object.keys(patch).sort().join(",");
    const now = Date.now();
    if (now - lastPush.current.at > COALESCE_MS || keys !== lastPush.current.keys) {
      past.current = [...past.current.slice(-(HISTORY_LIMIT - 1)), snap(draftRef.current)];
    }
    lastPush.current = { at: now, keys };
    future.current = [];
    setHistoryTick((t) => t + 1);
    const next = { ...draftRef.current, ...patch };
    draftRef.current = next;
    seqRef.current += 1;
    setDraft(next);
    setSeq(seqRef.current);
    if (!blockedRef.current) setSaveState("pending");
  };

  const doSave = useCallback(async (): Promise<boolean> => {
    if (inFlight.current) {
      await inFlight.current;
      if (seqRef.current === savedSeqRef.current) return true;
    }
    const d = draftRef.current;
    if (!d || blockedRef.current) return false;
    const at = seqRef.current;
    setSaveState("saving");
    const run = (async () => {
      try {
        const res = await saveVersion(d.id, { revision: revisionRef.current, name: d.name, template_key: d.template_key, settings: d.settings, sections: d.sections });
        revisionRef.current = res.revision;
        savedSeqRef.current = at;
        const meta = { revision: res.revision, checksum: res.checksum, template_name: res.template_name, ats_safe: res.ats_safe, updated_at: res.updated_at, status: res.status };
        draftRef.current = draftRef.current ? { ...draftRef.current, ...meta } : draftRef.current;
        setDraft((x) => (x ? { ...x, ...meta } : x));
        setSavedRevision(res.revision);
        qc.setQueryData(studioKeys.version(d.id), res);
        void qc.invalidateQueries({ queryKey: studioKeys.versions });
        setSaveState(seqRef.current === at ? "saved" : "pending");
        return true;
      } catch (e) {
        const c = saveConflict(e);
        if (c) {
          blockedRef.current = true;
          setSaveState("conflict");
          if (c === "locked") void refetchRef.current().then((r) => r.data && reset(r.data));
        } else {
          setSaveState("error");
          toast.error(errorMessage(e, "Couldn't save"));
        }
        return false;
      }
    })();
    inFlight.current = run;
    const ok = await run;
    inFlight.current = null;
    return ok;
  }, [qc, reset]);

  // Debounced autosave ~1.2 s after the last edit. Edits made during an in-flight save re-arm the timer, and
  // doSave waits for the in-flight request before sending the newer copy.
  useEffect(() => {
    if (seq === 0 || seq === savedSeqRef.current || blockedRef.current) return;
    const t = setTimeout(() => void doSave(), AUTOSAVE_MS);
    return () => clearTimeout(t);
  }, [seq, doSave]);

  // Warn before closing the tab with unsaved edits; flush them when leaving the editor.
  useEffect(() => {
    const onBefore = (e: BeforeUnloadEvent) => { if (seqRef.current !== savedSeqRef.current && !blockedRef.current) e.preventDefault(); };
    window.addEventListener("beforeunload", onBefore);
    return () => {
      window.removeEventListener("beforeunload", onBefore);
      void (inFlight.current ?? Promise.resolve(true)).then(() => {
        const d = draftRef.current;
        if (!d || seqRef.current === savedSeqRef.current || blockedRef.current || d.status === "locked") return;
        return saveVersion(d.id, { revision: revisionRef.current, name: d.name, template_key: d.template_key, settings: d.settings, sections: d.sections })
          .then(() => qc.invalidateQueries({ queryKey: studioKeys.versions }))
          .catch(() => toast.error("Your last resume edits couldn't be saved."));
      });
    };
  }, [qc]);

  const undo = useCallback(() => {
    const d = draftRef.current;
    const prev = past.current.at(-1);
    if (!d || !prev || d.status === "locked") return;
    past.current = past.current.slice(0, -1);
    future.current = [...future.current, snap(d)];
    lastPush.current = { at: 0, keys: "" };
    setHistoryTick((t) => t + 1);
    apply({ ...d, ...prev });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const redo = useCallback(() => {
    const d = draftRef.current;
    const nextSnap = future.current.at(-1);
    if (!d || !nextSnap || d.status === "locked") return;
    future.current = future.current.slice(0, -1);
    past.current = [...past.current, snap(d)];
    lastPush.current = { at: 0, keys: "" };
    setHistoryTick((t) => t + 1);
    apply({ ...d, ...nextSnap });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Ctrl/Cmd+Z undo, Ctrl/Cmd+Shift+Z or Ctrl+Y redo. (Form fields are controlled, so the browser's own per-field undo
  // would desynchronise from the document; the editor's history covers every change instead.)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      else if ((k === "z" && e.shiftKey) || k === "y") { e.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  const reload = async () => {
    const r = await query.refetch();
    if (r.data) { reset(r.data); toast("Loaded the latest version"); }
  };

  const makeCopy = async (from: VersionSummary | Version, name?: string) => {
    // Copying the open version: save pending edits first so the copy includes them.
    if (from.id === draftRef.current?.id && !readOnly && seqRef.current !== savedSeqRef.current && !(await doSave())) {
      toast.error("Save your changes before making a copy.");
      return;
    }
    clone.mutate({ id: from.id, name }, {
      onSuccess: (n) => { toast.success("Copy created — you're now editing it"); navigate(`/studio/${n.id}`); },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  const exportAs = async (format: "pdf" | "docx") => {
    if (!draft) return;
    setExporting(format);
    try {
      if (!readOnly && (seqRef.current !== savedSeqRef.current || inFlight.current)) {
        const ok = await doSave();
        if (!ok) { toast.error("Save your changes before exporting."); return; }
      }
      const res = await exportVersion(draft.id, format);
      await downloadFile(res.download_url, `${draft.name}.${format}`);
      setExported(format);
      clearTimeout(exportedTimer.current);
      exportedTimer.current = setTimeout(() => setExported(null), 3000);
      if (res.note) toast(res.note);
      else toast.success("Looking sharp. Ready to send.", {
        description: format === "pdf" ? `PDF downloaded${res.page_count ? ` · ${res.page_count} page${res.page_count === 1 ? "" : "s"}` : ""}` : "Word file downloaded",
      });
    } catch (e) {
      setExported(null);
      toast.error(errorMessage(e, "Export failed"));
    } finally {
      setExporting(null);
    }
  };

  const accept = (s: Suggestion): boolean => {
    if (!draftRef.current) return false;
    const r = applySuggestion(draftRef.current.sections, s);
    if ("error" in r) { toast.error(r.error); return false; }
    update({ sections: r.sections });
    toast.success("Applied. Saving…");
    return true;
  };

  if (query.isLoading || (!draft && !query.isError)) return <div role="status" className="flex items-center gap-2 py-8 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> Loading resume…</div>;
  if (query.isError || !draft) {
    return (
      <EmptyState icon={<FileText className="size-8" />} title="Couldn't open this resume">
        {errorMessage(query.error, "It may have been deleted.")}
        <div className="mt-3"><Button size="sm" variant="outline" render={<Link to="/studio" />}>Back to Resume Studio</Button></div>
      </EmptyState>
    );
  }

  const templateName = friendlyTemplateName(draft.template_key, (Array.isArray(templates.data) ? templates.data.find((t) => t.key === draft.template_key)?.name : undefined) ?? draft.template_name);
  const atsSafe = (Array.isArray(templates.data) ? templates.data.find((t) => t.key === draft.template_key)?.ats_safe : undefined) ?? draft.ats_safe;

  // Inspector badge counts come from data already loaded (never an extra check run just to fill a badge).
  const issues = (feedbackCache.data?.issues ?? []).filter((i) => i.level === "error" || i.level === "warning");
  const hasErrors = issues.some((i) => i.level === "error");
  const openSuggestions = (Array.isArray(suggestionsCache.data) ? suggestionsCache.data : []).filter((x) => !handledSuggestions.has(x.id)).length;
  const otherVersions = Math.max(0, versionList.length - 1);

  return (
    <>
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <Button size="icon-sm" variant="ghost" aria-label="Back to all resumes" render={<Link to="/studio" />}><ArrowLeft /></Button>
          <div className="min-w-0 flex-1">
            <label htmlFor="rv-name" className="sr-only">Resume name</label>
            <Input id="rv-name" value={draft.name} maxLength={120} disabled={readOnly} onChange={(e) => update({ name: e.target.value })}
                   className="h-9 w-full max-w-md border-transparent bg-transparent px-1.5 font-display text-[20px] font-extrabold md:text-[20px] tracking-[-0.02em] text-heading shadow-none hover:border-input focus-visible:border-input disabled:opacity-100 sm:w-[26rem] dark:bg-transparent" />
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-1.5 text-xs text-muted-foreground">
              <VersionStatusBadge status={draft.status} />
              <span>{templateName}</span><AtsBadge safe={atsSafe} />
              {!readOnly && <><span aria-hidden className={cn("h-3 w-px bg-border", saveState === "idle" && "hidden")} /><SaveStatus state={saveState} onRetry={() => void doSave()} onReload={() => void reload()} /></>}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!readOnly && (
            <div className="flex rounded-full bg-paper-sunk p-0.5 ring-1 ring-border/70" role="group" aria-label="Undo and redo">
              <Button size="icon-sm" variant="ghost" aria-label="Undo (Ctrl+Z)" title="Undo (Ctrl+Z)" disabled={!past.current.length} onClick={undo}><Undo2 /></Button>
              <Button size="icon-sm" variant="ghost" aria-label="Redo (Ctrl+Shift+Z)" title="Redo (Ctrl+Shift+Z)" disabled={!future.current.length} onClick={redo}><Redo2 /></Button>
            </div>
          )}
          <VersionSwitcher current={draft} versions={versionList} />
          <Button size="sm" variant="outline" onClick={() => void makeCopy(draft)} disabled={clone.isPending}><Copy /> <span className="sr-only sm:not-sr-only">Make a copy</span></Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button size="sm" variant={exported ? "outline" : "default"} disabled={!!exporting}
                                                 className={cn("min-w-[7.5rem]", exported && "border-success/40 text-success hover:text-success")} />}>
              {exporting ? <><Loader2 className="animate-spin" /> Exporting {exporting === "pdf" ? "PDF" : "Word"}…</>
                : exported ? <><Check className="jp-bump" /> Downloaded</>
                  : <><Download /> Export <ChevronDown /></>}
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onClick={() => void exportAs("pdf")}><FileText /> PDF <span className="ml-auto text-xs text-muted-foreground">best for applying</span></DropdownMenuItem>
              <DropdownMenuItem onClick={() => void exportAs("docx")}><FileText /> Word (.docx)</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <span className="sr-only" aria-live="polite">{exporting ? `Exporting ${exporting === "pdf" ? "PDF" : "Word file"}` : exported ? "Downloaded" : ""}</span>
        </div>
      </div>

      {readOnly && (
        <div role="status" className="mb-3 flex flex-col gap-2 rounded-2xl bg-caution-tint p-3 text-sm text-caution ring-1 ring-caution/25 sm:flex-row sm:items-center">
          <Lock className="size-4 shrink-0" />
          <p className="flex-1 text-foreground/85">This version was used in a submitted application and is kept exactly as sent. Make a copy to edit.</p>
          <Button size="sm" onClick={() => void makeCopy(draft)} disabled={clone.isPending}><Copy /> Make a copy</Button>
        </div>
      )}
      {saveState === "conflict" && !readOnly && (
        <div role="alert" className="mb-3 flex flex-col gap-2 rounded-2xl bg-destructive/10 p-3 text-sm text-destructive ring-1 ring-destructive/25 sm:flex-row sm:items-center">
          <AlertTriangle className="size-4 shrink-0" />
          <p className="flex-1 text-foreground/85">This resume was changed in another window or tab, so your latest edits here weren't saved. Reload to get the latest version.</p>
          <Button size="sm" variant="outline" onClick={() => void reload()}><RefreshCw /> Reload</Button>
        </div>
      )}

      <Tabs value={mobileView} onValueChange={(v) => setMobileView(v as "edit" | "preview")} className="mb-3 lg:hidden">
        <TabsList>
          <TabsTrigger value="edit">Edit</TabsTrigger>
          <TabsTrigger value="preview">Preview</TabsTrigger>
        </TabsList>
      </Tabs>

      {/* Split view: inspector and paper preview each scroll on their own, so tabs, design and export stay in reach. */}
      <div className="grid gap-4 lg:-mb-10 lg:h-[calc(100dvh-9.75rem)] lg:min-h-[540px] lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] xl:grid-cols-[minmax(0,21fr)_minmax(0,19fr)]">
        <section aria-label="Editor" className={cn("flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl bg-card ring-1 ring-border", mobileView !== "edit" && "hidden lg:flex")}>
          <Tabs defaultValue="content" className="min-h-0 flex-1 gap-0">
            <div className="shrink-0 overflow-x-auto border-b px-2.5 py-2">
              <TabsList>
                <TabsTrigger value="content">Content</TabsTrigger>
                <TabsTrigger value="design">Design</TabsTrigger>
                <TabsTrigger value="check">Check<TabCount n={issues.length} tone={hasErrors ? "coral" : "muted"} /></TabsTrigger>
                <TabsTrigger value="suggestions">Suggestions<TabCount n={openSuggestions} tone="route" /></TabsTrigger>
                <TabsTrigger value="history">History<TabCount n={otherVersions} tone="muted" /></TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="content" className="min-h-0 overflow-y-auto overscroll-contain p-3 sm:p-4">
              <DocumentEditor sections={draft.sections} readOnly={readOnly} onChange={(sections) => update({ sections })} />
            </TabsContent>
            <TabsContent value="design" className="min-h-0 overflow-y-auto overscroll-contain p-3 sm:p-4">
              <DesignPanel templateKey={draft.template_key} settings={draft.settings ?? {}} readOnly={readOnly}
                           onTemplate={(template_key) => update({ template_key, settings: styleReset(draft.settings) })} onSettings={(settings) => update({ settings })} />
            </TabsContent>
            <TabsContent value="check" className="min-h-0 overflow-y-auto overscroll-contain p-3 sm:p-4">
              <CheckPanel versionId={draft.id} jobId={jobId} onJob={setJobId} revision={savedRevision} />
            </TabsContent>
            <TabsContent value="suggestions" className="min-h-0 overflow-y-auto overscroll-contain p-3 sm:p-4">
              <SuggestionsPanel versionId={draft.id} jobId={jobId} onJob={setJobId} sections={draft.sections} readOnly={readOnly} onAccept={accept}
                                handled={handledSuggestions} onHandledChange={setHandledSuggestions} />
            </TabsContent>
            <TabsContent value="history" className="min-h-0 overflow-y-auto overscroll-contain p-3 sm:p-4">
              <HistoryPanel version={draft} restoring={clone.isPending} onRestore={(v) => void makeCopy(v, `${v.name} (restored)`)} />
            </TabsContent>
          </Tabs>
        </section>
        <section aria-label="Live preview" className={cn("min-h-0 min-w-0", mobileView !== "preview" && "hidden lg:block")}>
          <PreviewPane versionId={draft.id} revision={savedRevision} templateName={templateName} readOnly={readOnly}
                       onApplySettings={(patch) => update({ settings: { ...(draftRef.current?.settings ?? {}), ...patch } })} />
        </section>
      </div>
    </>
  );
}

/** A small count on an inspector tab. Hidden from assistive tech so the tab keeps its plain name. */
function TabCount({ n, tone }: { n: number; tone: "coral" | "route" | "muted" }) {
  if (!n) return null;
  return (
    <span aria-hidden className={cn("readout ml-0.5 min-w-[18px] rounded-full px-1.5 text-center text-[10.5px] leading-[18px] font-semibold",
      tone === "coral" ? "bg-peach text-coral-ink" : tone === "route" ? "bg-route-tint text-route" : "bg-paper-sunk text-muted-foreground ring-1 ring-inset ring-border")}>
      {n > 99 ? "99+" : n}
    </span>
  );
}

/** Jump between resume versions without going back to the list. */
function VersionSwitcher({ current, versions }: { current: Version; versions: VersionSummary[] }) {
  const navigate = useNavigate();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button size="sm" variant="outline" aria-label="Switch resume version" />}>
        <Layers /> <span className="sr-only sm:not-sr-only">Versions</span>{versions.length > 0 && <span className="readout text-muted-foreground">{versions.length}</span>} <ChevronDown />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 max-w-[calc(100vw-2rem)]">
        <div className="eyebrow px-2 pt-1.5 pb-1">Your versions</div>
        {versions.map((v) => {
          const on = v.id === current.id;
          return (
            <DropdownMenuItem key={v.id} onClick={() => { if (!on) navigate(`/studio/${v.id}`); }} className={cn("items-start gap-2.5 py-2", on && "bg-lavender/50")}>
              <span aria-hidden className={cn("mt-0.5 flex size-4 shrink-0 items-center justify-center", on ? "text-violet" : "text-transparent")}><Check className="size-4" /></span>
              <span className="min-w-0 flex-1">
                <span className={cn("block truncate text-[13px]", on ? "font-semibold text-heading" : "font-medium")}>{v.name}</span>
                <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  {friendlyTemplateName(v.template_key, v.template_name)} · {timeAgo(v.updated_at)}{v.status === "locked" && <Lock className="size-3 text-caution" aria-label="Locked" />}
                </span>
              </span>
            </DropdownMenuItem>
          );
        })}
        {!versions.length && <p className="px-2 py-2 text-xs text-muted-foreground">Loading versions…</p>}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate("/studio")}><ArrowLeft /> All resumes</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SaveStatus({ state, onRetry, onReload }: { state: SaveState; onRetry: () => void; onReload: () => void }) {
  return (
    <span className="inline-flex items-center gap-1" aria-live="polite">
      {state === "pending" && <span className="inline-flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-caution" aria-hidden />Unsaved changes</span>}
      {state === "saving" && <><Loader2 className="size-3 animate-spin" /> Saving…</>}
      {state === "saved" && <><Check className="size-3 text-success" /> Saved</>}
      {state === "error" && <span className="text-destructive">Couldn't save — <button type="button" className="underline" onClick={onRetry}>retry</button></span>}
      {state === "conflict" && <span className="text-destructive">Changed elsewhere — <button type="button" className="underline" onClick={onReload}>reload</button></span>}
    </span>
  );
}
