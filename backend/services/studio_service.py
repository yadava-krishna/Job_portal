"""Resume Studio: structured, versioned resumes built from the candidate's confirmed profile.

* A version is a document (sections -> blocks -> bullets) plus a template and layout settings. Saving replaces the
  document atomically and bumps `revision`; a stale revision is rejected (409) so two tabs can't overwrite each other.
* Locked versions (used in a submitted application) are immutable. Editing one means cloning it first.
* Exports are cached per content checksum: downloading twice never re-renders, and the application records the
  exact file hash.
* Suggestions are suggest-only and come from the candidate's own facts. Nothing is applied without the user.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import Counter
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core import textclean
from backend.config import BackendSettings
from backend.models import (CandidateProfile, ResumeBlock, ResumeBullet, ResumeExport, ResumeFeedback, ResumeSection,
                            ResumeTemplate, ResumeVersion, User, UserJob, utcnow)
from backend.services import platform_service
from backend.services.storage import get_storage
from backend.services.studio_render import TEMPLATES, layout_report, normalize_settings, render_docx, render_pdf

MAX_VERSIONS = 30
SECTION_TYPES = ("header", "summary", "experience", "projects", "education", "skills", "certifications", "publications",
                 "achievements", "custom")
BLOCK_TYPES = ("contact", "text", "entry", "skill_group")
log = __import__("logging").getLogger(__name__)
WEAK_STARTS = {"responsible for": "", "worked on": "Worked on", "helped": "Helped", "duties included": "",
               "assisted in": "Assisted with", "involved in": "Contributed to", "tasked with": ""}
_ING = re.compile(r"^(responsible for|tasked with|duties included)\s+(\w+ing)\b\s*(.*)$", re.I)
STOP = set("the and for with from into that this were was are our your their have has had over under using use a an of to in on by at as or".split())


# ---------------- templates ----------------

def ensure_templates(db: Session) -> list[ResumeTemplate]:
    have = {t.key: t for t in db.execute(select(ResumeTemplate)).scalars()}
    for key, cfg in TEMPLATES.items():
        config = {k: v for k, v in cfg.items() if k != "name"}
        if key not in have:
            t = ResumeTemplate(key=key, name=cfg["name"], category=cfg["category"], ats_safe=cfg["ats_safe"],
                               supports_docx=True, active=True, config_json=config)
            db.add(t)
            have[key] = t
        else:  # keep the catalogue row in step with the code (names and layout were redesigned); keys never change
            t = have[key]
            if (t.name, t.category, t.ats_safe, t.config_json) != (cfg["name"], cfg["category"], cfg["ats_safe"], config):
                t.name, t.category, t.ats_safe, t.config_json = cfg["name"], cfg["category"], cfg["ats_safe"], config
    db.commit()
    return [have[k] for k in TEMPLATES]


def template_by_key(db: Session, key: str) -> ResumeTemplate:
    ensure_templates(db)
    t = db.execute(select(ResumeTemplate).where(ResumeTemplate.key == key, ResumeTemplate.active.is_(True))).scalar_one_or_none()
    if t is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown template")
    return t


# ---------------- documents ----------------

def _doc_from_profile(conf: dict[str, Any]) -> list[dict[str, Any]]:
    def entry(title, org, start=None, end=None, current=False, bullets=(), ref=None, **extra):
        return {"type": "entry", "source_profile_ref": ref, "visible": True,
                "content": {"title": title, "organization": org, "start": start, "end": end, "current": current, **extra},
                "bullets": [{"text": b, "evidence_refs": [ref] if ref else [], "source": "profile", "approved": True} for b in bullets]}

    links = [v for v in (conf.get("linkedin_url"), conf.get("github_url"), conf.get("portfolio_url")) if v]
    # Achievements the resume parser lifted out of role or project bullets would print the same line twice: keep only
    # achievements that are not already a bullet elsewhere.
    norm = lambda t: " ".join(str(t or "").lower().split())  # noqa: E731
    elsewhere = {norm(b) for e in (conf.get("experience") or []) + (conf.get("projects") or []) for b in (e.get("bullets") or [])}
    achievements = [a for a in conf.get("achievements") or [] if norm(a) and norm(a) not in elsewhere]
    sections = [
        {"type": "header", "heading": "Contact", "visible": True, "blocks": [
            {"type": "contact", "source_profile_ref": "profile:contact", "visible": True, "bullets": [],
             "content": {"name": conf.get("full_name"), "headline": conf.get("headline"), "email": conf.get("email"),
                         "phone": conf.get("phone"), "location": conf.get("location"), "links": links}}]},
        {"type": "summary", "heading": "Summary", "visible": bool(conf.get("summary")), "blocks": [
            {"type": "text", "source_profile_ref": "profile:summary", "visible": True, "bullets": [], "content": {"text": conf.get("summary") or ""}}]},
        {"type": "experience", "heading": "Experience", "visible": True, "blocks": [
            entry(e.get("title"), e.get("company"), e.get("start"), e.get("end"), bool(e.get("is_current")), e.get("bullets") or [], f"experience:{i}",
                  **({"location": e["location"]} if e.get("location") else {}))
            for i, e in enumerate(conf.get("experience") or [])]},
        {"type": "projects", "heading": "Projects", "visible": bool(conf.get("projects")), "blocks": [
            entry(p.get("name"), None, bullets=p.get("bullets") or [], ref=f"project:{i}") for i, p in enumerate(conf.get("projects") or [])]},
        {"type": "education", "heading": "Education", "visible": True, "blocks": [
            entry(e.get("degree"), e.get("institution") or e.get("university"), None, e.get("year"), ref=f"education:{i}")
            for i, e in enumerate(conf.get("education") or [])]},
        {"type": "skills", "heading": "Skills", "visible": True, "blocks": [
            {"type": "skill_group", "source_profile_ref": "profile:skills", "visible": True, "bullets": [],
             "content": {"label": None, "items": list(conf.get("skills") or [])}}]
            + ([{"type": "skill_group", "source_profile_ref": "profile:languages", "visible": True, "bullets": [],
                 "content": {"label": "Languages", "items": list(conf.get("languages") or [])}}] if conf.get("languages") else [])},
        {"type": "certifications", "heading": "Certifications", "visible": bool(conf.get("certifications")), "blocks": [
            entry(c, None, ref=f"certification:{i}") for i, c in enumerate(conf.get("certifications") or [])]},
        {"type": "achievements", "heading": "Achievements", "visible": bool(achievements), "blocks": [
            {"type": "entry", "source_profile_ref": "profile:achievements", "visible": True, "content": {"title": None},
             "bullets": [{"text": a, "evidence_refs": ["profile:achievements"], "source": "profile", "approved": True}
                         for a in achievements]}] if achievements else []},
    ]
    return sections


def _write_sections(version: ResumeVersion, sections: list[dict[str, Any]]) -> None:
    version.sections.clear()
    for si, s in enumerate(sections):
        if s.get("type") not in SECTION_TYPES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown section type {s.get('type')}")
        sec = ResumeSection(type=s["type"], heading=(s.get("heading") or s["type"].title())[:80], position=si,
                            visible=bool(s.get("visible", True)))
        for bi, b in enumerate(s.get("blocks") or []):
            if b.get("type") not in BLOCK_TYPES:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown block type {b.get('type')}")
            content = {k: (textclean.clean(v) if isinstance(v, str) else [textclean.clean(x) if isinstance(x, str) else x for x in v] if isinstance(v, list) else v)
                       for k, v in (b.get("content") or {}).items() if isinstance(v, (str, int, float, bool, list, type(None)))}
            blk = ResumeBlock(type=b["type"], source_profile_ref=(b.get("source_profile_ref") or None), content_json=content,
                              position=bi, visible=bool(b.get("visible", True)))
            for ui, u in enumerate(b.get("bullets") or []):
                text = textclean.clean(u.get("text") or "", bullet=True).strip()[:1200]
                blk.bullets.append(ResumeBullet(text=text, position=ui, evidence_refs=[str(r)[:80] for r in u.get("evidence_refs") or []][:10],
                                                source=u.get("source") if u.get("source") in ("profile", "user", "suggestion") else "user",
                                                approved=bool(u.get("approved", True))))
            sec.blocks.append(blk)
        version.sections.append(sec)


def document(version: ResumeVersion) -> dict[str, Any]:
    return {"sections": [{"id": s.id, "type": s.type, "heading": s.heading, "visible": s.visible,
                          "blocks": [{"id": b.id, "type": b.type, "source_profile_ref": b.source_profile_ref, "visible": b.visible,
                                      "content": b.content_json or {},
                                      "bullets": [{"id": u.id, "text": u.text, "evidence_refs": u.evidence_refs or [], "source": u.source,
                                                   "approved": u.approved} for u in b.bullets]} for b in s.blocks]}
                         for s in version.sections]}


def checksum(version: ResumeVersion) -> str:
    doc = document(version)
    for s in doc["sections"]:
        s.pop("id", None)
        for b in s["blocks"]:
            b.pop("id", None)
            for u in b["bullets"]:
                u.pop("id", None)
    from backend.services.resume_check import RENDERER_VERSION

    # The renderer version is part of the key: after a renderer change, cached exports are re-rendered instead of the
    # preview showing an old PDF whose page count disagrees with a fresh check.
    payload = json.dumps({"t": version.template.key, "s": version.settings or {}, "d": doc, "r": RENDERER_VERSION}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def version_out(version: ResumeVersion) -> dict[str, Any]:
    return {"id": version.id, "name": version.name, "template_key": version.template.key, "template_name": version.template.name,
            "ats_safe": version.template.ats_safe, "status": version.status, "locked_at": version.locked_at,
            "revision": version.revision, "settings": version.settings or {}, "target_job_id": version.target_job_id,
            "parent_id": version.parent_id, "created_at": version.created_at, "updated_at": version.updated_at,
            "checksum": version.content_checksum, **document(version)}


def owned_version(db: Session, user: User, version_id: int) -> ResumeVersion:
    v = db.execute(select(ResumeVersion).where(ResumeVersion.id == version_id, ResumeVersion.user_id == user.id)).unique().scalar_one_or_none()
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume version not found")
    return v


def list_versions(db: Session, user: User) -> list[ResumeVersion]:
    return list(db.execute(select(ResumeVersion).where(ResumeVersion.user_id == user.id).order_by(ResumeVersion.updated_at.desc())).unique().scalars())


def _target_job(db: Session, user: User, user_job_id: int | None) -> int | None:
    if not user_job_id:
        return None
    uj = db.execute(select(UserJob).where(UserJob.id == user_job_id, UserJob.user_id == user.id)).scalar_one_or_none()
    if uj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return uj.job_id


def create_from_profile(db: Session, user: User, name: str, template_key: str, target_user_job_id: int | None = None) -> ResumeVersion:
    if len(list_versions(db, user)) >= MAX_VERSIONS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You can keep up to {MAX_VERSIONS} resume versions. Archive or delete one first.")
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    conf = (prof.confirmed_profile if prof else None) or {}
    tpl = template_by_key(db, template_key)
    v = ResumeVersion(user_id=user.id, template_id=tpl.id, name=name.strip()[:120] or "My resume", status="draft",
                      settings=normalize_settings(tpl.key, {})[0],
                      target_job_id=_target_job(db, user, target_user_job_id))
    v.template = tpl
    _write_sections(v, _doc_from_profile(conf))
    db.add(v)
    db.flush()
    v.content_checksum = checksum(v)
    platform_service.track(db, user.id, "resume_created", resume_version_id=v.id, template=tpl.key, from_profile=bool(conf))
    db.commit()
    db.refresh(v)
    return v


def save(db: Session, user: User, version: ResumeVersion, data: dict[str, Any]) -> ResumeVersion:
    if version.status == "locked":
        raise HTTPException(status.HTTP_409_CONFLICT, {"message": "This version was used in a submitted application and can't change. "
                                                                  "Make a copy to keep editing.", "locked": True})
    if data.get("revision") is not None and int(data["revision"]) != version.revision:
        raise HTTPException(status.HTTP_409_CONFLICT, {"message": "This resume changed in another window. Reload to get the latest.",
                                                       "revision": version.revision})
    before_bullets = [u.text for s in version.sections for b in s.blocks for u in b.bullets]
    if "name" in data and data["name"]:
        version.name = str(data["name"]).strip()[:120]
    if data.get("template_key") and data["template_key"] != version.template.key:
        tpl = template_by_key(db, data["template_key"])
        platform_service.track(db, user.id, "resume_template_changed", resume_version_id=version.id, from_=version.template.key, to=tpl.key)
        version.template_id, version.template = tpl.id, tpl
    if isinstance(data.get("settings"), dict) or data.get("template_key"):
        # Layout settings are validated against the (possibly new) template's guard rails: readable sizes, fonts the
        # template supports, colours with enough contrast, and no side labels on ATS templates.
        raw = {**(version.settings or {}), **(data.get("settings") or {})}
        if data.get("template_key") and not isinstance(data.get("settings"), dict):
            raw.pop("font_family", None)
            raw.pop("accent", None)
            raw.pop("heading_style", None)
        version.settings, _notes = normalize_settings(version.template.key, raw)
    if isinstance(data.get("sections"), list):
        _write_sections(version, data["sections"])
    db.flush()
    after_bullets = [u.text for s in version.sections for b in s.blocks for u in b.bullets]
    edited = len(set(after_bullets) - set(before_bullets))
    if edited:
        platform_service.track(db, user.id, "resume_bullet_edited", resume_version_id=version.id, bullets_changed=edited)
    version.revision += 1
    version.content_checksum = checksum(version)
    version.updated_at = utcnow()
    db.commit()
    db.refresh(version)
    return version


def clone(db: Session, user: User, version: ResumeVersion, name: str | None, target_user_job_id: int | None) -> ResumeVersion:
    """Copy (also how a locked or older version is restored): the original is never modified."""
    if len(list_versions(db, user)) >= MAX_VERSIONS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"You can keep up to {MAX_VERSIONS} resume versions.")
    v = ResumeVersion(user_id=user.id, template_id=version.template_id, name=(name or f"{version.name} (copy)")[:120], status="draft",
                      settings=dict(version.settings or {}), parent_id=version.id,
                      target_job_id=_target_job(db, user, target_user_job_id) if target_user_job_id else version.target_job_id)
    v.template = version.template
    _write_sections(v, document(version)["sections"])
    db.add(v)
    db.flush()
    v.content_checksum = checksum(v)
    db.commit()
    db.refresh(v)
    return v


def delete(db: Session, user: User, version: ResumeVersion) -> None:
    if version.status == "locked":
        raise HTTPException(status.HTTP_409_CONFLICT, "A version used in a submitted application is kept as a record and can't be deleted.")
    for e in db.execute(select(ResumeExport).where(ResumeExport.resume_version_id == version.id)).scalars():
        get_storage().delete(e.file_key)
    db.delete(version)
    db.commit()


# ---------------- export (cached per checksum) ----------------

_EXPORT_LOCKS: dict[tuple, threading.Lock] = {}
_EXPORT_LOCKS_GUARD = threading.Lock()


def export(db: Session, settings: BackendSettings, user: User, version: ResumeVersion, fmt: str) -> ResumeExport:
    """The export of this exact revision, rendered once per content checksum. Concurrent requests for the same file
    (the preview and the check right after a save) wait for one render instead of racing to store it twice."""
    if fmt not in ("pdf", "docx"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Format must be pdf or docx")
    key = (version.id, fmt, checksum(version))
    with _EXPORT_LOCKS_GUARD:
        lock = _EXPORT_LOCKS.setdefault(key, threading.Lock())
        if len(_EXPORT_LOCKS) > 512:  # forget old keys (never the one in use)
            for k in [k for k in _EXPORT_LOCKS if k != key][:256]:
                _EXPORT_LOCKS.pop(k, None)
    with lock:
        db.expire_all()  # see an export another request stored while this one waited
        return _export(db, settings, user, version, fmt)


def _export(db: Session, settings: BackendSettings, user: User, version: ResumeVersion, fmt: str) -> ResumeExport:
    ck = checksum(version)
    if version.content_checksum != ck:  # renderer upgraded (or never stored): the content's current key
        version.content_checksum = ck
    cached = db.execute(select(ResumeExport).where(ResumeExport.resume_version_id == version.id, ResumeExport.format == fmt,
                                                   ResumeExport.checksum == ck)).scalar_one_or_none()
    store = get_storage()
    if cached is not None and store.exists(cached.file_key):
        return cached
    doc = document(version)
    try:
        if fmt == "pdf":
            data, pages = render_pdf(doc, version.template.key, version.settings or {})
            note = None
        else:
            data, note = render_docx(doc, version.template.key, version.settings or {})
            pages = None
    except Exception as exc:
        platform_service.track(db, user.id, "export_failed", success=False, commit=True, resume_version_id=version.id, format=fmt)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "The resume could not be rendered.") from exc
    sha = hashlib.sha256(data).hexdigest()
    key = f"users/{user.id}/resume_exports/{version.id}/{ck[:16]}.{fmt}"
    store.put(key, data)
    if cached is not None:
        db.delete(cached)
        db.flush()
    row = ResumeExport(user_id=user.id, resume_version_id=version.id, format=fmt, file_key=key, checksum=ck, file_sha256=sha,
                       size_bytes=len(data), page_count=pages)
    db.add(row)
    platform_service.track(db, user.id, "resume_exported", resume_version_id=version.id, format=fmt, pages=pages or 0)
    try:
        db.commit()
    except IntegrityError:  # another worker process stored the same export first: use that one (same content, same key)
        db.rollback()
        row = db.execute(select(ResumeExport).where(ResumeExport.resume_version_id == version.id, ResumeExport.format == fmt,
                                                    ResumeExport.checksum == ck)).scalar_one()
        row.note = note  # type: ignore[attr-defined]
        return row
    db.refresh(row)
    row.note = note  # type: ignore[attr-defined]
    return row


def owned_export(db: Session, user: User, export_id: int) -> ResumeExport:
    e = db.execute(select(ResumeExport).where(ResumeExport.id == export_id, ResumeExport.user_id == user.id)).scalar_one_or_none()
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export not found")
    return e


def download_name(version: ResumeVersion, fmt: str) -> str:
    base = re.sub(r"[^A-Za-z0-9 _-]+", "", version.name).strip().replace(" ", "_") or "resume"
    return f"{base}.{fmt}"


# ---------------- feedback & suggestions ----------------

def _profile_facts(db: Session, user: User) -> tuple[set[str], set[str], str]:
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    conf = (prof.confirmed_profile if prof else None) or {}
    bullets = {b.strip() for e in conf.get("experience") or [] for b in e.get("bullets") or []}
    bullets |= {b.strip() for p in conf.get("projects") or [] for b in p.get("bullets") or []}
    skills = {s.lower() for s in conf.get("skills") or []}
    return bullets, skills, " ".join(bullets)


SCORE_METHOD = ("Resume Quality is JobPilot's own checklist for this exact exported PDF: 100 minus 25 for each must-fix item, 8 for "
                "each worth-fixing item and 3 for each suggestion. Notes don't lower it, and job coverage is measured separately "
                "(Resume–Job Alignment). It is not an ATS score: no universal ATS score exists, and each employer's system reads "
                "resumes differently. It doesn't predict whether you'll be shortlisted.")
JOB_MATCH_METHOD = ("Job Match compares your verified profile (skills, experience, location, preferences) with the job. It is the "
                    "same score as on the job card and doesn't change when you edit a resume.")


def _ym(value: Any) -> tuple[int, int] | None:
    from backend.services.studio_render import format_date

    t = format_date(value, "MM/YYYY")
    m = re.fullmatch(r"(\d{2})/(\d{4})", t or "")
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.fullmatch(r"\d{4}", t or "")
    return (int(t), 0) if m else None


def _user_job(db: Session, user: User, user_job_id: int | None):
    if not user_job_id:
        return None
    uj = db.execute(select(UserJob).where(UserJob.id == user_job_id, UserJob.user_id == user.id)).scalar_one_or_none()
    if uj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return uj


def _content_issues(doc: dict[str, Any], tpl: dict[str, Any], profile_bullets: set[str], profile_text: str) -> list[dict[str, Any]]:
    """Checks on the structured content (contact, dates, duplicates, writing, figures), each tied to its entry/field."""
    from backend.services.resume_check import entry_label, issue

    out: list[dict[str, Any]] = []
    if not tpl["ats_safe"]:
        out.append(issue("layout", "warning", "format", "Section names in the margin and colour suit people better than applicant-tracking systems.",
                         why="Side labels can scramble the reading order when a system extracts the text.",
                         fix="Use Classic ATS (or another ATS-safe template) for online forms.", key="template"))
    header = next((s for s in doc["sections"] if s["type"] == "header"), None)
    hc = (header["blocks"][0]["content"] if header and header["blocks"] else {}) or {}
    if not hc.get("name"):
        out.append(issue("contact_name", "error", "format", "Add your name to the header.", section="header", block=0, field="name", entry="Contact",
                         why="Without a name the resume can't be matched to you.", fix="Type your name in Contact.", key="name"))
    if not hc.get("email") and not hc.get("phone"):
        out.append(issue("contact", "error", "format", "Add an e-mail or phone number so employers can reach you.", section="header", block=0, field="email",
                         entry="Contact", why="Nobody can contact you otherwise.", fix="Add your e-mail in Contact.", key="contact"))
    elif not hc.get("email"):
        out.append(issue("contact_email", "warning", "format", "Add an e-mail address.", section="header", block=0, field="email", entry="Contact",
                         why="Most application systems require one.", fix="Add your e-mail in Contact.", key="email"))
    elif not hc.get("phone"):
        out.append(issue("contact_phone", "info", "format", "No phone number.", section="header", block=0, field="phone", entry="Contact",
                         why="Recruiters in India usually call first.", fix="Add a phone number if you're happy to share it.", key="phone"))
    for s in doc["sections"]:
        if not s["visible"] or s["type"] == "header":
            continue
        if not any(b["visible"] for b in s["blocks"]):
            out.append(issue("empty_section", "info", "format", f"'{s['heading']}' is empty.", section=s["type"], entry=s["heading"],
                             why="An empty heading looks unfinished.", fix="Hide the section or add content.", key=s["type"]))
        seen: dict[tuple, int] = {}
        for bi, b in enumerate(s["blocks"]):
            c = b.get("content") or {}
            if not b["visible"] or b["type"] != "entry":
                continue
            label = entry_label(c)
            k = (str(c.get("title") or "").strip().lower(), str(c.get("organization") or "").strip().lower(), str(c.get("start") or ""))
            ekey = f"{s['type']}|{k}"
            if any(k[:2]) and k in seen:
                out.append(issue("duplicate_entry", "warning", "format", f"{label} appears twice in {s['heading']} (items {seen[k] + 1} and {bi + 1}).",
                                 section=s["type"], block=bi, entry=label, why="Repeated entries look like a copy-paste slip.",
                                 evidence="Same title, employer and start date.", fix="Delete one of them.", key=ekey))
            seen.setdefault(k, bi)
            if s["type"] == "experience":
                start, end = _ym(c.get("start")), _ym(c.get("end"))
                if c.get("title") and not c.get("start"):
                    out.append(issue("date_missing", "warning", "format", f"{label} has no start date.", section=s["type"], block=bi, field="dates",
                                     entry=label, why="Dates let employers (and JobPilot) work out your experience.",
                                     fix="Add the month and year you started.", key=ekey))
                if start and end and not c.get("current") and end < start:
                    out.append(issue("date_order", "error", "format", f"{label} ends before it starts.", section=s["type"], block=bi, field="dates",
                                     entry=label, evidence=f"{c.get('start')} – {c.get('end')}", why="Reversed dates look like a typo.",
                                     fix="Swap the start and end dates.", key=ekey))
                if c.get("current") and c.get("end"):
                    out.append(issue("date_current", "info", "format", f"{label} is marked current but also has an end date.", section=s["type"],
                                     block=bi, field="dates", entry=label, why="The end date is not shown.", fix="Clear the end date or untick Current.", key=ekey))
    words: Counter = Counter()
    seen_bullets: dict[str, tuple] = {}
    for s in doc["sections"]:
        if not s["visible"]:
            continue
        for bi, b in enumerate(s["blocks"]):
            if not b["visible"]:
                continue
            label = entry_label(b.get("content") or {}) if b["type"] == "entry" else s["heading"]
            for ui, u in enumerate(b["bullets"]):
                if not u["approved"]:
                    continue
                text = u["text"]
                norm = " ".join(text.lower().split())
                bkey = f"{s['type']}|{label}|{norm[:80]}"
                loc = dict(section=s["type"], block=bi, bullet=ui, field="bullet", entry=label)
                if norm and norm in seen_bullets:
                    first = seen_bullets[norm]
                    out.append(issue("duplicate_bullet", "warning", "format", f"{label}: bullet {ui + 1} repeats a bullet in {first[0]}.", **loc,
                                     why="The same line twice reads as padding.", evidence=f"“{text[:80]}”", fix="Delete the repeat.", key=bkey))
                seen_bullets.setdefault(norm, (label, ui))
                low = text.lower()
                for weak in WEAK_STARTS:
                    if low.startswith(weak):
                        out.append(issue("weak_bullet", "suggestion", "writing", f"{label}: bullet {ui + 1} starts with '{weak}'.", **loc,
                                         why="Leading with what you did reads stronger.", evidence=f"“{text[:80]}”",
                                         fix="See Suggestions for a reworded version with the same facts.", key=bkey))
                        break
                n = len(text.split())
                if n > 40:
                    out.append(issue("long_bullet", "warning", "writing", f"{label}: bullet {ui + 1} has {n} words.", **loc,
                                     why="Long bullets get skimmed.", fix="Keep bullets under ~30 words; split it or trim it.", key=bkey))
                elif n < 4:
                    out.append(issue("short_bullet", "info", "writing", f"{label}: bullet {ui + 1} is very short.", **loc,
                                     why="A bullet says more with the result it had.", fix="Add what changed because of it, if you can back it up.", key=bkey))
                if u["source"] != "profile" and text.strip() not in profile_bullets:
                    nums = re.findall(r"\d[\d,.]*%?", text)
                    if nums and not all(x in profile_text for x in nums):
                        out.append(issue("unsupported_claim", "warning", "accuracy", f"{label}: {', '.join(nums)} isn't in your confirmed profile.", **loc,
                                         why="Only figures you can back up belong on a resume.", evidence=f"“{text[:80]}”",
                                         fix="Check the figure, or add it to your profile if it's true.", key=bkey))
                for w in re.findall(r"[a-zA-Z][a-zA-Z+#.-]{3,}", low):
                    if w not in STOP:
                        words[w] += 1
    for w, c in words.most_common(3):
        if c >= 7:
            out.append(issue("repeated_keyword", "suggestion", "writing", f"'{w}' appears {c} times.", why="Heavy repetition reads as keyword stuffing.",
                             fix="Vary the wording where it doesn't change the meaning.", key=w))
    return out


def feedback(db: Session, settings: BackendSettings, user: User, version: ResumeVersion, user_job_id: int | None,
             revision: int | None = None) -> dict[str, Any]:
    """The check of one exact revision: its exported PDF (the same file the preview shows and Smart Apply attaches) and
    its content. `revision`: the revision the caller is looking at; a check for an older one is refused (409) so a
    slow answer can never overwrite a newer result."""
    from backend.services import resume_check as rc

    if revision is not None and revision != version.revision:
        raise HTTPException(status.HTTP_409_CONFLICT, {"message": "The resume changed since this check was asked for.", "revision": version.revision})
    doc = document(version)
    tpl = TEMPLATES[version.template.key]
    profile_bullets, profile_skills, profile_text = _profile_facts(db, user)
    issues = _content_issues(doc, tpl, profile_bullets, profile_text)
    pages = export_id = None
    try:
        exp = export(db, settings, user, version, "pdf")  # cached per checksum: the exact file the preview shows
        export_id, pages = exp.id, exp.page_count
        pdf = get_storage().get(exp.file_key)
        info = rc.inspect_pdf(pdf)
        pages = info["pages"]
        chars = rc.character_findings(doc, info)
        issues += chars
        skip = {(i["where"]["section"], i["where"]["block"], i["where"]["bullet"], i["where"]["field"]) for i in chars if i["where"]}
        issues += rc.readback_findings(doc, info, skip)
        issues += rc.association_findings(doc, pdf)
        rep = layout(version)
        if rep["pages"] != pages:  # never expected: both render the same revision with the same renderer
            log.warning("layout pages %s != export pages %s for version %s", rep["pages"], pages, version.id)
        for w in rep["warnings"]:
            if w["level"] == "warning":
                code = "last_page" if "last page" in w["message"] else "overflow"
                issues.append(rc.issue(code, "warning", "format", w["message"], why="Page count and fit, measured on the exported PDF.",
                                       evidence=f"{pages} page{'s' if pages != 1 else ''}; last page {round(rep['page_fill'][-1] * 100)}% full.",
                                       fix="Use the fit suggestion above the preview, or trim older bullets (JobPilot never removes content).", key=code))
    except HTTPException:
        issues.append(rc.issue("render", "error", "format", "The resume could not be rendered.", why="Usually an unusual character.",
                               fix="Look for pasted symbols, then check again.", key="render"))
    except Exception:  # noqa: BLE001
        log.exception("resume check failed for version %s", version.id)
        issues.append(rc.issue("render", "error", "format", "The resume could not be checked.", fix="Try again; if it keeps failing, export it and look for odd characters.", key="render"))
    issues = rc.dedupe(issues)
    uj = _user_job(db, user, user_job_id)
    scores: dict[str, Any] = {"resume_quality": {"score": rc.quality_score(issues), "method": SCORE_METHOD,
                                                 "counts": {lvl: sum(1 for i in issues if i["level"] == lvl and i["kind"] != "job") for lvl in rc.LEVEL_POINTS}}}
    if uj is not None:
        job = uj.job
        scores["job_match"] = {"score": round(uj.match_score) if uj.match_score is not None else None, "category": uj.match_category,
                               "method": JOB_MATCH_METHOD}
        al = rc.alignment(doc, job, profile_skills, profile_text, _canonical_skills())
        scores["alignment"] = al
        for a in al["addable"]:
            issues.append(rc.issue("job_keyword", "suggestion", "job", f"The job asks for {a['skill']}: it's in your verified profile but not on this resume.",
                                   section="skills", why="Alignment counts only what is printed on this resume.",
                                   fix="Add it to Skills (see Suggestions), or mention where you used it in a bullet.", key=a["skill"]))
        for g in al["gaps"]:
            issues.append(rc.issue("job_gap", "info", "job", f"The job asks for {g['skill']}. Your profile has no evidence of it.",
                                   why="JobPilot never adds skills you haven't shown.", fix="Leave it off unless it's true; see Career → Skills for ways to build it.",
                                   key=g["skill"]))
    quality = scores["resume_quality"]["score"]
    fb = ResumeFeedback(user_id=user.id, resume_version_id=version.id, job_id=uj.job.id if uj else None,
                        checksum=version.content_checksum, score=quality, issues_json=issues)
    db.add(fb)
    db.commit()
    return {"resume_version_id": version.id, "revision": version.revision, "checksum": version.content_checksum, "export_id": export_id,
            "job_id": uj.job.id if uj else None, "pages": pages, "issues": issues, "readiness": quality, "scores": scores,
            "score_method": SCORE_METHOD, "ats_safe_template": tpl["ats_safe"],
            "note": "ATS-safe means a conservative, parseable layout. It does not guarantee how any employer's system will read it."}


def _rewrite_weak(text: str) -> str | None:
    m = _ING.match(text.strip())
    if m:
        verb = m.group(2)
        stem = verb[:-3]
        past = (stem + "ed") if not stem.endswith("e") else stem + "d"
        if re.search(r"(at|iz|is|ur|ag|ag)$", stem):
            past = stem + "ed"
        return f"{past[0].upper()}{past[1:]} {m.group(3)}".strip()
    for weak, repl in WEAK_STARTS.items():
        if text.lower().startswith(weak) and repl:
            rest = text[len(weak):].lstrip()
            return f"{repl} {rest}".strip()
    return None


# Recommendation categories (Resume Studio → Suggestions):
#   structure  A. fixes to how the resume is built or printed (unreadable characters, missing dates or contact)
#   writing    B. clearer wording with the same facts and numbers
#   emphasize  C. verified experience and skills to bring forward for the chosen job
#   confirm    D. information that is missing and only the user can supply or confirm
#   gap        E. requirements the user can't evidence yet: shown for honesty, never added
CATEGORY_LABEL = {"structure": "Structural fix", "writing": "Writing and clarity", "emphasize": "Verified experience to emphasise",
                  "confirm": "Needs your confirmation", "gap": "Can't evidence yet"}


def _where_label(doc: dict[str, Any], si: int, bi: int | None = None, ui: int | None = None, field: str | None = None) -> str:
    from backend.services.resume_check import FIELD_LABEL, entry_label

    s = doc["sections"][si]
    parts = [s["heading"] or s["type"].title()]
    if bi is not None and bi < len(s["blocks"]):
        b = s["blocks"][bi]
        if b["type"] == "entry":
            parts.append(entry_label(b.get("content") or {}))
    if ui is not None:
        parts.append(f"bullet {ui + 1}")
    elif field:
        parts.append(FIELD_LABEL.get(field, field))
    return " · ".join(parts)


def suggestions(db: Session, user: User, version: ResumeVersion, user_job_id: int | None) -> list[dict[str, Any]]:
    """Recommendations for this revision (and a chosen job): each says what, why, where, whether it is backed by
    verified data, and how it may move Resume Quality or Resume–Job Alignment. Nothing is applied here: the editor
    applies one only when the user accepts it, and the change can be undone (editor undo, or Restore in History)."""
    from backend.services import resume_check as rc
    from core.textclean import unreadable

    doc = document(version)
    _, profile_skills, profile_text = _profile_facts(db, user)
    out: list[dict[str, Any]] = []
    uj = _user_job(db, user, user_job_id)
    job = uj.job if uj else None

    def add(item: dict[str, Any], category: str, *, why: str, effect: str, verified: bool = True, actions: tuple[str, ...] = ("review", "ignore")):
        w = item.get("where") or {}
        item.update({"category": category, "category_label": CATEGORY_LABEL[category], "why": why, "effect": effect, "verified": verified,
                     "evidence": item.get("evidence") or ("supported" if verified else "unknown"), "actions": list(actions),
                     "where_label": _where_label(doc, w["section"], w.get("block"), w.get("bullet"), w.get("field")) if w else ""})
        out.append(item)

    # A. Structural fixes: characters that print as boxes, and missing dates or contact details.
    for si, s in enumerate(doc["sections"]):
        for bi, b in enumerate(s["blocks"]):
            c = b.get("content") or {}
            for f, v in c.items():
                if isinstance(v, str) and unreadable(v):
                    fixed = " ".join(re.sub("[�-]", " ", v).split())
                    add({"id": f"c{si}-{bi}-{f}", "kind": "edit_field", "where": {"section": si, "block": bi, "field": f}, "field": f,
                         "before": v, "after": fixed, "reason": "Removes characters that print as boxes. Retype any that were real symbols."},
                        "structure", why="They have no printable shape: the PDF shows a box and application systems read garbage.",
                        effect="Resume Quality: clears a must-fix item (up to +25).", actions=("review", "go_to", "ignore"))
            for ui, u in enumerate(b["bullets"]):
                if unreadable(u["text"]):
                    fixed = " ".join(re.sub("[�-]", " ", u["text"]).split())
                    add({"id": f"c{si}-{bi}-{ui}", "kind": "rewrite", "where": {"section": si, "block": bi, "bullet": ui},
                         "before": u["text"], "after": fixed, "reason": "Removes characters that print as boxes; every word and number stays."},
                        "structure", why="They print as boxes in the PDF.", effect="Resume Quality: clears a must-fix item (up to +25).",
                        actions=("review", "go_to", "ignore"))
            if s["type"] == "experience" and b["type"] == "entry" and b["visible"] and c.get("title") and not c.get("start"):
                add({"id": f"d{si}-{bi}", "kind": "confirm", "where": {"section": si, "block": bi, "field": "dates"}, "before": None, "after": None,
                     "reason": "Add the month and year you started (and ended)."},
                    "confirm", why="Without dates, employers and application systems can't count this experience.",
                    effect="Resume Quality: clears a worth-fixing item (+8).", verified=False, actions=("go_to", "ignore"))
    header = next((i for i, s in enumerate(doc["sections"]) if s["type"] == "header"), None)
    if header is not None and doc["sections"][header]["blocks"]:
        hc = doc["sections"][header]["blocks"][0].get("content") or {}
        for f, label in (("email", "e-mail"), ("phone", "phone number")):
            if not hc.get(f):
                add({"id": f"h-{f}", "kind": "confirm", "where": {"section": header, "block": 0, "field": f}, "before": None, "after": None,
                     "reason": f"Add your {label}."}, "confirm", why="Employers need a way to reach you.",
                    effect="Resume Quality: clears a contact item.", verified=False, actions=("go_to", "ignore"))

    # B. Writing: same facts, stronger opening verb.
    for si, s in enumerate(doc["sections"]):
        for bi, b in enumerate(s["blocks"]):
            for ui, u in enumerate(b["bullets"]):
                new = _rewrite_weak(u["text"])
                if new and new != u["text"] and not unreadable(u["text"]):
                    # Every number in the original must survive the rewrite (facts and figures are never changed).
                    if sorted(re.findall(r"\d[\d,.]*%?", new)) != sorted(re.findall(r"\d[\d,.]*%?", u["text"])):
                        continue
                    add({"id": f"w{si}-{bi}-{ui}", "kind": "rewrite", "where": {"section": si, "block": bi, "bullet": ui},
                         "before": u["text"], "after": new, "reason": "Same facts and numbers, stronger opening verb."},
                        "writing", why="Bullets that open with what you did are quicker to read than 'Responsible for…'.",
                        effect="Resume Quality: clears a suggestion (+3).", actions=("review", "go_to", "ignore"))

    # C. Emphasise verified experience for the job (reorders and verified skills only).
    if job:
        canon = _canonical_skills()
        terms = [t.lower() for t in (job.required_skills or []) + (job.preferred_skills or [])]
        wanted: set[str] = set()
        for t in (job.required_skills or []) + (job.preferred_skills or []):
            wanted |= canon(t) | {t.lower()}

        def relevance(text: str) -> int:
            low = (text or "").lower()
            return len((canon(text) & wanted) | {w for w in wanted if w in low})

        for si, s in enumerate(doc["sections"]):
            if not s["visible"]:
                continue
            for bi, b in enumerate(s["blocks"]):
                if s["type"] in ("experience", "projects") and len(b["bullets"]) > 1:
                    scored = sorted(range(len(b["bullets"])), key=lambda i: -sum(t in b["bullets"][i]["text"].lower() for t in terms))
                    if scored != list(range(len(b["bullets"]))) and any(t in b["bullets"][scored[0]]["text"].lower() for t in terms):
                        add({"id": f"r{si}-{bi}", "kind": "reorder", "where": {"section": si, "block": bi}, "order": scored, "before": None, "after": None,
                             "reason": "Moves the bullets that match this job's requirements to the top."}, "emphasize",
                            why="Readers skim the first bullet or two of each role.",
                            effect="No score change: the same evidence, where it's seen first.")
                items = (b.get("content") or {}).get("items") or []
                if b["type"] == "skill_group" and len(items) > 1:
                    order = sorted(range(len(items)), key=lambda i: (-min(1, relevance(items[i])), i))
                    if order != list(range(len(items))) and relevance(items[order[0]]):
                        matched = [items[i] for i in order if relevance(items[i])]
                        add({"id": f"k{si}-{bi}", "kind": "reorder_skills", "where": {"section": si, "block": bi}, "order": order,
                             "before": ", ".join(items[:6]), "after": ", ".join(items[i] for i in order[:6]),
                             "reason": f"Puts the skills this job asks for first ({', '.join(matched[:4])})."}, "emphasize",
                            why="The skills the job names are found faster.", effect="No score change: same skills, new order.")
            if s["type"] == "projects" and len(s["blocks"]) > 1:
                score = [relevance(json.dumps(b.get("content")) + " " + " ".join(u["text"] for u in b["bullets"])) for b in s["blocks"]]
                order = sorted(range(len(score)), key=lambda i: (-score[i], i))
                if order != list(range(len(score))) and score[order[0]]:
                    add({"id": f"p{si}", "kind": "reorder_entries", "where": {"section": si, "block": 0}, "order": order, "before": None, "after": None,
                         "reason": "Moves the projects that match this job's requirements to the top."}, "emphasize",
                        why="Your most relevant work should come first.", effect="No score change: same projects, new order.")
        al = rc.alignment(doc, job, profile_skills, profile_text, canon)
        skills_sec = next((i for i, s in enumerate(doc["sections"]) if s["type"] == "skills"), None)
        req = {s.lower() for s in job.required_skills or []}
        total = 2 * len(job.required_skills or []) + len([p for p in job.preferred_skills or [] if p not in (job.required_skills or [])])
        for a in al["addable"]:
            if skills_sec is None:
                break
            gain = round(100 * (2 if a["skill"].lower() in req else 1) / total) if total else 0
            add({"id": f"s-{a['skill']}", "kind": "add_skill", "where": {"section": skills_sec, "block": 0}, "skill": a["skill"],
                 "before": None, "after": a["skill"], "reason": f"The job asks for {a['skill']} and your verified profile includes it."}, "emphasize",
                why="Alignment counts only what is printed on this resume.",
                effect=f"Resume–Job Alignment: about +{gain} (from {al['score']}).", actions=("review", "ignore"))
        for g in al["gaps"]:
            add({"id": f"g-{g['skill']}", "kind": "gap", "where": None, "skill": g["skill"], "before": None, "after": None,
                 "reason": f"The job {'requires' if g['required'] else 'prefers'} {g['skill']}. Nothing in your profile shows it."}, "gap",
                why="JobPilot never adds a skill you haven't shown. If you do have it, add the evidence to your profile first.",
                effect="No change unless you add real evidence.", verified=False, actions=("profile", "ignore"))
    return out


def _canonical_skills():
    """text -> set of canonical skill names found in it (synonyms such as "MS Excel" and "Excel" agree)."""
    from functools import lru_cache

    from core.settings import PROJECT_ROOT
    from core.skills import SkillTaxonomy

    tax = SkillTaxonomy.from_file(PROJECT_ROOT / "config" / "skills_taxonomy.yaml")

    @lru_cache(maxsize=2048)
    def canon(text: str) -> frozenset[str]:
        return frozenset(h.skill.lower() for h in tax.find(text or ""))
    return canon


def layout(version: ResumeVersion) -> dict[str, Any]:
    """Pages, page fill, warnings and fit suggestions for the current version (suggestions are never applied)."""
    return layout_report(document(version), version.template.key, version.settings or {})
