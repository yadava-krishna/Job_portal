"""ORM → response-schema conversion."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Application, DiscoveryRun, Job, JobSourceLink, UserJob
from backend.schemas.applications import ApplicationDetail, ApplicationOut, EventOut
from backend.schemas.jobs import DiscoveryRunOut, JobDetail, JobListing, JobSourceOut, UserJobOut
from backend.services import application_service
from backend.services.discovery_service import posted_label
from backend.services.normalization import posted_confidence
from intelligence.jd_analyzer import JDAnalyzer


def job_links(db: Session, job_ids: list[int]) -> dict[int, list[JobSourceLink]]:
    out: dict[int, list[JobSourceLink]] = {}
    if job_ids:
        for link in db.execute(select(JobSourceLink).where(JobSourceLink.job_id.in_(job_ids)).order_by(JobSourceLink.id)).scalars():
            out.setdefault(link.job_id, []).append(link)
    return out


def job_listing(job: Job, links: list[JobSourceLink] | None = None) -> JobListing:
    desc = (job.description or "").strip()
    preview = " ".join(desc.split())[:280] + ("…" if len(desc) > 280 else "") if desc else None
    return JobListing(
        id=job.id, platform=job.platform, external_job_id=job.external_job_id, company=job.company, title=job.title,
        location=job.location, work_mode=job.work_mode, employment_type=job.employment_type, experience_required=job.experience_required,
        salary_range=job.salary_range, job_url=job.job_url, posted_at=job.posted_at, posted_at_source=job.posted_at_source,
        posted_label=posted_label(job), description_preview=preview,
        has_full_description=bool(desc) and len(desc) >= 80 and not job.description_is_snippet, source=job.source,
        posted_at_confidence=posted_confidence(job.posted_at, job.posted_at_source), first_seen_at=job.discovered_at or job.created_at,
        last_verified_at=job.last_verified_at, closed_at=job.closed_at, industry=job.industry, department=job.department, seniority=job.seniority, sponsorship_signal=job.sponsorship_signal,
        sources=[JobSourceOut(source=l.source, platform=l.platform, url=l.url, first_seen_at=l.first_seen_at) for l in links or []],
    )


def _apps_by_job(db: Session, user_id: int, job_ids: list[int]) -> dict[int, Application]:
    if not job_ids:
        return {}
    rows = db.execute(select(Application).where(Application.user_id == user_id, Application.job_id.in_(job_ids))).unique().scalars()
    return {a.job_id: a for a in rows}


def user_jobs(db: Session, items: list[UserJob]) -> list[UserJobOut]:
    if not items:
        return []
    apps = _apps_by_job(db, items[0].user_id, [u.job_id for u in items])
    links = job_links(db, [u.job_id for u in items])
    return [user_job(u, apps.get(u.job_id), links.get(u.job_id)) for u in items]


def user_job(uj: UserJob, app: Application | None, links: list[JobSourceLink] | None = None) -> UserJobOut:
    return UserJobOut(
        user_job_id=uj.id, status=uj.status, is_saved=uj.is_saved, match_score=uj.match_score, match_category=uj.match_category,
        matching_skills=uj.matching_skills or [], missing_skills=uj.missing_skills or [], eligibility_status=uj.eligibility_status, eligibility=uj.eligibility,
        eligibility_reasons=list(uj.eligibility_reasons or [])[:5], scoring_method=uj.scoring_method, discovered_at=uj.discovered_at, saved_at=uj.saved_at, dismissed_at=uj.dismissed_at,
        application_id=app.id if app else None, application_status=app.status if app else None, job=job_listing(uj.job, links),
    )


def job_detail(db: Session, uj: UserJob, analyzer: JDAnalyzer) -> JobDetail:
    app = _apps_by_job(db, uj.user_id, [uj.job_id]).get(uj.job_id)
    base = user_job(uj, app, job_links(db, [uj.job_id]).get(uj.job_id)).model_dump()
    job = uj.job
    return JobDetail(
        **base, description=job.description, responsibilities=analyzer.analyze(job.description or "").responsibilities if job.description else [],
        required_skills=job.required_skills or [], preferred_skills=job.preferred_skills or [],
        education_requirements=job.education_requirements or [], mandatory_qualifications=job.mandatory_qualifications or [],
        verification_flags=job.verification_flags or [], description_is_snippet=job.description_is_snippet,
    )


def application(app: Application, uj: UserJob | None = None) -> ApplicationOut:
    return ApplicationOut(
        id=app.id, status=app.status, stage=app.stage, user_job_id=app.user_job_id,
        match_score=uj.match_score if uj else None, match_category=uj.match_category if uj else None,
        resume_used=app.resume_used, reference_id=app.reference_id, confirmation_text=app.confirmation_text,
        confirmation_source=app.confirmation_source, created_at=app.created_at, opened_at=app.opened_at, submitted_at=app.submitted_at,
        submission_method=application_service.submission_method(app), follow_up_at=app.follow_up_at, job=job_listing(app.job),
        application_route=getattr(app, "application_route", "ROUTE_D_EXTERNAL_MANUAL") or "ROUTE_D_EXTERNAL_MANUAL",
        tailored_resume_id=getattr(app, "tailored_resume_id", None),
        route_metadata=getattr(app, "route_metadata", {}) or {},
        resume_version_id=app.resume_version_id, resume_export_id=app.resume_export_id, resume_checksum=app.resume_checksum,
        rejection_reason=app.rejection_reason, rejection_detail=app.rejection_detail, rejection_reason_known=app.rejection_reason_known,
    )


def application_detail(db: Session, user, app: Application) -> ApplicationDetail:
    uj = db.get(UserJob, app.user_job_id) if app.user_job_id else None
    base = application(app, uj if uj and uj.user_id == user.id else None).model_dump()
    return ApplicationDetail(
        **base, cover_letter=app.cover_letter, screening_answers=app.screening_answers or [], checklist=app.checklist or [],
        needs_candidate_input=application_service.needs_input(app), notes=app.notes,
        events=[EventOut(id=e.id, event_type=e.event_type, from_status=e.from_status, to_status=e.to_status, details=e.details,
                         created_at=e.created_at) for e in application_service.events(db, user, app)],
    )


def run(r: DiscoveryRun) -> DiscoveryRunOut:
    return DiscoveryRunOut(id=r.id, trigger=r.trigger, status=r.status, sources=r.sources or [], started_at=r.started_at,
                           completed_at=r.completed_at, jobs_found=r.jobs_found, jobs_new=r.jobs_new, jobs_matched=r.jobs_matched,
                           duplicates=r.duplicates, error_details=r.error_details or [], platform_stats=r.platform_stats or {},
                           saved_search_id=r.saved_search_id, source_results=r.source_results or {}, summary=r.summary)
