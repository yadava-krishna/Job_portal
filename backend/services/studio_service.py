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
from backend.services.studio_render import TEMPLATES, render_docx, render_pdf

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
        if key not in have:
            t = ResumeTemplate(key=key, name=cfg["name"], category=cfg["category"], ats_safe=cfg["ats_safe"],
                               supports_docx=True, active=True, config_json={k: v for k, v in cfg.items() if k != "name"})
            db.add(t)
            have[key] = t
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
        {"type": "achievements", "heading": "Achievements", "visible": bool(conf.get("achievements")), "blocks": [
            {"type": "entry", "source_profile_ref": "profile:achievements", "visible": True, "content": {"title": None},
             "bullets": [{"text": a, "evidence_refs": ["profile:achievements"], "source": "profile", "approved": True}
                         for a in conf.get("achievements") or []]}] if conf.get("achievements") else []},
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
                      settings={"font_size": 10.5, "density": "normal", "page_size": "A4"},
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
    if isinstance(data.get("settings"), dict):
        s = data["settings"]
        version.settings = {"font_size": float(min(12, max(9, s.get("font_size", 10.5)))),
                            "density": s.get("density") if s.get("density") in ("compact", "normal", "relaxed") else "normal",
                            "page_size": "LETTER" if s.get("page_size") == "LETTER" else "A4",
                            "mobility_line": str(s.get("mobility_line") or "")[:200]}
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


def feedback(db: Session, settings: BackendSettings, user: User, version: ResumeVersion, user_job_id: int | None) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    doc = document(version)
    tpl = TEMPLATES[version.template.key]
    profile_bullets, profile_skills, profile_text = _profile_facts(db, user)
    all_bullets = [(si, bi, ui, u) for si, s in enumerate(doc["sections"]) if s["visible"]
                   for bi, b in enumerate(s["blocks"]) if b["visible"] for ui, u in enumerate(b["bullets"]) if u["approved"]]

    def add(level, code, message, where=None):
        issues.append({"level": level, "code": code, "message": message, "where": where})

    if not tpl["ats_safe"]:
        add("warning", "layout", "Two-column layout: some applicant tracking systems read columns out of order. Use ATS Simple for online forms.")
    header = next((s for s in doc["sections"] if s["type"] == "header"), None)
    hc = (header["blocks"][0]["content"] if header and header["blocks"] else {})
    if not hc.get("email") and not hc.get("phone"):
        add("error", "contact", "Add an e-mail or phone number so employers can reach you.")
    for s in doc["sections"]:
        if s["visible"] and s["type"] not in ("header",) and not any(b["visible"] for b in s["blocks"]):
            add("info", "empty_section", f"'{s['heading']}' is empty: hide it or add content.", {"section": s["type"]})
    words = Counter()
    for si, bi, ui, u in all_bullets:
        text = u["text"]
        where = {"section": doc["sections"][si]["type"], "block": bi, "bullet": ui}
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
    for w, c in words.most_common(3):
        if c >= 7:
            add("warning", "repeated_keyword", f"'{w}' appears {c} times: repetition reads as keyword stuffing.")
    pages = None
    try:
        exp = export(db, settings, user, version, "pdf")
        pages = exp.page_count
        limit = tpl.get("max_pages", 2)
        if pages and pages > limit:
            add("warning", "overflow", f"{pages} pages: this template is designed for {limit}. Tighten bullets or use compact density.")
    except HTTPException:
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
            "readiness": score, "ats_safe_template": tpl["ats_safe"],
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
        skills_sec = next((i for i, s in enumerate(doc["sections"]) if s["type"] == "skills"), None)
        on_resume = json.dumps(doc).lower()
        for skill in job.required_skills or []:
            if skill.lower() not in on_resume and (skill.lower() in profile_skills or skill.lower() in profile_text.lower()) and skills_sec is not None:
                out.append({"id": f"s-{skill}", "kind": "add_skill", "where": {"section": skills_sec, "block": 0}, "skill": skill,
                            "before": None, "after": skill, "evidence": "supported",
                            "reason": f"The job asks for {skill} and your confirmed profile includes it."})
    return out
