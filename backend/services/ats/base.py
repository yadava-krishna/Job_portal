"""HTTP access and error handling shared by the ATS board clients."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx

from backend.config import VERSION
from backend.services.normalization import NormalizedJob

USER_AGENT = f"JobPilot/{VERSION} (job-board API reader; +https://github.com/yadava-krishna/Job_portal)"
MAX_BYTES = 25 * 1024 * 1024
TIMEOUT = httpx.Timeout(25.0, connect=8.0)
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")

# Tests replace this with an httpx.MockTransport; production uses the default network transport.
transport_override: httpx.BaseTransport | None = None


class AtsError(Exception):
    """kind: not_found (board does not exist), transient (retry later), invalid (unexpected response)."""

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


def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
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
