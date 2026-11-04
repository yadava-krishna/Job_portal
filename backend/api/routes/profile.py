from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.models import CandidateProfile, Resume
from backend.schemas.profile import (
    EditableProfile,
    EmailIntegrationIn,
    EmailIntegrationOut,
    OnboardingStatus,
    PlatformInfo,
    Preferences,
    PreferencesOut,
    PlatformsUpdate,
    ProfileOut,
    ResumeOut,
    VerifiedFacts,
)
from backend.services import matching_service, preference_service, resume_service
from backend.db import session_factory

router = APIRouter(tags=["profile"])


def _rescore_in_background(settings, user_id: int) -> None:
    from backend.models import User

    db = session_factory()()
    try:
        user = db.get(User, user_id)
        if user:
            matching_service.rescore_user(db, settings, user)
    finally:
        db.close()


def _profile_out(db, user) -> ProfileOut:
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    resume = resume_service.active_resume(db, user)
    if prof is None:
        return ProfileOut(has_resume=resume is not None, resume=ResumeOut.model_validate(resume) if resume else None)
    parsed = resume_service.editable_from_parsed(prof.parsed_profile) if prof.parsed_profile else None
    confirmed = EditableProfile.model_validate(prof.confirmed_profile) if prof.confirmed_profile else None
    exp = resume_service.experience_summary(confirmed or parsed) if (confirmed or parsed) else None
    return ProfileOut(
        has_resume=resume is not None, resume=ResumeOut.model_validate(resume) if resume else None, parsed=parsed, confirmed=confirmed,
        confirmed_at=prof.confirmed_at, experience=exp, parse_warnings=(prof.parsed_profile or {}).get("warnings", []),
        verified_facts=prof.verified_facts or {},
    )


@router.get("/profile", response_model=ProfileOut)
def get_profile(user: CurrentUser, db: DbSession) -> ProfileOut:
    return _profile_out(db, user)


@router.put("/profile", response_model=ProfileOut)
def put_profile(body: EditableProfile, user: CurrentUser, db: DbSession, settings: SettingsDep, bg: BackgroundTasks) -> ProfileOut:
    resume_service.confirm_profile(db, user, body)
    bg.add_task(_rescore_in_background, settings, user.id)
    return _profile_out(db, user)


@router.put("/profile/verified-facts", response_model=ProfileOut)
def put_facts(body: VerifiedFacts, user: CurrentUser, db: DbSession) -> ProfileOut:
    prof = resume_service.get_or_create_profile(db, user)
    prof.verified_facts = body.model_dump()
    db.commit()
    return _profile_out(db, user)


@router.post("/profile/resume", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(user: CurrentUser, db: DbSession, settings: SettingsDep, file: UploadFile = File(...)) -> ProfileOut:
    await resume_service.store_upload(db, settings, user, file)
    resume_service.parse_active_resume(db, settings, user)
    return _profile_out(db, user)


@router.get("/profile/resume")
def download_resume(user: CurrentUser, db: DbSession, settings: SettingsDep) -> FileResponse:
    resume = db.execute(select(Resume).where(Resume.user_id == user.id, Resume.is_active.is_(True)).order_by(Resume.id.desc())).scalars().first()
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No resume uploaded.")
    path = Path(resume.stored_path).resolve()
    if settings.user_dir(user.id).resolve() not in path.parents or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume file is missing.")
    return FileResponse(path, media_type="application/pdf", filename=resume.original_filename,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/profile/parse-resume", response_model=ProfileOut)
def parse_resume(user: CurrentUser, db: DbSession, settings: SettingsDep) -> ProfileOut:
    resume_service.parse_active_resume(db, settings, user)
    return _profile_out(db, user)


@router.get("/onboarding", response_model=OnboardingStatus)
def onboarding(user: CurrentUser, db: DbSession) -> OnboardingStatus:
    return preference_service.onboarding_status(db, user)


@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(user: CurrentUser, db: DbSession) -> PreferencesOut:
    return preference_service.preferences_out(preference_service.get_preferences(db, user))


@router.put("/preferences", response_model=PreferencesOut)
def put_preferences(body: Preferences, user: CurrentUser, db: DbSession, settings: SettingsDep, bg: BackgroundTasks) -> PreferencesOut:
    row = preference_service.save_preferences(db, user, body)
    bg.add_task(_rescore_in_background, settings, user.id)
    return preference_service.preferences_out(row)


@router.get("/platforms", response_model=list[PlatformInfo])
def get_platforms(user: CurrentUser, db: DbSession, settings: SettingsDep) -> list[PlatformInfo]:
    return preference_service.list_platforms(db, settings, user)


@router.put("/platforms/preferences", response_model=list[PlatformInfo])
def put_platforms(body: PlatformsUpdate, user: CurrentUser, db: DbSession, settings: SettingsDep) -> list[PlatformInfo]:
    preference_service.save_platforms(db, settings, user, body)
    return preference_service.list_platforms(db, settings, user)


@router.get("/integrations/email", response_model=EmailIntegrationOut)
def get_email(user: CurrentUser, db: DbSession) -> EmailIntegrationOut:
    return preference_service.email_out(preference_service.get_email_integration(db, user))


@router.put("/integrations/email", response_model=EmailIntegrationOut)
def put_email(body: EmailIntegrationIn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> EmailIntegrationOut:
    return preference_service.email_out(preference_service.save_email_integration(db, settings, user, body))
