"""Resume upload, validation, parsing (existing parser) and the confirmed candidate profile."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import CandidateProfile, Resume, User, utcnow
from backend.schemas.profile import EditableProfile, ExperienceSummary
from core import timeutil
from core.skills import SkillTaxonomy
from resume.profile_builder import ResumeProfileExtractor, merge_intervals, months_between, total_experience_months
from resume.resume_parser import ResumeParseError

log = logging.getLogger(__name__)
MAX_PAGES = 15


def taxonomy(settings: BackendSettings) -> SkillTaxonomy:
    from core.settings import PROJECT_ROOT

    return SkillTaxonomy.from_file(PROJECT_ROOT / "config" / "skills_taxonomy.yaml")


def safe_display_name(name: str | None) -> str:
    base = os.path.basename((name or "resume.pdf").replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._ ()\-]+", "_", base).strip(" ._") or "resume"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base[:120]


def get_or_create_profile(db: Session, user: User) -> CandidateProfile:
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    if prof is None:
        prof = CandidateProfile(user_id=user.id, verified_facts={})
        db.add(prof)
        db.flush()
    return prof


async def store_upload(db: Session, settings: BackendSettings, user: User, upload: UploadFile) -> Resume:
    limit = settings.max_upload_mb * 1024 * 1024
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Resume must be {settings.max_upload_mb} MB or smaller.")
    if len(data) < 200 or not data.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF resumes are accepted (the file is not a valid PDF).")
    if upload.content_type not in (None, "", "application/pdf", "application/x-pdf", "application/octet-stream"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF resumes are accepted.")

    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise HTTPException(422, "The PDF is damaged or cannot be opened.") from None
    try:
        if doc.needs_pass:
            raise HTTPException(422, "The PDF is password-protected. Upload an unprotected copy.")
        pages = doc.page_count
    finally:
        doc.close()
    if pages < 1 or pages > MAX_PAGES:
        raise HTTPException(422, f"The resume must have between 1 and {MAX_PAGES} pages.")

    folder = settings.user_dir(user.id, "resumes")
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{uuid.uuid4().hex}.pdf"  # server-chosen name: no client path ever reaches the filesystem
    tmp = target.with_suffix(".part")
    tmp.write_bytes(data)
    os.replace(tmp, target)

    db.execute(update(Resume).where(Resume.user_id == user.id).values(is_active=False))
    resume = Resume(user_id=user.id, original_filename=safe_display_name(upload.filename), stored_path=str(target),
                    sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data), page_count=pages, is_active=True)
    db.add(resume)
    db.flush()
    prof = get_or_create_profile(db, user)
    prof.active_resume_id = resume.id
    prof.resume_path = str(target)
    db.commit()
    db.refresh(resume)
    return resume


def active_resume(db: Session, user: User) -> Resume | None:
    return db.execute(select(Resume).where(Resume.user_id == user.id, Resume.is_active.is_(True)).order_by(Resume.id.desc())).scalars().first()


def parse_active_resume(db: Session, settings: BackendSettings, user: User) -> CandidateProfile:
    resume = active_resume(db, user)
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload a resume first.")
    path = Path(resume.stored_path)
    if not path.is_file() or settings.users_dir.resolve() not in path.resolve().parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stored resume file is missing; upload it again.")
    try:
        parsed = ResumeProfileExtractor(taxonomy(settings)).build(path, today=timeutil.today())
    except ResumeParseError as exc:
        raise HTTPException(422, str(exc)) from None
    parsed["resume"]["path"] = f"resume:{resume.id}"  # never expose server paths to clients
    prof = get_or_create_profile(db, user)
    prof.parsed_profile = parsed
    prof.experience_months = parsed["total_experience"]["months"]
    db.commit()
    db.refresh(prof)
    return prof


def editable_from_parsed(parsed: dict[str, Any]) -> EditableProfile:
    contact = parsed.get("contact") or {}
    return EditableProfile(
        full_name=parsed.get("name"),
        email=contact.get("email"),
        phone=contact.get("phone"),
        location=contact.get("location"),
        headline=parsed.get("headline"),
        summary=parsed.get("summary") or None,
        skills=[s["name"] for s in parsed.get("skills", [])],
        experience=[
            {"title": r.get("title", ""), "company": r.get("company", ""), "start": r.get("start"), "end": r.get("end"),
             "is_current": bool(r.get("is_current")), "bullets": r.get("bullets", [])}
            for r in parsed.get("experience", [])
        ],
        education=[{k: e.get(k) for k in ("degree", "institution", "university", "year")} for e in parsed.get("education", [])],
        certifications=parsed.get("certifications", []),
        projects=[{"name": p["name"], "bullets": p.get("bullets", [])} for p in parsed.get("projects", [])],
        achievements=[a["text"] for a in parsed.get("achievements", [])],
        languages=parsed.get("languages", []),
    )


def experience_summary(profile: EditableProfile, today: date | None = None) -> ExperienceSummary:
    today = today or timeutil.today()
    intervals = []
    for r in profile.experience:
        if not r.start:
            continue
        start = date.fromisoformat(r.start + "-01")
        end = date(today.year, today.month, 1) if (r.is_current or not r.end) else date.fromisoformat(r.end + "-01")
        if end >= start:
            intervals.append((start, end))
    months = total_experience_months(intervals) if intervals else 0
    note = None if intervals or not profile.experience else "Add start dates to your roles so experience can be calculated."
    return ExperienceSummary(
        months=months, years=round(months / 12, 1), years_months=f"{months // 12} years {months % 12} months",
        merged_periods=[[s.strftime("%Y-%m"), e.strftime("%Y-%m")] for s, e in merge_intervals(intervals)],
        method="union of employment date ranges (overlaps counted once, months inclusive)", note=note,
    )


def confirm_profile(db: Session, user: User, profile: EditableProfile) -> CandidateProfile:
    prof = get_or_create_profile(db, user)
    if prof.parsed_profile is None and prof.active_resume_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload and parse a resume before confirming the profile.")
    summary = experience_summary(profile)
    prof.confirmed_profile = profile.model_dump(mode="json")
    prof.experience_months = summary.months
    prof.confirmed_at = utcnow()
    db.commit()
    db.refresh(prof)
    return prof


def matcher_profile(prof: CandidateProfile, tax: SkillTaxonomy, today: date | None = None) -> dict[str, Any]:
    """Shape the confirmed profile like the CLI profile so the existing matcher can use it unchanged."""
    if not prof.confirmed_profile:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirm your profile before matching jobs.")
    today = today or timeutil.today()
    ep = EditableProfile.model_validate(prof.confirmed_profile)
    resume_text = (prof.parsed_profile or {}).get("resume_text", "")
    confirmed_text = "\n".join(
        [ep.summary or "", ep.headline or "", *ep.skills, *ep.certifications, *ep.achievements]
        + [b for r in ep.experience for b in r.bullets] + [f"{r.title} {r.company}" for r in ep.experience]
        + [b for p in ep.projects for b in p.bullets] + [e.degree or "" for e in ep.education]
    )
    full_text = resume_text + "\n" + confirmed_text
    skills: dict[str, dict[str, str]] = {}
    for s in ep.skills:
        name = tax.canonical(s) or s
        skills.setdefault(name, {"name": name, "source": "confirmed_profile"})
    for hit in tax.find(confirmed_text):
        skills.setdefault(hit.skill, {"name": hit.skill, "source": "confirmed_profile_text"})
    roles = []
    for r in ep.experience:
        start = date.fromisoformat(r.start + "-01") if r.start else None
        end = date(today.year, today.month, 1) if (r.is_current or not r.end) else date.fromisoformat(r.end + "-01")
        roles.append({"title": r.title, "company": r.company, "start": r.start, "end": None if r.is_current else r.end,
                      "is_current": r.is_current, "bullets": r.bullets, "months": months_between(start, end) if start else 0})
    summary = experience_summary(ep, today)
    achievements = [{"text": a, "metrics": re.findall(r"\d+(?:\.\d+)?%?", a), "context": ""} for a in ep.achievements]
    return {
        "name": ep.full_name, "configured_name": ep.full_name,
        "contact": {"email": ep.email, "phone": ep.phone, "location": ep.location},
        "headline": ep.headline, "summary": ep.summary or "",
        "skills": list(skills.values()), "experience": roles,
        "previous_companies": list(dict.fromkeys(r.company for r in ep.experience if r.company)),
        "total_experience": {"months": summary.months, "years": summary.years, "years_months": summary.years_months,
                             "as_of": today.isoformat(), "discrepancy_note": None},
        "education": [e.model_dump() for e in ep.education], "certifications": ep.certifications,
        "projects": [p.model_dump() for p in ep.projects], "achievements": achievements,
        "languages": ep.languages, "resume_text": full_text,
        "resume": {"path": prof.resume_path or "", "sha256": ""},
    }
