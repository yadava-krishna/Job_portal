import { useConnection } from "@/contexts/ConnectionContext";
import { useCareerGoals, useConsents } from "@/features/career/hooks";
import { timeAgo } from "@/lib/format";
import { NOTIFICATION_KINDS, useEmailIntegration, useExtensionDevices, useNotificationPrefs, usePlatforms, usePreferences, useProfile } from "@/services/queries";
import type { VerifiedFacts } from "@/types/api";
import { StatusPill } from "./primitives";

/** One status chip for the section header. Each reads the same cached query its section uses, so nothing extra loads. */
export function SectionStatus({ section }: { section: string }) {
  switch (section) {
    case "profile": return <ProfileStatus />;
    case "career-goals": return <GoalsStatus />;
    case "preferences": return <PreferencesStatus />;
    case "platforms": return <PlatformsStatus />;
    case "extension": return <ExtensionStatus />;
    case "answers": return <AnswersStatus />;
    case "email": return <EmailStatus />;
    case "notifications": return <NotificationsStatus />;
    case "privacy": return <PrivacyStatus />;
    case "account": return <AccountStatus />;
    default: return null;
  }
}

function ProfileStatus() {
  const { data } = useProfile();
  if (!data) return null;
  if (!data.has_resume && !data.confirmed) return <StatusPill tone="caution">No resume yet</StatusPill>;
  if (!data.confirmed_at) return <StatusPill tone="caution">Profile needs review</StatusPill>;
  return <StatusPill tone="success">Profile confirmed</StatusPill>;
}

const MODE_LABEL = { india: "India only", international: "Abroad", both: "India and abroad" } as const;

function GoalsStatus() {
  const { data } = useCareerGoals();
  if (!data) return null;
  return <StatusPill tone="neutral">{MODE_LABEL[data.search_mode] ?? data.search_mode}</StatusPill>;
}

function PreferencesStatus() {
  const { data } = usePreferences();
  if (!data) return null;
  if (!data.is_configured) return <StatusPill tone="caution">Not set up yet</StatusPill>;
  return <StatusPill tone="neutral">Shortlisting at <span className="readout">{data.min_match_score}%</span>+</StatusPill>;
}

function PlatformsStatus() {
  const { data } = usePlatforms();
  if (!data) return null;
  const on = data.filter((p) => p.enabled).length;
  return <StatusPill tone={on ? "neutral" : "caution"}><span className="readout">{on}</span> of <span className="readout">{data.length}</span> on</StatusPill>;
}

function ExtensionStatus() {
  const { data } = useExtensionDevices();
  if (!data) return null;
  if (!data.length) return <StatusPill tone="neutral">No browser connected</StatusPill>;
  return <StatusPill tone="success"><span className="readout">{data.length}</span> {data.length === 1 ? "browser" : "browsers"} connected</StatusPill>;
}

const FACT_KEYS: (keyof VerifiedFacts)[] = ["current_ctc", "expected_ctc", "notice_period", "earliest_start_date", "work_authorization",
  "shift_flexibility", "relevant_experience", "requires_sponsorship", "willing_to_relocate"];

function AnswersStatus() {
  const { data } = useProfile();
  const f = data?.verified_facts;
  if (!f) return null;
  const done = FACT_KEYS.filter((k) => f[k] != null && f[k] !== "").length;
  return (
    <StatusPill tone={done === FACT_KEYS.length ? "success" : "neutral"}>
      <span className="readout">{done}</span> of <span className="readout">{FACT_KEYS.length}</span> answered
    </StatusPill>
  );
}

function EmailStatus() {
  const { data } = useEmailIntegration();
  if (!data) return null;
  if (!data.enabled) return <StatusPill tone="neutral">Off</StatusPill>;
  if (data.last_error) return <StatusPill tone="caution" title={data.last_error}>Last check failed</StatusPill>;
  return <StatusPill tone="success">On{data.last_checked_at ? ` · checked ${timeAgo(data.last_checked_at)}` : ""}</StatusPill>;
}

function NotificationsStatus() {
  const { data } = useNotificationPrefs();
  if (!data?.kinds) return null;
  const on = NOTIFICATION_KINDS.filter((k) => data.kinds![k]).length;
  return <StatusPill tone="neutral"><span className="readout">{on}</span> of <span className="readout">{NOTIFICATION_KINDS.length}</span> alert types on</StatusPill>;
}

function PrivacyStatus() {
  const { data } = useConsents();
  if (!data) return null;
  const on = data.filter((c) => c.granted).length;
  return <StatusPill tone="neutral"><span className="readout">{on}</span> of <span className="readout">{data.length}</span> turned on</StatusPill>;
}

function AccountStatus() {
  const conn = useConnection();
  if (conn.state === "online") return <StatusPill tone="success">Server connected</StatusPill>;
  if (conn.state === "degraded") return <StatusPill tone="caution">Server partly working</StatusPill>;
  if (conn.state === "offline") return <StatusPill tone="danger">Server offline</StatusPill>;
  if (conn.state === "unconfigured") return <StatusPill tone="caution">No server address set</StatusPill>;
  return <StatusPill tone="neutral">Checking server…</StatusPill>;
}
