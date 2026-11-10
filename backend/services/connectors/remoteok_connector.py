"""backend/services/connectors/remoteok_connector.py

RemoteOK official JSON API and RSS connector.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.services.connectors.base_connector import BaseConnector
from backend.services.normalization import (
    NormalizedJob,
    html_to_text,
    local_date,
)
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)

REMOTEOK_API_URL = "https://remoteok.com/api"


class RemoteOkConnector(BaseConnector):
    """Discovers remote listings via RemoteOK public API."""

    source_id = "remoteok"
    name = "RemoteOK Remote Jobs"
    domain = "remoteok.com"
    category = SourceCategory.AGGREGATOR_API
    access_method = AccessMethod.API

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        crit = criteria or {}
        tag = crit.get("tag")
        url = f"{REMOTEOK_API_URL}?tag={tag}" if tag else REMOTEOK_API_URL

        try:
            resp = self.client.fetch_page(url, source_id=self.source_id)
            items = json.loads(resp.text)
        except Exception as exc:
            log.warning("RemoteOK fetch failed: %s", exc)
            self.record_failure(str(exc))
            return []

        discovered: list[NormalizedJob] = []
        # Note: RemoteOK API index 0 is often a legal notice dict without 'position'
        for r in items:
            if not isinstance(r, dict) or "position" not in r:
                continue

            ext_id = str(r.get("id") or "")
            title = (r.get("position") or "").strip()
            company = (r.get("company") or "").strip()
            if not title or not company:
                continue

            job_url = r.get("url") or f"https://remoteok.com/remote-jobs/{ext_id}"
            loc = r.get("location") or "Worldwide"
            date_str = r.get("date")
            posted_at = None
            if date_str:
                try:
                    posted_at = local_date(str(date_str)[:10])
                except Exception:
                    posted_at = None

            raw_desc = r.get("description") or ""
            clean_desc = html_to_text(raw_desc) if "<" in raw_desc else raw_desc

            min_sal = r.get("salary_min")
            max_sal = r.get("salary_max")
            sal_str = f"${min_sal} - ${max_sal}" if (min_sal or max_sal) else None

            tags = r.get("tags") or []
            skills = [str(t).strip() for t in tags if str(t).strip()]

            job = NormalizedJob(
                source="remoteok",
                source_key=f"remoteok:{ext_id}",
                platform="RemoteOK",
                company=company,
                title=title,
                external_job_id=ext_id,
                job_url=job_url,
                application_url=job_url,
                location=loc,
                locations=[loc] if loc else [],
                work_mode="Remote",
                salary_range=sal_str,
                description=clean_desc,
                posted_at=posted_at,
                posted_at_source="platform_api",
                required_skills=skills,
                source_name="RemoteOK API",
                extraction_method="api",
                extraction_confidence=0.98,
                parser_version="1.0.0",
            )

            valid, _ = self.validate_job(job)
            if valid:
                discovered.append(job)

        self.record_success(len(discovered))
        return discovered
