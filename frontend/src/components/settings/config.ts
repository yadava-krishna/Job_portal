import type { LucideIcon } from "lucide-react";
import { Bell, Cable, KeyRound, ListChecks, Mail, Plug, Puzzle, Shield, SlidersHorizontal, Target, UserRound } from "lucide-react";

export interface SettingsSectionDef {
  /** The `?tab=` value. Deep links (the extension, in-app links, ⌘K) rely on these keys: don't rename them. */
  key: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

export interface SettingsGroupDef {
  label: string;
  sections: SettingsSectionDef[];
}

export const SETTINGS_GROUPS: SettingsGroupDef[] = [
  {
    label: "My profile",
    sections: [
      { key: "profile", label: "Resume & profile", icon: UserRound,
        description: "Your resume and the profile JobPilot matches jobs and answers forms with." },
      { key: "career-goals", label: "Career goals", icon: Target,
        description: "Where you want to work and at what level. This decides which jobs you're eligible for." },
    ],
  },
  {
    label: "Job discovery",
    sections: [
      { key: "preferences", label: "Job preferences", icon: SlidersHorizontal,
        description: "The roles, places and pay you're after, and how strict matching should be." },
      { key: "platforms", label: "Platforms", icon: Plug,
        description: "Which job sites JobPilot looks at, and how jobs from each one reach you." },
      { key: "portals", label: "Portal Connections", icon: Cable,
        description: "What JobPilot can and can't do with LinkedIn, Naukri and Indeed, and a checklist to sharpen your profile there." },
    ],
  },
  {
    label: "Smart Apply",
    sections: [
      { key: "extension", label: "Browser extension", icon: Puzzle,
        description: "Connect the Smart Apply extension so employer forms fill themselves from your profile." },
      { key: "answers", label: "Verified answers", icon: ListChecks,
        description: "Answers to screening questions, written once by you or remembered while applying, and reused on applications." },
    ],
  },
  {
    label: "Notifications",
    sections: [
      { key: "email", label: "Alert emails", icon: Mail,
        description: "Let JobPilot read your own job-alert emails to find jobs and spot sent applications." },
      { key: "notifications", label: "Notifications", icon: Bell,
        description: "Which alerts show up under the bell, and how new-job alerts are filtered." },
    ],
  },
  {
    label: "Privacy & account",
    sections: [
      { key: "privacy", label: "Privacy & consent", icon: Shield,
        description: "Optional features that use your data. Each one is off until you turn it on." },
      { key: "account", label: "Account & connection", icon: KeyRound,
        description: "Sign out, export or delete your data, and check the server connection." },
    ],
  },
];

export const SETTINGS_SECTIONS = SETTINGS_GROUPS.flatMap((g) => g.sections.map((s) => ({ ...s, group: g.label })));
export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

export const DEFAULT_SECTION = "profile";

/** The section for a `?tab=` value; unknown or missing values fall back to the profile. */
export function sectionFor(tab: string | null): SettingsSection {
  return SETTINGS_SECTIONS.find((s) => s.key === tab) ?? SETTINGS_SECTIONS.find((s) => s.key === DEFAULT_SECTION)!;
}
