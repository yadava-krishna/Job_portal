export function scoreTone(score: number | null | undefined): "excellent" | "good" | "moderate" | "low" | "none" {
  if (score == null) return "none";
  if (score >= 85) return "excellent";
  if (score >= 70) return "good";
  if (score >= 55) return "moderate";
  return "low";
}

export const toneClasses: Record<ReturnType<typeof scoreTone>, string> = {
  excellent: "text-emerald-700 bg-emerald-50 ring-emerald-200 dark:text-emerald-300 dark:bg-emerald-950/40 dark:ring-emerald-900",
  good: "text-sky-700 bg-sky-50 ring-sky-200 dark:text-sky-300 dark:bg-sky-950/40 dark:ring-sky-900",
  moderate: "text-amber-700 bg-amber-50 ring-amber-200 dark:text-amber-300 dark:bg-amber-950/40 dark:ring-amber-900",
  low: "text-rose-700 bg-rose-50 ring-rose-200 dark:text-rose-300 dark:bg-rose-950/40 dark:ring-rose-900",
  none: "text-muted-foreground bg-muted ring-border",
};

export const toneStroke: Record<ReturnType<typeof scoreTone>, string> = {
  excellent: "stroke-emerald-500",
  good: "stroke-sky-500",
  moderate: "stroke-amber-500",
  low: "stroke-rose-500",
  none: "stroke-muted-foreground/40",
};

export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, withTime
    ? { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }
    : { day: "2-digit", month: "short", year: "numeric" });
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return "never";
  const diff = Date.now() - new Date(value).getTime();
  const s = Math.round(diff / 1000);
  if (s < 10) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return formatDate(value);
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export const statusLabels: Record<string, string> = {
  PREPARED: "Prepared",
  AWAITING_APPROVAL: "Awaiting approval",
  OPENED: "Opened",
  CONFIRMATION_PENDING: "Confirmation pending",
  SUBMITTED: "Submitted",
  FAILED: "Failed",
  WITHDRAWN: "Withdrawn",
};

export const stageLabels: Record<string, string> = {
  applied: "Applied",
  screening: "Screening",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export function lines(text: string): string[] {
  return text.split("\n").map((l) => l.trim()).filter(Boolean);
}

/** How a job's posting date is shown. An unknown date is never presented as recent. */
export function postedDisplay(job: { posted_at: string | null; posted_label: string; posted_at_confidence?: string; platform: string }): {
  text: string; badge: "Verified" | "Estimated" | "Unknown"; title: string;
} {
  const confidence = job.posted_at ? job.posted_at_confidence ?? "unknown" : "unknown";
  if (confidence === "verified")
    return { text: `Posted ${job.posted_label.replace(/^(Today|Yesterday)/, (m) => m.toLowerCase())}`, badge: "Verified",
             title: "Posting date from the employer's or platform's own data" };
  if (confidence === "estimated")
    return { text: job.posted_label, badge: "Estimated", title: "Estimated from the date of a job-alert email; the job may be older" };
  return { text: "Posting date unknown", badge: "Unknown", title: "The source did not publish a posting date" };
}

/** Distinct platforms a (deduplicated) job was seen on, first-seen first. */
export function seenOn(job: { platform: string; sources?: { platform: string | null }[] }): string[] {
  return Array.from(new Set([job.platform, ...(job.sources ?? []).map((s) => s.platform).filter((p): p is string => !!p)]));
}
