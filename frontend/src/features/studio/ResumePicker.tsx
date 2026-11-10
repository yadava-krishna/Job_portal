import { useState } from "react";
import { Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { NativeSelect } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { useAttachResumeVersion, useStudioVersions, type AttachResult } from "./api";

/**
 * "Resume to use" for an application: pick a Resume Studio version. The backend exports it (cached) and records the
 * exact file checksum on the application; the version is locked once the application is confirmed as submitted.
 */
export function ResumeVersionPicker({ applicationId, initialVersionId, onAttached }: {
  applicationId: number; initialVersionId?: number | null; onAttached?: (r: AttachResult) => void;
}) {
  const versions = useStudioVersions();
  const attach = useAttachResumeVersion();
  const [selected, setSelected] = useState<number | null>(initialVersionId ?? null);
  const [result, setResult] = useState<AttachResult | null>(null);
  const list = (Array.isArray(versions.data) ? versions.data : []).filter((v) => v.status === "draft" || v.status === "locked");
  if (!versions.isLoading && !list.length) {
    return <p className="text-xs text-muted-foreground">Want a tailored resume for this job? Build one in Resume Studio and it can be chosen here.</p>;
  }

  const choose = (raw: string) => {
    if (!raw) return;
    const id = Number(raw);
    const prev = selected;
    setSelected(id);
    attach.mutate({ applicationId, versionId: id }, {
      onSuccess: (r) => { setResult(r); onAttached?.(r); toast.success("Resume recorded for this application"); },
      onError: (e) => { setSelected(prev); toast.error(errorMessage(e)); },
    });
  };

  const options = [
    ...(selected == null ? [{ value: "", label: "Uploaded resume (default)" }] : []),
    ...list.map((v) => ({ value: String(v.id), label: `${v.name} · ${v.template_name}${v.status === "locked" ? " · locked" : ""}` })),
  ];
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={`rv-pick-${applicationId}`} className="text-sm font-medium">Resume to use</label>
        <NativeSelect id={`rv-pick-${applicationId}`} value={selected == null ? "" : String(selected)} onChange={choose} options={options}
                      className="min-w-0 flex-1" />
        {(attach.isPending || versions.isLoading) && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
      </div>
      {result?.resume_checksum && (
        <p className="flex items-start gap-1.5 text-xs text-emerald-800 dark:text-emerald-200">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0" />
          <span>This exact file will be recorded with the application. Checksum <code className="font-mono">{result.resume_checksum.slice(0, 12)}</code></span>
        </p>
      )}
    </div>
  );
}
