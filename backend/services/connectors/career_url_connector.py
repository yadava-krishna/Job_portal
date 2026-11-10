"""backend/services/connectors/career_url_connector.py

Automatic company career-page discovery and ATS auto-detection connector.

Flow:
1. Validates destination against SSRF (global IP, HTTPS 443 only, DNS pinning).
2. Inspects robots.txt compliance.
3. Detects known ATS platforms (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee).
4. Inspects Schema.org JobPosting JSON-LD.
5. Searches for sitemaps and RSS/Atom vacancy feeds.
6. Falls back to HTML table/card extraction.
7. Normalizes and validates discovered jobs into the pipeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from backend.services.ats import base as ats_base
from backend.services.connectors.base_connector import BaseConnector
from backend.services.connectors.html_connector import HtmlConnector
from backend.services.connectors.jsonld_connector import extract_jsonld_from_html
from backend.services.connectors.rss_connector import parse_feed_xml
from backend.services.connectors.sitemap_connector import parse_sitemap_urls
from backend.services.normalization import NormalizedJob
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)

# Patterns identifying supported ATS platforms from links, scripts, and embeds
ATS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("greenhouse", re.compile(r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("lever", re.compile(r"(?:jobs(?:\.eu)?\.lever\.co|api(?:\.eu)?\.lever\.co/v0/postings)/([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("ashby", re.compile(r"(?:jobs\.ashbyhq\.com|api\.ashbyhq\.com/posting-api/job-board)/([A-Za-z0-9][A-Za-z0-9._%-]{0,119})", re.I)),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("smartrecruiters", re.compile(r"api\.smartrecruiters\.com/v1/companies/([A-Za-z0-9][A-Za-z0-9._-]{0,119})", re.I)),
    ("recruitee", re.compile(r"https?://([a-z0-9][a-z0-9-]{0,62})\.recruitee\.com", re.I)),
]

FEED_LINK_PATTERN = re.compile(
    r'<link[^>]+type=["\'](?:application/rss\+xml|application/atom\+xml)["\'][^>]+href=["\']([^"\']+)["\']',
    re.I
)


@dataclass
class CareerAnalysisResult:
    url: str
    company_name: str
    detected_ats: str | None = None
    ats_token: str | None = None
    has_json_ld: bool = False
    json_ld_count: int = 0
    discovered_feed_url: str | None = None
    discovered_sitemap_url: str | None = None
    jobs: list[NormalizedJob] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class CareerUrlConnector(BaseConnector):
    """High-priority connector for automated company career URL exploration."""

    source_id = "user_career_url"
    name = "Company Career Page Auto-Discovery"
    domain = "*"
    category = SourceCategory.CAREER_PAGE
    access_method = AccessMethod.HTML

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client
        self.html_connector = HtmlConnector(self.client)

    def analyze_career_url(self, url: str, company_hint: str | None = None) -> CareerAnalysisResult:
        """Deeply inspect a company career URL to determine ATS, feeds, and jobs."""
        url = url.strip()
        domain = urlparse(url).netloc.lower()
        company = company_hint or domain.split(".")[0].title()

        result = CareerAnalysisResult(
            url=url,
            company_name=company,
        )

        try:
            resp = self.client.fetch_page(url)
        except Exception as exc:
            result.errors.append(f"Failed to fetch {url}: {exc}")
            return result

        page_html = resp.text

        # 1. Detect ATS embeds
        for provider, pattern in ATS_PATTERNS:
            match = pattern.search(page_html)
            if match:
                token = match.group(1).lower()
                result.detected_ats = provider
                result.ats_token = token
                break

        # If ATS found, attempt fetching official board jobs
        if result.detected_ats and result.ats_token:
            try:
                board_res = ats_base.fetch_board(result.detected_ats, result.ats_token, company_name=company)
                result.jobs.extend(board_res.jobs)
                return result
            except Exception as exc:
                result.errors.append(f"ATS board fetch for {result.detected_ats}:{result.ats_token} failed: {exc}")

        # 2. Extract JSON-LD JobPosting
        jsonld_jobs = extract_jsonld_from_html(page_html, resp.url, fallback_company=company)
        if jsonld_jobs:
            result.has_json_ld = True
            result.json_ld_count = len(jsonld_jobs)
            result.jobs.extend(jsonld_jobs)

        # 3. Discover RSS/Atom Feeds in header
        feed_match = FEED_LINK_PATTERN.search(page_html)
        if feed_match:
            feed_url = urljoin(url, feed_match.group(1))
            result.discovered_feed_url = feed_url
            try:
                feed_resp = self.client.fetch_feed(feed_url)
                feed_jobs = parse_feed_xml(feed_resp.text, feed_url, default_company=company)
                result.jobs.extend(feed_jobs)
            except Exception as exc:
                result.errors.append(f"Discovered feed fetch failed: {exc}")

        # 4. Probe for sitemap
        sitemap_candidate = f"{urlparse(url).scheme}://{domain}/sitemap.xml"
        try:
            sm_resp = self.client.fetch_sitemap(sitemap_candidate)
            if sm_resp.status == 200 and "<urlset" in sm_resp.text:
                result.discovered_sitemap_url = sitemap_candidate
        except Exception:
            pass

        # 5. If no jobs yet discovered, try heuristic HTML card extraction
        if not result.jobs:
            html_jobs = self.html_connector.extract_from_html(page_html, resp.url, {}, company_name=company)
            result.jobs.extend(html_jobs)

        return result

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        urls = (criteria or {}).get("urls", [])
        company_name = (criteria or {}).get("company")
        all_jobs: list[NormalizedJob] = []

        for u in urls:
            res = self.analyze_career_url(u, company_hint=company_name)
            for j in res.jobs:
                valid, _ = self.validate_job(j)
                if valid:
                    all_jobs.append(j)

        self.record_success(len(all_jobs))
        return all_jobs
