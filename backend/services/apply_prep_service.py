"""Application preflight: everything JobPilot already knows, prepared before the employer's form is opened.

The package (stored on `applications.package`, so it survives refreshes, closed tabs and restarts) holds:
  destination   where the application is really submitted, with the evidence (destination_service)
  capabilities  prepare / autofill / assisted submit / native hand-off / verified confirmation for that destination
  resume        the resume chosen for this application (the user's explicit choice is never replaced by the default)
  profile       the confirmed personal and professional details forms ask for
  answers       common questions + the employer's published questions (Greenhouse) or the questions Smart Apply saw on
                the form, each VERIFIED / SUGGESTED / NEEDS_INPUT from answer memory (never invented)
  eligibility, missing, conflicts, readiness, next action

Readiness is honest about what is unknown: when the employer's questions can't be read before the form is opened,
the package says "form not inspected yet" instead of claiming the application is complete.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Application, Resume, User, UserJob, utcnow
from backend.services import answer_memory, destination_service, resume_service

PACKAGE_VERSION = 1
QUESTIONS_TTL = timedelta(hours=24)
QUESTIONS_FAILED_TTL = timedelta(minutes=15)  # after a failed fetch, don't make the person wait on it again for a while
RESUME_STATES = ("form_opened", "filling", "needs_information", "ready_for_review", "reviewed", "interrupted", "submission_authorized")
ACTIONS = {
    "review_autofill": "Review and autofill",
    "continue_employer": "Continue on employer site",
    "open_native": "Open native application",
    "resume": "Resume application",
    "resolve_uncertain": "Check what happened",
    "done": "Submitted",
}
PERSONAL = (("full_name", "Full name"), ("email", "Email"), ("phone", "Phone"), ("location", "Location"))
PROFESSIONAL = (("current_title", "Current title"), ("current_company", "Current employer"),
                ("total_experience_years", "Total experience (years, from your resume)"), ("degree", "Highest qualification"),
                ("school", "School / university"))
LINKS = (("linkedin_url", "LinkedIn"), ("github_url", "GitHub"), ("portfolio_url", "Portfolio"), ("website_url", "Website"))


def _country_question(job) -> str:
    cc = (job.country or "").strip().lower()
    name = answer_memory.COUNTRY_NAMES.get({"gb": "uk"}.get(cc, cc))
    return f"Are you legally authorised to work in {name}?" if name else "Are you legally authorised to work in the job's country?"


def common_questions(job) -> list[str]:
    return ["Total years of experience", "Notice period", "Current CTC", "Expected CTC", "Willing to relocate?",
            _country_question(job), "Will you require visa sponsorship?"]


def _employer_questions(db: Session, pkg: dict[str, Any], dest: dict[str, Any], *, refresh: bool) -> tuple[list[dict[str, Any]], str]:
    """(questions, source). Greenhouse publishes its questions; for other forms we know them once Smart Apply has seen them."""
    from backend.services.ats import base as ats_base
    from backend.services.ats.greenhouse import fetch_questions
    from backend.services.extension_service import job_ref

    if dest.get("kind") == "ats" and dest.get("ats") == "greenhouse":
        cached = pkg.get("employer_questions") or {}
        fresh = cached.get("fetched_at") and utcnow() - datetime.fromisoformat(cached["fetched_at"]) < QUESTIONS_TTL
        if cached.get("url") == dest["url"] and fresh and not refresh:
            return cached.get("items") or [], cached.get("source", "employer_api")
        failed = pkg.get("employer_questions_failed") or {}
        recently_failed = (failed.get("url") == dest["url"] and failed.get("at")
                           and utcnow() - datetime.fromisoformat(failed["at"]) < QUESTIONS_FAILED_TTL)
        ref = job_ref(dest["url"])
        if ref and (refresh or not recently_failed):
            try:
                # One attempt: the person is waiting, and the form itself is read when it opens anyway.
                items = fetch_questions(ref[1], ref[2], retry=False)
                pkg["employer_questions"] = {"url": dest["url"], "fetched_at": utcnow().isoformat(), "items": items, "source": "employer_api"}
                pkg.pop("employer_questions_failed", None)
                return items, "employer_api"
            except ats_base.AtsError:
                pkg["employer_questions_failed"] = {"url": dest["url"], "at": utcnow().isoformat()}
    seen = pkg.get("form_questions") or {}
    if seen.get("items"):
        req = seen.get("requirements") or {}
        return [{"label": q, "required": req.get(q) == "required", "requirement": req.get(q, "unknown"), "type": "text", "options": []}
                for q in seen["items"]], "employer_form"
    return [], "not_inspected"


def _recommend_resume(db: Session, user: User, app: Application) -> dict[str, Any] | None:
    """A resume to suggest (never to use without the user's choice), with the evidence for it:
    a Resume Studio version made for this job, else the user's most recently edited Studio version, else their
    default upload."""
    from backend.models import ResumeVersion

    versions = list(db.execute(select(ResumeVersion).where(ResumeVersion.user_id == user.id, ResumeVersion.status != "archived")
                               .order_by(ResumeVersion.updated_at.desc())).unique().scalars())
    for v in versions:
        if v.target_job_id and v.target_job_id == app.job_id:
            return {"kind": "studio", "id": v.id, "name": v.name, "format": "pdf", "why": "Made in Resume Studio for this job."}
    if versions:
        v = versions[0]
        return {"kind": "studio", "id": v.id, "name": v.name, "format": "pdf", "why": "Your most recently edited Resume Studio version."}
    r = resume_service.active_resume(db, user)
    if r is not None:
        return {"kind": "upload", "id": r.id, "name": r.original_filename, "format": "docx" if r.stored_path.lower().endswith(".docx") else "pdf",
                "why": "Your default uploaded resume."}
    return None


def _resume(db: Session, user: User, app: Application, pkg: dict[str, Any]) -> dict[str, Any]:
    """The resume for this application. Only a resume the user chose for it counts as ready ("selected_by": "you");
    otherwise a recommendation is offered and the user must pick or confirm it. Never a silent default."""
    from backend.models import ResumeVersion

    choice = pkg.get("resume_choice") or {}
    if choice.get("kind") == "studio" and choice.get("id"):
        v = db.get(ResumeVersion, choice["id"])
        if v is not None and v.user_id == user.id:
            return {"kind": "studio", "id": v.id, "name": v.name, "format": choice.get("format") or "pdf", "selected_by": "you", "ready": True,
                    "revision": choice.get("revision"), "checksum": app.resume_checksum, "chosen_at": choice.get("at")}
    if choice.get("kind") == "upload" and choice.get("id"):
        r = db.get(Resume, choice["id"])
        if r is not None and r.user_id == user.id:
            return {"kind": "upload", "id": r.id, "name": r.original_filename, "format": "docx" if r.stored_path.lower().endswith(".docx") else "pdf",
                    "selected_by": "you", "ready": True, "checksum": r.sha256, "chosen_at": choice.get("at")}
    if app.resume_version_id:  # attached to the application from Resume Studio ("Use for an application")
        v = db.get(ResumeVersion, app.resume_version_id)
        if v is not None and v.user_id == user.id:
            return {"kind": "studio", "id": v.id, "name": v.name, "format": "pdf", "selected_by": "you", "ready": True, "checksum": app.resume_checksum}
    rec = _recommend_resume(db, user, app)
    if rec is None:
        return {"kind": None, "id": None, "name": None, "format": None, "selected_by": None, "ready": False, "recommended": None}
    # Nothing chosen yet: shown as a recommendation the user confirms. Not ready until they do.
    return {"kind": None, "id": None, "name": None, "format": None, "selected_by": None, "ready": False, "recommended": rec}


def _next_action(app: Application, caps: dict[str, Any], dest: dict[str, Any]) -> str:
    if app.status == "SUBMITTED":
        return "done"
    if app.apply_state == "submission_uncertain" or app.status == "CONFIRMATION_PENDING":
        return "resolve_uncertain"
    if app.apply_state in RESUME_STATES:
        return "resume"
    if caps.get("autofill") and dest.get("kind") == "ats":
        return "review_autofill"
    if dest.get("kind") == "restricted":
        return "open_native"
    return "continue_employer"


def build(db: Session, settings, user: User, app: Application, *, refresh_questions: bool = False, probe_hosted: bool = True,
          commit: bool = True) -> dict[str, Any]:
    from backend.services.extension_service import autofill_profile

    job = app.job
    uj = db.get(UserJob, app.user_job_id) if app.user_job_id else None
    pkg = dict(app.package or {})
    dest = destination_service.resolve(db, job, confirmed=pkg.get("destination_confirmed"), probe_hosted=probe_hosted)
    caps = dest.get("capabilities") or destination_service.capabilities("manual", None, None)
    prof = autofill_profile(db, user)
    fields = prof.get("fields") or {}

    def section(rows):
        return [{"key": k, "label": label, "value": fields.get(k), "source": "resume" if k == "total_experience_years" else "profile"}
                for k, label in rows]

    employer, q_source = _employer_questions(db, pkg, dest, refresh=refresh_questions)
    listing = [q for q in (job.screening_questions or []) if isinstance(q, str) and q.strip()]
    seen: set[str] = set()
    ordered: list[tuple[str, str, dict[str, Any]]] = []
    for origin, items in (("common", [{"label": q} for q in common_questions(job)]), ("employer", employer),
                          ("listing", [{"label": q} for q in listing])):
        for it in items:
            label = it["label"].strip()
            k = answer_memory.normalize(label)
            if label and k not in seen:
                seen.add(k)
                ordered.append((origin, label, it))
    overrides = pkg.get("overrides") or {}
    resolved = answer_memory.resolve(db, settings, user, [q for _, q, _ in ordered], company=job.company, job_id=job.id, overrides=overrides,
                                    job_country=job.country)
    # The same canonical key asked twice (a common question and the employer's wording): keep the employer's wording.
    by_key: dict[str, int] = {}
    answers: list[dict[str, Any]] = []
    for (origin, label, it), a in zip(ordered, resolved):
        required = bool(it.get("required")) or origin == "common"
        a = {**a, "origin": origin, "required": required, "options": it.get("options") or [], "field_type": it.get("type") or "text",
             # What the employer says: required | optional | unknown (JobPilot's own common questions count as required).
             "requirement": it.get("requirement") or ("required" if required else "optional" if origin == "employer" else "unknown")}
        if a["key"] and a["key"] in by_key:
            prev = by_key[a["key"]]
            if origin == "employer" and answers[prev]["origin"] == "common":
                answers[prev] = a
            continue
        if a["key"]:
            by_key[a["key"]] = len(answers)
        answers.append(a)

    missing = [m for m in prof.get("missing") or [] if m.get("key") in ("profile", "resume", "full_name", "email", "phone")]
    missing += [{"key": a["key"] or a["question"], "label": a["label"] if a["key"] else a["question"], "where": "this_application"}
                for a in answers if a["status"] == "NEEDS_INPUT" and a["sensitivity"] != "never" and (a["required"] or a["origin"] == "listing")]
    conflicts = _conflicts(answers, fields)
    eligibility = _eligibility(job, uj)
    resume = _resume(db, user, app, pkg)
    needs = [a for a in answers if a["status"] == "NEEDS_INPUT" and a["sensitivity"] != "never" and (a["required"] or a["origin"] == "listing")]
    to_check = [a for a in answers if a["status"] == "SUGGESTED"]
    # Unanswered questions not known to be required (e.g. read off the live form, which doesn't say): shown, not blocking.
    other = [a for a in answers if a["status"] == "NEEDS_INPUT" and a["sensitivity"] != "never" and a not in needs]
    inspected = q_source in ("employer_api", "employer_form")
    readiness = {
        "profile": bool(prof.get("ready")) and not any(m["key"] in ("profile", "full_name", "email", "phone") for m in missing),
        "resume": resume["ready"],
        "resume_choice_needed": not resume["ready"] and bool(resume.get("recommended")),
        "known_questions": not needs,
        "form_inspected": inspected,
        "to_check": len(to_check),
        "needs_input": len(needs),
        "other_unanswered": len(other),
    }
    readiness["level"] = ("blocked" if not readiness["profile"] or (not readiness["resume"] and not readiness["resume_choice_needed"]) else
                          "needs_input" if needs or readiness["resume_choice_needed"] else
                          "ready" if inspected else "ready_known")
    readiness["summary"] = {
        "blocked": "Finish your profile and add a resume first.",
        "needs_input": f"{len(needs)} answer{'s' if len(needs) != 1 else ''} needed before you apply.",
        "ready": "Everything the employer's form asks for is prepared.",
        "ready_known": "Everything JobPilot knows is prepared. The employer's form may ask more: Smart Apply shows those questions when it opens it.",
    }[readiness["level"]]
    if readiness["resume_choice_needed"]:
        readiness["summary"] = "Choose the resume for this application." + (f" {readiness['summary']}" if needs else "")
    if other and readiness["level"] in ("ready", "ready_known"):
        readiness["summary"] = ("Everything required that JobPilot knows of is prepared. "
                                f"{len(other)} other question{'s' if len(other) != 1 else ''} on the form "
                                f"{'have' if len(other) != 1 else 'has'} no answer yet: answer {'them' if len(other) != 1 else 'it'} below "
                                "or on the form if the employer requires it.")
    if not caps.get("autofill"):
        readiness["summary"] = readiness["summary"].replace("Smart Apply shows those questions when it opens it", "check the form when you open it")

    action = _next_action(app, caps, dest)
    pkg.update({
        "version": PACKAGE_VERSION, "prepared_at": utcnow().isoformat(),
        "job": {"title": job.title, "company": job.company, "source": job.platform, "location": job.location,
                "match_score": uj.match_score if uj else None, "job_url": job.job_url},
        "destination": {k: v for k, v in dest.items() if k != "capabilities"}, "capabilities": caps,
        "resume": resume, "profile": {"personal": section(PERSONAL), "professional": section(PROFESSIONAL), "links": section(LINKS)},
        "answers": answers, "questions_source": q_source, "missing": missing, "conflicts": conflicts, "eligibility": eligibility,
        "readiness": readiness, "action": action, "action_label": ACTIONS[action],
    })
    app.package = pkg
    if commit:
        db.commit()
        db.refresh(app)
    return pkg


def _conflicts(answers: list[dict[str, Any]], fields: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    by_key = {a["key"]: a for a in answers if a.get("key")}
    total = by_key.get("experience_years.total")
    resume_years = fields.get("total_experience_years")
    if total and total.get("source") == "memory" and isinstance(total.get("value"), (int, float)) and resume_years is not None:
        if abs(float(total["value"]) - float(resume_years)) >= 1.5:
            out.append({"key": "experience_years.total", "label": "Total experience",
                        "detail": f"You saved {total['value']:g} years; your resume dates add up to {resume_years:g}. Use the one that's right."})
    cur, exp = by_key.get("current_ctc"), by_key.get("expected_ctc")
    if cur and exp and isinstance(cur.get("value"), dict) and isinstance(exp.get("value"), dict):
        c, e = cur["value"], exp["value"]
        if c.get("currency") == e.get("currency") and c.get("period") == e.get("period") and e.get("amount", 0) < c.get("amount", 0):
            out.append({"key": "expected_ctc", "label": "Expected compensation",
                        "detail": "Your expected compensation is lower than your current compensation. Check both."})
    for a in answers:
        if a.get("notes") and a["status"] != "NEEDS_INPUT":
            out.append({"key": a.get("key") or a["question"], "label": a["question"], "detail": " ".join(a["notes"])})
    return out


def _eligibility(job, uj: UserJob | None) -> list[dict[str, Any]]:
    from core import timeutil

    out = []
    if job.closed_at or job.is_expired:
        out.append({"label": "Posting status", "status": "fail", "detail": "This posting looks closed or expired. Check before applying."})
    elif job.posted_at and (timeutil.today() - job.posted_at).days > 30:
        out.append({"label": "Posting age", "status": "warn", "detail": f"Posted {(timeutil.today() - job.posted_at).days} days ago; it may be closed."})
    if uj is not None and uj.eligibility_status:
        st = {"ELIGIBLE": "ok", "INELIGIBLE": "fail"}.get(uj.eligibility_status, "warn")
        out.append({"label": "Eligibility", "status": st,
                    "detail": "; ".join(uj.eligibility_reasons or []) or ("You meet the stated requirements." if st == "ok" else "Check the requirements.")})
    if job.sponsorship_signal in ("no", "not_offered"):
        out.append({"label": "Visa sponsorship", "status": "warn", "detail": job.sponsorship_evidence or "The posting says it doesn't sponsor visas."})
    return out


# ---- changes from the Apply Workspace --------------------------------------------------------

def select_resume(db: Session, settings, user: User, app: Application, kind: str, rid: int, fmt: str = "pdf") -> None:
    from backend.models import ResumeVersion
    from backend.services import application_service

    if app.status == "SUBMITTED":
        raise HTTPException(status.HTTP_409_CONFLICT, "The resume of a submitted application can't be changed.")
    pkg = dict(app.package or {})
    if kind == "studio":
        v = db.get(ResumeVersion, rid)
        if v is None or v.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume version not found.")
        application_service.attach_resume_version(db, settings, user, app, rid)
    elif kind == "upload":
        r = db.get(Resume, rid)
        if r is None or r.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found.")
        app.resume_id, app.resume_used = r.id, r.original_filename
        app.resume_version_id = app.resume_export_id = app.resume_checksum = None
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown resume kind.")
    pkg["resume_choice"] = {"kind": kind, "id": rid, "format": fmt if fmt in ("pdf", "docx") else "pdf", "at": utcnow().isoformat()}
    if kind == "studio":  # the exact revision and file chosen, for the application's history
        v = db.get(ResumeVersion, rid)
        pkg["resume_choice"].update({"revision": v.revision, "checksum": app.resume_checksum, "export_id": app.resume_export_id})
    else:
        pkg["resume_choice"]["checksum"] = r.sha256
        app.resume_checksum = r.sha256
    app.package = pkg
    db.commit()


def save_answers(db: Session, settings, user: User, app: Application, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Answers typed in the workspace: used for this application; remembered only where the user ticked "remember"."""
    if app.status == "SUBMITTED":
        raise HTTPException(status.HTTP_409_CONFLICT, "This application was already submitted.")
    pkg = dict(app.package or {})
    overrides = dict(pkg.get("overrides") or {})
    errors: list[dict[str, str]] = []
    saved: list[str] = []
    for it in items:
        q, raw = (it.get("question") or "").strip(), it.get("answer")
        if not q:
            continue
        m = answer_memory.classify(q)
        if m.never:
            errors.append({"question": q, "error": m.reason or "Answer this one yourself on the form."})
            continue
        if raw in (None, ""):
            overrides.pop(q, None)
            continue
        try:
            shown = answer_memory.parse(m.canon.value_type if m.canon else "text", raw)[1]
        except answer_memory.InvalidAnswer as e:
            errors.append({"question": q, "error": str(e)})
            continue
        overrides[q] = shown
        if it.get("remember"):
            try:
                answer_memory.save(db, settings, user, question=q, answer=raw, key=it.get("key") or None, company=app.job.company,
                                   job_id=app.job_id, source="apply_workspace", commit=False)
                saved.append(q)
            except HTTPException as e:
                errors.append({"question": q, "error": str(e.detail)})
    pkg["overrides"] = overrides
    app.package = pkg
    db.flush()
    out = build(db, settings, user, app)
    return {"package": out, "saved": saved, "errors": errors}


def record_form_questions(db: Session, app: Application, labels: list[str], *, requirements: dict[str, str] | None = None) -> None:
    """Questions Smart Apply saw on the employer's form (labels, and whether the form marks each required or optional),
    so the workspace can show them on return. Unmarked questions are "unknown", which is never treated as optional."""
    req = {" ".join(str(k).split())[:300]: v for k, v in (requirements or {}).items() if v in ("required", "optional")}
    clean = []
    for label in labels:
        t = " ".join(str(label or "").split())[:300]
        if t and not answer_memory.classify(t).never and t not in clean:
            clean.append(t)
    if not clean:
        return
    pkg = dict(app.package or {})
    pkg["form_questions"] = {"items": clean[:60], "requirements": {t: req[t] for t in clean[:60] if t in req},
                             "seen_at": utcnow().isoformat()}
    app.package = pkg


def confirm_destination(db: Session, settings, user: User, app: Application, url: str) -> dict[str, Any]:
    hit = destination_service.confirm_suggestion(db, app.job, url)
    if hit is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That employer posting is no longer available as a match for this job.")
    pkg = dict(app.package or {})
    pkg["destination_confirmed"] = {**hit, "at": utcnow().isoformat()}
    pkg.pop("employer_questions", None)
    app.package = pkg
    db.flush()
    return build(db, settings, user, app)


def clear_destination(db: Session, settings, user: User, app: Application) -> dict[str, Any]:
    pkg = dict(app.package or {})
    pkg.pop("destination_confirmed", None)
    pkg.pop("employer_questions", None)
    app.package = pkg
    db.flush()
    return build(db, settings, user, app)


def is_stale(db: Session, user: User, app: Application) -> bool:
    """The stored package predates the user's latest profile or remembered-answer change (so it must be rebuilt before
    the extension fills from it). A submitted application's package is history and is never rebuilt for filling."""
    from sqlalchemy import func, select

    from backend.models import AnswerMemory, CandidateProfile

    pkg = app.package or {}
    if not pkg:
        return True
    try:
        prepared = datetime.fromisoformat(pkg.get("prepared_at") or "")
    except ValueError:
        return True
    if prepared.tzinfo is None:
        prepared = prepared.replace(tzinfo=utcnow().tzinfo)
    changes = [db.execute(select(CandidateProfile.updated_at).where(CandidateProfile.user_id == user.id)).scalar_one_or_none(),
               db.execute(select(func.max(AnswerMemory.updated_at)).where(AnswerMemory.user_id == user.id)).scalar_one_or_none()]
    for t in changes:
        if t is not None and (t if t.tzinfo else t.replace(tzinfo=prepared.tzinfo)) > prepared:
            return True
    return False


def extension_view(app: Application) -> dict[str, Any]:
    """What the extension needs from the package: the chosen resume and the destination. Never the answers' history."""
    pkg = app.package or {}
    res = pkg.get("resume") or {}
    return {"application_id": app.id, "resume": {k: res.get(k) for k in ("kind", "id", "format", "name", "selected_by", "checksum")} if res.get("kind") else None,
            "destination_url": (pkg.get("destination") or {}).get("url"), "action": pkg.get("action"),
            "overrides": pkg.get("overrides") or {}, "cover_letter": app.cover_letter or None}
