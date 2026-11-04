from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from backend.api.deps import SettingsDep
from backend.config import VERSION
from backend.db import check_database
from backend.services.scheduler_service import get_scheduler

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health(settings: SettingsDep, response: Response) -> dict:
    """Liveness plus dependency status. The frontend polls this to decide online/offline."""
    db_ok, db_error = check_database()
    response.headers["Cache-Control"] = "no-store"
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "jobpilot-backend",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database": {"connected": db_ok, "error": db_error},
        "scheduler": get_scheduler(settings).status(),
    }


@router.get("/ready")
def ready(response: Response) -> dict:
    db_ok, db_error = check_database()
    response.headers["Cache-Control"] = "no-store"
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"ready": db_ok, "database": {"connected": db_ok, "error": db_error}}
