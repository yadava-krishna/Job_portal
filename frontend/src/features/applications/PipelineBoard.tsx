import { useState, type DragEvent, type ReactNode } from "react";
import { BellRing, GripVertical } from "lucide-react";
import { Card } from "@/components/ui/card";
import { NativeSelect, PlatformBadge, ScoreBadge } from "@/components/app/common";
import { formatDate, stageLabels } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Application, Stage } from "@/types/api";
import { daysSince, followUpState } from "./events";

/**
 * Kanban board of submitted applications. Cards can be dragged between columns; every card also has a
 * "Move to stage" menu, so the board works fully from the keyboard and with screen readers.
 */
export function PipelineBoard({ apps, stages, moveTo, onMove, onOpen, extra }: {
  apps: Application[]; stages: Stage[]; moveTo: Stage[];
  onMove: (a: Application, stage: Stage) => void; onOpen: (id: number) => void;
  /** Per-card extra content (e.g. the rejection reason). */
  extra?: (a: Application) => ReactNode;
}) {
  const [dragId, setDragId] = useState<number | null>(null);
  const [over, setOver] = useState<Stage | null>(null);
  const stageOf = (a: Application): Stage => a.stage ?? "applied";

  const drop = (e: DragEvent, stage: Stage) => {
    e.preventDefault();
    setOver(null);
    const id = Number(e.dataTransfer.getData("text/plain")) || dragId;
    const a = apps.find((x) => x.id === id);
    setDragId(null);
    if (a && stageOf(a) !== stage) onMove(a, stage);
  };

  return (
    <div>
      <p id="board-help" className="sr-only">Drag a card to another column, or use the Move to stage menu on the card.</p>
      <div className="flex gap-3 overflow-x-auto pb-2" data-testid="pipeline-board">
        {stages.map((stage) => {
          const col = apps.filter((a) => stageOf(a) === stage);
          return (
            <section key={stage} aria-label={`${stageLabels[stage]}: ${col.length}`} data-stage={stage}
                     onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setOver(stage); }}
                     onDragLeave={() => setOver((s) => (s === stage ? null : s))}
                     onDrop={(e) => drop(e, stage)}
                     className={cn("flex min-w-56 flex-1 basis-0 flex-col rounded-xl bg-muted/50 p-2.5 transition-colors",
                                   over === stage && "bg-primary/10 ring-2 ring-primary/40")}>
              <h3 className="mb-2 flex items-center justify-between px-1 text-sm font-medium">
                {stageLabels[stage]}<span className="tabular-nums text-muted-foreground">{col.length}</span>
              </h3>
              <div className="flex min-h-16 flex-col gap-2">
                {col.map((a) => {
                  const days = daysSince(a.submitted_at);
                  const fu = followUpState(a.follow_up_at);
                  return (
                    <Card key={a.id} draggable aria-describedby="board-help"
                          onDragStart={(e) => { e.dataTransfer.setData("text/plain", String(a.id)); e.dataTransfer.effectAllowed = "move"; setDragId(a.id); }}
                          onDragEnd={() => { setDragId(null); setOver(null); }}
                          className={cn("cursor-grab gap-1.5 p-2.5 active:cursor-grabbing", dragId === a.id && "opacity-50")}>
                      <div className="flex items-start gap-1">
                        <GripVertical className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                        <button className="min-w-0 text-left text-sm font-medium hover:underline" onClick={() => onOpen(a.id)}>{a.job.title}</button>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        <span className="truncate">{a.job.company}</span> <PlatformBadge platform={a.job.platform} />
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        {days != null && <span>{days === 0 ? "Applied today" : `Applied ${days}d ago`}</span>}
                        <ScoreBadge score={a.match_score} />
                      </div>
                      {fu && (
                        <div className={cn("flex items-center gap-1 text-xs", fu === "due" ? "font-medium text-amber-700 dark:text-amber-400" : "text-muted-foreground")}>
                          <BellRing className="size-3" aria-hidden /> {fu === "due" ? "Follow-up due" : `Follow up ${formatDate(a.follow_up_at!)}`}
                        </div>
                      )}
                      {extra?.(a)}
                      <NativeSelect ariaLabel={`Move ${a.job.title} to stage`} value={stageOf(a)} onChange={(v) => onMove(a, v as Stage)}
                                    className="h-7 w-full text-xs" options={moveTo.map((s) => ({ value: s, label: stageLabels[s] }))} />
                    </Card>
                  );
                })}
                {!col.length && <p className="px-1 py-3 text-center text-xs text-muted-foreground">Drop a card here</p>}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
