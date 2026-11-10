import { Link } from "react-router-dom";
import { ArrowRight, Compass, Target } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreBadge } from "@/components/app/common";
import { humanizeMissing, missingLabels, stageLabels } from "./format";
import { EligibilityBadge } from "./labels";
import type { CareerSnapshot } from "./types";

export function CareerSnapshotCard({ snapshot }: { snapshot: CareerSnapshot }) {
  const { profile_completeness: comp, next_step: next, top_matches: matches, top_gap: gap } = snapshot;
  const pct = Math.max(0, Math.min(100, comp.percent));
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2"><Compass className="size-4" /> Career snapshot</CardTitle>
          <CardDescription>Where you are now and the one thing worth doing next.</CardDescription>
        </div>
        <Badge variant="outline">{stageLabels[snapshot.stage] ?? snapshot.stage}</Badge>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="rounded-xl border border-primary/25 bg-primary/5 p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-primary">Your next step</div>
          <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">{humanizeMissing(next.reason)}</p>
            <Button size="lg" className="shrink-0" render={<Link to={next.link} />}>{next.label} <ArrowRight /></Button>
          </div>
        </div>

        <div className="grid gap-5 lg:grid-cols-3">
          <section aria-label="Profile completeness" className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">Profile</span>
              <span className="tabular-nums text-muted-foreground">{pct}% complete</span>
            </div>
            <div className="h-2 rounded-full bg-muted" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Profile completeness">
              <div className="h-2 rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
            {comp.missing.length > 0 ? (
              <p className="text-xs text-muted-foreground">
                Still missing: {comp.missing.map((m) => missingLabels[m] ?? m).join(", ")}.{" "}
                <Link to="/settings?tab=profile" className="text-primary underline-offset-4 hover:underline">Complete profile</Link>
              </p>
            ) : <p className="text-xs text-muted-foreground">Your profile has everything matching needs.</p>}
          </section>

          <section aria-label="Top matches" className="space-y-2">
            <div className="text-sm font-medium">Top matches</div>
            {matches.length ? (
              <ul className="space-y-1.5">
                {matches.slice(0, 3).map((m) => (
                  <li key={m.user_job_id}>
                    <Link to={`/discover?job=${m.user_job_id}`} className="flex items-center justify-between gap-2 rounded-lg border p-2 hover:border-primary/50">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">{m.title}</span>
                        <span className="block truncate text-xs text-muted-foreground">{m.company}</span>
                      </span>
                      <span className="flex shrink-0 flex-col items-end gap-1">
                        <ScoreBadge score={m.score} />
                        <EligibilityBadge value={m.eligibility} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-muted-foreground">No scored matches yet. They appear after the next job search.</p>}
          </section>

          <section aria-label="Top skill gap" className="space-y-2">
            <div className="flex items-center gap-1.5 text-sm font-medium"><Target className="size-3.5" /> Skill to work on</div>
            {gap ? (
              <div className="rounded-lg border p-3">
                <div className="text-sm font-medium">{gap.skill}</div>
                <p className="mt-1 text-xs text-muted-foreground">{gap.next_action}</p>
                <Link to="/career" className="mt-2 inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline">
                  See how to close it <ArrowRight className="size-3" />
                </Link>
              </div>
            ) : <p className="text-xs text-muted-foreground">No skill gaps found yet. We look for them once you have job matches.</p>}
          </section>
        </div>
      </CardContent>
    </Card>
  );
}

/** Shown to brand-new users instead of empty charts. */
export function WhatHappensNext() {
  const steps = [
    { title: "Finish your profile", text: "Your resume and preferences decide which jobs we find and how they are scored." },
    { title: "We search every day", text: "New jobs from the sites you chose are collected and matched to you automatically." },
    { title: "Review your best matches", text: "Each match shows why it fits, and whether you meet the hard requirements." },
    { title: "Apply and track", text: "Once you apply, your applications, interviews and follow-ups appear on this page." },
  ];
  return (
    <Card>
      <CardHeader><CardTitle>What happens next</CardTitle><CardDescription>Charts and your daily to-do list appear here after your first application.</CardDescription></CardHeader>
      <CardContent>
        <ol className="space-y-3">
          {steps.map((s, i) => (
            <li key={s.title} className="flex gap-3">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">{i + 1}</span>
              <div>
                <div className="text-sm font-medium">{s.title}</div>
                <div className="text-xs text-muted-foreground">{s.text}</div>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
