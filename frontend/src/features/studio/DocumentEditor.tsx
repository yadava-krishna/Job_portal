import { useState, type ReactNode } from "react";
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Eye, EyeOff, Plus, Trash2, Eraser } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Field, TagInput } from "@/components/app/common";
import { cn } from "@/lib/utils";
import { move, newKey, type Block, type Bullet, type ContactContent, type EntryContent, type Section, type SectionType } from "./api";
import { ConfirmDialog } from "./parts";

const entryLabels: Partial<Record<SectionType, [string, string]>> = {
  experience: ["Job title", "Company"],
  education: ["Degree / course", "Institution"],
  projects: ["Project name", "Organisation (optional)"],
  certifications: ["Certification", "Issuer (optional)"],
  publications: ["Title", "Publisher (optional)"],
  achievements: ["Title (optional)", "Organisation (optional)"],
};

type Confirm = { title: string; body: string; label: string; run: () => void };

/** Structured editor for a resume document: sections → blocks (contact, text, entry, skill group) → bullets. */
export function DocumentEditor({ sections, onChange, readOnly }: { sections: Section[]; onChange: (s: Section[]) => void; readOnly: boolean }) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [confirm, setConfirm] = useState<Confirm | null>(null);

  const setSection = (si: number, fn: (s: Section) => Section) => onChange(sections.map((s, i) => (i === si ? fn(s) : s)));
  const setBlocks = (si: number, fn: (b: Block[]) => Block[]) => setSection(si, (s) => ({ ...s, blocks: fn(s.blocks) }));
  const setBlock = (si: number, bi: number, fn: (b: Block) => Block) => setBlocks(si, (bs) => bs.map((b, i) => (i === bi ? fn(b) : b)));

  const addBlock = (si: number, s: Section) => {
    const base = { _k: newKey(), source_profile_ref: null, visible: true, bullets: [] as Bullet[] };
    const block: Block = s.type === "skills" ? { ...base, type: "skill_group", content: { label: "", items: [] } }
      : s.type === "summary" ? { ...base, type: "text", content: { text: "" } }
        : { ...base, type: "entry", content: { title: "", organization: "", start: "", end: "", current: false } };
    setSection(si, (x) => ({ ...x, visible: true, blocks: [...x.blocks, block] }));
  };

  return (
    <fieldset disabled={readOnly} className="min-w-0 space-y-3">
      <legend className="sr-only">Resume content</legend>
      {sections.map((s, si) => {
        const key = s._k ?? String(si);
        const open = !collapsed[key];
        const canAdd = s.type !== "header" && !(s.type === "summary" && s.blocks.length > 0);
        return (
          <section key={key} className={cn("rounded-xl border bg-card", !s.visible && "opacity-70")} aria-label={`${s.heading} section`}>
            <div className="flex flex-wrap items-center gap-1.5 border-b px-2 py-1.5">
              <Button size="icon-xs" variant="ghost" aria-label={open ? `Collapse ${s.heading}` : `Expand ${s.heading}`} aria-expanded={open}
                      onClick={() => setCollapsed({ ...collapsed, [key]: open })}>
                {open ? <ChevronDown /> : <ChevronRight />}
              </Button>
              <label htmlFor={`${key}-heading`} className="sr-only">Section heading</label>
              <Input id={`${key}-heading`} value={s.heading} maxLength={80} onChange={(e) => setSection(si, (x) => ({ ...x, heading: e.target.value }))}
                     className="h-7 max-w-56 flex-1 border-transparent px-1.5 font-medium shadow-none hover:border-input focus-visible:border-input" />
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{s.type}</span>
              <div className="ml-auto flex items-center gap-1">
                <span className="flex items-center gap-1.5 pr-1 text-xs text-muted-foreground">
                  <Switch size="sm" checked={s.visible} disabled={readOnly} aria-label={`Show ${s.heading} on the resume`}
                          onCheckedChange={(c) => setSection(si, (x) => ({ ...x, visible: !!c }))} />
                  {s.visible ? "Shown" : "Hidden"}
                </span>
                <Button size="icon-xs" variant="ghost" aria-label={`Move ${s.heading} up`} disabled={si === 0} onClick={() => onChange(move(sections, si, si - 1))}><ArrowUp /></Button>
                <Button size="icon-xs" variant="ghost" aria-label={`Move ${s.heading} down`} disabled={si === sections.length - 1} onClick={() => onChange(move(sections, si, si + 1))}><ArrowDown /></Button>
                {s.type !== "header" && (
                  <Button size="icon-xs" variant="ghost" aria-label={`Clear all content in ${s.heading}`} disabled={!s.blocks.length}
                          onClick={() => setConfirm({ title: `Clear "${s.heading}"?`, label: "Clear section",
                            body: `All ${s.blocks.length} item(s) in this section will be removed from this resume version. Your profile is not changed.`,
                            run: () => setBlocks(si, () => []) })}><Eraser /></Button>
                )}
              </div>
            </div>
            {open && (
              <div className="space-y-2 p-2">
                {!s.blocks.length && <p className="px-1 py-2 text-xs text-muted-foreground">Nothing here yet.</p>}
                {s.blocks.map((b, bi) => (
                  <BlockEditor key={b._k ?? bi} section={s} block={b} index={bi} count={s.blocks.length} readOnly={readOnly}
                               onChange={(nb) => setBlock(si, bi, () => nb)}
                               onMove={(to) => setBlocks(si, (bs) => move(bs, bi, to))}
                               onRemove={() => setConfirm({ title: "Remove this item?", label: "Remove",
                                 body: `"${blockTitle(b) || "This item"}" and its bullets will be removed from this resume version. Your profile is not changed.`,
                                 run: () => setBlocks(si, (bs) => bs.filter((_, i) => i !== bi)) })} />
                ))}
                {canAdd && (
                  <Button size="xs" variant="outline" onClick={() => addBlock(si, s)}>
                    <Plus /> {s.type === "skills" ? "Add skill group" : s.type === "summary" ? "Add summary" : "Add entry"}
                  </Button>
                )}
              </div>
            )}
          </section>
        );
      })}
      <ConfirmDialog open={!!confirm} title={confirm?.title ?? ""} confirmLabel={confirm?.label} onCancel={() => setConfirm(null)}
                     onConfirm={() => { confirm?.run(); setConfirm(null); }}>
        {confirm?.body}
      </ConfirmDialog>
    </fieldset>
  );
}

function blockTitle(b: Block): string {
  if (b.type === "entry") return [b.content.title, b.content.organization].filter(Boolean).join(" — ");
  if (b.type === "skill_group") return b.content.label || "Skill group";
  if (b.type === "text") return "Summary";
  return b.content.name ?? "Contact";
}

function BlockEditor({ section, block, index, count, readOnly, onChange, onMove, onRemove }: {
  section: Section; block: Block; index: number; count: number; readOnly: boolean;
  onChange: (b: Block) => void; onMove: (to: number) => void; onRemove: () => void;
}) {
  const id = block._k ?? `${section._k}-${index}`;
  const label = blockTitle(block) || `Item ${index + 1}`;
  const controls = block.type !== "contact" && (
    <div className="flex items-center gap-0.5">
      <Button size="icon-xs" variant="ghost" aria-label={block.visible ? `Hide ${label}` : `Show ${label}`} aria-pressed={!block.visible}
              onClick={() => onChange({ ...block, visible: !block.visible })}>{block.visible ? <Eye /> : <EyeOff />}</Button>
      {count > 1 && <>
        <Button size="icon-xs" variant="ghost" aria-label={`Move ${label} up`} disabled={index === 0} onClick={() => onMove(index - 1)}><ArrowUp /></Button>
        <Button size="icon-xs" variant="ghost" aria-label={`Move ${label} down`} disabled={index === count - 1} onClick={() => onMove(index + 1)}><ArrowDown /></Button>
      </>}
      <Button size="icon-xs" variant="ghost" aria-label={`Remove ${label}`} onClick={onRemove}><Trash2 /></Button>
    </div>
  );

  return (
    <div className={cn("rounded-lg border bg-background p-2.5", !block.visible && "border-dashed opacity-70")}>
      {block.type === "contact" && <ContactEditor id={id} c={block.content} onChange={(content) => onChange({ ...block, content })} />}

      {block.type === "text" && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between"><label htmlFor={`${id}-text`} className="text-sm font-medium">Text</label>{controls}</div>
          <Textarea id={`${id}-text`} rows={4} value={block.content.text ?? ""} onChange={(e) => onChange({ ...block, content: { ...block.content, text: e.target.value } })} />
        </div>
      )}

      {block.type === "skill_group" && (
        <div className="space-y-2">
          <div className="flex items-end gap-2">
            <Field label="Group label (optional)" htmlFor={`${id}-label`} className="flex-1">
              <Input id={`${id}-label`} value={block.content.label ?? ""} placeholder="e.g. Tools" onChange={(e) => onChange({ ...block, content: { ...block.content, label: e.target.value } })} />
            </Field>
            {controls}
          </div>
          <Field label="Skills" htmlFor={`${id}-items`} hint={readOnly ? undefined : "Press Enter or comma to add."}>
            <TagInput id={`${id}-items`} value={block.content.items ?? []} onChange={(items) => onChange({ ...block, content: { ...block.content, items } })} placeholder="Add a skill" />
          </Field>
        </div>
      )}

      {block.type === "entry" && (
        <EntryEditor id={id} type={section.type} c={block.content} controls={controls} onChange={(content) => onChange({ ...block, content })} />
      )}

      {(block.type === "entry" || block.bullets.length > 0) && (
        <BulletsEditor id={id} bullets={block.bullets} onChange={(bullets) => onChange({ ...block, bullets } as Block)} />
      )}
    </div>
  );
}

function ContactEditor({ id, c, onChange }: { id: string; c: ContactContent; onChange: (c: ContactContent) => void }) {
  const text = (k: keyof Omit<ContactContent, "links">, label: string, type = "text") => (
    <Field label={label} htmlFor={`${id}-${k}`}>
      <Input id={`${id}-${k}`} type={type} value={(c[k] as string | null | undefined) ?? ""} onChange={(e) => onChange({ ...c, [k]: e.target.value })} />
    </Field>
  );
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {text("name", "Full name")}
      {text("headline", "Headline")}
      {text("email", "E-mail", "email")}
      {text("phone", "Phone", "tel")}
      {text("location", "Location")}
      <Field label="Links" htmlFor={`${id}-links`} className="sm:col-span-2">
        <TagInput id={`${id}-links`} value={c.links ?? []} onChange={(links) => onChange({ ...c, links })} placeholder="LinkedIn, GitHub or portfolio URL" />
      </Field>
    </div>
  );
}

function EntryEditor({ id, type, c, controls, onChange }: { id: string; type: SectionType; c: EntryContent; controls: ReactNode; onChange: (c: EntryContent) => void }) {
  const [titleLabel, orgLabel] = entryLabels[type] ?? ["Title", "Organisation"];
  const set = (k: keyof EntryContent, v: string | boolean) => onChange({ ...c, [k]: v });
  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2">
        <div className="grid flex-1 gap-2 sm:grid-cols-2">
          <Field label={titleLabel} htmlFor={`${id}-title`}><Input id={`${id}-title`} value={c.title ?? ""} onChange={(e) => set("title", e.target.value)} /></Field>
          <Field label={orgLabel} htmlFor={`${id}-org`}><Input id={`${id}-org`} value={c.organization ?? ""} onChange={(e) => set("organization", e.target.value)} /></Field>
        </div>
        <div className="pt-6">{controls}</div>
      </div>
      <div className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr]">
        <Field label="Start" htmlFor={`${id}-start`}><Input id={`${id}-start`} value={c.start ?? ""} placeholder="e.g. Jan 2022" onChange={(e) => set("start", e.target.value)} /></Field>
        <Field label="End" htmlFor={`${id}-end`}>
          <Input id={`${id}-end`} value={c.current ? "" : c.end ?? ""} placeholder={c.current ? "Present" : "e.g. Mar 2024"} disabled={!!c.current} onChange={(e) => set("end", e.target.value)} />
        </Field>
        <Field label="Location" htmlFor={`${id}-loc`}><Input id={`${id}-loc`} value={c.location ?? ""} onChange={(e) => set("location", e.target.value)} /></Field>
      </div>
      <label className="flex w-fit items-center gap-2 text-sm">
        <input type="checkbox" className="size-4 accent-primary" checked={!!c.current} onChange={(e) => set("current", e.target.checked)} />
        I currently {type === "education" ? "study" : "work"} here
      </label>
    </div>
  );
}

function BulletsEditor({ id, bullets, onChange }: { id: string; bullets: Bullet[]; onChange: (b: Bullet[]) => void }) {
  const set = (ui: number, patch: Partial<Bullet>) => onChange(bullets.map((u, i) => (i === ui ? { ...u, ...patch } : u)));
  return (
    <div className="mt-2 space-y-1.5">
      <div className="text-xs font-medium text-muted-foreground">Bullets</div>
      {bullets.map((u, ui) => {
        const bid = `${id}-b${u._k ?? ui}`;
        const fromProfile = u.source === "profile";
        return (
          <div key={u._k ?? ui} className={cn("rounded-md border p-1.5", !u.approved && "border-dashed bg-muted/40")}>
            <label htmlFor={bid} className="sr-only">Bullet {ui + 1}</label>
            <Textarea id={bid} rows={2} value={u.text} className="min-h-0 resize-y border-0 px-1.5 py-1 shadow-none focus-visible:ring-0"
                      onChange={(e) => set(ui, { text: e.target.value, source: fromProfile ? "user" : u.source })} />
            <div className="flex flex-wrap items-center gap-1.5 px-1 pt-1">
              {fromProfile
                ? <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">from profile</span>
                : <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
                        title={u.source === "suggestion" ? "Accepted suggestion" : "Written or edited here"}>not from your profile</span>}
              <label className="ml-1 flex items-center gap-1 text-xs text-muted-foreground">
                <input type="checkbox" className="size-3.5 accent-primary" checked={u.approved} onChange={(e) => set(ui, { approved: e.target.checked })} />
                Include
              </label>
              <div className="ml-auto flex items-center gap-0.5">
                <Button size="icon-xs" variant="ghost" aria-label={`Move bullet ${ui + 1} up`} disabled={ui === 0} onClick={() => onChange(move(bullets, ui, ui - 1))}><ArrowUp /></Button>
                <Button size="icon-xs" variant="ghost" aria-label={`Move bullet ${ui + 1} down`} disabled={ui === bullets.length - 1} onClick={() => onChange(move(bullets, ui, ui + 1))}><ArrowDown /></Button>
                <Button size="icon-xs" variant="ghost" aria-label={`Delete bullet ${ui + 1}`} onClick={() => onChange(bullets.filter((_, i) => i !== ui))}><Trash2 /></Button>
              </div>
            </div>
          </div>
        );
      })}
      <Button size="xs" variant="ghost" onClick={() => onChange([...bullets, { _k: newKey(), text: "", evidence_refs: [], source: "user", approved: true }])}>
        <Plus /> Add bullet
      </Button>
    </div>
  );
}
