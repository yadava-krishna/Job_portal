import { useState, type FormEvent } from "react";
import { CalendarClock, ChevronDown, ChevronsUp, ChevronUp, ExternalLink, Gauge, Loader2, Lock, Plus, Users } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NativeSelect } from "@/components/app/common";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { SessionInput } from "./queries";
import type { Diagnosis, MentorAction, MentorNote, MentorSession } from "./types";
import { Chip, type Tone } from "./ui";

const confidenceTone: Record<string, Tone> = { high: "violet", medium: "route", low: "muted" };

/** One diagnosis as a block inside a list (the caller supplies the container). */
export function DiagnosisCard({ d }: { d: Diagnosis }) {
  return (
    <article className="space-y-1.5 py-3 first:pt-1 last:pb-0">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-[14px] font-semibold text-heading">{d.title}</h3>
        <Chip tone={confidenceTone[d.confidence] ?? "muted"} icon={<Gauge />} className="shrink-0">{d.confidence} confidence</Chip>
      </div>
      <ul className="list-disc space-y-0.5 pl-4 text-[13px] text-muted-foreground marker:text-border">{d.observations.map((o) => <li key={o}>{o}</li>)}</ul>
      <p className="text-[13px] text-foreground">{d.diagnosis}</p>
      {d.limitations && <p className="text-xs text-muted-foreground italic">{d.limitations}</p>}
    </article>
  );
}

const sourceLabels: Record<string, string> = {
  ai_mentor: "Suggested by the AI mentor",
  reflection: "From your weekly reflection",
  human_mentor: "Suggested by your mentor",
  self: "Added by you",
};

export function PriorityBadge({ priority }: { priority: string }) {
  if (priority === "high") return <Chip tone="caution" icon={<ChevronsUp />} className="capitalize">{priority}</Chip>;
  if (priority === "low") return <Chip tone="muted" icon={<ChevronDown />} className="capitalize">{priority}</Chip>;
  return <Chip tone="muted" icon={<ChevronUp />} className="capitalize">{priority}</Chip>;
}

export function ActionLine({ a }: { a: MentorAction }) {
  return (
    <div className="min-w-0">
      <div className={cn("text-[13.5px] font-medium text-foreground", a.completed_at && "text-muted-foreground line-through")}>{a.title}</div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <PriorityBadge priority={a.priority} />
        {a.due_on && <span className="inline-flex items-center gap-1"><CalendarClock className="size-3" aria-hidden />due {formatDate(a.due_on)}</span>}
        <span>{sourceLabels[a.source] ?? a.source}</span>
      </div>
      {a.reason && <p className="mt-0.5 text-xs text-muted-foreground">{a.reason}</p>}
    </div>
  );
}

/** Title + priority + due date (+ optional reason). Used for your own actions and a mentor's recommendation. */
export function ActionForm({ onSubmit, busy, withReason = false, submitLabel = "Add action" }: {
  onSubmit: (v: { title: string; reason: string; priority: string; due_on: string | null }, reset: () => void) => void;
  busy: boolean; withReason?: boolean; submitLabel?: string;
}) {
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [priority, setPriority] = useState("medium");
  const [due, setDue] = useState("");
  const reset = () => { setTitle(""); setReason(""); setPriority("medium"); setDue(""); };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (title.trim().length < 2) return toast.error("Describe the action in a few words.");
    onSubmit({ title: title.trim(), reason: reason.trim(), priority, due_on: due || null }, reset);
  };
  return (
    <form onSubmit={submit} className="@container space-y-2">
      <div className="grid grid-cols-2 gap-2 @xl:grid-cols-[1fr_7rem_9rem_auto]">
        <Input aria-label="Action" className="col-span-2 @xl:col-span-1" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Ask a former colleague for a referral" />
        <NativeSelect ariaLabel="Priority" value={priority} onChange={setPriority} className="min-w-0"
                      options={[{ value: "high", label: "High" }, { value: "medium", label: "Medium" }, { value: "low", label: "Low" }]} />
        <Input aria-label="Due date" type="date" className="min-w-0" value={due} onChange={(e) => setDue(e.target.value)} />
        <Button type="submit" className="col-span-2 h-10 @xl:col-span-1" disabled={busy}>{busy ? <Loader2 className="animate-spin" /> : <Plus />} {submitLabel}</Button>
      </div>
      {withReason && <Textarea aria-label="Why" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why this would help (the candidate sees this)" />}
    </form>
  );
}

export function NotesList({ notes, showVisibility = false }: { notes: MentorNote[]; showVisibility?: boolean }) {
  if (!notes.length) return <p className="text-xs text-muted-foreground">No notes yet.</p>;
  return (
    <ul className="space-y-2">
      {notes.map((n) => (
        <li key={n.id} className={cn("rounded-xl px-3 py-2 text-[13px]", n.by_me ? "ml-6 bg-route-tint/50" : "mr-6 bg-paper-sunk/80")}>
          <p className="whitespace-pre-wrap">{n.body}</p>
          <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
            {n.by_me ? "You" : "Them"} · {formatDate(n.created_at, true)}
            {showVisibility && (n.visibility === "private"
              ? <span className="inline-flex items-center gap-0.5"> · <Lock className="size-3" /> private, only you</span>
              : <span className="inline-flex items-center gap-0.5"> · <Users className="size-3" /> shared</span>)}
          </p>
        </li>
      ))}
    </ul>
  );
}

export function SessionRow({ s, who, actions }: { s: MentorSession; who?: string; actions?: React.ReactNode }) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-2 rounded-xl bg-paper-sunk/60 px-3 py-2.5 text-[13px] ring-1 ring-border/60">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5 font-medium text-heading">
          <CalendarClock className="size-3.5 text-route" aria-hidden /> {s.scheduled_at ? formatDate(s.scheduled_at, true) : "Time to be agreed"} · <span className="readout">{s.duration_minutes}</span> min
          {s.status !== "scheduled" && <Badge variant="outline" className="capitalize">{s.status}</Badge>}
        </div>
        {who && <div className="text-xs text-muted-foreground">With {who}</div>}
        {s.agenda && <p className="mt-1 text-xs whitespace-pre-wrap">{s.agenda}</p>}
        {s.summary && <p className="mt-1 text-xs text-muted-foreground whitespace-pre-wrap"><span className="font-medium">Summary:</span> {s.summary}</p>}
        {s.meeting_url && s.status === "scheduled" && (
          <a href={s.meeting_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-route underline-offset-2 hover:underline">Join meeting <ExternalLink className="size-3" /></a>
        )}
      </div>
      {actions}
    </li>
  );
}

export function SessionForm({ onSubmit, busy, submitLabel }: { onSubmit: (v: SessionInput, reset: () => void) => void; busy: boolean; submitLabel: string }) {
  const [when, setWhen] = useState("");
  const [duration, setDuration] = useState(30);
  const [url, setUrl] = useState("");
  const [agenda, setAgenda] = useState("");
  const reset = () => { setWhen(""); setDuration(30); setUrl(""); setAgenda(""); };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (url.trim() && !url.trim().startsWith("https://")) return toast.error("Meeting links must start with https://");
    onSubmit({ scheduled_at: when ? new Date(when).toISOString() : null, duration_minutes: duration, meeting_url: url.trim() || null, agenda: agenda.trim() || null }, reset);
  };
  return (
    <form onSubmit={submit} className="@container space-y-2 rounded-xl bg-paper-sunk/70 p-3 text-xs ring-1 ring-border/60 animate-in fade-in-0 slide-in-from-top-1 duration-200">
      <div className="grid grid-cols-[minmax(0,1fr)_5rem] gap-2">
        <label className="min-w-0"><span className="mb-1 block text-muted-foreground">When (optional)</span><Input type="datetime-local" className="min-w-0 px-2" value={when} onChange={(e) => setWhen(e.target.value)} /></label>
        <label className="min-w-0"><span className="mb-1 block text-muted-foreground">Minutes</span><Input type="number" className="min-w-0" min={10} max={180} value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></label>
      </div>
      <label className="block"><span className="mb-1 block text-muted-foreground">Meeting link (optional, https only)</span>
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://meet.google.com/…" /></label>
      <label className="block"><span className="mb-1 block text-muted-foreground">What to talk about</span>
        <Textarea rows={2} value={agenda} onChange={(e) => setAgenda(e.target.value)} placeholder="e.g. Review my last three rejections" /></label>
      <div className="flex justify-end"><Button size="sm" type="submit" disabled={busy}>{busy && <Loader2 className="animate-spin" />} {submitLabel}</Button></div>
    </form>
  );
}
