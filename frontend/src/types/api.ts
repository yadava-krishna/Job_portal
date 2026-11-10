// Types mirroring the backend's Pydantic schemas (backend/schemas/*).

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  role?: string;
  is_active?: boolean;
  created_at: string;
  onboarding_completed_at: string | null;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Health {
  status: "ok" | "degraded";
  service: string;
  version: string;
  timestamp: string;
  database: { connected: boolean; error: string | null };
  scheduler: { enabled: boolean; running: boolean; next_run: string | null; last_run: Record<string, unknown> | null };
}

export interface ExperienceItem {
  title: string;
  company: string;
  start: string | null;
  end: string | null;
  is_current: boolean;
  bullets: string[];
}
export interface EducationItem {
  degree: string | null;
  institution: string | null;
  university: string | null;
  year: number | null;
}
export interface ProjectItem {
  name: string;
  bullets: string[];
}
export interface EditableProfile {
  full_name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  headline: string | null;
  summary: string | null;
  skills: string[];
  experience: ExperienceItem[];
  education: EducationItem[];
  certifications: string[];
  projects: ProjectItem[];
  achievements: string[];
  languages: string[];
  linkedin_url?: string | null;
  github_url?: string | null;
  portfolio_url?: string | null;
  website_url?: string | null;
}
export interface ResumeInfo {
  id: number;
  original_filename: string;
  size_bytes: number;
  page_count: number;
  sha256: string;
  uploaded_at: string;
  is_active: boolean;
}
export interface ExperienceSummary {
  months: number;
  years: number;
  years_months: string;
  merged_periods: string[][];
  method: string;
  note: string | null;
}
export interface ProfileResponse {
  has_resume: boolean;
  resume: ResumeInfo | null;
  parsed: EditableProfile | null;
  confirmed: EditableProfile | null;
  confirmed_at: string | null;
  experience: ExperienceSummary | null;
  parse_warnings: string[];
  verified_facts: VerifiedFacts;
}
export interface VerifiedFacts {
  current_ctc?: string | null;
  expected_ctc?: string | null;
  notice_period?: string | null;
  willing_to_relocate?: boolean | null;
  work_authorization?: string | null;
  earliest_start_date?: string | null;
  shift_flexibility?: string | null;
  requires_sponsorship?: boolean | null;
  relevant_experience?: string | null;
  custom_answers?: { question: string; answer: string }[];
}

export interface ApplyOptions {
  original_url: string | null;
  original_supported: boolean;
  platform: string | null;
  hosted_form_url: string | null;
  direct_apply: boolean;
  message: string;
}
export interface PairingCode { code: string; expires_at: string; expires_in_seconds: number }
export interface ExtensionDevice { id: number; name: string; scopes: string[]; created_at: string; last_used_at: string | null; expires_at: string | null }

export type WorkMode = "Remote" | "Hybrid" | "On-site";
export type EmploymentType = "Full-time" | "Contract" | "Part-time" | "Internship" | "Temporary";
export interface Weights {
  core_skills: number;
  experience: number;
  responsibilities: number;
  education: number;
  location: number;
}
export interface Preferences {
  domains: string[];
  industries: string[];
  job_titles: string[];
  title_keywords: string[];
  locations: string[];
  work_modes: WorkMode[];
  salary_min: number | null;
  salary_max: number | null;
  currency: string;
  experience_min: number | null;
  experience_max: number | null;
  employment_types: EmploymentType[];
  notice_period: string | null;
  preferred_companies: string[];
  excluded_companies: string[];
  min_match_score: number;
  weights: Weights;
  application_settings: { approval_required: boolean; cover_letter: "never" | "when_required" | "always"; max_prepared_per_day: number };
  is_configured?: boolean;
}

export interface PlatformInfo {
  platform: string;
  enabled: boolean;
  discovery_sources: string[];
  available_sources: { id: string; label: string }[];
  automated_search: boolean;
  automated_apply: boolean;
  application_method: string;
  notes: string;
}
export interface OnboardingStatus {
  resume_uploaded: boolean;
  profile_confirmed: boolean;
  preferences_saved: boolean;
  platforms_selected: boolean;
  completed: boolean;
}
export interface EmailIntegration {
  enabled: boolean;
  imap_host: string;
  imap_port: number;
  username: string | null;
  has_password: boolean;
  folder: string;
  lookback_days: number;
  last_checked_at: string | null;
  last_error: string | null;
}

export interface JobListing {
  id: number;
  platform: string;
  external_job_id: string | null;
  company: string;
  title: string;
  location: string | null;
  work_mode: string | null;
  employment_type: string | null;
  experience_required: string | null;
  salary_range: string | null;
  job_url: string | null;
  posted_at: string | null;
  posted_at_source: string | null;
  posted_label: string;
  description_preview: string | null;
  has_full_description: boolean;
  source: string;
  /** verified (official API, listing page or you) | estimated (alert email) | unknown: never shown as recent. */
  posted_at_confidence: PostedConfidence;
  first_seen_at: string | null;
  last_verified_at: string | null;
  closed_at: string | null;
  industry: string | null;
  department: string | null;
  seniority?: string | null;
  sponsorship_signal?: "verified" | "inferred" | "none" | "unknown" | null;
  sources: JobSource[];
}
export type PostedConfidence = "verified" | "estimated" | "unknown";
export interface JobSource {
  source: string;
  platform: string | null;
  url: string | null;
  first_seen_at: string;
}
export interface UserJob {
  user_job_id: number;
  status: "new" | "shortlisted" | "dismissed" | "applied";
  is_saved: boolean;
  match_score: number | null;
  match_category: string | null;
  matching_skills: string[];
  missing_skills: string[];
  eligibility_status: string | null;
  eligibility?: "pass" | "fail" | "unknown" | null;
  scoring_method: string | null;
  discovered_at: string;
  saved_at: string | null;
  dismissed_at: string | null;
  application_id: number | null;
  application_status: string | null;
  job: JobListing;
}
export interface JobDetail extends UserJob {
  description: string | null;
  responsibilities: string[];
  required_skills: string[];
  preferred_skills: string[];
  education_requirements: string[];
  mandatory_qualifications: string[];
  verification_flags: string[];
  description_is_snippet: boolean;
}
export interface ComponentScore {
  name: string;
  score: number;
  weight: number;
  weighted: number;
  evidence: string;
  method: string;
}
export interface JobAnalysis {
  user_job_id: number;
  overall_score: number | null;
  category: string | null;
  components: ComponentScore[];
  matching_skills: string[];
  missing_skills: string[];
  missing_optional_skills: string[];
  relevant_experience: string;
  experience_gap: string;
  education_match: string | null;
  location_match: string | null;
  responsibilities_match: string[];
  reasons_for: string[];
  reasons_against: string[];
  recommendation: string;
  explanation: string;
  eligibility_status: string | null;
  eligibility_reasons: string[];
  scoring_method: string | null;
  confidence: string | null;
  notes: string[];
}
export interface JobList {
  items: UserJob[];
  total: number;
  /** Jobs left out by a posting-date filter because their posting date is unknown. */
  hidden_unknown_dates: number;
  page: number;
  page_size: number;
}
export interface DiscoveryRun {
  id: number;
  trigger: string;
  status: "running" | "completed" | "partial" | "failed";
  sources: string[];
  started_at: string;
  completed_at: string | null;
  jobs_found: number;
  jobs_new: number;
  jobs_matched: number;
  duplicates: number;
  error_details: { type: string; platform: string | null; message: string }[];
  platform_stats: Record<string, Record<string, number>>;
  saved_search_id?: number | null;
  /** Per source: what happened, including why a source did not run. */
  source_results: Record<string, SourceResult>;
  /** While running: the current stage. When finished: a plain-language outcome. */
  summary: string | null;
}
export type SourceResultStatus = "pending" | "ok" | "empty" | "partial" | "failed" | "not_configured" | "disabled";
export interface SourceResult {
  label: string;
  status: SourceResultStatus;
  message: string | null;
  found: number;
  new: number;
  duplicates: number;
  failed_requests: number;
  boards_ok?: number;
  boards_failed?: number;
  listings_checked?: number;
}
export interface SourceHealth {
  key: string;
  label: string;
  kind: "ats" | "api" | "email" | "manual";
  enabled: boolean;
  configured: boolean;
  missing: string | null;
  connection: "ok" | "degraded" | "failing" | "unknown" | "not_configured" | "disabled";
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  jobs_in_feed: number;
  boards: { total: number; ok: number; failing: number; unchecked: number } | null;
  last_run: (SourceResult & { run_id: number; at: string | null }) | null;
}
export interface SourcesOverview {
  sources: SourceHealth[];
  last_run: DiscoveryRun | null;
  saved_searches: number;
  enabled_searches: number;
}
export interface ImportResult {
  run: DiscoveryRun;
  user_job_ids: number[];
  errors: string[];
}
export interface SearchLink {
  platform: string;
  title: string;
  location: string;
  url: string;
}

export type ApplicationStatus = "PREPARED" | "OPENED" | "CONFIRMATION_PENDING" | "SUBMITTED" | "FAILED" | "WITHDRAWN";
export type Stage = "applied" | "screening" | "assessment" | "interview" | "offer" | "rejected" | "withdrawn" | "archived";
export interface Application {
  id: number;
  status: ApplicationStatus;
  stage: Stage | null;
  user_job_id: number | null;
  match_score: number | null;
  match_category: string | null;
  resume_used: string | null;
  reference_id: string | null;
  confirmation_text: string | null;
  confirmation_source: string | null;
  created_at: string;
  opened_at: string | null;
  submitted_at: string | null;
  submission_method?: string | null;
  follow_up_at?: string | null;
  job: JobListing;
}
export interface ScreeningAnswer {
  question: string;
  answer: string;
  source: string;
  status: string;
}
export interface ChecklistItem {
  check: string;
  status: "PASS" | "CHECK" | "WARN" | "ACTION";
  detail: string;
}
export interface AppEvent {
  id: number;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  details: string | null;
  created_at: string;
}
export interface ApplicationDetail extends Application {
  cover_letter: string | null;
  screening_answers: ScreeningAnswer[];
  checklist: ChecklistItem[];
  needs_candidate_input: string[];
  notes: string | null;
  events: AppEvent[];
}
export interface Report {
  id: number;
  kind: "daily" | "history";
  report_date: string;
  file_name: string;
  size_bytes: number;
  created_at: string;
}
export interface DashboardSummary {
  total_discovered: number;
  total_shortlisted: number;
  total_applied: number;
  total_saved: number;
  pending_applications: number;
  average_match_score: number | null;
  discovered_today: number;
  applied_today: number;
  posted_today_verified: number;
  interviews: number;
  offers: number;
  platforms: { platform: string; discovered: number; shortlisted: number; applied: number; average_score: number | null }[];
  last_discovery_run: null | {
    id: number;
    status: string;
    started_at: string;
    completed_at: string | null;
    jobs_found: number;
    jobs_new: number;
    jobs_matched: number;
    errors: number;
  };
}
export interface ActivityItem {
  kind: "application" | "discovery";
  event_type: string;
  at: string;
  application_id?: number;
  run_id?: number;
  title?: string;
  company?: string;
  to_status?: string | null;
  details?: string | null;
}
export interface Analytics {
  days: number;
  series: { date: string; discovered: number; applied: number }[];
  funnel: { stage: string; count: number }[];
  platforms: { platform: string; applied: number; responses: number; rejected: number; response_rate: number }[];
  status_counts: Record<string, number>;
}

export type AtsName = "greenhouse" | "lever" | "ashby" | "smartrecruiters" | "recruitee";
export type SearchSource = AtsName | "adzuna_api";
export interface DirectoryCompany {
  name: string;
  ats: AtsName;
  token: string;
  industry: string | null;
  domain: string | null;
  curated: boolean;
  company_id: number | null;
  watched: boolean;
}
export interface Company {
  id: number;
  name: string;
  ats: AtsName;
  board_token: string;
  region: string | null;
  industry: string | null;
  domain: string | null;
  origin: "curated" | "jobsync" | "user";
  board_url: string;
  last_fetched_at: string | null;
  last_status: "ok" | "empty" | "not_found" | "error" | null;
  last_error: string | null;
  job_count: number | null;
}
export interface SearchCriteria {
  keywords: string[];
  exclude_keywords: string[];
  locations: string[];
  remote_ok: boolean;
  industries: string[];
  experience_years: number | null;
  employment_types: EmploymentType[];
  work_modes: WorkMode[];
  company_ids: number[];
  use_watchlist: boolean;
  include_suggested: boolean;
  related_titles: boolean;
  sources: SearchSource[];
  max_age_days: number | null;
}
export interface SavedSearchInput {
  name: string;
  criteria: SearchCriteria;
  schedule: "manual" | "daily" | "weekly";
  min_match_score: number | null;
  enabled: boolean;
}
export interface SavedSearch extends SavedSearchInput {
  id: number;
  origin: "user" | "starter";
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run: DiscoveryRun | null;
}
export interface AppNotification {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  occurrences: number;
  read_at: string | null;
  created_at: string;
}
export interface NotificationList {
  items: AppNotification[];
  unread: number;
}

export interface Interview {
  id: number;
  application_id: number;
  /** Backend field names (InterviewOut). */
  round_name?: string | null;
  interviewers?: string | null;
  location?: string | null;
  mode?: "video" | "phone" | "onsite" | null;
  /** Older client names, kept so existing code compiles; the API sends the names above. */
  round?: string;
  meeting_url?: string | null;
  interviewer?: string | null;
  scheduled_at: string;
  duration_minutes: number;
  notes: string | null;
  outcome: string;
  created_at?: string;
  company?: string;
  title?: string;
}

export interface Offer {
  id: number;
  application_id: number;
  base_salary: number | null;
  currency: string;
  bonus: number | null;
  equity: string | null;
  signing_bonus?: number | null;
  /** Backend name (OfferOut); `deadline` is the older client name. */
  decision_deadline?: string | null;
  joining_date?: string | null;
  deadline?: string | null;
  status: string;
  notes: string | null;
  created_at: string;
  company?: string;
  title?: string;
}

export interface ApplicationContact {
  id: number;
  application_id: number;
  name: string;
  role: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  notes: string | null;
  created_at: string;
}
