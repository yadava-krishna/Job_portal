// Response shapes for the career, learning and international endpoints (backend/api/routes/career.py, growth.py).

export type Eligibility = "pass" | "fail" | "unknown" | null;
export type SkillState = "aware" | "learning" | "practising" | "project_evidence" | "professional_experience" | "interview_ready";
export type GapSeverity = "high" | "medium" | "low";
export type GapStatus = "open" | "in_progress" | "closed" | "ignored";

export interface Gap {
  id: number;
  skill: string;
  severity: GapSeverity | string;
  explanation: string;
  next_action: string;
  evidence_state: SkillState | null;
  status: GapStatus | string;
  job_count: number;
  rejection_count: number;
}

export interface NextStep {
  kind: string;
  label: string;
  link: string;
  reason: string;
}

export interface TopMatch {
  user_job_id: number;
  title: string;
  company: string;
  score: number | null;
  eligibility: Eligibility;
  score_version: string | null;
}

export interface CareerSnapshot {
  stage: "starting" | "exploring" | "applying" | "interviewing" | string;
  profile_completeness: { percent: number; missing: string[] };
  top_matches: TopMatch[];
  top_gap: Gap | null;
  alternative_gaps: Gap[];
  counts: { applications_submitted: number; applications_in_progress: number; upcoming_interviews: number };
  show: { tracker: boolean; interview_prep: boolean; learning: boolean; international: boolean; reflection: boolean };
  next_step: NextStep;
}

export type SearchMode = "india" | "international" | "both";
export type Seniority = "intern" | "entry" | "junior" | "mid" | "senior" | "lead" | "manager" | "director";

export interface CareerGoals {
  search_mode: SearchMode;
  target_countries: string[];
  seniority: Seniority | null;
  open_to_relocation: boolean | null;
  work_authorization: string[];
  needs_sponsorship: boolean | null;
}

export interface Consent {
  kind: string;
  granted: boolean;
  text: string;
  granted_at: string | null;
  revoked_at: string | null;
}

export type EvidenceType = "course" | "certificate" | "project" | "employment" | "publication" | "assessment" | "practice" | "other";

export interface Evidence {
  id: number;
  type: EvidenceType | string;
  title: string;
  url: string | null;
  description: string | null;
  source: string;
  occurred_on: string | null;
  created_at: string;
}

export interface Skill {
  id: number;
  name: string;
  canonical: string;
  state: SkillState;
  state_label: string;
  proficiency: string | null;
  years: number | null;
  source: string;
  verified: boolean;
  evidence_supports: SkillState;
  evidence: Evidence[];
}

export interface SkillsResponse {
  states: { key: SkillState; label: string }[];
  skills: Skill[];
}

export interface GapsResponse {
  best: Gap | null;
  alternatives: Gap[];
  gaps: Gap[];
}

export interface LearningResource {
  id: number;
  skill: string;
  title: string;
  url: string;
  provider: string;
  type: string;
  level: string;
  duration_minutes: number | null;
  is_free: boolean;
  source: string;
  checked_at: string | null;
  link_status: "ok" | "unverifiable" | "broken" | string;
  relevance: string;
}

export interface GapDetail extends Gap {
  learning: {
    skill: string;
    level_suggested: string;
    resources: LearningResource[];
    enough: boolean;
    note: string | null;
  };
}

export interface LearningSession {
  id: number;
  skill: string;
  resource_id: number | null;
  gap_id: number | null;
  status: "active" | "paused" | "completed" | string;
  started_at: string;
  ended_at: string | null;
  active_minutes: number;
  active_seconds: number;
  idle_seconds: number;
  notes: string | null;
  helpful: boolean | null;
}

export interface SessionsResponse {
  sessions: LearningSession[];
  stats: { days: number; sessions: number; completed: number; active_minutes: number; idle_minutes: number };
}

export interface ScoreChange {
  user_job_id: number;
  title: string;
  company: string;
  old_score: number | null;
  new_score: number | null;
}
export interface MatchHistoryItem extends ScoreChange {
  id: number;
  reason: string;
  score_version: string;
  created_at: string;
}
export interface CompleteResult {
  score_changes?: ScoreChange[];
  session: LearningSession;
  skill_state: SkillState;
  skill_state_label: string;
}

export interface Country {
  code: string;
  name: string;
  region: string | null;
  currency: string | null;
  official_source_url: string | null;
  routes: number;
}

export interface VisaRoute {
  id: number;
  country_code: string;
  code: string;
  name: string;
  summary: string;
  requires_sponsorship: boolean | null;
  source_url: string;
  confidence: "unverified" | "stale" | "verified" | string;
  verified_at: string | null;
  last_checked_at: string | null;
  review_by: string | null;
  source_changed_at: string | null;
  watching: boolean;
  notice: string;
  rules: { kind: string; description: string; source_url: string }[];
}

export interface RouteFit extends VisaRoute {
  fit: { strengths: string[]; gaps: string[]; unknown: string[]; summary: string };
}

export interface CountryFit {
  country: { code: string; name: string; official_source_url: string | null };
  already_authorised: boolean;
  profile_used: { years_experience: number; education: string | null; languages: string[] };
  routes: RouteFit[];
  notice: string;
  relocation_tips: string[];
}

/** The consent-required error body of a 403 (backend platform_service.require_consent). */
export interface ConsentRequired {
  message: string;
  consent: string;
  text: string;
}
