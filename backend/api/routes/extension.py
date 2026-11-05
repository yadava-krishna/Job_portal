"""Browser extension API. Two kinds of callers:

* the JobPilot web app (user JWT): create pairing codes, list and disconnect browsers;
* the extension (device credential, `Authorization: Bearer jpx_…`): everything under /extension/* that fills forms or
  tracks applications. Device credentials are accepted nowhere else, and user JWTs are not accepted here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.api.deps import CurrentUser, DbSession, SettingsDep, client_ip, _too_many
from backend.models import ExtensionToken, User
from backend.schemas.extension import (
    AnswerOut,
    AnswersRequest,
    AutofillOut,
    DeviceOut,
    ExtApplicationOut,
    ExtConfirmRequest,
    MatchOut,
    MatchRequest,
    PairingCodeOut,
    PairRequest,
    StartRequest,
    StatusOut,
    TokenOut,
)
from backend.security import rate_limiter
from backend.services import application_service, extension_service as ext, resume_service
from backend.services.answer_service import answer_questions
from backend.models import utcnow

router = APIRouter(prefix="/extension", tags=["extension"])
_bearer = HTTPBearer(auto_error=False)


def _limit(request: Request, settings, key: str, limit: int, window: int) -> None:
    retry = rate_limiter.check(f"ext:{key}:{client_ip(request, settings)}", limit, window)
    if retry is not None:
        raise _too_many(retry)


def _principal(scope: str):
    def dep(db: DbSession, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> tuple[User, ExtensionToken]:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not connected", headers={"WWW-Authenticate": "Bearer"})
        return ext.authenticate(db, credentials.credentials, scope)
    return dep


Autofill = Annotated[tuple[User, ExtensionToken], Depends(_principal(ext.SCOPE_AUTOFILL))]
Track = Annotated[tuple[User, ExtensionToken], Depends(_principal(ext.SCOPE_TRACK))]


def _display(user: User) -> str:
    return resume_service.safe_display_name(user.nickname or user.full_name) or user.email.split("@")[0]


# ---- web app (user JWT) ---------------------------------------------------------------------

@router.post("/pairing-codes", response_model=PairingCodeOut, status_code=status.HTTP_201_CREATED)
def create_pairing_code(user: CurrentUser, db: DbSession, settings: SettingsDep, request: Request) -> PairingCodeOut:
    """A one-time code to type into the extension. Valid for 5 minutes."""
    _limit(request, settings, f"codes:{user.id}", 10, 600)
    code, expires = ext.create_pairing_code(db, user, client_ip(request, settings))
    return PairingCodeOut(code=code, expires_at=expires, expires_in_seconds=int(ext.PAIRING_TTL.total_seconds()))


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(user: CurrentUser, db: DbSession) -> list[DeviceOut]:
    return [DeviceOut(id=t.id, name=t.name, scopes=t.scopes, created_at=t.created_at, last_used_at=t.last_used_at, expires_at=t.expires_at)
            for t in ext.devices(db, user)]


@router.delete("/devices/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_device(token_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep, request: Request) -> None:
    ext.revoke(db, user, token_id, client_ip(request, settings))


# ---- extension (device credential) ----------------------------------------------------------

@router.post("/pair", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def pair(body: PairRequest, db: DbSession, settings: SettingsDep, request: Request) -> TokenOut:
    _limit(request, settings, "pair", 10, 600)
    raw, row, user = ext.pair(db, body.code, body.device_name, client_ip(request, settings))
    return TokenOut(token=raw, token_id=row.id, expires_at=row.expires_at, scopes=row.scopes, user_display_name=_display(user))


@router.post("/rotate", response_model=TokenOut)
def rotate(p: Autofill, db: DbSession, settings: SettingsDep, request: Request) -> TokenOut:
    user, current = p
    raw, row = ext.rotate(db, user, current, client_ip(request, settings))
    return TokenOut(token=raw, token_id=row.id, expires_at=row.expires_at, scopes=row.scopes, user_display_name=_display(user))


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(p: Autofill, db: DbSession, settings: SettingsDep, request: Request) -> None:
    user, current = p
    ext.revoke(db, user, current.id, client_ip(request, settings), reason="extension")


@router.get("/status", response_model=StatusOut)
def ext_status(p: Autofill, db: DbSession) -> StatusOut:
    user, tok = p
    data = ext.autofill_profile(db, user)
    created = ext._aware(tok.created_at)
    return StatusOut(user_display_name=_display(user), token_id=tok.id, expires_at=tok.expires_at,
                     rotate_recommended=created is not None and utcnow() - created > ext.TOKEN_TTL / 3,
                     profile_ready=data["ready"], missing=data["missing"])


@router.post("/match", response_model=MatchOut)
def match(body: MatchRequest, p: Track, db: DbSession) -> MatchOut:
    """Which of your JobPilot jobs is this application page? Answers only for your own jobs."""
    return MatchOut(**ext.match(db, p[0], body.url))


@router.get("/autofill-profile", response_model=AutofillOut)
def autofill_profile(p: Autofill, db: DbSession) -> AutofillOut:
    return AutofillOut(**ext.autofill_profile(db, p[0]))


@router.post("/answers", response_model=list[AnswerOut])
def answers(body: AnswersRequest, p: Autofill, db: DbSession, settings: SettingsDep, request: Request) -> list[AnswerOut]:
    """Answers for the form's question labels, only from your verified information. Labels are not stored."""
    _limit(request, settings, f"answers:{p[1].id}", 60, 600)
    return [AnswerOut(**a) for a in answer_questions(db, settings, p[0], body.questions)]


@router.get("/resume")
def resume(p: Autofill, db: DbSession, settings: SettingsDep, request: Request) -> FileResponse:
    """Your active resume file, for attaching to the form you are filling. Requires an explicit click in the extension."""
    user, tok = p
    _limit(request, settings, f"resume:{tok.id}", 20, 3600)
    r = resume_service.active_resume(db, user)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No resume uploaded.")
    path = Path(r.stored_path).resolve()
    if settings.user_dir(user.id).resolve() not in path.parents or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume file is missing.")
    ext.audit(db, user, "extension.resume_downloaded", client_ip(request, settings), tok, resume_id=r.id)
    db.commit()
    return FileResponse(path, media_type="application/pdf", filename=r.original_filename,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/applications/start", response_model=ExtApplicationOut)
def start(body: StartRequest, p: Track, db: DbSession, settings: SettingsDep) -> ExtApplicationOut:
    """You are filling this job's form: prepare the application (if needed) and mark it in progress. Never 'applied'."""
    user = p[0]
    app = application_service.prepare(db, settings, user, body.user_job_id, None)
    application_service.mark_in_progress(db, user, app, "extension")
    return ExtApplicationOut(application_id=app.id, status=app.status, submitted_at=app.submitted_at)


@router.post("/applications/{application_id}/confirm", response_model=ExtApplicationOut)
def confirm(application_id: int, body: ExtConfirmRequest, p: Track, db: DbSession) -> ExtApplicationOut:
    """Your explicit statement that you did (or did not) submit on the employer's site. Same workflow as the web app."""
    user = p[0]
    app = application_service.owned_application(db, user, application_id)
    already = app.status == "SUBMITTED"
    application_service.confirm(db, user, app, body.submitted, body.reference_id, None, body.notes, source="extension_user_confirmed")
    return ExtApplicationOut(application_id=app.id, status=app.status, submitted_at=app.submitted_at, already_submitted=already and body.submitted)
