import { useState } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/settings/primitives";
import { Switch } from "@/components/ui/switch";
import { Field, LoadingState, NativeSelect, TagInput } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCareerGoals, useConsents, useCountries, useSaveCareerGoals, useSetConsent } from "./hooks";
import type { CareerGoals, SearchMode, Seniority } from "./types";

const MODES: { value: SearchMode; label: string; hint: string }[] = [
  { value: "india", label: "India", hint: "Only jobs in India" },
  { value: "international", label: "International", hint: "Jobs in the countries you list below" },
  { value: "both", label: "Both", hint: "India and the countries below" },
];

const SENIORITY: { value: Seniority | ""; label: string }[] = [
  { value: "", label: "Not specified" }, { value: "intern", label: "Intern" }, { value: "entry", label: "Entry level" },
  { value: "junior", label: "Junior" }, { value: "mid", label: "Mid level" }, { value: "senior", label: "Senior" },
  { value: "lead", label: "Lead" }, { value: "manager", label: "Manager" }, { value: "director", label: "Director" },
];

const triOptions = [{ value: "", label: "Not specified" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }];
const toTri = (v: boolean | null) => (v == null ? "" : v ? "yes" : "no");
const fromTri = (v: string) => (v === "" ? null : v === "yes");

const isCode = (c: string) => /^[A-Z]{2}$/.test(c);

const EMPTY: CareerGoals = { search_mode: "india", target_countries: [], seniority: null, open_to_relocation: null, work_authorization: [], needs_sponsorship: null };

export function CareerGoalsForm() {
  const goals = useCareerGoals();
  if (goals.isLoading) return <LoadingState />;
  return <GoalsEditor initial={goals.data ?? EMPTY} />;
}

function GoalsEditor({ initial }: { initial: CareerGoals }) {
  const countries = useCountries();
  const save = useSaveCareerGoals();
  const [f, setF] = useState<CareerGoals>(initial);

  const codes = (v: string[]) => Array.from(new Set(v.map((c) => c.trim().toUpperCase()).filter(Boolean)));
  const badTargets = f.target_countries.filter((c) => !isCode(c));
  const badAuth = f.work_authorization.filter((c) => !isCode(c));
  const suggestions = (countries.data ?? []).map((c) => c.code);
  const names = new Map((countries.data ?? []).map((c) => [c.code, c.name]));
  const describe = (list: string[]) => list.filter(isCode).map((c) => names.get(c) ?? c).join(", ");
  const invalid = badTargets.length > 0 || badAuth.length > 0;

  return (
    <Panel title="Matching and eligibility"
           description="These decide which jobs you are matched with and whether you count as eligible (for example, whether you can legally work there). Saving re-scores your jobs.">
      <div className="space-y-6">
        <fieldset className="space-y-2.5">
          <legend className="mb-2.5 text-[13px] font-semibold text-heading">Where do you want to work?</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {MODES.map((m) => (
              <label key={m.value} className={cn("flex cursor-pointer items-start gap-2.5 rounded-xl p-3.5 text-sm ring-1 transition-[background-color,box-shadow] duration-200 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                f.search_mode === m.value ? "bg-route-tint/60 ring-2 ring-route/50" : "ring-border hover:ring-foreground/25")}>
                <input type="radio" name="search_mode" value={m.value} checked={f.search_mode === m.value} onChange={() => setF({ ...f, search_mode: m.value })} className="mt-0.5 accent-primary" />
                <span><span className="font-medium">{m.label}</span><span className="block text-xs text-muted-foreground">{m.hint}</span></span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid gap-x-5 gap-y-4 border-t pt-5 sm:grid-cols-2">
          <Field label="Countries you want to work in" htmlFor="cg-targets"
                 hint={badTargets.length ? <span className="text-destructive">Use two-letter country codes (e.g. GB, DE, AE). Not valid: {badTargets.join(", ")}</span>
                   : <>Two-letter country codes, e.g. GB for the United Kingdom, DE for Germany.{describe(f.target_countries) && ` Selected: ${describe(f.target_countries)}.`}</>}>
            <TagInput id="cg-targets" value={f.target_countries} onChange={(v) => setF({ ...f, target_countries: codes(v) })} placeholder="e.g. GB, DE" suggestions={suggestions} />
          </Field>
          <Field label="Countries where you can already work" htmlFor="cg-auth"
                 hint={badAuth.length ? <span className="text-destructive">Use two-letter country codes (e.g. IN). Not valid: {badAuth.join(", ")}</span>
                   : <>Where you're a citizen or already hold a work permit, e.g. IN for India.{describe(f.work_authorization) && ` Selected: ${describe(f.work_authorization)}.`}</>}>
            <TagInput id="cg-auth" value={f.work_authorization} onChange={(v) => setF({ ...f, work_authorization: codes(v) })} placeholder="e.g. IN" />
          </Field>
          <Field label="Level you're aiming for" htmlFor="cg-seniority">
            <NativeSelect id="cg-seniority" value={f.seniority ?? ""} onChange={(v) => setF({ ...f, seniority: (v || null) as Seniority | null })} options={SENIORITY} className="w-full" />
          </Field>
          <Field label="Open to relocating?" htmlFor="cg-reloc">
            <NativeSelect id="cg-reloc" value={toTri(f.open_to_relocation)} onChange={(v) => setF({ ...f, open_to_relocation: fromTri(v) })} options={triOptions} className="w-full" />
          </Field>
          <Field label="Will you need visa sponsorship?" htmlFor="cg-spons" hint="Used to check whether jobs abroad are realistic for you.">
            <NativeSelect id="cg-spons" value={toTri(f.needs_sponsorship)} onChange={(v) => setF({ ...f, needs_sponsorship: fromTri(v) })} options={triOptions} className="w-full" />
          </Field>
        </div>

        <Link to="/international" className="inline-block text-sm text-primary underline-offset-4 hover:underline">See visa routes for these countries</Link>
        <div data-save-bar className="flex items-center justify-end gap-3">
          <Button disabled={invalid || save.isPending}
                  onClick={() => save.mutate(f, { onSuccess: () => toast.success("Saved. Your jobs are being re-scored."), onError: (e) => toast.error(errorMessage(e)) })}>
            {save.isPending && <Loader2 className="animate-spin" />} Save career goals
          </Button>
        </div>
      </div>
    </Panel>
  );
}

const CONSENT_TITLES: Record<string, string> = {
  ai_processing: "AI suggestions",
  learning_tracking: "Learning time tracking",
  mentor_sharing: "Sharing with mentors",
  extension: "Browser extension",
  email_notifications: "E-mail reminders",
  research_feedback: "Short feedback questions",
};

export function PrivacyConsents() {
  const consents = useConsents();
  const set = useSetConsent();
  return (
    <Panel title="Your choices" description="Each of these is off until you turn it on, and you can turn any of them off again at any time.">
      <div className="space-y-4">
        {consents.isLoading ? <LoadingState /> : consents.isError ? <p className="text-sm text-destructive">{errorMessage(consents.error)}</p> : (
          <ul className="divide-y overflow-hidden rounded-xl ring-1 ring-border">
            {(consents.data ?? []).map((c) => (
              <li key={c.kind} className={cn("flex items-start justify-between gap-4 p-4 transition-colors duration-200", c.granted ? "bg-card" : "bg-paper-sunk/50")}>
                <div className="space-y-1">
                  <div className="text-sm font-semibold text-heading">{CONSENT_TITLES[c.kind] ?? c.kind.replaceAll("_", " ")}</div>
                  <p className="text-sm text-muted-foreground">{c.text}</p>
                  <p key={String(c.granted)} className="text-xs text-muted-foreground animate-in fade-in-0 duration-200">
                    {c.granted ? `On since ${formatDate(c.granted_at)}` : c.revoked_at ? `Turned off ${formatDate(c.revoked_at)}` : "Off"}
                  </p>
                </div>
                <Switch checked={c.granted} disabled={set.isPending && set.variables?.kind === c.kind} aria-label={CONSENT_TITLES[c.kind] ?? c.kind}
                        onCheckedChange={(on) => set.mutate({ kind: c.kind, granted: !!on }, {
                          onSuccess: () => toast.success(on ? "Turned on" : "Turned off"), onError: (e) => toast.error(errorMessage(e)),
                        })} />
              </li>
            ))}
          </ul>
        )}
        <p className="text-[13px] text-muted-foreground">
          To download a copy of everything JobPilot holds about you, or to delete your account, go to{" "}
          <Link to="/settings?tab=account" className="text-primary underline-offset-4 hover:underline">Account & connection</Link>.
        </p>
      </div>
    </Panel>
  );
}
