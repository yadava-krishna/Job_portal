"""Ashby public Job Postings API: https://developers.ashbyhq.com/docs/public-job-posting-api"""

from __future__ import annotations

from typing import Any

from backend.services.ats.base import AtsError, BoardResult, get_json
from backend.services.normalization import NormalizedJob, employment_type, html_to_text, local_date, split_locations, work_mode

API = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def fetch(token: str, *, company_name: str | None = None, region: str | None = None) -> BoardResult:
    data = get_json(API.format(token=token), {"includeCompensation": "true"})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise AtsError("invalid", "Unexpected Ashby response.")
    result = BoardResult("ashby", token, company_name)
    for raw in data["jobs"]:
        job = parse_job(raw, token, company_name)
        if job is None:
            result.skipped += 1
        else:
            result.jobs.append(job)
    return result


def _salary(raw: dict[str, Any]) -> str | None:
    comp = raw.get("compensation") if isinstance(raw.get("compensation"), dict) else {}
    if raw.get("shouldDisplayCompensationOnJobPostings") is False:
        return None
    return (comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary") or "").strip() or None


def parse_job(raw: dict[str, Any], token: str, company_name: str | None) -> NormalizedJob | None:
    # Unlisted postings are hidden from the employer's own careers page, so we skip them too.
    if not isinstance(raw, dict) or raw.get("isListed") is False or not raw.get("id") or not (raw.get("title") or "").strip():
        return None
    secondary = [s.get("location") for s in raw.get("secondaryLocations") or [] if isinstance(s, dict)]
    locations = split_locations(raw.get("location"), secondary)
    posted = local_date(raw.get("publishedAt"))
    mode = work_mode(raw.get("workplaceType")) or ("Remote" if raw.get("isRemote") else None)
    return NormalizedJob(
        source="ashby", source_key=f"ashby:{token.lower()}:{raw['id']}", platform="Ashby",
        company=(company_name or token).strip(), title=raw["title"].strip(), external_job_id=str(raw["id"]),
        location=raw.get("location") or None, locations=locations, work_mode=mode,
        employment_type=employment_type(raw.get("employmentType")), salary_range=_salary(raw),
        description=(raw.get("descriptionPlain") or html_to_text(raw.get("descriptionHtml")) or "").strip() or None,
        job_url=raw.get("jobUrl"), department=raw.get("department") or raw.get("team"),
        application_method="Apply on the employer's Ashby job page",
        posted_at=posted, posted_at_source="platform_api" if posted else None,
    )
