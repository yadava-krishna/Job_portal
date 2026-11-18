// Entrance cascades play the first time a set of results is shown in this session, not every time the user comes back.
const seen = new Map<string, number>();

/** True the first time `key` is asked about (and for a moment after, so React's double-invoked initialisers agree). */
export function firstSight(key: string): boolean {
  const now = Date.now();
  const at = seen.get(key);
  if (at === undefined) { seen.set(key, now); return true; }
  return now - at < 120;
}
