import { useId, useState } from "react";
import { ChevronDown, Eye, EyeOff, Loader2, Lock, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { LoadingState } from "@/components/app/common";
import { Panel } from "@/components/settings/primitives";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAnswerMemory, useDeleteMemoryAnswer, useSaveMemoryAnswer } from "@/services/queries";
import type { MemoryAnswer } from "@/types/api";
import { answerHint, GROUP_LABELS, GROUP_ORDER, memorySourceLabel } from "./copy";
import { Chip } from "./parts";

const rowKey = (r: Pick<MemoryAnswer, "key" | "scope_ref">) => `${r.key}|${r.scope_ref}`;

/**
 * Settings -> Verified answers -> Remembered answers: what JobPilot reuses on application forms, only because the user
 * ticked "remember". Private answers (pay, work authorisation) stay masked until "Show", which fetches them on request.
 */
export function RememberedAnswers() {
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const list = useAnswerMemory(false);
  const reveal = useAnswerMemory(true, revealed.size > 0);
  const [forget, setForget] = useState<MemoryAnswer | null>(null);
  const del = useDeleteMemoryAnswer();

  const plain = (r: MemoryAnswer): string | null => {
    if (!r.masked) return r.answer;
    if (!revealed.has(rowKey(r))) return null;
    return reveal.data?.find((x) => rowKey(x) === rowKey(r))?.answer ?? null;
  };
  const toggle = (r: MemoryAnswer) => setRevealed((s) => {
    const n = new Set(s);
    if (n.has(rowKey(r))) n.delete(rowKey(r)); else n.add(rowKey(r));
    return n;
  });

  const rows = Array.isArray(list.data) ? list.data : [];
  const groups = GROUP_ORDER.map((g) => ({ g, rows: rows.filter((r) => (GROUP_ORDER.includes(r.group) ? r.group : "other") === g) })).filter((x) => x.rows.length);
  const stale = rows.filter((r) => r.stale).length;

  return (
    <Panel title="Remembered answers"
           description={<>Answers you chose to remember while applying. JobPilot reuses them on forms that ask the same thing, and asks you to check time-sensitive ones (pay, notice period) again after a while. Private answers are stored encrypted.</>}
           actions={rows.length > 0 ? <span className="readout text-xs text-muted-foreground">{rows.length} saved{stale ? ` · ${stale} to check` : ""}</span> : undefined}>
      <div data-testid="remembered-answers">
        {list.isLoading ? <LoadingState /> : list.isError ? <p role="alert" className="text-sm text-destructive">{errorMessage(list.error)}</p> : !rows.length ? (
          <p className="rounded-xl bg-paper-sunk px-4 py-3 text-[13px] text-muted-foreground">
            Nothing remembered yet. When you answer a question in the Apply Workspace and tick "Remember for future applications", it shows up here.
          </p>
        ) : (
          <div className="space-y-5">
            {groups.map(({ g, rows: rs }) => (
              <div key={g} role="group" aria-label={GROUP_LABELS[g] ?? g}>
                <h4 className="mb-1.5 text-[13px] font-semibold text-heading">{GROUP_LABELS[g] ?? g}</h4>
                <ul className="divide-y divide-border/70 rounded-xl ring-1 ring-border">
                  {rs.map((r) => (
                    <MemoryRow key={rowKey(r)} row={r} shown={plain(r)} revealed={revealed.has(rowKey(r))} revealing={reveal.isFetching && revealed.has(rowKey(r))}
                               onToggle={() => toggle(r)} onForget={() => setForget(r)} onReveal={() => { if (!revealed.has(rowKey(r))) toggle(r); }} />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
      <Dialog open={forget != null} onOpenChange={(o) => { if (!o && !del.isPending) setForget(null); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="font-display text-[19px] font-bold text-heading">Forget this answer?</DialogTitle>
            <DialogDescription>
              JobPilot stops reusing "{forget?.label}" and its history is deleted. Forms that ask it will show it as needing your answer again.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setForget(null)} disabled={del.isPending}>Keep it</Button>
            <Button variant="destructive" disabled={del.isPending} onClick={() => {
              if (!forget) return;
              del.mutate({ key: forget.key, scopeRef: forget.scope_ref || undefined }, {
                onSuccess: () => { toast("Forgotten."); setForget(null); },
                onError: (e) => toast.error(errorMessage(e)),
              });
            }}>{del.isPending ? <Loader2 className="animate-spin" /> : <Trash2 />} Forget it</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Panel>
  );
}

function MemoryRow({ row, shown, revealed, revealing, onToggle, onForget, onReveal }: {
  row: MemoryAnswer; shown: string | null; revealed: boolean; revealing: boolean; onToggle: () => void; onForget: () => void; onReveal: () => void;
}) {
  const save = useSaveMemoryAnswer();
  const [editing, setEditing] = useState(false);
  // null until the user types: shows the saved answer (a private one once it has been fetched).
  const [typed, setValue] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState(false);
  const id = useId();
  const scoped = !!row.scope_ref;
  const original = shown ?? "";
  const value = typed ?? original;

  const startEdit = () => {
    if (row.masked && !revealed) onReveal();
    setValue(null);
    setError(null);
    setEditing(true);
  };
  const submit = () => {
    const answer = value.trim();
    if (!answer) { setError("Type an answer, or use Forget to remove it."); return; }
    save.mutate({ key: row.key, question: row.question ?? row.label, answer }, {
      onSuccess: () => { setEditing(false); toast.success("Saved. Locked in."); },
      onError: (e) => setError(errorMessage(e)),
    });
  };

  return (
    <li className="px-3 py-2.5 text-[13px]" data-testid={`memory-${row.key}`}>
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {row.sensitivity === "private" && <Lock className="size-3.5 text-muted-foreground" aria-label="Private, stored encrypted" />}
            <span id={`${id}-label`} className="font-medium">{row.label}</span>
            {row.stale && <Chip tone="warn" title={row.revalidate_days ? `Time-sensitive: check every ${row.revalidate_days} days` : undefined}>Check this</Chip>}
            {scoped && <Chip tone="neutral">One employer only</Chip>}
          </div>
          {!editing && (
            <div className="mt-0.5 text-foreground">
              {row.masked && !revealed ? <span className="tracking-widest text-muted-foreground" aria-label="Hidden">••••••</span>
                : revealing && shown == null ? <Loader2 className="inline size-3.5 animate-spin" aria-label="Loading" />
                  : <span className="break-words" data-testid="memory-answer">{shown ?? "—"}</span>}
            </div>
          )}
          <div className="mt-0.5 text-xs text-muted-foreground">
            {memorySourceLabel(row.source)}{row.last_confirmed_at ? <> · last confirmed <span className="readout">{formatDate(row.last_confirmed_at)}</span></> : null}
          </div>
        </div>
        {!editing && (
          <div className="flex items-center gap-1">
            {row.masked && (
              <Button size="sm" variant="ghost" aria-pressed={revealed} data-guard-ignore onClick={onToggle} aria-label={`${revealed ? "Hide" : "Show"} ${row.label}`}>
                {revealed ? <EyeOff /> : <Eye />} {revealed ? "Hide" : "Show"}
              </Button>
            )}
            {!scoped && <Button size="icon-sm" variant="ghost" aria-label={`Edit ${row.label}`} onClick={startEdit}><Pencil /></Button>}
            <Button size="icon-sm" variant="ghost" aria-label={`Forget ${row.label}`} onClick={onForget}><Trash2 /></Button>
          </div>
        )}
      </div>
      {editing && (
        <div className="mt-2 space-y-1.5">
          <Input id={`${id}-edit`} aria-labelledby={`${id}-label`} value={value} placeholder={answerHint({ value_type: row.value_type, unit: row.unit })}
                 aria-invalid={!!error || undefined} autoFocus onChange={(e) => { setValue(e.target.value); setError(null); }}
                 onKeyDown={(e) => { if (e.key === "Enter") submit(); if (e.key === "Escape") setEditing(false); }}
                 {...(value === original ? { "data-guard-ignore": "" } : {})} />
          {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          {/* Marked as a save bar so the Settings unsaved-changes guard can save this edit; laid out inline, not sticky. */}
          <div data-save-bar className="!static !m-0 !flex !justify-end !gap-2 !rounded-none !border-0 !bg-transparent !p-0 !shadow-none !ring-0">
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={save.isPending}>Cancel</Button>
            <Button size="sm" onClick={submit} disabled={save.isPending}>{save.isPending && <Loader2 className="animate-spin" />} Save</Button>
          </div>
        </div>
      )}
      {row.history.length > 0 && (
        <div className="mt-1">
          <button type="button" aria-expanded={history} onClick={() => setHistory((h) => !h)}
                  className="inline-flex items-center gap-1 rounded text-xs text-route hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none">
            <ChevronDown className={cn("size-3.5 transition-transform duration-200", history && "rotate-180")} aria-hidden />
            History ({row.history.length})
          </button>
          {history && (
            <ol className="mt-1 space-y-0.5 border-l-2 border-border pl-3 text-xs text-muted-foreground">
              {row.history.map((h, i) => (
                <li key={`${h.at}-${i}`}>
                  <span className="readout">{h.at ? formatDate(h.at, true) : "Earlier"}</span> · {memorySourceLabel(h.source)}
                  {h.answer && h.answer !== "(hidden)" ? <>: <span className="text-foreground">{h.answer}</span></> : row.masked ? ": hidden" : null}
                  {h.question && h.question !== row.label && <span className="block italic">“{h.question}”</span>}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </li>
  );
}
