import { useEffect, useId, useMemo, useState } from "react";
import { ChevronDown, Loader2, Lock, ShieldOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useApplyWorkspace } from "@/services/queries";
import type { PackageAnswer, PackageOut, WorkspaceAnswerInput } from "@/types/api";
import { answerHint, isLongText, sourceLabel } from "./copy";
import { Chip, WsSection } from "./parts";

interface Draft { answer: string; remember: boolean }

const statusChip = (a: PackageAnswer) =>
  a.sensitivity === "never" ? <Chip tone="neutral">You answer this</Chip>
    : a.status === "NEEDS_INPUT" ? <Chip tone="warn">Needs your answer</Chip>
      : a.status === "SUGGESTED" ? <Chip tone="check">Check</Chip>
        : <Chip tone="ok">Ready</Chip>;

function changed(a: PackageAnswer, d: Draft | undefined): boolean {
  if (!d) return false;
  if (d.answer.trim() !== (a.answer ?? "").trim()) return true;
  return d.remember !== a.remember_default && d.answer.trim() !== "" && a.scope !== "job";
}

/**
 * The questions this application asks, with what JobPilot already knows. Answers needing input come first, then
 * the ones to check, then the ready ones (collapsed). Nothing is remembered unless the user ticks "remember".
 */
export function AnswersEditor({ appId, answers, locked, onDirtyChange }: {
  appId: number; answers: PackageAnswer[]; locked: boolean; onDirtyChange?: (n: number) => void;
}) {
  const ws = useApplyWorkspace();
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [showReady, setShowReady] = useState(false);
  const readyId = useId();

  const { needs, check, never, ready } = useMemo(() => ({
    needs: answers.filter((a) => a.status === "NEEDS_INPUT" && a.sensitivity !== "never"),
    check: answers.filter((a) => a.status === "SUGGESTED" && a.sensitivity !== "never"),
    never: answers.filter((a) => a.sensitivity === "never"),
    ready: answers.filter((a) => a.status === "VERIFIED" && a.sensitivity !== "never"),
  }), [answers]);

  const dirty = answers.filter((a) => a.sensitivity !== "never" && changed(a, drafts[a.question]));
  useEffect(() => { onDirtyChange?.(dirty.length); }, [dirty.length, onDirtyChange]);

  const set = (a: PackageAnswer, patch: Partial<Draft>) => {
    setDrafts((d) => ({ ...d, [a.question]: { answer: d[a.question]?.answer ?? a.answer ?? "", remember: d[a.question]?.remember ?? a.remember_default, ...patch } }));
    setErrors((e) => { if (!(a.question in e)) return e; const { [a.question]: _drop, ...rest } = e; return rest; });
  };

  const save = () => {
    const items: WorkspaceAnswerInput[] = dirty.map((a) => {
      const d = drafts[a.question];
      return { question: a.question, answer: d.answer.trim() || null, remember: a.scope !== "job" && d.remember, ...(a.key ? { key: a.key } : {}) };
    });
    if (!items.length) return;
    ws.mutate({ kind: "answers", id: appId, items }, {
      onSuccess: (out) => {
        const res = out as PackageOut;
        const errs = Object.fromEntries((res.errors ?? []).map((e) => [e.question, e.error]));
        setErrors(errs);
        setDrafts((d) => Object.fromEntries(Object.entries(d).filter(([q]) => q in errs)));
        const ok = items.length - Object.keys(errs).length;
        const remembered = res.saved?.length ?? 0;
        if (ok > 0) {
          toast.success(`Saved. Locked in.${remembered ? ` ${remembered} remembered for future applications.` : " Used for this application only."}`);
        }
        if (Object.keys(errs).length) toast.error(`${Object.keys(errs).length} answer${Object.keys(errs).length === 1 ? "" : "s"} need a fix. See below.`);
      },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };

  const row = (a: PackageAnswer) => (
    <AnswerRow key={a.question} a={a} draft={drafts[a.question]} error={errors[a.question]} locked={locked} onChange={(p) => set(a, p)} />
  );

  if (!answers.length) {
    return (
      <WsSection title="Questions on the form">
        <p className="text-[13px] text-muted-foreground">No questions known yet. The employer's form may still ask some: check it when you open it.</p>
      </WsSection>
    );
  }

  return (
    <WsSection title="Questions on the form" testId="ws-answers"
               aside={<span className="readout">{needs.length} to answer · {check.length} to check · {ready.length} ready</span>}>
      <ul className="divide-y divide-border/70 rounded-xl ring-1 ring-border" data-testid="ws-answer-list">
        {needs.map(row)}
        {check.map(row)}
        {never.map(row)}
      </ul>
      {ready.length > 0 && (
        <div>
          <Button variant="ghost" size="sm" aria-expanded={showReady} aria-controls={readyId} onClick={() => setShowReady((v) => !v)} className="-ml-2">
            <ChevronDown className={cn("transition-transform duration-200", showReady && "rotate-180")} />
            {showReady ? "Hide" : "Show"} {ready.length} ready answer{ready.length === 1 ? "" : "s"}
          </Button>
          {showReady && <ul id={readyId} className="mt-1 divide-y divide-border/70 rounded-xl ring-1 ring-border" data-testid="ws-ready-list">{ready.map(row)}</ul>}
        </div>
      )}
      {!locked && (
        <div className="flex flex-wrap items-center justify-end gap-3">
          <span aria-live="polite" className="text-xs text-muted-foreground">
            {dirty.length ? `${dirty.length} unsaved answer${dirty.length === 1 ? "" : "s"}` : ""}
          </span>
          <Button size="sm" onClick={save} disabled={!dirty.length || ws.isPending}>
            {ws.isPending && ws.variables?.kind === "answers" && <Loader2 className="animate-spin" />} Save answers
          </Button>
        </div>
      )}
    </WsSection>
  );
}

function AnswerRow({ a, draft, error, locked, onChange }: {
  a: PackageAnswer; draft?: Draft; error?: string; locked: boolean; onChange: (p: Partial<Draft>) => void;
}) {
  const id = useId();
  const value = draft?.answer ?? a.answer ?? "";
  const remember = draft?.remember ?? a.remember_default;
  const src = sourceLabel(a.source);
  const hint = answerHint(a);
  const errId = `${id}-err`;
  const testId = a.sensitivity === "never" ? "ws-answer-never" : `ws-answer-${a.status.toLowerCase()}`;

  if (a.sensitivity === "never") {
    return (
      <li className="flex gap-2.5 px-3 py-2.5 text-[13px]" data-testid={testId}>
        <ShieldOff className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0">
          <div className="font-medium">{a.question}</div>
          <p className="text-xs text-muted-foreground">Answer this yourself on the form. JobPilot never answers or stores it.</p>
        </div>
      </li>
    );
  }

  const describedBy = [error ? errId : null, hint ? `${id}-hint` : null].filter(Boolean).join(" ") || undefined;
  const field = a.value_type === "boolean" ? (
    <div role="group" aria-labelledby={`${id}-q`} className="inline-flex rounded-full bg-paper-sunk p-0.5 ring-1 ring-border">
      {["Yes", "No"].map((v) => (
        <button key={v} type="button" aria-pressed={value.toLowerCase() === v.toLowerCase()} disabled={locked}
                onClick={() => onChange({ answer: v })}
                className={cn("min-w-14 rounded-full px-3 py-1 text-[13px] font-medium transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50",
                  value.toLowerCase() === v.toLowerCase() ? "bg-card text-heading shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground")}>
          {v}
        </button>
      ))}
    </div>
  ) : a.options.length > 0 && a.field_type !== "multi_select" ? (
    <select id={id} value={value} disabled={locked} aria-describedby={describedBy} aria-invalid={!!error || undefined}
            onChange={(e) => onChange({ answer: e.target.value })}
            className="h-9 w-full rounded-xl border bg-card px-3 text-sm outline-none transition-colors hover:border-foreground/25 focus-visible:ring-3 focus-visible:ring-ring/50 sm:max-w-sm">
      <option value="">Choose…</option>
      {value && !a.options.includes(value) && <option value={value}>{value}</option>}
      {a.options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  ) : isLongText(a) ? (
    <Textarea id={id} rows={3} value={value} disabled={locked} aria-describedby={describedBy} aria-invalid={!!error || undefined}
              onChange={(e) => onChange({ answer: e.target.value })} />
  ) : (
    <Input id={id} value={value} disabled={locked} placeholder={hint} aria-describedby={describedBy} aria-invalid={!!error || undefined}
           inputMode={a.value_type === "number" ? "decimal" : undefined} onChange={(e) => onChange({ answer: e.target.value })} className="sm:max-w-sm" />
  );

  return (
    <li className={cn("space-y-1.5 px-3 py-2.5", a.status === "NEEDS_INPUT" && "bg-caution-tint/20")} data-testid={testId}>
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <label id={`${id}-q`} htmlFor={a.value_type === "boolean" ? undefined : id} className="flex min-w-0 items-center gap-1.5 text-[13px] font-medium">
          {a.sensitivity === "private" && <Lock className="size-3.5 shrink-0 text-muted-foreground" aria-label="Private answer, stored encrypted" />}
          <span className="min-w-0">{a.question}</span>
          {a.origin === "employer" && a.required && <span className="text-xs font-normal text-destructive">Required</span>}
          {a.origin === "employer" && !a.required && a.requirement === "optional" && <span className="text-xs font-normal text-muted-foreground">Optional</span>}
          {a.origin === "employer" && !a.required && a.requirement === "unknown" && (
            <span className="text-xs font-normal text-caution" title="The employer's form doesn't say. Answer it unless you're sure it's optional.">Required? Not stated</span>
          )}
        </label>
        <div className="flex items-center gap-1.5">
          {statusChip(a)}
        </div>
      </div>
      {field}
      {hint && a.value_type !== "boolean" && <p id={`${id}-hint`} className="sr-only">{hint}</p>}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="min-w-0">
          {src && <span>{src}</span>}
          {a.origin === "employer" && <span>{src ? " · " : ""}The employer's question</span>}
          {a.origin === "listing" && <span>{src ? " · " : ""}From the job listing</span>}
          {a.reason && <span className="block text-foreground/75">{a.reason}</span>}
          {a.notes.map((n) => <span key={n} className="block text-caution">{n}</span>)}
        </span>
        {a.scope !== "job" && !locked && (
          <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-foreground/80">
            <input type="checkbox" checked={remember} aria-describedby={`${id}-q`} onChange={(e) => onChange({ remember: e.target.checked })} className="size-3.5 accent-[var(--route)]" />
            {a.scope === "company" ? "Remember for this employer only" : "Remember for future applications"}
          </label>
        )}
      </div>
      {error && <p id={errId} role="alert" className="text-xs font-medium text-destructive">{error}</p>}
    </li>
  );
}
