"""Browser-extension ("Fill with JobPilot") pairing, credentials and the data the extension may read.

Credentials
  * A pairing code is created by the logged-in user in Settings: 8 characters, single use, 5 minutes. It is stored
    hashed in `extension_tokens` with the scope "pair" and can never be used as a bearer credential.
  * Exchanging the code yields an opaque device credential (`jpx_…`, 256 bits), returned once and stored hashed,
    with the scopes below and a 90-day lifetime. It is rotated by the extension (old one stays valid for a short
    grace period so a lost response cannot lock the device out) and can be revoked at any time from Settings or the
    extension itself. Extension credentials are accepted only on /extension/* routes.

What the extension may read is deliberately small: the fields application forms ask for, the verified answers,
and the active resume file. Never summaries, scores, other jobs or anyone else's data.
"""

from __future__ import annotations

import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Application, AuditLog, CandidateProfile, ExtensionToken, Job, JobSourceLink, User, UserJob, utcnow
from backend.schemas.profile import EditableProfile
from backend.security import hash_token
from backend.services import resume_service
from backend.services.ats import base as ats_base

SCOPE_PAIR = "pair"
SCOPE_AUTOFILL = "autofill:read"
SCOPE_TRACK = "applications:track"
DEVICE_SCOPES = [SCOPE_AUTOFILL, SCOPE_TRACK]
TOKEN_PREFIX = "jpx_"
PAIRING_TTL = timedelta(minutes=5)
TOKEN_TTL = timedelta(days=90)
ROTATION_GRACE = timedelta(minutes=2)
MAX_LIVE_CODES = 3
MAX_DEVICES = 10
LAST_USED_RESOLUTION = timedelta(minutes=5)
# Crockford base32 without I, L, O, U: unambiguous when read aloud or typed.
_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_FIXUPS = str.maketrans({"O": "0", "I": "1", "L": "1"})


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def audit(db: Session, user: User, action: str, ip: str | None, token: ExtensionToken | None = None, **details: Any) -> None:
    db.add(AuditLog(actor_id=user.id, action=action, target_type="extension_token" if token else None,
                    target_id=str(token.id) if token and token.id else None, ip=ip, details=details))


# ---- pairing --------------------------------------------------------------------------------

def normalize_code(code: str) -> str:
    return re.sub(r"[\s-]", "", (code or "").upper()).translate(_CODE_FIXUPS)


def create_pairing_code(db: Session, user: User, ip: str | None) -> tuple[str, datetime]:
    now = utcnow()
    live = db.execute(select(ExtensionToken).where(ExtensionToken.user_id == user.id, ExtensionToken.revoked_at.is_(None))).scalars().all()
    codes = sorted((t for t in live if SCOPE_PAIR in (t.scopes or []) and _aware(t.expires_at) > now), key=lambda t: t.created_at)
    for old in codes[: max(0, len(codes) - MAX_LIVE_CODES + 1)]:
        old.revoked_at = now  # keep at most MAX_LIVE_CODES outstanding; the oldest goes first
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    row = ExtensionToken(user_id=user.id, name="pairing code", token_hash=hash_token("pair:" + code), scopes=[SCOPE_PAIR],
                         expires_at=now + PAIRING_TTL)
    db.add(row)
    db.flush()
    audit(db, user, "extension.pairing_code_created", ip, row)
    db.commit()
    return f"{code[:4]}-{code[4:]}", row.expires_at


def _new_device_token(db: Session, user: User, name: str, scopes: list[str]) -> tuple[str, ExtensionToken]:
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = ExtensionToken(user_id=user.id, name=name, token_hash=hash_token(raw), scopes=scopes, expires_at=utcnow() + TOKEN_TTL)
    db.add(row)
    db.flush()
    return raw, row


def pair(db: Session, code: str, device_name: str, ip: str | None) -> tuple[str, ExtensionToken, User]:
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "That pairing code is not valid or has expired. Create a new one in JobPilot Settings.")
    norm = normalize_code(code)
    if len(norm) != 8 or any(c not in _CODE_ALPHABET for c in norm):
        raise invalid
    now = utcnow()
    row = db.execute(select(ExtensionToken).where(ExtensionToken.token_hash == hash_token("pair:" + norm))
                     .with_for_update()).scalar_one_or_none()
    if row is None or SCOPE_PAIR not in (row.scopes or []) or row.revoked_at is not None or _aware(row.expires_at) <= now:
        raise invalid
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise invalid
    row.revoked_at = now  # single use
    active = [t for t in db.execute(select(ExtensionToken).where(ExtensionToken.user_id == user.id, ExtensionToken.revoked_at.is_(None)))
              .scalars() if SCOPE_PAIR not in (t.scopes or []) and _aware(t.expires_at) > now]
    if len(active) >= MAX_DEVICES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You already have {MAX_DEVICES} connected browsers. Disconnect one in Settings first.")
    raw, device = _new_device_token(db, user, device_name, list(DEVICE_SCOPES))
    audit(db, user, "extension.paired", ip, device, device=device_name)
    db.commit()
    return raw, device, user


# ---- authentication -------------------------------------------------------------------------

def authenticate(db: Session, raw: str, scope: str) -> tuple[User, ExtensionToken]:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "This browser is not connected to JobPilot (or was disconnected).",
                                 headers={"WWW-Authenticate": "Bearer"})
    if not raw or not raw.startswith(TOKEN_PREFIX) or len(raw) > 100:
        raise unauthorized
    row = db.execute(select(ExtensionToken).where(ExtensionToken.token_hash == hash_token(raw))).scalar_one_or_none()
    now = utcnow()
    if row is None or row.revoked_at is not None or _aware(row.expires_at) is None or _aware(row.expires_at) <= now:
        raise unauthorized
    scopes = row.scopes or []
    if SCOPE_PAIR in scopes:
        raise unauthorized
    if scope not in scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This extension connection is not allowed to do that.")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise unauthorized
    if row.last_used_at is None or now - _aware(row.last_used_at) > LAST_USED_RESOLUTION:
        row.last_used_at = now
        db.commit()
    return user, row


def rotate(db: Session, user: User, current: ExtensionToken, ip: str | None) -> tuple[str, ExtensionToken]:
    if current.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    raw, row = _new_device_token(db, user, current.name, list(current.scopes or DEVICE_SCOPES))
    current.expires_at = min(_aware(current.expires_at), utcnow() + ROTATION_GRACE)
    audit(db, user, "extension.rotated", ip, row, previous=current.id)
    db.commit()
    return raw, row


def devices(db: Session, user: User) -> list[ExtensionToken]:
    now = utcnow()
    rows = db.execute(select(ExtensionToken).where(ExtensionToken.user_id == user.id, ExtensionToken.revoked_at.is_(None))
                      .order_by(ExtensionToken.created_at.desc())).scalars().all()
    return [t for t in rows if SCOPE_PAIR not in (t.scopes or []) and _aware(t.expires_at) > now]


def revoke(db: Session, user: User, token_id: int, ip: str | None, *, reason: str = "settings") -> None:
    row = db.execute(select(ExtensionToken).where(ExtensionToken.id == token_id, ExtensionToken.user_id == user.id)).scalar_one_or_none()
    if row is None or SCOPE_PAIR in (row.scopes or []):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connection not found")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        audit(db, user, "extension.revoked", ip, row, reason=reason)
    db.commit()


def revoke_all(db: Session, user: User, ip: str | None, *, reason: str) -> int:
    rows = db.execute(select(ExtensionToken).where(ExtensionToken.user_id == user.id, ExtensionToken.revoked_at.is_(None))).scalars().all()
    for r in rows:
        r.revoked_at = utcnow()
    if rows:
        audit(db, user, "extension.revoked_all", ip, None, reason=reason, count=len(rows))
    db.commit()
    return len(rows)


# ---- what the extension may read ------------------------------------------------------------

def _split_name(full: str | None) -> tuple[str | None, str | None]:
    parts = (full or "").split()
    if not parts:
        return None, None
    return (parts[0], " ".join(parts[1:]) or None)


FACT_LABELS = {
    "current_ctc": "Current salary (CTC)", "expected_ctc": "Expected salary", "notice_period": "Notice period",
    "work_authorization": "Work authorisation", "willing_to_relocate": "Willing to relocate",
    "earliest_start_date": "Earliest start date", "requires_sponsorship": "Visa sponsorship needed",
}


def autofill_profile(db: Session, user: User) -> dict[str, Any]:
    """The minimal field set for application forms, plus what is missing (and where to fix it)."""
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    missing: list[dict[str, str]] = []
    if prof is None or not prof.confirmed_profile:
        return {"ready": False, "fields": {}, "facts": {}, "missing": [{"key": "profile", "label": "Confirmed profile",
                                                                        "where": "settings/profile"}], "has_resume": False}
    ep = EditableProfile.model_validate(prof.confirmed_profile)
    first, last = _split_name(ep.full_name)
    current = next((r for r in ep.experience if r.is_current), None)
    edu = ep.education[0] if ep.education else None
    exp = resume_service.experience_summary(ep)
    fields: dict[str, Any] = {
        "full_name": ep.full_name, "first_name": first, "last_name": last, "email": ep.email, "phone": ep.phone,
        "location": ep.location, "current_company": current.company if current else None,
        "current_title": current.title if current else None,
        "linkedin_url": ep.linkedin_url, "github_url": ep.github_url, "portfolio_url": ep.portfolio_url, "website_url": ep.website_url,
        "school": (edu.institution or edu.university) if edu else None, "degree": edu.degree if edu else None,
        "graduation_year": edu.year if edu else None,
        "total_experience_years": exp.years if exp.months else None,
    }
    labels = {"full_name": "Full name", "email": "Email", "phone": "Phone", "location": "Location",
              "current_company": "Current company (mark a role as current)", "current_title": "Current designation",
              "linkedin_url": "LinkedIn URL"}
    missing += [{"key": k, "label": v, "where": "settings/profile"} for k, v in labels.items() if not fields.get(k)]
    facts = {k: v for k, v in (prof.verified_facts or {}).items() if k in FACT_LABELS and v not in (None, "")}
    missing += [{"key": k, "label": v, "where": "settings/answers"} for k, v in FACT_LABELS.items() if k not in facts]
    resume = resume_service.active_resume(db, user)
    if resume is None:
        missing.append({"key": "resume", "label": "Resume", "where": "settings/profile"})
    return {"ready": True, "fields": {k: v for k, v in fields.items() if v not in (None, "")}, "facts": facts, "missing": missing,
            "has_resume": resume is not None, "resume_filename": resume.original_filename if resume else None}


# ---- which of my jobs is this page? ---------------------------------------------------------

_GH_HOST = re.compile(r"^(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io$")
_UUIDISH = re.compile(r"^[0-9a-fA-F-]{8,64}$")


def job_ref(url: str) -> tuple[str, str, str] | None:
    """(ats, board, job id) for a hosted Greenhouse, Lever or Ashby job/application page, else None."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme != "https":
        return None
    host = (parts.hostname or "").lower()
    seg = [s for s in parts.path.split("/") if s]
    q = parse_qs(parts.query)
    try:
        if _GH_HOST.match(host):
            if seg[:2] == ["embed", "job_app"]:
                board, jid = q.get("for", [""])[0], q.get("token", [""])[0]
            elif len(seg) >= 3 and seg[1] == "jobs":
                board, jid = seg[0], seg[2]
            else:
                return None
            return ("greenhouse", ats_base.valid_token(board).lower(), jid) if jid.isdigit() else None
        if host in ("jobs.lever.co", "jobs.eu.lever.co") and len(seg) >= 2 and _UUIDISH.match(seg[1]):
            return "lever", ats_base.valid_token(seg[0]).lower(), seg[1].lower()
        if host == "jobs.ashbyhq.com" and len(seg) >= 2 and _UUIDISH.match(seg[1]):
            return "ashby", ats_base.valid_token(seg[0]).lower(), seg[1].lower()
    except ats_base.AtsError:
        return None
    return None


def match(db: Session, user: User, url: str) -> dict[str, Any]:
    ref = job_ref(url)
    if ref is None:
        return {"supported": False, "platform": None, "in_jobpilot": False}
    ats, board, jid = ref
    platform = {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby"}[ats]
    link = db.execute(select(JobSourceLink).where(JobSourceLink.source_key == f"{ats}:{board}:{jid}")).scalar_one_or_none()
    uj = None
    if link is not None:
        uj = db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == link.job_id)).unique().scalar_one_or_none()
    if uj is None:
        return {"supported": True, "platform": platform, "in_jobpilot": False}
    job: Job = uj.job
    app = db.execute(select(Application).where(Application.user_id == user.id, Application.job_id == job.id)).unique().scalar_one_or_none()
    return {"supported": True, "platform": platform, "in_jobpilot": True, "user_job_id": uj.id, "title": job.title, "company": job.company,
            "application_id": app.id if app else None, "application_status": app.status if app else None,
            "submitted_at": app.submitted_at if app else None}


# ---- Greenhouse-hosted application page -----------------------------------------------------

def greenhouse_hosted_form(job: Job, links: list[JobSourceLink]) -> str | None:
    """The Greenhouse-hosted application form for a Greenhouse job whose listing lives on the employer's own site.

    Never guessed: the form URL is Greenhouse's documented embed address for the board and job id we already hold,
    and it is offered only if Greenhouse serves the application form for exactly that job (HTTP 200 without a
    redirect, containing the job id and the standard first-name field). Anything else returns None.
    """
    if job.job_url and job_ref(job.job_url):
        return None  # the listing is already a Greenhouse-hosted page
    gh = next((l for l in links if l.source == "greenhouse" and l.source_key.count(":") == 2), None)
    if gh is None:
        return None
    _, board, jid = gh.source_key.split(":")
    if not jid.isdigit():
        return None
    url = f"https://job-boards.greenhouse.io/embed/job_app?for={board}&token={jid}"
    hit = _hosted_cache.get(url)
    if hit is not None and time.monotonic() - hit[0] < HOSTED_CACHE_SECONDS:
        return hit[1]
    try:
        code, text = ats_base.get_page(url)
    except ats_base.AtsError:
        return None  # transient: not cached, try again next time
    ok = url if code == 200 and jid in text and 'id="first_name"' in text.replace("'", '"') else None
    _hosted_cache[url] = (time.monotonic(), ok)
    return ok


HOSTED_CACHE_SECONDS = 6 * 3600
_hosted_cache: dict[str, tuple[float, str | None]] = {}
