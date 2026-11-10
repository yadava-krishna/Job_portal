"""backend/services/connectors/himalayas_connector.py

Himalayas official API connector for remote jobs.
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

HIMALAYAS_API_URL = "https://himalayas.app/jobs/api"


class HimalayasConnector(BaseConnector):
    """Discovers remote listings via Himalayas official API."""

    source_id = "himalayas"
    name = "Himalayas Remote Jobs"
    domain = "himalayas.app"
    category = SourceCategory.AGGREGATOR_API
    access_method = AccessMethod.API

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        crit = criteria or {}
        limit = crit.get("limit", 100)
        url = f"{HIMALAYAS_API_URL}?limit={limit}"

        try:
            resp = self.client.fetch_page(url, source_id=self.source_id)
            data = json.loads(resp.text)
        except Exception as exc:
            log.warning("Himalayas API fetch failed: %s", exc)
            self.record_failure(str(exc))
            return []

        raw_jobs = data.get("jobs", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        discovered: list[NormalizedJob] = []

        for r in raw_jobs:
            ext_id = str(r.get("id") or r.get("guid") or "")
            title = (r.get("title") or "").strip()
            company = (r.get("companyName") or r.get("company") or "").strip()
            if not title or not company:
                continue

            job_url = r.get("applicationUrl") or r.get("url") or f"https://himalayas.app/jobs/{ext_id}"
            loc = r.get("location") or "Worldwide Remote"
            pub_date_str = r.get("pubDate") or r.get("createdAt")
            posted_at = None
            if pub_date_str:
                try:
                    posted_at = local_date(str(pub_date_str)[:10])
                except Exception:
                    posted_at = None

            raw_desc = r.get("description") or ""
            clean_desc = html_to_text(raw_desc) if "<" in raw_desc else raw_desc

            min_sal = r.get("minSalary")
            max_sal = r.get("maxSalary")
            currency = r.get("salaryCurrency") or "USD"
            salary_str = f"{currency} {min_sal} - {max_sal}" if (min_sal or max_sal) else None

            job = NormalizedJob(
                source="himalayas",
                source_key=f"himalayas:{ext_id or canonical_url(job_url)}",
                platform="Himalayas",
                company=company,
                title=title,
                external_job_id=ext_id,
                job_url=job_url,
                application_url=job_url,
                location=loc,
                locations=[loc] if loc else [],
                work_mode="Remote",
                employment_type=normalize_employment_type(r.get("employmentType")),
                salary_range=salary_str,
                description=clean_desc,
                posted_at=posted_at,
                posted_at_source="platform_api",
                source_name="Himalayas API",
                extraction_method="api",
                extraction_confidence=0.98,
                parser_version="1.0.0",
            )

            valid, _ = self.validate_job(job)
            if valid:
                discovered.append(job)

        self.record_success(len(discovered))
        return discovered
