"""backend/services/connectors/sitemap_connector.py

Discovers job listing pages from XML sitemaps using Scrapling.
"""

from __future__ import annotations

import gzip
import logging
import re
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from backend.services.connectors.base_connector import BaseConnector
from backend.services.connectors.jsonld_connector import extract_jsonld_from_html
from backend.services.normalization import NormalizedJob
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)

CAREER_URL_PATTERNS = [
    re.compile(r"/(?:careers?|jobs?|openings?|vacanc(?:y|ies)|positions?)/[a-zA-Z0-9_\-\./]+", re.I),
]


def parse_sitemap_urls(xml_content: str | bytes, sitemap_url: str) -> tuple[list[str], list[str]]:
    """Parse XML sitemap returning (sub_sitemap_urls, page_urls)."""
    sub_sitemaps: list[str] = []
    page_urls: list[str] = []

    # Handle gzip bytes if needed
    if isinstance(xml_content, bytes) and xml_content.startswith(b"\x1f\x8b"):
        try:
            xml_content = gzip.decompress(xml_content).decode("utf-8", errors="replace")
        except Exception:
            return [], []
    elif isinstance(xml_content, bytes):
        xml_content = xml_content.decode("utf-8", errors="replace")

    try:
        root = ET.fromstring(xml_content)
    except Exception as exc:
        log.warning("Sitemap XML parse failed for %s: %s", sitemap_url, exc)
        return [], []

    # Namespace removal for easy xpath
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    # Sitemap index
    if root.tag == "sitemapindex":
        for sm in root.findall(".//sitemap/loc"):
            if sm.text and sm.text.strip():
                sub_sitemaps.append(sm.text.strip())

    # Regular urlset
    if root.tag == "urlset":
        for loc in root.findall(".//url/loc"):
            if loc.text and loc.text.strip():
                page_urls.append(loc.text.strip())

    return sub_sitemaps, page_urls


class SitemapConnector(BaseConnector):
    """Connector discovering vacancies through company sitemaps."""

    source_id = "sitemap"
    name = "XML Sitemap Vacancy Discovery"
    domain = "*"
    category = SourceCategory.SITEMAP
    access_method = AccessMethod.SITEMAP

    def __init__(self, scrapling_client: ScraplingClient | None = None, max_urls_per_site: int = 20):
        super().__init__()
        self.client = scrapling_client or default_client
        self.max_urls_per_site = max_urls_per_site

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        sitemap_urls = (criteria or {}).get("sitemap_urls", [])
        company_name = (criteria or {}).get("company")
        jobs: list[NormalizedJob] = []

        for sm_url in sitemap_urls:
            try:
                resp = self.client.fetch_sitemap(sm_url)
                subs, urls = parse_sitemap_urls(resp.text, resp.url)

                # Process any sub-sitemaps that look career-related
                for sub in subs:
                    if any(kw in sub.lower() for kw in ("job", "career", "opening", "vacancy")):
                        try:
                            sub_resp = self.client.fetch_sitemap(sub)
                            _, sub_urls = parse_sitemap_urls(sub_resp.text, sub_resp.url)
                            urls.extend(sub_urls)
                        except Exception as exc:
                            log.debug("Sub-sitemap fetch failed %s: %s", sub, exc)

                # Filter urls matching career patterns
                career_urls: list[str] = []
                for u in urls:
                    if any(pat.search(u) for pat in CAREER_URL_PATTERNS):
                        career_urls.append(u)

                # Bounded fetch of individual career pages
                career_urls = career_urls[:self.max_urls_per_site]

                for target_url in career_urls:
                    try:
                        page_resp = self.client.fetch_page(target_url)
                        extracted = extract_jsonld_from_html(page_resp.text, page_resp.url, fallback_company=company_name)
                        for j in extracted:
                            j.extraction_method = "sitemap_jsonld"
                            valid, _ = self.validate_job(j)
                            if valid:
                                jobs.append(j)
                    except Exception as exc:
                        log.debug("Page extraction failed for %s: %s", target_url, exc)

            except Exception as exc:
                log.warning("Sitemap crawl error on %s: %s", sm_url, exc)

        self.record_success(len(jobs))
        return jobs
