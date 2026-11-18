import { useState, type ReactNode } from "react";
import { Download, FileSpreadsheet, History, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { ErrorState, PageHeader } from "@/components/app/common";
import { downloadFile, errorMessage } from "@/lib/api";
import { bytes, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useAnalytics, useGenerateReport, useReports } from "@/services/queries";
import { useFunnel } from "@/features/growth/queries";
import { StatusPill } from "@/features/applications/pills";
import type { Report } from "@/types/api";

const tooltipStyle = {
  contentStyle: { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 12, fontSize: 12, boxShadow: "var(--shadow-raised)" },
  labelStyle: { color: "var(--muted-foreground)", marginBottom: 2 },
  itemStyle: { color: "var(--foreground)", padding: 0 },
  cursor: { fill: "var(--muted)", opacity: 0.6 },
};
const axisTick = { fill: "var(--muted-foreground)", fontSize: 11 };
const STATUS_ORDER = ["SUBMITTED", "CONFIRMATION_PENDING", "OPENED", "PREPARED", "FAILED", "WITHDRAWN"];

/** One question, one answer: the question as the heading, the answer as a big number or a small chart. */
function Block({ q, children, className, aside }: { q: string; children: ReactNode; className?: string; aside?: ReactNode }) {
  return (
    <section className={cn("flex min-w-0 flex-col rounded-2xl bg-card p-4 ring-1 ring-border sm:p-5", className)}>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="font-display text-[15px] font-bold tracking-[-0.01em] text-heading">{q}</h2>
        {aside && <div className="text-xs text-muted-foreground">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

function Big({ value, unit, tone }: { value: ReactNode; unit?: string; tone?: "route" | "success" | "muted" }) {
  return (
    <div className={cn("readout text-[40px] leading-none font-semibold tracking-[-0.03em]",
      tone === "route" ? "text-route" : tone === "success" ? "text-success" : tone === "muted" ? "text-muted-foreground" : "text-heading")}>
      {value}{unit && <span className="ml-0.5 text-lg text-muted-foreground">{unit}</span>}
    </div>
  );
}

export function ReportsPage() {
  const reports = useReports();
  const generate = useGenerateReport();
  const analytics = useAnalytics(90);
  const funnel = useFunnel();
  const [downloading, setDownloading] = useState<number | null>(null);
  const a = analytics.data;
  const applied = a?.status_counts.SUBMITTED ?? 0;
  const responses = a?.platforms.reduce((s, p) => s + p.responses, 0) ?? 0;
  const rate = applied ? Math.round((100 * responses) / applied) : null;
  const sentInRange = a?.series.reduce((s, d) => s + d.applied, 0) ?? 0;
  const series = (a?.series ?? []).map((d) => ({ ...d, day: new Date(d.date).toLocaleDateString(undefined, { day: "numeric", month: "short" }) }));
  const outcomes = a ? STATUS_ORDER.filter((k) => a.status_counts[k]).map((k) => [k, a.status_counts[k]] as const)
    .concat(Object.entries(a.status_counts).filter(([k, v]) => v && !STATUS_ORDER.includes(k))) : [];

  const download = async (r: Report) => {
    setDownloading(r.id);
    try {
      await downloadFile(`/reports/${r.id}/download`, r.file_name);
    } catch (e) {
      toast.error(errorMessage(e, "Download failed"));
    } finally {
      setDownloading(null);
    }
  };

  const make = (kind: "daily" | "history") => generate.mutate(kind, {
    onSuccess: async (r) => { toast.success("Report ready. Fresh off the press."); await download(r); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader title={<>The <em>receipts</em></>} description="How your search is really going, with numbers to back it up, plus Excel downloads of only your own jobs and applications."
                  actions={<>
                    <Button variant="outline" size="sm" onClick={() => make("history")} disabled={generate.isPending}><History /> Full history (Excel)</Button>
                    <Button size="sm" onClick={() => make("daily")} disabled={generate.isPending}>{generate.isPending ? <Loader2 className="animate-spin" /> : <FileSpreadsheet />} Today's report (Excel)</Button>
                  </>} />

      {analytics.isError && <ErrorState error={analytics.error} onRetry={() => void analytics.refetch()} className="mb-4" />}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Block q="How many did you send?" aside={a ? `last ${a.days} days` : undefined}>
          <div className="flex items-end justify-between gap-3">
            <div><Big value={sentInRange} /><p className="mt-1 text-xs text-muted-foreground">confirmed submissions{applied !== sentInRange && <> · <span className="readout">{applied}</span> in total</>}</p></div>
          </div>
          <div className="mt-3 h-24" aria-label="Applications submitted per day" role="img">
            {series.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={series} margin={{ top: 2, right: 0, bottom: 0, left: 0 }} barCategoryGap={2}>
                  <XAxis dataKey="day" hide />
                  <YAxis hide allowDecimals={false} />
                  <Tooltip {...tooltipStyle} formatter={(v) => [v, "Submitted"]} />
                  <Bar dataKey="applied" name="Submitted" fill="var(--chart-1)" radius={[4, 4, 0, 0]} minPointSize={2} />
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-muted-foreground">Nothing sent yet. Your first one's a click away.</p>}
          </div>
        </Block>

        <Block q="Is anyone answering?">
          <Big value={rate ?? "—"} unit={rate != null ? "%" : undefined} tone={rate ? "route" : "muted"} />
          <p className="mt-1 text-xs text-muted-foreground">
            <span className="readout text-foreground">{responses}</span> of <span className="readout text-foreground">{applied}</span> submitted applications got a reply (screening, interview or offer)
          </p>
          <div className="mt-auto pt-4">
            <div className="h-2 overflow-hidden rounded-full bg-muted" aria-hidden>
              <div className="h-full rounded-full bg-route transition-[width] duration-500 ease-[cubic-bezier(.2,0,0,1)]" style={{ width: `${rate ?? 0}%` }} />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{rate == null ? "Replies show up here once you've sent a few." : rate >= 30 ? "That's a strong reply rate. Keep the momentum." : "Replies take time. Tailored resumes tend to lift this."}</p>
          </div>
        </Block>

        <Block q="Where do applications stall?" className="md:col-span-2 xl:col-span-1" aside="all time">
          {funnel.isLoading ? <Loader2 className="size-4 animate-spin text-muted-foreground" /> : !funnel.data ? <p className="text-sm text-muted-foreground">Not enough data yet.</p> : (
            <FunnelBars counts={funnel.data.counts} conversion={funnel.data.conversion} />
          )}
        </Block>

        <Block q="Which platforms reply?" className="md:col-span-2" aside="submitted vs. replies">
          {a?.platforms.length ? (
            <div className="h-48" role="img" aria-label="Submitted applications and replies by platform">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={a.platforms} layout="vertical" margin={{ top: 0, right: 28, bottom: 0, left: 0 }} barGap={2} barCategoryGap="28%">
                  <CartesianGrid horizontal={false} stroke="var(--border)" strokeDasharray="2 4" />
                  <XAxis type="number" allowDecimals={false} tick={axisTick} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="platform" tick={axisTick} axisLine={false} tickLine={false} width={108} />
                  <Tooltip {...tooltipStyle} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, color: "var(--muted-foreground)" }} />
                  <Bar dataKey="applied" name="Submitted" fill="var(--chart-1)" radius={[0, 4, 4, 0]}>
                    <LabelList dataKey="applied" position="right" fill="var(--muted-foreground)" fontSize={11} />
                  </Bar>
                  <Bar dataKey="responses" name="Replies" fill="var(--chart-4)" radius={[0, 4, 4, 0]}>
                    <LabelList dataKey="responses" position="right" fill="var(--muted-foreground)" fontSize={11} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : <p className="text-sm text-muted-foreground">No submitted applications yet. Once you send some, you'll see which job sites answer.</p>}
        </Block>

        <Block q="Where does everything stand?">
          {outcomes.length ? (
            <ul className="divide-y divide-border/70 text-sm">
              {outcomes.map(([k, v]) => (
                <li key={k} className="flex items-center justify-between py-2"><StatusPill status={k} /><span className="readout text-[15px] font-semibold text-heading">{v}</span></li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted-foreground">No applications yet.</p>}
        </Block>
      </div>

      <section className="mt-6">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <h2 className="font-display text-[17px] font-bold text-heading">Workbooks</h2>
          <p className="text-xs text-muted-foreground">A daily one is made after each scheduled search. Older files are never overwritten.</p>
        </div>
        {reports.isError ? <ErrorState error={reports.error} onRetry={() => void reports.refetch()} /> : !reports.data?.length ? (
          <div className="rounded-2xl border border-dashed px-5 py-8 text-center text-sm text-muted-foreground">
            <FileSpreadsheet className="mx-auto mb-2 size-6" />
            <div className="font-medium text-foreground">No workbooks yet</div>
            Generate today's report or your full history above.
          </div>
        ) : (
          <ul className="divide-y divide-border/70 overflow-hidden rounded-2xl bg-card ring-1 ring-border">
            {reports.data.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm">
                <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg", r.kind === "daily" ? "bg-route-tint text-route" : "bg-lavender text-violet")}>
                  {r.kind === "daily" ? <FileSpreadsheet className="size-4" /> : <History className="size-4" />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{r.file_name}</div>
                  <div className="readout text-xs text-muted-foreground">{r.kind === "daily" ? `Daily · ${r.report_date}` : "Full history"} · {bytes(r.size_bytes)} · created {formatDate(r.created_at, true)}</div>
                </div>
                <Button size="sm" variant="ghost" onClick={() => download(r)} disabled={downloading === r.id}>{downloading === r.id ? <Loader2 className="animate-spin" /> : <Download />} Download</Button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

const FUNNEL = [
  { key: "applied", label: "Applied" }, { key: "screening", label: "Screening" }, { key: "interview", label: "Interview" }, { key: "offer", label: "Offer" },
] as const;

/** Submitted → screening → interview → offer, each bar scaled to the submitted count, with the step-to-step rate. */
function FunnelBars({ counts, conversion }: { counts: Record<string, number>; conversion: { application_to_screening: number | null; application_to_interview: number | null; interview_to_offer: number | null } }) {
  const top = Math.max(1, counts.applied ?? 0);
  const rates: (number | null)[] = [null, conversion.application_to_screening, conversion.application_to_interview, conversion.interview_to_offer];
  const rateLabel = ["", "of applied", "of applied", "of interviews"];
  return (
    <ol className="space-y-3">
      {FUNNEL.map((s, i) => {
        const n = counts[s.key] ?? 0;
        return (
          <li key={s.key} className="grid grid-cols-[7rem_minmax(0,1fr)_2.25rem] items-center gap-2.5 text-[13px]">
            <span className="leading-tight text-foreground">{s.label}
              {rates[i] != null && <span className="readout block text-[10.5px] text-muted-foreground">{rates[i]}% {rateLabel[i]}</span>}
            </span>
            <span className="relative h-4 overflow-hidden rounded-md bg-muted/70">
              <span className={cn("absolute inset-y-0 left-0 rounded-md transition-[width] duration-500 ease-[cubic-bezier(.2,0,0,1)]", s.key === "offer" ? "bg-success" : "bg-[var(--chart-1)]")}
                    style={{ width: `${Math.max(n ? 3 : 0, (100 * n) / top)}%`, opacity: 1 - i * 0.12 }} />
            </span>
            <span className="readout text-right text-[15px] font-semibold text-heading">{n}</span>
          </li>
        );
      })}
    </ol>
  );
}
