"""Lever Postings API: https://github.com/lever/postings-api"""

from __future__ import annotations

from typing import Any

from backend.services.ats.base import AtsError, BoardResult, get_json
from backend.services.normalization import NormalizedJob, employment_type, html_to_text, local_date, split_locations, work_mode

API = {None: "https://api.lever.co/v0/postings/{token}", "eu": "https://api.eu.lever.co/v0/postings/{token}"}


def fetch(token: str, *, company_name: str | None = None, region: str | None = None) -> BoardResult:
    data = get_json(API.get(region, API[None]).format(token=token), {"mode": "json"})
    if not isinstance(data, list):
        raise AtsError("invalid", "Unexpected Lever response.")
    result = BoardResult("lever", token, company_name)
    for raw in data:
        job = parse_job(raw, token, company_name)
        if job is None:
            result.skipped += 1
        else:
            result.jobs.append(job)
    return result


def _description(raw: dict[str, Any]) -> str | None:
    parts = [raw.get("descriptionPlain") or html_to_text(raw.get("description"))]
    for block in raw.get("lists") or []:
        if isinstance(block, dict):
            items = html_to_text(block.get("content"))
            parts.append(f"{(block.get('text') or '').strip()}\n{items}".strip())
    parts.append(raw.get("additionalPlain") or html_to_text(raw.get("additional")))
    text = "\n\n".join(p.strip() for p in parts if p and p.strip())
    return text or None


def salary(raw: dict[str, Any]) -> tuple[str | None, float | None, float | None]:
    sr = raw.get("salaryRange") if isinstance(raw.get("salaryRange"), dict) else None
    text = (raw.get("salaryDescriptionPlain") or "").strip() or None
    if not sr or not (sr.get("min") or sr.get("max")):
        return text, None, None
    cur, interval = (sr.get("currency") or "").upper(), (sr.get("interval") or "").lower()
    lo, hi = sr.get("min"), sr.get("max")
    label = text or f"{cur} {lo or '?'}–{hi or '?'} {interval.replace('-', ' ')}".strip()
    if cur == "INR" and interval in ("per-year-salary", "per-year", "yearly", ""):
        return label, (round(lo / 1e5, 2) if lo else None), (round(hi / 1e5, 2) if hi else None)
    return label, None, None


def parse_job(raw: dict[str, Any], token: str, company_name: str | None) -> NormalizedJob | None:
    if not isinstance(raw, dict) or not raw.get("id") or not (raw.get("text") or "").strip():
        return None
    cat = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
    locations = split_locations(cat.get("allLocations") or cat.get("location"))
    posted = local_date(raw.get("createdAt"))  # milliseconds since epoch, set by Lever when the posting is created
    sal_text, sal_lo, sal_hi = salary(raw)
    return NormalizedJob(
        source="lever", source_key=f"lever:{token.lower()}:{raw['id']}", platform="Lever",
        company=(company_name or token).strip(), title=raw["text"].strip(), external_job_id=str(raw["id"]),
        location=cat.get("location") or (", ".join(locations) if locations else None), locations=locations,
        work_mode=work_mode(raw.get("workplaceType"), cat.get("location")), employment_type=employment_type(cat.get("commitment")),
        salary_range=sal_text, salary_min_lpa=sal_lo, salary_max_lpa=sal_hi, description=_description(raw),
        job_url=raw.get("hostedUrl"), department=cat.get("department") or cat.get("team"),
        application_method="Apply on the employer's Lever job page",
        posted_at=posted, posted_at_source="platform_api" if posted else None,
    )
