import { useId, useState } from "react";
import { Download, Eye, FileText, Loader2, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { downloadFile, errorMessage, previewFile } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApplyWorkspace, useResumes } from "@/services/queries";
import { exportVersion, fetchPreview, useStudioVersions } from "@/features/studio/api";
import { templateName } from "@/features/studio/templateCopy";
import type { PackageResume } from "@/types/api";
import { Chip, WsSection } from "./parts";

interface Option { value: string; kind: "upload" | "studio"; id: number; name: string; meta: string; pdf: boolean }

const keyOf = (r: Pick<PackageResume, "kind" | "id">) => (r.kind && r.id ? `${r.kind}:${r.id}` : "");

async function previewStudio(id: number) {
  const win = window.open("", "_blank");  // synchronously, so pop-up blockers allow it
  try {
    const { blob } = await fetchPreview(id);
    const url = URL.createObjectURL(blob);
    if (win) win.location.href = url;
    else window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (e) {
    win?.close();
    throw e;
  }
}

/**
 * Which resume goes with this application: an upload or a Resume Studio version. The user's pick is recorded on the
 * application and Smart Apply attaches exactly that file; it is never swapped back to the default behind their back.
 */
export function ResumeChooser({ appId, resume, locked }: { appId: number; resume: PackageResume; locked: boolean }) {
  const uploads = useResumes();
  const versions = useStudioVersions();
  const ws = useApplyWorkspace();
  const name = useId();
  const current = keyOf(resume);
  // The row ticked here but not yet used; otherwise the resume the application has.
  const [picked, setPick] = useState<string | null>(null);
  const pick = picked ?? current;
  const [failed, setFailed] = useState<string | null>(null);

  const options: Option[] = [
    ...(Array.isArray(uploads.data) ? uploads.data : []).map((r) => ({
      value: `upload:${r.id}`, kind: "upload" as const, id: r.id, name: r.original_filename, pdf: r.original_filename.toLowerCase().endsWith(".pdf"),
      meta: `Uploaded ${formatDate(r.uploaded_at)}${r.is_active ? " · your default" : ""}`,
    })),
    ...(Array.isArray(versions.data) ? versions.data : []).filter((v) => v.status === "draft" || v.status === "locked").map((v) => ({
      value: `studio:${v.id}`, kind: "studio" as const, id: v.id, name: v.name, pdf: true,
      meta: `Resume Studio · ${templateName(v.template_key, v.template_name)}${v.status === "locked" ? " · locked" : ""}`,
    })),
  ];
  if (current && !options.some((o) => o.value === current) && resume.kind && resume.id) {
    options.unshift({ value: current, kind: resume.kind, id: resume.id, name: resume.name ?? "Chosen resume", meta: "Chosen for this application", pdf: resume.format !== "docx" });
  }
  const loading = uploads.isLoading || versions.isLoading;
  const chosen = options.find((o) => o.value === pick);

  const use = () => {
    if (!chosen) return;
    setFailed(null);
    ws.mutate({ kind: "resume", id: appId, choice: { kind: chosen.kind, id: chosen.id, ...(chosen.kind === "studio" ? { format: "pdf" as const } : {}) } }, {
      onSuccess: (out) => {
        if (keyOf(out.package.resume) !== chosen.value) {
          // The server didn't take it: say so rather than quietly using another file.
          setFailed(`${chosen.name} couldn't be used for this application. Pick it again or choose another.`);
          return;
        }
        setPick(null);
        toast.success("Resume locked in for this application.");
      },
      onError: (e) => setFailed(errorMessage(e)),
    });
  };

  const preview = (o: Option) => {
    const run = o.kind === "upload" ? previewFile(`/profile/resumes/${o.id}/file?inline=true`) : previewStudio(o.id);
    run.catch((e) => toast.error(errorMessage(e)));
  };
  const download = (o: Option) => {
    const run = o.kind === "upload" ? downloadFile(`/profile/resumes/${o.id}/file`, o.name)
      : exportVersion(o.id, "pdf").then((r) => downloadFile(r.download_url, `${o.name}.pdf`));
    run.catch((e) => toast.error(errorMessage(e)));
  };

  return (
    <WsSection title="Resume for this application" testId="ws-resume"
               aside={resume.kind ? (resume.selected_by === "you" ? <Chip tone="ok">Chosen by you</Chip> : <Chip tone="neutral">Your default resume</Chip>) : null}>
      {loading && !options.length ? (
        <p className="flex items-center gap-2 text-[13px] text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Loading your resumes…</p>
      ) : !options.length ? (
        <p className="rounded-xl bg-caution-tint/40 px-3 py-2.5 text-[13px] ring-1 ring-caution/20">
          No resume yet. <a href="#/settings?tab=profile" className="font-medium text-route underline underline-offset-2">Upload one in Settings</a> or build one in Resume Studio.
        </p>
      ) : (
        <div role="radiogroup" aria-label="Resume for this application" className="divide-y divide-border/70 overflow-hidden rounded-xl ring-1 ring-border">
          {options.map((o) => {
            const isCurrent = o.value === current;
            return (
              <div key={o.value} className={cn("flex items-center gap-2 px-3 py-2 transition-colors duration-150", o.value === pick ? "bg-route-tint/50" : "hover:bg-muted/50")}>
                <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 text-[13px]">
                  <input type="radio" name={name} value={o.value} checked={o.value === pick} disabled={locked}
                         onChange={() => setPick(o.value)} className="size-4 shrink-0 accent-[var(--route)]" />
                  {o.kind === "studio" ? <Sparkles className="size-4 shrink-0 text-violet" aria-hidden /> : <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />}
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{o.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">{o.meta}{isCurrent ? " · used for this application" : ""}</span>
                  </span>
                </label>
                {o.pdf && <Button size="icon-sm" variant="ghost" aria-label={`Preview ${o.name}`} onClick={() => preview(o)}><Eye /></Button>}
                <Button size="icon-sm" variant="ghost" aria-label={`Download ${o.name}`} onClick={() => download(o)}><Download /></Button>
              </div>
            );
          })}
        </div>
      )}
      {failed && <p role="alert" className="text-[13px] text-destructive">{failed}</p>}
      {locked ? <p className="text-xs text-muted-foreground">This application was submitted, so its resume can't change.</p> : options.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">Smart Apply attaches exactly the resume you choose here.</p>
          <Button size="sm" variant={pick !== current ? "default" : "outline"} disabled={!chosen || pick === current || ws.isPending} onClick={use}>
            {ws.isPending && ws.variables?.kind === "resume" && <Loader2 className="animate-spin" />} Use this resume
          </Button>
        </div>
      )}
    </WsSection>
  );
}
