"""Job preferences, platform selection, email integration and onboarding status."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import CandidateProfile, EmailIntegration, JobPreference, PlatformPreference, Resume, User, utcnow
from backend.schemas.profile import (
    EmailIntegrationIn,
    EmailIntegrationOut,
    OnboardingStatus,
    PlatformInfo,
    Preferences,
    PreferencesOut,
    PlatformsUpdate,
)
from backend.security import CredentialCipher
from core.models import Platform
from platforms import get_adapter

SOURCE_LABELS = {
    "user_job_url": "User-provided job URL",
    "browser_clipper": "Browser clipper (you capture the listing you are viewing, in your own logged-in browser)",
    "file_import": "User-provided file import (JSON/CSV/TXT)",
    "alert_email": "User-provided job alert email",
    "manual_search": "Manual search (pre-filtered links)",
    "adzuna_api": "Official integration (Adzuna Jobs API)",
}
PLATFORM_SOURCES = ["browser_clipper", "user_job_url", "file_import", "alert_email", "manual_search"]
ADZUNA = "Adzuna"


def get_preferences(db: Session, user: User) -> JobPreference | None:
    return db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none()


def preferences_out(row: JobPreference | None) -> PreferencesOut:
    if row is None:
        return PreferencesOut(is_configured=False)
    data = {c: getattr(row, c) for c in Preferences.model_fields}
    data["weights"] = row.weights or {}
    data["application_settings"] = row.application_settings or {}
    return PreferencesOut(**data, is_configured=True)


def save_preferences(db: Session, user: User, prefs: Preferences) -> JobPreference:
    if sum(prefs.weights.model_dump().values()) <= 0:
        raise HTTPException(422, "Scoring weights must add up to more than 0.")
    row = get_preferences(db, user) or JobPreference(user_id=user.id)
    for field, value in prefs.model_dump(mode="json").items():
        setattr(row, field, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def platform_rows(db: Session, user: User) -> dict[str, PlatformPreference]:
    rows = db.execute(select(PlatformPreference).where(PlatformPreference.user_id == user.id)).scalars().all()
    return {r.platform: r for r in rows}


def list_platforms(db: Session, settings: BackendSettings, user: User) -> list[PlatformInfo]:
    rows = platform_rows(db, user)
    out = []
    for p in Platform:
        caps = get_adapter(p).capabilities
        row = rows.get(p.value)
        out.append(PlatformInfo(
            platform=p.value,
            enabled=row.enabled if row else False,
            discovery_sources=row.discovery_sources if row else [],
            available_sources=[{"id": s, "label": SOURCE_LABELS[s]} for s in PLATFORM_SOURCES],
            automated_search=caps.automated_search, automated_apply=caps.automated_apply,
            application_method=caps.application_method, notes=caps.notes,
        ))
    row = rows.get(ADZUNA)
    out.append(PlatformInfo(
        platform=ADZUNA,
        enabled=bool(row and row.enabled and settings.adzuna_enabled),
        discovery_sources=["adzuna_api"] if settings.adzuna_enabled else [],
        available_sources=[{"id": "adzuna_api", "label": SOURCE_LABELS["adzuna_api"]}] if settings.adzuna_enabled else [],
        automated_search=settings.adzuna_enabled, automated_apply=False,
        application_method="Open the listing and apply on the employer/job-board site",
        notes=("Official Adzuna API (aggregates many Indian job boards). Posting dates are verified; descriptions are snippets."
               if settings.adzuna_enabled else "Not configured on this server (ADZUNA_APP_ID / ADZUNA_APP_KEY)."),
    ))
    return out


def save_platforms(db: Session, settings: BackendSettings, user: User, update: PlatformsUpdate) -> None:
    rows = platform_rows(db, user)
    for item in update.platforms:
        allowed = {"adzuna_api"} if item.platform == ADZUNA else set(PLATFORM_SOURCES)
        bad = [s for s in item.discovery_sources if s not in allowed]
        if bad:
            raise HTTPException(422, f"{item.platform} does not support source(s): {', '.join(bad)}")
        if item.platform == ADZUNA and item.enabled and not settings.adzuna_enabled:
            raise HTTPException(422, "Adzuna is not configured on this server.")
        row = rows.get(item.platform) or PlatformPreference(user_id=user.id, platform=item.platform)
        row.enabled = item.enabled
        row.discovery_sources = list(dict.fromkeys(item.discovery_sources)) or (["adzuna_api"] if item.platform == ADZUNA else ["user_job_url"])
        db.add(row)
    db.commit()


def enabled_platform_names(db: Session, user: User) -> set[str]:
    return {name for name, r in platform_rows(db, user).items() if r.enabled}


def get_email_integration(db: Session, user: User) -> EmailIntegration | None:
    return db.execute(select(EmailIntegration).where(EmailIntegration.user_id == user.id)).scalar_one_or_none()


def email_out(row: EmailIntegration | None) -> EmailIntegrationOut:
    if row is None:
        return EmailIntegrationOut(enabled=False, imap_host="imap.gmail.com", imap_port=993, username=None, has_password=False,
                                   folder="INBOX", lookback_days=2, last_checked_at=None, last_error=None)
    return EmailIntegrationOut(enabled=row.enabled, imap_host=row.imap_host, imap_port=row.imap_port, username=row.username,
                               has_password=bool(row.password_encrypted), folder=row.folder, lookback_days=row.lookback_days,
                               last_checked_at=row.last_checked_at, last_error=row.last_error)


def save_email_integration(db: Session, settings: BackendSettings, user: User, data: EmailIntegrationIn) -> EmailIntegration:
    row = get_email_integration(db, user) or EmailIntegration(user_id=user.id)
    row.enabled, row.imap_host, row.imap_port = data.enabled, data.imap_host, data.imap_port
    row.username, row.folder, row.lookback_days = (data.username or "").strip() or None, data.folder, data.lookback_days
    if data.password:
        row.password_encrypted = CredentialCipher(settings).encrypt(data.password)
    if row.enabled and not (row.username and row.password_encrypted):
        raise HTTPException(422, "Username and app password are required to enable email alerts.")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def onboarding_status(db: Session, user: User) -> OnboardingStatus:
    resume = db.execute(select(Resume.id).where(Resume.user_id == user.id, Resume.is_active.is_(True))).first() is not None
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    confirmed = bool(prof and prof.confirmed_profile)
    prefs = get_preferences(db, user) is not None
    platforms = bool(enabled_platform_names(db, user))
    done = resume and confirmed and prefs and platforms
    if done and user.onboarding_completed_at is None:
        user.onboarding_completed_at = utcnow()
        db.commit()
    return OnboardingStatus(resume_uploaded=resume, profile_confirmed=confirmed, preferences_saved=prefs,
                            platforms_selected=platforms, completed=done)
