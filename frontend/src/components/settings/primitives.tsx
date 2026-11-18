import { useId, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * A settings panel: one card per form scope. A descendant marked `data-save-bar` (the row holding the form's save
 * button) sticks to the bottom of the viewport while the panel is on screen, so long forms always show their save.
 */
export function Panel({ title, description, actions, children, className, bodyClassName, tone = "default" }: {
  title?: ReactNode; description?: ReactNode; actions?: ReactNode; children: ReactNode;
  className?: string; bodyClassName?: string; tone?: "default" | "danger";
}) {
  const id = useId();
  return (
    <section data-slot="settings-panel" aria-labelledby={title ? id : undefined}
             className={cn("rounded-2xl bg-card text-sm text-card-foreground shadow-[var(--shadow-raised)] ring-1",
               tone === "danger" ? "ring-destructive/30" : "ring-border/80",
               // The sticky save row (see doc comment). Negative margins match the body padding below.
               "[&_[data-save-bar]]:sticky [&_[data-save-bar]]:bottom-0 [&_[data-save-bar]]:z-10 [&_[data-save-bar]]:-mx-4 [&_[data-save-bar]]:-mb-4 [&_[data-save-bar]]:rounded-b-2xl [&_[data-save-bar]]:border-t [&_[data-save-bar]]:bg-card [&_[data-save-bar]]:px-4 [&_[data-save-bar]]:py-3 [&_[data-save-bar]]:shadow-[0_-10px_18px_-14px_rgb(23_25_39/0.25)]",
               "sm:[&_[data-save-bar]]:-mx-6 sm:[&_[data-save-bar]]:-mb-6 sm:[&_[data-save-bar]]:px-6",
               className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 px-4 pt-4 sm:px-6 sm:pt-5">
          <div className="min-w-0">
            {title && <h3 id={id} className={cn("font-display text-[15.5px] leading-snug font-bold tracking-[-0.015em]", tone === "danger" ? "text-destructive" : "text-heading")}>{title}</h3>}
            {description && <div className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">{description}</div>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn("p-4 sm:p-6", (title || actions) && "pt-4 sm:pt-5", bodyClassName)}>{children}</div>
    </section>
  );
}

/** A labelled group of related fields inside a panel, separated from the previous group by a hairline. */
export function FieldGroup({ title, hint, children, className }: { title: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  const id = useId();
  return (
    <div role="group" aria-labelledby={id} className={cn("space-y-3 border-t pt-5 first:border-t-0 first:pt-0", className)}>
      <div>
        <h4 id={id} className="text-[13px] font-semibold text-heading">{title}</h4>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

/** Label/value rows (account details, connection). */
export function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-2.5 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <dt className="text-[13px] text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-[13.5px] font-medium break-words sm:text-right">{children}</dd>
    </div>
  );
}

export type StatusTone = "success" | "caution" | "danger" | "neutral" | "route";

const toneClass: Record<StatusTone, { pill: string; dot: string }> = {
  success: { pill: "bg-success-tint text-success", dot: "bg-success" },
  caution: { pill: "bg-caution-tint text-caution", dot: "bg-caution" },
  danger: { pill: "bg-destructive/10 text-destructive", dot: "bg-destructive" },
  route: { pill: "bg-route-tint text-route", dot: "bg-route" },
  neutral: { pill: "bg-paper-sunk text-muted-foreground ring-1 ring-border", dot: "bg-muted-foreground/60" },
};

/** A small status chip for section headers ("1 browser connected", "Needs review"). */
export function StatusPill({ tone, children, title }: { tone: StatusTone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex max-w-full items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium whitespace-nowrap animate-in fade-in-0 zoom-in-95 duration-200", toneClass[tone].pill)}>
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", toneClass[tone].dot)} />
      <span className="truncate">{children}</span>
    </span>
  );
}
