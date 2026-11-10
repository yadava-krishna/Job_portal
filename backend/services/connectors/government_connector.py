"""backend/services/connectors/government_connector.py

Indian public sector, central commission, and PSU recruitment portal connector.
Covers UPSC, SSC, DRDO, ISRO, and State PSC vacancy announcements.
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
)
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)

# Official government vacancy URLs
GOV_PORTALS = {
    "upsc": {"name": "Union Public Service Commission (UPSC)", "url": "https://upsc.gov.in/recruitment/recruitment-advertisement"},
    "ssc": {"name": "Staff Selection Commission (SSC)", "url": "https://ssc.gov.in/notices"},
    "isro": {"name": "ISRO Recruitment Board (ICRB)", "url": "https://isro.gov.in/Careers.html"},
    "drdo": {"name": "DRDO Recruitment (RAC)", "url": "https://rac.gov.in"},
}


class GovernmentConnector(BaseConnector):
    """Discovers public notifications from Indian government portals."""

    source_id = "government"
    name = "Indian Public Sector & Government Portals"
    domain = "gov.in"
    category = SourceCategory.GOVERNMENT
    access_method = AccessMethod.HTML

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        crit = criteria or {}
        target_keys = crit.get("targets") or list(GOV_PORTALS.keys())
        discovered: list[NormalizedJob] = []

        for key in target_keys:
            portal_info = GOV_PORTALS.get(key)
            if not portal_info:
                continue

            portal_name = portal_info["name"]
            url = portal_info["url"]

            try:
                resp = self.client.fetch_page(url, source_id=self.source_id)

                # Try JSON-LD first
                jobs = extract_jsonld_from_html(resp.text, resp.url, fallback_company=portal_name)
                for j in jobs:
                    j.source = "government"
                    j.platform = portal_name
                    j.country = "IN"
                    discovered.append(j)

                # If no JSON-LD, parse tables / list items of notifications
                if not jobs:
                    rows = resp.css("table.views-table tr, table tr, .notice-item, .recruitment-row")
                    for row in rows:
                        title = (row.css("a::text, td:nth-child(2)::text, .title::text").get("") or "").strip()
                        if not title or len(title) < 5 or any(w in title.lower() for w in ("s.no", "serial", "download", "link")):
                            continue

                        link_href = row.css("a::attr(href)").get("") or ""
                        job_url = urljoin(resp.url, link_href) if link_href else resp.url
                        date_str = (row.css("td:nth-child(3)::text, .date::text").get("") or "").strip()
                        posted_at = None
                        if date_str:
                            try:
                                posted_at = local_date(date_str[:10])
                            except Exception:
                                posted_at = None

                        job = NormalizedJob(
                            source="government",
                            source_key=f"gov:{key}:{canonical_url(job_url) or job_url}",
                            platform=portal_name,
                            company=portal_name,
                            title=title,
                            job_url=job_url,
                            application_url=job_url,
                            location="India",
                            country="IN",
                            work_mode="On-site",
                            employment_type="Full-time",
                            description=f"Official recruitment announcement by {portal_name}: {title}. Apply through official portal.",
                            posted_at=posted_at,
                            posted_at_source="platform_page" if posted_at else None,
                            source_name=portal_name,
                            extraction_method="html_gov",
                            extraction_confidence=0.88,
                            parser_version="1.0.0",
                        )

                        valid, _ = self.validate_job(job)
                        if valid:
                            discovered.append(job)

            except Exception as exc:
                log.warning("Government portal fetch error for %s (%s): %s", key, url, exc)

        self.record_success(len(discovered))
        return discovered
