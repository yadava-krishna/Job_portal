import { useEffect, useRef, useState } from "react";
import { Bookmark, Loader2, Plus, Trash2, UploadCloud } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Field, NativeSelect, TagInput } from "@/components/app/common";
import { FieldGroup } from "@/components/settings/primitives";
import { errorMessage } from "@/lib/api";
import { bookmarkletHref } from "@/lib/clipper";
import { bytes, formatDate, lines } from "@/lib/format";
import { usePlatforms, useSavePlatforms, useSavePreferences, useSaveProfile, useUploadResume } from "@/services/queries";
import type { EditableProfile, PlatformInfo, Preferences, ProfileResponse } from "@/types/api";

// ---- Resume upload -------------------------------------------------------------------

export function ResumeUpload({ profile, onUploaded }: { profile?: ProfileResponse; onUploaded?: () => void }) {
  const upload = useUploadResume();
  const [drag, setDrag] = useState(false);
  const pick = (file?: File) => {
    if (!file) return;
    const okType = !file.type || file.type === "application/pdf" || file.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" || /\.(pdf|docx)$/i.test(file.name);
    if (!okType) return toast.error("Please choose a PDF or Word (.docx) file.");
    if (file.size > 5 * 1024 * 1024) return toast.error("The resume must be 5 MB or smaller.");
    upload.mutate(file, {
      onSuccess: () => { toast.success("Resume uploaded and read. Give what we pulled out a quick vibe check."); onUploaded?.(); },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };
  return (
    <div className="space-y-3">
      <label onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
             onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
             className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors duration-150 focus-within:outline-2 focus-within:outline-ring ${drag ? "border-primary bg-primary/5" : "hover:border-route/40 hover:bg-route-tint/40"}`}>
        {upload.isPending ? <Loader2 className="size-8 animate-spin text-primary" /> : <UploadCloud className="size-8 text-muted-foreground" />}
        <span className="font-medium">{upload.isPending ? "Uploading and parsing your resume…" : "Drop your resume PDF here or click to browse"}</span>
        <span className="text-xs text-muted-foreground">PDF or Word (.docx) · up to 5 MB · stored privately for your account</span>
        <input type="file" accept="application/pdf,.pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="sr-only" disabled={upload.isPending} onChange={(e) => pick(e.target.files?.[0])} />
      </label>
      {profile?.resume && (
        <p className="text-sm text-muted-foreground">
          Current: <span className="font-medium text-foreground">{profile.resume.original_filename}</span> · {profile.resume.page_count} page(s) · {bytes(profile.resume.size_bytes)} · uploaded {formatDate(profile.resume.uploaded_at, true)}
        </p>
      )}
    </div>
  );
}

// ---- Editable profile ------------------------------------------------------------------

export const EMPTY_PROFILE: EditableProfile = {
  full_name: null, email: null, phone: null, location: null, headline: null, summary: null, skills: [], experience: [],
  education: [], certifications: [], projects: [], achievements: [], languages: [],
};

/** `manual`: no resume yet (students / early career): start from an empty profile the candidate fills in. */
export function ProfileForm({ profile, onSaved, submitLabel = "Save profile", manual = false }: { profile: ProfileResponse; onSaved?: () => void; submitLabel?: string; manual?: boolean }) {
  const save = useSaveProfile();
  const [p, setP] = useState<EditableProfile | null>(null);
  useEffect(() => {
    const start = profile.confirmed ?? profile.parsed ?? (manual ? EMPTY_PROFILE : null);
    setP(start ? structuredClone(start) : null);
  }, [profile.confirmed, profile.parsed, manual]);
  if (!p) return <p className="text-sm text-muted-foreground">Upload a resume first.</p>;
  const set = <K extends keyof EditableProfile>(k: K, v: EditableProfile[K]) => setP({ ...p, [k]: v });

  return (
    <div className="space-y-6">
      {profile.parse_warnings.length > 0 && (
        <div className="rounded-xl bg-caution-tint p-3 text-sm text-foreground ring-1 ring-caution/25">
          <strong className="text-caution">Please check:</strong>
          <ul className="mt-1 list-disc pl-5">{profile.parse_warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Full name" htmlFor="pf-name"><Input id="pf-name" value={p.full_name ?? ""} onChange={(e) => set("full_name", e.target.value)} /></Field>
        <Field label="Email" htmlFor="pf-email"><Input id="pf-email" value={p.email ?? ""} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Phone" htmlFor="pf-phone"><Input id="pf-phone" value={p.phone ?? ""} onChange={(e) => set("phone", e.target.value)} /></Field>
        <Field label="Location" htmlFor="pf-loc"><Input id="pf-loc" value={p.location ?? ""} onChange={(e) => set("location", e.target.value)} /></Field>
        <Field label="Headline" htmlFor="pf-head" className="sm:col-span-2"><Input id="pf-head" value={p.headline ?? ""} onChange={(e) => set("headline", e.target.value)} /></Field>
        <Field label="Professional summary" htmlFor="pf-sum" className="sm:col-span-2"><Textarea id="pf-sum" rows={4} value={p.summary ?? ""} onChange={(e) => set("summary", e.target.value)} /></Field>
      </div>

      <div>
        <h3 className="mb-1 text-[13px] font-semibold text-heading">Links (optional)</h3>
        <p className="mb-3 text-xs text-muted-foreground">Application forms often ask for these. They are filled only when you click Fill in the Smart Apply extension.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="LinkedIn URL" htmlFor="pf-li"><Input id="pf-li" inputMode="url" value={p.linkedin_url ?? ""} placeholder="https://www.linkedin.com/in/…" onChange={(e) => set("linkedin_url", e.target.value || null)} /></Field>
          <Field label="GitHub URL" htmlFor="pf-gh"><Input id="pf-gh" inputMode="url" value={p.github_url ?? ""} placeholder="https://github.com/…" onChange={(e) => set("github_url", e.target.value || null)} /></Field>
          <Field label="Portfolio URL" htmlFor="pf-pf"><Input id="pf-pf" inputMode="url" value={p.portfolio_url ?? ""} onChange={(e) => set("portfolio_url", e.target.value || null)} /></Field>
          <Field label="Personal website" htmlFor="pf-web"><Input id="pf-web" inputMode="url" value={p.website_url ?? ""} onChange={(e) => set("website_url", e.target.value || null)} /></Field>
        </div>
      </div>

      <Field label="Skills" hint="Only skills you actually have. These drive the match score.">
        <TagInput value={p.skills} onChange={(v) => set("skills", v)} placeholder="Add a skill and press Enter" />
      </Field>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-heading">Experience</h3>
          <Button size="sm" variant="outline" onClick={() => set("experience", [...p.experience, { title: "", company: "", start: null, end: null, is_current: false, bullets: [] }])}><Plus /> Add role</Button>
        </div>
        {profile.experience && <p className="text-sm text-muted-foreground">Total experience from dates: <strong>{profile.experience.years_months}</strong> (overlapping roles counted once).</p>}
        {p.experience.map((r, i) => (
          <div key={i} className="space-y-3 rounded-xl bg-paper-sunk/70 p-4 ring-1 ring-border/70">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Job title"><Input value={r.title} onChange={(e) => set("experience", p.experience.map((x, j) => j === i ? { ...x, title: e.target.value } : x))} /></Field>
              <Field label="Company"><Input value={r.company} onChange={(e) => set("experience", p.experience.map((x, j) => j === i ? { ...x, company: e.target.value } : x))} /></Field>
              <Field label="Start (month)"><Input type="month" value={r.start ?? ""} onChange={(e) => set("experience", p.experience.map((x, j) => j === i ? { ...x, start: e.target.value || null } : x))} /></Field>
              <Field label="End (month)">
                <div className="flex items-center gap-3">
                  <Input type="month" value={r.end ?? ""} disabled={r.is_current} onChange={(e) => set("experience", p.experience.map((x, j) => j === i ? { ...x, end: e.target.value || null } : x))} />
                  <label className="flex shrink-0 items-center gap-2 text-sm"><Checkbox checked={r.is_current} onCheckedChange={(c) => set("experience", p.experience.map((x, j) => j === i ? { ...x, is_current: !!c, end: c ? null : x.end } : x))} /> Current</label>
                </div>
              </Field>
            </div>
            <Field label="Responsibilities and achievements (one per line)">
              <Textarea rows={4} value={r.bullets.join("\n")} onChange={(e) => set("experience", p.experience.map((x, j) => j === i ? { ...x, bullets: e.target.value.split("\n") } : x))} />
            </Field>
            <div><Button size="sm" variant="ghost" onClick={() => set("experience", p.experience.filter((_, j) => j !== i))}><Trash2 /> Remove role</Button></div>
          </div>
        ))}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-heading">Education</h3>
          <Button size="sm" variant="outline" onClick={() => set("education", [...p.education, { degree: "", institution: "", university: "", year: null }])}><Plus /> Add</Button>
        </div>
        {p.education.map((e, i) => (
          <div key={i} className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 rounded-xl bg-paper-sunk/70 p-2 ring-1 ring-border/70 sm:grid-cols-[2fr_2fr_2fr_1fr_auto] sm:bg-transparent sm:p-0 sm:ring-0 [&>input]:col-start-1 sm:[&>input]:col-start-auto [&>button]:col-start-2 [&>button]:row-start-1 sm:[&>button]:col-start-auto">
            <Input aria-label="Degree" placeholder="Degree" value={e.degree ?? ""} onChange={(ev) => set("education", p.education.map((x, j) => j === i ? { ...x, degree: ev.target.value } : x))} />
            <Input aria-label="Institution" placeholder="Institution" value={e.institution ?? ""} onChange={(ev) => set("education", p.education.map((x, j) => j === i ? { ...x, institution: ev.target.value } : x))} />
            <Input aria-label="University" placeholder="University" value={e.university ?? ""} onChange={(ev) => set("education", p.education.map((x, j) => j === i ? { ...x, university: ev.target.value } : x))} />
            <Input aria-label="Year" placeholder="Year" inputMode="numeric" value={e.year ?? ""} onChange={(ev) => set("education", p.education.map((x, j) => j === i ? { ...x, year: ev.target.value ? Number(ev.target.value) || null : null } : x))} />
            <Button size="icon-sm" variant="ghost" aria-label="Remove education" onClick={() => set("education", p.education.filter((_, j) => j !== i))}><Trash2 /></Button>
          </div>
        ))}
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Certifications / training"><TagInput value={p.certifications} onChange={(v) => set("certifications", v)} /></Field>
        <Field label="Languages"><TagInput value={p.languages} onChange={(v) => set("languages", v)} /></Field>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[13px] font-semibold text-heading">Projects</h3>
          <Button size="sm" variant="outline" onClick={() => set("projects", [...p.projects, { name: "", bullets: [] }])}><Plus /> Add</Button>
        </div>
        {p.projects.map((pr, i) => (
          <div key={i} className="space-y-2 rounded-xl bg-paper-sunk/70 p-4 ring-1 ring-border/70">
            <Input aria-label="Project name" placeholder="Project name" value={pr.name} onChange={(e) => set("projects", p.projects.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
            <Textarea rows={3} aria-label="Project details" placeholder="Details (one per line)" value={pr.bullets.join("\n")} onChange={(e) => set("projects", p.projects.map((x, j) => j === i ? { ...x, bullets: e.target.value.split("\n") } : x))} />
            <div><Button size="sm" variant="ghost" onClick={() => set("projects", p.projects.filter((_, j) => j !== i))}><Trash2 /> Remove</Button></div>
          </div>
        ))}
      </section>

      <Field label="Measurable achievements (one per line)">
        <Textarea rows={4} value={p.achievements.join("\n")} onChange={(e) => set("achievements", e.target.value.split("\n"))} />
      </Field>

      <div data-save-bar className="flex justify-end">
        <Button onClick={() => {
          // Drop blank lines that the multi-line editors keep while typing.
          const clean = { ...p, achievements: lines(p.achievements.join("\n")),
            experience: p.experience.map((r) => ({ ...r, bullets: lines(r.bullets.join("\n")) })),
            projects: p.projects.filter((x) => x.name.trim()).map((x) => ({ ...x, bullets: lines(x.bullets.join("\n")) })) };
          setP(clean);
          save.mutate(clean, { onSuccess: () => { toast.success("Profile saved. Main-character energy."); onSaved?.(); }, onError: (e) => toast.error(errorMessage(e)) });
        }} disabled={save.isPending}>
          {save.isPending && <Loader2 className="animate-spin" />} {submitLabel}
        </Button>
      </div>
    </div>
  );
}

// ---- Preferences -----------------------------------------------------------------------

export const defaultPreferences: Preferences = {
  domains: [], industries: [], job_titles: [], title_keywords: [], locations: [], work_modes: ["Remote", "Hybrid", "On-site"],
  salary_min: null, salary_max: null, currency: "INR", experience_min: null, experience_max: null, employment_types: ["Full-time"],
  notice_period: null, preferred_companies: [], excluded_companies: [], min_match_score: 70,
  weights: { core_skills: 35, experience: 25, responsibilities: 20, education: 10, location: 10 },
  application_settings: { approval_required: true, cover_letter: "when_required", max_prepared_per_day: 25 },
};

const DOMAINS = ["Finance", "Accounting", "Healthcare Operations", "Revenue Cycle Management", "Banking", "Insurance", "Operations", "Analytics"];
const LOCATIONS = ["Bengaluru", "Remote - India", "Hyderabad", "Chennai", "Pune", "Mumbai", "Delhi NCR"];

export function PreferencesForm({ initial, suggestedTitles = [], onSaved, submitLabel = "Save preferences" }: {
  initial?: Preferences; suggestedTitles?: string[]; onSaved?: () => void; submitLabel?: string;
}) {
  const save = useSavePreferences();
  const [p, setP] = useState<Preferences>(defaultPreferences);
  useEffect(() => { if (initial) setP({ ...defaultPreferences, ...initial, weights: { ...defaultPreferences.weights, ...initial.weights }, application_settings: { ...defaultPreferences.application_settings, ...initial.application_settings } }); }, [initial]);
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => setP((x) => ({ ...x, [k]: v }));
  const toggle = <T extends string>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);
  const num = (v: string) => (v === "" ? null : Number(v));
  const weightTotal = Object.values(p.weights).reduce((a, b) => a + Number(b || 0), 0);

  return (
    <div className="space-y-6">
      <FieldGroup title="Roles you want">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Preferred job titles"><TagInput value={p.job_titles} onChange={(v) => set("job_titles", v)} suggestions={suggestedTitles} placeholder="e.g. Financial Analyst" /></Field>
          <Field label="Additional title keywords"><TagInput value={p.title_keywords} onChange={(v) => set("title_keywords", v)} placeholder="e.g. FP&A, MIS" /></Field>
          <Field label="Target domains" hint="Select several if you are open to more than one."><TagInput value={p.domains} onChange={(v) => set("domains", v)} suggestions={DOMAINS} placeholder="e.g. Finance" /></Field>
          <Field label="Target industries"><TagInput value={p.industries} onChange={(v) => set("industries", v)} suggestions={["Healthcare", "BFSI", "IT Services", "Consulting", "E-commerce"]} /></Field>
        </div>
      </FieldGroup>

      <FieldGroup title="Where and how">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Preferred locations" className="md:col-span-2"><TagInput value={p.locations} onChange={(v) => set("locations", v)} suggestions={LOCATIONS} /></Field>
          <Field label="Work mode">
            <div className="flex flex-wrap gap-x-4 gap-y-2 pt-1">
              {(["Remote", "Hybrid", "On-site"] as const).map((m) => (
                <label key={m} className="flex items-center gap-2 text-sm"><Checkbox checked={p.work_modes.includes(m)} onCheckedChange={() => set("work_modes", toggle(p.work_modes, m))} /> {m}</label>
              ))}
            </div>
          </Field>
          <Field label="Employment type">
            <div className="flex flex-wrap gap-x-4 gap-y-2 pt-1">
              {(["Full-time", "Contract", "Part-time", "Internship"] as const).map((m) => (
                <label key={m} className="flex items-center gap-2 text-sm"><Checkbox checked={p.employment_types.includes(m)} onCheckedChange={() => set("employment_types", toggle(p.employment_types, m))} /> {m}</label>
              ))}
            </div>
          </Field>
        </div>
      </FieldGroup>

      <FieldGroup title="Pay and experience">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Expected salary (annual)" className="md:col-span-2">
            <div className="flex max-w-xl gap-2">
              <NativeSelect ariaLabel="Currency" value={p.currency} onChange={(v) => set("currency", v)} options={["INR", "USD", "EUR", "GBP", "AED", "SGD"].map((c) => ({ value: c, label: c }))} className="shrink-0" />
              <Input type="number" min={0} placeholder="Minimum" className="readout" value={p.salary_min ?? ""} onChange={(e) => set("salary_min", num(e.target.value))} aria-label="Minimum salary" />
              <Input type="number" min={0} placeholder="Maximum" className="readout" value={p.salary_max ?? ""} onChange={(e) => set("salary_max", num(e.target.value))} aria-label="Maximum salary" />
            </div>
          </Field>
          <Field label="Experience range (years)">
            <div className="flex max-w-xs items-center gap-2">
              <Input type="number" min={0} step={0.5} placeholder="Min" className="readout" value={p.experience_min ?? ""} onChange={(e) => set("experience_min", num(e.target.value))} aria-label="Minimum experience" />
              <span aria-hidden className="text-muted-foreground">–</span>
              <Input type="number" min={0} step={0.5} placeholder="Max" className="readout" value={p.experience_max ?? ""} onChange={(e) => set("experience_max", num(e.target.value))} aria-label="Maximum experience" />
            </div>
          </Field>
          <Field label="Notice period (optional)" hint="Only if you want to share it."><Input className="max-w-xs" value={p.notice_period ?? ""} onChange={(e) => set("notice_period", e.target.value || null)} placeholder="e.g. 30 days" /></Field>
        </div>
      </FieldGroup>

      <FieldGroup title="Companies">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Preferred companies"><TagInput value={p.preferred_companies} onChange={(v) => set("preferred_companies", v)} /></Field>
          <Field label="Excluded companies" hint="Jobs from these companies are marked not eligible."><TagInput value={p.excluded_companies} onChange={(v) => set("excluded_companies", v)} /></Field>
        </div>
      </FieldGroup>

      <FieldGroup title="Matching">
        <Field label={`Minimum match to shortlist: ${p.min_match_score}%`}>
          <input type="range" min={0} max={100} step={5} value={p.min_match_score} onChange={(e) => set("min_match_score", Number(e.target.value))} className="w-full max-w-md accent-primary" aria-label="Minimum match percentage" />
        </Field>

        <details className="group rounded-xl bg-paper-sunk/60 p-4 ring-1 ring-border/70">
          <summary className="cursor-pointer rounded text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring">Scoring weights & application settings</summary>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
            {(Object.keys(p.weights) as (keyof Preferences["weights"])[]).map((k) => (
              <Field key={k} label={k.replace("_", " ")} className="[&>label]:capitalize"><Input type="number" min={0} max={100} className="readout" value={p.weights[k]} onChange={(e) => set("weights", { ...p.weights, [k]: Number(e.target.value) })} /></Field>
            ))}
          </div>
          <p className={`mt-2 text-xs ${weightTotal === 100 ? "text-muted-foreground" : "text-caution"}`}>Total {weightTotal}%. Weights are normalised, but 100 keeps them easy to read.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="Cover letters">
              <NativeSelect value={p.application_settings.cover_letter} onChange={(v) => set("application_settings", { ...p.application_settings, cover_letter: v as Preferences["application_settings"]["cover_letter"] })}
                            options={[{ value: "when_required", label: "Only when the job asks for one" }, { value: "always", label: "Always prepare one" }, { value: "never", label: "Never" }]} className="w-full" />
            </Field>
          </div>
        </details>
      </FieldGroup>

      <div data-save-bar className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
        {!p.job_titles.length && <p className="text-xs text-muted-foreground">Add at least one job title.</p>}
        <Button onClick={() => save.mutate(p, { onSuccess: () => { toast.success("Preferences saved. Your feed just got a vibe check."); onSaved?.(); }, onError: (e) => toast.error(errorMessage(e)) })}
                disabled={save.isPending || !p.job_titles.length}>
          {save.isPending && <Loader2 className="animate-spin" />} {submitLabel}
        </Button>
      </div>
    </div>
  );
}

// ---- Platforms --------------------------------------------------------------------------

export function PlatformsForm({ onSaved, submitLabel = "Save platforms" }: { onSaved?: () => void; submitLabel?: string }) {
  const { data } = usePlatforms();
  const save = useSavePlatforms();
  const [rows, setRows] = useState<PlatformInfo[]>([]);
  useEffect(() => {
    if (data) setRows(data.map((p) => ({ ...p, discovery_sources: p.discovery_sources.length ? p.discovery_sources : p.platform === "Adzuna" ? ["adzuna_api"] : ["browser_clipper", "user_job_url"] })));
  }, [data]);
  if (!data) return <Loader2 className="animate-spin" />;
  const update = (i: number, patch: Partial<PlatformInfo>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  return (
    <div className="space-y-4">
      <ul className="divide-y overflow-hidden rounded-xl ring-1 ring-border">
        {rows.map((r, i) => {
          const unavailable = r.platform === "Adzuna" && r.available_sources.length === 0;
          return (
            <li key={r.platform} className={`flex items-start gap-4 p-4 transition-colors duration-200 ${r.enabled && !unavailable ? "bg-card" : "bg-paper-sunk/60"} ${unavailable ? "opacity-60" : ""}`}>
              <div className="min-w-0 flex-1 space-y-2.5">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-display text-[15px] font-bold tracking-[-0.01em] text-heading">{r.platform}</span>
                    {r.automated_search && <span className="rounded-full bg-route-tint px-2 py-px text-[11px] font-medium text-route">Official API</span>}
                  </div>
                  <p className="mt-0.5 text-[13px] text-muted-foreground">{r.notes}</p>
                </div>
                {r.available_sources.length > 0 && (
                  <div>
                    <p className="eyebrow mb-1.5 text-[10px]">Discovery sources</p>
                    <div className="flex flex-col gap-1.5 sm:flex-row sm:flex-wrap sm:gap-x-5">
                      {r.available_sources.map((s) => (
                        <label key={s.id} className={`flex items-start gap-2 text-sm ${r.enabled ? "" : "text-muted-foreground"}`}>
                          <Checkbox className="mt-0.5" disabled={!r.enabled} checked={r.discovery_sources.includes(s.id)}
                                    onCheckedChange={() => update(i, { discovery_sources: r.discovery_sources.includes(s.id) ? r.discovery_sources.filter((x) => x !== s.id) : [...r.discovery_sources, s.id] })} />
                          {s.label}
                        </label>
                      ))}
                    </div>
                  </div>
                )}
                <p className="text-xs text-muted-foreground">Apply: {r.application_method}. Automated search: {r.automated_search ? "yes (official API)" : "no"} · automated apply: no.</p>
              </div>
              <Switch className="mt-1" checked={r.enabled} disabled={unavailable} onCheckedChange={(c) => update(i, { enabled: !!c })} aria-label={`Enable ${r.platform}`} />
            </li>
          );
        })}
      </ul>
      <div data-save-bar className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1">
        {!rows.some((r) => r.enabled) && <p className="text-xs text-muted-foreground">Switch on at least one platform.</p>}
        <Button onClick={() => save.mutate(rows.filter((r) => !(r.platform === "Adzuna" && r.available_sources.length === 0)).map((r) => ({ platform: r.platform, enabled: r.enabled, discovery_sources: r.discovery_sources })), {
          onSuccess: () => { toast.success("Platforms saved. Say less."); onSaved?.(); }, onError: (e) => toast.error(errorMessage(e)),
        })} disabled={save.isPending || !rows.some((r) => r.enabled)}>
          {save.isPending && <Loader2 className="animate-spin" />} {submitLabel}
        </Button>
      </div>
    </div>
  );
}

// ---- Browser clipper ---------------------------------------------------------------------

export function ClipperCard() {
  const ref = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    // React blocks javascript: URLs in JSX, so the bookmarklet href is set directly.
    ref.current?.setAttribute("href", bookmarkletHref());
  }, []);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 font-display text-[15.5px] font-bold tracking-[-0.015em] text-heading"><Bookmark className="size-4 text-route" /> Browser job clipper</CardTitle>
        <CardDescription>
          Capture full job details from LinkedIn, Indeed or Naukri pages you are viewing in your own (logged-in) browser.
          It reads only the page you clicked it on, after you click it; nothing runs in the background, and no cookies or passwords leave your browser.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ol className="list-decimal space-y-1.5 pl-5 marker:font-semibold marker:text-route">
          <li>Show your browser's bookmarks bar (Ctrl+Shift+B).</li>
          <li>Drag this button onto the bookmarks bar: <a ref={ref} onClick={(e) => { e.preventDefault(); toast("Drag it to your bookmarks bar, then click it on a job page."); }}
              className="ml-1 inline-flex cursor-grab items-center gap-1 rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground shadow-[var(--shadow-raised)] transition-transform duration-150 hover:-translate-y-px active:cursor-grabbing">＋ Clip to JobPilot</a></li>
          <li>Open a job on LinkedIn, Indeed or Naukri and click the bookmark. JobPilot opens with the details filled in for you to review and save.</li>
        </ol>
        <p className="text-xs text-muted-foreground">Tip: if a page layout changes, select the job description text before clicking the bookmark and it will be used.</p>
      </CardContent>
    </Card>
  );
}
