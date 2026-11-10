// Plain-language labels and small formatters shared by the career screens.
import type { EvidenceType, SkillState } from "./types";

export const SKILL_STATES: { key: SkillState; label: string }[] = [
  { key: "aware", label: "Aware" },
  { key: "learning", label: "Learning" },
  { key: "practising", label: "Practising" },
  { key: "project_evidence", label: "Project evidence" },
  { key: "professional_experience", label: "Professional experience" },
  { key: "interview_ready", label: "Interview ready" },
];

export const stateLabel = (s: string | null | undefined) => SKILL_STATES.find((x) => x.key === s)?.label ?? "Not started";

/** Plain wording for the profile items the completeness check can report missing. */
export const missingLabels: Record<string, string> = {
  name: "your name",
  contact: "contact details",
  headline: "a headline",
  summary: "a short summary",
  skills: "at least 5 skills",
  experience_or_projects: "work experience or projects",
  education: "education",
  target_roles: "the roles you want",
  locations: "preferred locations",
  search_mode: "where you want to work",
};

export function humanizeMissing(text: string): string {
  return Object.entries(missingLabels).reduce((t, [k, v]) => t.replace(new RegExp(`\\b${k}\\b`, "g"), v), text);
}

export const stageLabels: Record<string, string> = {
  starting: "Getting started",
  exploring: "Exploring jobs",
  applying: "Applying",
  interviewing: "Interviewing",
};

export const EVIDENCE_TYPES: { value: EvidenceType; label: string }[] = [
  { value: "course", label: "Course" },
  { value: "certificate", label: "Certificate" },
  { value: "project", label: "Project" },
  { value: "employment", label: "Work experience (a job)" },
  { value: "publication", label: "Publication or article" },
  { value: "assessment", label: "Test or assessment" },
  { value: "practice", label: "Practice exercises" },
  { value: "other", label: "Other" },
];
export const evidenceLabel = (t: string) => EVIDENCE_TYPES.find((e) => e.value === t)?.label ?? t;

export const isHttpsLink = (v: string) => /^https:\/\/\S+\.\S+/.test(v.trim());

export function minutes(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 60) return `${n} min`;
  const h = Math.floor(n / 60);
  return `${h} h${n % 60 ? ` ${n % 60} min` : ""}`;
}

export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}
