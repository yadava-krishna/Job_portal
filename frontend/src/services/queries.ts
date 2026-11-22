import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Analytics,
  ActivityItem,
  Application,
  Company,
  DirectoryCompany,
  NotificationList,
  SavedSearch,
  SavedSearchInput,
  SourcesOverview,
  ApplicationDetail,
  AnswerCatalogueEntry,
  ApplyOptions,
  HandoffOut,
  MemoryAnswer,
  AnswerConflict,
  PackageOut,
  WorkspaceAnswerInput,
  ExtensionDevice,
  PairingCode,
  DashboardSummary,
  DiscoveryRun,
  EditableProfile,
  EmailIntegration,
  ImportResult,
  JobAnalysis,
  JobDetail,
  JobList,
  OnboardingStatus,
  PlatformInfo,
  Preferences,
  ProfileResponse,
  ResumeInfo,
  Report,
  SearchLink,
  Stage,
  VerifiedFacts,
} from "@/types/api";

export const qk = {
  profile: ["profile"] as const,
  onboarding: ["onboarding"] as const,
  preferences: ["preferences"] as const,
  platforms: ["platforms"] as const,
  email: ["email"] as const,
  jobs: (params: object) => ["jobs", params] as const,
  job: (id: number) => ["job", id] as const,
  analysis: (id: number) => ["analysis", id] as const,
  applications: (status?: string[]) => ["applications", status ?? []] as const,
  application: (id: number) => ["application", id] as const,
  applyPackage: (id: number) => ["apply-package", id] as const,
  answerMemory: (reveal: boolean) => ["answer-memory", reveal] as const,
  reports: ["reports"] as const,
  summary: ["summary"] as const,
  activity: ["activity"] as const,
  analytics: (days: number) => ["analytics", days] as const,
  runs: ["runs"] as const,
  links: ["search-links"] as const,
  searches: ["saved-searches"] as const,
  watchlist: ["watchlist"] as const,
  suggested: ["suggested-companies"] as const,
  directory: (q: string, ats: string) => ["company-directory", q, ats] as const,
  notifications: ["notifications"] as const,
  sources: ["discovery-sources"] as const,
};

export const useProfile = () => useQuery({ queryKey: qk.profile, queryFn: async () => (await api.get<ProfileResponse>("/profile")).data });
export const useOnboarding = (enabled = true) =>
  useQuery({ queryKey: qk.onboarding, queryFn: async () => (await api.get<OnboardingStatus>("/onboarding")).data, enabled });
export const usePreferences = () => useQuery({ queryKey: qk.preferences, queryFn: async () => (await api.get<Preferences>("/preferences")).data });
export const usePlatforms = () => useQuery({ queryKey: qk.platforms, queryFn: async () => (await api.get<PlatformInfo[]>("/platforms")).data });
export const useEmailIntegration = () =>
  useQuery({ queryKey: qk.email, queryFn: async () => (await api.get<EmailIntegration>("/integrations/email")).data });

export interface JobQuery {
  view?: "feed" | "saved" | "dismissed" | "applied" | "all";
  q?: string;
  platform?: string[];
  posted?: "any" | "today" | "24h" | "3d" | "7d" | "30d" | "range";
  include_estimated?: boolean;
  confidence?: ("verified" | "estimated" | "unknown")[];
  industry?: string;
  employment_type?: string[];
  company?: string;
  saved_search_id?: number;
  include_closed?: boolean;
  /** false: list every listing; default groups the same company + title onto one card. */
  group_similar?: boolean;
  include_unknown_dates?: boolean;
  date_from?: string;
  date_to?: string;
  domain?: string;
  location?: string;
  work_mode?: string[];
  experience?: number;
  min_score?: number;
  skill?: string;
  salary_min_lpa?: number;
  application_status?: string[];
  country?: string;
  seniority?: string;
  sponsorship?: ("verified" | "inferred" | "none" | "unknown")[];
  eligibility?: ("pass" | "fail" | "unknown")[];
  sort?: "score" | "posted" | "discovered";
  /** jobs: everything except internships; internships: only internships. */
  kind?: "all" | "jobs" | "internships";
  page?: number;
  page_size?: number;
}

function toParams(q: JobQuery) {
  const p = new URLSearchParams();
  Object.entries(q).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) return;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)));
    else p.set(k, String(v));
  });
  return p;
}

export const useJobs = (q: JobQuery) =>
  useQuery({ queryKey: qk.jobs(q), queryFn: async () => (await api.get<JobList>("/jobs", { params: toParams(q) })).data, placeholderData: keepPreviousData });
export const useJob = (id: number | null) =>
  useQuery({ queryKey: qk.job(id ?? 0), queryFn: async () => (await api.get<JobDetail>(`/jobs/${id}`)).data, enabled: id != null });
export const useAnalysis = (id: number | null) =>
  useQuery({ queryKey: qk.analysis(id ?? 0), queryFn: async () => (await api.get<JobAnalysis>(`/jobs/${id}/analysis`)).data, enabled: id != null });
export const useSearchLinks = () => useQuery({ queryKey: qk.links, queryFn: async () => (await api.get<SearchLink[]>("/jobs/search-links")).data });
export const useRuns = () => useQuery({ queryKey: qk.runs, queryFn: async () => (await api.get<DiscoveryRun[]>("/jobs/runs")).data });

export const useApplications = (status?: string[]) =>
  useQuery({
    queryKey: qk.applications(status),
    queryFn: async () => (await api.get<Application[]>("/applications", { params: toParams({ status } as never) })).data,
  });
export const useApplication = (id: number | null) =>
  useQuery({ queryKey: qk.application(id ?? 0), queryFn: async () => (await api.get<ApplicationDetail>(`/applications/${id}`)).data, enabled: id != null });

export const useReports = () => useQuery({ queryKey: qk.reports, queryFn: async () => (await api.get<Report[]>("/reports")).data });
export const useSummary = () => useQuery({ queryKey: qk.summary, queryFn: async () => (await api.get<DashboardSummary>("/dashboard/summary")).data });
export const useActivity = () => useQuery({ queryKey: qk.activity, queryFn: async () => (await api.get<ActivityItem[]>("/dashboard/activity")).data });
export const useAnalytics = (days = 30) =>
  useQuery({ queryKey: qk.analytics(days), queryFn: async () => (await api.get<Analytics>("/dashboard/analytics", { params: { days } })).data });

/** Invalidate everything that depends on the job feed / applications. */
export function useInvalidateWork() {
  const qc = useQueryClient();
  return () =>
    Promise.all(["jobs", "job", "analysis", "applications", "application", "summary", "activity", "analytics", "runs",
      "discovery-sources", "saved-searches", "notifications", "watchlist", "funnel", "snapshot"].map((k) =>
      qc.invalidateQueries({ queryKey: [k] }),
    ));
}

export function useJobAction() {
  const invalidate = useInvalidateWork();
  return useMutation({
    mutationFn: async ({ id, action }: { id: number; action: "save" | "unsave" | "dismiss" | "restore" | "rescore" }) => {
      if (action === "unsave") return (await api.delete<JobDetail>(`/jobs/${id}/save`)).data;
      return (await api.post<JobDetail>(`/jobs/${id}/${action}`)).data;
    },
    onSuccess: () => invalidate(),
  });
}

export function useImportJob() {
  const invalidate = useInvalidateWork();
  return useMutation({
    mutationFn: async (body: Record<string, unknown>) => (await api.post<ImportResult>("/jobs/import", body)).data,
    onSuccess: () => invalidate(),
  });
}

export function useImportFile() {
  const invalidate = useInvalidateWork();
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return (await api.post<ImportResult>("/jobs/import-file", fd)).data;
    },
    onSuccess: () => invalidate(),
  });
}

export function useAddDescription() {
  const invalidate = useInvalidateWork();
  return useMutation({
    mutationFn: async ({ id, description }: { id: number; description: string }) =>
      (await api.put<JobDetail>(`/jobs/${id}/description`, { description })).data,
    onSuccess: () => invalidate(),
  });
}

export function useApplicationAction() {
  const invalidate = useInvalidateWork();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (
      args:
        | { kind: "prepare"; userJobId: number; includeCoverLetter?: boolean }
        | { kind: "open"; id: number }
        | { kind: "confirm"; id: number; submitted: boolean; reference_id?: string; confirmation_text?: string }
        | { kind: "pending"; id: number }
        | { kind: "fail" | "withdraw"; id: number; reason?: string }
        | { kind: "stage"; id: number; stage: Stage; note?: string },
    ): Promise<ApplicationDetail> => {
      switch (args.kind) {
        case "prepare":
          return (await api.post<ApplicationDetail>("/applications/prepare", { user_job_id: args.userJobId, include_cover_letter: args.includeCoverLetter })).data;
        case "open":
          return (await api.post<{ application: ApplicationDetail }>(`/applications/${args.id}/open`)).data.application;
        case "confirm":
          return (await api.post<ApplicationDetail>(`/applications/${args.id}/confirm`, {
            submitted: args.submitted, reference_id: args.reference_id || null, confirmation_text: args.confirmation_text || null,
          })).data;
        case "pending":
          return (await api.post<ApplicationDetail>(`/applications/${args.id}/pending`)).data;
        case "fail":
        case "withdraw":
          return (await api.post<ApplicationDetail>(`/applications/${args.id}/${args.kind}`, { reason: args.reason || null })).data;
        case "stage":
          return (await api.post<ApplicationDetail>(`/applications/${args.id}/stage`, { stage: args.stage, note: args.note || null })).data;
      }
    },
    onSuccess: (app) => {
      qc.setQueryData(qk.application(app.id), app);
      void invalidate();
    },
  });
}

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (profile: EditableProfile) => (await api.put<ProfileResponse>("/profile", profile)).data,
    onSuccess: (data) => {
      qc.setQueryData(qk.profile, data);
      void qc.invalidateQueries({ queryKey: qk.onboarding });
      // A profile change can make saved answers and prepared applications out of date.
      void qc.invalidateQueries({ queryKey: ["answer-conflicts"] });
      void qc.invalidateQueries({ queryKey: ["apply-package"] });
      setTimeout(() => void qc.invalidateQueries({ queryKey: ["jobs"] }), 1500);
    },
  });
}

export function useUploadResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return (await api.post<ProfileResponse>("/profile/resume", fd, { timeout: 120_000 })).data;
    },
    onSuccess: (data) => {
      qc.setQueryData(qk.profile, data);
      void qc.invalidateQueries({ queryKey: qk.onboarding });
    },
  });
}

export function useSaveFacts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (facts: VerifiedFacts) => (await api.put<ProfileResponse>("/profile/verified-facts", facts)).data,
    onSuccess: (data) => qc.setQueryData(qk.profile, data),
  });
}

export interface RescoreStatus { requested_at: string | null; rescored_at: string | null; pending: boolean }

/** Match-score refresh after a preference or profile change. Polls only while a refresh is pending. */
export const useRescoreStatus = (watch: boolean) =>
  useQuery({
    queryKey: ["rescore-status"],
    queryFn: async () => (await api.get<RescoreStatus>("/preferences/rescore")).data,
    enabled: watch,
    staleTime: 0,
    refetchInterval: (q) => (q.state.data?.pending ? 1500 : false),
  });

export function useRetryRescore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<RescoreStatus>("/preferences/rescore")).data,
    onSuccess: (data) => qc.setQueryData(["rescore-status"], data),
  });
}

export function useSavePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (prefs: Preferences) => (await api.put<Preferences>("/preferences", prefs)).data,
    onSuccess: (data) => {
      qc.setQueryData(qk.preferences, data);
      void qc.invalidateQueries({ queryKey: qk.onboarding });
      void qc.invalidateQueries({ queryKey: qk.links });
      void qc.invalidateQueries({ queryKey: ["rescore-status"] });
      setTimeout(() => void qc.invalidateQueries({ queryKey: ["jobs"] }), 1500);
    },
  });
}

export function useSavePlatforms() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (platforms: { platform: string; enabled: boolean; discovery_sources: string[] }[]) =>
      (await api.put<PlatformInfo[]>("/platforms/preferences", { platforms })).data,
    onSuccess: (data) => {
      qc.setQueryData(qk.platforms, data);
      void qc.invalidateQueries({ queryKey: qk.onboarding });
      void qc.invalidateQueries({ queryKey: qk.links });
    },
  });
}

export function useSaveEmail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Record<string, unknown>) => (await api.put<EmailIntegration>("/integrations/email", body)).data,
    onSuccess: (data) => qc.setQueryData(qk.email, data),
  });
}

export function useDiscover() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<DiscoveryRun>("/jobs/discover", {})).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.runs }),
  });
}

export async function pollRun(id: number, onUpdate: (r: DiscoveryRun) => void, timeoutMs = 180_000): Promise<DiscoveryRun> {
  const started = Date.now();
  for (;;) {
    const run = (await api.get<DiscoveryRun>(`/jobs/runs/${id}`)).data;
    onUpdate(run);
    if (run.status !== "running" || Date.now() - started > timeoutMs) return run;
    await new Promise((r) => setTimeout(r, 2000));
  }
}

export function useGenerateReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (kind: "daily" | "history") =>
      (await api.post<Report>(kind === "daily" ? "/reports/daily" : "/reports/history", undefined, { timeout: 120_000 })).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.reports }),
  });
}

// ---- saved searches, companies, notifications --------------------------------------------------------

export const useSavedSearches = () =>
  useQuery({ queryKey: qk.searches, queryFn: async () => (await api.get<SavedSearch[]>("/saved-searches")).data });

export function useSaveSearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id?: number; body: SavedSearchInput }) =>
      (id ? await api.put<SavedSearch>(`/saved-searches/${id}`, body) : await api.post<SavedSearch>("/saved-searches", body)).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.searches }),
  });
}

export function useDeleteSearch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => { await api.delete(`/saved-searches/${id}`); },
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.searches }),
  });
}

export function useRunSearch() {
  return useMutation({ mutationFn: async (id: number) => (await api.post<DiscoveryRun>(`/saved-searches/${id}/run`)).data });
}

export const useWatchlist = () => useQuery({ queryKey: qk.watchlist, queryFn: async () => (await api.get<Company[]>("/companies/watchlist")).data });
export const useSuggestedCompanies = () =>
  useQuery({ queryKey: qk.suggested, queryFn: async () => (await api.get<DirectoryCompany[]>("/companies/suggested")).data });
export const useCompanyDirectory = (q: string, ats: string) =>
  useQuery({
    queryKey: qk.directory(q, ats),
    queryFn: async () => (await api.get<DirectoryCompany[]>("/companies/directory", { params: { q, ats: ats || undefined, limit: 25 } })).data,
    enabled: q.trim().length >= 2,
    placeholderData: keepPreviousData,
  });

function useInvalidateCompanies() {
  const qc = useQueryClient();
  return () => Promise.all([qk.watchlist, qk.suggested, ["company-directory"]].map((k) => qc.invalidateQueries({ queryKey: k })));
}

export function useWatchCompany() {
  const invalidate = useInvalidateCompanies();
  return useMutation({
    mutationFn: async (body: { url?: string; ats?: string; token?: string; name?: string }) =>
      (await api.post<Company>("/companies/watchlist", body, { timeout: 60_000 })).data,
    onSuccess: () => void invalidate(),
  });
}

export function useWatchMany() {
  const invalidate = useInvalidateCompanies();
  return useMutation({
    mutationFn: async (companies: { ats: string; token: string }[]) =>
      (await api.post<Company[]>("/companies/watchlist/bulk", { companies }, { timeout: 120_000 })).data,
    onSuccess: () => void invalidate(),
  });
}

export function useUnwatchCompany() {
  const invalidate = useInvalidateCompanies();
  return useMutation({
    mutationFn: async (id: number) => { await api.delete(`/companies/watchlist/${id}`); },
    onSuccess: () => void invalidate(),
  });
}

export const useNotifications = () =>
  useQuery({
    queryKey: qk.notifications,
    queryFn: async () => (await api.get<NotificationList>("/notifications", { params: { limit: 20 } })).data,
    refetchInterval: 60_000,
  });

export function useMarkNotifications() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id?: number) => { await api.post(id ? `/notifications/${id}/read` : "/notifications/read-all"); },
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.notifications }),
  });
}

export const useSourceHealth = () =>
  useQuery({ queryKey: qk.sources, queryFn: async () => (await api.get<SourcesOverview>("/discovery/sources")).data });

// ---- browser extension ---------------------------------------------------------------------

export const useApplyOptions = (applicationId?: number | null) =>
  useQuery({
    queryKey: ["apply-options", applicationId ?? 0],
    queryFn: async () => (await api.get<ApplyOptions>(`/applications/${applicationId}/apply-options`)).data,
    enabled: applicationId != null,
    staleTime: 5 * 60_000,
  });

export const useExtensionDevices = () =>
  useQuery({ queryKey: ["extension-devices"], queryFn: async () => (await api.get<ExtensionDevice[]>("/extension/devices")).data });

export function useCreatePairingCode() {
  return useMutation({ mutationFn: async () => (await api.post<PairingCode>("/extension/pairing-codes")).data });
}

export function useDisconnectDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => { await api.delete(`/extension/devices/${id}`); },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["extension-devices"] }),
  });
}

export function useUpdateTracking() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, notes, follow_up_at }: { id: number; notes?: string | null; follow_up_at?: string | null }) =>
      (await api.put<ApplicationDetail>(`/applications/${id}/tracking`, { notes, follow_up_at })).data,
    onSuccess: (a) => { qc.setQueryData(qk.application(a.id), a); void qc.invalidateQueries({ queryKey: ["applications"] }); },
  });
}

// ---- resume versions, notification preferences ----------------------------------------------

export const useResumes = () => useQuery({ queryKey: ["resumes"], queryFn: async () => (await api.get<ResumeInfo[]>("/profile/resumes")).data });

export function useResumeAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (a: { kind: "default"; id: number } | { kind: "delete"; id: number } | { kind: "rename"; id: number; name: string } | { kind: "upload"; file: File; makeDefault: boolean }) => {
      if (a.kind !== "upload") {
        if (a.kind === "rename") return (await api.put(`/profile/resumes/${a.id}`, { name: a.name })).data;
        if (a.kind === "default") return (await api.post(`/profile/resumes/${a.id}/default`)).data;
        return (await api.delete(`/profile/resumes/${a.id}`)).data;
      }
      const fd = new FormData();
      fd.append("file", a.file);
      return (await api.post<ProfileResponse>("/profile/resume", fd, { params: { make_default: a.makeDefault }, timeout: 120_000 })).data;
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["resumes"] }); void qc.invalidateQueries({ queryKey: qk.profile }); },
  });
}

export const NOTIFICATION_KINDS = ["new_match", "follow_up_due", "interview_upcoming", "application_incomplete", "listing_closed", "discovery_failed"] as const;
export type NotificationKind = (typeof NOTIFICATION_KINDS)[number];
export interface NotificationPrefs {
  new_matches: boolean; delivery: "immediate" | "daily_digest"; min_score: number | null; sources: string[]; email: "off";
  /** On/off per alert type. Missing when the server predates per-type switches. */
  kinds?: Record<NotificationKind, boolean>;
}
export type NotificationPrefsPatch = Partial<Omit<NotificationPrefs, "kinds">> & { kinds?: Partial<Record<NotificationKind, boolean>> };
const notificationPrefsKey = ["notification-prefs"];
export const useNotificationPrefs = () =>
  useQuery({ queryKey: notificationPrefsKey, queryFn: async () => (await api.get<NotificationPrefs>("/notifications/preferences")).data });
/** Changes only the fields sent, so the alert-type switches and the new-job settings can be saved separately. */
export function useSaveNotificationPrefs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (p: NotificationPrefsPatch) => (await api.patch<NotificationPrefs>("/notifications/preferences", p)).data,
    // Take from the reply only what this request changed: replies to quick successive saves can arrive out of order.
    onSuccess: (d, sent) => qc.setQueryData<NotificationPrefs>(notificationPrefsKey, (old) => {
      if (!old) return d;
      const next: NotificationPrefs = { ...old, kinds: old.kinds && d.kinds ? { ...old.kinds } : d.kinds ?? old.kinds };
      for (const k of Object.keys(sent) as (keyof NotificationPrefsPatch)[]) if (k !== "kinds") Object.assign(next, { [k]: d[k] });
      for (const k of Object.keys(sent.kinds ?? {}) as NotificationKind[]) if (next.kinds && d.kinds) next.kinds[k] = d.kinds[k];
      if ("new_matches" in sent || sent.kinds?.new_match !== undefined) {  // one switch, two names
        next.new_matches = d.new_matches;
        if (next.kinds && d.kinds) next.kinds.new_match = d.kinds.new_match;
      }
      return next;
    }),
  });
}

// ---- Apply Workspace: the prepared package and answer memory -------------------------------------

/** The prepared package for one application (destination, resume, answers, readiness, next step). */
export const useApplyPackage = (applicationId: number | null | undefined) =>
  useQuery({
    queryKey: qk.applyPackage(applicationId ?? 0),
    queryFn: async () => (await api.get<PackageOut>(`/applications/${applicationId}/package`)).data,
    enabled: applicationId != null,
    // Smart Apply changes the application from another tab (filled, interrupted, confirmed): never trust a cached copy.
    staleTime: 0,
    refetchOnMount: "always",
    retry: (n, err) => n < 1 && (err as { response?: { status?: number } })?.response?.status !== 404,
  });

export type WorkspaceChange =
  | { kind: "resume"; id: number; choice: { kind: "upload" | "studio"; id: number; format?: "pdf" | "docx" } }
  | { kind: "answers"; id: number; items: WorkspaceAnswerInput[] }
  | { kind: "destination"; id: number; url: string }
  | { kind: "clear-destination"; id: number }
  | { kind: "refresh"; id: number }
  | { kind: "handoff"; id: number; smart: boolean };

/** Changes made in the Apply Workspace. Each returns the rebuilt package, which replaces the cached one. */
export function useApplyWorkspace() {
  const qc = useQueryClient();
  const invalidate = useInvalidateWork();
  return useMutation({
    mutationFn: async (c: WorkspaceChange): Promise<PackageOut | HandoffOut> => {
      const base = `/applications/${c.id}`;
      switch (c.kind) {
        case "resume": return (await api.put<PackageOut>(`${base}/resume`, c.choice)).data;
        case "answers": return (await api.post<PackageOut>(`${base}/answers`, { items: c.items })).data;
        case "destination": return (await api.post<PackageOut>(`${base}/destination`, { url: c.url })).data;
        case "clear-destination": return (await api.delete<PackageOut>(`${base}/destination`)).data;
        case "refresh": return (await api.get<PackageOut>(`${base}/package?refresh=true`)).data;
        case "handoff": return (await api.post<HandoffOut>(`${base}/handoff?smart=${c.smart}`)).data;
      }
    },
    onSuccess: (out, c) => {
      if (!out?.application || !out.package) return;
      qc.setQueryData(qk.applyPackage(c.id), { application: out.application, package: out.package });
      qc.setQueryData(qk.application(c.id), out.application);
      if (c.kind === "handoff") void invalidate();
      else void qc.invalidateQueries({ queryKey: ["applications"] });
      if (c.kind === "answers" && (out as PackageOut).saved?.length) void qc.invalidateQueries({ queryKey: ["answer-memory"] });
    },
  });
}

/** Remembered answers. `reveal` decrypts private ones (pay, work authorisation): fetched only on request, not kept around. */
export const useAnswerMemory = (reveal = false, enabled = true) =>
  useQuery({
    queryKey: qk.answerMemory(reveal),
    queryFn: async () => (await api.get<MemoryAnswer[]>("/answers/memory", { params: reveal ? { reveal: true } : undefined })).data,
    enabled,
    ...(reveal ? { staleTime: 0, gcTime: 30_000 } : {}),
  });

/** Saved answers that disagree with the confirmed profile (refreshed whenever answers or the profile change). */
export const useAnswerConflicts = (enabled = true) =>
  useQuery({ queryKey: ["answer-conflicts"], queryFn: async () => (await api.get<AnswerConflict[]>("/answers/conflicts")).data, enabled });

export const useAnswerCatalogue = () =>
  useQuery({ queryKey: ["answer-catalogue"], queryFn: async () => (await api.get<AnswerCatalogueEntry[]>("/answers/catalogue")).data, staleTime: 3_600_000 });

function useInvalidateMemory() {
  const qc = useQueryClient();
  return () => Promise.all([["answer-memory"], ["answer-conflicts"], qk.profile, ["apply-package"]].map((k) => qc.invalidateQueries({ queryKey: k })));
}

export function useSaveMemoryAnswer() {
  const invalidate = useInvalidateMemory();
  return useMutation({
    mutationFn: async (body: { question?: string; answer: string; key?: string; scope_ref?: string }) => (await api.put<MemoryAnswer>("/answers/memory", body)).data,
    onSuccess: () => void invalidate(),
  });
}

export function useDeleteMemoryAnswer() {
  const invalidate = useInvalidateMemory();
  return useMutation({
    mutationFn: async ({ key, scopeRef }: { key: string; scopeRef?: string }) => {
      await api.delete(`/answers/memory/${encodeURIComponent(key)}`, { params: scopeRef ? { scope_ref: scopeRef } : undefined });
    },
    onSuccess: () => void invalidate(),
  });
}
