import { useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { SETTINGS_GROUPS, SETTINGS_SECTIONS } from "./config";

type Box = { x: number; y: number; w: number; h: number };

/** Measures the active item inside a container so one highlight can slide to it instead of jumping. */
function useIndicator(active: string) {
  const boxRef = useRef<HTMLDivElement>(null);
  const items = useRef<Record<string, HTMLButtonElement | null>>({});
  const [box, setBox] = useState<Box | null>(null);
  useLayoutEffect(() => {
    const measure = () => {
      const el = items.current[active];
      if (!el || !el.offsetParent) { setBox(null); return; }
      setBox({ x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight });
    };
    measure();
    if (typeof ResizeObserver === "undefined" || !boxRef.current) return;
    const ro = new ResizeObserver(measure);
    ro.observe(boxRef.current);
    return () => ro.disconnect();
  }, [active]);
  return { boxRef, items, box };
}

const EASE = "ease-[cubic-bezier(.2,0,0,1)]";

/** Settings categories: a sticky grouped list on wide screens, a horizontal scroller above the content on smaller ones. */
export function SettingsNav({ active, onSelect, attention = {} }: {
  active: string; onSelect: (key: string) => void; attention?: Record<string, string | undefined>;
}) {
  return (
    <>
      <DesktopNav active={active} onSelect={onSelect} attention={attention} />
      <MobileNav active={active} onSelect={onSelect} attention={attention} />
    </>
  );
}

function AttentionDot({ reason }: { reason?: string }) {
  if (!reason) return null;
  return (
    <span className="ml-auto flex size-4 shrink-0 items-center justify-center" title={reason}>
      <span aria-hidden className="size-1.5 rounded-full bg-coral" />
      <span className="sr-only">({reason})</span>
    </span>
  );
}

function DesktopNav({ active, onSelect, attention }: { active: string; onSelect: (key: string) => void; attention: Record<string, string | undefined> }) {
  const { boxRef, items, box } = useIndicator(active);
  return (
    <nav aria-label="Settings sections" className="sticky top-[76px] hidden self-start xl:block">
      <div ref={boxRef} className="relative">
        {box && (
          <span aria-hidden className={cn("pointer-events-none absolute inset-x-0 top-0 rounded-xl bg-card shadow-[var(--shadow-raised)] ring-1 ring-border/80 transition-[transform,height] duration-[240ms]", EASE)}
                style={{ transform: `translateY(${box.y}px)`, height: box.h }}>
            <span className="absolute top-2 bottom-2 left-0 w-[3px] rounded-r-full bg-route" />
          </span>
        )}
        {SETTINGS_GROUPS.map((g, gi) => (
          <div key={g.label} className={cn(gi > 0 && "mt-5")}>
            <div className="eyebrow mb-1.5 px-3 text-[10px]">{g.label}</div>
            <ul className="space-y-0.5">
              {g.sections.map((s) => {
                const on = s.key === active;
                const Icon = s.icon;
                return (
                  <li key={s.key}>
                    <button type="button" ref={(el) => { items.current[s.key] = el; }} onClick={() => onSelect(s.key)}
                            aria-current={on ? "page" : undefined}
                            className={cn("group relative flex h-10 w-full items-center gap-2.5 rounded-xl px-3 text-left text-[13.5px] transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                              on ? "font-semibold text-heading" : "font-medium text-muted-foreground hover:bg-muted/70 hover:text-foreground")}>
                      <Icon aria-hidden className={cn("size-4 shrink-0 transition-colors duration-200", on ? "text-route" : "text-muted-foreground/80 group-hover:text-foreground")} />
                      <span className="min-w-0 flex-1 truncate">{s.label}</span>
                      <AttentionDot reason={attention[s.key]} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}

function MobileNav({ active, onSelect, attention }: { active: string; onSelect: (key: string) => void; attention: Record<string, string | undefined> }) {
  const { boxRef, items, box } = useIndicator(active);
  const scroller = useRef<HTMLDivElement>(null);
  // Keep the chosen chip in view (centred when possible) without scrolling the page itself.
  useLayoutEffect(() => {
    const el = items.current[active];
    const sc = scroller.current;
    if (!el || !sc || !sc.offsetParent) return;
    const left = el.offsetLeft - (sc.clientWidth - el.offsetWidth) / 2;
    if (typeof sc.scrollTo === "function") sc.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
  }, [active, items]);
  return (
    <nav aria-label="Settings sections" className="-mx-4 mb-5 sm:-mx-8 xl:hidden">
      <div ref={scroller} className="overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:px-8 [&::-webkit-scrollbar]:hidden">
        <div ref={boxRef} className="relative flex w-max gap-1 rounded-2xl bg-paper-sunk p-1 ring-1 ring-border/70">
          {box && (
            <span aria-hidden className={cn("pointer-events-none absolute top-0 left-0 rounded-xl bg-card shadow-[var(--shadow-raised)] ring-1 ring-border/80 transition-[transform,width] duration-[240ms]", EASE)}
                  style={{ transform: `translate(${box.x}px, ${box.y}px)`, width: box.w, height: box.h }} />
          )}
          {SETTINGS_SECTIONS.map((s) => {
            const on = s.key === active;
            const Icon = s.icon;
            return (
              <button key={s.key} type="button" ref={(el) => { items.current[s.key] = el; }} onClick={() => onSelect(s.key)}
                      aria-current={on ? "page" : undefined}
                      className={cn("relative flex h-9 shrink-0 items-center gap-1.5 rounded-xl px-3 text-[13px] whitespace-nowrap transition-colors duration-200 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                        on ? "font-semibold text-heading" : "font-medium text-muted-foreground hover:text-foreground")}>
                <Icon aria-hidden className={cn("size-3.5", on ? "text-route" : "text-muted-foreground/80")} />
                {s.label}
                {attention[s.key] && <><span aria-hidden className="size-1.5 rounded-full bg-coral" /><span className="sr-only">({attention[s.key]})</span></>}
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
