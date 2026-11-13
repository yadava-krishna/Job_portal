import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Clock, Calendar, CheckCircle2, AlertCircle } from "lucide-react";
import { Link } from "react-router-dom";

interface TodayItem {
  kind: string;
  application_id: number;
  company: string;
  title: string;
  detail: string;
  due_date?: string | null;
}

interface TodayData {
  your_move: TodayItem[];
  coming_up: TodayItem[];
  waiting_on_them: TodayItem[];
}

export function TodayView() {
  const [data, setData] = useState<TodayData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<TodayData>("/dashboard/today")
      .then((res) => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-4 animate-pulse h-32 flex items-center justify-center text-muted-foreground text-sm">
        Loading today's agenda...
      </div>
    );
  }

  if (!data) return null;

  const totalItems = data.your_move.length + data.coming_up.length + data.waiting_on_them.length;

  if (totalItems === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-card/50 p-6 text-center">
        <CheckCircle2 className="h-8 w-8 text-emerald-500 mx-auto mb-2" />
        <h4 className="font-medium text-foreground text-sm">All caught up for today</h4>
        <p className="text-xs text-muted-foreground mt-1">
          No pending follow-ups or immediate interviews. Discover new jobs to keep momentum!
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
          <Clock className="h-5 w-5 text-primary" /> Today's Focus
        </h3>
        <span className="text-xs text-muted-foreground">{totalItems} active priorities</span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 [&>*]:min-w-0">
        {/* 1. Your Move */}
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
              <AlertCircle className="h-4 w-4" /> Your Move
            </h4>
            <span className="text-xs font-bold text-amber-700 dark:text-amber-400">
              {data.your_move.length}
            </span>
          </div>

          <div className="space-y-2">
            {data.your_move.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nothing waiting on you right now.</p>
            ) : (
              data.your_move.map((item, idx) => (
                <Link
                  key={idx}
                  to={`/applied`}
                  className="block rounded-lg border border-border bg-card p-2.5 hover:border-primary/50 transition-colors"
                >
                  <div className="text-xs font-medium text-foreground truncate">{item.title}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{item.company}</div>
                  <div className="text-[10px] text-amber-600 dark:text-amber-400 mt-1 font-medium">
                    {item.detail}
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>

        {/* 2. Coming Up */}
        <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-primary flex items-center gap-1.5">
              <Calendar className="h-4 w-4" /> Coming Up
            </h4>
            <span className="text-xs font-bold text-primary">{data.coming_up.length}</span>
          </div>

          <div className="space-y-2">
            {data.coming_up.length === 0 ? (
              <p className="text-xs text-muted-foreground">No interviews in the next 3 days.</p>
            ) : (
              data.coming_up.map((item, idx) => (
                <Link
                  key={idx}
                  to={`/applied`}
                  className="block rounded-lg border border-border bg-card p-2.5 hover:border-primary/50 transition-colors"
                >
                  <div className="text-xs font-medium text-foreground truncate">{item.title}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{item.company}</div>
                  <div className="text-[10px] text-primary mt-1 font-medium">{item.detail}</div>
                </Link>
              ))
            )}
          </div>
        </div>

        {/* 3. Waiting On Them */}
        <div className="rounded-xl border border-border bg-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
              <Clock className="h-4 w-4 text-muted-foreground" /> Waiting On Them
            </h4>
            <span className="text-xs font-bold text-muted-foreground">{data.waiting_on_them.length}</span>
          </div>

          <div className="space-y-2">
            {data.waiting_on_them.length === 0 ? (
              <p className="text-xs text-muted-foreground">No applications currently in quiet wait.</p>
            ) : (
              data.waiting_on_them.slice(0, 5).map((item, idx) => (
                <Link
                  key={idx}
                  to={`/applied`}
                  className="block rounded-lg border border-border bg-muted/30 p-2.5 hover:border-primary/50 transition-colors"
                >
                  <div className="text-xs font-medium text-foreground truncate">{item.title}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{item.company}</div>
                  <div className="text-[10px] text-muted-foreground mt-1">{item.detail}</div>
                </Link>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
