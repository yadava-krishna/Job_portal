// "Clip to JobPilot" bookmarklet.
//
// Runs only when the user clicks it, in the user's own browser tab, on the job page they are
// already viewing (logged in or not). It reads that single page and opens the portal with an
// import form prefilled for review. It never crawls, never runs in the background, and no
// cookies or credentials ever leave the browser. Data travels in the URL fragment (#...), which
// browsers do not send to any server.

import bookmarkletSource from "./clipper.bookmarklet.js?raw";

export function portalUrl(): string {
  return window.location.origin + window.location.pathname;
}

export function bookmarkletHref(portal = portalUrl()): string {
  const fn = bookmarkletSource.replace(/^\s*\/\/.*$/gm, "").trim();
  return "javascript:" + encodeURIComponent(`(${fn})(${JSON.stringify(portal)});void 0`);
}

export interface ClippedJob {
  url?: string;
  title?: string;
  company?: string;
  location?: string;
  description?: string;
  posted_date?: string;
  posted_date_source?: "user" | "page";
  salary?: string;
  experience?: string;
}

export function decodeClip(param: string | null): ClippedJob | null {
  if (!param) return null;
  try {
    const b64 = param.replace(/-/g, "+").replace(/_/g, "/");
    const json = decodeURIComponent(escape(atob(b64)));
    const data = JSON.parse(json) as ClippedJob;
    return typeof data === "object" && data ? data : null;
  } catch {
    return null;
  }
}

const CLIP_KEY = "jobpilot.pendingClip";
export function stashClip(job: ClippedJob) {
  try {
    sessionStorage.setItem(CLIP_KEY, JSON.stringify(job));
  } catch {
    /* ignore */
  }
}
export function takeClip(): ClippedJob | null {
  try {
    const v = sessionStorage.getItem(CLIP_KEY);
    sessionStorage.removeItem(CLIP_KEY);
    return v ? (JSON.parse(v) as ClippedJob) : null;
  } catch {
    return null;
  }
}
