"""Find the official job board behind a company's careers page.

A user pastes https://www.example.com/careers; JobPilot reads that one page (like a browser would), looks for links
or embeds of a supported job-board provider, and checks the board through the provider's official API before it
is added. Nothing else on the site is crawled.

The URL comes from a user, so the fetch is locked down against server-side request forgery: https on port 443
only, no credentials in the URL, every address the name resolves to must be public, the connection goes to the
vetted address itself (TLS still verified against the hostname, so DNS cannot be switched in between), each
redirect is re-checked, and size and time are capped.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from backend.services.ats import base as ats_base

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# (provider, pattern capturing the board token) found in links, iframes and scripts.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("greenhouse", re.compile(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("lever", re.compile(r"(?:jobs(?:\.eu)?\.lever\.co|api(?:\.eu)?\.lever\.co/v0/postings)/([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("ashby", re.compile(r"(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com/posting-api/job-board)/([A-Za-z0-9][A-Za-z0-9._%-]{0,119})", re.I)),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("smartrecruiters", re.compile(r"api\.smartrecruiters\.com/v1/companies/([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("recruitee", re.compile(r"https?://([a-z0-9][a-z0-9-]{0,62})\.recruitee\.com", re.I)),
]
NOT_TOKENS = {"embed", "js", "jobs", "job_board", "v0", "v1", "api", "www", "app", "docs", "static", "assets", "careers", "oauth"}


class CareersPageError(Exception):
    pass


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise CareersPageError("That website could not be found.") from exc
    return sorted({i[4][0] for i in infos})


def check_url(url: str) -> tuple[str, str]:
    """(hostname, a vetted public IP) for an allowed careers-page URL, or CareersPageError."""
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise CareersPageError("That is not a valid web address.") from exc
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or not host or parts.username or parts.password or parts.port not in (None, 443):
        raise CareersPageError("Use the company's https careers page address, e.g. https://www.example.com/careers.")
    try:
        ipaddress.ip_address(host)
        raise CareersPageError("Use the company's website name, not an IP address.")
    except ValueError:
        pass
    if "." not in host or host.endswith((".local", ".internal", ".localhost", ".lan", ".home", ".corp")):
        raise CareersPageError("That is not a public website.")
    addrs = _resolve(host)
    if not addrs or not all(ipaddress.ip_address(a).is_global for a in addrs):
        raise CareersPageError("That address is not a public website.")
    v4 = [a for a in addrs if ":" not in a]
    return host, (v4 or addrs)[0]  # prefer IPv4: many hosts have no IPv6 route


def fetch_page(url: str) -> tuple[str, str]:
    """(final URL, HTML) of a public careers page."""
    for _ in range(MAX_REDIRECTS + 1):
        host, ip = check_url(url)
        parts = urlsplit(url)
        if ats_base.transport_override is not None:  # tests: no real network, no DNS pinning
            target, extensions = url, {}
        else:
            netloc = f"[{ip}]" if ":" in ip else ip
            target, extensions = urlunsplit(("https", netloc, parts.path or "/", parts.query, "")), {"sni_hostname": host}
        try:
            with httpx.Client(timeout=TIMEOUT, transport=ats_base.transport_override, follow_redirects=False,
                              headers={"User-Agent": ats_base.USER_AGENT, "Accept": "text/html", "Host": host}) as client:
                with client.stream("GET", target, extensions=extensions) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        url = urljoin(url, r.headers["location"])
                        continue
                    if r.status_code != 200:
                        raise CareersPageError(f"The page could not be read (HTTP {r.status_code}).")
                    body = bytearray()
                    for chunk in r.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                    return url, bytes(body).decode("utf-8", "replace")
        except httpx.HTTPError as exc:
            raise CareersPageError("The page could not be reached.") from exc
    raise CareersPageError("The page redirects too many times.")


def find_boards(html: str) -> list[tuple[str, str]]:
    """Distinct (provider, token) candidates referenced by the page, in order of appearance."""
    found: list[tuple[int, str, str]] = []
    for ats, rx in PATTERNS:
        for m in rx.finditer(html):
            token = m.group(1).split("?")[0].split("#")[0].rstrip(".")
            if token.lower() in NOT_TOKENS:
                continue
            found.append((m.start(), ats, token))
    out: list[tuple[str, str]] = []
    for _, ats, token in sorted(found):
        if (ats, token.lower()) not in {(a, t.lower()) for a, t in out}:
            out.append((ats, token))
    return out[:5]
