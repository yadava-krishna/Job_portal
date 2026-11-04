import { useState } from "react";
import { Download, FileSpreadsheet, History, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, PageHeader } from "@/components/app/common";
import { StatCard } from "@/pages/DashboardPage";
import { downloadFile, errorMessage } from "@/lib/api";
import { bytes, formatDate, statusLabels } from "@/lib/format";
import { useAnalytics, useGenerateReport, useReports } from "@/services/queries";
import type { Report } from "@/types/api";
import { Briefcase, CheckCircle2, MessageSquare, XCircle } from "lucide-react";

export function ReportsPage() {
  const reports = useReports();
  const generate = useGenerateReport();
  const analytics = useAnalytics(90);
  const [downloading, setDownloading] = useState<number | null>(null);
  const a = analytics.data;
  const applied = a?.status_counts.SUBMITTED ?? 0;
  const responses = a?.platforms.reduce((s, p) => s + p.responses, 0) ?? 0;

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
    onSuccess: async (r) => { toast.success("Report ready"); await download(r); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader title="Reports" description="Excel workbooks with only your own jobs and applications. Earlier files are never overwritten."
                  actions={<>
                    <Button variant="outline" onClick={() => make("history")} disabled={generate.isPending}><History /> Full history (Excel)</Button>
                    <Button onClick={() => make("daily")} disabled={generate.isPending}>{generate.isPending ? <Loader2 className="animate-spin" /> : <FileSpreadsheet />} Today's report (Excel)</Button>
                  </>} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Applied (90 days)" value={applied} icon={Briefcase} />
        <StatCard label="Responses" value={responses} icon={MessageSquare} hint="screening, interview or offer" />
        <StatCard label="Response rate" value={applied ? `${Math.round((100 * responses) / applied)}%` : "—"} icon={CheckCircle2} />
        <StatCard label="Failed / withdrawn" value={(a?.status_counts.FAILED ?? 0) + (a?.status_counts.WITHDRAWN ?? 0)} icon={XCircle} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>By platform</CardTitle><CardDescription>Submitted applications and responses</CardDescription></CardHeader>
          <CardContent className="h-64">
            {a?.platforms.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={a.platforms} margin={{ left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="platform" fontSize={11} /><YAxis allowDecimals={false} fontSize={11} /><Tooltip />
                  <Bar dataKey="applied" name="Applied" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="responses" name="Responses" fill="#10b981" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-muted-foreground">No submitted applications yet.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Application outcomes</CardTitle></CardHeader>
          <CardContent>
            {a && Object.keys(a.status_counts).length ? (
              <ul className="divide-y text-sm">{Object.entries(a.status_counts).map(([k, v]) => <li key={k} className="flex justify-between py-2"><span>{statusLabels[k] ?? k}</span><span className="tabular-nums">{v}</span></li>)}</ul>
            ) : <p className="text-sm text-muted-foreground">No applications yet.</p>}
          </CardContent>
        </Card>
      </div>

      <h2 className="mt-8 mb-3 text-lg font-semibold">Generated workbooks</h2>
      {!reports.data?.length ? (
        <EmptyState icon={<FileSpreadsheet className="size-8" />} title="No reports yet">Generate today's report or your full history above. A daily report is also created automatically after the scheduled discovery.</EmptyState>
      ) : (
        <Card className="divide-y p-0">
          {reports.data.map((r) => (
            <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
              <div>
                <div className="font-medium">{r.file_name}</div>
                <div className="text-xs text-muted-foreground">{r.kind === "daily" ? `Daily · ${r.report_date}` : "Full history"} · {bytes(r.size_bytes)} · created {formatDate(r.created_at, true)}</div>
              </div>
              <Button size="sm" variant="outline" onClick={() => download(r)} disabled={downloading === r.id}>{downloading === r.id ? <Loader2 className="animate-spin" /> : <Download />} Download</Button>
            </div>
          ))}
        </Card>
      )}
    </>
  );
}
