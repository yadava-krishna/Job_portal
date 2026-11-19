// Talking to the JobPilot Smart Apply browser extension from the web app (its manifest's externally_connectable lists
// this site). Two messages only: "ping" (installed? connected?) and "apply" (open one job's form and fill it). The
// extension never sends profile data back, and it never submits: the user reviews and submits in its panel.

export const SMART_APPLY_ID = "ehpfmhhbnijflgagkpdbhiakldmgedgp";
const FILLABLE_HOSTS = ["job-boards.greenhouse.io", "boards.greenhouse.io", "job-boards.eu.greenhouse.io", "boards.eu.greenhouse.io",
  "jobs.lever.co", "jobs.eu.lever.co", "jobs.ashbyhq.com"];

export interface SmartApplyStatus { version: string; connected: boolean }
type Reply<T> = { ok: boolean; data?: T; error?: string };
type Runtime = { sendMessage: (id: string, msg: unknown, cb: (r: unknown) => void) => void; lastError?: unknown };

function runtime(): Runtime | null {
  const rt = (globalThis as { chrome?: { runtime?: Runtime } }).chrome?.runtime;
  return rt && typeof rt.sendMessage === "function" ? rt : null;
}

function send<T>(msg: unknown, timeoutMs = 1500): Promise<Reply<T> | null> {
  const rt = runtime();
  if (!rt) return Promise.resolve(null);  // not Chrome/Edge/Brave, or no extension that lists this site
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeoutMs);
    try {
      rt.sendMessage(SMART_APPLY_ID, msg, (r) => {
        clearTimeout(timer);
        void rt.lastError;  // "receiving end does not exist" = not installed
        resolve((r as Reply<T> | undefined) ?? null);
      });
    } catch {
      clearTimeout(timer);
      resolve(null);
    }
  });
}

/** null when Smart Apply is not installed (or is an older version that does not answer). */
export async function smartApplyStatus(): Promise<SmartApplyStatus | null> {
  const r = await send<SmartApplyStatus>({ type: "ping" });
  return r?.ok && r.data ? r.data : null;
}

/**
 * Opens the form in a new tab; the extension fills it there. Throws with a plain message if it cannot.
 * applicationId lets the extension load this application's prepared package (chosen resume, answers you typed here).
 */
export async function smartApplyStart(url: string, userJobId: number, applicationId?: number | null): Promise<void> {
  const msg = applicationId != null ? { type: "apply", url, userJobId, applicationId } : { type: "apply", url, userJobId };
  const r = await send<{ tabId: number }>(msg, 5000);
  if (!r) throw new Error("Smart Apply didn't answer. Check it's installed and switched on in chrome://extensions.");
  if (!r.ok) throw new Error(r.error || "Smart Apply couldn't open this form.");
}

/** Greenhouse, Lever and Ashby forms can be filled in one click; other sites are applied to by hand. */
export function canSmartApply(url: string | null | undefined): boolean {
  if (!url) return false;
  try {
    const u = new URL(url);
    return u.protocol === "https:" && FILLABLE_HOSTS.includes(u.hostname);
  } catch {
    return false;
  }
}
