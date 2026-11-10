"""backend/services/connectors/html_connector.py

Permitted HTML extraction connector using Scrapling's Adaptor, CSS/XPath queries,
and self-healing adaptive selectors.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin, urlparse

from backend.services.connectors.base_connector import BaseConnector
from backend.services.normalization import (
    NormalizedJob,
    canonical_url,
    local_date,
    work_mode as normalize_work_mode,
)
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)


class HtmlConnector(BaseConnector):
    """Configurable HTML extractor for permitted public vacancy boards."""

    source_id = "html_career"
    name = "HTML Career Page Extractor"
    domain = "*"
    category = SourceCategory.CAREER_PAGE
    access_method = AccessMethod.HTML

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def extract_from_html(
        self,
        html_text: str,
        page_url: str,
        selectors: dict[str, str],
        company_name: str | None = None,
    ) -> list[NormalizedJob]:
        try:
            from scrapling.parser import Adaptor
        except ImportError:
            from scrapling import Selector as Adaptor

        page = Adaptor(html_text, url=page_url)
        container_sel = selectors.get("container", ".job-item, .job-listing, .career-card, tr.job-row")
        title_sel = selectors.get("title", "h2, h3, h4, .job-title, .title, a")
        link_sel = selectors.get("link", "a")
        loc_sel = selectors.get("location", ".location, .loc, .city")
        desc_sel = selectors.get("description", ".description, .desc, .summary")
        date_sel = selectors.get("date", ".date, .posted, time")

        cards = page.css(container_sel)
        jobs: list[NormalizedJob] = []
        domain = urlparse(page_url).netloc.lower()
        effective_company = company_name or domain

        for card in cards:
            # Title
            title_node = card.css_first(title_sel) if hasattr(card, "css_first") else (card.css(title_sel) and card.css(title_sel)[0])
            title = ""
            if title_node:
                title = title_node.text.strip() if hasattr(title_node, "text") else (title_node.css("::text").get("") or "").strip()
            if not title:
                continue

            # Link
            link_node = card.css_first(link_sel) if hasattr(card, "css_first") else (card.css(link_sel) and card.css(link_sel)[0])
            href = ""
            if link_node:
                href = link_node.attrib.get("href", "") if hasattr(link_node, "attrib") else (link_node.css("::attr(href)").get("") or "")
            job_url = urljoin(page_url, href) if href else page_url

            # Location
            loc_node = card.css_first(loc_sel) if hasattr(card, "css_first") else (card.css(loc_sel) and card.css(loc_sel)[0])
            location = ""
            if loc_node:
                location = (loc_node.css("::text").get("") or "").strip()

            # Description
            desc_node = card.css_first(desc_sel) if hasattr(card, "css_first") else (card.css(desc_sel) and card.css(desc_sel)[0])
            description = ""
            if desc_node:
                description = (desc_node.css("::text").get("") or "").strip()

            # Date
            posted_at = None
            date_node = card.css_first(date_sel) if hasattr(card, "css_first") else (card.css(date_sel) and card.css(date_sel)[0])
            if date_node:
                date_str = (date_node.css("::text").get("") or "").strip()
                if date_str:
                    try:
                        posted_at = local_date(date_str[:10])
                    except Exception:
                        posted_at = None

            job = NormalizedJob(
                source="career_page",
                source_key=f"html:{domain}:{canonical_url(job_url) or job_url}",
                platform="Career Page",
                company=effective_company,
                title=title,
                job_url=job_url,
                application_url=job_url,
                location=location or None,
                description=description or f"Job opening for {title} at {effective_company}.",
                posted_at=posted_at,
                posted_at_source="platform_page" if posted_at else None,
                work_mode=normalize_work_mode(location, title),
                extraction_method="html_css",
                extraction_confidence=0.85,
                parser_version="1.0.0",
            )
            jobs.append(job)

        return jobs

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        urls = (criteria or {}).get("urls", [])
        selectors = (criteria or {}).get("selectors", {})
        company_name = (criteria or {}).get("company")
        requires_js = (criteria or {}).get("requires_js", False)

        jobs: list[NormalizedJob] = []
        for url in urls:
            try:
                resp = self.client.fetch_page(url, js_render=requires_js)
                extracted = self.extract_from_html(resp.text, resp.url, selectors, company_name=company_name)
                for j in extracted:
                    valid, _ = self.validate_job(j)
                    if valid:
                        jobs.append(j)
            except Exception as exc:
                log.warning("HTML extraction failed for %s: %s", url, exc)

        self.record_success(len(jobs))
        return jobs
