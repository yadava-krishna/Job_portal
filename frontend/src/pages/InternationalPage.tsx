import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, BadgeCheck, CheckCircle2, CircleHelp, ExternalLink, Globe2, Loader2, Settings2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { EmptyState, PageHeader } from "@/components/app/common";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCareerGoals, useCountries, useCountryFit, useVisaRoutes, useWatchRoute } from "@/features/career/hooks";
import { ConfidenceBadge } from "@/features/career/labels";
import type { RouteFit } from "@/features/career/types";

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
      <PageHeader title="Working abroad" description="Visa routes for the countries you're interested in, and how your profile compares."
                  actions={<Button variant="outline" render={<Link to="/settings?tab=career-goals" />}><Settings2 /> Set where you want to work</Button>} />

      <div role="note" className="mb-6 flex items-start gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-600 dark:text-amber-400" />
        <div>
          <p className="font-semibold">This is not legal advice.</p>
          <p className="text-muted-foreground">{fit.data?.notice ?? NOTICE}</p>
        </div>
      </div>

      {goals.data && goals.data.search_mode === "india" && (
        <p className="mb-4 text-sm text-muted-foreground">
          Your job search is set to India only.{" "}
          <Link to="/settings?tab=career-goals" className="text-primary underline-offset-4 hover:underline">Change it to International or Both</Link> to include jobs abroad in your matches.
        </p>
      )}

      <section aria-label="Countries" className="mb-6">
        <h2 className="mb-2 text-sm font-medium">Choose a country</h2>
        {countries.isLoading ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
        ) : countries.isError ? <p className="text-sm text-destructive">{errorMessage(countries.error)}</p> : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {list.map((c) => (
              <button key={c.code} type="button" onClick={() => setPicked(c.code)} aria-pressed={country === c.code}
                      className={cn("rounded-xl border bg-card p-3 text-left transition-colors hover:border-primary/50",
                        country === c.code && "border-primary ring-2 ring-primary/30")}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{c.name}</span>
                  <span className="text-xs text-muted-foreground">{c.code}</span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">{c.region ?? ""}{c.region ? " · " : ""}{c.routes} route{c.routes === 1 ? "" : "s"}</div>
              </button>
            ))}
          </div>
        )}
      </section>

      {!country ? (
        <EmptyState icon={<Globe2 className="size-8" />} title="Pick a country to see its visa routes">
          We'll show the main work routes, what they generally need, and how your profile compares.
        </EmptyState>
      ) : fit.isLoading ? <Skeleton className="h-64" /> : fit.isError ? (
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
    <div className="space-y-6">
      {fit.already_authorised && (
        <div role="status" className="flex items-start gap-3 rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-4 text-sm">
          <BadgeCheck className="mt-0.5 size-5 shrink-0 text-emerald-600" />
          <div>
            <p className="font-semibold">You said you can already work in {fit.country.name}.</p>
            <p className="text-muted-foreground">You may not need a visa route. The routes below are shown for reference.</p>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">{fit.country.name}</h2>
          <p className="text-xs text-muted-foreground">
            Compared using: {p.years_experience} years of experience · education {p.education ?? "not found in your profile"}
            {" "}· languages {p.languages.length ? p.languages.join(", ") : "none listed"}
          </p>
        </div>
        {fit.country.official_source_url && (
          <a href={fit.country.official_source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline">
            Official immigration site <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>

      {fit.routes.length === 0 ? <EmptyState title="No routes catalogued for this country yet" /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          {fit.routes.map((r) => <RouteCard key={r.id} route={r} watching={watchFlags.get(r.id) ?? r.watching} watchKnown={!!watched.data} />)}
        </div>
      )}

      {fit.relocation_tips.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Tips if you plan to relocate</CardTitle></CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 pl-5 text-sm">{fit.relocation_tips.map((t) => <li key={t}>{t}</li>)}</ul>
          </CardContent>
        </Card>
      )}
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
    <Card>
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle>{route.name}</CardTitle>
          <ConfidenceBadge confidence={route.confidence} />
        </div>
        <CardDescription>{route.summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>{sponsorshipText(route.requires_sponsorship)}</span>
          <span>Official page last checked: {route.last_checked_at ? formatDate(route.last_checked_at) : "not yet"}</span>
          {route.review_by && <span>Review due {formatDate(route.review_by)}</span>}
        </div>
        {route.source_changed_at && (
          <p className="rounded-md bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-800 dark:text-amber-300">
            The official page changed on {formatDate(route.source_changed_at)}. Read it before relying on this summary.
          </p>
        )}

        <div className={cn("rounded-lg px-3 py-2 text-sm font-medium", gaps.length ? "bg-amber-500/10 text-amber-800 dark:text-amber-300" : "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300")}>
          {summary}
        </div>
        <FitList icon={<CheckCircle2 className="size-3.5 text-emerald-600" />} title="In your favour" items={strengths} />
        <FitList icon={<XCircle className="size-3.5 text-rose-600" />} title="Gaps" items={gaps} />
        <FitList icon={<CircleHelp className="size-3.5 text-muted-foreground" />} title="Couldn't tell from your profile" items={unknown} />

        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
          <a href={route.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
            Official source <ExternalLink className="size-3.5" />
          </a>
          <label className="flex items-center gap-2 text-xs">
            {watch.isPending && <Loader2 className="size-3 animate-spin" />}
            <Switch checked={watching} disabled={!watchKnown || watch.isPending} aria-label={`Tell me if the official page for ${route.name} changes`}
                    onCheckedChange={(c) => watch.mutate({ id: route.id, watching: !!c }, {
                      onSuccess: (r) => toast.success(r.watching ? "We'll tell you if the official page changes" : "Stopped watching this route"),
                      onError: (e) => toast.error(errorMessage(e)),
                    })} />
            Tell me if the official page changes
          </label>
        </div>
      </CardContent>
    </Card>
  );
}

function FitList({ icon, title, items }: { icon: React.ReactNode; title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-muted-foreground">{title}</div>
      <ul className="space-y-1">{items.map((t) => <li key={t} className="flex items-start gap-1.5"><span className="mt-0.5 shrink-0">{icon}</span>{t}</li>)}</ul>
    </div>
  );
}
