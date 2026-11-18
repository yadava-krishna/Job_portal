// Small layout pieces shared by the growth pages (career, interview prep, mentor, international, admin), so every
// section reads the same way: one container, a quiet header, rows inside. Tokens only.
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type Tone = "success" | "caution" | "danger" | "route" | "violet" | "coral" | "muted";

/** Soft fill + text colour for a small label. Green only for confirmed / healthy outcomes. */
export const toneChip: Record<Tone, string> = {
  success: "bg-success-tint text-success",
  caution: "bg-caution-tint text-caution",
  danger: "bg-destructive/10 text-destructive",
  route: "bg-route-tint text-route",
  violet: "bg-lavender text-violet",
  coral: "bg-peach text-coral-ink",
  muted: "bg-muted text-muted-foreground",
};
export const toneText: Record<Tone, string> = {
  success: "text-success", caution: "text-caution", danger: "text-destructive", route: "text-route", violet: "text-violet",
  coral: "text-coral-ink", muted: "text-muted-foreground",
};
export const toneDot: Record<Tone, string> = {
  success: "bg-success", caution: "bg-caution", danger: "bg-destructive", route: "bg-route", violet: "bg-violet", coral: "bg-coral",
  muted: "bg-muted-foreground/50",
};

/** A small rounded label; pass an icon so meaning never rests on colour alone. */
export function Chip({ tone = "muted", icon, children, className, title }: { tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium whitespace-nowrap [&_svg]:size-3 [&_svg]:shrink-0", toneChip[tone], className)}>
      {icon}{children}
    </span>
  );
}

/** Status as a dot plus words (the words carry the meaning; the dot is a quick scan aid). */
export function StatusDot({ tone, children, className, pulse }: { tone: Tone; children: ReactNode; className?: string; pulse?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", className)}>
      <span aria-hidden className={cn("size-2 shrink-0 rounded-full", toneDot[tone], pulse && "animate-pulse")} />
      {children}
    </span>
  );
}

/** One section container: optional icon tile, title, count, actions; children are the body. */
export function Panel({ title, icon, count, description, actions, children, className, bodyClassName, id, as: Tag = "section", ...rest }: {
  title?: ReactNode; icon?: ReactNode; count?: ReactNode; description?: ReactNode; actions?: ReactNode; children?: ReactNode;
  className?: string; bodyClassName?: string; id?: string; as?: "section" | "div"; "data-testid"?: string; "aria-label"?: string;
}) {
  const headingId = id ? `${id}-h` : undefined;
  return (
    <Tag id={id} aria-labelledby={title && headingId ? headingId : undefined} className={cn("min-w-0 rounded-2xl bg-card ring-1 ring-border", className)} {...rest}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 px-4 pt-4 sm:px-5">
          <div className="flex min-w-0 items-start gap-2.5">
            {icon && <span aria-hidden className="mt-px flex size-7 shrink-0 items-center justify-center rounded-lg bg-paper-sunk text-heading [&_svg]:size-3.5">{icon}</span>}
            <div className="min-w-0">
              {title && (
                <h2 id={headingId} className="flex items-center gap-2 font-display text-[15px] leading-7 font-bold tracking-[-0.015em] text-heading">
                  {title}
                  {count != null && <span className="readout rounded-full bg-paper-sunk px-1.5 text-[11px] font-medium text-muted-foreground">{count}</span>}
                </h2>
              )}
              {description && <div className="text-[12.5px] leading-snug text-muted-foreground">{description}</div>}
            </div>
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn("px-4 pt-3 pb-4 sm:px-5", !(title || actions) && "pt-4", bodyClassName)}>{children}</div>
    </Tag>
  );
}

/** A small mono label above a group of rows. */
export function GroupLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("text-[11px] font-semibold tracking-[0.06em] text-muted-foreground uppercase", className)}>{children}</div>;
}

/** A soft inline note (needs-attention, info) with an icon. */
export function Note({ tone = "muted", icon, children, className, role }: { tone?: Tone; icon?: ReactNode; children: ReactNode; className?: string; role?: string }) {
  return (
    <div role={role} className={cn("flex items-start gap-2 rounded-xl px-3 py-2 text-[12.5px] leading-snug [&>svg]:mt-0.5 [&>svg]:size-3.5 [&>svg]:shrink-0", toneChip[tone], className)}>
      {icon}<div className="min-w-0">{children}</div>
    </div>
  );
}

/** Dense table styles for admin and similar tabular data. */
export const table = {
  wrap: "overflow-x-auto",
  table: "w-full text-left text-[12.5px]",
  thead: "border-y border-border bg-paper-sunk/70 text-[11px] text-muted-foreground",
  th: "px-4 py-2 font-medium whitespace-nowrap first:pl-5 last:pr-5",
  tr: "border-b border-border/70 last:border-0 transition-colors hover:bg-paper-sunk/50",
  td: "px-4 py-2.5 align-top first:pl-5 last:pr-5",
};
