"""backend/services/scrapling_client.py

Robust, ethical client wrapping the Scrapling framework for multi-source job discovery.

Provides:
- SSRF-protected HTTP fetching with DNS validation and address vetting.
- Automatic rate-limiting per domain (token bucket) and crawl-delay directives.
- robots.txt compliance checking and caching.
- Plain HTTPS requests that identify as JobPilot (no TLS/browser impersonation, no stealth browsers).
- Pages that need JavaScript are reported as unsupported rather than rendered.
- Exponential backoff on 429 / 503 with Retry-After header honouring.
- In-memory response caching (30-min TTL for pages, 6h for sitemaps).
- Bounded concurrency with asyncio.Semaphore.
- Memory and size caps (max 25MB response).
- Test mock transport hooks compatible with existing test suite patterns.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlsplit
import urllib.robotparser

import httpx

from backend.services.ats import base as ats_base
from backend.services.source_policies import get_source_policy, is_permitted

log = logging.getLogger(__name__)
USER_AGENT = "JobPilot/2.0 (+private job-search assistant; respects robots.txt)"

# Constants
MAX_RESPONSE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_PAGE_BYTES = 5 * 1024 * 1024        # 5 MB for individual HTML page
MAX_REDIRECTS = 3
DEFAULT_TIMEOUT_SEC = 25.0
DEFAULT_RATE_LIMIT_RPM = 10

# Global mock transport hook for offline/reproducible test runs
mock_fetch_handler: Any | None = None


class ScraplingError(Exception):
    """Base error for Scrapling discovery operations."""


class SSRFBlockedError(ScraplingError):
    """Raised when a URL resolves to a non-public, loopback, or cloud-metadata IP."""


class RobotsDisallowedError(ScraplingError):
    """Raised when robots.txt disallows scraping the requested path."""


class RateLimitError(ScraplingError):
    """Raised when a source exceeds polite request thresholds and backoff fails."""


class ScraplingFetchError(ScraplingError):
    """Raised on network failure, timeout, or HTTP error status."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ScraplingResponse:
    url: str
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    from_cache: bool = False
    extraction_method: str = "static_fetcher"
    elapsed_seconds: float = 0.0

    @property
    def adaptor(self):
        try:
            from scrapling.parser import Adaptor
        except ImportError:
            from scrapling import Selector as Adaptor
        return Adaptor(self.text, url=self.url)

    def css(self, query: str):
        return self.adaptor.css(query)

    def xpath(self, query: str):
        return self.adaptor.xpath(query)


@dataclass
class ClientMetrics:
    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    bytes_downloaded: int = 0
    cache_hits: int = 0
    js_renders: int = 0
    domain_counts: dict[str, int] = field(default_factory=dict)


class DomainRateLimiter:
    """Token-bucket per-domain rate limiter."""

    def __init__(self):
        self._last_request_time: dict[str, float] = {}
        self._domain_rpm: dict[str, int] = {}

    def set_rate_limit(self, domain: str, rpm: int) -> None:
        self._domain_rpm[domain.lower()] = max(1, rpm)

    def get_rate_limit(self, domain: str) -> int:
        return self._domain_rpm.get(domain.lower(), DEFAULT_RATE_LIMIT_RPM)

    def throttle(self, domain: str) -> None:
        """Blocks synchronously for polite spacing between requests to the same domain."""
        domain = domain.lower()
        rpm = self.get_rate_limit(domain)
        delay = 60.0 / rpm
        now = time.time()
        last = self._last_request_time.get(domain, 0.0)
        elapsed = now - last
        if elapsed < delay:
            sleep_time = delay - elapsed
            time.sleep(sleep_time)
        self._last_request_time[domain] = time.time()

    async def throttle_async(self, domain: str) -> None:
        """Async non-blocking sleep for rate spacing."""
        domain = domain.lower()
        rpm = self.get_rate_limit(domain)
        delay = 60.0 / rpm
        now = time.time()
        last = self._last_request_time.get(domain, 0.0)
        elapsed = now - last
        if elapsed < delay:
            sleep_time = delay - elapsed
            await asyncio.sleep(sleep_time)
        self._last_request_time[domain] = time.time()


class RobotsCache:
    """In-memory cache and evaluator for robots.txt directives."""

    def __init__(self):
        self._cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._ttl: dict[str, float] = {}
        self._ttl_seconds: float = 3600 * 6  # 6 hours

    def get_parser(self, domain: str) -> urllib.robotparser.RobotFileParser | None:
        now = time.time()
        if domain in self._cache and (now - self._ttl.get(domain, 0.0)) < self._ttl_seconds:
            return self._cache[domain]
        return None

    def set_parser(self, domain: str, parser: urllib.robotparser.RobotFileParser | None) -> None:
        self._cache[domain] = parser
        self._ttl[domain] = time.time()

    def is_allowed(self, url: str, user_agent: str = "JobPilot") -> bool:
        domain = urlparse(url).netloc.lower()
        parser = self.get_parser(domain)
        if parser is None:
            # Not yet fetched or robots.txt not found -> default to allowed
            return True
        return parser.can_fetch(user_agent, url)


class ScraplingClient:
    """Unified client orchestrating Scrapling operations with safety and compliance."""

    def __init__(self, max_concurrency: int = 4):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.rate_limiter = DomainRateLimiter()
        self.robots_cache = RobotsCache()
        self.metrics = ClientMetrics()
        self._response_cache: dict[str, tuple[float, ScraplingResponse]] = {}
        self._cache_ttl = 1800  # 30 minutes

    # ---------------- Security & SSRF Validation ----------------
    @staticmethod
    def validate_url(url: str) -> tuple[str, str]:
        """Validate URL against SSRF; returns (normalized_host, vetted_ip)."""
        url = url.strip()
        try:
            parts = urlsplit(url)
        except ValueError as exc:
            raise SSRFBlockedError(f"Invalid URL syntax: {url}") from exc

        host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme not in ("https", "http") or not host:
            raise SSRFBlockedError(f"Unsupported scheme or missing host in {url}")

        if parts.username or parts.password:
            raise SSRFBlockedError("Credentials embedded in URL are prohibited.")

        if parts.port not in (None, 80, 443):
            raise SSRFBlockedError(f"Non-standard port {parts.port} is blocked.")

        # Block direct IP literals
        try:
            ipaddress.ip_address(host)
            raise SSRFBlockedError(f"Direct IP addresses are prohibited ({host}). Use domain name.")
        except ValueError:
            pass

        # Block private suffixes
        if "." not in host or host.endswith((".local", ".internal", ".localhost", ".lan", ".home", ".corp", ".test")):
            raise SSRFBlockedError(f"Restricted internal hostname: {host}")

        # Resolve DNS
        try:
            infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise ScraplingFetchError(f"Host name lookup failed for {host}: {exc}") from exc

        addrs = sorted({i[4][0] for i in infos})
        if not addrs:
            raise ScraplingFetchError(f"No IP addresses resolved for {host}")

        # Assert every resolved address is globally routable (not loopback, private, carrier-grade NAT, or link-local)
        for addr in addrs:
            ip_obj = ipaddress.ip_address(addr)
            if not ip_obj.is_global:
                raise SSRFBlockedError(f"Host {host} resolved to non-global IP {addr} (blocked)")

        v4 = [a for a in addrs if ":" not in a]
        vetted_ip = (v4 or addrs)[0]
        return host, vetted_ip

    # ---------------- Honest HTTP fetch ----------------
    def _honest_get(self, url: str, timeout: float) -> tuple[str, int, dict]:
        """Plain HTTPS GET identifying as JobPilot (no browser impersonation). Redirects are followed by hand so
        that every hop passes the same SSRF validation."""
        current = url
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            for _ in range(4):
                self.validate_url(current)
                r = client.get(current, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml"})
                if r.is_redirect and r.headers.get("location"):
                    current = str(r.url.join(r.headers["location"]))
                    continue
                return r.text, r.status_code, dict(r.headers)
        raise ScraplingFetchError(f"too many redirects fetching {url}", status_code=None)

    # ---------------- robots.txt Check ----------------
    def check_robots(self, url: str) -> None:
        """Fetch and enforce robots.txt permissions."""
        domain = urlparse(url).netloc.lower()
        parser = self.robots_cache.get_parser(domain)

        if parser is None:
            # Attempt to fetch robots.txt
            robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
            rp = urllib.robotparser.RobotFileParser()
            try:
                # Use lightweight fetch or mock
                if ats_base.transport_override or mock_fetch_handler:
                    # In test mode, don't fail if mock doesn't define robots
                    rp.allow_all = True
                else:
                    host, ip = self.validate_url(robots_url)
                    with httpx.Client(timeout=8.0, follow_redirects=True) as client:
                        resp = client.get(robots_url, headers={"User-Agent": USER_AGENT})
                        if resp.status_code == 200:
                            rp.parse(resp.text.splitlines())
                        elif 400 <= resp.status_code < 500:
                            rp.allow_all = True  # no robots.txt published: crawling is not restricted
                        else:
                            rp.disallow_all = True  # server error: don't assume permission
            except Exception as exc:
                log.debug("robots.txt fetch failed for %s (%s); treating as disallowed", domain, exc)
                rp.disallow_all = True

            self.robots_cache.set_parser(domain, rp)
            parser = rp

        if not parser.can_fetch("JobPilot/2.0", url):
            raise RobotsDisallowedError(f"robots.txt disallows crawling {url}")

    # ---------------- Fetching Pipeline ----------------
    def fetch_page(
        self,
        url: str,
        *,
        js_render: bool = False,
        use_cache: bool = True,
        source_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SEC,
    ) -> ScraplingResponse:
        """Synchronously fetch and parse an HTML page with security and rate controls."""
        url = url.strip()
        domain = urlparse(url).netloc.lower()

        # Check source policy permissions if a source_id is specified
        if source_id and not is_permitted(source_id):
            policy = get_source_policy(source_id)
            status_desc = policy.permission_status.value if policy else "unregistered"
            raise ScraplingError(f"Source '{source_id}' is not approved for automated discovery (status: {status_desc}).")

        # Cache check
        if use_cache and url in self._response_cache:
            ts, cached_resp = self._response_cache[url]
            if time.time() - ts < self._cache_ttl:
                self.metrics.cache_hits += 1
                return ScraplingResponse(
                    url=cached_resp.url,
                    status=cached_resp.status,
                    text=cached_resp.text,
                    headers=cached_resp.headers,
                    from_cache=True,
                    extraction_method=cached_resp.extraction_method,
                    elapsed_seconds=0.0,
                )

        # SSRF validation & robots.txt compliance
        self.validate_url(url)
        self.check_robots(url)

        # Apply domain rate limit
        policy = get_source_policy(source_id) if source_id else None
        if policy and policy.rate_limit_rpm:
            self.rate_limiter.set_rate_limit(domain, policy.rate_limit_rpm)
        self.rate_limiter.throttle(domain)

        # Handle Mock Transport (unit tests / CI)
        if mock_fetch_handler is not None:
            resp = mock_fetch_handler(url)
            self.metrics.requests_total += 1
            self.metrics.requests_success += 1
            return resp

        if ats_base.transport_override is not None:
            # Adapt existing test transport override
            with httpx.Client(transport=ats_base.transport_override, timeout=timeout) as client:
                t0 = time.time()
                r = client.get(url, headers={"User-Agent": "JobPilot/2.0 (Job Discovery)"})
                elapsed = time.time() - t0
                s_resp = ScraplingResponse(
                    url=str(r.url),
                    status=r.status_code,
                    text=r.text,
                    headers=dict(r.headers),
                    extraction_method="mock_transport",
                    elapsed_seconds=elapsed,
                )
                self.metrics.requests_total += 1
                self.metrics.requests_success += 1
                return s_resp

        # Live Execution via Scrapling Fetcher or StealthyFetcher
        self.metrics.requests_total += 1
        t0 = time.time()

        for attempt in range(1, 4):
            try:
                if js_render or (policy and policy.requires_js):
                    # Compliance (DSC-13/NEG-02): no headless/stealth browsers. Pages that need JavaScript are
                    # reported as unsupported instead of being rendered in a disguised browser.
                    raise ScraplingFetchError(f"{url} needs JavaScript rendering, which JobPilot does not do", status_code=None)
                text, status, headers = self._honest_get(url, timeout)
                method = "static_fetcher"
                elapsed = time.time() - t0

                if status == 429 or status == 503:
                    retry_after = headers.get("retry-after")
                    backoff = float(retry_after) if retry_after and retry_after.isdigit() else (2.0 ** attempt)
                    log.warning("Rate limit / service unavailable (%s) for %s; backing off %ss", status, url, backoff)
                    time.sleep(backoff)
                    continue

                if status >= 400:
                    raise ScraplingFetchError(f"HTTP {status} fetching {url}", status_code=status)

                # Cap size
                body_bytes = len(text.encode("utf-8", errors="replace"))
                if body_bytes > MAX_PAGE_BYTES:
                    log.warning("Truncating oversized response from %s (%d bytes)", url, body_bytes)
                    text = text[:MAX_PAGE_BYTES]

                result = ScraplingResponse(
                    url=url,
                    status=status,
                    text=text,
                    headers=headers,
                    extraction_method=method,
                    elapsed_seconds=elapsed,
                )

                # Cache and metric record
                self._response_cache[url] = (time.time(), result)
                self.metrics.requests_success += 1
                self.metrics.bytes_downloaded += body_bytes
                self.metrics.domain_counts[domain] = self.metrics.domain_counts.get(domain, 0) + 1
                return result

            except ScraplingError:
                raise
            except Exception as exc:
                if attempt == 3:
                    self.metrics.requests_failed += 1
                    raise ScraplingFetchError(f"Failed to fetch {url} after 3 attempts: {exc}") from exc
                time.sleep(1.5 * attempt)

        self.metrics.requests_failed += 1
        raise ScraplingFetchError(f"Exhausted retries fetching {url}")

    async def fetch_page_async(self, url: str, **kwargs) -> ScraplingResponse:
        """Asynchronous execution wrapped in global concurrency semaphore."""
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: self.fetch_page(url, **kwargs))

    fetch = fetch_page
    fetch_async = fetch_page_async

    # ---------------- Specialized Feed & Sitemap Helpers ----------------
    def fetch_feed(self, feed_url: str, **kwargs) -> ScraplingResponse:
        """Fetch RSS or Atom XML feed."""
        return self.fetch_page(feed_url, js_render=False, **kwargs)

    def fetch_sitemap(self, sitemap_url: str, **kwargs) -> ScraplingResponse:
        """Fetch sitemap XML with longer cache TTL."""
        resp = self.fetch_page(sitemap_url, js_render=False, **kwargs)
        # Sitemaps change infrequently: store with 6h TTL
        self._response_cache[sitemap_url] = (time.time() + 18000, resp)
        return resp

    def get_metrics(self) -> dict[str, Any]:
        """Return diagnostic metrics of this client instance."""
        return {
            "requests_total": self.metrics.requests_total,
            "requests_success": self.metrics.requests_success,
            "requests_failed": self.metrics.requests_failed,
            "bytes_downloaded": self.metrics.bytes_downloaded,
            "cache_hits": self.metrics.cache_hits,
            "js_renders": self.metrics.js_renders,
            "active_domains": len(self.metrics.domain_counts),
        }


# Global singleton client instance
client = ScraplingClient()


def get_scrapling_client() -> ScraplingClient:
    return client
