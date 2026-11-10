import axios from "axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  BackgroundJob, CandidateListItem, CandidateSummary, ConsentRequired, Funnel, InterviewPrep, JobRunResult, MentorAction, MentorNote,
  MentorPlan, MentorSession, MyMentors, Practice, ProductMetrics, Reflection, RejectionReason, RejectionResult, SystemStatus,
} from "./types";

export const gk = {
  prep: (id: number) => ["interview-prep", id] as const,
  practices: ["interview-practice"] as const,
  practice: (id: number) => ["interview-practice", id] as const,
  reasons: ["rejection-reasons"] as const,
  funnel: ["funnel"] as const,
  plan: ["mentor-plan"] as const,
  reflections: ["mentor-reflections"] as const,
  mentors: ["my-mentors"] as const,
  notes: (id: number) => ["mentor-notes", id] as const,
  candidates: ["mentor-candidates"] as const,
  candidate: (id: number) => ["mentor-candidate", id] as const,
  adminJobs: ["admin-jobs"] as const,
  productMetrics: (days: number) => ["admin-product-metrics", days] as const,
  system: ["admin-system"] as const,
};

/** The 403 body the backend sends when an action needs a consent the user hasn't given yet. */
export function consentRequired(err: unknown): ConsentRequired | null {
  if (!axios.isAxiosError(err) || err.response?.status !== 403) return null;
  const d = (err.response.data as { detail?: unknown } | undefined)?.detail;
  if (d && typeof d === "object" && "consent" in d && "text" in d) return d as ConsentRequired;
  return null;
}

// ---- interview prep & practice ----
export const useInterviewPrep = (userJobId: number | null) =>
  useQuery({ queryKey: gk.prep(userJobId ?? 0), queryFn: async () => (await api.get<InterviewPrep>(`/interview-prep/${userJobId}`)).data, enabled: userJobId != null });
export const usePractices = () => useQuery({ queryKey: gk.practices, queryFn: async () => (await api.get<Practice[]>("/interview-practice")).data });
export const usePractice = (id: number | null) =>
  useQuery({ queryKey: gk.practice(id ?? 0), queryFn: async () => (await api.get<Practice>(`/interview-practice/${id}`)).data, enabled: id != null });

export function useStartPractice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (userJobId: number) => (await api.post<Practice>("/interview-practice", { user_job_id: userJobId })).data,
    onSuccess: (p) => { qc.setQueryData(gk.practice(p.id), p); void qc.invalidateQueries({ queryKey: gk.practices, exact: true }); },
  });
}

export function useSaveAnswer(practiceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { question_id: string; answer: string; self_rating: number | null }) =>
      (await api.post<Practice>(`/interview-practice/${practiceId}/answers`, body)).data,
    onSuccess: (p) => { qc.setQueryData(gk.practice(p.id), p); void qc.invalidateQueries({ queryKey: gk.practices, exact: true }); },
  });
}

export function useAddInsight(userJobId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { company: string; role: string; source: string; url: string | null; question: string | null; note: string | null }) =>
      (await api.post<{ id: number; source: string }>("/interview-insights", body)).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: gk.prep(userJobId) }),
  });
}

// ---- rejections, interview feedback, funnel ----
export const useRejectionReasons = () =>
  useQuery({ queryKey: gk.reasons, queryFn: async () => (await api.get<RejectionReason[]>("/rejection-reasons")).data, staleTime: 60 * 60_000 });
export function useReasonLabels(): Record<string, string> {
  const reasons = useRejectionReasons();
  return Object.fromEntries((reasons.data ?? []).map((r) => [r.key, r.label]));
}
export const useFunnel = () => useQuery({ queryKey: gk.funnel, queryFn: async () => (await api.get<Funnel>("/analytics/funnel")).data });

export function useRecordRejection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: number; reason: string; detail: string | null; known: boolean }) =>
      (await api.post<RejectionResult>(`/applications/${id}/rejection`, body)).data,
    onSuccess: () => Promise.all(["applications", "application", "funnel", "summary"].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

export interface InterviewFeedbackInput {
  interview_type: string | null; outcome: string | null; topics: string[]; strengths: string | null; weaknesses: string | null;
  candidate_feedback: string | null;
}
export function useInterviewFeedback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: InterviewFeedbackInput & { id: number }) => (await api.post(`/interviews/${id}/feedback`, body)).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: gk.funnel }),
  });
}

// ---- AI mentor ----
export const useMentorPlan = () => useQuery({ queryKey: gk.plan, queryFn: async () => (await api.get<MentorPlan>("/mentor/plan")).data });
export const useReflections = () => useQuery({ queryKey: gk.reflections, queryFn: async () => (await api.get<Reflection[]>("/mentor/reflections")).data });

function useInvalidatePlan() {
  const qc = useQueryClient();
  return () => Promise.all([gk.plan, gk.reflections].map((k) => qc.invalidateQueries({ queryKey: k })));
}

export function useReflect() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: async (body: { outcome: string; obstacle: string; next_action: string; mood: number | null }) =>
      (await api.post<Reflection>("/mentor/reflection", body)).data,
    onSuccess: () => void invalidate(),
  });
}

export function useAddAction() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: async (body: { title: string; reason?: string; priority: string; due_on: string | null }) =>
      (await api.post<MentorAction>("/mentor/actions", body)).data,
    onSuccess: () => void invalidate(),
  });
}

export function usePatchAction() {
  const invalidate = useInvalidatePlan();
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: number; done?: boolean; dismissed?: boolean; due_on?: string }) =>
      (await api.patch<MentorAction>(`/mentor/actions/${id}`, body)).data,
    onSuccess: () => void invalidate(),
  });
}

// ---- human mentoring: candidate side ----
export const useMyMentors = () => useQuery({ queryKey: gk.mentors, queryFn: async () => (await api.get<MyMentors>("/mentoring/mentors")).data });
export const useMentorNotes = (assignmentId: number | null) =>
  useQuery({ queryKey: gk.notes(assignmentId ?? 0), queryFn: async () => (await api.get<MentorNote[]>(`/mentoring/mentors/${assignmentId}/notes`)).data, enabled: assignmentId != null });

export function useInviteMentor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { mentor_email: string; scopes: string[] }) => (await api.post("/mentoring/mentors", body)).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: gk.mentors }),
  });
}

export function useGrantConsent() {
  return useMutation({ mutationFn: async (kind: string) => (await api.put(`/consents/${kind}`, { granted: true })).data });
}

export function useRevokeMentor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (assignmentId: number) => { await api.delete(`/mentoring/mentors/${assignmentId}`); },
    onSuccess: () => void qc.invalidateQueries({ queryKey: gk.mentors }),
  });
}

export function useCandidateNote(assignmentId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: string) => (await api.post(`/mentoring/mentors/${assignmentId}/notes`, { body, visibility: "shared" })).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: gk.notes(assignmentId) }),
  });
}

export interface SessionInput { scheduled_at: string | null; duration_minutes: number; meeting_url: string | null; agenda: string | null }
export function useRequestSession(assignmentId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: SessionInput) => (await api.post<MentorSession>(`/mentoring/mentors/${assignmentId}/sessions`, body)).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: gk.mentors }),
  });
}

export function usePatchSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: number; status?: string; summary?: string; agenda?: string }) =>
      (await api.patch<MentorSession>(`/mentoring/sessions/${id}`, body)).data,
    onSuccess: () => Promise.all([gk.mentors, ["mentor-candidate"]].map((k) => qc.invalidateQueries({ queryKey: k }))),
  });
}

// ---- human mentoring: mentor side ----
export const useCandidates = (enabled = true) =>
  useQuery({ queryKey: gk.candidates, queryFn: async () => (await api.get<CandidateListItem[]>("/mentor-workspace/candidates")).data, enabled });
export const useCandidate = (assignmentId: number | null) =>
  useQuery({
    queryKey: gk.candidate(assignmentId ?? 0),
    queryFn: async () => (await api.get<CandidateSummary>(`/mentor-workspace/candidates/${assignmentId}`)).data,
    enabled: assignmentId != null,
  });

export function useMentorWorkspaceAction(assignmentId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (a: { kind: "note"; body: string; visibility: "shared" | "private" } | ({ kind: "session" } & SessionInput)
      | { kind: "action"; title: string; reason: string; priority: string; due_on: string | null }) => {
      const { kind, ...body } = a;
      const path = kind === "note" ? "notes" : kind === "session" ? "sessions" : "actions";
      return (await api.post(`/mentor-workspace/candidates/${assignmentId}/${path}`, body)).data;
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: gk.candidate(assignmentId) }),
  });
}

// ---- admin operations ----
export const useAdminJobs = () => useQuery({ queryKey: gk.adminJobs, queryFn: async () => (await api.get<BackgroundJob[]>("/admin/jobs")).data });
export const useProductMetrics = (days: number) =>
  useQuery({ queryKey: gk.productMetrics(days), queryFn: async () => (await api.get<ProductMetrics>("/admin/product-metrics", { params: { days } })).data });
export const useSystemStatus = () => useQuery({ queryKey: gk.system, queryFn: async () => (await api.get<SystemStatus>("/admin/system")).data });

export function useRunJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (name: string) => (await api.post<JobRunResult>(`/admin/jobs/${encodeURIComponent(name)}/run`, undefined, { timeout: 600_000 })).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: gk.adminJobs }),
  });
}
