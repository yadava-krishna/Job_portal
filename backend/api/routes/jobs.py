from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select

from backend.api import serializers
from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.db import session_factory
from backend.models import Application, DiscoveryRun, Job, JobSourceLink, User, UserJob, utcnow
from backend.schemas.jobs import DiscoverRequest, DiscoveryRunOut, ImportJobRequest, ImportResult, JobAnalysis, JobDetail, JobList, SearchLinkOut
from backend.schemas.profile import JobMatchIntelligenceOut
from backend.services import discovery_service, resume_service
from backend.services.matching_service import UserMatcher, compute_career_intelligence
from core import timeutil
from core.models import MatchResult
from intelligence.jd_analyzer import JDAnalyzer

router = APIRouter(prefix="/jobs", tags=["jobs"])
VERIFIED = discovery_service.VERIFIED_DATE_SOURCES


def _owned(db, user: User, user_job_id: int) -> UserJob:
    uj = db.execute(select(UserJob).where(UserJob.id == user_job_id, UserJob.user_id == user.id)).unique().scalar_one_or_none()
    if uj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found in your feed.")
    return uj


def _discover_bg(settings, user_id: int, run_id: int, sources: list[str] | None) -> None:
    from backend.services import saved_search_service

    db = session_factory()()
    try:
        user = db.get(User, user_id)
        run = db.get(DiscoveryRun, run_id)
        if user and run:
            if sources:
                discovery_service.run_discovery(db, settings, user, sources, run=run)
            else:
                saved_search_service.run_all(db, settings, user, run)
    finally:
        db.close()


@router.post("/discover", response_model=DiscoveryRunOut, status_code=status.HTTP_202_ACCEPTED)
def discover(body: DiscoverRequest, user: CurrentUser, db: DbSession, settings: SettingsDep, bg: BackgroundTasks) -> DiscoveryRunOut:
    """Run discovery now: company job boards (your saved searches), Adzuna and alert emails. Poll /jobs/runs/{id}.

    Every source reports an outcome on the run (`source_results`), including why it did not run.
    """
    running = db.execute(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id, DiscoveryRun.status == "running",
                                                    DiscoveryRun.started_at > utcnow() - timedelta(minutes=10))).scalars().first()
    if running:
        return serializers.run(running)
    run = discovery_service.start_run(db, user, "manual", list(body.sources or ["all"]))
    bg.add_task(_discover_bg, settings, user.id, run.id, list(body.sources) if body.sources else None)
    return serializers.run(run)


@router.get("/runs", response_model=list[DiscoveryRunOut])
def runs(user: CurrentUser, db: DbSession, limit: int = Query(10, ge=1, le=50)) -> list[DiscoveryRunOut]:
    rows = db.execute(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id).order_by(DiscoveryRun.id.desc()).limit(limit)).scalars()
    return [serializers.run(r) for r in rows]


@router.get("/runs/{run_id}", response_model=DiscoveryRunOut)
def get_run(run_id: int, user: CurrentUser, db: DbSession) -> DiscoveryRunOut:
    run = db.execute(select(DiscoveryRun).where(DiscoveryRun.id == run_id, DiscoveryRun.user_id == user.id)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return serializers.run(run)


@router.post("/import", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def import_job(body: ImportJobRequest, user: CurrentUser, db: DbSession, settings: SettingsDep) -> ImportResult:
    """Add a job you found (URL + pasted description). It is scored against your profile immediately."""
    if not body.url and not body.title:
        raise HTTPException(422, "Provide at least the job URL or title.")
    run, feed = discovery_service.import_job(db, settings, user, body)
    return ImportResult(run=serializers.run(run), user_job_ids=[u.id for u in feed], errors=[e["message"] for e in run.error_details or []])


@router.post("/import-file", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
async def import_file(user: CurrentUser, db: DbSession, settings: SettingsDep, file: UploadFile = File(...)) -> ImportResult:
    content = await file.read(2 * 1024 * 1024 + 1)
    run, feed, errors = discovery_service.import_file(db, settings, user, file.filename or "", content)
    return ImportResult(run=serializers.run(run), user_job_ids=[u.id for u in feed], errors=errors)


@router.get("/search-links", response_model=list[SearchLinkOut])
def links(user: CurrentUser, db: DbSession) -> list[SearchLinkOut]:
    return [SearchLinkOut(**l) for l in discovery_service.search_links(db, user)]


@router.get("", response_model=JobList)
def list_jobs(
    user: CurrentUser, db: DbSession,
    view: Literal["feed", "saved", "dismissed", "applied", "all"] = "feed",
    q: str | None = Query(None, max_length=200, description="Search title, company or description"),
    platform: list[str] | None = Query(None, description="Matches any source the job was seen on (LinkedIn, Greenhouse, Adzuna…)"),
    posted: Literal["any", "today", "24h", "3d", "7d", "30d", "range"] = "any",
    include_estimated: bool = Query(False, description="Let estimated dates (alert emails) count in posted-date windows"),
    confidence: list[Literal["verified", "estimated", "unknown"]] | None = Query(None),
    date_from: date | None = None, date_to: date | None = None,
    industry: str | None = Query(None, max_length=100),
    employment_type: list[str] | None = Query(None),
    company: str | None = Query(None, max_length=200),
    saved_search_id: int | None = None,
    include_closed: bool = Query(False, description="Include jobs no longer listed on the employer's board"),
    include_unknown_dates: bool = Query(False, description="With a posting-date filter, also list jobs whose posting date is unknown"),
    domain: str | None = Query(None, max_length=100),
    location: str | None = Query(None, max_length=100),
    work_mode: list[str] | None = Query(None),
    experience: float | None = Query(None, ge=0, le=60, description="Show jobs whose experience range includes this many years"),
    salary_min_lpa: float | None = Query(None, ge=0),
    min_score: float | None = Query(None, ge=0, le=100),
    skill: str | None = Query(None, max_length=100, description="Jobs that ask for this skill (in requirements or description)"),
    application_status: list[Literal["none", "PREPARED", "OPENED", "CONFIRMATION_PENDING", "SUBMITTED", "FAILED", "WITHDRAWN"]] | None = Query(None),
    sort: Literal["score", "posted", "discovered"] = "score",
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
) -> JobList:
    stmt = select(UserJob).join(Job, Job.id == UserJob.job_id).where(UserJob.user_id == user.id)
    if view == "feed":
        stmt = stmt.where(UserJob.status.in_(["new", "shortlisted"]))
    elif view == "saved":
        stmt = stmt.where(UserJob.is_saved.is_(True), UserJob.status != "dismissed")
    elif view == "dismissed":
        stmt = stmt.where(UserJob.status == "dismissed")
    elif view == "applied":
        stmt = stmt.where(UserJob.status == "applied")
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Job.title).like(like), func.lower(Job.company).like(like), func.lower(Job.description).like(like)))
    if platform:
        linked = select(JobSourceLink.id).where(JobSourceLink.job_id == Job.id, JobSourceLink.platform.in_(platform)).exists()
        stmt = stmt.where(or_(Job.platform.in_(platform), linked))
    today = timeutil.today()
    # Date filters only trust dates we can vouch for; an unknown date never counts as recent or in range. Such jobs are
    # counted (hidden_unknown_dates) and can be listed with include_unknown_dates=true, labelled "Posting date unknown".
    known = [*VERIFIED, "alert_email"]
    trusted = Job.posted_at_source.in_(VERIFIED) if not include_estimated else Job.posted_at_source.in_(known)
    unknown_date = Job.posted_at.is_(None) | Job.posted_at_source.is_(None) | Job.posted_at_source.not_in(known)
    windows = {"today": 0, "24h": 1, "3d": 3, "7d": 7, "30d": 30}
    date_cond = None
    if posted == "today":
        date_cond = (Job.posted_at == today) & Job.posted_at_source.in_(VERIFIED)
    elif posted in windows:
        date_cond = (Job.posted_at >= today - timedelta(days=windows[posted])) & trusted
    elif posted == "range" and (date_from or date_to):  # "Date range" with no dates entered filters nothing
        date_cond = Job.posted_at.is_not(None) & Job.posted_at_source.in_(known)
        if date_from:
            date_cond = date_cond & (Job.posted_at >= date_from)
        if date_to:
            date_cond = date_cond & (Job.posted_at <= date_to)
    if domain:
        like = f"%{domain.lower()}%"
        stmt = stmt.where(or_(func.lower(Job.title).like(like), func.lower(Job.description).like(like)))
    if location:
        stmt = stmt.where(func.lower(Job.location).like(f"%{location.lower()}%"))
    if work_mode:
        stmt = stmt.where(Job.work_mode.in_(work_mode))
    if experience is not None:
        stmt = stmt.where(or_(Job.experience_min.is_(None), Job.experience_min <= experience),
                          or_(Job.experience_max.is_(None), Job.experience_max >= experience))
    if salary_min_lpa is not None:
        stmt = stmt.where(or_(Job.salary_max_lpa >= salary_min_lpa, Job.salary_min_lpa >= salary_min_lpa))
    if min_score is not None:
        stmt = stmt.where(UserJob.match_score >= min_score)
    if skill:
        like = f"%{skill.lower()}%"
        stmt = stmt.where(or_(func.lower(cast(Job.required_skills, String)).like(like), func.lower(cast(Job.preferred_skills, String)).like(like),
                              func.lower(Job.description).like(like)))
    if application_status:
        app_status = select(Application.status).where(Application.user_id == user.id, Application.job_id == Job.id).scalar_subquery()
        conds = [app_status.in_([s for s in application_status if s != "none"])] if any(s != "none" for s in application_status) else []
        if "none" in application_status:
            conds.append(~select(Application.id).where(Application.user_id == user.id, Application.job_id == Job.id).exists())
        stmt = stmt.where(or_(*conds))
    if confidence:
        conds = []
        if "verified" in confidence:
            conds.append(Job.posted_at.is_not(None) & Job.posted_at_source.in_(VERIFIED))
        if "estimated" in confidence:
            conds.append(Job.posted_at.is_not(None) & (Job.posted_at_source == "alert_email"))
        if "unknown" in confidence:
            conds.append(Job.posted_at.is_(None) | Job.posted_at_source.is_(None)
                         | Job.posted_at_source.not_in([*VERIFIED, "alert_email"]))
        stmt = stmt.where(or_(*conds))
    if industry:
        stmt = stmt.where(func.lower(Job.industry) == industry.lower())
    if employment_type:
        stmt = stmt.where(Job.employment_type.in_(employment_type))
    if company:
        stmt = stmt.where(func.lower(Job.company).like(f"%{company.lower()}%"))
    if saved_search_id is not None:
        found_by = select(DiscoveryRun.id).where(DiscoveryRun.id == UserJob.discovery_run_id, DiscoveryRun.saved_search_id == saved_search_id,
                                                 DiscoveryRun.user_id == user.id).exists()
        stmt = stmt.where(found_by)
    if not include_closed and view == "feed":
        stmt = stmt.where(Job.closed_at.is_(None))
    hidden_unknown = 0
    if date_cond is not None:
        if include_unknown_dates:
            stmt = stmt.where(date_cond | unknown_date)
        else:
            hidden_unknown = db.execute(select(func.count()).select_from(stmt.where(unknown_date).subquery())).scalar_one()
            stmt = stmt.where(date_cond)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    order = {
        "score": (UserJob.match_score.desc().nullslast(), UserJob.id.desc()),
        "posted": (Job.posted_at.desc().nullslast(), UserJob.id.desc()),
        "discovered": (UserJob.discovered_at.desc(), UserJob.id.desc()),
    }[sort]
    rows = db.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)).unique().scalars().all()
    return JobList(items=serializers.user_jobs(db, list(rows)), total=total, page=page, page_size=page_size,
                   hidden_unknown_dates=hidden_unknown)


@router.get("/{user_job_id}", response_model=JobDetail)
def get_job(user_job_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> JobDetail:
    uj = _owned(db, user, user_job_id)
    from backend.services import tracker_service

    tracker_service.record_view(db, user, uj.job_id)  # "jobs viewed" metric and recently-viewed list
    return serializers.job_detail(db, uj, JDAnalyzer(resume_service.taxonomy(settings)))


@router.get("/{user_job_id}/analysis", response_model=JobAnalysis)
def analysis(user_job_id: int, user: CurrentUser, db: DbSession) -> JobAnalysis:
    uj = _owned(db, user, user_job_id)
    m = MatchResult.model_validate(uj.match) if uj.match else None
    comp = {c.name: c for c in (m.components if m else [])}
    return JobAnalysis(
        user_job_id=uj.id, overall_score=uj.match_score, category=uj.match_category,
        components=[c.model_dump() for c in (m.components if m else [])],
        matching_skills=m.matching_skills if m else [], missing_skills=m.missing_skills if m else [],
        missing_optional_skills=m.missing_optional_skills if m else [], relevant_experience=m.relevant_experience if m else "",
        experience_gap=m.experience_gap if m else "", education_match=comp["education"].evidence if "education" in comp else None,
        location_match=comp["location"].evidence if "location" in comp else None,
        responsibilities_match=m.matching_responsibilities if m else [], reasons_for=m.reasons_for if m else [],
        reasons_against=m.reasons_against if m else [], recommendation=m.recommendation if m else "",
        explanation=m.explanation() if m else "Not scored yet.", eligibility_status=uj.eligibility_status,
        eligibility_reasons=uj.eligibility_reasons or [], scoring_method=uj.scoring_method,
        confidence=m.confidence if m else None, notes=m.notes if m else [],
        score_version=uj.score_version, dimensions=uj.match_components or [], eligibility=uj.eligibility,
        unknown_dimensions=(uj.match or {}).get("unknown_dimensions", []), disclaimer=(uj.match or {}).get("disclaimer"),
    )


class DescriptionIn(BaseModel):
    description: str = Field(min_length=80, max_length=60000)


@router.put("/{user_job_id}/description", response_model=JobDetail)
def add_description(user_job_id: int, body: DescriptionIn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> JobDetail:
    """Attach a full description to a job that only has a snippet or none, then re-score it for you."""
    uj = _owned(db, user, user_job_id)
    job = uj.job
    if job.description and not job.description_is_snippet and len(job.description) >= 80:
        raise HTTPException(status.HTTP_409_CONFLICT, "This job already has a full description.")
    a = JDAnalyzer(resume_service.taxonomy(settings)).analyze(body.description, title=job.title)
    job.description, job.description_is_snippet = body.description.strip(), False
    job.required_skills, job.preferred_skills = a.required_skills, a.preferred_skills
    job.education_requirements, job.mandatory_qualifications = a.education, a.mandatory_qualifications
    if job.experience_min is None and a.exp_min is not None:
        job.experience_min, job.experience_max, job.experience_required = a.exp_min, a.exp_max, a.experience_text
    if uj.status in ("new", "shortlisted"):
        UserMatcher(db, settings, user).apply(uj)
    db.commit()
    return serializers.job_detail(db, uj, JDAnalyzer(resume_service.taxonomy(settings)))


@router.post("/{user_job_id}/rescore", response_model=JobDetail)
def rescore(user_job_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> JobDetail:
    uj = _owned(db, user, user_job_id)
    UserMatcher(db, settings, user).apply(uj)
    db.commit()
    return serializers.job_detail(db, uj, JDAnalyzer(resume_service.taxonomy(settings)))


@router.post("/{user_job_id}/save", response_model=JobDetail)
def save(user_job_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> JobDetail:
    uj = _owned(db, user, user_job_id)
    uj.is_saved, uj.saved_at = True, uj.saved_at or utcnow()
    if uj.status == "dismissed":
        uj.status, uj.dismissed_at = "new", None
    db.commit()
    return serializers.job_detail(db, uj, JDAnalyzer(resume_service.taxonomy(settings)))


@router.delete("/{user_job_id}/save", response_model=JobDetail)
def unsave(user_job_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> JobDetail:
    uj = _owned(db, user, user_job_id)
    uj.is_saved, uj.saved_at = False, None
    db.commit()
    return serializers.job_detail(db, uj, JDAnalyzer(resume_service.taxonomy(settings)))


@router.post("/{user_job_id}/dismiss", response_model=JobDetail)
def dismiss(user_job_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> JobDetail:
    uj = _owned(db, user, user_job_id)
    if uj.status == "applied":
        raise HTTPException(status.HTTP_409_CONFLICT, "Applied jobs cannot be dismissed.")
    uj.status, uj.dismissed_at = "dismissed", utcnow()
    db.commit()
    return serializers.job_detail(db, uj, JDAnalyzer(resume_service.taxonomy(settings)))


@router.post("/{user_job_id}/restore", response_model=JobDetail)
def restore(user_job_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> JobDetail:
    uj = _owned(db, user, user_job_id)
    if uj.status == "dismissed":
        uj.status, uj.dismissed_at = "new", None
        try:
            UserMatcher(db, settings, user, use_llm=False).apply(uj)
        except HTTPException:
            pass
    db.commit()
    return serializers.job_detail(db, uj, JDAnalyzer(resume_service.taxonomy(settings)))


# --- Phase 10: Career Intelligence 4-Factor Matching Endpoint ---

@router.get("/{job_id}/intelligence", response_model=JobMatchIntelligenceOut)
def get_job_intelligence(job_id: int, user: CurrentUser, db: DbSession) -> JobMatchIntelligenceOut:
    """Calculates explainable 4-factor career match score and learning roadmap for a job."""
    from backend.services.jd_intelligence_service import JDIntelligenceService
    from backend.services.profile_master_service import ProfileMasterService
    from backend.services.skill_gap_service import SkillGapService

    job = db.get(Job, job_id)
    if not job:
        uj = db.execute(select(UserJob).where(UserJob.id == job_id, UserJob.user_id == user.id)).unique().scalar_one_or_none()
        if uj:
            job = uj.job
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")

    report = compute_career_intelligence(db, user, job)

    profile = ProfileMasterService.get_or_create_profile(db, user.id)
    candidate_skills = [s.name for s in profile.skills]
    jd_analysis = JDIntelligenceService.analyze_jd(job.title or "", job.description or "", job.location or "")
    gap_report = SkillGapService.analyze_skill_gaps(candidate_skills, jd_analysis.required_skills, jd_analysis.preferred_skills)

    return JobMatchIntelligenceOut(
        job_id=job.id,
        composite_score=report.composite_score,
        eligibility_score=report.eligibility_score,
        skill_score=report.skill_score,
        experience_score=report.experience_score,
        preference_score=report.preference_score,
        matched_skills=report.matched_skills,
        missing_skills=report.missing_skills,
        disqualifiers=report.disqualifiers,
        explanation=report.explanation,
        learning_roadmap=gap_report.learning_roadmap,
    )

