"""Job records from an approved portal job API or licensed feed → JobPilot's normalised job model.

JobPilot has no such approval from LinkedIn, Indeed or Naukri (see portal_service: job_retrieval is unavailable for all
three), so APPROVED_JOB_ACCESS is empty and ingest() refuses every portal. Signing in with a portal never changes that.
Jobs from those portals keep arriving the ways that are allowed today: a pasted link, the clipper, alert e-mails.

The mapping exists so that, once an approval is real and recorded here (with the agreement that grants it), records
come in through the single ingest path (discovery_service.ingest_normalized: dedup, the user's feed, scoring) with
their provenance: source, provider job id, original and application URLs, a posting date only when the provider gives
one, and when JobPilot last verified the listing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.models import User, UserJob
from backend.services import normalization
from backend.services.normalization import NormalizedJob

# provider -> the agreement or partner approval that grants JobPilot access to its job records. None today.
APPROVED_JOB_ACCESS: dict[str, str] = {}
NAMES = {"linkedin": "LinkedIn", "indeed": "Indeed", "naukri": "Naukri"}


def source_name(provider: str) -> str:
    return f"{provider}_api"


def to_normalized(provider: str, rec: dict[str, Any], *, verified_at: datetime) -> NormalizedJob:
    """One provider record. Required: id, title, company, url. Optional: location, description (text or HTML),
    apply_url, posted_at (ISO date or timestamp from the provider), employment_type, work_mode."""
    missing = [k for k in ("id", "title", "company", "url") if not str(rec.get(k) or "").strip()]
    if missing:
        raise ValueError(f"{NAMES.get(provider, provider)} record without {', '.join(missing)}")
    posted = normalization.local_date(rec.get("posted_at")) if rec.get("posted_at") else None
    location = (rec.get("location") or None) and str(rec["location"]).strip()
    src = source_name(provider)
    return NormalizedJob(
        source=src, source_key=f"{src}:{rec['id']}", platform=NAMES.get(provider, provider), company=str(rec["company"]).strip(),
        title=str(rec["title"]).strip(), external_job_id=str(rec["id"]), location=location, locations=normalization.split_locations(location),
        work_mode=normalization.work_mode(rec.get("work_mode"), location), employment_type=normalization.employment_type(rec.get("employment_type")),
        description=normalization.html_to_text(rec.get("description")) or None, job_url=str(rec["url"]).strip(),
        application_url=(str(rec["apply_url"]).strip() if rec.get("apply_url") else None),
        posted_at=posted, posted_at_source="platform_api" if posted else None, source_name=f"{NAMES.get(provider, provider)} API",
        extraction_method="provider_api", observed_at=verified_at,
    )


def ingest(db: Session, user: User, provider: str, records: Iterable[dict[str, Any]], *, verified_at: datetime) -> list[UserJob]:
    if provider not in APPROVED_JOB_ACCESS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"JobPilot has no approved access to {NAMES.get(provider, provider)} job data. "
                                                       "Add jobs with a link, the clipper or alert e-mails instead.")
    from backend.services import discovery_service

    items = [to_normalized(provider, r, verified_at=verified_at) for r in records]
    run = discovery_service.start_run(db, user, "provider_api", [source_name(provider)])
    feed = discovery_service.ingest_normalized(db, user, run, items, None, explicit_sources=True)
    by_key = {nj.source_key: nj for nj in items}
    for uj in feed:
        job = uj.job
        nj = next((n for k, n in by_key.items() if n.external_job_id == job.external_job_id), None)
        if nj and nj.application_url and not job.application_url:
            job.application_url = nj.application_url
        job.last_verified_at = verified_at
    discovery_service.finish_run(db, run)
    db.commit()
    return feed
