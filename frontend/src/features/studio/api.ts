import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { api } from "@/lib/api";

// ---------------- types (mirror backend/services/studio_service.py) ----------------

export type TemplateKey = "ats_simple" | "modern_professional" | "technical" | "finance" | "graduate" | "international";
export type VersionStatus = "draft" | "locked" | "archived";
export type Density = "compact" | "normal" | "relaxed";
export type PageSize = "A4" | "LETTER";
export type SectionType = "header" | "summary" | "experience" | "projects" | "education" | "skills" | "certifications"
  | "publications" | "achievements" | "custom";
export type BulletSource = "profile" | "user" | "suggestion";

export interface StudioTemplate {
  key: TemplateKey;
  name: string;
  category: string;
  ats_safe: boolean;
  columns: number;
  description: string;
  max_pages: number;
  supports_docx: boolean;
}

export interface StudioSettings {
  font_size?: number;
  density?: Density;
  page_size?: PageSize;
  mobility_line?: string;
}

export interface ContactContent { name?: string | null; headline?: string | null; email?: string | null; phone?: string | null; location?: string | null; links?: string[] }
export interface TextContent { text?: string | null }
export interface EntryContent { title?: string | null; organization?: string | null; start?: string | null; end?: string | null; current?: boolean; location?: string | null; link?: string | null; detail?: string | null }
export interface SkillGroupContent { label?: string | null; items?: string[] }

export interface Bullet {
  id?: number;
  /** Client-only stable key (server ids change on every save). Never sent. */
  _k?: string;
  text: string;
  evidence_refs: string[];
  source: BulletSource;
  approved: boolean;
}

interface BlockBase { id?: number; _k?: string; source_profile_ref: string | null; visible: boolean; bullets: Bullet[] }
export type Block =
  | (BlockBase & { type: "contact"; content: ContactContent })
  | (BlockBase & { type: "text"; content: TextContent })
  | (BlockBase & { type: "entry"; content: EntryContent })
  | (BlockBase & { type: "skill_group"; content: SkillGroupContent });
export type BlockType = Block["type"];

export interface Section {
  id?: number;
  _k?: string;
  type: SectionType;
  heading: string;
  visible: boolean;
  blocks: Block[];
}

export interface VersionSummary {
  id: number;
  name: string;
  template_key: TemplateKey;
  template_name: string;
  ats_safe: boolean;
  status: VersionStatus;
  locked_at: string | null;
  revision: number;
  settings: StudioSettings;
  target_job_id: number | null;
  parent_id: number | null;
  created_at: string;
  updated_at: string;
  checksum: string | null;
}
export interface Version extends VersionSummary { sections: Section[] }

export interface ExportResult {
  id: number;
  format: "pdf" | "docx";
  checksum: string;
  file_sha256: string;
  size_bytes?: number;
  page_count: number | null;
  created_at?: string;
  note: string | null;
  download_url: string;
}

export type IssueLevel = "error" | "warning" | "suggestion" | "info";
export interface FeedbackIssue {
  level: IssueLevel;
  code: string;
  message: string;
  /** Feedback uses the section *type*; block/bullet are indexes in that section. */
  where: { section: string; block?: number; bullet?: number } | null;
}
export interface Feedback {
  resume_version_id: number;
  job_id: number | null;
  pages: number | null;
  issues: FeedbackIssue[];
  readiness: number;
  ats_safe_template: boolean;
  note: string;
}

export interface Suggestion {
  id: string;
  kind: "rewrite" | "reorder" | "add_skill";
  /** Suggestions use section/block/bullet *indexes* of the saved document. */
  where: { section: number; block: number; bullet?: number };
  before: string | null;
  after: string | null;
  order?: number[];
  skill?: string;
  evidence: "supported" | "unknown";
  reason: string;
}

export interface AttachResult {
  id?: number;
  resume_version_id: number;
  resume_export_id: number | null;
  resume_checksum: string | null;
  resume_used: string | null;
}

export interface SavePayload {
  revision: number;
  name?: string;
  template_key?: TemplateKey;
  settings?: StudioSettings;
  sections?: Section[];
}

// ---------------- query hooks ----------------

export const studioKeys = {
  templates: ["studio", "templates"] as const,
  versions: ["studio", "versions"] as const,
  version: (id: number) => ["studio", "version", id] as const,
  feedback: (id: number, jobId: number | null) => ["studio", "feedback", id, jobId] as const,
  suggestions: (id: number, jobId: number | null) => ["studio", "suggestions", id, jobId] as const,
};

export const useStudioTemplates = () =>
  useQuery({ queryKey: studioKeys.templates, queryFn: async () => (await api.get<StudioTemplate[]>("/studio/templates")).data, staleTime: 3_600_000 });

export const useStudioVersions = (enabled = true) =>
  useQuery({ queryKey: studioKeys.versions, queryFn: async () => (await api.get<VersionSummary[]>("/studio/versions")).data, enabled });

export const useStudioVersion = (id: number | null) =>
  useQuery({
    queryKey: studioKeys.version(id ?? 0),
    queryFn: async () => (await api.get<Version>(`/studio/versions/${id}`)).data,
    enabled: id != null,
    // The editor owns the working copy; refetching underneath it would discard typing.
    refetchOnWindowFocus: false,
  });

export const useStudioFeedback = (id: number, jobId: number | null, enabled: boolean) =>
  useQuery({
    queryKey: studioKeys.feedback(id, jobId),
    queryFn: async () => (await api.get<Feedback>(`/studio/versions/${id}/feedback`, { params: jobId ? { user_job_id: jobId } : {} })).data,
    enabled,
    refetchOnWindowFocus: false,
  });

export const useStudioSuggestions = (id: number, jobId: number | null, enabled: boolean) =>
  useQuery({
    queryKey: studioKeys.suggestions(id, jobId),
    queryFn: async () => (await api.get<Suggestion[]>(`/studio/versions/${id}/suggestions`, { params: jobId ? { user_job_id: jobId } : {} })).data,
    enabled,
    refetchOnWindowFocus: false,
  });

export function useCreateVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { name: string; template_key: TemplateKey; target_user_job_id?: number | null }) =>
      (await api.post<Version>("/studio/versions", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: studioKeys.versions }),
  });
}

export function useCloneVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...body }: { id: number; name?: string; target_user_job_id?: number | null }) =>
      (await api.post<Version>(`/studio/versions/${id}/clone`, body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: studioKeys.versions }),
  });
}

export function useDeleteVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => { await api.delete(`/studio/versions/${id}`); },
    onSuccess: () => qc.invalidateQueries({ queryKey: studioKeys.versions }),
  });
}

export function useAttachResumeVersion() {
  return useMutation({
    mutationFn: async ({ applicationId, versionId }: { applicationId: number; versionId: number }) =>
      (await api.put<AttachResult>(`/applications/${applicationId}/resume-version`, { resume_version_id: versionId })).data,
  });
}

// ---------------- plain calls ----------------

export async function saveVersion(id: number, body: SavePayload): Promise<Version> {
  const payload = { ...body, sections: body.sections ? stripKeys(body.sections) : undefined };
  return (await api.put<Version>(`/studio/versions/${id}`, payload)).data;
}

export async function exportVersion(id: number, format: "pdf" | "docx"): Promise<ExportResult> {
  return (await api.post<ExportResult>(`/studio/versions/${id}/export`, { format }, { timeout: 120_000 })).data;
}

export async function fetchPreview(id: number): Promise<{ blob: Blob; pages: number | null }> {
  const res = await api.get(`/studio/versions/${id}/preview.pdf`, { responseType: "blob", timeout: 120_000 });
  const raw = Number(res.headers?.["x-page-count"]);
  return { blob: new Blob([res.data as Blob], { type: "application/pdf" }), pages: Number.isFinite(raw) && raw > 0 ? raw : null };
}

/** Classify a save failure from the backend's 409 detail. */
export function saveConflict(err: unknown): "stale" | "locked" | null {
  if (!axios.isAxiosError(err) || err.response?.status !== 409) return null;
  const d = (err.response.data as { detail?: unknown } | undefined)?.detail;
  if (d && typeof d === "object" && (d as { locked?: boolean }).locked) return "locked";
  return "stale";
}

// ---------------- document helpers (pure) ----------------

let keySeq = 0;
export const newKey = () => `k${++keySeq}`;

export function withKeys(sections: Section[]): Section[] {
  return sections.map((s) => ({
    ...s, _k: s._k ?? newKey(),
    blocks: s.blocks.map((b) => ({ ...b, _k: b._k ?? newKey(), bullets: b.bullets.map((u) => ({ ...u, _k: u._k ?? newKey() })) }) as Block),
  }));
}

export function stripKeys(sections: Section[]): Section[] {
  return sections.map(({ _k: _s, id: _sid, ...s }) => ({
    ...s,
    blocks: s.blocks.map(({ _k: _b, id: _bid, ...b }) => ({ ...b, bullets: b.bullets.map(({ _k: _u, id: _uid, ...u }) => u) }) as Block),
  }));
}

export function move<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length || from === to) return list;
  const next = [...list];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

/**
 * Apply an accepted suggestion to the local document. Returns the new sections, or an error message when the document
 * changed since the suggestion was made (so the user is never surprised by an edit landing in the wrong place).
 */
export function applySuggestion(sections: Section[], s: Suggestion): { sections: Section[] } | { error: string } {
  const stale = { error: "That part of the resume changed since the suggestion was made. Refresh suggestions." };
  const sec = sections[s.where.section];
  if (!sec) return stale;
  const replaceSection = (ns: Section) => sections.map((x, i) => (i === s.where.section ? ns : x));
  if (s.kind === "add_skill") {
    const skill = s.skill ?? s.after;
    if (!skill) return stale;
    const bi = sec.blocks.findIndex((b) => b.type === "skill_group");
    if (bi < 0) return { error: "Add a skill group to the Skills section first." };
    const blocks = sec.blocks.map((b, i) => {
      if (i !== bi || b.type !== "skill_group") return b;
      const items = b.content.items ?? [];
      if (items.some((x) => x.toLowerCase() === skill.toLowerCase())) return b;
      return { ...b, content: { ...b.content, items: [...items, skill] } };
    });
    return { sections: replaceSection({ ...sec, blocks }) };
  }
  const blk = sec.blocks[s.where.block];
  if (!blk) return stale;
  if (s.kind === "rewrite") {
    const ui = s.where.bullet ?? -1;
    const bullet = blk.bullets[ui];
    if (!bullet || s.after == null || (s.before != null && bullet.text !== s.before)) return stale;
    const bullets = blk.bullets.map((u, i) => (i === ui ? { ...u, text: s.after as string, source: "suggestion" as const } : u));
    return { sections: replaceSection({ ...sec, blocks: sec.blocks.map((b, i) => (i === s.where.block ? ({ ...b, bullets } as Block) : b)) }) };
  }
  // reorder
  const order = s.order ?? [];
  if (order.length !== blk.bullets.length || new Set(order).size !== order.length || order.some((i) => !blk.bullets[i])) return stale;
  const bullets = order.map((i) => blk.bullets[i]);
  return { sections: replaceSection({ ...sec, blocks: sec.blocks.map((b, i) => (i === s.where.block ? ({ ...b, bullets } as Block) : b)) }) };
}
