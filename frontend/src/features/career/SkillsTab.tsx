import { useState } from "react";
import { ExternalLink, Info, Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, Field, NativeSelect } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { backendMessage, useAddEvidence, useAddSkill, useDeleteEvidence, useDeleteSkill, useMatchHistory, useSetSkillState, useSkills } from "./hooks";
import { EVIDENCE_TYPES, evidenceLabel, isHttpsLink, SKILL_STATES, stateLabel } from "./format";
import { StateStepper } from "./labels";
import type { Evidence, EvidenceType, Skill } from "./types";

export function SkillsTab() {
  const skills = useSkills();
  if (skills.isLoading) return <div className="space-y-3"><Skeleton className="h-20" /><Skeleton className="h-28" /><Skeleton className="h-28" /></div>;
  if (skills.isError) return <EmptyState title="Couldn't load your skills">{errorMessage(skills.error)}</EmptyState>;
  const list = skills.data?.skills ?? [];
  return (
    <div className="space-y-6">
      <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
        <Info className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <div>
          <p className="font-medium">Courses and projects never count as work experience.</p>
          <p className="text-muted-foreground">
            Each skill moves through six steps. You can move a skill up only as far as your evidence supports: a course shows you are
            learning, a project shows you can use it, and only a real job counts as professional experience.
          </p>
        </div>
      </div>
      <ScoreHistory />
      <AddSkillForm />
      {list.length === 0 ? (
        <EmptyState title="No skills yet">Skills from your resume appear here automatically. You can also add one above.</EmptyState>
      ) : (
        <div className="space-y-3">{list.map((s) => <SkillCard key={s.id} skill={s} />)}</div>
      )}
    </div>
  );
}

function AddSkillForm() {
  const add = useAddSkill();
  const [name, setName] = useState("");
  const [proficiency, setProficiency] = useState("");
  const [years, setYears] = useState("");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    add.mutate({ name: name.trim(), proficiency: proficiency || null, years: years === "" ? null : Number(years) }, {
      onSuccess: () => { toast.success("Skill added"); setName(""); setProficiency(""); setYears(""); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };
  return (
    <Card>
      <CardHeader><CardTitle>Add a skill</CardTitle><CardDescription>New skills start at "Aware". Add evidence to move them up.</CardDescription></CardHeader>
      <CardContent>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_12rem_8rem_auto] sm:items-end">
          <Field label="Skill" htmlFor="sk-name"><Input id="sk-name" value={name} maxLength={100} placeholder="e.g. SAP FICO" onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="How well you know it" htmlFor="sk-prof">
            <NativeSelect id="sk-prof" value={proficiency} onChange={setProficiency} className="w-full"
                          options={[{ value: "", label: "Not sure" }, { value: "beginner", label: "Beginner" }, { value: "intermediate", label: "Intermediate" },
                                    { value: "advanced", label: "Advanced" }, { value: "expert", label: "Expert" }]} />
          </Field>
          <Field label="Years" htmlFor="sk-years"><Input id="sk-years" type="number" min={0} max={50} step={0.5} value={years} onChange={(e) => setYears(e.target.value)} /></Field>
          <Button type="submit" disabled={!name.trim() || add.isPending}>{add.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Add skill</Button>
        </form>
      </CardContent>
    </Card>
  );
}

function SkillCard({ skill }: { skill: Skill }) {
  const setState = useSetSkillState();
  const delSkill = useDeleteSkill();
  const delEvidence = useDeleteEvidence();
  const [stateError, setStateError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [confirm, setConfirm] = useState<{ kind: "evidence"; item: Evidence } | { kind: "skill" } | null>(null);

  const changeState = (state: string) => {
    if (state === skill.state) return;
    setStateError(null);
    setState.mutate({ id: skill.id, state }, {
      onSuccess: (s) => toast.success(`${s.name}: now "${s.state_label}"`),
      onError: (err) => setStateError(backendMessage(err)),
    });
  };

  const doDelete = () => {
    if (!confirm) return;
    const done = { onSuccess: () => { toast.success("Removed"); setConfirm(null); }, onError: (err: unknown) => toast.error(errorMessage(err)) };
    if (confirm.kind === "evidence") delEvidence.mutate(confirm.item.id, done);
    else delSkill.mutate(skill.id, done);
  };

  return (
    <Card className="gap-3 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-medium">{skill.name}</div>
          <div className="text-xs text-muted-foreground">
            {skill.source === "resume_parse" ? "From your resume" : "Added by you"}
            {skill.proficiency && ` · ${skill.proficiency}`}
            {skill.years != null && ` · ${skill.years} yr`}
            {` · Your evidence supports up to "${stateLabel(skill.evidence_supports)}"`}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <NativeSelect id={`state-${skill.id}`} ariaLabel={`Step for ${skill.name}`} value={skill.state} onChange={changeState}
                        options={SKILL_STATES.map((s) => ({ value: s.key, label: s.label }))} />
          <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}><Plus /> Add evidence</Button>
          <Button size="icon-sm" variant="ghost" aria-label={`Remove ${skill.name}`} onClick={() => setConfirm({ kind: "skill" })}><Trash2 /></Button>
        </div>
      </div>
      <StateStepper state={skill.state} supports={skill.evidence_supports} />
      {setState.isPending && <p className="text-xs text-muted-foreground">Saving…</p>}
      {stateError && <p role="alert" className="rounded-md bg-destructive/10 px-2.5 py-1.5 text-xs text-destructive">{stateError}</p>}

      {skill.evidence.length > 0 ? (
        <ul className="space-y-1.5">
          {skill.evidence.map((e) => (
            <li key={e.id} className="flex items-start justify-between gap-2 rounded-lg border px-3 py-2 text-sm">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-secondary px-1.5 py-0.5 text-xs">{evidenceLabel(e.type)}</span>
                  <span className="font-medium">{e.title}</span>
                  {e.url && <a href={e.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-primary underline-offset-2 hover:underline">Open link <ExternalLink className="size-3" /></a>}
                </div>
                <div className="text-xs text-muted-foreground">
                  {e.occurred_on ? formatDate(e.occurred_on) : `Added ${formatDate(e.created_at)}`}
                  {e.source === "learning_session" && " · from a learning session"}
                </div>
                {e.description && <p className="mt-1 text-xs text-muted-foreground">{e.description}</p>}
              </div>
              <Button size="icon-xs" variant="ghost" aria-label={`Delete evidence ${e.title}`} onClick={() => setConfirm({ kind: "evidence", item: e })}><Trash2 /></Button>
            </li>
          ))}
        </ul>
      ) : <p className="text-xs text-muted-foreground">No evidence yet.</p>}

      <AddEvidenceDialog skill={skill} open={addOpen} onOpenChange={setAddOpen} />

      <Dialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{confirm?.kind === "evidence" ? "Delete this evidence?" : `Remove ${skill.name}?`}</DialogTitle>
            <DialogDescription>
              {confirm?.kind === "evidence"
                ? `"${confirm.item.title}" will be removed. If it was what supported the skill's current step, the skill may move back down.`
                : "The skill and all its evidence will be removed. Skills on your resume may be added back the next time it is read."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)}>Cancel</Button>
            <Button variant="destructive" disabled={delEvidence.isPending || delSkill.isPending} onClick={doDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/** Before/after match scores caused by evidence the candidate added or removed (MAT-13). */
function ScoreHistory() {
  const h = useMatchHistory();
  const rows = Array.isArray(h.data) ? h.data.slice(0, 8) : [];
  if (!rows.length) return null;
  return (
    <Card data-testid="score-history">
      <CardHeader>
        <CardTitle className="text-base">How your evidence changed your matches</CardTitle>
        <CardDescription>When a skill reaches project or work evidence, the jobs that ask for it are re-scored. Courses alone don't change scores.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y text-sm">
          {rows.map((r) => {
            const up = (r.new_score ?? 0) >= (r.old_score ?? 0);
            return (
              <li key={r.id} className="flex flex-wrap items-baseline justify-between gap-2 py-2">
                <span className="min-w-0"><a className="font-medium hover:underline" href={`#/discover?job=${r.user_job_id}`}>{r.title}</a>
                  <span className="text-muted-foreground"> · {r.company}</span>
                  <span className="block text-xs text-muted-foreground">{r.reason} · {formatDate(r.created_at)}</span></span>
                <span className={up ? "font-semibold text-emerald-700 dark:text-emerald-400" : "font-semibold text-rose-700 dark:text-rose-400"}>
                  {Math.round(r.old_score ?? 0)}% → {Math.round(r.new_score ?? 0)}%
                </span>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}

function AddEvidenceDialog({ skill, open, onOpenChange }: { skill: Skill; open: boolean; onOpenChange: (o: boolean) => void }) {
  const add = useAddEvidence();
  const blank = { evidence_type: "course" as EvidenceType, title: "", url: "", description: "", occurred_on: "" };
  const [f, setF] = useState(blank);
  const urlBad = f.url.trim() !== "" && !isHttpsLink(f.url);
  const canSave = f.title.trim().length >= 2 && !urlBad && !add.isPending;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSave) return;
    add.mutate({
      skillId: skill.id,
      body: { evidence_type: f.evidence_type, title: f.title.trim(), url: f.url.trim() || null, description: f.description.trim() || null, occurred_on: f.occurred_on || null },
    }, {
      onSuccess: (s) => {
        const ups = (s.score_changes ?? []).filter((c) => (c.new_score ?? 0) > (c.old_score ?? 0));
        toast.success(`Evidence added. ${s.name} is now "${s.state_label}".`,
                      ups.length ? { description: `${ups.length} job match${ups.length === 1 ? "" : "es"} went up, e.g. ${ups[0].title}: ${Math.round(ups[0].old_score ?? 0)}% → ${Math.round(ups[0].new_score ?? 0)}%.` } : undefined);
        setF(blank); onOpenChange(false);
      },
      onError: (err) => toast.error(backendMessage(err)),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add evidence for {skill.name}</DialogTitle>
          <DialogDescription>Something that shows you have used or studied this skill. Courses and projects never count as work experience.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <Field label="What kind of evidence" htmlFor="ev-type">
            <NativeSelect id="ev-type" value={f.evidence_type} onChange={(v) => setF({ ...f, evidence_type: v as EvidenceType })} options={EVIDENCE_TYPES} className="w-full" />
          </Field>
          <Field label="Title" htmlFor="ev-title"><Input id="ev-title" value={f.title} maxLength={300} placeholder="e.g. Built a month-end close tracker in Excel" onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Link (optional)" htmlFor="ev-url" hint={urlBad ? <span className="text-destructive">Links must start with https://</span> : "A certificate, repository or portfolio page. Must start with https://"}>
            <Input id="ev-url" type="url" value={f.url} placeholder="https://" aria-invalid={urlBad} onChange={(e) => setF({ ...f, url: e.target.value })} />
          </Field>
          <Field label="When (optional)" htmlFor="ev-date"><Input id="ev-date" type="date" value={f.occurred_on} onChange={(e) => setF({ ...f, occurred_on: e.target.value })} /></Field>
          <Field label="Details (optional)" htmlFor="ev-desc"><Textarea id="ev-desc" value={f.description} maxLength={5000} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={!canSave}>{add.isPending && <Loader2 className="animate-spin" />} Add evidence</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
