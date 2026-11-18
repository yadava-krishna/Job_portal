// A page with unsaved edits can ask to be consulted before the app navigates away (links, ⌘K). Only one guard at a time.
type Guard = (proceed: () => void) => boolean;  // return true when it took over (it will call proceed itself, or not)
let current: Guard | null = null;

export function setNavGuard(g: Guard | null) { current = g; }

/** Run a navigation, unless a guard intercepts it (it then calls `go` once the user decides). */
export function guardedNavigate(go: () => void) {
  if (current && current(go)) return;
  go();
}
