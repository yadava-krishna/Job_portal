"""Per-host politeness for the background crawler (JPSE blueprint §5).

Limits are policy, not a speed knob: a global cap on transfers in flight, a cap per host, and a token bucket per host.
A host that keeps failing is paused by the frontier's back-off (crawl_state.cooldown_until), never retried in a loop.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlsplit

GLOBAL_IN_FLIGHT = 16
PER_HOST_IN_FLIGHT = 2

# Requests per second per API host. Close to the rate the old one-board-at-a-time loop already used on each host;
# the speed-up comes from working on several hosts at once and from 304 answers, not from pressing harder on one host.
HOST_RPS = {
    "boards-api.greenhouse.io": 3.0,
    "api.lever.co": 1.0,
    "api.eu.lever.co": 1.0,
    "api.ashbyhq.com": 3.0,
    "api.smartrecruiters.com": 2.0,
}
DEFAULT_RPS = 1.0

# Never crawled, whatever a target row says (also enforced for feeds by the connector registry).
DENIED_HOST_SUFFIXES = ("linkedin.com", "naukri.com", "indeed.com", "indeed.co.in", "glassdoor.com", "glassdoor.co.in")


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def denied(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in DENIED_HOST_SUFFIXES)


class _Bucket:
    def __init__(self, rps: float) -> None:
        self.rps = rps
        self.tokens = 1.0
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def take(self) -> float:
        """Reserve one request; returns how long the caller must wait first."""
        with self.lock:
            now = time.monotonic()
            self.tokens = min(1.0, self.tokens + (now - self.updated) * self.rps)
            self.updated = now
            self.tokens -= 1.0
            return 0.0 if self.tokens >= 0 else -self.tokens / self.rps


class HostLimiter:
    """``with limiter.slot(host): ...`` waits for a global slot, a per-host slot and a token for that host."""

    def __init__(self, global_in_flight: int = GLOBAL_IN_FLIGHT, per_host: int = PER_HOST_IN_FLIGHT,
                 rps: dict[str, float] | None = None, sleep=time.sleep) -> None:
        self._global = threading.BoundedSemaphore(global_in_flight)
        self._per_host = per_host
        self._rps = {**HOST_RPS, **(rps or {})}
        self._hosts: dict[str, tuple[threading.BoundedSemaphore, _Bucket]] = {}
        self._lock = threading.Lock()
        self._sleep = sleep

    def _host(self, host: str) -> tuple[threading.BoundedSemaphore, _Bucket]:
        with self._lock:
            if host not in self._hosts:
                self._hosts[host] = (threading.BoundedSemaphore(self._per_host), _Bucket(self._rps.get(host, DEFAULT_RPS)))
            return self._hosts[host]

    def slot(self, host: str) -> "_Slot":
        if denied(host):
            raise PermissionError(f"{host} is never crawled")
        sem, bucket = self._host(host)
        return _Slot(self, sem, bucket)


class _Slot:
    def __init__(self, limiter: HostLimiter, sem: threading.BoundedSemaphore, bucket: _Bucket) -> None:
        self.limiter, self.sem, self.bucket = limiter, sem, bucket

    def __enter__(self) -> None:
        self.sem.acquire()
        self.limiter._global.acquire()
        wait = self.bucket.take()
        if wait > 0:
            self.limiter._sleep(wait)

    def __exit__(self, *exc: object) -> None:
        self.limiter._global.release()
        self.sem.release()
