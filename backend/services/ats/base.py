"""HTTP access and error handling shared by the ATS board clients."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from backend.config import VERSION
from backend.services.normalization import NormalizedJob

USER_AGENT = f"JobPilot/{VERSION} (job-board API reader; +https://github.com/yadava-krishna/Job_portal)"
MAX_BYTES = 64 * 1024 * 1024  # some Ashby boards return every full job ad in one response (Bjak: ~34 MB)
TIMEOUT = httpx.Timeout(25.0, connect=8.0)
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")

# Tests replace this with an httpx.MockTransport; production uses the default network transport.
transport_override: httpx.BaseTransport | None = None


class AtsError(Exception):
    """kind: not_found (board does not exist), transient (retry later), invalid (unexpected response),
    not_modified (crawl context only: the board answered 304 to our ETag, so nothing changed)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass
class BoardResult:
    ats: str
    token: str
    company_name: str | None
    jobs: list[NormalizedJob] = field(default_factory=list)
    skipped: int = 0  # unlisted or unusable postings


# Pauses before retrying a board that timed out or answered 429/5xx. A busy board often answers on the next try.
RETRY_DELAYS: tuple[float, ...] = (2.0, 6.0)


class CrawlContext:
    """Opt-in per-thread fetch settings used by the background crawler (backend/services/crawler).

    - one pooled HTTP client per worker thread, so a host's connections are reused across boards;
    - ``etag``: sent as If-None-Match on the board's first request; a 304 raises AtsError("not_modified");
    - after the fetch, ``etag_out`` holds the board's new ETag and ``body_hash`` a fingerprint of every response body.

    Code that never enters a CrawlContext (saved-search runs, company lookups, tests) behaves exactly as before.
    """

    _local = threading.local()
    _all_clients: "list[httpx.Client]" = []
    _clients_lock = threading.Lock()

    def __init__(self, etag: str | None = None, *, conditional: bool = True) -> None:
        self.etag = etag if conditional else None
        self.etag_out: str | None = None
        self.requests = 0
        self.got_first = False  # the board's first page answered (a retried first request still counts as first)
        self.bytes = 0
        self._hash = hashlib.blake2b(digest_size=16)

    @property
    def body_hash(self) -> str:
        return self._hash.hexdigest()

    def __enter__(self) -> "CrawlContext":
        CrawlContext._local.current = self
        return self

    def __exit__(self, *exc: object) -> None:
        CrawlContext._local.current = None

    @classmethod
    def current(cls) -> "CrawlContext | None":
        return getattr(cls._local, "current", None)

    @classmethod
    def client(cls) -> httpx.Client:
        c = getattr(cls._local, "client", None)
        if c is None or c.is_closed:
            c = httpx.Client(timeout=TIMEOUT, transport=transport_override, follow_redirects=True,
                             headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                             limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=60))
            cls._local.client = c
            with cls._clients_lock:
                cls._all_clients.append(c)
        return c

    @classmethod
    def close_all(cls) -> None:
        """Close every worker thread's pooled client (end of a crawl tick)."""
        with cls._clients_lock:
            clients, cls._all_clients = cls._all_clients, []
        for c in clients:
            try:
                c.close()
            except Exception:
                pass


def get_json(url: str, params: dict[str, Any] | None = None, *, retry: bool = True) -> Any:
    """GET a job-board JSON document; transient failures are retried (RETRY_DELAYS) before giving up.

    retry=False makes one attempt only (for requests a person is waiting on, which fall back to something else)."""
    for delay in (*(RETRY_DELAYS if retry else ()), None):
        try:
            return _get_json_once(url, params)
        except AtsError as exc:
            if exc.kind != "transient" or delay is None:
                raise
            time.sleep(delay)
    raise AssertionError("unreachable")


def _get_json_once(url: str, params: dict[str, Any] | None = None) -> Any:
    ctx = CrawlContext.current()
    if ctx is not None:
        return _crawl_get_json(ctx, url, params)
    try:
        with httpx.Client(timeout=TIMEOUT, transport=transport_override, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as client:
            with client.stream("GET", url, params=params) as r:
                if r.status_code == 404:
                    raise AtsError("not_found", "Job board not found (the company may have moved or renamed its board).")
                if r.status_code == 429 or r.status_code >= 500:
                    raise AtsError("transient", f"Job board temporarily unavailable (HTTP {r.status_code}).")
                if r.status_code >= 400:
                    raise AtsError("invalid", f"Job board request failed (HTTP {r.status_code}).")
                body = bytearray()
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise AtsError("invalid", "Job board response is too large.")
    except httpx.TimeoutException as exc:
        raise AtsError("transient", "Job board timed out.") from exc
    except httpx.HTTPError as exc:
        raise AtsError("transient", f"Job board unreachable ({type(exc).__name__}).") from exc
    try:
        return json.loads(bytes(body))
    except ValueError as exc:
        raise AtsError("invalid", "Job board returned a response that is not JSON.") from exc


def _crawl_get_json(ctx: CrawlContext, url: str, params: dict[str, Any] | None) -> Any:
    """Same status handling and size limit as _get_json_once, on the thread's pooled client, with ETag support."""
    first = not ctx.got_first
    ctx.requests += 1
    headers = {"If-None-Match": ctx.etag} if first and ctx.etag else {}
    try:
        with CrawlContext.client().stream("GET", url, params=params, headers=headers) as r:
            if r.status_code == 304 and headers:
                ctx.etag_out, ctx.got_first = r.headers.get("etag") or ctx.etag, True
                raise AtsError("not_modified", "Not modified since the last crawl.")
            if r.status_code == 404:
                raise AtsError("not_found", "Job board not found (the company may have moved or renamed its board).")
            if r.status_code == 429 or r.status_code >= 500:
                raise AtsError("transient", f"Job board temporarily unavailable (HTTP {r.status_code}).")
            if r.status_code >= 400:
                raise AtsError("invalid", f"Job board request failed (HTTP {r.status_code}).")
            if first:
                ctx.etag_out = r.headers.get("etag")
                ctx.got_first = True
            body = bytearray()
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) > MAX_BYTES:
                    raise AtsError("invalid", "Job board response is too large.")
    except httpx.TimeoutException as exc:
        raise AtsError("transient", "Job board timed out.") from exc
    except httpx.HTTPError as exc:
        raise AtsError("transient", f"Job board unreachable ({type(exc).__name__}).") from exc
    ctx.bytes += len(body)
    ctx._hash.update(bytes(body))
    try:
        return json.loads(bytes(body))
    except ValueError as exc:
        raise AtsError("invalid", "Job board returned a response that is not JSON.") from exc


def valid_token(token: str) -> str:
    token = (token or "").strip()
    if not TOKEN_RE.match(token):
        raise AtsError("invalid", "That doesn't look like a job-board name.")
    return token


def get_page(url: str, *, max_bytes: int = 2 * 1024 * 1024) -> tuple[int, str]:
    """(status, text) of a public page, without following redirects (a redirect means "not this page")."""
    try:
        with httpx.Client(timeout=TIMEOUT, transport=transport_override, follow_redirects=False,
                          headers={"User-Agent": USER_AGENT, "Accept": "text/html"}) as client:
            with client.stream("GET", url) as r:
                body = bytearray()
                if r.status_code == 200:
                    for chunk in r.iter_bytes():
                        body += chunk
                        if len(body) > max_bytes:
                            raise AtsError("invalid", "Page is too large.")
                return r.status_code, bytes(body).decode("utf-8", "replace")
    except httpx.TimeoutException as exc:
        raise AtsError("transient", "Page timed out.") from exc
    except httpx.HTTPError as exc:
        raise AtsError("transient", f"Page unreachable ({type(exc).__name__}).") from exc


def fetch_board(ats: str, token: str, *, company_name: str | None = None, region: str | None = None) -> BoardResult:
    from backend.services.ats import ashby, greenhouse, lever, recruitee, smartrecruiters

    fetchers: dict[str, Callable[..., BoardResult]] = {"greenhouse": greenhouse.fetch, "lever": lever.fetch, "ashby": ashby.fetch,
                                                        "smartrecruiters": smartrecruiters.fetch, "recruitee": recruitee.fetch}
    if ats not in fetchers:
        raise AtsError("invalid", f"Unsupported job board type: {ats}")
    return fetchers[ats](valid_token(token), company_name=company_name, region=region)


_BOARD_PATTERNS = (
    ("greenhouse", re.compile(r"^(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io$"), 0),
    ("greenhouse", re.compile(r"^boards-api\.greenhouse\.io$"), 2),  # /v1/boards/{token}/...
    ("lever", re.compile(r"^jobs\.(?:eu\.)?lever\.co$"), 0),
    ("ashby", re.compile(r"^jobs\.ashbyhq\.com$"), 0),
    ("smartrecruiters", re.compile(r"^(?:jobs|careers)\.smartrecruiters\.com$"), 0),
    ("smartrecruiters", re.compile(r"^api\.smartrecruiters\.com$"), 2),  # /v1/companies/{token}/postings
)
_RECRUITEE = re.compile(r"^([a-z0-9][a-z0-9-]{0,62})\.recruitee\.com$")


def parse_board_url(url: str) -> tuple[str, str, str | None]:
    """A public board or job URL → (ats, token, region). Raises AtsError('invalid') for anything else."""
    try:
        parts = urlsplit(url.strip() if "://" in url else f"https://{url.strip()}")
    except ValueError as exc:
        raise AtsError("invalid", "That is not a valid URL.") from exc
    host = parts.netloc.lower().split(":")[0]
    segments = [s for s in parts.path.split("/") if s]
    for ats, pattern, index in _BOARD_PATTERNS:
        if pattern.match(host) and len(segments) > index:
            token = segments[index]
            if ats == "greenhouse" and token == "embed":  # boards.greenhouse.io/embed/job_board?for=token
                token = dict(p.split("=", 1) for p in parts.query.split("&") if "=" in p).get("for", "")
            region = "eu" if ats == "lever" and host.startswith("jobs.eu.") else None
            return ats, valid_token(token), region
    m = _RECRUITEE.match(host)
    if m and m.group(1) not in ("www", "app", "api", "docs"):
        return "recruitee", valid_token(m.group(1)), None
    raise AtsError("invalid", "Use a Greenhouse, Lever, Ashby, SmartRecruiters or Recruitee job-board link (e.g. https://jobs.lever.co/company).")
