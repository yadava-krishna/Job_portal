"""Recruitee Careers Site API (public, no authentication): https://docs.recruitee.com/reference/offers

GET https://<company>.recruitee.com/api/offers/ lists the company's published offers with full descriptions.
"""

from __future__ import annotations

from typing import Any

from backend.services.ats.base import AtsError, BoardResult, get_json
from backend.services.normalization import NormalizedJob, html_to_text, local_date

API = "https://{token}.recruitee.com/api/offers/"
EMPLOYMENT = {"fulltime": "Full-time", "parttime": "Part-time", "contract": "Contract", "internship": "Internship",
              "temporary": "Temporary", "freelance": "Contract"}


def fetch(token: str, *, company_name: str | None = None, region: str | None = None) -> BoardResult:
    if not token.replace("-", "").isalnum():
        raise AtsError("invalid", "That doesn't look like a Recruitee company name.")
    data = get_json(API.format(token=token.lower()))
    if not isinstance(data, dict) or not isinstance(data.get("offers"), list):
        raise AtsError("invalid", "Unexpected Recruitee response.")
    result = BoardResult("recruitee", token, company_name)
    for raw in data["offers"]:
        job = parse_job(raw, token, company_name)
        if job is None:
            result.skipped += 1
        else:
            result.company_name = result.company_name or job.company
            result.jobs.append(job)
    return result


def parse_job(raw: dict[str, Any], token: str, company_name: str | None) -> NormalizedJob | None:
    if not isinstance(raw, dict) or not raw.get("id") or not (raw.get("title") or "").strip() or raw.get("status") not in (None, "published"):
        return None
    location = (raw.get("location") or "").strip() or None
    mode = "Remote" if raw.get("remote") else "Hybrid" if raw.get("hybrid") else ("On-site" if raw.get("on_site") else None)
    emp_code = str(raw.get("employment_type_code") or "")
    emp = next((v for k, v in EMPLOYMENT.items() if emp_code.startswith(k)), None)
    text = "\n\n".join(p for p in (html_to_text(raw.get("description")), html_to_text(raw.get("requirements"))) if p) or None
    posted = local_date((raw.get("published_at") or "").replace(" UTC", "+00:00").replace(" ", "T", 1))
    url = raw.get("careers_url") if str(raw.get("careers_url", "")).startswith("https://") else None
    return NormalizedJob(
        source="recruitee", source_key=f"recruitee:{token.lower()}:{raw['id']}", platform="Recruitee",
        company=(company_name or raw.get("company_name") or token).strip(), title=" ".join(raw["title"].split()),
        external_job_id=str(raw["id"]), location=location, locations=[location] if location else [], work_mode=mode,
        employment_type=emp, description=text, job_url=url, department=(raw.get("department") or None),
        application_method="Apply on the employer's Recruitee careers page",
        posted_at=posted, posted_at_source="platform_api" if posted else None,
    )
