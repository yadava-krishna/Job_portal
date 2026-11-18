import { useState } from "react";
import { ArrowDownRight, ArrowUpRight, BadgeCheck, ExternalLink, Info, Loader2, Plus, Trash2, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, Field, NativeSelect } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Note, Panel } from "@/features/growth/ui";
import { backendMessage, useAddEvidence, useAddSkill, useDeleteEvidence, useDeleteSkill, useMatchHistory, useSetSkillState, useSkills } from "./hooks";
import { EVIDENCE_TYPES, evidenceLabel, isHttpsLink, SKILL_STATES, stateLabel } from "./format";
import { StateStepper } from "./labels";
import type { Evidence, EvidenceType, Skill } from "./types";

export function SkillsTab() {
  const skills = useSkills();
  if (skills.isLoading) return <div className="space-y-3"><Skeleton className="h-20 rounded-2xl" /><Skeleton className="h-28 rounded-2xl" /><Skeleton className="h-28 rounded-2xl" /></div>;
  if (skills.isError) return <EmptyState title="Couldn't load your skills">{errorMessage(skills.error)}</EmptyState>;
  const list = skills.data?.skills ?? [];
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
      <Panel title="Your skills" count={list.length} icon={<BadgeCheck />}
             description="Each skill moves up six steps as you add evidence." bodyClassName="px-0 pb-1 sm:px-0">
        {list.length === 0 ? (
          <div className="px-4 pb-3 sm:px-5">
            <EmptyState title="No skills yet. Let's fix that.">Skills from your resume appear here automatically. You can also add one with the form.</EmptyState>
          </div>
        ) : (
          <ul className="divide-y divide-border/70">{list.map((s) => <SkillCard key={s.id} skill={s} />)}</ul>
        )}
      </Panel>
      <div className="space-y-4">
      <Note tone="violet" icon={<Info />} className="rounded-2xl px-4 py-3 text-[13px]">
        <p className="font-semibold">Courses and projects never count as work experience.</p>
        <p className="mt-0.5 text-foreground/75">
          You can move a skill up only as far as your evidence supports: a course shows you are learning, a project shows you can use it,
          and only a real job counts as professional experience.
        </p>
      </Note>
      <AddSkillForm />
      <ScoreHistory />
      </div>
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
      onSuccess: () => { toast.success("Skill added. Now stack some evidence."); setName(""); setProficiency(""); setYears(""); },
      onError: (err) => toast.error(errorMessage(err)),
    });
  };
  return (
    <Panel title="Add a skill" icon={<Plus />} description={<>New skills start at "Aware". Add evidence to move them up.</>}>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_8rem] lg:grid-cols-[1fr_5.5rem]">
        <Field label="Skill" htmlFor="sk-name" className="sm:col-span-2"><Input id="sk-name" value={name} maxLength={100} placeholder="e.g. SAP FICO" onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="How well you know it" htmlFor="sk-prof">
          <NativeSelect id="sk-prof" value={proficiency} onChange={setProficiency} className="w-full"
                        options={[{ value: "", label: "Not sure" }, { value: "beginner", label: "Beginner" }, { value: "intermediate", label: "Intermediate" },
                                  { value: "advanced", label: "Advanced" }, { value: "expert", label: "Expert" }]} />
        </Field>
        <Field label="Years" htmlFor="sk-years"><Input id="sk-years" type="number" min={0} max={50} step={0.5} value={years} onChange={(e) => setYears(e.target.value)} /></Field>
        <Button type="submit" className="sm:col-span-2" disabled={!name.trim() || add.isPending}>{add.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Add skill</Button>
      </form>
    </Panel>
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
    <li className="space-y-2.5 px-4 py-3.5 sm:px-5">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
        <div className="min-w-0">
          <div className="font-semibold text-heading">{skill.name}</div>
          <div className="text-xs text-muted-foreground">
            {skill.source === "resume_parse" ? "From your resume" : "Added by you"}
            {skill.proficiency && ` · ${skill.proficiency}`}
            {skill.years != null && ` · ${skill.years} yr`}
            {` · Your evidence supports up to "${stateLabel(skill.evidence_supports)}"`}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <NativeSelect id={`state-${skill.id}`} ariaLabel={`Step for ${skill.name}`} value={skill.state} onChange={changeState} className="h-8 rounded-full px-2.5 text-[12.5px]"
                        options={SKILL_STATES.map((s) => ({ value: s.key, label: s.label }))} />
          <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}><Plus /> Add evidence</Button>
          <Button size="icon-sm" variant="ghost" className="text-muted-foreground hover:text-destructive" aria-label={`Remove ${skill.name}`} onClick={() => setConfirm({ kind: "skill" })}><Trash2 /></Button>
        </div>
      </div>
      <StateStepper state={skill.state} supports={skill.evidence_supports} />
      {setState.isPending && <p className="text-xs text-muted-foreground">Saving…</p>}
      {stateError && <p role="alert" className="rounded-lg bg-destructive/10 px-2.5 py-1.5 text-xs text-destructive">{stateError}</p>}

      {skill.evidence.length > 0 ? (
        <ul className="space-y-1">
          {skill.evidence.map((e) => (
            <li key={e.id} className="flex items-start justify-between gap-2 rounded-xl bg-paper-sunk/70 px-3 py-2 text-[13px]">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="rounded-full bg-card px-2 py-0.5 text-[11px] font-medium text-heading ring-1 ring-border/70">{evidenceLabel(e.type)}</span>
                  <span className="font-medium">{e.title}</span>
                  {e.url && <a href={e.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-route underline-offset-2 hover:underline">Open link <ExternalLink className="size-3" /></a>}
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {e.occurred_on ? formatDate(e.occurred_on) : `Added ${formatDate(e.created_at)}`}
                  {e.source === "learning_session" && " · from a learning session"}
                </div>
                {e.description && <p className="mt-1 text-xs text-muted-foreground">{e.description}</p>}
              </div>
              <Button size="icon-xs" variant="ghost" className="text-muted-foreground hover:text-destructive" aria-label={`Delete evidence ${e.title}`} onClick={() => setConfirm({ kind: "evidence", item: e })}><Trash2 /></Button>
            </li>
          ))}
        </ul>
      ) : <p className="text-xs text-muted-foreground">No evidence yet. Add a course, project or job to move this skill up.</p>}

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
    </li>
  );
}

/** Before/after match scores caused by evidence the candidate added or removed (MAT-13). */
function ScoreHistory() {
  const h = useMatchHistory();
  const rows = Array.isArray(h.data) ? h.data.slice(0, 8) : [];
  if (!rows.length) return null;
  return (
    <Panel data-testid="score-history" title="How your evidence changed your matches" icon={<TrendingUp />}
           description="When a skill reaches project or work evidence, the jobs that ask for it are re-scored. Courses alone don't change scores."
           bodyClassName="px-0 pb-1 sm:px-0">
      <ul className="divide-y divide-border/70 text-[13px]">
        {rows.map((r) => {
          const up = (r.new_score ?? 0) >= (r.old_score ?? 0);
          return (
            <li key={r.id} className="flex items-start justify-between gap-3 px-4 py-2.5 sm:px-5">
              <span className="min-w-0"><a className="font-medium hover:underline" href={`#/discover?job=${r.user_job_id}`}>{r.title}</a>
                <span className="text-muted-foreground"> · {r.company}</span>
                <span className="block text-xs text-muted-foreground">{r.reason} · {formatDate(r.created_at)}</span></span>
              <span className={cn("readout inline-flex shrink-0 items-center gap-1 font-semibold", up ? "text-route" : "text-destructive")}>
                {up ? <ArrowUpRight className="size-3.5" aria-hidden /> : <ArrowDownRight className="size-3.5" aria-hidden />}
                {Math.round(r.old_score ?? 0)}% → {Math.round(r.new_score ?? 0)}%
              </span>
            </li>
          );
        })}
      </ul>
    </Panel>
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
