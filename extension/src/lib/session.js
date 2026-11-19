// Small, pure decisions the service worker makes about a Smart Apply session (no chrome.*, no network, no storage),
// kept here so they can be unit-tested on their own.

/** States in which closing the tab leaves the application half-done: recorded as "interrupted" (a pause). */
export const INTERRUPTIBLE = ["form_opened", "filling", "needs_information", "ready_for_review", "reviewed", "submission_authorized"];

/** What to record when the session's tab is closed: {state, message}, or null (nothing to record). */
export function afterTabClosed(state) {
  if (INTERRUPTIBLE.includes(state)) return { state: "interrupted", message: "Tab closed before submitting." };
  if (state === "submission_pending") return { state: "submission_uncertain", message: "Tab closed right after submitting." };
  return null;
}

/** A resume choice {kind: "upload"|"studio", id, format: "pdf"|"docx", name?} if `r` is a usable one, else null. */
export function validResume(r) {
  if (!r || typeof r !== "object" || !["upload", "studio"].includes(r.kind)) return null;
  const id = Number(r.id);
  if (!Number.isInteger(id) || id <= 0) return null;
  return { kind: r.kind, id, format: r.format === "docx" ? "docx" : "pdf", name: typeof r.name === "string" ? r.name.slice(0, 200) : null };
}

/**
 * Which resume to attach: the one the user picked in the popup (now, or earlier for this session), else the one chosen
 * for this application in JobPilot (its package), else null (the server's default: the active upload).
 * Returns {choice, from: "popup"|"package"|"default"}.
 */
export function resumeChoice(explicit, session) {
  const picked = validResume(explicit) || validResume(session?.resume);
  if (picked) return { choice: picked, from: "popup" };
  const pkg = validResume(session?.packageResume);
  if (pkg) return { choice: pkg, from: "package" };
  return { choice: null, from: "default" };
}

/** The optional application id the JobPilot web app hands over with a job, or null. */
export function handoffApplicationId(value) {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? n : null;
}

/** Which kind of confirmation signal was seen. Unknown kinds are dropped (the server then treats it as unspecified). */
export const SIGNAL_KINDS = ["adapter", "url", "text"];
export const signalKind = (k) => (SIGNAL_KINDS.includes(k) ? k : undefined);

/** The answers the user ticked "save for next time", trimmed to what the server accepts. */
export function learnItems(items) {
  return (Array.isArray(items) ? items : []).slice(0, 30)
    .map((i) => ({ question: String(i?.question ?? "").replace(/\s+/g, " ").trim().slice(0, 500), answer: String(i?.answer ?? "").trim().slice(0, 2000) }))
    .filter((i) => i.question.length >= 2 && i.answer.length >= 1);
}
