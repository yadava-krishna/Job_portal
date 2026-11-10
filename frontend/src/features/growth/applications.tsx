import { useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Field, NativeSelect, TagInput } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useFunnel, useInterviewFeedback, useRecordRejection, useRejectionReasons } from "./queries";
import type { Funnel, RejectionResult } from "./types";

// ---------------------------------------------------------------- rejection

export function RejectionLabel({ reason, known, labels }: { reason: string | null | undefined; known: boolean | null | undefined; labels: Record<string, string> }) {
  if (!reason) return null;
  return (
    <span className="text-xs text-muted-foreground" data-testid="rejection-label">
      {labels[reason] ?? reason.replaceAll("_", " ")} <span className={cn(known ? "text-foreground" : "italic")}>{known ? "(employer said)" : "(your guess)"}</span>
    </span>
  );
}

type RejectTarget = { id: number; title: string; company: string };

export function RejectionDialog({ app, onClose, onSaved }: { app: RejectTarget | null; onClose: () => void; onSaved?: (r: RejectionResult) => void }) {
  return (
    <Dialog open={app != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        {app && <RejectionForm key={app.id} app={app} onClose={onClose} onSaved={onSaved} />}
      </DialogContent>
    </Dialog>
  );
}

function RejectionForm({ app, onClose, onSaved }: { app: RejectTarget; onClose: () => void; onSaved?: (r: RejectionResult) => void }) {
  const reasons = useRejectionReasons();
  const save = useRecordRejection();
  const [reason, setReason] = useState("");
  const [detail, setDetail] = useState("");
  const [known, setKnown] = useState<"yes" | "no" | "">("");
  const [tried, setTried] = useState(false);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (!reason || !known) return;
    save.mutate({ id: app.id, reason, detail: detail.trim() || null, known: known === "yes" }, {
      onSuccess: (r) => { toast.success("Rejection recorded"); onSaved?.(r); onClose(); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>Record rejection</DialogTitle>
        <DialogDescription>{app.title} at {app.company}. This moves the application to Rejected and helps spot patterns.</DialogDescription>
      </DialogHeader>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Reason" htmlFor="rej-reason" hint={tried && !reason ? "Choose a reason." : undefined}>
          <NativeSelect id="rej-reason" ariaLabel="Reason" value={reason} onChange={setReason} className="w-full"
                        options={[{ value: "", label: "Choose a reason…" }, ...(reasons.data ?? []).map((r) => ({ value: r.key, label: r.label }))]} />
        </Field>
        <Field label="Details (optional)" htmlFor="rej-detail">
          <Textarea id="rej-detail" rows={3} value={detail} onChange={(e) => setDetail(e.target.value)} placeholder="What they said, or what you think happened" />
        </Field>
        <fieldset className="space-y-1.5">
          <legend className="text-sm font-medium">Did the employer tell you this?</legend>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-1.5"><input type="radio" name="rej-known" value="yes" checked={known === "yes"} onChange={() => setKnown("yes")} /> Yes, they told me</label>
            <label className="flex items-center gap-1.5"><input type="radio" name="rej-known" value="no" checked={known === "no"} onChange={() => setKnown("no")} /> No, it's my guess</label>
          </div>
          <p className="text-xs text-muted-foreground">Guesses are kept separate from reasons the employer actually gave, so your patterns stay honest.</p>
          {tried && !known && <p role="alert" className="text-xs text-destructive">Please say whether the employer told you this or it's your guess.</p>}
        </fieldset>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" disabled={save.isPending}>{save.isPending && <Loader2 className="animate-spin" />} Save</Button>
        </div>
      </form>
    </>
  );
}

// ---------------------------------------------------------------- interview feedback

const TYPES = [
  { value: "", label: "Not sure" }, { value: "hr", label: "HR / recruiter" }, { value: "technical", label: "Technical" },
  { value: "behavioural", label: "Behavioural" }, { value: "case", label: "Case study" }, { value: "panel", label: "Panel" }, { value: "final", label: "Final round" },
];
const OUTCOMES = [
  { value: "", label: "Don't know yet" }, { value: "passed", label: "Moved forward" }, { value: "failed", label: "Didn't move forward" },
  { value: "cancelled", label: "Cancelled" }, { value: "scheduled", label: "Still waiting" },
];

type FeedbackTarget = { id: number; label: string };

export function InterviewFeedbackDialog({ interview, onClose, onSaved }: { interview: FeedbackTarget | null; onClose: () => void; onSaved?: () => void }) {
  return (
    <Dialog open={interview != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        {interview && <FeedbackForm key={interview.id} interview={interview} onClose={onClose} onSaved={onSaved} />}
      </DialogContent>
    </Dialog>
  );
}

function FeedbackForm({ interview, onClose, onSaved }: { interview: FeedbackTarget; onClose: () => void; onSaved?: () => void }) {
  const save = useInterviewFeedback();
  const [type, setType] = useState("");
  const [outcome, setOutcome] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [strengths, setStrengths] = useState("");
  const [weaknesses, setWeaknesses] = useState("");
  const [notes, setNotes] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate({
      id: interview.id, interview_type: type || null, outcome: outcome || null, topics, strengths: strengths.trim() || null,
      weaknesses: weaknesses.trim() || null, candidate_feedback: notes.trim() || null,
    }, {
      onSuccess: () => { toast.success("Thanks, saved. This feeds your mentor plan."); onSaved?.(); onClose(); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>How did it go?</DialogTitle>
        <DialogDescription>{interview.label}. Write it down while it's fresh.</DialogDescription>
      </DialogHeader>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type of interview" htmlFor="fb-type"><NativeSelect id="fb-type" value={type} onChange={setType} options={TYPES} className="w-full" /></Field>
          <Field label="Outcome" htmlFor="fb-outcome"><NativeSelect id="fb-outcome" value={outcome} onChange={setOutcome} options={OUTCOMES} className="w-full" /></Field>
        </div>
        <Field label="Topics they asked about" htmlFor="fb-topics" hint="Press Enter after each topic.">
          <TagInput id="fb-topics" value={topics} onChange={setTopics} placeholder="e.g. Excel, reconciliations, why this company" />
        </Field>
        <Field label="What went well" htmlFor="fb-strengths"><Textarea id="fb-strengths" rows={2} value={strengths} onChange={(e) => setStrengths(e.target.value)} /></Field>
        <Field label="What was hard" htmlFor="fb-weak"><Textarea id="fb-weak" rows={2} value={weaknesses} onChange={(e) => setWeaknesses(e.target.value)} /></Field>
        <Field label="Other notes" htmlFor="fb-notes"><Textarea id="fb-notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Anything the interviewer said, next steps" /></Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" disabled={save.isPending}>{save.isPending && <Loader2 className="animate-spin" />} Save</Button>
        </div>
      </form>
    </>
  );
}

// ---------------------------------------------------------------- funnel

const FUNNEL_STEPS: { key: keyof Funnel["counts"]; label: string; hint: string }[] = [
  { key: "prepared", label: "Prepared", hint: "Ready, not opened yet" },
  { key: "opened", label: "Opened", hint: "Opened on the job site" },
  { key: "pending", label: "Pending", hint: "Waiting for you to confirm" },
  { key: "applied", label: "Applied", hint: "Confirmed submitted" },
  { key: "screening", label: "Screening", hint: "Reached screening or later" },
  { key: "interview", label: "Interview", hint: "Reached an interview" },
  { key: "offer", label: "Offer", hint: "Got an offer" },
  { key: "rejected", label: "Rejected", hint: "Recorded as rejected" },
];

const pct = (v: number | null) => (v == null ? "—" : `${v}%`);

export function FunnelPanel() {
  const { data, isLoading } = useFunnel();
  if (isLoading) return <Card className="p-4"><Loader2 className="animate-spin" /></Card>;
  if (!data) return null;
  return <FunnelView data={data} title="Your results so far" />;
}

export function FunnelView({ data, title }: { data: Funnel; title: string }) {
  return (
    <Card className="gap-3 p-4" data-testid="funnel-panel">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="text-xs text-muted-foreground">Each count is kept separate: preparing or opening is not the same as applying.</p>
      </div>
      <div className="grid grid-cols-4 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-8">
        {FUNNEL_STEPS.map((s, i) => (
          <div key={s.key} className={cn("bg-card px-2 py-1.5", i === 3 && "bg-muted/40")} title={s.hint}>
            <div className="text-[11px] text-muted-foreground">{s.label}</div>
            <div className="text-lg font-semibold tabular-nums">{data.counts[s.key] ?? 0}</div>
          </div>
        ))}
      </div>
      <div className="grid gap-4 text-sm md:grid-cols-3">
        <div>
          <h3 className="mb-1 text-xs font-medium text-muted-foreground">Conversion</h3>
          <dl className="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5">
            <dt>Applied → screening</dt><dd className="tabular-nums">{pct(data.conversion.application_to_screening)}</dd>
            <dt>Applied → interview</dt><dd className="tabular-nums">{pct(data.conversion.application_to_interview)}</dd>
            <dt>Interview → offer</dt><dd className="tabular-nums">{pct(data.conversion.interview_to_offer)}</dd>
          </dl>
        </div>
        <div>
          <h3 className="mb-1 text-xs font-medium text-muted-foreground">Top rejection reasons</h3>
          {data.rejection_reasons.length === 0 ? <p className="text-xs text-muted-foreground">None recorded yet.</p> : (
            <ul className="space-y-0.5">
              {data.rejection_reasons.slice(0, 4).map((r) => <li key={r.reason} className="flex justify-between gap-2"><span className="truncate">{r.label}</span><span className="tabular-nums">{r.count}</span></li>)}
            </ul>
          )}
          {data.counts.rejected > 0 && <p className="mt-1 text-xs text-muted-foreground">{data.rejections_with_known_reason} of {data.counts.rejected} reason(s) came from the employer; the rest are guesses.</p>}
        </div>
        <div>
          <h3 className="mb-1 text-xs font-medium text-muted-foreground">By resume version</h3>
          {data.by_resume_version.length === 0 ? <p className="text-xs text-muted-foreground">No submitted applications yet.</p> : (
            <table className="w-full text-xs">
              <thead className="text-muted-foreground"><tr><th className="text-left font-normal">Version</th><th className="text-right font-normal">Applied</th><th className="text-right font-normal">Interviews</th></tr></thead>
              <tbody>{data.by_resume_version.map((v) => <tr key={v.version}><td className="truncate pr-2">{v.version}</td><td className="text-right tabular-nums">{v.applications}</td><td className="text-right tabular-nums">{v.interviews}</td></tr>)}</tbody>
            </table>
          )}
        </div>
      </div>
      {data.note && <p className="text-xs text-muted-foreground">{data.note}</p>}
    </Card>
  );
}
