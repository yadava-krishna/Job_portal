"""backend/services/connectors/jsonld_connector.py

Extracts Schema.org JobPosting structured data from HTML pages using Scrapling.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

from backend.services.connectors.base_connector import BaseConnector
from backend.services.normalization import (
    NormalizedJob,
    canonical_url,
    html_to_text,
    local_date,
    work_mode as normalize_work_mode,
    employment_type as normalize_employment_type,
)
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)


def parse_jsonld_job(data: dict[str, Any], page_url: str, fallback_company: str | None = None) -> NormalizedJob | None:
    """Parse a single Schema.org JobPosting dictionary into NormalizedJob."""
    if not isinstance(data, dict):
        return None
    type_val = data.get("@type")
    if type_val != "JobPosting" and not (isinstance(type_val, list) and "JobPosting" in type_val):
        return None

    title = (data.get("title") or "").strip()
    if not title:
        return None

    # Company name
    company = ""
    hiring_org = data.get("hiringOrganization")
    if isinstance(hiring_org, dict):
        company = (hiring_org.get("name") or "").strip()
    elif isinstance(hiring_org, str):
        company = hiring_org.strip()
    if not company and fallback_company:
        company = fallback_company.strip()

    # Location
    location_parts: list[str] = []
    job_loc = data.get("jobLocation")
    if isinstance(job_loc, list):
        for loc in job_loc:
            if isinstance(loc, dict):
                addr = loc.get("address", {})
                if isinstance(addr, dict):
                    loc_str = ", ".join(filter(None, [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]))
                    if loc_str:
                        location_parts.append(loc_str)
    elif isinstance(job_loc, dict):
        addr = job_loc.get("address", {})
        if isinstance(addr, dict):
            loc_str = ", ".join(filter(None, [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]))
            if loc_str:
                location_parts.append(loc_str)
        elif isinstance(addr, str) and addr.strip():
            location_parts.append(addr.strip())

    primary_loc = location_parts[0] if location_parts else None

    # Work Mode
    work_mode_str = None
    loc_type = str(data.get("jobLocationType") or "").upper()
    if "TELECOMMUTE" in loc_type or "REMOTE" in loc_type:
        work_mode_str = "Remote"
    else:
        work_mode_str = normalize_work_mode(primary_loc or "", title)

    # Description
    raw_desc = data.get("description") or ""
    clean_desc = html_to_text(raw_desc) if "<" in raw_desc else raw_desc.strip()

    # Posted Date
    date_posted_str = data.get("datePosted")
    posted_at: date | None = None
    if date_posted_str:
        try:
            # Handle ISO string like 2026-10-15T08:00:00Z or bare date 2026-10-15
            posted_at = local_date(date_posted_str[:10])
        except Exception:
            posted_at = None

    # Employment Type
    emp_type_raw = data.get("employmentType")
    emp_type = None
    if isinstance(emp_type_raw, list) and emp_type_raw:
        emp_type = normalize_employment_type(str(emp_type_raw[0]))
    elif isinstance(emp_type_raw, str):
        emp_type = normalize_employment_type(emp_type_raw)

    # Salary
    salary_min_lpa = None
    salary_max_lpa = None
    salary_range_str = None
    base_sal = data.get("baseSalary")
    if isinstance(base_sal, dict):
        currency = str(base_sal.get("currency") or "INR").upper()
        val = base_sal.get("value")
        if isinstance(val, dict):
            min_val = val.get("minValue")
            max_val = val.get("maxValue")
            unit = str(val.get("unitText") or "").upper()
            if min_val is not None:
                try:
                    f_min = float(min_val)
                    if currency == "INR":
                        if unit == "MONTH" or f_min < 200000:
                            f_min *= 12
                        salary_min_lpa = round(f_min / 100000.0, 2)
                    else:
                        salary_min_lpa = round(f_min, 2)
                except (ValueError, TypeError):
                    pass
            if max_val is not None:
                try:
                    f_max = float(max_val)
                    if currency == "INR":
                        if unit == "MONTH" or f_max < 200000:
                            f_max *= 12
                        salary_max_lpa = round(f_max / 100000.0, 2)
                    else:
                        salary_max_lpa = round(f_max, 2)
                except (ValueError, TypeError):
                    pass
            if salary_min_lpa or salary_max_lpa:
                salary_range_str = f"{currency} {min_val or ''} - {max_val or ''}"

    # URLs
    job_url = data.get("url") or page_url
    domain = urlparse(page_url).netloc.lower()
    source_key = f"jsonld:{domain}:{canonical_url(job_url) or job_url}"

    return NormalizedJob(
        source="career_page",
        source_key=source_key,
        platform="Career Page",
        company=company,
        title=title,
        job_url=job_url,
        application_url=job_url,
        location=primary_loc,
        locations=location_parts,
        work_mode=work_mode_str,
        employment_type=emp_type,
        salary_range=salary_range_str,
        salary_min_lpa=salary_min_lpa,
        salary_max_lpa=salary_max_lpa,
        description=clean_desc,
        posted_at=posted_at,
        posted_at_source="platform_page",
        extraction_method="json_ld",
        extraction_confidence=0.95,
        parser_version="1.0.0",
    )


def extract_jsonld_from_html(html_text: str, page_url: str, fallback_company: str | None = None) -> list[NormalizedJob]:
    """Extract all JobPosting records found in JSON-LD script tags."""
    jobs: list[NormalizedJob] = []
    # Scrape script tags with type application/ld+json
    pattern = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
    matches = pattern.findall(html_text)

    for script_body in matches:
        script_body = script_body.strip()
        if not script_body:
            continue
        try:
            parsed = json.loads(script_body)
        except Exception:
            # Handle potential unescaped control chars
            try:
                cleaned = re.sub(r'[\x00-\x1f]+', ' ', script_body)
                parsed = json.loads(cleaned)
            except Exception:
                continue

        # Can be single dict or @graph list
        items = []
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            if "@graph" in parsed and isinstance(parsed["@graph"], list):
                items = parsed["@graph"]
            else:
                items = [parsed]

        for item in items:
            job = parse_jsonld_job(item, page_url, fallback_company=fallback_company)
            if job is not None:
                jobs.append(job)

    return jobs


class JsonLdConnector(BaseConnector):
    """Generic connector for web pages publishing Schema.org JobPosting JSON-LD."""

    source_id = "json_ld"
    name = "Schema.org JobPosting Extractor"
    domain = "*"
    category = SourceCategory.JSON_LD
    access_method = AccessMethod.JSON_LD

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        """Extract jobs from target URLs passed in criteria."""
        urls = (criteria or {}).get("urls", [])
        discovered: list[NormalizedJob] = []

        for url in urls:
            try:
                resp = self.client.fetch_page(url)
                jobs = extract_jsonld_from_html(resp.text, resp.url)
                for j in jobs:
                    valid, _ = self.validate_job(j)
                    if valid:
                        discovered.append(j)
            except Exception as exc:
                log.warning("JSON-LD extraction failed for %s: %s", url, exc)

        self.record_success(len(discovered))
        return discovered
