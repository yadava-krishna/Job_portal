// Plain-language names and descriptions for resume templates and fonts. The server's own wording leans on recruiting
// jargon ("ATS", "parseable"); this is what people see instead. Keys match the server's template and font keys; anything
// unknown falls back to the server's text, so a new template still shows up.
import type { StudioTemplate, TemplateKey } from "./api";

const TEMPLATES: Record<TemplateKey, { name: string; description: string }> = {
  ats_simple: {
    name: "Clean & Simple",
    description: "One column, plain headings, black text. The easiest layout for job-site application forms to read, so it's the safest pick for applying online.",
  },
  modern_professional: {
    name: "Modern",
    description: "Section titles down the left side with a blue accent. Looks great as a PDF you email or print. For online application forms, Clean & Simple is safer.",
  },
  technical: {
    name: "Tech & Data",
    description: "Skills and projects up top, with skills grouped in rows. Built for engineering, data and analytics roles.",
  },
  finance: {
    name: "Experienced",
    description: "A classic serif look with your work history first, then achievements and qualifications. For long careers.",
  },
  graduate: {
    name: "Fresher / Graduate",
    description: "Education and projects first, fits on one page. For students and first jobs.",
  },
  executive: {
    name: "Executive",
    description: "Name centred, elegant serif, key wins before work history. For senior and leadership roles.",
  },
  international: {
    name: "International (A4)",
    description: "A4 page with a line for your work permit and willingness to relocate. For jobs in another country.",
  },
};

const FONTS: Record<string, string> = {
  liberation_sans: "Arial-style (clean, modern)",
  lato: "Lato (friendly, rounded)",
  liberation_serif: "Times-style (classic)",
  palatino: "Palatino-style (elegant)",
  dejavu_sans: "DejaVu Sans (handles most languages)",
};

export function templateName(key: TemplateKey | null | undefined, fallback = ""): string {
  return (key && TEMPLATES[key]?.name) || fallback;
}

export function templateDescription(t: Pick<StudioTemplate, "key" | "description">): string {
  return TEMPLATES[t.key]?.description ?? t.description;
}

export function fontLabel(key: string, fallback: string): string {
  return FONTS[key] ?? fallback;
}

/** What the "safe for online forms" badge means, for tooltips and help text. */
export const FORM_FRIENDLY_HELP = "Job sites run your resume through software that reads it automatically (often called an ATS). This layout is easy for that software to read.";
export const PRINT_FIRST_HELP = "Looks great to a person, but the software job sites use to read resumes can misread this layout. Use a form-friendly template when applying online.";
