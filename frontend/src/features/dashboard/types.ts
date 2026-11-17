export interface OverviewJob {
  user_job_id: number;
  title: string;
  company: string;
  match_score: number | null;
  location: string | null;
  salary: string | null;
  discovered_at: string | null;
  freshness: "open" | "unconfirmed" | "unchecked" | "expired" | "closed";
  eligibility_status: string | null;
}

export interface OverviewItem {
  kind: string;
  title: string;
  detail: string | null;
  due: string | null;
  application_id: number | null;
  user_job_id: number | null;
  interview_id: number | null;
}

export interface Overview {
  new_jobs: { count: number; min_score: number; days: number; top: OverviewJob[] };
  attention: OverviewItem[];
  upcoming: OverviewItem[];
  waiting: OverviewItem[];
  saved: { count: number; no_longer_open: number; top: OverviewJob[] };
  recent_submitted: { application_id: number; title: string; company: string; submitted_at: string | null; stage: string }[];
  resume: {
    state: "missing" | "not_exported" | "ready";
    message: string | null;
    uploaded: { filename: string; uploaded_at: string } | null;
    profile_confirmed: boolean;
    versions: number;
    latest: { id: number; name: string; updated_at: string | null; status: string } | null;
    last_export_at: string | null;
  };
  discovery: {
    state: "never_run" | "running" | "ok" | "partial" | "failed" | "not_configured";
    problems: { source: string; label: string; status: string; message: string | null }[];
    last_run: { id: number; status: string; started_at: string; completed_at: string | null; jobs_found: number; jobs_new: number } | null;
  };
}
