"""backend/services/connectors/ncs_connector.py

National Career Service (NCS India) public portal connector.
Discovers public sector and certified vacancies from ncs.gov.in.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

from backend.services.connectors.base_connector import BaseConnector
from backend.services.connectors.jsonld_connector import extract_jsonld_from_html
from backend.services.normalization import (
    NormalizedJob,
    canonical_url,
    local_date,
    work_mode as normalize_work_mode,
)
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)

NCS_PORTAL_URL = "https://www.ncs.gov.in"


class NcsConnector(BaseConnector):
    """National Career Service (Government of India) vacancy connector."""

    source_id = "ncs_india"
    name = "National Career Service (NCS)"
    domain = "ncs.gov.in"
    category = SourceCategory.GOVERNMENT
    access_method = AccessMethod.HTML

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        crit = criteria or {}
        jobs: list[NormalizedJob] = []

        # Target NCS public job listing page
        url = crit.get("url") or f"{NCS_PORTAL_URL}/job-search"

        try:
            resp = self.client.fetch_page(url, source_id=self.source_id)

            # 1. Try JSON-LD first
            jobs = extract_jsonld_from_html(resp.text, resp.url, fallback_company="Government of India")
            for j in jobs:
                j.source = "ncs_india"
                j.platform = "NCS India"
                j.country = "IN"

            # 2. If no JSON-LD, parse vacancy list cards using Scrapling
            if not jobs:
                cards = resp.css(".job-card, .search-result-item, .vacancy-row, tr.job-item")
                for card in cards:
                    title = (card.css("h3 a::text, .job-title::text, a::text").get("") or "").strip()
                    if not title or len(title) < 3:
                        continue
                    link_href = card.css("a::attr(href)").get("") or ""
                    job_url = urljoin(resp.url, link_href) if link_href else resp.url
                    company = (card.css(".org-name::text, .company-name::text").get("") or "Public Sector / NCS").strip()
                    location = (card.css(".location::text, .city::text").get("") or "India").strip()
                    desc = (card.css(".description::text, .desc::text").get("") or f"NCS Job vacancy: {title}").strip()
                    date_str = (card.css(".date::text, .posted-on::text").get("") or "").strip()
                    posted_at = None
                    if date_str:
                        try:
                            posted_at = local_date(date_str[:10])
                        except Exception:
                            posted_at = None

                    job = NormalizedJob(
                        source="ncs_india",
                        source_key=f"ncs:{canonical_url(job_url) or job_url}",
                        platform="NCS India",
                        company=company,
                        title=title,
                        job_url=job_url,
                        application_url=job_url,
                        location=location,
                        country="IN",
                        work_mode=normalize_work_mode(location, title),
                        description=desc,
                        posted_at=posted_at,
                        posted_at_source="platform_page" if posted_at else None,
                        source_name="National Career Service",
                        extraction_method="html_css",
                        extraction_confidence=0.85,
                        parser_version="1.0.0",
                    )
                    valid, _ = self.validate_job(job)
                    if valid:
                        jobs.append(job)

        except Exception as exc:
            log.warning("NCS discovery error: %s", exc)
            self.record_failure(str(exc))
            return []

        self.record_success(len(jobs))
        return jobs
