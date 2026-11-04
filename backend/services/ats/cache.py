"""Short-lived in-process cache so many users and saved searches share one fetch per board."""

from __future__ import annotations

import threading
import time

from backend.services.ats.base import AtsError, BoardResult, fetch_board

TTL_SECONDS = 30 * 60
NOT_FOUND_TTL_SECONDS = 6 * 3600


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
        return result

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


board_cache = BoardCache()
