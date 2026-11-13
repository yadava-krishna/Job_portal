// Response shapes for the growth endpoints (backend/api/routes/growth.py, admin.py ops section, jobs analysis v2).
import type { JobAnalysis } from "@/types/api";

// ---- versioned score (scoring_v2) ----
export interface ScoreDimension {
  name: string;
  label: string;
  status: "known" | "unknown";
  score: number | null;
  base_weight: number;
  weight: number;
  weighted: number;
  evidence: string;
  method: string;
}
export type Eligibility = "pass" | "fail" | "unknown";
export interface AnalysisV2 extends JobAnalysis {
  score_version?: string | null;
  dimensions?: ScoreDimension[];
  eligibility?: Eligibility | null;
  unknown_dimensions?: string[];
  disclaimer?: string | null;
}

// ---- interview prep & practice ----
export interface PrepQuestion { id: string; kind: string; competency: string; question: string; why: string }
export interface ReferenceLink { source: string; label: string; url: string }
export interface Insight { id: number; source: string; url: string | null; question: string | null; note: string | null; created_at: string }
export interface InterviewPrep {
  job: { user_job_id: number; title: string; company: string };
  questions: PrepQuestion[];
  reference_links: ReferenceLink[];
  reference_note: string;
  insights: Insight[];
}
export interface AnswerFeedback { question_id: string; score: number; out_of: number; notes: string[]; method: string }
export interface PracticeAnswer { answer: string; self_rating: number | null; at: string }
export interface Practice {
  id: number;
  title: string;
  user_job_id: number | null;
  application_id: number | null;
  status: string;
  questions: PrepQuestion[];
  answers: Record<string, PracticeAnswer> | null;
  feedback: AnswerFeedback[] | null;
  created_at: string;
  completed_at: string | null;
}

// ---- rejections, feedback, funnel ----
export interface RejectionReason { key: string; label: string }
export interface RejectionResult { id: number; stage: string | null; rejection_reason: string | null; rejection_reason_known: boolean | null }
export interface Funnel {
  counts: Record<"prepared" | "opened" | "pending" | "applied" | "screening" | "assessment" | "interview" | "offer" | "rejected", number>;
  conversion: { application_to_screening: number | null; application_to_interview: number | null; interview_to_offer: number | null };
  rejection_reasons: { reason: string; label: string; count: number }[];
  rejections_with_known_reason: number;
  by_resume_version: { version: string; applications: number; interviews: number }[];
  note: string | null;
}

// ---- AI mentor ----
export interface Diagnosis {
  rule: string;
  title: string;
  observations: string[];
  diagnosis: string;
  confidence: "high" | "medium" | "low" | string;
  limitations: string;
  suggested_actions?: string[];
}
export interface MentorAction {
  id: number;
  title: string;
  reason: string;
  priority: "high" | "medium" | "low" | string;
  due_on: string | null;
  source: string;
  completed_at: string | null;
  created_at: string;
}
export interface Reflection { id: number; week_start: string; outcome: string; obstacle: string; next_action: string; mood: number | null; created_at: string }
export interface MentorPlan {
  diagnoses: Diagnosis[];
  actions: MentorAction[];
  next_step: { kind: string; label: string; link: string; reason: string } | null;
  reflection_due: boolean;
  last_reflection: Reflection | null;
  method: string;
  note: string;
}

// ---- human mentoring ----
export const SCOPES = ["profile", "funnel", "gaps", "actions", "applications"] as const;
export type Scope = (typeof SCOPES)[number];
export const scopeLabels: Record<Scope, { label: string; hint: string }> = {
  profile: { label: "Profile", hint: "How complete your profile is" },
  funnel: { label: "Results so far", hint: "Your application funnel and the AI mentor's diagnoses" },
  gaps: { label: "Skill gaps", hint: "Skills jobs ask for that you're still building" },
  actions: { label: "Action plan", hint: "Your open actions; the mentor can also suggest new ones" },
  applications: { label: "Applications", hint: "Job title, company and stage of each application" },
};
export interface MentorAssignment {
  id: number;
  mentor_name: string;
  mentor_email: string;
  status: "active" | "revoked" | string;
  scopes: Scope[];
  consented_at: string | null;
  revoked_at: string | null;
}
export interface MentorSession {
  id: number;
  scheduled_at: string | null;
  duration_minutes: number;
  meeting_url: string | null;
  agenda: string | null;
  status: "scheduled" | "done" | "cancelled" | string;
  summary: string | null;
  assignment_id?: number;
}
export interface MentorNote { id: number; body: string; visibility: "shared" | "private"; by_me: boolean; created_at: string }
export interface MyMentors { mentors: MentorAssignment[]; sessions: MentorSession[] }
export interface CandidateListItem { assignment_id: number; candidate_name: string; scopes: Scope[]; since: string | null }
export interface Gap {
  id: number; skill: string; severity: string; explanation: string; next_action: string; evidence_state: string; status: string;
  job_count: number; rejection_count: number;
}
export interface CandidateSummary {
  assignment_id: number;
  candidate_name: string | null;
  scopes: Scope[];
  profile_completeness?: { percent: number; missing: string[] };
  funnel?: Funnel;
  diagnoses?: Diagnosis[];
  gaps?: Gap[];
  actions?: MentorAction[];
  applications?: { id: number; title: string; company: string; status: string; stage: string | null }[];
  notes: MentorNote[];
  sessions: MentorSession[];
}
export interface ConsentRequired { message: string; consent: string; text: string }

// ---- admin operations ----
export interface BackgroundJob {
  name: string;
  schedule: string;
  owner: string;
  description: string;
  retries: number;
  last_status: string | null;
  last_started_at: string | null;
  last_error: string | null;
  last_ok_at: string | null;
  last_details: unknown;
  last_trigger?: string | null;
  runs_with?: string | null;
}
export interface JobRunResult { id: number; name: string; status: string; attempts: number; details: unknown; error: string | null }
export interface ProductMetrics {
  days: number;
  events: Record<string, { count: number; users: number; failed: number }>;
  north_star: Record<string, number | null>;
  ai_costs: { purpose: string; calls: number; cost_usd: number }[];
  feedback: { topic: string; responses: number; average_rating: number | null }[];
  note: string;
}
export interface SystemStatus {
  disk: { used_percent: number; free_gb: number; level: "ok" | "warning" | "high" | "critical" | string };
  backup: { status: string; at?: string; label?: string; folder?: string; size_kb?: number; encrypted?: boolean; offhost?: string; error?: string; note?: string };
}
