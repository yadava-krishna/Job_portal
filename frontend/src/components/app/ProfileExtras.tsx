import { useEffect, useRef, useState } from "react";
import { Download, Eye, Loader2, Plus, Star, Trash2, UploadCloud } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Field, NativeSelect } from "@/components/app/common";
import { downloadFile, errorMessage, previewFile } from "@/lib/api";
import { bytes, formatDate } from "@/lib/format";
import { useNotificationPrefs, useResumeAction, useResumes, useSaveNotificationPrefs, type NotificationPrefs } from "@/services/queries";
import type { VerifiedFacts } from "@/types/api";

/** Several resume versions (e.g. one per role family); the default one is used for applications and the extension. */
export function ResumeVersions() {
  const resumes = useResumes();
  const act = useResumeAction();
  const fileRef = useRef<HTMLInputElement>(null);
  const [makeDefault, setMakeDefault] = useState(false);
  const [editing, setEditing] = useState<{ id: number; name: string } | null>(null);
  const run = (a: Parameters<typeof act.mutate>[0], ok: string) => act.mutate(a, { onSuccess: () => toast.success(ok), onError: (e) => toast.error(errorMessage(e)) });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Resume versions</CardTitle>
        <CardDescription>Keep role-specific resumes. The default is attached by Fill with JobPilot and recorded on new applications. Changing the default does not change your confirmed profile.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {resumes.isLoading && <Loader2 className="animate-spin" />}
        {resumes.data?.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm">
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
              {r.is_active ? <Badge>Default</Badge> : <Button size="sm" variant="outline" onClick={() => run({ kind: "default", id: r.id }, "Default resume changed")}><Star /> Make default</Button>}
              <Button size="icon-sm" variant="ghost" aria-label="Preview" onClick={() => previewFile(`/profile/resumes/${r.id}/file?inline=true`).catch((e) => toast.error(errorMessage(e)))}><Eye /></Button>
              <Button size="icon-sm" variant="ghost" aria-label="Download" onClick={() => downloadFile(`/profile/resumes/${r.id}/file`, r.original_filename).catch((e) => toast.error(errorMessage(e)))}><Download /></Button>
              {!r.is_active && <Button size="icon-sm" variant="ghost" aria-label="Delete" onClick={() => run({ kind: "delete", id: r.id }, "Deleted")}><Trash2 /></Button>}
            </div>
          </div>
        ))}
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept="application/pdf,.pdf" className="sr-only" aria-label="Add a resume version"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) run({ kind: "upload", file: f, makeDefault }, makeDefault ? "Uploaded. Review your profile below." : "Added"); e.target.value = ""; }} />
          <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={act.isPending}>{act.isPending ? <Loader2 className="animate-spin" /> : <UploadCloud />} Add a version</Button>
          <label className="flex items-center gap-2 text-sm"><Switch checked={makeDefault} onCheckedChange={(c) => setMakeDefault(!!c)} /> Make it the default (and re-read it into the profile for review)</label>
        </div>
      </CardContent>
    </Card>
  );
}

/** The user's own approved answers to questions applications keep asking. */
export function AnswerBank({ facts, onChange }: { facts: VerifiedFacts; onChange: (f: VerifiedFacts) => void }) {
  const items = facts.custom_answers ?? [];
  const set = (next: { question: string; answer: string }[]) => onChange({ ...facts, custom_answers: next });
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold">Your saved answers</h3>
        <p className="text-xs text-muted-foreground">Write the answer once; it is used when an application asks the same (or a very similar) question. Demographic questions are never answered for you.</p>
      </div>
      {items.map((it, i) => (
        <div key={i} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-[1fr_1fr_auto]">
          <Input value={it.question} placeholder="Question, e.g. Are you comfortable working from office?" aria-label={`Question ${i + 1}`}
                 onChange={(e) => set(items.map((x, j) => (j === i ? { ...x, question: e.target.value } : x)))} />
          <Textarea rows={1} value={it.answer} placeholder="Your answer" aria-label={`Answer ${i + 1}`}
                    onChange={(e) => set(items.map((x, j) => (j === i ? { ...x, answer: e.target.value } : x)))} />
          <Button size="icon-sm" variant="ghost" aria-label="Remove" onClick={() => set(items.filter((_, j) => j !== i))}><Trash2 /></Button>
        </div>
      ))}
      <Button size="sm" variant="outline" onClick={() => set([...items, { question: "", answer: "" }])} disabled={items.length >= 50}><Plus /> Add an answer</Button>
    </div>
  );
}

const SOURCES = [["greenhouse", "Greenhouse"], ["lever", "Lever"], ["ashby", "Ashby"], ["smartrecruiters", "SmartRecruiters"], ["recruitee", "Recruitee"],
                 ["adzuna_api", "Adzuna"], ["alert_email", "Alert e-mails"]] as const;

export function NotificationSettings() {
  const { data } = useNotificationPrefs();
  const save = useSaveNotificationPrefs();
  const [p, setP] = useState<NotificationPrefs | null>(null);
  useEffect(() => { if (data) setP(data); }, [data]);
  if (!p) return <Loader2 className="animate-spin" />;
  const toggleSource = (s: string) => setP({ ...p, sources: p.sources.includes(s) ? p.sources.filter((x) => x !== s) : [...p.sources, s] });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Notifications</CardTitle>
        <CardDescription>In-app alerts when discovery finds new matching jobs. A high score is a guide to read the job, not proof that it suits you.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <label className="flex items-center gap-2"><Switch checked={p.new_matches} onCheckedChange={(c) => setP({ ...p, new_matches: !!c })} /> Notify me about new matching jobs</label>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Delivery">
            <NativeSelect value={p.delivery} onChange={(v) => setP({ ...p, delivery: v as NotificationPrefs["delivery"] })} className="w-full"
                          options={[{ value: "immediate", label: "One alert per job" }, { value: "daily_digest", label: "One daily summary" }]} />
          </Field>
          <Field label="Minimum match score" hint="Empty: use each saved search's own threshold.">
            <Input type="number" min={0} max={100} value={p.min_score ?? ""} onChange={(e) => setP({ ...p, min_score: e.target.value === "" ? null : Number(e.target.value) })} />
          </Field>
        </div>
        <div>
          <div className="mb-1 font-medium">Only from these sources <span className="font-normal text-muted-foreground">(none selected = all)</span></div>
          <div className="flex flex-wrap gap-2">
            {SOURCES.map(([id, label]) => (
              <button key={id} type="button" aria-pressed={p.sources.includes(id)} onClick={() => toggleSource(id)}
                      className={`rounded-full border px-3 py-1 text-xs ${p.sources.includes(id) ? "border-primary bg-primary/10 text-primary" : ""}`}>{label}</button>
            ))}
          </div>
        </div>
        <p className="rounded-lg bg-muted p-3 text-xs text-muted-foreground">E-mail delivery is not available yet: it needs an e-mail (SMTP) account configured on the server.</p>
        <div className="flex justify-end">
          <Button onClick={() => save.mutate(p, { onSuccess: () => toast.success("Saved"), onError: (e) => toast.error(errorMessage(e)) })} disabled={save.isPending}>Save</Button>
        </div>
      </CardContent>
    </Card>
  );
}
