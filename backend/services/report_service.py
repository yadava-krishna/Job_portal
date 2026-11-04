"""Per-user Excel reports using the existing OpenPyXL generator, unchanged.

`UserReportSource` exposes the same read methods the generator calls on the CLI's SQLite
`Database` (report_rows, runs_on, errors_on, platform_status_on), built from one user's
Postgres rows, so a report can only ever contain that user's data.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import Application, ApplicationEvent, CandidateProfile, DiscoveryRun, JobPreference, Report, RunError, User, UserJob
from backend.services.discovery_service import search_links
from core import timeutil
from core.models import Platform
from platforms.base_platform import SearchLink
from reports.excel_generator import ExcelReportGenerator


def _local_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timeutil.tz()).isoformat(timespec="seconds")


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    """Local-day bounds expressed in UTC (works for Postgres timestamptz and SQLite's naive UTC storage)."""
    start = datetime.combine(day, time.min, tzinfo=timeutil.tz()).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def pipeline_label(uj: UserJob, min_score: float) -> str:
    if uj.status == "dismissed":
        return "DISMISSED"
    if uj.status == "applied":
        return "APPLICATION_CREATED"
    if uj.status == "shortlisted":
        return "SHORTLISTED"
    if uj.match_score is None:
        return "DISCOVERED"
    if not uj.job.description or len(uj.job.description) < 80:
        return "NEEDS_DESCRIPTION"
    if uj.eligibility_status == "INELIGIBLE":
        return "NOT_ELIGIBLE"
    return "BELOW_THRESHOLD" if uj.match_score < min_score else "SCORED"


class UserReportSource:
    def __init__(self, db: Session, user: User, *, history: bool = False):
        self.db, self.user, self.history = db, user, history
        prefs = db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none()
        self.min_score = prefs.min_match_score if prefs else 70

    def report_rows(self, day: date) -> list[dict[str, Any]]:
        q = select(UserJob, Application).outerjoin(
            Application, and_(Application.job_id == UserJob.job_id, Application.user_id == UserJob.user_id)
        ).where(UserJob.user_id == self.user.id)
        if not self.history:
            start, end = _day_bounds(day)
            changed = select(ApplicationEvent.application_id).where(ApplicationEvent.user_id == self.user.id,
                                                                    ApplicationEvent.created_at >= start, ApplicationEvent.created_at < end)
            q = q.where(or_(and_(UserJob.discovered_at >= start, UserJob.discovered_at < end), Application.id.in_(changed)))
        rows = []
        for uj, app in self.db.execute(q.order_by(UserJob.match_score.desc().nullslast(), UserJob.id)).unique().all():
            j = uj.job
            rows.append({
                "id": uj.id, "job_key": j.job_key, "platform": j.platform, "platform_job_id": j.external_job_id,
                "company": j.company, "title": j.title, "url": j.job_url, "location": j.location, "work_mode": j.work_mode,
                "employment_type": j.employment_type, "experience_required": j.experience_required, "salary_range": j.salary_range,
                "posted_date": j.posted_at.isoformat() if j.posted_at else None, "description": j.description,
                "required_skills": json.dumps(j.required_skills or []), "preferred_skills": json.dumps(j.preferred_skills or []),
                "first_seen_at": _local_iso(uj.discovered_at), "last_seen_at": _local_iso(uj.discovered_at),
                "match_score": uj.match_score, "match_category": uj.match_category,
                "match_json": json.dumps(uj.match) if uj.match else None,
                "eligibility_status": uj.eligibility_status,
                "eligibility_json": json.dumps({"status": uj.eligibility_status, "reasons": uj.eligibility_reasons or []}) if uj.eligibility_status else None,
                "pipeline_status": pipeline_label(uj, self.min_score), "notes": uj.notes,
                "app_id": app.id if app else None, "app_status": app.status if app else None,
                "app_created_at": _local_iso(app.created_at) if app else None, "submitted_at": _local_iso(app.submitted_at) if app else None,
                "reference_id": app.reference_id if app else None, "confirmation_text": app.confirmation_text if app else None,
                "confirmation_source": app.confirmation_source if app else None, "app_resume_path": app.resume_used if app else None,
                "cover_letter": app.cover_letter if app else None,
                "screening_json": json.dumps(app.screening_answers) if app else None,
                "app_error": None, "app_notes": (f"Stage: {app.stage}" if app and app.stage else (app.notes if app else None)),
            })
        return rows

    def _runs(self, day: date):
        q = select(DiscoveryRun).where(DiscoveryRun.user_id == self.user.id)
        if not self.history:
            start, end = _day_bounds(day)
            q = q.where(DiscoveryRun.started_at >= start, DiscoveryRun.started_at < end)
        return self.db.execute(q.order_by(DiscoveryRun.id)).scalars().all()

    def runs_on(self, day: date) -> list[dict[str, Any]]:
        return [{"stats_json": json.dumps({"platforms": r.platform_stats or {}})} for r in self._runs(day)]

    def errors_on(self, day: date) -> list[dict[str, Any]]:
        q = select(RunError).where(RunError.user_id == self.user.id)
        if not self.history:
            start, end = _day_bounds(day)
            q = q.where(RunError.created_at >= start, RunError.created_at < end)
        return [{"created_at": _local_iso(e.created_at), "platform": e.platform, "job_key": e.job_key, "error_type": e.error_type,
                 "description": e.description, "recovery_status": e.recovery_status} for e in self.db.execute(q.order_by(RunError.id)).scalars()]

    def platform_status_on(self, day: date) -> list[dict[str, Any]]:
        out = []
        for r in self._runs(day):
            for platform, s in (r.platform_stats or {}).items():
                out.append({"platform": platform, "status": r.status, "access_mode": ", ".join(r.sources or []),
                            "records_seen": s.get("records_seen", 0), "error": None})
        return out


def generate(db: Session, settings: BackendSettings, user: User, kind: str, day: date | None = None) -> Report:
    day = day or timeutil.today()
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    years = (prof.experience_months or 0) / 12 if prof else 0.0
    name = ((prof.confirmed_profile or {}).get("full_name") if prof else None) or user.full_name or user.email
    source = UserReportSource(db, user, history=(kind == "history"))
    out_dir = settings.user_dir(user.id, "reports", kind)
    links = [SearchLink(platform=Platform(l["platform"]), title=l["title"],
                        location=l["location"], url=l["url"]) for l in search_links(db, user)]
    path = ExcelReportGenerator(source, out_dir, name, years, source.min_score).generate(day, links)  # type: ignore[arg-type]
    rep = Report(user_id=user.id, kind=kind, report_date=day, file_path=str(path), file_name=path.name, size_bytes=path.stat().st_size)
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return rep


def report_file(db: Session, settings: BackendSettings, user: User, report_id: int) -> tuple[Path, str]:
    rep = db.execute(select(Report).where(Report.id == report_id, Report.user_id == user.id)).scalar_one_or_none()
    if rep is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    path = Path(rep.file_path).resolve()
    owner_dir = settings.user_dir(user.id).resolve()
    if owner_dir not in path.parents or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report file is missing.")
    return path, rep.file_name
