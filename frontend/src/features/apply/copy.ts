// Plain-language words for the Apply Workspace: where an answer came from, what to type, what the next step is called.
import { toast } from "sonner";
import type { ApplyAction, PackageAnswer, PackageDestination } from "@/types/api";

/** Where a prepared answer came from, in the user's words. */
export function sourceLabel(source: string | null | undefined): string | null {
  if (!source) return null;
  if (source === "memory") return "Remembered answer";
  if (source === "settings" || source.startsWith("verified_facts")) return "From your Settings";
  if (source === "profile") return "From your profile";
  if (source === "resume") return "From your resume dates";
  if (source === "this_application") return "You answered this for this application";
  if (source.startsWith("answer_bank")) return "From your saved answers";
  if (source.startsWith("saved_for_one_job")) return "Saved for another job";
  return source.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Where a remembered answer was last confirmed. */
export function memorySourceLabel(source: string | null | undefined): string {
  switch (source) {
    case "apply_workspace": return "Saved while applying";
    case "settings": return "Saved in Settings";
    case "extension": return "Saved from Smart Apply";
    case "user_confirmed": return "You confirmed it";
    default: return source ? source.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase()) : "You confirmed it";
  }
}

/** An example of what to type for a value type, so the server's validation rarely has to say no. */
export function answerHint(a: Pick<PackageAnswer, "value_type" | "unit">): string | undefined {
  switch (a.value_type) {
    case "days": return "e.g. 30 days or Immediate";
    case "money": return "e.g. 12 LPA or USD 90,000 a year";
    case "number": return a.unit === "years" ? "e.g. 4 or 2.5" : "e.g. 4";
    case "date_text": return "e.g. 1 Dec 2026 or Immediately";
    case "url": return "e.g. https://…";
    case "email": return "e.g. you@example.com";
    case "phone": return "e.g. +91 98765 43210";
    default: return undefined;
  }
}

export function isLongText(a: Pick<PackageAnswer, "field_type" | "value_type" | "question">): boolean {
  return a.field_type === "textarea" || (a.value_type === "text" && a.question.length > 90);
}

/** The host of a URL ("boards.greenhouse.io"), or null. */
export function hostOf(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

/** The label of the primary button for the next step. */
export function actionLabel(action: ApplyAction, dest: PackageDestination | undefined, smartReady: boolean): string {
  switch (action) {
    case "review_autofill": return smartReady ? "Review and autofill" : "Continue on employer site";
    case "continue_employer": return "Continue on employer site";
    case "open_native": return `Open on ${dest?.platform_name || "the job site"}`;
    case "resume": return "Resume application";
    case "resolve_uncertain": return "Check what happened";
    case "done": return "Done";
  }
}

export const GROUP_LABELS: Record<string, string> = {
  personal: "Personal", professional: "Work and pay", preferences: "Preferences", eligibility: "Eligibility", links: "Links", other: "Other questions",
};
export const GROUP_ORDER = ["personal", "professional", "preferences", "eligibility", "links", "other"];

export function copyText(text: string, what = "Copied") {
  if (!navigator.clipboard?.writeText) { toast.error("Copying isn't available in this browser. Select the text instead."); return; }
  navigator.clipboard.writeText(text).then(() => toast.success(what), () => toast.error("Couldn't copy. Select the text instead."));
}
