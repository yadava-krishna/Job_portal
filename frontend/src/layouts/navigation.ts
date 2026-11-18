// The app's map: four areas (Home, Jobs, Applications, Career), a footer group, and every place the command menu can
// jump to. Routes are unchanged, so bookmarks, alert-email links and the extension's deep links keep working; only how
// they are grouped and found changes.
import type { LucideIcon } from "lucide-react";
import {
  Bell, Bookmark, Briefcase, Compass, FileSpreadsheet, FileText, Globe, Home, KeyRound, ListChecks, MessagesSquare,
  Plug, Radar, Search, Settings, Shield, Sparkles, Target, UserRound, Users,
} from "lucide-react";

export interface NavLeaf { to: string; label: string; icon: LucideIcon; match?: string[] }
export interface NavArea { key: string; label: string; icon: LucideIcon; to: string; children: NavLeaf[] }

export const areas: NavArea[] = [
  { key: "home", label: "Home", icon: Home, to: "/dashboard", children: [] },
  {
    key: "jobs", label: "Jobs", icon: Search, to: "/discover", children: [
      { to: "/discover", label: "Matches", icon: Search },
      { to: "/saved", label: "Saved", icon: Bookmark },
      { to: "/searches", label: "Searches & companies", icon: Radar },
    ],
  },
  {
    key: "applications", label: "Applications", icon: Briefcase, to: "/applied", children: [
      { to: "/applied", label: "Pipeline", icon: Briefcase },
      { to: "/reports", label: "Outcomes & reports", icon: FileSpreadsheet },
    ],
  },
  {
    key: "career", label: "Career", icon: Compass, to: "/studio", children: [
      { to: "/studio", label: "Resumes", icon: FileText },
      { to: "/career", label: "Skills & learning", icon: Target },
      { to: "/interview-prep", label: "Interview practice", icon: MessagesSquare },
      { to: "/mentor", label: "Plan & mentor", icon: Compass },
      { to: "/international", label: "Work abroad", icon: Globe },
    ],
  },
];

export function footerItems(role?: string): NavLeaf[] {
  return [
    ...(role === "mentor" ? [{ to: "/mentoring", label: "My mentees", icon: Users }] : []),
    ...(role === "admin" ? [{ to: "/admin", label: "Admin", icon: Shield }] : []),
    { to: "/settings", label: "Settings", icon: Settings },
  ];
}

/** The area a path belongs to, so its group stays open and highlighted. */
export function areaFor(pathname: string): NavArea | undefined {
  return areas.find((a) => a.to === pathname || a.children.some((c) => pathname === c.to || pathname.startsWith(c.to + "/")));
}

export interface Command { id: string; label: string; group: string; to: string; icon: LucideIcon; keywords?: string }

/** Everything ⌘K can reach: every page, every settings and sub-tab that has a deep link. */
export function commands(role?: string): Command[] {
  const pages: Command[] = [
    ...areas.flatMap((a) => (a.children.length ? a.children : [{ to: a.to, label: a.label, icon: a.icon }])
      .map((c) => ({ id: `page:${c.to}`, label: a.children.length ? `${a.label} › ${c.label}` : c.label, group: "Go to", to: c.to, icon: c.icon }))),
    ...footerItems(role).map((c) => ({ id: `page:${c.to}`, label: c.label, group: "Go to", to: c.to, icon: c.icon })),
  ];
  const deep: Command[] = [
    { id: "searches:companies", label: "Companies you watch", group: "Jobs", to: "/searches?tab=companies", icon: Radar, keywords: "employers watchlist careers page" },
    { id: "searches:sources", label: "Job source health", group: "Jobs", to: "/searches?tab=sources", icon: Radar, keywords: "boards status adzuna greenhouse lever" },
    { id: "career:gaps", label: "Skill gaps", group: "Career", to: "/career?tab=gaps", icon: Target },
    { id: "career:skills", label: "Skills & evidence", group: "Career", to: "/career?tab=skills", icon: Target },
    { id: "career:learning", label: "Learning plan", group: "Career", to: "/career?tab=learning", icon: Sparkles, keywords: "courses" },
  ];
  const settings: [string, string, LucideIcon, string?][] = [
    ["profile", "Resume & profile", UserRound, "cv upload"],
    ["preferences", "Job preferences", ListChecks, "titles cities salary remote"],
    ["career-goals", "Career goals", Target],
    ["platforms", "Platforms", Plug, "sites sources job platforms"],
    ["answers", "Verified answers", ListChecks, "screening questions"],
    ["email", "Alert emails", Bell],
    ["notifications", "Notifications", Bell],
    ["extension", "Browser extension", Plug, "smart apply chrome browser connect install connection code"],
    ["privacy", "Privacy & consent", Shield],
    ["account", "Account & connection", KeyRound, "password sign out"],
  ];
  return [
    ...pages,
    ...deep,
    ...settings.map(([tab, label, icon, keywords]) => ({ id: `settings:${tab}`, label, group: "Settings", to: `/settings?tab=${tab}`, icon, keywords })),
  ];
}
