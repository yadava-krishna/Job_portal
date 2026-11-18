// ⌘K / Ctrl+K: jump to any page or settings tab by typing. Arrow keys move, Return opens, Escape closes.
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CornerDownLeft, Search } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { commands, type Command } from "@/layouts/navigation";
import { cn } from "@/lib/utils";
import { guardedNavigate } from "@/lib/navGuard";

function score(c: Command, q: string): number {
  if (!q) return 1;
  const hay = `${c.label} ${c.group} ${c.keywords ?? ""}`.toLowerCase();
  const words = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.every((w) => hay.includes(w))) return 0;
  return c.label.toLowerCase().startsWith(words[0]) ? 3 : hay.includes(` ${words[0]}`) ? 2 : 1;
}

export function useCommandMenuShortcut(open: () => void) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); open(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
}

export function CommandMenu({ open, onOpenChange, role }: { open: boolean; onOpenChange: (o: boolean) => void; role?: string }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const all = useMemo(() => commands(role), [role]);
  const results = useMemo(() => all.map((c) => [c, score(c, q.trim())] as const).filter(([, s]) => s > 0)
    .sort((a, b) => b[1] - a[1]).map(([c]) => c).slice(0, 40), [all, q]);

  useEffect(() => { if (open) { setQ(""); setActive(0); } }, [open]);
  useEffect(() => { setActive(0); }, [q]);
  useEffect(() => { listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" }); }, [active]);

  const go = (c: Command | undefined) => { if (!c) return; onOpenChange(false); guardedNavigate(() => navigate(c.to)); };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(results.length - 1, i + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); go(results[active]); }
  };

  let lastGroup = "";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showCloseButton={false} className="top-[18%] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-xl" data-testid="command-menu">
        <DialogTitle className="sr-only">Go to a page or setting</DialogTitle>
        <div className="flex items-center gap-2 border-b px-4">
          <Search className="size-4 text-muted-foreground" aria-hidden />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKeyDown}
                 placeholder="Go to a page or setting…" aria-label="Go to a page or setting"
                 role="combobox" aria-expanded aria-controls="command-results" aria-activedescendant={results[active] ? `cmd-${results[active].id}` : undefined}
                 className="h-12 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground" />
          <kbd className="readout rounded border px-1.5 py-0.5 text-[11px] text-muted-foreground">Esc</kbd>
        </div>
        <div ref={listRef} id="command-results" role="listbox" className="max-h-[min(60vh,420px)] overflow-y-auto p-2">
          {results.length === 0 && <p className="px-3 py-8 text-center text-sm text-muted-foreground">Nothing called "{q}". Try a page name such as Saved, Resumes or Smart Apply.</p>}
          {results.map((c, i) => {
            const heading = c.group !== lastGroup ? c.group : null;
            lastGroup = c.group;
            const Icon = c.icon;
            return (
              <div key={c.id}>
                {heading && <div className="px-3 pt-2 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{heading}</div>}
                <div id={`cmd-${c.id}`} role="option" aria-selected={i === active} data-index={i}
                     onMouseMove={() => setActive(i)} onClick={() => go(c)}
                     className={cn("flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm", i === active ? "bg-route-tint text-foreground" : "text-foreground/90")}>
                  <Icon className={cn("size-4", i === active ? "text-route" : "text-muted-foreground")} aria-hidden />
                  <span className="flex-1">{c.label}</span>
                  {i === active && <CornerDownLeft className="size-3.5 text-muted-foreground" aria-hidden />}
                </div>
              </div>
            );
          })}
        </div>
        <div className="flex gap-4 border-t px-4 py-2 text-[11px] text-muted-foreground">
          <span><kbd className="readout">↑↓</kbd> move</span><span><kbd className="readout">Return</kbd> open</span><span><kbd className="readout">Esc</kbd> close</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
