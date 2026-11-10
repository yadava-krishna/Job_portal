import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import type {
  CareerGoals, CareerSnapshot, CompleteResult, Consent, ConsentRequired, Country, CountryFit, EvidenceType, GapDetail,
  GapsResponse, LearningSession, SessionsResponse, Skill, SkillsResponse, VisaRoute,
} from "./types";

export const ck = {
  snapshot: ["career-snapshot"] as const,
  goals: ["career-goals"] as const,
  consents: ["consents"] as const,
  skills: ["skills"] as const,
  gaps: ["gaps"] as const,
  gap: (id: number) => ["gap", id] as const,
  sessions: ["learning-sessions"] as const,
  countries: ["countries"] as const,
  routes: (country: string) => ["visa-routes", country] as const,
  fit: (country: string) => ["country-fit", country] as const,
};

/** HTTP status and body of a failed request (works on axios errors and plain test doubles). */
function responseOf(err: unknown): { status?: number; detail?: unknown } {
  const r = (err as { response?: { status?: number; data?: { detail?: unknown } } } | null)?.response;
  return { status: r?.status, detail: r?.data?.detail };
}

/** If the request was refused because a permission is missing, the permission and its explanation. */
export function consentRequired(err: unknown): ConsentRequired | null {
  const { status, detail } = responseOf(err);
  if (status !== 403 || !detail || typeof detail !== "object") return null;
  const d = detail as Partial<ConsentRequired>;
  return d.consent ? { message: d.message ?? "This needs your permission first.", consent: d.consent, text: d.text ?? "" } : null;
}

/** The backend's own explanation (e.g. the 409 "needs evidence" message), else the generic error text. */
export function backendMessage(err: unknown): string {
  const { detail } = responseOf(err);
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") return (detail as { message: string }).message;
  return errorMessage(err);
}

export const useCareerSnapshot = () =>
  useQuery({ queryKey: ck.snapshot, queryFn: async () => (await api.get<CareerSnapshot>("/career/snapshot")).data });

// ---------- goals & consent ----------

export const useCareerGoals = () => useQuery({ queryKey: ck.goals, queryFn: async () => (await api.get<CareerGoals>("/career-goals")).data });

export function useSaveCareerGoals() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: CareerGoals) => (await api.put<CareerGoals>("/career-goals", body)).data,
    onSuccess: (data) => {
      qc.setQueryData(ck.goals, data);
      // Goals change eligibility and match scores.
      ["career-snapshot", "jobs", "job", "summary", "gaps", "country-fit"].forEach((k) => void qc.invalidateQueries({ queryKey: [k] }));
    },
  });
}

export const useConsents = () => useQuery({ queryKey: ck.consents, queryFn: async () => (await api.get<Consent[]>("/consents")).data });

export function useSetConsent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ kind, granted }: { kind: string; granted: boolean }) => (await api.put<Consent[]>(`/consents/${kind}`, { granted })).data,
    onSuccess: (data) => qc.setQueryData(ck.consents, data),
  });
}

export function useSendFeedback() {
  return useMutation({
    mutationFn: async (body: { topic: string; rating: number | null; comment: string | null }) =>
      (await api.post<{ id: number; topic: string }>("/feedback", body)).data,
  });
}

// ---------- skills & evidence ----------

export const useSkills = () => useQuery({ queryKey: ck.skills, queryFn: async () => (await api.get<SkillsResponse>("/skills")).data });

function useInvalidateCareer() {
  const qc = useQueryClient();
  return () => ["skills", "gaps", "gap", "career-snapshot"].forEach((k) => void qc.invalidateQueries({ queryKey: [k] }));
}

export function useAddSkill() {
  const invalidate = useInvalidateCareer();
  return useMutation({
    mutationFn: async (body: { name: string; proficiency: string | null; years: number | null }) => (await api.post<Skill>("/skills", body)).data,
    onSuccess: invalidate,
  });
}

export function useSetSkillState() {
  const invalidate = useInvalidateCareer();
  return useMutation({
    mutationFn: async ({ id, state }: { id: number; state: string }) => (await api.put<Skill>(`/skills/${id}/state`, { state })).data,
    onSuccess: invalidate,
  });
}

export function useDeleteSkill() {
  const invalidate = useInvalidateCareer();
  return useMutation({ mutationFn: async (id: number) => { await api.delete(`/skills/${id}`); }, onSuccess: invalidate });
}

export interface EvidenceInput {
  evidence_type: EvidenceType;
  title: string;
  url: string | null;
  description: string | null;
  occurred_on: string | null;
}

export function useAddEvidence() {
  const invalidate = useInvalidateCareer();
  return useMutation({
    mutationFn: async ({ skillId, body }: { skillId: number; body: EvidenceInput }) => (await api.post<Skill>(`/skills/${skillId}/evidence`, body)).data,
    onSuccess: invalidate,
  });
}

export function useDeleteEvidence() {
  const invalidate = useInvalidateCareer();
  return useMutation({ mutationFn: async (id: number) => { await api.delete(`/evidence/${id}`); }, onSuccess: invalidate });
}

// ---------- gaps & learning ----------

export const useGaps = () => useQuery({ queryKey: ck.gaps, queryFn: async () => (await api.get<GapsResponse>("/gaps")).data });

export function useRefreshGaps() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.get<GapsResponse>("/gaps", { params: { refresh: true } })).data,
    onSuccess: (data) => {
      qc.setQueryData(ck.gaps, data);
      void qc.invalidateQueries({ queryKey: ck.snapshot });
    },
  });
}

export const useGapDetail = (id: number | null) =>
  useQuery({ queryKey: ck.gap(id ?? 0), queryFn: async () => (await api.get<GapDetail>(`/gaps/${id}`)).data, enabled: id != null });

export const useLearningSessions = () =>
  useQuery({ queryKey: ck.sessions, queryFn: async () => (await api.get<SessionsResponse>("/learning-sessions")).data });

/** Put an updated session into the cached list without a refetch. */
function useStoreSession() {
  const qc = useQueryClient();
  return (s: LearningSession) =>
    qc.setQueryData<SessionsResponse>(ck.sessions, (old) => {
      if (!old) return old;
      const others = old.sessions.filter((x) => x.id !== s.id).map((x) => (s.status === "active" && x.status === "active" ? { ...x, status: "paused" } : x));
      return { ...old, sessions: [s, ...others].sort((a, b) => b.started_at.localeCompare(a.started_at)) };
    });
}

export function useStartSession() {
  const store = useStoreSession();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { resource_id?: number | null; gap_id?: number | null; skill?: string | null }) =>
      (await api.post<LearningSession>("/learning-sessions", body)).data,
    onSuccess: (s) => {
      store(s);
      void qc.invalidateQueries({ queryKey: ck.sessions });
      void qc.invalidateQueries({ queryKey: ck.gaps });
    },
  });
}

export function useSessionAction() {
  const store = useStoreSession();
  return useMutation({
    mutationFn: async ({ id, action, active }: { id: number; action: "heartbeat" | "pause" | "resume"; active?: boolean }) =>
      (await api.post<LearningSession>(`/learning-sessions/${id}/${action}`, action === "heartbeat" ? { active: !!active } : undefined)).data,
    onSuccess: store,
  });
}

export interface CompleteInput {
  notes: string | null;
  knowledge_check: Record<string, string>;
  helpful: boolean | null;
  evidence_url: string | null;
  evidence_title: string | null;
}

export function useCompleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: CompleteInput }) =>
      (await api.post<CompleteResult>(`/learning-sessions/${id}/complete`, body)).data,
    onSuccess: () => ["learning-sessions", "skills", "gaps", "gap", "career-snapshot"].forEach((k) => void qc.invalidateQueries({ queryKey: [k] })),
  });
}

// ---------- international ----------

export const useCountries = () => useQuery({ queryKey: ck.countries, queryFn: async () => (await api.get<Country[]>("/countries")).data, staleTime: 5 * 60_000 });

export const useCountryFit = (country: string | null) =>
  useQuery({
    queryKey: ck.fit(country ?? ""),
    queryFn: async () => (await api.get<CountryFit>("/country-fit", { params: { country } })).data,
    enabled: !!country,
  });

/** Routes with the user's watch flags (country-fit does not include them). */
export const useVisaRoutes = (country: string | null) =>
  useQuery({
    queryKey: ck.routes(country ?? ""),
    queryFn: async () => (await api.get<VisaRoute[]>("/visa-routes", { params: { country } })).data,
    enabled: !!country,
  });

export function useWatchRoute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, watching }: { id: number; watching: boolean }) =>
      (await api.put<{ route_id: number; watching: boolean }>(`/visa-routes/${id}/watch`, { watching })).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["visa-routes"] }),
  });
}
