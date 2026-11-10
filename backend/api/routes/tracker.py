"""Phase 4 routes: interviews, offers, contacts, Today, activity, data export and account deletion."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import JSONResponse, Response

from backend.api.deps import CurrentUser, DbSession, SettingsDep, client_ip
from backend.models import ApplicationContact, Interview, Offer
from backend.schemas.tracker import (
    ActivityOut,
    ContactIn,
    ContactOut,
    DeleteAccountIn,
    HeartbeatIn,
    InterviewIn,
    InterviewOut,
    OfferIn,
    OfferOut,
    TodayOut,
)
from backend.services import tracker_service as svc

router = APIRouter(tags=["tracker"])


def _iv(db, iv: Interview) -> InterviewOut:
    from backend.models import Application

    app = db.get(Application, iv.application_id)
    return InterviewOut.model_validate(iv).model_copy(update={"company": app.job.company, "title": app.job.title})


def _offer(db, o: Offer) -> OfferOut:
    from backend.models import Application

    app = db.get(Application, o.application_id)
    return OfferOut.model_validate(o).model_copy(update={"company": app.job.company, "title": app.job.title})


@router.post("/applications/{application_id}/interviews", response_model=InterviewOut, status_code=status.HTTP_201_CREATED)
def add_interview(application_id: int, body: InterviewIn, user: CurrentUser, db: DbSession) -> InterviewOut:
    return _iv(db, svc.add_interview(db, user, application_id, body.model_dump()))


@router.get("/interviews", response_model=list[InterviewOut])
def list_interviews(user: CurrentUser, db: DbSession, upcoming: bool = False, application_id: int | None = None) -> list[InterviewOut]:
    return [_iv(db, i) for i in svc.interviews(db, user, upcoming=upcoming) if application_id is None or i.application_id == application_id]


@router.get("/interviews/calendar.ics")
def calendar(user: CurrentUser, db: DbSession) -> Response:
    return Response(svc.calendar_ics(db, user), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="jobpilot-interviews.ics"', "Cache-Control": "private, no-store"})


@router.put("/interviews/{interview_id}", response_model=InterviewOut)
def update_interview(interview_id: int, body: InterviewIn, user: CurrentUser, db: DbSession) -> InterviewOut:
    return _iv(db, svc.update_interview(db, user, interview_id, body.model_dump()))


@router.delete("/interviews/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview(interview_id: int, user: CurrentUser, db: DbSession) -> None:
    svc.delete_row(db, user, Interview, interview_id)


@router.put("/applications/{application_id}/offer", response_model=OfferOut)
def put_offer(application_id: int, body: OfferIn, user: CurrentUser, db: DbSession) -> OfferOut:
    return _offer(db, svc.upsert_offer(db, user, application_id, body.model_dump()))


@router.get("/offers", response_model=list[OfferOut])
def list_offers(user: CurrentUser, db: DbSession) -> list[OfferOut]:
    return [_offer(db, o) for o in svc.offers(db, user)]


@router.delete("/offers/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offer(offer_id: int, user: CurrentUser, db: DbSession) -> None:
    svc.delete_row(db, user, Offer, offer_id)


@router.get("/applications/{application_id}/contacts", response_model=list[ContactOut])
def list_contacts(application_id: int, user: CurrentUser, db: DbSession) -> list[ContactOut]:
    return [ContactOut.model_validate(c) for c in svc.contacts(db, user, application_id)]


@router.post("/applications/{application_id}/contacts", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def add_contact(application_id: int, body: ContactIn, user: CurrentUser, db: DbSession) -> ContactOut:
    return ContactOut.model_validate(svc.add_contact(db, user, application_id, body.model_dump()))


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(contact_id: int, user: CurrentUser, db: DbSession) -> None:
    svc.delete_row(db, user, ApplicationContact, contact_id)


@router.get("/dashboard/today", response_model=TodayOut)
def today(user: CurrentUser, db: DbSession) -> TodayOut:
    return TodayOut(**svc.today_view(db, user))


@router.post("/activity/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def heartbeat(body: HeartbeatIn, user: CurrentUser, db: DbSession) -> None:
    svc.heartbeat(db, user, body.visible, body.active)


@router.get("/dashboard/activity-metrics", response_model=ActivityOut)
def activity_metrics(user: CurrentUser, db: DbSession, days: int = Query(30, ge=1, le=365)) -> ActivityOut:
    return ActivityOut(**svc.activity_metrics(db, user, days))


@router.get("/account/export")
def export(user: CurrentUser, db: DbSession) -> JSONResponse:
    return JSONResponse(svc.export(db, user), headers={"Content-Disposition": 'attachment; filename="jobpilot-my-data.json"',
                                                       "Cache-Control": "private, no-store"})


@router.post("/account/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(body: DeleteAccountIn, request: Request, user: CurrentUser, db: DbSession, settings: SettingsDep) -> None:
    """Permanently delete your account and everything in it (resumes, jobs, applications). Requires your password."""
    svc.delete_account(db, settings, user, body.password, client_ip(request, settings))
