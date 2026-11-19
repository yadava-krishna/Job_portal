import { useId, type ReactNode } from "react";
import { Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { copyText } from "./copy";

/** One titled block of the workspace. */
export function WsSection({ title, aside, children, className, testId }: { title: ReactNode; aside?: ReactNode; children: ReactNode; className?: string; testId?: string }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={cn("space-y-2.5", className)} data-testid={testId}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 id={id} className="eyebrow">{title}</h3>
        {aside && <div className="text-xs text-muted-foreground">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

export type ChipTone = "ok" | "warn" | "fail" | "check" | "neutral";
const chipTone: Record<ChipTone, string> = {
  ok: "bg-success-tint text-success ring-success/20",
  warn: "bg-caution-tint text-caution ring-caution/25",
  fail: "bg-destructive/10 text-destructive ring-destructive/20",
  check: "bg-lavender text-violet ring-violet/20",
  neutral: "bg-paper-sunk text-muted-foreground ring-border",
};

export function Chip({ tone, children, className, title }: { tone: ChipTone; children: ReactNode; className?: string; title?: string }) {
  return (
    <span title={title} className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset [&_svg]:size-3.5", chipTone[tone], className)}>
      {children}
    </span>
  );
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  return (
    <Button size="icon-sm" variant="ghost" aria-label={`Copy ${label}`} title="Copy" onClick={() => copyText(text, `Copied: ${label}`)}>
      <Copy />
    </Button>
  );
}
