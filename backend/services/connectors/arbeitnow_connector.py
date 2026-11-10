"""backend/services/connectors/arbeitnow_connector.py

Arbeitnow official job board API connector for European and international tech/remote roles.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from backend.services.connectors.base_connector import BaseConnector
from backend.services.normalization import (
    NormalizedJob,
    canonical_url,
    html_to_text,
    employment_type as normalize_employment_type,
)
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)

ARBEITNOW_API_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowConnector(BaseConnector):
    """Discovers roles via Arbeitnow API."""

    source_id = "arbeitnow"
    name = "Arbeitnow Job Board"
    domain = "arbeitnow.com"
    category = SourceCategory.AGGREGATOR_API
    access_method = AccessMethod.API

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        crit = criteria or {}
        page = crit.get("page", 1)
        url = f"{ARBEITNOW_API_URL}?page={page}"

        try:
            resp = self.client.fetch_page(url, source_id=self.source_id)
            data = json.loads(resp.text)
        except Exception as exc:
            log.warning("Arbeitnow API fetch failed: %s", exc)
            self.record_failure(str(exc))
            return []

        raw_jobs = data.get("data", [])
        discovered: list[NormalizedJob] = []

        for r in raw_jobs:
            slug = r.get("slug") or ""
            title = (r.get("title") or "").strip()
            company = (r.get("company_name") or "").strip()
            if not title or not company:
                continue

            job_url = r.get("url") or f"https://www.arbeitnow.com/jobs/{slug}"
            loc = r.get("location") or ("Remote" if r.get("remote") else "")
            created_ts = r.get("created_at")
            posted_at = None
            if created_ts:
                try:
                    posted_at = datetime.fromtimestamp(created_ts, tz=timezone.utc).date()
                except Exception:
                    posted_at = None

            raw_desc = r.get("description") or ""
            clean_desc = html_to_text(raw_desc) if "<" in raw_desc else raw_desc

            is_remote = bool(r.get("remote"))
            work_mode_str = "Remote" if is_remote else ("Hybrid" if "hybrid" in loc.lower() else "On-site")

            job_types = r.get("job_types") or []
            emp_type = normalize_employment_type(job_types[0]) if job_types else None

            tags = r.get("tags") or []
            skills = [str(t).strip() for t in tags if str(t).strip()]

            job = NormalizedJob(
                source="arbeitnow",
                source_key=f"arbeitnow:{slug}",
                platform="Arbeitnow",
                company=company,
                title=title,
                external_job_id=slug,
                job_url=job_url,
                application_url=job_url,
                location=loc,
                locations=[loc] if loc else [],
                work_mode=work_mode_str,
                employment_type=emp_type,
                description=clean_desc,
                posted_at=posted_at,
                posted_at_source="platform_api",
                required_skills=skills,
                source_name="Arbeitnow API",
                extraction_method="api",
                extraction_confidence=0.98,
                parser_version="1.0.0",
            )

            valid, _ = self.validate_job(job)
            if valid:
                discovered.append(job)

        self.record_success(len(discovered))
        return discovered
