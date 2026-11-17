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
PAGE_SIZE = 20
MAX_PAGES = 10


def _as_list(value: Any) -> list[Any]:
    if value in (None, "", "None"):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.startswith("["):
        try:
            parsed = json.loads(value.replace("'", '"'))
            return parsed if isinstance(parsed, list) else [parsed]
        except ValueError:
            return [v.strip(" '\"") for v in value.strip("[]").split(",") if v.strip(" '\"")]
    return [value]


def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _epoch_date(value: Any):
    """Himalayas sends Unix seconds (as a number or a string); older payloads used ISO dates."""
    if value in (None, "", "None"):
        return None
    text = str(value).strip()
    if text.isdigit():
        n = int(text)
        return local_date(n * 1000 if n < 10**11 else n)
    return local_date(text)


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
        limit = int(crit.get("limit", 100))
        # The API serves 20 jobs per page; follow its cursor (newest first) until `limit` jobs or MAX_PAGES pages.
        raw_jobs: list[dict[str, Any]] = []
        cursor: str | None = None
        for _page in range(MAX_PAGES):
            url = f"{HIMALAYAS_API_URL}?limit={PAGE_SIZE}" + (f"&cursor={cursor}" if cursor else "")
            try:
                resp = self.client.fetch_page(url, source_id=self.source_id)
                data = json.loads(resp.text)
            except Exception as exc:
                log.warning("Himalayas API fetch failed: %s", exc)
                if not raw_jobs:
                    self.record_failure(str(exc))
                    return []
                break  # keep the pages already read
            page = data.get("jobs", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            raw_jobs += page
            cursor = data.get("nextCursor") if isinstance(data, dict) else None
            if not page or not cursor or len(raw_jobs) >= limit:
                break
        discovered: list[NormalizedJob] = []

        for r in raw_jobs:
            ext_id = str(r.get("id") or r.get("guid") or "")
            title = (r.get("title") or "").strip()
            company = (r.get("companyName") or r.get("company") or "").strip()
            if not title or not company:
                continue

            job_url = r.get("applicationLink") or r.get("applicationUrl") or r.get("guid") or r.get("url") \
                or f"https://himalayas.app/jobs/{ext_id}"
            # Himalayas lists who may apply (countries); "Worldwide" only when it sets no restriction.
            allowed = [str(x).strip() for x in _as_list(r.get("locationRestrictions")) if str(x).strip()]
            loc = ("Remote - " + "; ".join(allowed)) if allowed else (r.get("location") or "Worldwide Remote")
            posted_at = _epoch_date(r.get("pubDate") or r.get("createdAt"))
            expires_at = _epoch_date(r.get("expiryDate"))

            raw_desc = r.get("description") or ""
            clean_desc = html_to_text(raw_desc) if "<" in raw_desc else raw_desc

            min_sal, max_sal = _num(r.get("minSalary")), _num(r.get("maxSalary"))
            currency = (r.get("currency") or r.get("salaryCurrency") or "").strip().upper() or None
            period = {"annual": "year", "yearly": "year", "monthly": "month", "hourly": "hour", "weekly": "week",
                      "daily": "day"}.get(str(r.get("salaryPeriod") or "").lower())
            salary_str = None
            if (min_sal or max_sal) and currency:
                amount = f"{min_sal:g} - {max_sal:g}" if min_sal and max_sal else f"{(min_sal or max_sal):g}"
                salary_str = f"{currency} {amount}" + (f" per {period}" if period else "")
            seniority = _as_list(r.get("seniority"))

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
                locations=allowed or ([loc] if loc else []),
                work_mode="Remote",
                expires_at=expires_at,
                seniority=str(seniority[0]) if seniority else None,
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
