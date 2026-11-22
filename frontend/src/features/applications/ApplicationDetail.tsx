import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Ban, ChevronDown, ExternalLink, Loader2, Mail, MessageSquareText, Phone, Plus, Trash2, Video, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LoadingState, NativeSelect, PlatformBadge } from "@/components/app/common";
import { CompanyMark } from "@/components/app/JobCard";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApplication, useApplicationAction, useUpdateTracking } from "@/services/queries";
import type { ApplicationContact, Interview, Offer } from "@/types/api";
import { InterviewFeedbackDialog, RejectionLabel } from "@/features/growth/applications";
import type { RejectionResult } from "@/features/growth/types";
import { eventDetail, eventLabel } from "./events";
import { JourneyTimeline } from "./Journey";
import { ApplyStatePill, EvidencePill, StagePill, StatusPill } from "./pills";

// The backend's interview fields (round_name, interviewers, location) and rejection fields, which the shared types don't list yet.
type InterviewRow = Interview & { round_name?: string | null; interviewers?: string | null; location?: string | null; interview_type?: string | null; feedback_at?: string | null };
type WithRejection = { rejection_reason?: string | null; rejection_reason_known?: boolean | null };
export type RejectTarget = { id: number; title: string; company: string };

/** One application in full: where it stands (the route on the left) and everything you track for it (tabs). */
export function ApplicationDetailDialog({ id, onClose, onReject, rejection, reasonLabels }: {
  id: number | null; onClose: () => void; onReject: (t: RejectTarget) => void; rejection?: RejectionResult; reasonLabels: Record<string, string>;
}) {
  const { data, isError, error } = useApplication(id);
  const action = useApplicationAction();
  const rej = rejection ?? (data as (typeof data & WithRejection) | undefined);
  const [journeyOpen, setJourneyOpen] = useState(false);

  return (
    <Dialog open={id != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="application-detail"
                     className="flex h-dvh max-h-dvh w-full max-w-full flex-col gap-0 overflow-hidden rounded-none p-0 sm:h-[86vh] sm:max-h-[86vh] sm:max-w-[940px] sm:rounded-[22px]">
        {!data ? (
          <div className="space-y-3 p-8" role="status" aria-label="Loading application">
            <DialogTitle className="sr-only">Loading application</DialogTitle>
            {isError ? <p className="text-sm text-destructive">This application couldn't be loaded. {errorMessage(error)}</p>
              : <><Skeleton className="h-8 w-2/3" /><Skeleton className="h-4 w-1/2" /><Skeleton className="h-64 w-full" /></>}
          </div>
        ) : (
          <>
            <header className="border-b px-5 pt-5 pb-4 sm:px-7">
              <div className="flex items-start gap-3.5 pr-8">
                <CompanyMark name={data.job.company || "?"} className="size-11 text-[14px]" />
                <div className="min-w-0 flex-1">
                  <DialogTitle className="font-display text-[20px] leading-tight font-bold tracking-[-0.02em] text-heading sm:text-[23px]">{data.job.title}</DialogTitle>
                  <DialogDescription className="mt-0.5 text-[13.5px]">
                    <span className="font-medium text-foreground">{data.job.company}</span>{data.job.location ? ` · ${data.job.location}` : ""}
                  </DialogDescription>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    <StatusPill status={data.status} />
                    {data.status === "SUBMITTED" && <StagePill stage={data.stage ?? "applied"} />}
                    <ApplyStatePill state={data.apply_state} label={data.apply_state_label} />
                    <PlatformBadge platform={data.job.platform} />
                  </div>
                </div>
                {data.match_score != null && (
                  <div className="hidden text-right sm:block" aria-label={`${Math.round(data.match_score)} percent match`}>
                    <div className="readout text-[28px] leading-none font-semibold text-heading">{Math.round(data.match_score)}<span className="text-sm text-muted-foreground">%</span></div>
                    <div className="eyebrow mt-1 text-[10px]">Match</div>
                  </div>
                )}
              </div>
            </header>

            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain lg:grid lg:grid-cols-[16.5rem_minmax(0,1fr)] lg:overflow-hidden">
              <aside className="border-b bg-paper-sunk/60 px-5 py-3.5 sm:px-7 lg:py-5 lg:overflow-y-auto lg:border-r lg:border-b-0 lg:px-5">
                <h3 className="eyebrow mb-3 max-lg:hidden">Where it stands</h3>
                <button type="button" aria-expanded={journeyOpen} onClick={() => setJourneyOpen((o) => !o)}
                        className="flex w-full items-center justify-between gap-2 text-left lg:hidden">
                  <span className="eyebrow">Where it stands</span>
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-route">{journeyOpen ? "Hide timeline" : "Show timeline"}
                    <ChevronDown className={cn("size-3.5 transition-transform duration-200", journeyOpen && "rotate-180")} /></span>
                </button>
                <div className={cn("max-lg:mt-3", !journeyOpen && "max-lg:hidden")}><JourneyTimeline app={data} /></div>
              </aside>

              <div className="px-5 py-4 sm:px-7 lg:overflow-y-auto lg:overscroll-contain">
                <Tabs defaultValue="overview">
                  <TabsList className="w-full sm:w-fit">
                    <TabsTrigger value="overview">Overview</TabsTrigger>
                    <TabsTrigger value="interviews">Interviews</TabsTrigger>
                    <TabsTrigger value="offer">Offer</TabsTrigger>
                    <TabsTrigger value="contacts">Contacts</TabsTrigger>
                  </TabsList>

                  <TabsContent value="overview" className="space-y-5 pt-3">
                    <dl className="grid grid-cols-2 gap-x-5 gap-y-3 text-sm sm:grid-cols-3">
                      <Fact label="Prepared"><span className="readout">{formatDate(data.created_at)}</span></Fact>
                      <Fact label="Submitted">{data.submitted_at ? <span className="readout">{formatDate(data.submitted_at)}</span> : <span className="text-muted-foreground">Not yet</span>}</Fact>
                      <Fact label="Reference">{data.reference_id ? <span className="readout">{data.reference_id}</span> : <span className="text-muted-foreground">—</span>}</Fact>
                      <Fact label="How you applied">{data.submission_method ?? <span className="text-muted-foreground">—</span>}</Fact>
                      {data.confirmation_type && <Fact label="Evidence"><EvidencePill app={data} className="whitespace-normal" /></Fact>}
                      {data.apply_state_label && <Fact label="Smart Apply">{data.apply_state_label}{data.apply_state_at && <span className="readout block text-xs text-muted-foreground">{formatDate(data.apply_state_at, true)}</span>}</Fact>}
                      <Fact label="Resume used">{data.resume_used ?? <span className="text-muted-foreground">—</span>}</Fact>
                      {rej?.rejection_reason && <Fact label="Rejection reason"><RejectionLabel reason={rej.rejection_reason} known={rej.rejection_reason_known} labels={reasonLabels} /></Fact>}
                    </dl>
                    <TrackingForm id={data.id} notes={data.notes} followUp={data.follow_up_at ?? null} />
                    <section>
                      <h4 className="eyebrow mb-2">History</h4>
                      <ol className="divide-y divide-border/70 rounded-xl ring-1 ring-border">
                        {[...data.events].reverse().map((e) => (
                          <li key={e.id} className="flex flex-wrap items-baseline justify-between gap-x-3 px-3 py-2 text-[13px]">
                            <span className="min-w-0"><span className="font-medium">{eventLabel(e)}</span>{eventDetail(e) && <span className="block text-xs text-muted-foreground">{eventDetail(e)}</span>}</span>
                            <span className="readout shrink-0 text-[11.5px] text-muted-foreground">{formatDate(e.created_at, true)}</span>
                          </li>
                        ))}
                      </ol>
                    </section>
                  </TabsContent>
                  <TabsContent value="interviews" className="pt-3"><InterviewsSection applicationId={data.id} /></TabsContent>
                  <TabsContent value="offer" className="pt-3"><OfferSection applicationId={data.id} /></TabsContent>
                  <TabsContent value="contacts" className="pt-3"><ContactsSection applicationId={data.id} /></TabsContent>
                </Tabs>
              </div>
            </div>

            <footer className="flex flex-wrap items-center gap-2 border-t bg-card px-5 py-3 sm:px-7">
              {data.job.job_url && (
                <Button variant="ghost" size="sm" render={<a href={data.job.job_url} target="_blank" rel="noopener noreferrer" />}><ExternalLink /> Original listing</Button>
              )}
              {data.status !== "WITHDRAWN" && (
                <div className="ml-auto flex flex-wrap justify-end gap-2">
                  {data.status === "SUBMITTED" && !rej?.rejection_reason && (
                    <Button variant="outline" size="sm" onClick={() => onReject({ id: data.id, title: data.job.title, company: data.job.company })}><XCircle /> Record rejection</Button>
                  )}
                  {data.status !== "SUBMITTED" && <Button variant="outline" size="sm" onClick={() => action.mutate({ kind: "fail", id: data.id, reason: "Marked failed by user" }, { onError: (e) => toast.error(errorMessage(e)) })}>Mark failed</Button>}
                  <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive" onClick={() => action.mutate({ kind: "withdraw", id: data.id }, { onSuccess: () => toast("Withdrawn"), onError: (e) => toast.error(errorMessage(e)) })}><Ban /> Withdraw</Button>
                </div>
              )}
            </footer>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div className="min-w-0"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-0.5 break-words">{children}</dd></div>;
}

function Label({ htmlFor, children }: { htmlFor: string; children: ReactNode }) {
  return <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium text-muted-foreground">{children}</label>;
}

/** A form that stays folded behind one button until you need it. */
function Addable({ open, onOpen, label, children }: { open: boolean; onOpen: () => void; label: string; children: ReactNode }) {
  if (!open) return <Button variant="outline" size="sm" onClick={onOpen}><Plus /> {label}</Button>;
  return <div className="rounded-xl bg-paper-sunk/70 p-3.5 ring-1 ring-border animate-in fade-in-0 slide-in-from-top-1 duration-200">{children}</div>;
}

function TrackingForm({ id, notes, followUp }: { id: number; notes: string | null; followUp: string | null }) {
  const save = useUpdateTracking();
  const [n, setN] = useState(notes ?? "");
  const [f, setF] = useState(followUp ? followUp.slice(0, 10) : "");
  useEffect(() => { setN(notes ?? ""); setF(followUp ? followUp.slice(0, 10) : ""); }, [id, notes, followUp]);
  return (
    <div className="grid gap-3 rounded-xl p-3.5 ring-1 ring-border sm:grid-cols-[1fr_10.5rem]">
      <div><Label htmlFor={`notes-${id}`}>Notes</Label>
        <Textarea id={`notes-${id}`} rows={2} value={n} onChange={(e) => setN(e.target.value)} placeholder="Contacts, interview prep, anything to remember" /></div>
      <div className="flex flex-col"><Label htmlFor={`follow-${id}`}>Follow up on</Label>
        <Input id={`follow-${id}`} type="date" value={f} onChange={(e) => setF(e.target.value)} />
        <Button size="sm" variant="outline" className="mt-auto self-end max-sm:mt-3" disabled={save.isPending}
                onClick={() => save.mutate({ id, notes: n || null, follow_up_at: f ? `${f}T09:00:00` : null },
                  { onSuccess: () => toast.success("Saved. Locked in."), onError: (e) => toast.error(errorMessage(e)) })}>
          {save.isPending && <Loader2 className="animate-spin" />} Save notes
        </Button>
      </div>
    </div>
  );
}

function InterviewsSection({ applicationId }: { applicationId: number }) {
  const [items, setItems] = useState<InterviewRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [feedbackFor, setFeedbackFor] = useState<{ id: number; label: string } | null>(null);
  const [round, setRound] = useState("Screening");
  const [schedAt, setSchedAt] = useState("");
  const [duration, setDuration] = useState(45);
  const [meetingUrl, setMeetingUrl] = useState("");
  const [interviewer, setInterviewer] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoading(true);
    api.get<InterviewRow[]>(`/interviews?application_id=${applicationId}`)
      .then((res) => setItems(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [applicationId]);

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault();
    if (!schedAt) return toast.error("Select interview date and time");
    try {
      setSubmitting(true);
      await api.post(`/applications/${applicationId}/interviews`, {
        round_name: round,
        scheduled_at: new Date(schedAt).toISOString(),
        duration_minutes: duration,
        location: meetingUrl || null,
        interviewers: interviewer || null,
        notes: notes || null,
      });
      toast.success("Interview on the calendar. You've got this.");
      setMeetingUrl("");
      setInterviewer("");
      setNotes("");
      setAdding(false);
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (ivId: number) => {
    try {
      await api.delete(`/interviews/${ivId}`);
      toast.success("Interview removed");
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const sorted = [...items].sort((a, b) => b.scheduled_at.localeCompare(a.scheduled_at));
  return (
    <div className="space-y-3">
      {loading ? <LoadingState /> : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No interviews yet. When one's booked, add it here and it lands in your calendar file.</p>
      ) : (
        <ul className="divide-y divide-border/70 rounded-xl ring-1 ring-border">
          {sorted.map((iv) => {
            const name = iv.round_name ?? iv.round ?? "Interview";
            const who = iv.interviewers ?? iv.interviewer;
            const link = iv.meeting_url ?? (iv.location?.startsWith("http") ? iv.location : null);
            const when = new Date(iv.scheduled_at);
            const upcoming = when.getTime() > Date.now();
            return (
              <li key={iv.id} className="flex items-start gap-3 p-3 text-sm">
                <div className={cn("flex w-12 shrink-0 flex-col items-center rounded-xl py-1.5", upcoming ? "bg-route-tint text-route" : "bg-paper-sunk text-muted-foreground")}>
                  <span className="readout text-lg leading-none font-semibold">{when.getDate()}</span>
                  <span className="text-[10.5px] font-medium uppercase">{when.toLocaleString(undefined, { month: "short" })}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-heading">{name}</div>
                  <div className="readout text-xs text-muted-foreground">
                    {when.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}{iv.duration_minutes ? ` · ${iv.duration_minutes} min` : ""}
                    {iv.outcome && iv.outcome !== "scheduled" ? ` · ${iv.outcome}` : ""}{iv.feedback_at ? " · feedback saved" : ""}
                  </div>
                  {who && <div className="text-xs text-muted-foreground">With {who}</div>}
                  {link ? (
                    <a href={link} target="_blank" rel="noopener noreferrer" className="mt-0.5 inline-flex items-center gap-1 text-xs font-medium text-route hover:underline"><Video className="size-3" /> Meeting link</a>
                  ) : iv.location && <div className="text-xs text-muted-foreground">{iv.location}</div>}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button size="xs" variant="outline" onClick={() => setFeedbackFor({ id: iv.id, label: `${name}, ${formatDate(iv.scheduled_at)}` })}>
                    <MessageSquareText /> How did it go?
                  </Button>
                  <Button size="icon-xs" variant="ghost" aria-label="Remove interview" onClick={() => handleDelete(iv.id)}><Trash2 className="size-3.5 text-destructive" /></Button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <Addable open={adding || (!loading && items.length === 0)} onOpen={() => setAdding(true)} label="Add an interview">
        <form onSubmit={handleAdd} className="space-y-3">
          <h5 className="text-[13px] font-semibold text-heading">Schedule an interview</h5>
          <div className="grid gap-2.5 sm:grid-cols-2">
            <div><Label htmlFor="iv-round">Round</Label><Input id="iv-round" value={round} onChange={(e) => setRound(e.target.value)} placeholder="e.g. Technical Round 1" required /></div>
            <div><Label htmlFor="iv-at">Date & time</Label><Input id="iv-at" type="datetime-local" value={schedAt} onChange={(e) => setSchedAt(e.target.value)} required /></div>
            <div><Label htmlFor="iv-who">Interviewer (optional)</Label><Input id="iv-who" value={interviewer} onChange={(e) => setInterviewer(e.target.value)} placeholder="e.g. John Doe" /></div>
            <div><Label htmlFor="iv-dur">Duration (minutes)</Label><Input id="iv-dur" type="number" min={15} max={240} value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></div>
            <div className="sm:col-span-2"><Label htmlFor="iv-url">Meeting URL (optional)</Label><Input id="iv-url" value={meetingUrl} onChange={(e) => setMeetingUrl(e.target.value)} placeholder="https://meet.google.com/..." /></div>
            <div className="sm:col-span-2"><Label htmlFor="iv-notes">Notes (optional)</Label><Textarea id="iv-notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Topics, preparation links, etc." /></div>
          </div>
          <div className="flex justify-end gap-2">
            {items.length > 0 && <Button size="sm" type="button" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>}
            <Button size="sm" type="submit" disabled={submitting}>{submitting ? <Loader2 className="animate-spin" /> : <Plus />} Schedule</Button>
          </div>
        </form>
      </Addable>
      <InterviewFeedbackDialog interview={feedbackFor} onClose={() => setFeedbackFor(null)} onSaved={load} />
    </div>
  );
}

function OfferSection({ applicationId }: { applicationId: number }) {
  const [baseSalary, setBaseSalary] = useState<string>("");
  const [currency, setCurrency] = useState("INR");
  const [bonus, setBonus] = useState<string>("");
  const [equity, setEquity] = useState("");
  const [status, setStatus] = useState("received");
  const [deadline, setDeadline] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get<Offer[]>("/offers")
      .then((res) => {
        const found = res.data.find((o) => o.application_id === applicationId);
        if (found) {
          setBaseSalary(found.base_salary != null ? String(found.base_salary) : "");
          setCurrency(found.currency || "INR");
          setBonus(found.bonus != null ? String(found.bonus) : "");
          setEquity(found.equity || "");
          setStatus(found.status || "received");
          const due = (found as Offer & { decision_deadline?: string | null }).decision_deadline ?? found.deadline;
          setDeadline(due ? due.slice(0, 10) : "");
          setNotes(found.notes || "");
          setSaved(true);
        }
      })
      .catch(() => {});
  }, [applicationId]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      setSubmitting(true);
      await api.put(`/applications/${applicationId}/offer`, {
        base_salary: baseSalary ? Number(baseSalary) : null,
        currency,
        bonus: bonus ? Number(bonus) : null,
        equity: equity || null,
        decision_deadline: deadline || null,
        status,
        notes: notes || null,
      });
      toast.success("Offer details saved. Big W 🎉");
      setSaved(true);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const total = (Number(baseSalary) || 0) + (Number(bonus) || 0);
  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {saved && total > 0 ? (
        <div className="flex flex-wrap items-end gap-x-6 gap-y-2 rounded-xl bg-success-tint/60 px-4 py-3 ring-1 ring-success/20">
          <div><div className="text-xs text-muted-foreground">Base + bonus</div>
            <div className="readout text-[26px] leading-tight font-semibold text-heading">{currency} {total.toLocaleString()}</div></div>
          {deadline && <div><div className="text-xs text-muted-foreground">Decide by</div><div className="readout font-medium">{formatDate(deadline)}</div></div>}
        </div>
      ) : <p className="text-sm text-muted-foreground">Got an offer? Note the numbers here so you can compare and decide calmly.</p>}
      <div className="grid gap-2.5 rounded-xl p-3.5 ring-1 ring-border sm:grid-cols-2">
        <div><Label htmlFor="of-base">Base salary</Label><Input id="of-base" type="number" value={baseSalary} onChange={(e) => setBaseSalary(e.target.value)} placeholder="e.g. 1500000" /></div>
        <div><Label htmlFor="of-cur">Currency</Label><Input id="of-cur" value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="INR, USD, EUR" /></div>
        <div><Label htmlFor="of-bonus">Bonus</Label><Input id="of-bonus" type="number" value={bonus} onChange={(e) => setBonus(e.target.value)} placeholder="e.g. 200000" /></div>
        <div><Label htmlFor="of-eq">Equity</Label><Input id="of-eq" value={equity} onChange={(e) => setEquity(e.target.value)} placeholder="e.g. 5,000 ESOPs / 4-yr vest" /></div>
        <div><Label htmlFor="of-due">Decision deadline</Label><Input id="of-due" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} /></div>
        <div><Label htmlFor="of-status">Status</Label>
          <NativeSelect id="of-status" ariaLabel="Offer status" value={status} onChange={setStatus} className="w-full"
                        options={[{ value: "received", label: "Offer received" }, { value: "negotiating", label: "Negotiating" }, { value: "accepted", label: "Accepted" }, { value: "declined", label: "Declined" }]} />
        </div>
        <div className="sm:col-span-2"><Label htmlFor="of-notes">Notes</Label><Textarea id="of-notes" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Benefits, insurance, start date details..." /></div>
        <div className="flex justify-end sm:col-span-2">
          <Button size="sm" type="submit" disabled={submitting}>{submitting && <Loader2 className="animate-spin" />} Save offer</Button>
        </div>
      </div>
    </form>
  );
}

function ContactsSection({ applicationId }: { applicationId: number }) {
  const [items, setItems] = useState<ApplicationContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [linkedin, setLinkedin] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoading(true);
    api.get<ApplicationContact[]>(`/applications/${applicationId}/contacts`)
      .then((res) => setItems(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [applicationId]);

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      setSubmitting(true);
      await api.post(`/applications/${applicationId}/contacts`, {
        name: name.trim(),
        role: role.trim() || null,
        email: email.trim() || null,
        phone: phone.trim() || null,
        linkedin_url: linkedin.trim() || null,
      });
      toast.success("Contact added. Networking era unlocked.");
      setName("");
      setRole("");
      setEmail("");
      setPhone("");
      setLinkedin("");
      setAdding(false);
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (contactId: number) => {
    try {
      await api.delete(`/contacts/${contactId}`);
      toast.success("Contact removed");
      load();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  return (
    <div className="space-y-3">
      {loading ? <LoadingState /> : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No contacts yet. A recruiter's name now saves a hunt through your inbox later.</p>
      ) : (
        <ul className="divide-y divide-border/70 rounded-xl ring-1 ring-border">
          {items.map((c) => (
            <li key={c.id} className="flex items-start gap-3 p-3 text-sm">
              <CompanyMark name={c.name} className="size-9 rounded-full text-[12px]" />
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-heading">{c.name}{c.role && <span className="ml-1.5 text-xs font-normal text-muted-foreground">{c.role}</span>}</div>
                <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                  {c.email && <a href={`mailto:${c.email}`} className="inline-flex items-center gap-1 hover:text-route"><Mail className="size-3" /> {c.email}</a>}
                  {c.phone && <span className="readout inline-flex items-center gap-1"><Phone className="size-3" /> {c.phone}</span>}
                  {c.linkedin_url && <a href={c.linkedin_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-route hover:underline">LinkedIn profile <ExternalLink className="size-3" /></a>}
                </div>
              </div>
              <Button size="icon-xs" variant="ghost" aria-label={`Remove contact ${c.name}`} onClick={() => handleDelete(c.id)}><Trash2 className="size-3.5 text-destructive" /></Button>
            </li>
          ))}
        </ul>
      )}

      <Addable open={adding || (!loading && items.length === 0)} onOpen={() => setAdding(true)} label="Add a contact">
        <form onSubmit={handleAdd} className="space-y-3">
          <h5 className="text-[13px] font-semibold text-heading">Add a contact</h5>
          <div className="grid gap-2.5 sm:grid-cols-2">
            <div><Label htmlFor="ct-name">Name</Label><Input id="ct-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Recruiter / Hiring Manager" required /></div>
            <div><Label htmlFor="ct-role">Role / title</Label><Input id="ct-role" value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Technical Recruiter" /></div>
            <div><Label htmlFor="ct-email">Email</Label><Input id="ct-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="recruiter@company.com" /></div>
            <div><Label htmlFor="ct-phone">Phone</Label><Input id="ct-phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 ..." /></div>
            <div className="sm:col-span-2"><Label htmlFor="ct-li">LinkedIn URL</Label><Input id="ct-li" value={linkedin} onChange={(e) => setLinkedin(e.target.value)} placeholder="https://linkedin.com/in/..." /></div>
          </div>
          <div className="flex justify-end gap-2">
            {items.length > 0 && <Button size="sm" type="button" variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>}
            <Button size="sm" type="submit" disabled={submitting}>{submitting ? <Loader2 className="animate-spin" /> : <Plus />} Add contact</Button>
          </div>
        </form>
      </Addable>
    </div>
  );
}
