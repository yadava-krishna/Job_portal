import { useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowLeft, Check, ExternalLink, History, ListChecks, Loader2, MessagesSquare, NotebookPen, Play, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
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
import { Panel } from "@/features/growth/ui";

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
  const past = <PastPractice onOpen={(id) => setParam("practice", String(id))} />;

  return (
    <>
      <PageHeader eyebrow="Interview practice" title={<>Walk in with <em>main-character</em> energy.</>}
                  description="Likely questions for a specific job, places to research the company, and a place to practise your answers." />
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-2xl bg-card px-4 py-2.5 ring-1 ring-border">
        <label htmlFor="prep-job" className="text-[13px] font-medium text-heading">Job</label>
        <NativeSelect id="prep-job" ariaLabel="Choose a job" className="h-9 min-w-0 flex-1 rounded-full sm:max-w-xl" value={jobId ? String(jobId) : ""}
                      onChange={(v) => setParam("job", v || null)}
                      options={[{ value: "", label: options.length ? "Choose a job you saved or applied to…" : "No saved or applied jobs yet" },
                        ...options, ...(jobId && !options.some((o) => o.value === String(jobId)) ? [{ value: String(jobId), label: `Job #${jobId}` }] : [])]} />
        <span className="hidden text-xs text-muted-foreground md:inline">Questions come from that job's own requirements and your profile.</span>
      </div>
      {jobId == null ? (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <EmptyState icon={<MessagesSquare className="size-8" />} title="Pick a job and we'll prep you for it">
            Questions are built from that job's own requirements and your profile, so they're specific to it. Save or apply to a job first if the list is empty.
          </EmptyState>
          {past}
        </div>
      ) : (
        <PrepForJob userJobId={jobId} onPractice={(id) => setParam("practice", String(id))} aside={past} />
      )}
    </>
  );
}

function PrepForJob({ userJobId, onPractice, aside }: { userJobId: number; onPractice: (id: number) => void; aside: React.ReactNode }) {
  const prep = useInterviewPrep(userJobId);
  const start = useStartPractice();
  if (prep.isLoading) return <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]"><Skeleton className="h-96 rounded-2xl" /><Skeleton className="h-64 rounded-2xl" /></div>;
  if (prep.error || !prep.data) return <EmptyState title="Couldn't load interview prep">{errorMessage(prep.error)}</EmptyState>;
  const p = prep.data;
  let n = 0;

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <Panel title={p.job.title} icon={<MessagesSquare />} description={<>{p.job.company} · <span className="readout">{p.questions.length}</span> likely questions</>}
             bodyClassName="px-0 pb-1 sm:px-0"
             actions={
               <Button disabled={start.isPending} onClick={() => start.mutate(userJobId, { onSuccess: (x) => onPractice(x.id), onError: (e) => toast.error(errorMessage(e)) })}>
                 {start.isPending ? <Loader2 className="animate-spin" /> : <Play />} Start practice
               </Button>
             }>
        {groupByKind(p.questions).map(([kind, qs]) => (
          <section key={kind} className="border-t border-border/70 first:border-t-0">
            <h3 className="flex items-center gap-2 bg-paper-sunk/50 px-4 py-1.5 text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase sm:px-5">
              {KIND_LABELS[kind] ?? kind} <span className="readout font-normal">({qs.length})</span>
            </h3>
            <ol className="divide-y divide-border/60">
              {qs.map((q) => {
                n += 1;
                return (
                  <li key={q.id} className="flex gap-3 px-4 py-2.5 sm:px-5">
                    <span className="readout w-5 shrink-0 pt-px text-[12px] text-muted-foreground" aria-hidden>{n}</span>
                    <div className="min-w-0">
                      <p className="text-[13.5px] font-medium text-foreground">{q.question}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground"><span className="font-medium text-foreground/70">Why this question:</span> {q.why}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
      </Panel>
      <div className="space-y-4">
        <Panel title="Research the company" icon={<Search />} description={p.reference_note}>
          <ul className="-mx-2 space-y-0.5">
            {p.reference_links.map((l) => (
              <li key={l.url}>
                <a href={l.url} target="_blank" rel="noopener noreferrer"
                   className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-[13px] font-medium text-route transition-colors duration-150 hover:bg-route-tint/60">
                  <span className="truncate">{l.label}</span><ExternalLink className="size-3.5 shrink-0" aria-hidden />
                </a>
              </li>
            ))}
          </ul>
        </Panel>
        <Insights prep={p} />
        {aside}
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
      onSuccess: () => { toast.success("Saved. Locked in."); setUrl(""); setQuestion(""); setNote(""); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };
  return (
    <Panel title="What you found" icon={<NotebookPen />} count={prep.insights.length || undefined} description={<>Your saved notes for {prep.job.company}, with where they came from.</>}>
      <div className="space-y-3">
        {prep.insights.length === 0 ? <p className="text-xs text-muted-foreground">Nothing saved yet. Drop what you dig up here.</p> : (
          <ul className="space-y-2">
            {prep.insights.map((i) => (
              <li key={i.id} className="rounded-xl bg-paper-sunk/70 px-3 py-2 text-[13px]">
                {i.question && <p className="font-medium">{i.question}</p>}
                {i.note && <p className="text-muted-foreground">{i.note}</p>}
                <p className="mt-1 text-xs text-muted-foreground">
                  {sourceLabel(i.source)} · {formatDate(i.created_at)}
                  {i.url && <> · <a href={i.url} target="_blank" rel="noopener noreferrer" className="text-route underline">link</a></>}
                </p>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={submit} className="space-y-2 border-t border-border/70 pt-3">
          <h4 className="text-xs font-semibold text-heading">Save something you found</h4>
          <div className="grid grid-cols-2 gap-2">
            <NativeSelect ariaLabel="Where you found it" value={source} onChange={setSource} options={SOURCES} className="w-full" />
            <Input aria-label="Link" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://… (optional)" />
          </div>
          <Textarea aria-label="Question" rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="A question people were asked" />
          <Textarea aria-label="Note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Your note: process, tips, rounds…" />
          <div className="flex justify-end"><Button size="sm" variant="outline" type="submit" disabled={add.isPending}>{add.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Save</Button></div>
        </form>
      </div>
    </Panel>
  );
}

function PastPractice({ onOpen }: { onOpen: (id: number) => void }) {
  const list = usePractices();
  if (!list.data?.length) return null;
  return (
    <Panel title="Your practice sessions" icon={<History />} count={list.data.length} bodyClassName="px-0 pb-1 sm:px-0">
      <ul className="divide-y divide-border/70 text-[13px]">
        {list.data.map((p) => {
          const answered = Object.keys(p.answers ?? {}).length;
          const done = p.status === "completed";
          return (
            <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-5">
              <div className="min-w-0">
                <div className="truncate font-medium">{p.title}</div>
                <div className="text-xs text-muted-foreground">
                  {formatDate(p.created_at)} · <span className="readout">{answered}</span> of <span className="readout">{p.questions.length}</span> answered{done ? " · finished" : ""}
                </div>
              </div>
              <Button size="xs" variant={done ? "ghost" : "outline"} onClick={() => onOpen(p.id)}>{done ? "Review" : "Continue"}</Button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function PracticeView({ id, onBack }: { id: number; onBack: () => void }) {
  const practice = usePractice(id);
  const p = practice.data;
  const answered = p ? Object.keys(p.answers ?? {}).length : 0;
  return (
    <>
      <Button variant="ghost" size="sm" className="mb-2 -ml-2" onClick={onBack}><ArrowLeft /> Back to interview prep</Button>
      {!p ? (practice.error ? <EmptyState title="Couldn't load this practice session">{errorMessage(practice.error)}</EmptyState> : <Skeleton className="h-96 rounded-2xl" />) : (
        <>
          <PageHeader eyebrow={<>Practice · <span className="readout">{answered}</span> of <span className="readout">{p.questions.length}</span> answered</>} title={`Practice: ${p.title}`}
                      description="Answer out loud first, then type the gist. After saving you get a checklist of things strong answers usually include. It checks the answer's shape, not you." />
          <ol className="max-w-4xl space-y-3">
            {p.questions.map((q, i) => <PracticeQuestion key={q.id} practice={p} q={q} index={i} />)}
          </ol>
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
    <li className="space-y-3 rounded-2xl bg-card p-4 ring-1 ring-border sm:p-5">
      <div className="flex gap-3">
        <span aria-hidden className={cn("readout flex size-7 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold",
          prev ? "bg-route-tint text-route" : "bg-paper-sunk text-heading")}>{prev ? <Check className="size-3.5" /> : index + 1}</span>
        <div className="min-w-0">
          <div className="text-xs text-muted-foreground">Question {index + 1} · {KIND_LABELS[q.kind] ?? q.kind}</div>
          <p className="font-display text-[15px] font-bold text-heading">{q.question}</p>
          <p className="mt-0.5 text-xs text-muted-foreground"><span className="font-medium text-foreground/70">Why this question:</span> {q.why}</p>
        </div>
      </div>
      <Textarea aria-label={`Your answer to question ${index + 1}`} rows={4} value={answer} onChange={(e) => setAnswer(e.target.value)}
                placeholder="Situation, what you did, and the result" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1 text-xs" role="group" aria-label="How did that feel?">
          <span className="mr-1 text-muted-foreground">How confident do you feel?</span>
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" aria-pressed={rating === n} onClick={() => setRating(rating === n ? null : n)}
                    className={cn("readout size-7 rounded-full text-xs ring-1 transition-colors duration-150",
                      rating === n ? "bg-violet text-primary-foreground ring-violet" : "ring-border hover:bg-muted")}>{n}</button>
          ))}
        </div>
        <Button size="sm" disabled={!answer.trim() || !dirty || save.isPending}
                onClick={() => save.mutate({ question_id: q.id, answer: answer.trim(), self_rating: rating }, { onError: (e) => toast.error(errorMessage(e)) })}>
          {save.isPending && <Loader2 className="animate-spin" />} {prev ? "Save again" : "Save answer"}
        </Button>
      </div>
      {fb && (
        <div className="rounded-xl bg-paper-sunk p-3 text-[13px] animate-in fade-in-0 slide-in-from-top-1 duration-200" data-testid={`feedback-${q.id}`}>
          <div className="mb-1 flex flex-wrap items-center gap-x-2 text-xs font-medium text-heading">
            <ListChecks className="size-3.5" aria-hidden /> Checklist: <span className="readout">{fb.score}/{fb.out_of}</span>
            <span className="font-normal text-muted-foreground">(automatic check of structure and detail, not a grade of you)</span>
          </div>
          <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">{fb.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </div>
      )}
    </li>
  );
}
