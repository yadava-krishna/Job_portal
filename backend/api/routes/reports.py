from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.models import Report
from backend.schemas.applications import ReportOut
from backend.services import dashboard_service, report_service

router = APIRouter(tags=["reports", "dashboard"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _out(r: Report) -> ReportOut:
    return ReportOut(id=r.id, kind=r.kind, report_date=r.report_date, file_name=r.file_name, size_bytes=r.size_bytes, created_at=r.created_at)


@router.get("/reports", response_model=list[ReportOut])
def list_reports(user: CurrentUser, db: DbSession, limit: int = Query(50, ge=1, le=200)) -> list[ReportOut]:
    rows = db.execute(select(Report).where(Report.user_id == user.id).order_by(Report.id.desc()).limit(limit)).scalars()
    return [_out(r) for r in rows]


@router.get("/reports/daily", response_model=ReportOut)
def daily(user: CurrentUser, db: DbSession, settings: SettingsDep, day: date | None = None) -> ReportOut:
    """The latest daily workbook for `day` (default today); generated if none exists yet."""
    from core import timeutil

    day = day or timeutil.today()
    existing = db.execute(select(Report).where(Report.user_id == user.id, Report.kind == "daily", Report.report_date == day)
                          .order_by(Report.id.desc()).limit(1)).scalar_one_or_none()
    return _out(existing or report_service.generate(db, settings, user, "daily", day))


@router.post("/reports/daily", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def regenerate_daily(user: CurrentUser, db: DbSession, settings: SettingsDep, day: date | None = None) -> ReportOut:
    """Generate a fresh daily workbook reflecting the latest state. Earlier files are kept, never overwritten."""
    return _out(report_service.generate(db, settings, user, "daily", day))


@router.post("/reports/history", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def history(user: CurrentUser, db: DbSession, settings: SettingsDep) -> ReportOut:
    """Generate a workbook with your complete job and application history."""
    return _out(report_service.generate(db, settings, user, "history"))


@router.get("/reports/{report_id}/download")
def download(report_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> FileResponse:
    path, name = report_service.report_file(db, settings, user, report_id)
    return FileResponse(path, media_type=XLSX, filename=name, headers={"Cache-Control": "private, no-store"})


@router.get("/dashboard/summary")
def summary(user: CurrentUser, db: DbSession) -> dict:
    return dashboard_service.summary(db, user)


@router.get("/dashboard/activity")
def activity(user: CurrentUser, db: DbSession, limit: int = Query(30, ge=1, le=100)) -> list[dict]:
    return dashboard_service.activity(db, user, limit)


@router.get("/dashboard/analytics")
def analytics(user: CurrentUser, db: DbSession, days: int = Query(30, ge=7, le=180)) -> dict:
    return dashboard_service.analytics(db, user, days)
