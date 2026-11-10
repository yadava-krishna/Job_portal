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
    if (file.type && file.type !== "application/pdf") return toast.error("Please choose a PDF file.");
    if (file.size > 5 * 1024 * 1024) return toast.error("The resume must be 5 MB or smaller.");
    upload.mutate(file, {
      onSuccess: () => { toast.success("Resume uploaded and parsed"); onUploaded?.(); },
      onError: (e) => toast.error(errorMessage(e)),
    });
  };
  return (
    <div className="space-y-3">
      <label onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
             onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
             className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-10 text-center transition-colors ${drag ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}>
        {upload.isPending ? <Loader2 className="size-8 animate-spin text-primary" /> : <UploadCloud className="size-8 text-muted-foreground" />}
        <span className="font-medium">{upload.isPending ? "Uploading and parsing your resume…" : "Drop your resume PDF here or click to browse"}</span>
        <span className="text-xs text-muted-foreground">PDF only · up to 5 MB · stored privately for your account</span>
        <input type="file" accept="application/pdf,.pdf" className="sr-only" disabled={upload.isPending} onChange={(e) => pick(e.target.files?.[0])} />
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
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100">
          <strong>Please check:</strong>
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
        <h3 className="mb-1 text-sm font-semibold">Links (optional)</h3>
        <p className="mb-3 text-xs text-muted-foreground">Application forms often ask for these. They are filled only when you click Fill with JobPilot.</p>
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
          <h3 className="font-medium">Experience</h3>
          <Button size="sm" variant="outline" onClick={() => set("experience", [...p.experience, { title: "", company: "", start: null, end: null, is_current: false, bullets: [] }])}><Plus /> Add role</Button>
        </div>
        {profile.experience && <p className="text-sm text-muted-foreground">Total experience from dates: <strong>{profile.experience.years_months}</strong> (overlapping roles counted once).</p>}
        {p.experience.map((r, i) => (
          <Card key={i} className="gap-3 p-4">
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
          </Card>
        ))}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-medium">Education</h3>
          <Button size="sm" variant="outline" onClick={() => set("education", [...p.education, { degree: "", institution: "", university: "", year: null }])}><Plus /> Add</Button>
        </div>
        {p.education.map((e, i) => (
          <div key={i} className="grid gap-2 sm:grid-cols-[2fr_2fr_2fr_1fr_auto]">
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
          <h3 className="font-medium">Projects</h3>
          <Button size="sm" variant="outline" onClick={() => set("projects", [...p.projects, { name: "", bullets: [] }])}><Plus /> Add</Button>
        </div>
        {p.projects.map((pr, i) => (
          <Card key={i} className="gap-2 p-4">
            <Input aria-label="Project name" placeholder="Project name" value={pr.name} onChange={(e) => set("projects", p.projects.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
            <Textarea rows={3} aria-label="Project details" placeholder="Details (one per line)" value={pr.bullets.join("\n")} onChange={(e) => set("projects", p.projects.map((x, j) => j === i ? { ...x, bullets: e.target.value.split("\n") } : x))} />
            <div><Button size="sm" variant="ghost" onClick={() => set("projects", p.projects.filter((_, j) => j !== i))}><Trash2 /> Remove</Button></div>
          </Card>
        ))}
      </section>

      <Field label="Measurable achievements (one per line)">
        <Textarea rows={4} value={p.achievements.join("\n")} onChange={(e) => set("achievements", e.target.value.split("\n"))} />
      </Field>

      <div className="flex justify-end">
        <Button onClick={() => {
          // Drop blank lines that the multi-line editors keep while typing.
          const clean = { ...p, achievements: lines(p.achievements.join("\n")),
            experience: p.experience.map((r) => ({ ...r, bullets: lines(r.bullets.join("\n")) })),
            projects: p.projects.filter((x) => x.name.trim()).map((x) => ({ ...x, bullets: lines(x.bullets.join("\n")) })) };
          setP(clean);
          save.mutate(clean, { onSuccess: () => { toast.success("Profile saved"); onSaved?.(); }, onError: (e) => toast.error(errorMessage(e)) });
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
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Target domains" hint="Select several if you are open to more than one."><TagInput value={p.domains} onChange={(v) => set("domains", v)} suggestions={DOMAINS} placeholder="e.g. Finance" /></Field>
        <Field label="Target industries"><TagInput value={p.industries} onChange={(v) => set("industries", v)} suggestions={["Healthcare", "BFSI", "IT Services", "Consulting", "E-commerce"]} /></Field>
        <Field label="Preferred job titles"><TagInput value={p.job_titles} onChange={(v) => set("job_titles", v)} suggestions={suggestedTitles} placeholder="e.g. Financial Analyst" /></Field>
        <Field label="Additional title keywords"><TagInput value={p.title_keywords} onChange={(v) => set("title_keywords", v)} placeholder="e.g. FP&A, MIS" /></Field>
        <Field label="Preferred locations"><TagInput value={p.locations} onChange={(v) => set("locations", v)} suggestions={LOCATIONS} /></Field>
        <Field label="Work mode">
          <div className="flex flex-wrap gap-4 pt-1">
            {(["Remote", "Hybrid", "On-site"] as const).map((m) => (
              <label key={m} className="flex items-center gap-2 text-sm"><Checkbox checked={p.work_modes.includes(m)} onCheckedChange={() => set("work_modes", toggle(p.work_modes, m))} /> {m}</label>
            ))}
          </div>
        </Field>
        <Field label="Expected salary (annual)">
          <div className="flex gap-2">
            <NativeSelect ariaLabel="Currency" value={p.currency} onChange={(v) => set("currency", v)} options={["INR", "USD", "EUR", "GBP", "AED", "SGD"].map((c) => ({ value: c, label: c }))} />
            <Input type="number" min={0} placeholder="Minimum" value={p.salary_min ?? ""} onChange={(e) => set("salary_min", num(e.target.value))} aria-label="Minimum salary" />
            <Input type="number" min={0} placeholder="Maximum" value={p.salary_max ?? ""} onChange={(e) => set("salary_max", num(e.target.value))} aria-label="Maximum salary" />
          </div>
        </Field>
        <Field label="Experience range (years)">
          <div className="flex gap-2">
            <Input type="number" min={0} step={0.5} placeholder="Min" value={p.experience_min ?? ""} onChange={(e) => set("experience_min", num(e.target.value))} aria-label="Minimum experience" />
            <Input type="number" min={0} step={0.5} placeholder="Max" value={p.experience_max ?? ""} onChange={(e) => set("experience_max", num(e.target.value))} aria-label="Maximum experience" />
          </div>
        </Field>
        <Field label="Employment type">
          <div className="flex flex-wrap gap-4 pt-1">
            {(["Full-time", "Contract", "Part-time", "Internship"] as const).map((m) => (
              <label key={m} className="flex items-center gap-2 text-sm"><Checkbox checked={p.employment_types.includes(m)} onCheckedChange={() => set("employment_types", toggle(p.employment_types, m))} /> {m}</label>
            ))}
          </div>
        </Field>
        <Field label="Notice period (optional)" hint="Only if you want to share it."><Input value={p.notice_period ?? ""} onChange={(e) => set("notice_period", e.target.value || null)} placeholder="e.g. 30 days" /></Field>
        <Field label="Preferred companies"><TagInput value={p.preferred_companies} onChange={(v) => set("preferred_companies", v)} /></Field>
        <Field label="Excluded companies" hint="Jobs from these companies are marked not eligible."><TagInput value={p.excluded_companies} onChange={(v) => set("excluded_companies", v)} /></Field>
      </div>

      <Field label={`Minimum match to shortlist: ${p.min_match_score}%`}>
        <input type="range" min={0} max={100} step={5} value={p.min_match_score} onChange={(e) => set("min_match_score", Number(e.target.value))} className="w-full accent-primary" aria-label="Minimum match percentage" />
      </Field>

      <details className="rounded-lg border p-4">
        <summary className="cursor-pointer text-sm font-medium">Scoring weights & application settings</summary>
        <div className="mt-4 grid gap-3 sm:grid-cols-5">
          {(Object.keys(p.weights) as (keyof Preferences["weights"])[]).map((k) => (
            <Field key={k} label={k.replace("_", " ")}><Input type="number" min={0} max={100} value={p.weights[k]} onChange={(e) => set("weights", { ...p.weights, [k]: Number(e.target.value) })} /></Field>
          ))}
        </div>
        <p className={`mt-2 text-xs ${weightTotal === 100 ? "text-muted-foreground" : "text-amber-600"}`}>Total {weightTotal}%. Weights are normalised, but 100 keeps them easy to read.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Cover letters">
            <NativeSelect value={p.application_settings.cover_letter} onChange={(v) => set("application_settings", { ...p.application_settings, cover_letter: v as Preferences["application_settings"]["cover_letter"] })}
                          options={[{ value: "when_required", label: "Only when the job asks for one" }, { value: "always", label: "Always prepare one" }, { value: "never", label: "Never" }]} className="w-full" />
          </Field>
        </div>
      </details>

      <div className="flex justify-end">
        <Button onClick={() => save.mutate(p, { onSuccess: () => { toast.success("Preferences saved"); onSaved?.(); }, onError: (e) => toast.error(errorMessage(e)) })}
                disabled={save.isPending || !p.job_titles.length}>
          {save.isPending && <Loader2 className="animate-spin" />} {submitLabel}
        </Button>
      </div>
      {!p.job_titles.length && <p className="text-right text-xs text-muted-foreground">Add at least one job title.</p>}
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
      <div className="grid gap-4 md:grid-cols-2">
        {rows.map((r, i) => {
          const unavailable = r.platform === "Adzuna" && r.available_sources.length === 0;
          return (
            <Card key={r.platform} className={unavailable ? "opacity-60" : ""}>
              <CardHeader className="flex-row items-start justify-between gap-3">
                <div>
                  <CardTitle>{r.platform}</CardTitle>
                  <CardDescription className="mt-1">{r.notes}</CardDescription>
                </div>
                <Switch checked={r.enabled} disabled={unavailable} onCheckedChange={(c) => update(i, { enabled: !!c })} aria-label={`Enable ${r.platform}`} />
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Discovery sources</p>
                {r.available_sources.map((s) => (
                  <label key={s.id} className="flex items-start gap-2 text-sm">
                    <Checkbox className="mt-0.5" disabled={!r.enabled} checked={r.discovery_sources.includes(s.id)}
                              onCheckedChange={() => update(i, { discovery_sources: r.discovery_sources.includes(s.id) ? r.discovery_sources.filter((x) => x !== s.id) : [...r.discovery_sources, s.id] })} />
                    {s.label}
                  </label>
                ))}
                <p className="pt-2 text-xs text-muted-foreground">Apply: {r.application_method}. Automated search: {r.automated_search ? "yes (official API)" : "no"} · automated apply: no.</p>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <div className="flex justify-end">
        <Button onClick={() => save.mutate(rows.filter((r) => !(r.platform === "Adzuna" && r.available_sources.length === 0)).map((r) => ({ platform: r.platform, enabled: r.enabled, discovery_sources: r.discovery_sources })), {
          onSuccess: () => { toast.success("Platforms saved"); onSaved?.(); }, onError: (e) => toast.error(errorMessage(e)),
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
        <CardTitle className="flex items-center gap-2"><Bookmark className="size-4" /> Browser job clipper</CardTitle>
        <CardDescription>
          Capture full job details from LinkedIn, Indeed or Naukri pages you are viewing in your own (logged-in) browser.
          It reads only the page you clicked it on, after you click it; nothing runs in the background, and no cookies or passwords leave your browser.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ol className="list-decimal space-y-1 pl-5">
          <li>Show your browser's bookmarks bar (Ctrl+Shift+B).</li>
          <li>Drag this button onto the bookmarks bar: <a ref={ref} onClick={(e) => { e.preventDefault(); toast("Drag it to your bookmarks bar, then click it on a job page."); }}
              className="ml-1 inline-flex cursor-grab items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground">＋ Clip to JobPilot</a></li>
          <li>Open a job on LinkedIn, Indeed or Naukri and click the bookmark. JobPilot opens with the details filled in for you to review and save.</li>
        </ol>
        <p className="text-xs text-muted-foreground">Tip: if a page layout changes, select the job description text before clicking the bookmark and it will be used.</p>
      </CardContent>
    </Card>
  );
}
