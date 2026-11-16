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
from collections import Counter
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

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
            entry(e.get("title"), e.get("company"), e.get("start"), e.get("end"), bool(e.get("is_current")), e.get("bullets") or [], f"experience:{i}")
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
            content = {k: v for k, v in (b.get("content") or {}).items() if isinstance(v, (str, int, float, bool, list, type(None)))}
            blk = ResumeBlock(type=b["type"], source_profile_ref=(b.get("source_profile_ref") or None), content_json=content,
                              position=bi, visible=bool(b.get("visible", True)))
            for ui, u in enumerate(b.get("bullets") or []):
                text = (u.get("text") or "").strip()[:1200]
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
    payload = json.dumps({"t": version.template.key, "s": version.settings or {}, "d": doc}, sort_keys=True, ensure_ascii=False)
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

def export(db: Session, settings: BackendSettings, user: User, version: ResumeVersion, fmt: str) -> ResumeExport:
    if fmt not in ("pdf", "docx"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Format must be pdf or docx")
    ck = version.content_checksum or checksum(version)
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
    db.commit()
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


# Each issue has a kind:
#   format    objective, checked mechanically (contact details, dates, duplicates, characters, pages, export read-back)
#   accuracy  figures not backed by the confirmed profile
#   writing   style advice (weak openings, very short bullets, repetition): opinions, not rules
#   job       how this resume covers a chosen job's listed skills
ISSUE_KIND = {"contact": "format", "contact_email": "format", "contact_phone": "format", "empty_section": "format", "duplicate_entry": "format",
              "duplicate_bullet": "format", "date_order": "format", "date_missing": "format", "date_current": "format",
              "unsupported_chars": "format", "layout": "format", "overflow": "format", "last_page": "format", "long_bullet": "format",
              "export_readback": "format", "render": "format", "unsupported_claim": "accuracy", "weak_bullet": "writing",
              "short_bullet": "writing", "repeated_keyword": "writing", "job_keyword": "job", "job_gap": "job"}
SCORE_METHOD = ("Readiness is JobPilot's own checklist: 100 minus 25 for each must-fix item, 8 for each worth-fixing item, 3 for each "
                "suggestion and 1 for each note. It is not an ATS score: no universal ATS score exists, and each employer's system "
                "reads resumes differently.")
_ODD_CHARS = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uE000-\uF8FF\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFD]")


def _ym(value: Any) -> tuple[int, int] | None:
    from backend.services.studio_render import format_date

    t = format_date(value, "MM/YYYY")
    m = re.fullmatch(r"(\d{2})/(\d{4})", t or "")
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.fullmatch(r"\d{4}", t or "")
    return (int(t), 0) if m else None


def _readback(doc: dict[str, Any], template_key: str, settings_: dict[str, Any]) -> list[str]:
    """Render the PDF, read it back with JobPilot's own parser, and list what did not come back out."""
    import tempfile
    from pathlib import Path

    from core.settings import PROJECT_ROOT
    from core.skills import SkillTaxonomy
    from resume.profile_builder import ResumeProfileExtractor

    pdf, _ = render_pdf(doc, template_key, settings_)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "resume.pdf"
        path.write_bytes(pdf)
        try:
            p = ResumeProfileExtractor(SkillTaxonomy.from_file(PROJECT_ROOT / "config" / "skills_taxonomy.yaml")).build(path)
        except Exception as exc:  # noqa: BLE001 - any parser failure is itself the finding
            return [f"The exported PDF could not be read back ({type(exc).__name__})."]
    text = " ".join((p.get("resume_text") or "").split())
    missing: list[str] = []
    for s in doc["sections"]:
        if not s["visible"]:
            continue
        for b in s["blocks"]:
            if not b["visible"]:
                continue
            for u in b["bullets"]:
                t = " ".join((u.get("text") or "").split())
                if u.get("approved", True) and t and t[:60] not in text:
                    missing.append(f"bullet \"{t[:50]}…\"")
    exp = next((s for s in doc["sections"] if s["type"] == "experience" and s["visible"]), None)
    found = {(r.get("title") or "").lower() for r in p.get("experience", [])}
    for b in (exp or {}).get("blocks", []):
        c = b.get("content") or {}
        if b["visible"] and c.get("title") and c.get("start") and c["title"].lower() not in found:
            missing.append(f"role \"{c['title']}\" (title, company and dates as one entry)")
    return missing


def feedback(db: Session, settings: BackendSettings, user: User, version: ResumeVersion, user_job_id: int | None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    doc = document(version)
    tpl = TEMPLATES[version.template.key]
    profile_bullets, profile_skills, profile_text = _profile_facts(db, user)
    all_bullets = [(si, bi, ui, u) for si, s in enumerate(doc["sections"]) if s["visible"]
                   for bi, b in enumerate(s["blocks"]) if b["visible"] for ui, u in enumerate(b["bullets"]) if u["approved"]]

    def add(level, code, message, where=None):
        issues.append({"level": level, "code": code, "kind": ISSUE_KIND.get(code, "format"), "message": message, "where": where})

    if not tpl["ats_safe"]:
        add("warning", "layout", "Section names in the margin and colour suit people better than applicant-tracking systems. Use Classic ATS for online forms.")
    header = next((s for s in doc["sections"] if s["type"] == "header"), None)
    hc = (header["blocks"][0]["content"] if header and header["blocks"] else {})
    if not hc.get("email") and not hc.get("phone"):
        add("error", "contact", "Add an e-mail or phone number so employers can reach you.")
    elif not hc.get("email"):
        add("warning", "contact_email", "Add an e-mail address: most application systems require one.")
    elif not hc.get("phone"):
        add("info", "contact_phone", "No phone number. Recruiters in India usually call first.")
    if not hc.get("name"):
        add("error", "contact", "Add your name to the header.")
    for si, s in enumerate(doc["sections"]):
        if not s["visible"] or s["type"] == "header":
            continue
        if not any(b["visible"] for b in s["blocks"]):
            add("info", "empty_section", f"'{s['heading']}' is empty: hide it or add content.", {"section": s["type"]})
        seen: dict[tuple, int] = {}
        for bi, b in enumerate(s["blocks"]):
            c = b.get("content") or {}
            if not b["visible"] or b["type"] != "entry":
                continue
            key = (str(c.get("title") or "").strip().lower(), str(c.get("organization") or "").strip().lower(), str(c.get("start") or ""))
            if any(key[:2]) and key in seen:
                add("warning", "duplicate_entry", f"'{c.get('title') or c.get('organization')}' appears twice in {s['heading']}.", {"section": s["type"], "block": bi})
            seen.setdefault(key, bi)
            if s["type"] == "experience":
                start, end = _ym(c.get("start")), _ym(c.get("end"))
                if c.get("title") and not c.get("start"):
                    add("warning", "date_missing", f"'{c.get('title')}' has no start date. Dates let employers (and JobPilot) work out your experience.",
                        {"section": s["type"], "block": bi})
                if start and end and not c.get("current") and end < start:
                    add("error", "date_order", f"'{c.get('title')}' ends before it starts.", {"section": s["type"], "block": bi})
                if c.get("current") and c.get("end"):
                    add("info", "date_current", f"'{c.get('title')}' is marked current but also has an end date; the end date is not shown.", {"section": s["type"], "block": bi})
    texts = [json.dumps(hc, ensure_ascii=False)] + [json.dumps(b.get("content") or {}, ensure_ascii=False) for s in doc["sections"] for b in s["blocks"]] + \
            [u["text"] for *_, u in all_bullets]
    odd = sorted({ch for t in texts for ch in _ODD_CHARS.findall(t)})
    if odd:
        add("warning", "unsupported_chars", f"Emoji or special symbols ({' '.join(odd[:6])}) may show as boxes or be dropped by application systems. Use plain text.")
    words = Counter()
    seen_bullets: dict[str, dict] = {}
    dup_bullets: dict[str, list] = {}
    for si, bi, ui, u in all_bullets:
        text = u["text"]
        where = {"section": doc["sections"][si]["type"], "block": bi, "bullet": ui}
        norm = " ".join(text.lower().split())
        if norm and norm in seen_bullets:
            dup_bullets.setdefault(where["section"], []).append((seen_bullets[norm]["section"], where))
        seen_bullets.setdefault(norm, where)
        low = text.lower()
        for weak in WEAK_STARTS:
            if low.startswith(weak):
                add("warning", "weak_bullet", f"Starts with '{weak}': lead with what you did.", where)
                break
        n = len(text.split())
        if n > 40:
            add("warning", "long_bullet", f"{n} words: keep bullets under ~30 words.", where)
        elif n < 4:
            add("info", "short_bullet", "Very short bullet: add what changed because of it.", where)
        if u["source"] != "profile" and text.strip() not in profile_bullets:
            nums = re.findall(r"\d[\d,.]*%?", text)
            if nums and not all(x in profile_text for x in nums):
                add("warning", "unsupported_claim", f"'{', '.join(nums)}' isn't in your confirmed profile. Only keep figures you can back up.", where)
        for w in re.findall(r"[a-zA-Z][a-zA-Z+#.-]{3,}", low):
            if w not in STOP:
                words[w] += 1
    for sec_type, dups in dup_bullets.items():
        first_where = dups[0][1]
        also = sorted({src for src, _ in dups})
        heading = next((s["heading"] for s in doc["sections"] if s["type"] == sec_type), sec_type)
        add("warning", "duplicate_bullet", f"{len(dups)} bullet{'s' if len(dups) > 1 else ''} in {heading} repeat{'' if len(dups) > 1 else 's'} "
            f"text already used in {', '.join(next((s['heading'] for s in doc['sections'] if s['type'] == t), t) for t in also)}. Remove the repeats.",
            first_where)
    for w, c in words.most_common(3):
        if c >= 7:
            add("warning", "repeated_keyword", f"'{w}' appears {c} times: repetition reads as keyword stuffing.")
    pages = None
    try:
        rep = layout(version)
        pages = rep["pages"]
        for w in rep["warnings"]:
            if w["level"] == "warning":
                add("warning", "last_page" if "last page" in w["message"] else "overflow", w["message"])
        missing = _readback(doc, version.template.key, version.settings or {})
        if missing:
            add("error", "export_readback", "When JobPilot reads the exported PDF back, it can't find: " + "; ".join(missing[:4])
                + (f" and {len(missing) - 4} more" if len(missing) > 4 else "") + ". Application systems may miss them too.")
    except HTTPException:
        add("error", "render", "The resume could not be rendered; check for unusual characters.")
    except Exception:  # noqa: BLE001
        log_ = __import__("logging").getLogger(__name__)
        log_.exception("resume layout/read-back check failed")
        add("error", "render", "The resume could not be rendered; check for unusual characters.")
    job = None
    if user_job_id:
        uj = db.execute(select(UserJob).where(UserJob.id == user_job_id, UserJob.user_id == user.id)).scalar_one_or_none()
        if uj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
        job = uj.job
        resume_text = json.dumps(doc).lower()
        for skill in job.required_skills or []:
            if skill.lower() in resume_text:
                continue
            if skill.lower() in profile_skills or skill.lower() in profile_text.lower():
                add("suggestion", "job_keyword", f"The job asks for {skill}, which is in your profile but not on this resume.")
            else:
                add("info", "job_gap", f"The job asks for {skill}. It isn't in your profile, so don't add it unless it's true; see Career > Gaps.")
    score = max(0, 100 - sum({"error": 25, "warning": 8, "suggestion": 3, "info": 1}[i["level"]] for i in issues))
    fb = ResumeFeedback(user_id=user.id, resume_version_id=version.id, job_id=job.id if job else None,
                        checksum=version.content_checksum, score=score, issues_json=issues)
    db.add(fb)
    db.commit()
    return {"resume_version_id": version.id, "job_id": job.id if job else None, "pages": pages, "issues": issues,
            "readiness": score, "score_method": SCORE_METHOD, "ats_safe_template": tpl["ats_safe"],
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


def suggestions(db: Session, user: User, version: ResumeVersion, user_job_id: int | None) -> list[dict[str, Any]]:
    doc = document(version)
    _, profile_skills, profile_text = _profile_facts(db, user)
    out: list[dict[str, Any]] = []
    job = None
    if user_job_id:
        uj = db.execute(select(UserJob).where(UserJob.id == user_job_id, UserJob.user_id == user.id)).scalar_one_or_none()
        if uj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
        job = uj.job
    for si, s in enumerate(doc["sections"]):
        for bi, b in enumerate(s["blocks"]):
            for ui, u in enumerate(b["bullets"]):
                new = _rewrite_weak(u["text"])
                if new and new != u["text"]:
                    out.append({"id": f"w{si}-{bi}-{ui}", "kind": "rewrite", "where": {"section": si, "block": bi, "bullet": ui},
                                "before": u["text"], "after": new, "evidence": "supported",
                                "reason": "Same facts, stronger opening verb."})
            if job and s["type"] in ("experience", "projects") and len(b["bullets"]) > 1:
                terms = [t.lower() for t in (job.required_skills or []) + (job.preferred_skills or [])]
                scored = sorted(range(len(b["bullets"])), key=lambda i: -sum(t in b["bullets"][i]["text"].lower() for t in terms))
                if scored != list(range(len(b["bullets"]))) and any(t in b["bullets"][scored[0]]["text"].lower() for t in terms):
                    out.append({"id": f"r{si}-{bi}", "kind": "reorder", "where": {"section": si, "block": bi}, "order": scored,
                                "before": None, "after": None, "evidence": "supported",
                                "reason": "Moves the bullets that match this job's requirements to the top."})
    if job:
        canon = _canonical_skills()
        wanted = set()
        for t in (job.required_skills or []) + (job.preferred_skills or []):
            wanted |= canon(t) | {t.lower()}

        def relevance(text: str) -> int:
            low = (text or "").lower()
            return len((canon(text) & wanted) | {w for w in wanted if w in low})

        for si, s in enumerate(doc["sections"]):
            if not s["visible"]:
                continue
            # Skills the job asks for first in each skill group (same items, new order).
            for bi, b in enumerate(s["blocks"]):
                items = (b.get("content") or {}).get("items") or []
                if b["type"] == "skill_group" and len(items) > 1:
                    order = sorted(range(len(items)), key=lambda i: (-min(1, relevance(items[i])), i))
                    if order != list(range(len(items))) and relevance(items[order[0]]):
                        matched = [items[i] for i in order if relevance(items[i])]
                        out.append({"id": f"k{si}-{bi}", "kind": "reorder_skills", "where": {"section": si, "block": bi}, "order": order,
                                    "before": ", ".join(items[:6]), "after": ", ".join(items[i] for i in order[:6]), "evidence": "supported",
                                    "reason": f"Puts the skills this job asks for first ({', '.join(matched[:4])})."})
            # Most relevant projects first (same entries, new order).
            if s["type"] == "projects" and len(s["blocks"]) > 1:
                score = [relevance(json.dumps(b.get("content")) + " " + " ".join(u["text"] for u in b["bullets"])) for b in s["blocks"]]
                order = sorted(range(len(score)), key=lambda i: (-score[i], i))
                if order != list(range(len(score))) and score[order[0]]:
                    out.append({"id": f"p{si}", "kind": "reorder_entries", "where": {"section": si, "block": 0}, "order": order,
                                "before": None, "after": None, "evidence": "supported",
                                "reason": "Moves the projects that match this job's requirements to the top."})
        skills_sec = next((i for i, s in enumerate(doc["sections"]) if s["type"] == "skills"), None)
        on_resume = json.dumps(doc).lower()
        for skill in job.required_skills or []:
            if skill.lower() not in on_resume and (skill.lower() in profile_skills or skill.lower() in profile_text.lower()) and skills_sec is not None:
                out.append({"id": f"s-{skill}", "kind": "add_skill", "where": {"section": skills_sec, "block": 0}, "skill": skill,
                            "before": None, "after": skill, "evidence": "supported",
                            "reason": f"The job asks for {skill} and your confirmed profile includes it."})
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
