import { useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, ExternalLink, Loader2, MessagesSquare, Play, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, NativeSelect, PageHeader } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApplications, useJobs } from "@/services/queries";
import { useAddInsight, useInterviewPrep, usePractice, usePractices, useSaveAnswer, useStartPractice } from "@/features/growth/queries";
import type { InterviewPrep, Practice, PrepQuestion } from "@/features/growth/types";

const KIND_LABELS: Record<string, string> = {
  technical: "Skills from the job",
  behavioural: "Experience and behaviour",
  motivation: "Motivation",
  screening: "Screening",
};
const KIND_ORDER = ["technical", "behavioural", "motivation", "screening"];
const SOURCES = [
  { value: "glassdoor", label: "Glassdoor" }, { value: "ambitionbox", label: "AmbitionBox" }, { value: "reddit", label: "Reddit" },
  { value: "indeed", label: "Indeed" }, { value: "own", label: "My own experience" }, { value: "other", label: "Somewhere else" },
];
const sourceLabel = (s: string) => SOURCES.find((x) => x.value === s)?.label ?? s;

function groupByKind(qs: PrepQuestion[]): [string, PrepQuestion[]][] {
  const groups = new Map<string, PrepQuestion[]>();
  for (const q of qs) groups.set(q.kind, [...(groups.get(q.kind) ?? []), q]);
  const rank = (k: string) => (KIND_ORDER.includes(k) ? KIND_ORDER.indexOf(k) : KIND_ORDER.length);
  return [...groups.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));
}

export function InterviewPrepPage() {
  const [params, setParams] = useSearchParams();
  const jobId = params.get("job") ? Number(params.get("job")) : null;
  const practiceId = params.get("practice") ? Number(params.get("practice")) : null;
  const setParam = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next);
  };

  const saved = useJobs({ view: "saved", page_size: 100 });
  const apps = useApplications();
  const options = useMemo(() => {
    const seen = new Map<number, string>();
    for (const a of apps.data ?? []) if (a.user_job_id && a.status !== "WITHDRAWN") seen.set(a.user_job_id, `${a.job.title} · ${a.job.company} (application)`);
    for (const j of saved.data?.items ?? []) if (!seen.has(j.user_job_id)) seen.set(j.user_job_id, `${j.job.title} · ${j.job.company} (saved)`);
    return [...seen.entries()].map(([value, label]) => ({ value: String(value), label }));
  }, [apps.data, saved.data]);

  if (practiceId != null) return <PracticeView id={practiceId} onBack={() => setParam("practice", null)} />;

  return (
    <>
      <PageHeader title="Interview prep" description="Likely questions for a specific job, places to research the company, and a place to practise your answers." />
      <div className="mb-6 flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor="prep-job" className="text-muted-foreground">Job</label>
        <NativeSelect id="prep-job" ariaLabel="Choose a job" className="min-w-72 max-w-full" value={jobId ? String(jobId) : ""}
                      onChange={(v) => setParam("job", v || null)}
                      options={[{ value: "", label: options.length ? "Choose a job you saved or applied to…" : "No saved or applied jobs yet" },
                        ...options, ...(jobId && !options.some((o) => o.value === String(jobId)) ? [{ value: String(jobId), label: `Job #${jobId}` }] : [])]} />
      </div>
      {jobId == null ? (
        <EmptyState icon={<MessagesSquare className="size-8" />} title="Pick a job to prepare for">
          Questions are built from that job's own requirements and your profile, so they're specific to it. Save or apply to a job first if the list is empty.
        </EmptyState>
      ) : (
        <PrepForJob userJobId={jobId} onPractice={(id) => setParam("practice", String(id))} />
      )}
      <PastPractice className="mt-8" onOpen={(id) => setParam("practice", String(id))} />
    </>
  );
}

function PrepForJob({ userJobId, onPractice }: { userJobId: number; onPractice: (id: number) => void }) {
  const prep = useInterviewPrep(userJobId);
  const start = useStartPractice();
  if (prep.isLoading) return <div className="grid gap-4 lg:grid-cols-3"><Skeleton className="h-96 lg:col-span-2" /><Skeleton className="h-64" /></div>;
  if (prep.error || !prep.data) return <EmptyState title="Couldn't load interview prep">{errorMessage(prep.error)}</EmptyState>;
  const p = prep.data;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold">{p.job.title}</h2>
            <p className="text-sm text-muted-foreground">{p.job.company} · {p.questions.length} likely questions</p>
          </div>
          <Button disabled={start.isPending} onClick={() => start.mutate(userJobId, { onSuccess: (x) => onPractice(x.id), onError: (e) => toast.error(errorMessage(e)) })}>
            {start.isPending ? <Loader2 className="animate-spin" /> : <Play />} Start practice
          </Button>
        </div>
        {groupByKind(p.questions).map(([kind, qs]) => (
          <Card key={kind} className="gap-0 p-0">
            <div className="border-b px-4 py-2 text-sm font-medium">{KIND_LABELS[kind] ?? kind} <span className="text-muted-foreground">({qs.length})</span></div>
            <ol className="divide-y">
              {qs.map((q) => (
                <li key={q.id} className="px-4 py-3">
                  <p className="text-sm">{q.question}</p>
                  <p className="mt-1 text-xs text-muted-foreground"><span className="font-medium">Why this question:</span> {q.why}</p>
                </li>
              ))}
            </ol>
          </Card>
        ))}
      </div>
      <div className="space-y-4">
        <Card>
          <CardHeader><CardTitle className="text-base">Research the company</CardTitle><CardDescription>{p.reference_note}</CardDescription></CardHeader>
          <CardContent>
            <ul className="space-y-1.5 text-sm">
              {p.reference_links.map((l) => (
                <li key={l.url}><a href={l.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">{l.label}<ExternalLink className="size-3" /></a></li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Insights prep={p} />
      </div>
    </div>
  );
}

function Insights({ prep }: { prep: InterviewPrep }) {
  const add = useAddInsight(prep.job.user_job_id);
  const [source, setSource] = useState("glassdoor");
  const [url, setUrl] = useState("");
  const [question, setQuestion] = useState("");
  const [note, setNote] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!question.trim() && !note.trim()) return toast.error("Add the question you found or a note about it.");
    if (url.trim() && !/^https?:\/\//i.test(url.trim())) return toast.error("Links should start with https://");
    add.mutate({ company: prep.job.company, role: prep.job.title, source, url: url.trim() || null, question: question.trim() || null, note: note.trim() || null }, {
      onSuccess: () => { toast.success("Saved"); setUrl(""); setQuestion(""); setNote(""); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">What you found</CardTitle><CardDescription>Your saved notes for {prep.job.company}, with where they came from.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {prep.insights.length === 0 ? <p className="text-xs text-muted-foreground">Nothing saved yet.</p> : (
          <ul className="space-y-2">
            {prep.insights.map((i) => (
              <li key={i.id} className="rounded-lg border p-2 text-sm">
                {i.question && <p className="font-medium">{i.question}</p>}
                {i.note && <p className="text-muted-foreground">{i.note}</p>}
                <p className="mt-1 text-xs text-muted-foreground">
                  {sourceLabel(i.source)} · {formatDate(i.created_at)}
                  {i.url && <> · <a href={i.url} target="_blank" rel="noopener noreferrer" className="underline">link</a></>}
                </p>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={submit} className="space-y-2 rounded-lg border bg-muted/20 p-3">
          <h4 className="text-xs font-semibold">Save something you found</h4>
          <div className="grid grid-cols-2 gap-2">
            <NativeSelect ariaLabel="Where you found it" value={source} onChange={setSource} options={SOURCES} className="w-full" />
            <Input aria-label="Link" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://… (optional)" />
          </div>
          <Textarea aria-label="Question" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="A question people were asked" />
          <Textarea aria-label="Note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Your note: process, tips, rounds…" />
          <div className="flex justify-end"><Button size="sm" type="submit" disabled={add.isPending}>{add.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Save</Button></div>
        </form>
      </CardContent>
    </Card>
  );
}

function PastPractice({ onOpen, className }: { onOpen: (id: number) => void; className?: string }) {
  const list = usePractices();
  if (!list.data?.length) return null;
  return (
    <section className={className}>
      <h2 className="mb-2 text-sm font-semibold">Your practice sessions</h2>
      <Card className="gap-0 p-0">
        <ul className="divide-y text-sm">
          {list.data.map((p) => {
            const answered = Object.keys(p.answers ?? {}).length;
            return (
              <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-2">
                <div className="min-w-0">
                  <div className="truncate font-medium">{p.title}</div>
                  <div className="text-xs text-muted-foreground">{formatDate(p.created_at)} · {answered} of {p.questions.length} answered{p.status === "completed" ? " · finished" : ""}</div>
                </div>
                <Button size="xs" variant="outline" onClick={() => onOpen(p.id)}>{p.status === "completed" ? "Review" : "Continue"}</Button>
              </li>
            );
          })}
        </ul>
      </Card>
    </section>
  );
}

function PracticeView({ id, onBack }: { id: number; onBack: () => void }) {
  const practice = usePractice(id);
  const p = practice.data;
  return (
    <>
      <Button variant="ghost" size="sm" className="mb-3" onClick={onBack}><ArrowLeft /> Back to interview prep</Button>
      {!p ? (practice.error ? <EmptyState title="Couldn't load this practice session">{errorMessage(practice.error)}</EmptyState> : <Skeleton className="h-96" />) : (
        <>
          <PageHeader title={`Practice: ${p.title}`}
                      description="Answer out loud first, then type the gist. After saving you get a checklist of things strong answers usually include. It checks the answer's shape, not you." />
          <div className="space-y-4">
            {p.questions.map((q, i) => <PracticeQuestion key={q.id} practice={p} q={q} index={i} />)}
          </div>
        </>
      )}
    </>
  );
}

function PracticeQuestion({ practice, q, index }: { practice: Practice; q: PrepQuestion; index: number }) {
  const save = useSaveAnswer(practice.id);
  const prev = practice.answers?.[q.id];
  const fb = practice.feedback?.find((f) => f.question_id === q.id);
  const [answer, setAnswer] = useState(prev?.answer ?? "");
  const [rating, setRating] = useState<number | null>(prev?.self_rating ?? null);
  const dirty = answer.trim() !== (prev?.answer ?? "") || rating !== (prev?.self_rating ?? null);

  return (
    <Card className="gap-3 p-4">
      <div>
        <div className="text-xs text-muted-foreground">Question {index + 1} · {KIND_LABELS[q.kind] ?? q.kind}</div>
        <p className="font-medium">{q.question}</p>
        <p className="mt-0.5 text-xs text-muted-foreground"><span className="font-medium">Why this question:</span> {q.why}</p>
      </div>
      <Textarea aria-label={`Your answer to question ${index + 1}`} rows={5} value={answer} onChange={(e) => setAnswer(e.target.value)}
                placeholder="Situation, what you did, and the result" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 text-xs" role="group" aria-label="How did that feel?">
          <span className="mr-1 text-muted-foreground">How confident do you feel?</span>
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" aria-pressed={rating === n} onClick={() => setRating(rating === n ? null : n)}
                    className={cn("size-6 rounded-md border text-xs tabular-nums", rating === n ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>{n}</button>
          ))}
        </div>
        <Button size="sm" disabled={!answer.trim() || !dirty || save.isPending}
                onClick={() => save.mutate({ question_id: q.id, answer: answer.trim(), self_rating: rating }, { onError: (e) => toast.error(errorMessage(e)) })}>
          {save.isPending && <Loader2 className="animate-spin" />} {prev ? "Save again" : "Save answer"}
        </Button>
      </div>
      {fb && (
        <div className="rounded-lg bg-muted/60 p-3 text-sm" data-testid={`feedback-${q.id}`}>
          <div className="mb-1 flex items-center gap-2 text-xs font-medium">
            <CheckCircle2 className="size-3.5" /> Checklist: {fb.score}/{fb.out_of} <span className="font-normal text-muted-foreground">(automatic check of structure and detail, not a grade of you)</span>
          </div>
          <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">{fb.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </div>
      )}
    </Card>
  );
}
