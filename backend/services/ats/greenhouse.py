"""Greenhouse Job Board API: https://developers.greenhouse.io/job-board.html"""

from __future__ import annotations

from typing import Any

from backend.services.ats.base import AtsError, BoardResult, get_json
from backend.services.normalization import NormalizedJob, html_to_text, local_date, split_locations

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch(token: str, *, company_name: str | None = None, region: str | None = None) -> BoardResult:
    data = get_json(API.format(token=token), {"content": "true"})
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise AtsError("invalid", "Unexpected Greenhouse response.")
    result = BoardResult("greenhouse", token, company_name)
    for raw in data["jobs"]:
        job = parse_job(raw, token, company_name)
        if job is None:
            result.skipped += 1
        else:
            result.company_name = result.company_name or job.company
            result.jobs.append(job)
    return result


def parse_job(raw: dict[str, Any], token: str, company_name: str | None) -> NormalizedJob | None:
    if not isinstance(raw, dict) or not raw.get("id") or not (raw.get("title") or "").strip():
        return None
    location = ((raw.get("location") or {}).get("name") or "").strip() or None
    departments = [d.get("name") for d in raw.get("departments") or [] if isinstance(d, dict) and d.get("name")]
    # first_published is when the posting went live. updated_at changes on any edit, so it is never used as a posting date.
    posted = local_date(raw.get("first_published"))
    return NormalizedJob(
        source="greenhouse", source_key=f"greenhouse:{token.lower()}:{raw['id']}", platform="Greenhouse",
        company=(company_name or raw.get("company_name") or token).strip(), title=raw["title"].strip(),
        external_job_id=str(raw["id"]), location=location, locations=split_locations(location),
        description=html_to_text(raw.get("content")) or None, job_url=raw.get("absolute_url"),
        department=departments[0] if departments else None,
        application_method="Apply on the employer's Greenhouse job page",
        posted_at=posted, posted_at_source="platform_api" if posted else None,
    )
