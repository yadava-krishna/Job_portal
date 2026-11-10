import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, ChevronDown, Copy, Download, FileText, Loader2, Lock, RefreshCw } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/app/common";
import { downloadFile, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useJobs } from "@/services/queries";
import {
  applySuggestion, exportVersion, saveConflict, saveVersion, studioKeys, useCloneVersion, useStudioTemplates, useStudioVersion, withKeys,
  type Suggestion, type Version, type VersionSummary,
} from "./api";
import { DocumentEditor } from "./DocumentEditor";
import { CheckPanel, DesignPanel, HistoryPanel, SuggestionsPanel } from "./Panels";
import { PreviewPane } from "./PreviewPane";
import { AtsBadge, VersionStatusBadge } from "./parts";

type SaveState = "idle" | "pending" | "saving" | "saved" | "error" | "conflict";
const AUTOSAVE_MS = 1200;

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

  const draftRef = useRef<Version | null>(null);
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

  const update = (patch: Partial<Version>) => {
    if (!draftRef.current || readOnly) return;
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
      if (res.note) toast(res.note);
      else toast.success(format === "pdf" ? `PDF exported${res.page_count ? ` (${res.page_count} page${res.page_count === 1 ? "" : "s"})` : ""}` : "Word file exported");
    } catch (e) {
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

  if (query.isLoading || (!draft && !query.isError)) return <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> Loading resume…</div>;
  if (query.isError || !draft) {
    return (
      <EmptyState icon={<FileText className="size-8" />} title="Couldn't open this resume">
        {errorMessage(query.error, "It may have been deleted.")}
        <div className="mt-3"><Button size="sm" variant="outline" render={<Link to="/studio" />}>Back to Resume Studio</Button></div>
      </EmptyState>
    );
  }

  const templateName = (Array.isArray(templates.data) ? templates.data.find((t) => t.key === draft.template_key)?.name : undefined) ?? draft.template_name;
  const atsSafe = (Array.isArray(templates.data) ? templates.data.find((t) => t.key === draft.template_key)?.ats_safe : undefined) ?? draft.ats_safe;

  return (
    <>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <Button size="icon-sm" variant="ghost" aria-label="Back to all resumes" render={<Link to="/studio" />}><ArrowLeft /></Button>
          <div className="min-w-0">
            <label htmlFor="rv-name" className="sr-only">Resume name</label>
            <Input id="rv-name" value={draft.name} maxLength={120} disabled={readOnly} onChange={(e) => update({ name: e.target.value })}
                   className="h-8 w-full max-w-sm border-transparent px-1.5 text-lg font-semibold shadow-none hover:border-input focus-visible:border-input sm:w-80" />
            <div className="flex flex-wrap items-center gap-2 px-1.5 text-xs text-muted-foreground">
              <VersionStatusBadge status={draft.status} />
              <span>{templateName}</span><AtsBadge safe={atsSafe} />
              {!readOnly && <SaveStatus state={saveState} onRetry={() => void doSave()} onReload={() => void reload()} />}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => void makeCopy(draft)} disabled={clone.isPending}><Copy /> Make a copy</Button>
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button size="sm" disabled={!!exporting} />}>
              {exporting ? <Loader2 className="animate-spin" /> : <Download />} Export <ChevronDown />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuItem onClick={() => void exportAs("pdf")}><FileText /> PDF</DropdownMenuItem>
              <DropdownMenuItem onClick={() => void exportAs("docx")}><FileText /> Word (.docx)</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {readOnly && (
        <div role="status" className="mb-4 flex flex-col gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 sm:flex-row sm:items-center dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          <Lock className="size-4 shrink-0" />
          <p className="flex-1">This version was used in a submitted application and is kept exactly as sent. Make a copy to edit.</p>
          <Button size="sm" onClick={() => void makeCopy(draft)} disabled={clone.isPending}><Copy /> Make a copy</Button>
        </div>
      )}
      {saveState === "conflict" && !readOnly && (
        <div role="alert" className="mb-4 flex flex-col gap-2 rounded-lg border border-rose-300 bg-rose-50 p-3 text-sm text-rose-950 sm:flex-row sm:items-center dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-100">
          <AlertTriangle className="size-4 shrink-0" />
          <p className="flex-1">This resume was changed in another window or tab, so your latest edits here weren't saved. Reload to get the latest version.</p>
          <Button size="sm" variant="outline" onClick={() => void reload()}><RefreshCw /> Reload</Button>
        </div>
      )}

      <Tabs value={mobileView} onValueChange={(v) => setMobileView(v as "edit" | "preview")} className="mb-3 lg:hidden">
        <TabsList>
          <TabsTrigger value="edit">Edit</TabsTrigger>
          <TabsTrigger value="preview">Preview</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className={cn("min-w-0", mobileView !== "edit" && "hidden lg:block")}>
          <Tabs defaultValue="content">
            <div className="overflow-x-auto pb-1">
              <TabsList>
                <TabsTrigger value="content">Content</TabsTrigger>
                <TabsTrigger value="design">Design</TabsTrigger>
                <TabsTrigger value="check">Check</TabsTrigger>
                <TabsTrigger value="suggestions">Suggestions</TabsTrigger>
                <TabsTrigger value="history">History</TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="content" className="pt-2">
              <DocumentEditor sections={draft.sections} readOnly={readOnly} onChange={(sections) => update({ sections })} />
            </TabsContent>
            <TabsContent value="design" className="pt-2">
              <DesignPanel templateKey={draft.template_key} settings={draft.settings ?? {}} readOnly={readOnly}
                           onTemplate={(template_key) => update({ template_key })} onSettings={(settings) => update({ settings })} />
            </TabsContent>
            <TabsContent value="check" className="pt-2">
              <CheckPanel versionId={draft.id} jobId={jobId} onJob={setJobId} revision={savedRevision} />
            </TabsContent>
            <TabsContent value="suggestions" className="pt-2">
              <SuggestionsPanel versionId={draft.id} jobId={jobId} onJob={setJobId} sections={draft.sections} readOnly={readOnly} onAccept={accept} />
            </TabsContent>
            <TabsContent value="history" className="pt-2">
              <HistoryPanel version={draft} restoring={clone.isPending} onRestore={(v) => void makeCopy(v, `${v.name} (restored)`)} />
            </TabsContent>
          </Tabs>
        </div>
        <div className={cn("min-w-0 lg:sticky lg:top-4 lg:h-[calc(100dvh-8rem)] lg:self-start", mobileView !== "preview" && "hidden lg:block")}>
          <PreviewPane versionId={draft.id} revision={savedRevision} templateName={templateName} />
        </div>
      </div>
    </>
  );
}

function SaveStatus({ state, onRetry, onReload }: { state: SaveState; onRetry: () => void; onReload: () => void }) {
  return (
    <span className="inline-flex items-center gap-1" aria-live="polite">
      {state === "pending" && <span>Unsaved changes</span>}
      {state === "saving" && <><Loader2 className="size-3 animate-spin" /> Saving…</>}
      {state === "saved" && <><Check className="size-3 text-emerald-600" /> Saved</>}
      {state === "error" && <span className="text-rose-600">Couldn't save — <button type="button" className="underline" onClick={onRetry}>retry</button></span>}
      {state === "conflict" && <span className="text-rose-600">Changed elsewhere — <button type="button" className="underline" onClick={onReload}>reload</button></span>}
    </span>
  );
}
