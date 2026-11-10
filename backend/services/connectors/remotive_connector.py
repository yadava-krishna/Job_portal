"""backend/services/connectors/remotive_connector.py

Remotive official public API connector for verified remote tech and finance jobs.
Complies with Remotive terms by maintaining source attribution and direct links.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.services.connectors.base_connector import BaseConnector
from backend.services.normalization import (
    NormalizedJob,
    canonical_url,
    html_to_text,
    local_date,
    employment_type as normalize_employment_type,
)
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)

REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveConnector(BaseConnector):
    """Discovers remote roles via official Remotive API with attribution."""

    source_id = "remotive"
    name = "Remotive Remote Jobs"
    domain = "remotive.com"
    category = SourceCategory.AGGREGATOR_API
    access_method = AccessMethod.API

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        crit = criteria or {}
        category = crit.get("category")
        search_term = crit.get("query")
        limit = crit.get("limit", 100)

        query_params = []
        if category:
            query_params.append(f"category={category}")
        if search_term:
            query_params.append(f"search={search_term}")
        if limit:
            query_params.append(f"limit={limit}")

        url = REMOTIVE_API_URL + (f"?{'&'.join(query_params)}" if query_params else "")

        try:
            resp = self.client.fetch_page(url, source_id=self.source_id)
            data = json.loads(resp.text)
        except Exception as exc:
            log.warning("Remotive API fetch failed: %s", exc)
            self.record_failure(str(exc))
            return []

        raw_jobs = data.get("jobs", [])
        discovered: list[NormalizedJob] = []

        for r in raw_jobs:
            ext_id = str(r.get("id"))
            title = (r.get("title") or "").strip()
            company = (r.get("company_name") or "").strip()
            if not title or not company:
                continue

            job_url = r.get("url") or f"https://remotive.com/remote-jobs/{ext_id}"
            loc = r.get("candidate_required_location") or "Remote"
            pub_date_str = r.get("publication_date")
            posted_at = None
            if pub_date_str:
                try:
                    posted_at = local_date(pub_date_str[:10])
                except Exception:
                    posted_at = None

            raw_desc = r.get("description") or ""
            clean_desc = html_to_text(raw_desc) if "<" in raw_desc else raw_desc

            salary = r.get("salary") or None
            emp_type = normalize_employment_type(r.get("job_type"))

            tags = r.get("tags") or []
            skills = [str(t).strip() for t in tags if str(t).strip()]

            job = NormalizedJob(
                source="remotive",
                source_key=f"remotive:{ext_id}",
                platform="Remotive",
                company=company,
                title=title,
                external_job_id=ext_id,
                job_url=job_url,
                application_url=job_url,
                location=loc,
                locations=[loc] if loc else [],
                work_mode="Remote",
                employment_type=emp_type,
                salary_range=salary,
                description=clean_desc,
                posted_at=posted_at,
                posted_at_source="platform_api",
                required_skills=skills,
                source_name="Remotive API",
                extraction_method="api",
                extraction_confidence=0.98,
                parser_version="1.0.0",
            )

            valid, _ = self.validate_job(job)
            if valid:
                discovered.append(job)

        self.record_success(len(discovered))
        return discovered
