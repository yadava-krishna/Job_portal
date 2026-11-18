import { useRef, useState } from "react";
import { Check, Download, Eye, Loader2, Plus, Star, Trash2, UploadCloud } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ErrorState, Field, LoadingState, NativeSelect } from "@/components/app/common";
import { Panel } from "@/components/settings/primitives";
import { downloadFile, errorMessage, previewFile } from "@/lib/api";
import { bytes, formatDate } from "@/lib/format";
import { NOTIFICATION_KINDS, useNotificationPrefs, useResumeAction, useResumes, useSaveNotificationPrefs, type NotificationKind, type NotificationPrefs } from "@/services/queries";
import type { SavedAnswer, VerifiedFacts } from "@/types/api";

/** Several resume versions (e.g. one per role family); the default one is used for applications and the extension. */
export function ResumeVersions() {
  const resumes = useResumes();
  const act = useResumeAction();
  const fileRef = useRef<HTMLInputElement>(null);
  const [makeDefault, setMakeDefault] = useState(false);
  const [editing, setEditing] = useState<{ id: number; name: string } | null>(null);
  const run = (a: Parameters<typeof act.mutate>[0], ok: string) => act.mutate(a, { onSuccess: () => toast.success(ok), onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Panel title="Resume versions"
           description="Keep role-specific resumes. The default is offered first by the Smart Apply extension (you can pick another resume or a Resume Studio version) and recorded on applications. Changing the default does not change your confirmed profile.">
      <div className="space-y-3">
        {resumes.isLoading && <Loader2 className="animate-spin" />}
        {resumes.data?.map((r) => (
          <div key={r.id} className={`flex flex-wrap items-center justify-between gap-2 rounded-xl p-3 text-sm ring-1 transition-colors duration-200 ${r.is_active ? "bg-route-tint/50 ring-route/25" : "ring-border"}`}>
            <div className="min-w-0">
              {editing?.id === r.id ? (
                <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run({ kind: "rename", id: r.id, name: editing.name }, "Renamed"); setEditing(null); }}>
                  <Input value={editing.name} onChange={(e) => setEditing({ id: r.id, name: e.target.value })} aria-label="Resume name" className="h-8" autoFocus />
                  <Button size="sm" type="submit">Save</Button>
                </form>
              ) : (
                <button type="button" className="truncate text-left font-medium hover:underline" onClick={() => setEditing({ id: r.id, name: r.original_filename.replace(/\.pdf$/i, "") })} title="Rename">{r.original_filename}</button>
              )}
              <div className="text-xs text-muted-foreground">{r.page_count} page(s) · {bytes(r.size_bytes)} · uploaded {formatDate(r.uploaded_at)}</div>
            </div>
            <div className="flex items-center gap-1">
              {r.is_active ? <Badge className="animate-in fade-in-0 zoom-in-95 duration-200">Default</Badge> : <Button size="sm" variant="outline" onClick={() => run({ kind: "default", id: r.id }, "Default resume changed")}><Star /> Make default</Button>}
              {r.original_filename.toLowerCase().endsWith(".pdf") && <Button size="icon-sm" variant="ghost" aria-label="Preview" onClick={() => previewFile(`/profile/resumes/${r.id}/file?inline=true`).catch((e) => toast.error(errorMessage(e)))}><Eye /></Button>}
              <Button size="icon-sm" variant="ghost" aria-label="Download" onClick={() => downloadFile(`/profile/resumes/${r.id}/file`, r.original_filename).catch((e) => toast.error(errorMessage(e)))}><Download /></Button>
              {!r.is_active && <Button size="icon-sm" variant="ghost" aria-label="Delete" onClick={() => run({ kind: "delete", id: r.id }, "Deleted")}><Trash2 /></Button>}
            </div>
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-4">
          <input ref={fileRef} type="file" accept="application/pdf,.pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="sr-only" aria-label="Add a resume version"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) run({ kind: "upload", file: f, makeDefault }, makeDefault ? "Uploaded. Review your profile below." : "Added"); e.target.value = ""; }} />
          <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={act.isPending}>{act.isPending ? <Loader2 className="animate-spin" /> : <UploadCloud />} Add a version</Button>
          <label className="flex min-w-0 items-center gap-2 text-[13px] text-muted-foreground"><Switch checked={makeDefault} onCheckedChange={(c) => setMakeDefault(!!c)} /> Make it the default (and re-read it into the profile for review)</label>
        </div>
      </div>
    </Panel>
  );
}

/** The user's own approved answers to questions applications keep asking. */
export function AnswerBank({ facts, onChange }: { facts: VerifiedFacts; onChange: (f: VerifiedFacts) => void }) {
  const items: SavedAnswer[] = facts.custom_answers ?? [];
  const set = (next: SavedAnswer[]) => onChange({ ...facts, custom_answers: next });
  const patch = (i: number, p: Partial<SavedAnswer>) => set(items.map((x, j) => (j === i ? { ...x, ...p } : x)));
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-[13px] font-semibold text-heading">Your saved answers</h3>
        <p className="text-xs text-muted-foreground">
          Write the answer once; it is used when an application asks the same (or a very similar) question. Answers marked
          "One job only" are offered as a suggestion for you to check, never filled as confirmed. Demographic questions are never answered for you.
        </p>
      </div>
      {items.map((it, i) => (
        <div key={i} className="grid gap-2 rounded-xl bg-paper-sunk/60 p-3 ring-1 ring-border/70 animate-in fade-in-0 slide-in-from-top-1 duration-200 sm:grid-cols-[1fr_1fr_auto]">
          <Input value={it.question} placeholder="Question, e.g. Are you comfortable working from office?" aria-label={`Question ${i + 1}`}
                 onChange={(e) => patch(i, { question: e.target.value })} />
          <Textarea rows={1} value={it.answer} placeholder="Your answer" aria-label={`Answer ${i + 1}`}
                    onChange={(e) => patch(i, { answer: e.target.value })} />
          <Button size="icon-sm" variant="ghost" aria-label={`Remove answer ${i + 1}`} onClick={() => set(items.filter((_, j) => j !== i))}><Trash2 /></Button>
          <div className="flex flex-wrap items-center gap-2 sm:col-span-3">
            <NativeSelect ariaLabel={`Use answer ${i + 1} for`} value={it.applies_to ?? "any"} onChange={(v) => patch(i, { applies_to: v as SavedAnswer["applies_to"] })}
                          options={[{ value: "any", label: "Any application (confirmed)" }, { value: "one_job", label: "One job only (check each time)" }]} />
            {it.applies_to === "one_job" && (
              <Input className="h-8 max-w-56" value={it.note ?? ""} placeholder="Which job or company" aria-label={`Note for answer ${i + 1}`}
                     onChange={(e) => patch(i, { note: e.target.value })} />
            )}
            {it.updated_at && <span className="text-xs text-muted-foreground">Saved {formatDate(it.updated_at)}</span>}
          </div>
        </div>
      ))}
      <Button size="sm" variant="outline" onClick={() => set([...items, { question: "", answer: "", applies_to: "any" }])} disabled={items.length >= 50}><Plus /> Add an answer</Button>
    </div>
  );
}

const SOURCES = [["greenhouse", "Greenhouse"], ["lever", "Lever"], ["ashby", "Ashby"], ["smartrecruiters", "SmartRecruiters"], ["recruitee", "Recruitee"],
                 ["adzuna_api", "Adzuna"], ["alert_email", "Alert e-mails"], ["remotive", "Remotive"], ["himalayas", "Himalayas"],
                 ["remoteok", "RemoteOK"], ["arbeitnow", "Arbeitnow"]] as const;

const KIND_LABELS: Record<NotificationKind, { label: string; description: string }> = {
  new_match: { label: "New matching jobs", description: "A job search found a job that matches you. Fine-tune these under New job alerts." },
  follow_up_due: { label: "Follow-up reminders", description: "The day you planned to follow up on an application has come." },
  interview_upcoming: { label: "Interview reminders", description: "You have an interview in the next 24 hours." },
  application_incomplete: { label: "Unfinished applications", description: "An application you started has sat untouched for 3 days, or we couldn't confirm it was sent." },
  listing_closed: { label: "Closed listings", description: "A job you saved or started applying for is no longer open." },
  discovery_failed: { label: "Job search problems", description: "One of your job searches couldn't run." },
};

type RowState = { state: "saving" } | { state: "saved" } | { state: "error"; message: string };

/** One switch per alert type. Each switch saves on its own, straight away. */
export function NotificationTypeSettings() {
  const prefs = useNotificationPrefs();
  const save = useSaveNotificationPrefs();
  const [pending, setPending] = useState<Partial<Record<NotificationKind, boolean>>>({});
  const [rows, setRows] = useState<Partial<Record<NotificationKind, RowState>>>({});
  const kinds = prefs.data?.kinds;
  const toggle = (kind: NotificationKind, on: boolean) => {
    setPending((p) => ({ ...p, [kind]: on }));
    setRows((r) => ({ ...r, [kind]: { state: "saving" } }));
    const done = (row: RowState) => {
      setPending((p) => { const next = { ...p }; delete next[kind]; return next; });
      setRows((r) => ({ ...r, [kind]: row }));
    };
    save.mutate({ kinds: { [kind]: on } }, {
      onSuccess: () => done({ state: "saved" }),
      onError: (e) => done({ state: "error", message: errorMessage(e) }),
    });
  };
  return (
    <Panel title="Which alerts you get"
           description="Alerts appear under the bell at the top of the page. Each switch saves straight away. Turning a type off stops new alerts of that type; ones you already have stay.">
      <div>
        {prefs.isPending ? <LoadingState label="Loading your alert settings…" />
          : prefs.isError ? <ErrorState title="Your alert settings couldn't be loaded" error={prefs.error} onRetry={() => void prefs.refetch()} />
          : !kinds ? <p className="rounded-lg bg-muted p-3 text-sm text-muted-foreground">These switches need a newer JobPilot server. Ask the portal owner to update it.</p>
          : (
            <ul className="divide-y overflow-hidden rounded-xl ring-1 ring-border">
              {NOTIFICATION_KINDS.map((kind) => {
                const on = pending[kind] ?? kinds[kind];
                const row = rows[kind];
                const id = `notify-kind-${kind}`;
                return (
                  <li key={kind} className="flex items-start gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <label htmlFor={id} className="text-sm font-medium">{KIND_LABELS[kind].label}</label>
                      <p id={`${id}-desc`} className="text-xs text-muted-foreground">{KIND_LABELS[kind].description}</p>
                      {row?.state === "error" && <p role="alert" className="mt-1 text-xs text-destructive">Couldn't save this change: {row.message}</p>}
                    </div>
                    <span aria-live="polite" className="mt-0.5 w-14 shrink-0 text-right text-xs text-muted-foreground">
                      {row?.state === "saving" ? <Loader2 className="ml-auto size-3.5 animate-spin" aria-label="Saving" />
                        : row?.state === "saved" ? <span className="inline-flex items-center gap-1 text-success animate-in fade-in-0 zoom-in-90 duration-200"><Check className="jp-bump size-3.5" aria-hidden />Saved</span>
                        : null}
                    </span>
                    <Switch id={id} className="mt-0.5" checked={on} aria-describedby={`${id}-desc`} disabled={row?.state === "saving"}
                            onCheckedChange={(c) => toggle(kind, !!c)} />
                  </li>
                );
              })}
            </ul>
          )}
      </div>
    </Panel>
  );
}

type NewJobPrefs = Pick<NotificationPrefs, "delivery" | "min_score" | "sources">;

/** How new-match alerts are delivered and filtered. Whether they are on at all is a switch in NotificationTypeSettings. */
export function NotificationSettings() {
  const prefs = useNotificationPrefs();
  const save = useSaveNotificationPrefs();
  const [edits, setP] = useState<NewJobPrefs | null>(null);
  const data = prefs.data;
  // Server values until the first edit; after that, later cache updates (e.g. an alert-type switch saving) leave the
  // edits not yet saved here alone.
  const p: NewJobPrefs | null = edits ?? (data ? { delivery: data.delivery, min_score: data.min_score, sources: data.sources } : null);
  const title = "New job alerts";
  const description = "How alerts about new matching jobs reach you. A high score is a guide to read the job, not proof that it suits you.";
  if (prefs.isError && !p) return <Panel title={title} description={description}><ErrorState title="Your alert settings couldn't be loaded" error={prefs.error} onRetry={() => void prefs.refetch()} /></Panel>;
  if (!p || !data) return <Panel title={title} description={description}><LoadingState /></Panel>;
  const toggleSource = (s: string) => setP({ ...p, sources: p.sources.includes(s) ? p.sources.filter((x) => x !== s) : [...p.sources, s] });
  return (
    <Panel title={title} description={description}>
      <div className="space-y-5 text-sm">
        {!data.new_matches && <p className="rounded-lg bg-muted p-3 text-xs text-muted-foreground">New matching job alerts are switched off above. These settings apply when you switch them back on.</p>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Delivery">
            <NativeSelect value={p.delivery} onChange={(v) => setP({ ...p, delivery: v as NotificationPrefs["delivery"] })} className="w-full"
                          options={[{ value: "immediate", label: "One alert per job" }, { value: "daily_digest", label: "One daily summary" }]} />
          </Field>
          <Field label="Minimum match score" hint="Empty: use each saved search's own threshold.">
            <Input className="readout max-w-32" type="number" min={0} max={100} value={p.min_score ?? ""} onChange={(e) => setP({ ...p, min_score: e.target.value === "" ? null : Number(e.target.value) })} />
          </Field>
        </div>
        <div>
          <div className="mb-2 font-medium">Only from these sources <span className="font-normal text-muted-foreground">(none selected = all)</span></div>
          <div className="flex flex-wrap gap-2">
            {SOURCES.map(([id, label]) => (
              <button key={id} type="button" aria-pressed={p.sources.includes(id)} onClick={() => toggleSource(id)}
                      className={`rounded-full px-3 py-1.5 text-xs font-medium ring-1 transition-[background-color,color,box-shadow] duration-150 focus-visible:outline-2 focus-visible:outline-ring active:scale-[.97] ${p.sources.includes(id) ? "bg-route-tint text-route ring-route/40" : "bg-card text-muted-foreground ring-border hover:text-foreground hover:ring-foreground/25"}`}>{label}</button>
            ))}
          </div>
        </div>
        <p className="rounded-lg bg-muted p-3 text-xs text-muted-foreground">E-mail delivery is not available yet: it needs an e-mail (SMTP) account configured on the server.</p>
        <div data-save-bar className="flex justify-end">
          <Button onClick={() => save.mutate(p, { onSuccess: () => toast.success("Saved. Locked in."), onError: (e) => toast.error(errorMessage(e)) })} disabled={save.isPending}>Save</Button>
        </div>
      </div>
    </Panel>
  );
}
