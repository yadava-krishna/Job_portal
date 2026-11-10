"""backend/services/connectors/academic_connector.py

Academic and research institution recruitment connector.
Discovers staff, researcher, and faculty postings from premier institutes (IITs, IISc, IIMs).
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

ACADEMIC_INSTITUTES = {
    "iit_bombay": {"name": "IIT Bombay", "url": "https://www.iitb.ac.in/en/careers/staff-recruitment"},
    "iit_delhi": {"name": "IIT Delhi", "url": "https://home.iitd.ac.in/jobs-iitd.php"},
    "iit_madras": {"name": "IIT Madras", "url": "https://www.iitm.ac.in/careers"},
    "iisc_bangalore": {"name": "IISc Bangalore", "url": "https://iisc.ac.in/positions-open/"},
}


class AcademicConnector(BaseConnector):
    """Discovers openings from academic and research institutions."""

    source_id = "academic"
    name = "Academic & Research Institutions"
    domain = "ac.in"
    category = SourceCategory.ACADEMIC
    access_method = AccessMethod.HTML

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        crit = criteria or {}
        targets = crit.get("targets") or list(ACADEMIC_INSTITUTES.keys())
        discovered: list[NormalizedJob] = []

        for key in targets:
            inst = ACADEMIC_INSTITUTES.get(key)
            if not inst:
                continue

            inst_name = inst["name"]
            url = inst["url"]

            try:
                resp = self.client.fetch_page(url, source_id=self.source_id)

                # 1. Try JSON-LD first
                jobs = extract_jsonld_from_html(resp.text, resp.url, fallback_company=inst_name)
                for j in jobs:
                    j.source = "academic"
                    j.platform = inst_name
                    j.country = "IN"
                    discovered.append(j)

                # 2. HTML table/list fallback
                if not jobs:
                    rows = resp.css("table tr, .job-listing, .career-item, li.recruitment-item")
                    for r in rows:
                        title = (r.css("a::text, .title::text, td:nth-child(2)::text").get("") or "").strip()
                        if not title or len(title) < 5 or "s.no" in title.lower():
                            continue

                        link_href = r.css("a::attr(href)").get("") or ""
                        job_url = urljoin(resp.url, link_href) if link_href else resp.url
                        date_str = (r.css(".date::text, td:nth-child(3)::text").get("") or "").strip()
                        posted_at = None
                        if date_str:
                            try:
                                posted_at = local_date(date_str[:10])
                            except Exception:
                                posted_at = None

                        job = NormalizedJob(
                            source="academic",
                            source_key=f"acad:{key}:{canonical_url(job_url) or job_url}",
                            platform=inst_name,
                            company=inst_name,
                            title=title,
                            job_url=job_url,
                            application_url=job_url,
                            location="India",
                            country="IN",
                            work_mode="On-site",
                            employment_type="Full-time",
                            description=f"Academic opening at {inst_name}: {title}. Apply through institution portal.",
                            posted_at=posted_at,
                            posted_at_source="platform_page" if posted_at else None,
                            source_name=inst_name,
                            extraction_method="html_academic",
                            extraction_confidence=0.88,
                            parser_version="1.0.0",
                        )
                        valid, _ = self.validate_job(job)
                        if valid:
                            discovered.append(job)

            except Exception as exc:
                log.warning("Academic portal fetch error for %s: %s", key, exc)

        self.record_success(len(discovered))
        return discovered
