"""Browser extension API. Two kinds of callers:

* the JobPilot web app (user JWT): create pairing codes, list and disconnect browsers;
* the extension (device credential, `Authorization: Bearer jpx_…`): everything under /extension/* that fills forms or
  tracks applications. Device credentials are accepted nowhere else, and user JWTs are not accepted here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.api.deps import CurrentUser, DbSession, SettingsDep, client_ip, _too_many
from backend.models import ExtensionToken, User
from backend.schemas.extension import (
    AnswerOut,
    AnswersRequest,
    ApplyStateRequest,
    AutofillOut,
    DeviceOut,
    ExtApplicationOut,
    ExtConfirmRequest,
    ExtPackageOut,
    ExtResumeOut,
    LearnOut,
    LearnRequest,
    MatchOut,
    MatchRequest,
    PairingCodeOut,
    PairRequest,
    ProveOut,
    ProveRequest,
    StartRequest,
    StatusOut,
    TokenOut,
)
from backend.security import rate_limiter
from backend.services import answer_memory, application_service, apply_prep_service, apply_state_service, extension_service as ext, resume_service
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
    user = p[0]
    company = job_id = country = None
    overrides: dict[str, str] = {}
    if body.application_id:
        app = application_service.owned_application(db, user, body.application_id)
        company, job_id, country = app.job.company, app.job_id, app.job.country
        overrides = (app.package or {}).get("overrides") or {}
        # Labels (and what the form marks required/optional) only, so the workspace can show them.
        apply_prep_service.record_form_questions(db, app, body.questions, requirements=body.requirements)
        db.commit()
    out = answer_memory.resolve(db, settings, user, body.questions, company=company, job_id=job_id, overrides=overrides,
                                job_country=country)
    return [AnswerOut(**{k: a.get(k) for k in AnswerOut.model_fields if k in a}) for a in out]


@router.post("/answers/learn", response_model=LearnOut)
def learn(body: LearnRequest, p: Autofill, db: DbSession, settings: SettingsDep, request: Request) -> LearnOut:
    """Remember answers you typed on the employer's form, only the ones you ticked "save for next time" in the panel.
    Sensitive questions are refused; values are validated (years, notice period, amounts, yes/no)."""
    _limit(request, settings, f"learn:{p[1].id}", 30, 600)
    user = p[0]
    company = job_id = None
    if body.application_id:
        app = application_service.owned_application(db, user, body.application_id)
        company, job_id = app.job.company, app.job_id
    saved, errors = [], []
    for it in body.items:
        try:
            answer_memory.save(db, settings, user, question=it.question, answer=it.answer, company=company, job_id=job_id,
                               source="form_correction", commit=False)
            saved.append(it.question)
        except HTTPException as e:
            errors.append({"question": it.question, "error": str(e.detail)})
    db.commit()
    return LearnOut(saved=saved, errors=errors)


@router.post("/prove", response_model=ProveOut)
def prove(body: ProveRequest, db: DbSession, settings: SettingsDep, request: Request) -> ProveOut:
    """Proves this server is the JobPilot that issued the extension's credential, without the credential being sent:
    HMAC-SHA256 keyed with the stored hash of the device credential over the extension's random nonce. The extension
    checks it before sending its credential to a newly published server address."""
    _limit(request, settings, "prove", 30, 600)
    if body.v < 2:
        if not settings.extension_prove_legacy:
            raise HTTPException(status.HTTP_410_GONE, "Update the JobPilot extension: this server needs its newer identity check.")
        return ProveOut(proof=ext.prove(db, body.token_id, body.nonce))
    return ProveOut(proof=ext.prove(db, body.token_id, body.nonce, host=ext.prove_host(settings, body.host, request.headers.get("host"))))


@router.get("/resumes", response_model=list[ExtResumeOut])
def resumes(p: Autofill, db: DbSession) -> list[ExtResumeOut]:
    """Resumes you can attach: uploaded files and Resume Studio versions (PDF or Word)."""
    return [ExtResumeOut(**r) for r in ext.resume_choices(db, p[0])]


@router.get("/resume")
def resume(p: Autofill, db: DbSession, settings: SettingsDep, request: Request, kind: str = "upload", id: int | None = None,
           format: str = "pdf") -> Response:
    """The chosen resume file (default: your active upload), for attaching to the form you are filling.

    Requires an explicit click in the extension. Resume Studio versions are exported on demand as PDF or DOCX.
    """
    user, tok = p
    _limit(request, settings, f"resume:{tok.id}", 30, 3600)
    data, name, media, meta = ext.resume_file(db, settings, user, kind, id, format)
    ext.audit(db, user, "extension.resume_downloaded", client_ip(request, settings), tok, **meta)
    db.commit()
    from urllib.parse import quote

    return Response(data, media_type=media, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}", "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff", "X-Resume-Sha256": meta.get("sha256", ""), "Access-Control-Expose-Headers":
        "Content-Disposition, X-Resume-Sha256"})


def _app_out(app, already: bool = False) -> ExtApplicationOut:
    return ExtApplicationOut(application_id=app.id, status=app.status, submitted_at=app.submitted_at, already_submitted=already,
                             **apply_state_service.summary(app))


@router.post("/applications/start", response_model=ExtApplicationOut)
def start(body: StartRequest, p: Track, db: DbSession, settings: SettingsDep) -> ExtApplicationOut:
    """You are filling this job's form: prepare the application (if needed) and mark it in progress. Never 'applied'."""
    user = p[0]
    app = application_service.prepare(db, settings, user, body.user_job_id, None)
    application_service.mark_in_progress(db, user, app, "extension")
    return _app_out(app)


@router.post("/applications/{application_id}/confirm", response_model=ExtApplicationOut)
def confirm(application_id: int, body: ExtConfirmRequest, p: Track, db: DbSession) -> ExtApplicationOut:
    """Your explicit statement that you did (or did not) submit on the employer's site. Same workflow as the web app."""
    user = p[0]
    app = application_service.owned_application(db, user, application_id)
    already = app.status == "SUBMITTED"
    application_service.confirm(db, user, app, body.submitted, body.reference_id, None, body.notes, source="extension_user_confirmed")
    apply_state_service.after_user_confirm(db, app, body.submitted)
    return _app_out(app, already and body.submitted)


@router.get("/applications/{application_id}", response_model=ExtApplicationOut)
def application_state(application_id: int, p: Track, db: DbSession) -> ExtApplicationOut:
    """Where this application stands, so the extension can resume after a browser restart."""
    return _app_out(application_service.owned_application(db, p[0], application_id))


@router.get("/applications/{application_id}/package", response_model=ExtPackageOut)
def application_package(application_id: int, p: Track, db: DbSession, settings: SettingsDep) -> ExtPackageOut:
    """The resume chosen for this application and the answers typed for it in the Apply Workspace."""
    user = p[0]
    app = application_service.owned_application(db, user, application_id)
    if not app.package or (app.status != "SUBMITTED" and apply_prep_service.is_stale(db, user, app)):
        # Built before the latest profile or saved-answer change: never fill from outdated answers.
        apply_prep_service.build(db, settings, user, app, probe_hosted=False)
    return ExtPackageOut(**apply_prep_service.extension_view(app))


@router.post("/applications/{application_id}/state", response_model=ExtApplicationOut)
def record_state(application_id: int, body: ApplyStateRequest, p: Track, db: DbSession, settings: SettingsDep,
                 request: Request) -> ExtApplicationOut:
    """Record a Smart Apply step (filling, reviewed, submission authorised, confirmed, uncertain, …).

    A submission is recorded only with a confirmation signal from the employer's page; an already submitted
    application can never be authorised again.
    """
    user, tok = p
    _limit(request, settings, f"state:{tok.id}", 240, 3600)
    app = application_service.owned_application(db, user, application_id)
    app = apply_state_service.record(db, user, app, body.state, mode=body.mode, session=body.session, reference_id=body.reference_id)
    return _app_out(app)
