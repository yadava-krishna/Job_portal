"""Short-lived in-process cache so many users and saved searches share one fetch per board."""

from __future__ import annotations

import threading
import time

from backend.services.ats.base import AtsError, BoardResult, fetch_board

TTL_SECONDS = 30 * 60
NOT_FOUND_TTL_SECONDS = 6 * 3600
# Board results hold full job descriptions, so the cache is bounded: the least recently used boards are dropped
# beyond this many. A run that checks hundreds of boards then keeps memory flat; a board fetched again later is
# simply fetched again.
MAX_BOARDS = 40


class BoardCache:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str, str | None], tuple[float, BoardResult | AtsError]] = {}
        self._lock = threading.Lock()

    def get(self, ats: str, token: str, *, company_name: str | None = None, region: str | None = None) -> BoardResult:
        key = (ats, token.lower(), region)
        now = time.monotonic()
        with self._lock:
            hit = self._items.get(key)
        if hit:
            ttl = NOT_FOUND_TTL_SECONDS if isinstance(hit[1], AtsError) else TTL_SECONDS
            if now - hit[0] < ttl:
                if isinstance(hit[1], AtsError):
                    raise hit[1]
                with self._lock:  # mark as recently used
                    self._items.pop(key, None)
                    self._items[key] = hit
                return hit[1]
        try:
            result = fetch_board(ats, token, company_name=company_name, region=region)
        except AtsError as exc:
            if exc.kind == "not_found":  # don't hammer boards that don't exist; transient errors retry next time
                with self._lock:
                    self._items[key] = (now, exc)
            raise
        with self._lock:
            self._items[key] = (now, result)
            self._trim()
        return result

    def _trim(self) -> None:
        boards = [k for k, (_, v) in self._items.items() if not isinstance(v, AtsError)]
        for k in boards[: max(0, len(boards) - MAX_BOARDS)]:  # dicts keep insertion order: oldest first
            del self._items[k]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


board_cache = BoardCache()
