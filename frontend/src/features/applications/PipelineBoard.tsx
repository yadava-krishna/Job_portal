import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { BellRing, GripVertical } from "lucide-react";
import { NativeSelect } from "@/components/app/common";
import { CompanyMark } from "@/components/app/JobCard";
import { formatDate, stageLabels } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Application, Stage } from "@/types/api";
import { daysSince, followUpState } from "./events";

const dotTone: Record<string, string> = {
  applied: "bg-heading/50", screening: "bg-violet", assessment: "bg-violet", interview: "bg-route", offer: "bg-success",
  rejected: "bg-destructive", archived: "bg-muted-foreground/50", withdrawn: "bg-muted-foreground/50",
};

/**
 * Kanban board of submitted applications. Cards can be dragged between columns; every card also has a
 * "Move to stage" menu, so the board works fully from the keyboard and with screen readers.
 * Columns scroll sideways when they don't fit; their headers stay pinned while a long column scrolls.
 */
export function PipelineBoard({ apps, stages, moveTo, onMove, onOpen, extra, focus, className }: {
  apps: Application[]; stages: Stage[]; moveTo: Stage[];
  onMove: (a: Application, stage: Stage) => void; onOpen: (id: number) => void;
  /** Per-card extra content (e.g. the rejection reason). */
  extra?: (a: Application) => ReactNode;
  /** A column to bring into view and emphasise (the stage chosen in the stage strip). */
  focus?: Stage | null;
  className?: string;
}) {
  const [dragId, setDragId] = useState<number | null>(null);
  const [over, setOver] = useState<Stage | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const stageOf = (a: Application): Stage => a.stage ?? "applied";
  const dragging = dragId != null ? apps.find((a) => a.id === dragId) : undefined;

  useEffect(() => {
    if (!focus || !scroller.current) return;
    const col = scroller.current.querySelector<HTMLElement>(`[data-stage="${focus}"]`);
    if (!col) return;
    const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    scroller.current.scrollTo?.({ left: Math.max(0, col.offsetLeft - 8), behavior: reduce ? "auto" : "smooth" });
  }, [focus]);

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
      <div ref={scroller} data-testid="pipeline-board"
           className={cn("flex gap-2 overflow-auto overscroll-x-contain rounded-2xl pb-2 [scrollbar-width:thin]", className)}>
        {stages.map((stage) => {
          const col = apps.filter((a) => stageOf(a) === stage);
          const isOver = over === stage && !!dragging && stageOf(dragging) !== stage;
          const focused = focus === stage;
          return (
            <section key={stage} aria-label={`${stageLabels[stage]}: ${col.length}`} data-stage={stage} data-over={isOver || undefined}
                     onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setOver(stage); }}
                     onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver((s) => (s === stage ? null : s)); }}
                     onDrop={(e) => drop(e, stage)}
                     className={cn("group/col relative flex min-w-[11.25rem] flex-1 basis-0 flex-col rounded-2xl bg-paper-sunk ring-1 ring-border/70",
                       "transition-[background-color,box-shadow] duration-200 ease-[cubic-bezier(.2,0,0,1)]",
                       focused && "ring-2 ring-route/40",
                       isOver && "bg-route-tint ring-2 ring-route/55")}>
              <h3 className={cn("sticky top-0 z-10 flex items-center gap-2 rounded-t-2xl px-3 pt-2.5 pb-2 text-[13px] font-semibold text-heading",
                "bg-paper-sunk transition-colors duration-200 group-data-[over]/col:bg-route-tint")}>
                <span aria-hidden className={cn("size-2 rounded-full", dotTone[stage] ?? "bg-border")} />
                {stageLabels[stage]}
                <span className="readout ml-auto rounded-full bg-card px-1.5 text-[11.5px] font-medium text-muted-foreground ring-1 ring-border">{col.length}</span>
              </h3>
              <div className="flex min-h-24 flex-1 flex-col gap-2 px-2 pb-2">
                {col.map((a) => {
                  const days = daysSince(a.submitted_at);
                  const fu = followUpState(a.follow_up_at);
                  const lifted = dragId === a.id;
                  return (
                    <article key={a.id} draggable aria-describedby="board-help" data-dragging={lifted || undefined}
                             onDragStart={(e) => { e.dataTransfer.setData("text/plain", String(a.id)); e.dataTransfer.effectAllowed = "move"; setDragId(a.id); }}
                             onDragEnd={() => { setDragId(null); setOver(null); }}
                             className={cn("group/card relative cursor-grab rounded-xl bg-card p-2.5 ring-1 ring-border select-none",
                               "transition-[transform,box-shadow,opacity] duration-200 ease-[cubic-bezier(.2,0,0,1)]",
                               "hover:shadow-[var(--shadow-raised)] hover:ring-route/25 active:cursor-grabbing active:scale-[1.02] active:shadow-[var(--shadow-overlay)]",
                               lifted && "z-20 scale-[1.02] -rotate-1 opacity-80 shadow-[var(--shadow-overlay)] ring-2 ring-route/50")}>
                      <div className="flex items-start gap-2">
                        <CompanyMark name={a.job.company || "?"} className="mt-0.5 size-7 rounded-lg text-[10.5px]" />
                        <div className="min-w-0 flex-1">
                          <button type="button" className="line-clamp-2 text-left text-[13px] leading-snug font-semibold text-heading decoration-route/40 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                                  onClick={() => onOpen(a.id)}>{a.job.title}</button>
                          <div className="truncate text-xs text-muted-foreground">{a.job.company}</div>
                        </div>
                        <GripVertical className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/40 transition-colors group-hover/card:text-muted-foreground" aria-hidden />
                      </div>
                      <div className="mt-2 flex items-center gap-2 text-[11.5px] text-muted-foreground">
                        {days != null && <span className="readout">{days === 0 ? "Applied today" : `Applied ${days}d ago`}</span>}
                        {a.match_score != null && <span className="readout ml-auto font-medium text-foreground/80" title="Match score">{Math.round(a.match_score)}%</span>}
                      </div>
                      {fu && (
                        <div className={cn("mt-1.5 inline-flex items-center gap-1 rounded-full px-1.5 py-px text-[11.5px]",
                          fu === "due" ? "bg-caution-tint font-medium text-caution" : "text-muted-foreground")}>
                          <BellRing className="size-3" aria-hidden /><span>{fu === "due" ? "Follow-up due" : `Follow up ${formatDate(a.follow_up_at!)}`}</span>
                        </div>
                      )}
                      {extra?.(a) && <div className="mt-1">{extra(a)}</div>}
                      <NativeSelect ariaLabel={`Move ${a.job.title} to stage`} value={stageOf(a)} onChange={(v) => onMove(a, v as Stage)}
                                    className="mt-2 h-7 w-full rounded-lg bg-paper-sunk/60 px-2 text-xs text-muted-foreground hover:text-foreground"
                                    options={moveTo.map((s) => ({ value: s, label: s === stageOf(a) ? `In ${stageLabels[s]}` : `Move to ${stageLabels[s]}` }))} />
                    </article>
                  );
                })}
                {isOver && (
                  <div aria-hidden className="flex h-14 items-center justify-center rounded-xl border-2 border-dashed border-route/45 text-xs font-medium text-route animate-in fade-in-0 zoom-in-95 duration-150">
                    Drop to move to {stageLabels[stage]}
                  </div>
                )}
                {!col.length && !isOver && <p className="px-1 py-4 text-center text-xs text-muted-foreground/80">{dragging ? "Drop a card here" : "Nothing here yet"}</p>}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
