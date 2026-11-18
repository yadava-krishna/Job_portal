// Protects unsaved Settings edits. Wraps the active section, notices when its fields differ from what was loaded,
// and before the user leaves the section (another category, a link, ⌘K, refresh or close) asks: save, discard, or keep
// editing. It reads the form's own fields, so every section is covered without changing each form's logic.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { CircleAlert, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { setNavGuard } from "@/lib/navGuard";

/** Everything a user can change in the section, as one string. File pickers and things marked data-guard-ignore are left out. */
function snapshot(root: HTMLElement): string {
  const parts: string[] = [];
  root.querySelectorAll<HTMLElement>("input, textarea, select, [role=switch], [role=checkbox], [role=radio], [aria-pressed], [data-guard-value]").forEach((el, i) => {
    if (el.closest("[data-guard-ignore]")) return;
    if (el instanceof HTMLInputElement) {
      if (el.type === "file" || el.type === "password" || el.type === "hidden") return;
      parts.push(`${i}:${el.name || el.id}:${el.type === "checkbox" || el.type === "radio" ? el.checked : el.value}`);
    } else if (el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) {
      parts.push(`${i}:${el.name || el.id}:${el.value}`);
    } else {
      parts.push(`${i}:${el.getAttribute("aria-checked") ?? el.getAttribute("aria-pressed") ?? el.getAttribute("data-guard-value")}`);
    }
  });
  return parts.join("|");
}

export interface UnsavedGuardApi {
  dirty: boolean;
  /** Ask before running `go` when there are unsaved edits; runs it straight away otherwise. */
  confirm: (go: () => void) => void;
}

export function useUnsavedGuard(sectionKey: string) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const baseline = useRef<string | null>(null);
  const touched = useRef(false);
  const [dirty, setDirty] = useState(false);
  const [resetKey, setResetKey] = useState(0);
  const [pending, setPending] = useState<null | (() => void)>(null);
  const [saving, setSaving] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const rebaseline = useCallback(() => {
    if (bodyRef.current) baseline.current = snapshot(bodyRef.current);
    touched.current = false;
    setDirty(false);
  }, []);

  // A new section (or a discard) starts clean. While the user hasn't typed, follow the DOM as data loads in.
  useEffect(() => {
    rebaseline();
    const root = bodyRef.current;
    if (!root) return;
    const mo = new MutationObserver(() => { if (!touched.current) baseline.current = snapshot(root); });
    mo.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ["value", "aria-checked", "aria-pressed", "data-guard-value"] });
    const onEdit = (e: Event) => {
      if (!e.isTrusted) return;
      // Let React apply the change first (controlled inputs, tag lists), then compare.
      requestAnimationFrame(() => {
        if (!bodyRef.current) return;
        touched.current = true;
        setDirty(baseline.current != null && snapshot(bodyRef.current) !== baseline.current);
      });
    };
    root.addEventListener("input", onEdit, true);
    root.addEventListener("change", onEdit, true);
    root.addEventListener("click", onEdit, true);
    root.addEventListener("keyup", onEdit, true);
    return () => { mo.disconnect(); root.removeEventListener("input", onEdit, true); root.removeEventListener("change", onEdit, true); root.removeEventListener("click", onEdit, true); root.removeEventListener("keyup", onEdit, true); };
  }, [sectionKey, resetKey, rebaseline]);

  // A successful save (any mutation finishing while edits are pending) makes the saved values the new baseline.
  useEffect(() => qc.getMutationCache().subscribe((ev) => {
    if (ev.type === "updated" && ev.mutation.state.status === "success" && touched.current) setTimeout(rebaseline, 350);
  }), [qc, rebaseline]);

  // Refresh / close tab: the browser shows its own "leave site?" prompt.
  useEffect(() => {
    if (!dirty) return;
    const onUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, [dirty]);

  const confirm = useCallback((go: () => void) => { if (dirty) setPending(() => go); else go(); }, [dirty]);

  // Links elsewhere in the app (sidebar, breadcrumbs, cards) and ⌘K jumps.
  useEffect(() => {
    if (!dirty) { setNavGuard(null); return; }
    setNavGuard((go) => { setPending(() => go); return true; });
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement).closest("a[href]") as HTMLAnchorElement | null;
      if (!a || a.target === "_blank" || bodyRef.current?.contains(a)) return;
      const href = a.getAttribute("href") ?? "";
      if (!href.startsWith("#/") || href.startsWith("#/settings")) return;
      e.preventDefault();
      e.stopPropagation();
      setPending(() => () => navigate(href.slice(1)));
    };
    document.addEventListener("click", onClick, true);
    return () => { document.removeEventListener("click", onClick, true); setNavGuard(null); };
  }, [dirty, navigate]);

  const discard = () => {
    const go = pending;
    setPending(null);
    setResetKey((k) => k + 1);   // remounts the section: fields go back to the saved values
    setDirty(false);
    touched.current = false;
    go?.();
  };

  const saveThen = async () => {
    const root = bodyRef.current;
    const buttons = root ? [...root.querySelectorAll<HTMLButtonElement>("[data-save-bar] button")].filter((b) => !b.disabled) : [];
    const save = buttons.find((b) => b.type === "submit") ?? buttons[buttons.length - 1];
    if (!save) { setPending(null); return; }   // nothing to press: keep editing
    setSaving(true);
    const ok = await new Promise<boolean>((resolve) => {
      const timer = setTimeout(() => { unsub(); resolve(false); }, 15000);
      const unsub = qc.getMutationCache().subscribe((ev) => {
        if (ev.type !== "updated") return;
        if (ev.mutation.state.status === "success") { clearTimeout(timer); unsub(); resolve(true); }
        if (ev.mutation.state.status === "error") { clearTimeout(timer); unsub(); resolve(false); }
      });
      save.click();
    });
    setSaving(false);
    if (!ok) { setPending(null); return; }   // the form shows its own error; the user stays to fix it
    const go = pending;
    setPending(null);
    rebaseline();
    go?.();
  };

  const dialog: ReactNode = (
    <Dialog open={pending != null} onOpenChange={(o) => { if (!o && !saving) setPending(null); }}>
      <DialogContent className="sm:max-w-md" data-testid="unsaved-dialog">
        <DialogHeader>
          <div className="mb-1 flex size-10 items-center justify-center rounded-2xl bg-caution-tint text-caution"><CircleAlert className="size-5" aria-hidden /></div>
          <DialogTitle className="font-display text-[19px] font-bold text-heading">You have unsaved changes</DialogTitle>
          <DialogDescription>Save them before you go, or discard them. Nothing is saved automatically here.</DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2 sm:justify-between">
          <Button variant="ghost" onClick={() => setPending(null)} disabled={saving}>Keep editing</Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={discard} disabled={saving}>Discard</Button>
            <Button onClick={() => void saveThen()} disabled={saving}>{saving && <Loader2 className="animate-spin" />} Save changes</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { bodyRef, dirty, confirm, resetKey, dialog };
}
