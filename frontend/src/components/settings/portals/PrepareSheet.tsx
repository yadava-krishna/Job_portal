// "Prepare application" for a portal: pick one of your jobs from that portal and continue in the Apply Workspace
// (resume choice, verified answers, opening the original posting, recording what you report).
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { EmptyState, LoadingState } from "@/components/app/common";
import { Chip } from "@/features/apply/parts";
import { api, errorMessage } from "@/lib/api";
import type { JobList, UserJob } from "@/types/api";
import { PLATFORM, type Portal } from "./types";

export function PrepareSheet({ p, onClose, onPick, onImport }: {
  p: Portal | null; onClose: () => void; onPick: (job: UserJob) => void; onImport: () => void;
}) {
  const jobs = useQuery({
    queryKey: ["portal-jobs", p?.portal], enabled: !!p,
    queryFn: async () => (await api.get<JobList>("/jobs", {
      params: new URLSearchParams({ view: "all", platform: PLATFORM[p!.portal], sort: "discovered", page_size: "25", group_similar: "false" }),
    })).data,
  });
  const items = (jobs.data?.items ?? []).filter((j) => j.status !== "dismissed");
  return (
    <Sheet open={!!p} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto data-[side=right]:w-full data-[side=right]:sm:max-w-lg" data-testid="prepare-sheet">
        {p && (
          <>
            <SheetHeader className="pr-12">
              <SheetTitle className="font-display text-[17px] font-bold text-heading">Prepare a {p.name} application</SheetTitle>
              <SheetDescription className="text-xs">
                Pick a job. The Apply Workspace asks which resume to use, fills in your verified answers, opens the posting on {p.name}, and records
                what you report back.
              </SheetDescription>
            </SheetHeader>
            <div className="px-4 pb-6">
              {jobs.isLoading ? <LoadingState /> : jobs.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(jobs.error)}</p>
                : items.length === 0 ? (
                  <EmptyState title={`No ${p.name} jobs in JobPilot yet`}>
                    <p className="mb-3">Import one by its link first, then come back here.</p>
                    <Button size="sm" onClick={onImport}><Link2 /> Import {p.name} job</Button>
                  </EmptyState>
                ) : (
                  <ul className="space-y-2" aria-label={`${p.name} jobs`}>
                    {items.map((j) => (
                      <li key={j.user_job_id} className="flex items-center gap-3 rounded-xl p-3 ring-1 ring-border">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-semibold text-heading">{j.job.title || "Untitled job"}</p>
                          <p className="truncate text-xs text-muted-foreground">{[j.job.company, j.job.location].filter(Boolean).join(" · ")}</p>
                        </div>
                        {j.status === "applied" && <Chip tone="ok">Applied</Chip>}
                        <Button size="sm" variant="outline" onClick={() => onPick(j)}>Prepare <ArrowRight /></Button>
                      </li>
                    ))}
                  </ul>
                )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
