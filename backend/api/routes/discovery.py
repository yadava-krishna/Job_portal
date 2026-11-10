"""Companies and watchlists, saved searches, notifications."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Query, status
from sqlalchemy import select

from backend.api import serializers
from backend.api.deps import CurrentAdmin, CurrentUser, DbSession, SettingsDep
from backend.db import session_factory
from backend.models import DiscoveryRun, SavedSearch, User
from backend.schemas.discovery import (
    CareerAnalysisOut,
    CareerUrlRequest,
    CompanyOut,
    DirectoryCompany,
    NotificationList,
    NotificationPrefs,
    NotificationOut,
    SavedSearchIn,
    SavedSearchOut,
    SourceConnectorOut,
    WatchManyRequest,
    WatchRequest,
    ATSDetectRequest,
    ATSDetectResponse,
    ReapResponse,
)
from backend.models import utcnow
from backend.schemas.jobs import DiscoveryRunOut
from backend.services import company_service, notification_service, saved_search_service, source_health

companies = APIRouter(prefix="/companies", tags=["companies"])
searches = APIRouter(prefix="/saved-searches", tags=["saved searches"])
notifications = APIRouter(prefix="/notifications", tags=["notifications"])
health = APIRouter(prefix="/discovery", tags=["discovery"])


@health.get("/sources", response_model=source_health.SourcesOverview)
def sources(user: CurrentUser, db: DbSession, settings: SettingsDep) -> source_health.SourcesOverview:
    """Every discovery source for you: configured or not (and what's missing), connection, last attempt/success, jobs found."""
    if user.onboarding_completed_at is not None:
        saved_search_service.ensure_starter(db, settings, user)
    return source_health.overview(db, settings, user)


# ---- companies ----------------------------------------------------------------------------------

@companies.get("/directory", response_model=list[DirectoryCompany])
def directory(user: CurrentUser, db: DbSession, q: str | None = Query(None, max_length=100),
              ats: Literal["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee"] | None = None, limit: int = Query(30, ge=1, le=100)) -> list[DirectoryCompany]:
    """Search known employer boards: JobPilot's curated India list first, then the JobSync directory (MIT)."""
    return company_service.search_directory(db, user, q, ats, limit)


@companies.get("/suggested", response_model=list[DirectoryCompany])
def suggested(user: CurrentUser, db: DbSession) -> list[DirectoryCompany]:
    watched = company_service.watched_keys(db, user)
    return [DirectoryCompany(name=c["name"], ats=c["ats"], token=c["token"], industry=c.get("industry"), domain=c.get("domain"),
                             curated=True, watched=(c["ats"], c["token"].lower()) in watched) for c in company_service.curated()]


@companies.get("/watchlist", response_model=list[CompanyOut])
def get_watchlist(user: CurrentUser, db: DbSession) -> list[CompanyOut]:
    return [company_service.company_out(c) for c in company_service.watchlist(db, user)]


@companies.post("/watchlist", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def add_to_watchlist(body: WatchRequest, user: CurrentUser, db: DbSession) -> CompanyOut:
    """Watch a company by its public job-board URL, or by ATS + board token. Unknown boards are checked once."""
    return company_service.company_out(company_service.watch(db, user, body))


@companies.post("/watchlist/bulk", response_model=list[CompanyOut], status_code=status.HTTP_201_CREATED)
def add_many(body: WatchManyRequest, user: CurrentUser, db: DbSession) -> list[CompanyOut]:
    return [company_service.company_out(company_service.watch(db, user, w)) for w in body.companies]


@companies.delete("/watchlist/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(company_id: int, user: CurrentUser, db: DbSession) -> None:
    company_service.unwatch(db, user, company_id)


# ---- saved searches -------------------------------------------------------------------------------

def _run_bg(settings, user_id: int, search_id: int, run_id: int) -> None:
    db = session_factory()()
    try:
        user, row, run = db.get(User, user_id), db.get(SavedSearch, search_id), db.get(DiscoveryRun, run_id)
        if user and row and run and run.status == "running":
            saved_search_service.execute(db, settings, user, row, run)
    finally:
        db.close()


@searches.get("", response_model=list[SavedSearchOut])
def list_searches(user: CurrentUser, db: DbSession, settings: SettingsDep) -> list[SavedSearchOut]:
    if user.onboarding_completed_at is not None:
        saved_search_service.ensure_starter(db, settings, user)
    return [saved_search_service.out(db, r) for r in saved_search_service.list_for(db, user)]


@searches.post("", response_model=SavedSearchOut, status_code=status.HTTP_201_CREATED)
def create_search(body: SavedSearchIn, user: CurrentUser, db: DbSession) -> SavedSearchOut:
    return saved_search_service.out(db, saved_search_service.create(db, user, body))


@searches.get("/{search_id}", response_model=SavedSearchOut)
def get_search(search_id: int, user: CurrentUser, db: DbSession) -> SavedSearchOut:
    return saved_search_service.out(db, saved_search_service._owned(db, user, search_id))


@searches.put("/{search_id}", response_model=SavedSearchOut)
def update_search(search_id: int, body: SavedSearchIn, user: CurrentUser, db: DbSession) -> SavedSearchOut:
    return saved_search_service.out(db, saved_search_service.update(db, user, search_id, body))


@searches.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search(search_id: int, user: CurrentUser, db: DbSession) -> None:
    saved_search_service.delete(db, user, search_id)


@searches.post("/{search_id}/run", response_model=DiscoveryRunOut, status_code=status.HTTP_202_ACCEPTED)
def run_search(search_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep, bg: BackgroundTasks) -> DiscoveryRunOut:
    """Run now in the background; poll /jobs/runs/{id}. A run already in progress is returned instead of starting another."""
    row = saved_search_service._owned(db, user, search_id)
    run, created = saved_search_service.start(db, user, row)
    if created:
        bg.add_task(_run_bg, settings, user.id, row.id, run.id)
    return serializers.run(run)


@searches.get("/{search_id}/runs", response_model=list[DiscoveryRunOut])
def search_runs(search_id: int, user: CurrentUser, db: DbSession, limit: int = Query(10, ge=1, le=50)) -> list[DiscoveryRunOut]:
    row = saved_search_service._owned(db, user, search_id)
    rows = db.execute(select(DiscoveryRun).where(DiscoveryRun.saved_search_id == row.id, DiscoveryRun.user_id == user.id)
                      .order_by(DiscoveryRun.id.desc()).limit(limit)).scalars()
    return [serializers.run(r) for r in rows]


# ---- notifications --------------------------------------------------------------------------------

@notifications.get("/preferences", response_model=NotificationPrefs)
def get_notification_prefs(user: CurrentUser, db: DbSession) -> NotificationPrefs:
    return NotificationPrefs(**notification_service.prefs(db, user))


@notifications.put("/preferences", response_model=NotificationPrefs)
def put_notification_prefs(body: NotificationPrefs, user: CurrentUser, db: DbSession) -> NotificationPrefs:
    return NotificationPrefs(**notification_service.save_prefs(db, user, body.model_dump()))


@notifications.get("", response_model=NotificationList)
def list_notifications(user: CurrentUser, db: DbSession, unread_only: bool = False,
                       limit: int = Query(30, ge=1, le=100)) -> NotificationList:
    items, unread = notification_service.list_for(db, user, unread_only=unread_only, limit=limit)
    return NotificationList(items=[NotificationOut.model_validate(n, from_attributes=True) for n in items], unread=unread)


@notifications.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def read_one(notification_id: int, user: CurrentUser, db: DbSession) -> None:
    notification_service.mark_read(db, user, notification_id)


@notifications.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def read_all(user: CurrentUser, db: DbSession) -> None:
    notification_service.mark_read(db, user)


# ---- career url & multi-source connectors ---------------------------------------------------------

@companies.post("/career-url", response_model=CareerAnalysisOut)
def analyze_career_url(body: CareerUrlRequest, user: CurrentUser, db: DbSession, settings: SettingsDep) -> CareerAnalysisOut:
    """Analyze a user-submitted company careers page URL: validates SSRF, checks robots.txt, detects ATS, and extracts jobs."""
    from backend.services.connectors.career_url_connector import CareerUrlConnector
    from backend.services.discovery_service import ingest_normalized, UserMatcher

    conn = CareerUrlConnector()
    res = conn.analyze_career_url(body.url, company_hint=body.company_name)
    if res.jobs and user.onboarding_completed_at is not None:
        matcher = UserMatcher(db, settings, user)
        ingest_normalized(db, user, None, res.jobs, matcher, source_name="career_page")

    return CareerAnalysisOut(
        url=res.url,
        company_name=res.company_name,
        detected_ats=res.detected_ats,
        ats_token=res.ats_token,
        has_json_ld=res.has_json_ld,
        json_ld_count=res.json_ld_count,
        discovered_feed_url=res.discovered_feed_url,
        discovered_sitemap_url=res.discovered_sitemap_url,
        jobs_count=len(res.jobs),
        errors=res.errors,
    )


@health.get("/connectors", response_model=list[SourceConnectorOut])
def list_connectors(user: CurrentUser) -> list[SourceConnectorOut]:
    """List all discovery connectors with real-time health, permission policy, and throughput stats."""
    from backend.services.connectors import registry

    out = []
    for c in registry.list_all():
        pol = c.policy
        h = c.get_source_health()
        out.append(SourceConnectorOut(
            source_id=c.source_id,
            name=c.name,
            domain=c.domain,
            category=c.category.value,
            access_method=c.access_method.value,
            permission_status=pol.permission_status.value if pol else "unknown",
            is_discoverable=pol.is_discoverable if pol else False,
            status=h.status,
            rate_limit_rpm=pol.rate_limit_rpm if pol else 10,
            last_success_at=h.last_success_at,
            last_error=h.last_error,
            jobs_discovered=h.jobs_discovered,
        ))
    return out


@health.post("/connectors/{source_id}/test", response_model=dict)
def test_connector(source_id: str, user: CurrentAdmin) -> dict:
    """Trigger a dry-run test discovery on a specific connector."""
    from backend.services.connectors import registry

    jobs = registry.run_connector(source_id, criteria={"limit": 5})
    return {
        "source_id": source_id,
        "jobs_found": len(jobs),
        "sample": [j.title for j in jobs[:3]],
    }


@health.post("/detect-ats", response_model=ATSDetectResponse)
async def detect_ats(body: ATSDetectRequest, user: CurrentUser) -> ATSDetectResponse:
    """Auto-detect ATS platform, board token, sitemap, and feeds from an employer URL."""
    from backend.services import ats_detector

    result = await ats_detector.detect_career_url(body.url, fetch_if_needed=True)
    return ATSDetectResponse(**result)


@health.post("/reap-expired", response_model=ReapResponse)
def reap_expired(user: CurrentAdmin, db: DbSession, max_age_days: int = Query(45, ge=7, le=180)) -> ReapResponse:
    """Flag stale active jobs older than max_age_days as expired."""
    from backend.services import discovery_service

    count = discovery_service.reap_expired_jobs(db, max_age_days=max_age_days)
    return ReapResponse(reaped_count=count, cutoff_days=max_age_days, timestamp=utcnow())


@health.get("/sources/catalog", response_model=list[dict])
def sources_catalog(user: CurrentUser, category: str | None = Query(None)) -> list[dict]:
    """Retrieve catalog of vetted technology employers and discovery feeds."""
    from backend.services.source_policies import list_policies

    policies = list_policies()
    out = []
    for p in policies:
        if category and p.category.value != category:
            continue
        out.append({
            "source_id": p.source_id,
            "name": p.name,
            "domain": p.domain,
            "category": p.category.value,
            "access_method": p.access_method.value,
            "permission_status": p.permission_status.value,
            "rate_limit_rpm": p.rate_limit_rpm,
            "notes": p.notes,
        })
    return out


