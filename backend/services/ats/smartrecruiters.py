"""SmartRecruiters Posting API (public, no authentication): https://developers.smartrecruiters.com/docs/posting-api

The list endpoint gives title, location (with remote/hybrid flags), employment type and release date. The full job
ad needs one request per posting, so descriptions are fetched only for postings that pass a search's title and
location filters (`complete`), and cached.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from backend.services.ats.base import AtsError, BoardResult, get_json
from backend.services.normalization import NormalizedJob, employment_type, html_to_text, local_date

API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"
PAGE = 100
MAX_POSTINGS = 1000  # very large employers list thousands; the most recent 1,000 are read
DETAIL_TTL = 6 * 3600
_details: dict[str, tuple[float, str | None]] = {}
_lock = threading.Lock()


def fetch(token: str, *, company_name: str | None = None, region: str | None = None) -> BoardResult:
    result = BoardResult("smartrecruiters", token, company_name)
    offset = 0
    # region: an ISO country code ("in") for boards followed for one country. Large employers list thousands of
    # postings worldwide; asking the API for that country's postings keeps them inside the 1,000-posting window.
    country = {"country": region.lower()} if region and len(region) == 2 and region.isalpha() else {}
    while offset < MAX_POSTINGS:
        data = get_json(API.format(token=token), {"limit": PAGE, "offset": offset, **country})
        if not isinstance(data, dict) or not isinstance(data.get("content"), list):
            raise AtsError("invalid", "Unexpected SmartRecruiters response.")
        for raw in data["content"]:
            job = parse_job(raw, token, company_name)
            if job is None:
                result.skipped += 1
            else:
                result.company_name = result.company_name or job.company
                result.jobs.append(job)
        total = int(data.get("totalFound") or 0)
        offset += PAGE
        if offset >= total or not data["content"]:
            break
    return result


def parse_job(raw: dict[str, Any], token: str, company_name: str | None) -> NormalizedJob | None:
    if not isinstance(raw, dict) or not raw.get("id") or not (raw.get("name") or "").strip():
        return None
    loc = raw.get("location") if isinstance(raw.get("location"), dict) else {}
    location = (loc.get("fullLocation") or ", ".join(p for p in (loc.get("city"), loc.get("region"), loc.get("country", "").upper()) if p)).strip() or None
    mode = "Remote" if loc.get("remote") else "Hybrid" if loc.get("hybrid") else ("On-site" if location else None)
    posted = local_date(raw.get("releasedDate"))
    company = (company_name or (raw.get("company") or {}).get("name") or token).strip()
    emp = ((raw.get("typeOfEmployment") or {}).get("label") or "").strip()
    return NormalizedJob(
        source="smartrecruiters", source_key=f"smartrecruiters:{token.lower()}:{raw['id']}", platform="SmartRecruiters",
        company=company, title=" ".join(raw["name"].split()), external_job_id=str(raw["id"]), location=location,
        locations=[location] if location else [], work_mode=mode, employment_type=employment_type(emp) if emp else None,
        description=None, description_is_snippet=True,
        job_url=f"https://jobs.smartrecruiters.com/{token}/{raw['id']}",
        department=((raw.get("department") or {}).get("label") or None),
        application_method="Apply on the employer's SmartRecruiters job page",
        posted_at=posted, posted_at_source="platform_api" if posted else None,
    )


def complete(nj: NormalizedJob, token: str | None = None) -> None:
    """Fetch the full job ad for one posting (only for postings a search kept). `token` is the board's own spelling."""
    if nj.source != "smartrecruiters" or nj.description:
        return
    _, lower_token, pid = nj.source_key.split(":", 2)
    token = token or lower_token
    now = time.monotonic()
    with _lock:
        hit = _details.get(nj.source_key)
    if hit and now - hit[0] < DETAIL_TTL:
        text, url = hit[1], None
    else:
        try:
            raw = get_json(f"{API.format(token=token)}/{pid}")
        except AtsError:
            return
        sections = ((raw.get("jobAd") or {}).get("sections") or {}) if isinstance(raw, dict) else {}
        parts = [html_to_text((sections.get(k) or {}).get("text")) for k in ("jobDescription", "qualifications", "additionalInformation")]
        text = "\n\n".join(p for p in parts if p) or None
        url = raw.get("postingUrl") if isinstance(raw, dict) else None
        with _lock:
            _details[nj.source_key] = (now, text)
    if text:
        nj.description = text
        nj.description_is_snippet = False
    if url and url.startswith("https://jobs.smartrecruiters.com/"):
        nj.job_url = url
