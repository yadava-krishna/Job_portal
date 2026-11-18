import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, BadgeCheck, Building2, CalendarCheck, CheckCircle2, CircleAlert, CircleHelp, ExternalLink, Globe2, Lightbulb, Loader2, Settings2, UserRound, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { EmptyState, PageHeader } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCareerGoals, useCountries, useCountryFit, useVisaRoutes, useWatchRoute } from "@/features/career/hooks";
import { ConfidenceBadge } from "@/features/career/labels";
import type { RouteFit } from "@/features/career/types";
import { Note, Panel } from "@/features/growth/ui";

const NOTICE = "General information only, not legal or immigration advice and not a prediction of approval. Rules change: always confirm on the official page before you act.";

export function InternationalPage() {
  const countries = useCountries();
  const goals = useCareerGoals();
  const [picked, setPicked] = useState<string | null>(null);
  const list = countries.data ?? [];
  // Default to the first target country from career goals that is in the catalogue.
  const fromGoals = goals.data?.target_countries.find((c) => list.some((x) => x.code === c)) ?? null;
  const country = picked ?? fromGoals;
  const fit = useCountryFit(country);

  return (
    <>
      <PageHeader eyebrow="Work abroad" title={<>Passport era? <em>Let's map it</em>.</>}
                  description="Visa routes for the countries you're interested in, and how your profile compares."
                  actions={<Button variant="outline" render={<Link to="/settings?tab=career-goals" />}><Settings2 /> Set where you want to work</Button>} />

      <div role="note" className="mb-4 flex items-start gap-3 rounded-2xl bg-caution-tint px-4 py-3 text-[13px]">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" aria-hidden />
        <div>
          <p className="font-semibold text-caution">This is not legal advice.</p>
          <p className="text-foreground/80">{fit.data?.notice ?? NOTICE}</p>
        </div>
      </div>

      {goals.data && goals.data.search_mode === "india" && (
        <p className="mb-4 text-[13px] text-muted-foreground">
          Your job search is set to India only.{" "}
          <Link to="/settings?tab=career-goals" className="font-medium text-route underline-offset-4 hover:underline">Change it to International or Both</Link> to include jobs abroad in your matches.
        </p>
      )}

      <section aria-labelledby="countries-h" className="mb-4">
        <h2 id="countries-h" className="mb-2 text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase">Choose a country</h2>
        {countries.isLoading ? (
          <div className="flex flex-wrap gap-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-11 w-36 rounded-2xl" />)}</div>
        ) : countries.isError ? <p className="text-sm text-destructive">{errorMessage(countries.error)}</p> : (
          <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 sm:flex-wrap">
            {list.map((c) => {
              const on = country === c.code;
              return (
                <button key={c.code} type="button" onClick={() => setPicked(c.code)} aria-pressed={on}
                        className={cn("flex shrink-0 items-center gap-2.5 rounded-2xl bg-card py-1.5 pr-3.5 pl-1.5 text-left ring-1 transition-[box-shadow,background-color] duration-150",
                          on ? "ring-2 ring-route/45 shadow-[var(--shadow-raised)]" : "ring-border hover:bg-paper-sunk/60")}>
                  <span aria-hidden className={cn("readout flex h-8 w-9 items-center justify-center rounded-xl text-[12px] font-semibold", on ? "bg-route text-primary-foreground" : "bg-paper-sunk text-heading")}>{c.code}</span>
                  <span>
                    <span className="block text-[13.5px] font-semibold text-heading">{c.name}</span>
                    <span className="block text-[11.5px] text-muted-foreground">{c.region ?? ""}{c.region ? " · " : ""}{c.routes} route{c.routes === 1 ? "" : "s"}</span>
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {!country ? (
        <EmptyState icon={<Globe2 className="size-8" />} title="Pick a country to see its visa routes">
          We'll show the main work routes, what they generally need, and how your profile compares.
        </EmptyState>
      ) : fit.isLoading ? <Skeleton className="h-64 rounded-2xl" /> : fit.isError ? (
        <EmptyState title="Couldn't load this country">{errorMessage(fit.error)}</EmptyState>
      ) : fit.data && <CountryFitView code={country} />}
    </>
  );
}

function CountryFitView({ code }: { code: string }) {
  const fit = useCountryFit(code).data!;
  const watched = useVisaRoutes(code);
  const watchFlags = new Map((watched.data ?? []).map((r) => [r.id, r.watching]));
  const p = fit.profile_used;
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 space-y-4">
        {fit.already_authorised && (
          <div role="status" className="flex items-start gap-3 rounded-2xl bg-success-tint px-4 py-3 text-[13px]">
            <BadgeCheck className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
            <div>
              <p className="font-semibold text-success">You said you can already work in {fit.country.name}.</p>
              <p className="text-foreground/80">You may not need a visa route. The routes below are shown for reference.</p>
            </div>
          </div>
        )}
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-[20px] font-bold tracking-[-0.02em]">Routes into {fit.country.name}</h2>
          <span className="text-xs text-muted-foreground"><span className="readout">{fit.routes.length}</span> route{fit.routes.length === 1 ? "" : "s"} catalogued</span>
        </div>
        {fit.routes.length === 0 ? <EmptyState title="No routes catalogued for this country yet" /> : (
          <div className="grid gap-4 xl:grid-cols-2">
            {fit.routes.map((r) => <RouteCard key={r.id} route={r} watching={watchFlags.get(r.id) ?? r.watching} watchKnown={!!watched.data} />)}
          </div>
        )}
      </div>

      <div className="space-y-4">
        <Panel title="Compared using" icon={<UserRound />} description="From your profile. Update it in Settings if anything is off.">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[13px]">
            <dt className="text-muted-foreground">Experience</dt><dd><span className="readout">{p.years_experience}</span> years</dd>
            <dt className="text-muted-foreground">Education</dt><dd className="capitalize">{p.education ?? "not found in your profile"}</dd>
            <dt className="text-muted-foreground">Languages</dt><dd>{p.languages.length ? p.languages.join(", ") : "none listed"}</dd>
          </dl>
          {fit.country.official_source_url && (
            <a href={fit.country.official_source_url} target="_blank" rel="noopener noreferrer"
               className="mt-3 inline-flex items-center gap-1 text-[13px] font-medium text-route underline-offset-4 hover:underline">
              Official immigration site <ExternalLink className="size-3.5" aria-hidden />
            </a>
          )}
        </Panel>
        {fit.relocation_tips.length > 0 && (
          <Panel title="Tips if you plan to relocate" icon={<Lightbulb />}>
            <ul className="space-y-2 text-[13px]">
              {fit.relocation_tips.map((t) => <li key={t} className="flex gap-2"><span aria-hidden className="mt-1.5 size-1.5 shrink-0 rounded-full bg-violet" />{t}</li>)}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}

function sponsorshipText(v: boolean | null): string {
  if (v === true) return "Needs a job offer from an employer who sponsors you";
  if (v === false) return "No employer sponsorship needed";
  return "Sponsorship: not stated";
}

function RouteCard({ route, watching, watchKnown }: { route: RouteFit; watching: boolean; watchKnown: boolean }) {
  const watch = useWatchRoute();
  const { strengths, gaps, unknown, summary } = route.fit;
  return (
    <article className="flex flex-col rounded-2xl bg-card ring-1 ring-border">
      <div className="space-y-2 px-4 pt-4 sm:px-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h3 className="font-display text-[16px] font-bold text-heading">{route.name}</h3>
          <ConfidenceBadge confidence={route.confidence} />
        </div>
        <p className="text-[13px] text-muted-foreground">{route.summary}</p>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1"><Building2 className="size-3" aria-hidden />{sponsorshipText(route.requires_sponsorship)}</span>
          <span className="inline-flex items-center gap-1"><CalendarCheck className="size-3" aria-hidden />Official page last checked: {route.last_checked_at ? formatDate(route.last_checked_at) : "not yet"}</span>
          {route.review_by && <span>Review due {formatDate(route.review_by)}</span>}
        </div>
      </div>
      <div className="flex-1 space-y-3 px-4 pt-3 pb-4 text-[13px] sm:px-5">
        {route.source_changed_at && (
          <Note tone="caution" icon={<AlertTriangle />}>The official page changed on {formatDate(route.source_changed_at)}. Read it before relying on this summary.</Note>
        )}
        <div className={cn("flex items-center gap-2 rounded-xl px-3 py-2 font-medium", gaps.length ? "bg-caution-tint text-caution" : "bg-route-tint text-route")}>
          {gaps.length ? <CircleAlert className="size-4 shrink-0" aria-hidden /> : <CheckCircle2 className="size-4 shrink-0" aria-hidden />}
          {summary}
        </div>
        <FitList icon={<CheckCircle2 className="size-3.5 text-route" />} title="In your favour" items={strengths} />
        <FitList icon={<XCircle className="size-3.5 text-destructive" />} title="Gaps" items={gaps} />
        <FitList icon={<CircleHelp className="size-3.5 text-muted-foreground" />} title="Couldn't tell from your profile" items={unknown} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/70 px-4 py-3 text-[13px] sm:px-5">
        <a href={route.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-medium text-route underline-offset-4 hover:underline">
          Official source <ExternalLink className="size-3.5" aria-hidden />
        </a>
        <label className="flex items-center gap-2 text-xs">
          {watch.isPending && <Loader2 className="size-3 animate-spin" />}
          <Switch checked={watching} disabled={!watchKnown || watch.isPending} aria-label={`Tell me if the official page for ${route.name} changes`}
                  onCheckedChange={(c) => watch.mutate({ id: route.id, watching: !!c }, {
                    onSuccess: (r) => toast.success(r.watching ? "On it. We'll tell you if the official page changes" : "Stopped watching this route"),
                    onError: (e) => toast.error(errorMessage(e)),
                  })} />
          Tell me if the official page changes
        </label>
      </div>
    </article>
  );
}

function FitList({ icon, title, items }: { icon: React.ReactNode; title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold tracking-[0.04em] text-muted-foreground uppercase">{title}</div>
      <ul className="space-y-1">{items.map((t) => <li key={t} className="flex items-start gap-1.5"><span className="mt-0.5 shrink-0" aria-hidden>{icon}</span>{t}</li>)}</ul>
    </div>
  );
}
