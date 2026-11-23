// One portal's card: logo, one line about it, its real state, one main action, at most two more, and links to the
// details panel and (where offered) the profile checklist. Every button here opens a working flow.
import { useState } from "react";
import { ArrowRight, ClipboardList, ExternalLink, Info, Link2, Loader2, LogIn, RefreshCw, Settings2, UserRound } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Chip, type ChipTone } from "@/features/apply/parts";
import { PortalLogo } from "./PortalLogo";
import type { Transient, usePortalActions } from "./hooks";
import type { Portal } from "./types";

export type CardIntent = "details" | "checklist" | "prepare" | "setup" | "import";

const TONE: Record<Portal["status"], ChipTone> = {
  linked: "ok", not_linked: "check", not_configured: "neutral", reconnect_required: "warn", authorization_required: "warn", native_only: "check",
};

interface Btn { key: string; label: string; icon: React.ReactNode; onClick?: () => void; href?: string; disabled?: boolean }

export function ProviderCard({ p, transient, actions, isAdmin, onIntent }: {
  p: Portal; transient: Transient | null; actions: ReturnType<typeof usePortalActions>; isAdmin: boolean; onIntent: (i: CardIntent) => void;
}) {
  const [opened, setOpened] = useState(false);
  const has = (a: Portal["actions"][number]) => p.actions.includes(a);
  const sim = p.simulated ? " (simulated)" : "";
  const kind = transient?.kind;

  const importBtn: Btn = { key: "import", label: `Import ${p.name} job`, icon: <Link2 />, onClick: () => onIntent("import") };
  const openBtn: Btn = { key: "open", label: `Open ${p.name}`, icon: <ExternalLink />, href: p.url };
  const prepareBtn: Btn = { key: "prepare", label: "Prepare application", icon: <ArrowRight />, onClick: () => onIntent("prepare") };
  const connectBtn: Btn = { key: "connect", label: `Connect with ${p.name}${sim}`, icon: <LogIn />, onClick: () => actions.connect.mutate(), disabled: actions.busy };

  let primary: Btn;
  let secondary: Btn[];
  if (kind === "connecting") {
    primary = { key: "connecting", label: "Connecting…", icon: <Loader2 className="animate-spin" />, disabled: true };
    secondary = [importBtn, openBtn];
  } else if (kind === "failed" && has("connect")) {
    primary = { ...connectBtn, key: "retry", label: "Try again" };
    secondary = [importBtn, openBtn];
  } else if (kind === "unavailable") {
    primary = { key: "check", label: "Check again", icon: <RefreshCw />, onClick: () => actions.check.mutate(), disabled: actions.busy };
    secondary = [importBtn, openBtn];
  } else if (p.kind === "native") {
    primary = { ...openBtn, onClick: () => setOpened(true) };
    secondary = [importBtn, prepareBtn];
  } else if (p.status === "not_linked") {
    primary = connectBtn;
    secondary = [importBtn, openBtn];
  } else if (p.status === "reconnect_required" && has("reconnect")) {
    primary = { ...connectBtn, key: "reconnect", label: `Reconnect ${p.name}${sim}` };
    secondary = [importBtn, openBtn];
  } else if (p.status === "linked") {
    primary = importBtn;
    secondary = [openBtn, prepareBtn];
  } else if (has("setup")) {  // not configured, or refused by the portal: an admin fixes the setup
    primary = { key: "setup", label: p.status === "authorization_required" ? "Review setup" : `Set up ${p.name}`, icon: <Settings2 />, onClick: () => onIntent("setup") };
    secondary = [importBtn, openBtn];
  } else {  // a candidate on a server without the portal's sign-in: what still works
    primary = importBtn;
    secondary = [openBtn, prepareBtn];
  }

  const chip: [string, ChipTone] = kind === "connecting" ? ["Connecting…", "neutral"] : kind === "failed" ? ["Connection failed", "fail"]
    : kind === "unavailable" ? ["Temporarily unavailable", "warn"] : [p.status_label, p.status === "linked" && p.limited ? "warn" : TONE[p.status]];
  const id = p.identity;
  const note = transient?.message ?? (p.status !== "linked" ? p.reason : null);

  return (
    <li className="min-w-0 rounded-2xl bg-card ring-1 ring-border" data-testid={`portal-${p.portal}`} data-state={kind ?? p.status}>
      <div className="flex flex-col gap-3 p-4 lg:flex-row lg:items-start lg:gap-6">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <PortalLogo portal={p.portal} />
          <div className="min-w-0 flex-1 space-y-2">
            <div>
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <h4 className="font-display text-[15.5px] font-bold text-heading">{p.name}</h4>
                <Chip tone={chip[1]}>{kind === "connecting" && <Loader2 className="animate-spin" aria-hidden />}{chip[0]}</Chip>
              </div>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{p.summary}</p>
            </div>
            {id && p.status === "linked" && !kind && (
              <div className="flex w-fit max-w-full items-center gap-2 rounded-lg bg-paper-sunk/70 px-2.5 py-1.5 text-xs ring-1 ring-border/70" data-testid={`identity-${p.portal}`}>
                <UserRound className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 truncate"><b className="font-medium text-foreground">{id.name || "Name not shared"}</b>{id.email ? ` · ${id.email}` : ""}</span>
              </div>
            )}
            {id?.simulated && <p className="text-xs font-medium text-caution" data-testid={`simulated-${p.portal}`}>Simulated test account from a local test server. This is not your {p.name} account.</p>}
            {note && (
              <p role={kind === "failed" || kind === "unavailable" ? "alert" : undefined}
                 className={`text-xs leading-relaxed ${kind || p.status === "reconnect_required" || p.status === "authorization_required" ? "text-caution" : "text-muted-foreground"}`}>{note}</p>
            )}
            {opened && p.kind === "native" && (
              <div className="rounded-lg bg-route-tint/50 px-3 py-2 text-xs leading-relaxed" role="status" data-testid="naukri-return">
                {p.name} opened in a new tab; sign in there yourself if it asks. Found a job? Copy its link, come back to this tab and
                <Button size="xs" variant="link" className="h-auto px-1" onClick={() => onIntent("import")}>import it</Button>. Your JobPilot session stays open.
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 lg:w-[22rem] lg:shrink-0 lg:justify-end" data-actions>
          {[primary, ...secondary].map((b, i) => (
            b.href ? (
              // A real link (it opens the portal), styled like the buttons next to it.
              <a key={b.key} href={b.href} target="_blank" rel="noopener noreferrer" onClick={b.onClick}
                 className={buttonVariants({ size: "sm", variant: i === 0 ? "default" : "outline" })}>
                {b.icon} {b.label}<span className="sr-only"> (opens in a new tab)</span>
              </a>
            ) : (
              <Button key={b.key} size="sm" variant={i === 0 ? "default" : "outline"} disabled={b.disabled} onClick={b.onClick}>
                {b.icon} {b.label}
              </Button>
            )
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t px-4 py-2.5 text-xs">
        {p.kind === "oauth" && (id || has("check")) && (
          <button type="button" className="font-medium text-route underline-offset-4 hover:underline" onClick={() => onIntent("details")}>Manage connection</button>
        )}
        {has("optimize") && (
          <button type="button" className="inline-flex items-center gap-1 font-medium text-route underline-offset-4 hover:underline" onClick={() => onIntent("checklist")}>
            <ClipboardList className="size-3.5" aria-hidden /> Profile checklist
          </button>
        )}
        <button type="button" className="inline-flex items-center gap-1 font-medium text-route underline-offset-4 hover:underline" onClick={() => onIntent("details")}>
          <Info className="size-3.5" aria-hidden /> Capabilities & limitations
        </button>
        {isAdmin && has("setup") && primary.key !== "setup" && (
          <button type="button" className="inline-flex items-center gap-1 font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline" onClick={() => onIntent("setup")}>
            <Settings2 className="size-3.5" aria-hidden /> Setup
          </button>
        )}
      </div>
    </li>
  );
}
