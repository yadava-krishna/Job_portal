import { useEffect, useState, type FormEvent } from "react";
import { Calendar, ExternalLink, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState, NativeSelect, PageHeader, PlatformBadge, ScoreBadge, StageBadge, StatusBadge } from "@/components/app/common";
import { ApplyDialog } from "@/components/app/ApplyDialog";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { formatDate, stageLabels, statusLabels } from "@/lib/format";
import { useApplication, useApplicationAction, useApplications, useUpdateTracking } from "@/services/queries";
import type { Application, ApplicationContact, Interview, Offer, Stage, UserJob } from "@/types/api";

const STAGES: Stage[] = ["applied", "screening", "assessment", "interview", "offer", "rejected"];
const MOVE_TO: Stage[] = [...STAGES, "archived"];
const STATUS_FILTERS = ["all", "PREPARED", "OPENED", "CONFIRMATION_PENDING", "SUBMITTED", "FAILED", "WITHDRAWN"];

function asUserJob(a: Application): UserJob {
  return { user_job_id: a.user_job_id ?? 0, status: a.status === "SUBMITTED" ? "applied" : "shortlisted", is_saved: false, match_score: a.match_score,
    match_category: a.match_category, matching_skills: [], missing_skills: [], eligibility_status: null, scoring_method: null, discovered_at: a.created_at,
    saved_at: null, dismissed_at: null, application_id: a.id, application_status: a.status, job: a.job };
}

export function AppliedPage() {
  const [filter, setFilter] = useState("all");
  const apps = useApplications(filter === "all" ? undefined : [filter]);
  const all = useApplications();
  const action = useApplicationAction();
  const [detailId, setDetailId] = useState<number | null>(null);
  const [resume, setResume] = useState<UserJob | null>(null);
  const submitted = (all.data ?? []).filter((a) => a.status === "SUBMITTED");
  const pending = (all.data ?? []).filter((a) => ["PREPARED", "OPENED", "CONFIRMATION_PENDING"].includes(a.status));

  const moveStage = (a: Application, stage: Stage) => action.mutate({ kind: "stage", id: a.id, stage }, {
    onSuccess: () => toast.success(`Moved to ${stageLabels[stage]}`), onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader
        title="Applications"
        description="Everything you prepared or applied to, and where each application stands."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => void downloadFile("/interviews/calendar.ics", "jobpilot-interviews.ics").catch((e) => toast.error(errorMessage(e)))}
          >
            <Calendar className="size-4" /> Download calendar (.ics)
          </Button>
        }
      />
      <Tabs defaultValue="list">
        <TabsList>
          <TabsTrigger value="list">All applications</TabsTrigger>
          <TabsTrigger value="board">Pipeline board ({submitted.length})</TabsTrigger>
          <TabsTrigger value="pending">Pending ({pending.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="list" className="pt-4">
          <div className="mb-3 flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Status</span>
            <NativeSelect ariaLabel="Filter by status" value={filter} onChange={setFilter} options={STATUS_FILTERS.map((s) => ({ value: s, label: s === "all" ? "All" : statusLabels[s] }))} />
          </div>
          {apps.isLoading ? <Loader2 className="animate-spin" /> : !apps.data?.length ? (
            <EmptyState title="No applications yet">Use Apply on a job to prepare one. It appears here once prepared and moves to Submitted after you confirm.</EmptyState>
          ) : (
            <Card className="overflow-x-auto p-0">
              <table className="w-full min-w-[820px] text-sm">
                <thead className="border-b bg-muted/50 text-left text-muted-foreground">
                  <tr>{["Company", "Job title", "Platform", "Applied on", "Status", "Stage", "Match", "Reference", ""].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y">
                  {apps.data.map((a) => (
                    <tr key={a.id} className="hover:bg-muted/30">
                      <td className="px-3 py-2 font-medium">{a.job.company}</td>
                      <td className="px-3 py-2"><button className="text-left hover:underline" onClick={() => setDetailId(a.id)}>{a.job.title}</button></td>
                      <td className="px-3 py-2"><PlatformBadge platform={a.job.platform} /></td>
                      <td className="px-3 py-2 whitespace-nowrap">{a.submitted_at ? formatDate(a.submitted_at) : <span className="text-muted-foreground">—</span>}</td>
                      <td className="px-3 py-2"><StatusBadge status={a.status} /></td>
                      <td className="px-3 py-2"><StageBadge stage={a.stage} /></td>
                      <td className="px-3 py-2"><ScoreBadge score={a.match_score} /></td>
                      <td className="px-3 py-2 font-mono text-xs">{a.reference_id ?? "—"}</td>
                      <td className="px-3 py-2">
                        <div className="flex justify-end gap-1">
                          {a.status !== "SUBMITTED" && a.status !== "WITHDRAWN" && <Button size="xs" onClick={() => setResume(asUserJob(a))}>Continue</Button>}
                          {a.job.job_url && <Button size="icon-xs" variant="ghost" aria-label="Open original listing" render={<a href={a.job.job_url} target="_blank" rel="noopener noreferrer" />}><ExternalLink /></Button>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="board" className="pt-4">
          {!submitted.length ? <EmptyState title="No submitted applications yet">After you confirm a submission it appears here. Move it along as you hear back.</EmptyState> : (
            <div className="grid gap-4 overflow-x-auto md:grid-cols-3 xl:grid-cols-6">
              {STAGES.map((stage) => {
                const col = submitted.filter((a) => (a.stage ?? "applied") === stage);
                return (
                  <div key={stage} className="min-w-56 rounded-xl bg-muted/50 p-3">
                    <div className="mb-3 flex items-center justify-between text-sm font-medium">{stageLabels[stage]}<span className="text-muted-foreground">{col.length}</span></div>
                    <div className="space-y-2">
                      {col.map((a) => (
                        <Card key={a.id} className="gap-2 p-3">
                          <button className="text-left text-sm font-medium hover:underline" onClick={() => setDetailId(a.id)}>{a.job.title}</button>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">{a.job.company} <PlatformBadge platform={a.job.platform} /></div>
                          <NativeSelect ariaLabel="Move to stage" value={a.stage ?? "applied"} onChange={(v) => moveStage(a, v as Stage)} className="h-7 w-full text-xs"
                                        options={MOVE_TO.map((s) => ({ value: s, label: stageLabels[s] }))} />
                        </Card>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </TabsContent>

        <TabsContent value="pending" className="pt-4">
          {!pending.length ? <EmptyState title="Nothing pending">Prepared or opened applications that you haven't confirmed appear here.</EmptyState> : (
            <div className="grid gap-3 md:grid-cols-2">
              {pending.map((a) => (
                <Card key={a.id} className="flex-row items-center justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{a.job.title}</div>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">{a.job.company} <StatusBadge status={a.status} /></div>
                  </div>
                  <Button size="sm" onClick={() => setResume(asUserJob(a))}>Continue</Button>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
      <ApplicationDetailDialog id={detailId} onClose={() => setDetailId(null)} />
      <ApplyDialog item={resume} onClose={() => setResume(null)} />
    </>
  );
}

function ApplicationDetailDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { data } = useApplication(id);
  const action = useApplicationAction();

  return (
    <Dialog open={id != null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-2xl">
        {!data ? <Loader2 className="animate-spin" /> : (
          <>
            <DialogHeader>
              <DialogTitle>{data.job.title}</DialogTitle>
              <DialogDescription>{data.job.company} · {data.job.platform} · <StatusBadge status={data.status} /></DialogDescription>
            </DialogHeader>

            <Tabs defaultValue="overview" className="mt-2">
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="interviews">Interviews</TabsTrigger>
                <TabsTrigger value="offer">Offer</TabsTrigger>
                <TabsTrigger value="contacts">Contacts</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="space-y-4 pt-3">
                <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1.5 text-sm">
                  <dt className="text-muted-foreground">Prepared</dt><dd>{formatDate(data.created_at, true)}</dd>
                  <dt className="text-muted-foreground">Submitted</dt><dd>{data.submitted_at ? formatDate(data.submitted_at, true) : "—"}</dd>
                  <dt className="text-muted-foreground">Reference</dt><dd>{data.reference_id ?? "—"}</dd>
                  <dt className="text-muted-foreground">How you applied</dt><dd>{data.submission_method ?? "—"}</dd>
                  <dt className="text-muted-foreground">Resume used</dt><dd>{data.resume_used ?? "—"}</dd>
                  {data.job.job_url && <><dt className="text-muted-foreground">Original listing</dt><dd><a className="underline" href={data.job.job_url} target="_blank" rel="noopener noreferrer">Open</a></dd></>}
                </dl>
                <TrackingForm id={data.id} notes={data.notes} followUp={data.follow_up_at ?? null} />
                <div>
                  <h4 className="mb-2 text-sm font-medium">History</h4>
                  <ol className="space-y-1.5 border-l pl-4 text-sm">
                    {data.events.map((e) => (
                      <li key={e.id}><span className="font-medium">{e.event_type.replaceAll("_", " ").toLowerCase()}</span> <span className="text-muted-foreground">· {formatDate(e.created_at, true)}</span>{e.details && <div className="text-xs text-muted-foreground">{e.details}</div>}</li>
                    ))}
                  </ol>
                </div>
              </TabsContent>

              <TabsContent value="interviews" className="pt-3">
                <InterviewsSection applicationId={data.id} />
              </TabsContent>

              <TabsContent value="offer" className="pt-3">
                <OfferSection applicationId={data.id} />
              </TabsContent>

              <TabsContent value="contacts" className="pt-3">
                <ContactsSection applicationId={data.id} />
              </TabsContent>
            </Tabs>

            {data.status !== "WITHDRAWN" && (
              <div className="mt-4 flex justify-end gap-2 border-t pt-3">
                {data.status !== "SUBMITTED" && <Button variant="outline" size="sm" onClick={() => action.mutate({ kind: "fail", id: data.id, reason: "Marked failed by user" }, { onError: (e) => toast.error(errorMessage(e)) })}>Mark failed</Button>}
                <Button variant="outline" size="sm" onClick={() => action.mutate({ kind: "withdraw", id: data.id }, { onSuccess: () => toast("Withdrawn"), onError: (e) => toast.error(errorMessage(e)) })}>Withdraw</Button>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function TrackingForm({ id, notes, followUp }: { id: number; notes: string | null; followUp: string | null }) {
  const save = useUpdateTracking();
  const [n, setN] = useState(notes ?? "");
  const [f, setF] = useState(followUp ? followUp.slice(0, 10) : "");
  useEffect(() => { setN(notes ?? ""); setF(followUp ? followUp.slice(0, 10) : ""); }, [id, notes, followUp]);
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="grid gap-2 sm:grid-cols-[1fr_10rem]">
        <label className="text-sm"><span className="mb-1 block text-muted-foreground">Notes</span>
          <Textarea rows={2} value={n} onChange={(e) => setN(e.target.value)} placeholder="Contacts, interview prep, anything to remember" /></label>
        <label className="text-sm"><span className="mb-1 block text-muted-foreground">Follow up on</span>
          <Input type="date" value={f} onChange={(e) => setF(e.target.value)} /></label>
      </div>
      <div className="flex justify-end">
        <Button size="sm" variant="outline" disabled={save.isPending}
                onClick={() => save.mutate({ id, notes: n || null, follow_up_at: f ? `${f}T09:00:00` : null },
                  { onSuccess: () => toast.success("Saved"), onError: (e) => toast.error(errorMessage(e)) })}>Save notes</Button>
      </div>
    </div>
  );
}

function InterviewsSection({ applicationId }: { applicationId: number }) {
  const [items, setItems] = useState<Interview[]>([]);
  const [loading, setLoading] = useState(true);
  const [round, setRound] = useState("Screening");
  const [schedAt, setSchedAt] = useState("");
  const [duration, setDuration] = useState(45);
  const [meetingUrl, setMeetingUrl] = useState("");
  const [interviewer, setInterviewer] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoading(true);
    api.get<Interview[]>(`/interviews?application_id=${applicationId}`)
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
        round,
        scheduled_at: new Date(schedAt).toISOString(),
        duration_minutes: duration,
        meeting_url: meetingUrl || null,
        interviewer: interviewer || null,
        notes: notes || null,
      });
      toast.success("Interview scheduled");
      setMeetingUrl("");
      setInterviewer("");
      setNotes("");
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

  return (
    <div className="space-y-4">
      {loading ? <Loader2 className="animate-spin" /> : items.length === 0 ? (
        <p className="text-xs text-muted-foreground">No interviews scheduled yet for this application.</p>
      ) : (
        <div className="space-y-2">
          {items.map((iv: Interview) => (
            <div key={iv.id} className="flex items-center justify-between rounded-lg border p-3 text-sm">
              <div>
                <div className="font-medium text-foreground">{iv.round} ({iv.duration_minutes}m)</div>
                <div className="text-xs text-muted-foreground">{formatDate(iv.scheduled_at, true)}</div>
                {iv.interviewer && <div className="text-xs text-muted-foreground">With: {iv.interviewer}</div>}
                {iv.meeting_url && (
                  <a href={iv.meeting_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary underline block mt-0.5">
                    Meeting link
                  </a>
                )}
              </div>
              <Button size="icon-xs" variant="ghost" onClick={() => handleDelete(iv.id)}><Trash2 className="size-3.5 text-destructive" /></Button>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleAdd} className="rounded-lg border p-3 space-y-3 bg-muted/20">
        <h5 className="text-xs font-semibold text-foreground">Schedule Interview</h5>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <label className="block text-muted-foreground mb-1">Round</label>
            <Input value={round} onChange={(e) => setRound(e.target.value)} placeholder="e.g. Technical Round 1" required />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">Date & Time</label>
            <Input type="datetime-local" value={schedAt} onChange={(e) => setSchedAt(e.target.value)} required />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">Interviewer (optional)</label>
            <Input value={interviewer} onChange={(e) => setInterviewer(e.target.value)} placeholder="e.g. John Doe" />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">Duration (minutes)</label>
            <Input type="number" min={15} max={240} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
          </div>
          <div className="col-span-2">
            <label className="block text-muted-foreground mb-1">Meeting URL (optional)</label>
            <Input value={meetingUrl} onChange={(e) => setMeetingUrl(e.target.value)} placeholder="https://meet.google.com/..." />
          </div>
          <div className="col-span-2">
            <label className="block text-muted-foreground mb-1">Notes (optional)</label>
            <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Topics, preparation links, etc." />
          </div>
        </div>
        <div className="flex justify-end">
          <Button size="sm" type="submit" disabled={submitting}>
            {submitting ? <Loader2 className="animate-spin size-3.5" /> : <Plus className="size-3.5" />} Schedule
          </Button>
        </div>
      </form>
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
          setDeadline(found.deadline ? found.deadline.slice(0, 10) : "");
          setNotes(found.notes || "");
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
        deadline: deadline ? `${deadline}T18:00:00` : null,
        status,
        notes: notes || null,
      });
      toast.success("Offer details saved");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border p-3 space-y-3 bg-muted/20">
      <h5 className="text-xs font-semibold text-foreground">Offer Details</h5>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <label className="block text-muted-foreground mb-1">Base Salary</label>
          <Input type="number" value={baseSalary} onChange={(e) => setBaseSalary(e.target.value)} placeholder="e.g. 1500000" />
        </div>
        <div>
          <label className="block text-muted-foreground mb-1">Currency</label>
          <Input value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="INR, USD, EUR" />
        </div>
        <div>
          <label className="block text-muted-foreground mb-1">Bonus</label>
          <Input type="number" value={bonus} onChange={(e) => setBonus(e.target.value)} placeholder="e.g. 200000" />
        </div>
        <div>
          <label className="block text-muted-foreground mb-1">Equity</label>
          <Input value={equity} onChange={(e) => setEquity(e.target.value)} placeholder="e.g. 5,000 ESOPs / 4-yr vest" />
        </div>
        <div>
          <label className="block text-muted-foreground mb-1">Decision Deadline</label>
          <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
        </div>
        <div>
          <label className="block text-muted-foreground mb-1">Status</label>
          <NativeSelect
            ariaLabel="Offer status"
            value={status}
            onChange={setStatus}
            options={[
              { value: "received", label: "Offer Received" },
              { value: "negotiating", label: "Negotiating" },
              { value: "accepted", label: "Accepted" },
              { value: "declined", label: "Declined" },
            ]}
          />
        </div>
        <div className="col-span-2">
          <label className="block text-muted-foreground mb-1">Notes</label>
          <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Benefits, insurance, start date details..." />
        </div>
      </div>
      <div className="flex justify-end">
        <Button size="sm" type="submit" disabled={submitting}>
          {submitting ? <Loader2 className="animate-spin size-3.5" /> : null} Save Offer
        </Button>
      </div>
    </form>
  );
}

function ContactsSection({ applicationId }: { applicationId: number }) {
  const [items, setItems] = useState<ApplicationContact[]>([]);
  const [loading, setLoading] = useState(true);
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
      toast.success("Contact added");
      setName("");
      setRole("");
      setEmail("");
      setPhone("");
      setLinkedin("");
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
    <div className="space-y-4">
      {loading ? <Loader2 className="animate-spin" /> : items.length === 0 ? (
        <p className="text-xs text-muted-foreground">No contacts saved yet for this application.</p>
      ) : (
        <div className="space-y-2">
          {items.map((c: ApplicationContact) => (
            <div key={c.id} className="flex items-center justify-between rounded-lg border p-3 text-sm">
              <div>
                <div className="font-medium text-foreground">{c.name} {c.role && <span className="text-xs text-muted-foreground">({c.role})</span>}</div>
                {c.email && <div className="text-xs text-muted-foreground">Email: {c.email}</div>}
                {c.phone && <div className="text-xs text-muted-foreground">Phone: {c.phone}</div>}
                {c.linkedin_url && (
                  <a href={c.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary underline block mt-0.5">
                    LinkedIn Profile
                  </a>
                )}
              </div>
              <Button size="icon-xs" variant="ghost" onClick={() => handleDelete(c.id)}><Trash2 className="size-3.5 text-destructive" /></Button>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleAdd} className="rounded-lg border p-3 space-y-3 bg-muted/20">
        <h5 className="text-xs font-semibold text-foreground">Add Contact</h5>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <label className="block text-muted-foreground mb-1">Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Recruiter / Hiring Manager" required />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">Role / Title</label>
            <Input value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Technical Recruiter" />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">Email</label>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="recruiter@company.com" />
          </div>
          <div>
            <label className="block text-muted-foreground mb-1">Phone</label>
            <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 ..." />
          </div>
          <div className="col-span-2">
            <label className="block text-muted-foreground mb-1">LinkedIn URL</label>
            <Input value={linkedin} onChange={(e) => setLinkedin(e.target.value)} placeholder="https://linkedin.com/in/..." />
          </div>
        </div>
        <div className="flex justify-end">
          <Button size="sm" type="submit" disabled={submitting}>
            {submitting ? <Loader2 className="animate-spin size-3.5" /> : <Plus className="size-3.5" />} Add Contact
          </Button>
        </div>
      </form>
    </div>
  );
}
