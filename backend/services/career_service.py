"""Career graph core: candidate skills with evidence states, job requirements, gaps, the career snapshot and the
single next step.

Truthfulness rules:
* A skill's state only moves up with evidence. Courses and practice can reach `practising`; a project link reaches
  `project_evidence`; only employment evidence reaches `professional_experience`. `interview_ready` is the
  candidate's own affirmation on top of project or professional evidence.
* Gaps come from the requirements of jobs in the candidate's own feed, weighted by how relevant those jobs are and
  by rejections the candidate recorded. A gap closes only when the skill reaches project evidence or better.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import (Application, CandidateProfile, CandidateSkill, Gap, Interview, Job, JobPreference, JobRequirement,
                            MatchHistory, ResumeVersion, SkillEvidence, User, UserJob, VisaWatch, utcnow)
from backend.models.career import EVIDENCE_TYPES, SKILL_STATES
from backend.services import platform_service, resume_service

STATE_RANK = {s: i for i, s in enumerate(SKILL_STATES)}
CLOSING_STATE = "project_evidence"
# Highest state each kind of evidence can justify on its own.
EVIDENCE_CEILING = {"course": "learning", "certificate": "practising", "practice": "practising", "assessment": "practising",
                    "project": "project_evidence", "publication": "project_evidence", "employment": "professional_experience",
                    "other": "learning"}
STATE_LABELS = {"aware": "Aware", "learning": "Learning", "practising": "Practising", "project_evidence": "Project evidence",
                "professional_experience": "Professional experience", "interview_ready": "Interview ready"}


def _canon(settings: BackendSettings, name: str) -> str:
    c = resume_service.taxonomy(settings).canonical(name)
    return (c or name).strip()


# ---------------- skills & evidence ----------------

MAX_SKILL_NAME = 60


def sync_skills_from_profile(db: Session, settings: BackendSettings, user: User) -> int:
    """Create candidate skills from the confirmed profile. A skill named in a job's bullets starts at
    professional_experience, in a project at project_evidence, otherwise at aware. Never downgrades."""
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    conf = (prof.confirmed_profile if prof else None) or {}
    if not conf:
        return 0
    tax = resume_service.taxonomy(settings)
    work_text = " ".join(b for e in conf.get("experience") or [] for b in e.get("bullets") or [])
    proj_text = " ".join(b for p in conf.get("projects") or [] for b in p.get("bullets") or [])
    names = list(dict.fromkeys([*(conf.get("skills") or []), *tax.skills_in(work_text), *tax.skills_in(proj_text)]))
    existing = {s.canonical.lower(): s for s in db.execute(select(CandidateSkill).where(CandidateSkill.user_id == user.id)).scalars()}
    added = 0
    for name in names:
        name = " ".join((name or "").split())
        canonical = tax.canonical(name) or name
        # A resume line that was parsed as a "skill" (e.g. a certifications sentence) is not a skill: skip it rather
        # than fail the whole sync on the column limit.
        if not canonical or len(canonical) > MAX_SKILL_NAME or len(name) > MAX_SKILL_NAME:
            continue
        in_work = canonical in tax.skills_in(work_text) or name.lower() in work_text.lower()
        in_proj = canonical in tax.skills_in(proj_text) or name.lower() in proj_text.lower()
        state = "professional_experience" if in_work else "project_evidence" if in_proj else "aware"
        row = existing.get(canonical.lower())
        if row is None:
            row = CandidateSkill(user_id=user.id, name=name, canonical=canonical, state=state, source="resume_parse",
                                 verified=True, verified_at=utcnow(), confidence=0.9 if in_work or in_proj else 0.6)
            db.add(row)
            existing[canonical.lower()] = row
            added += 1
        elif STATE_RANK[state] > STATE_RANK[row.state]:
            row.state = state
    db.commit()
    return added


def list_skills(db: Session, user: User) -> list[CandidateSkill]:
    return list(db.execute(select(CandidateSkill).where(CandidateSkill.user_id == user.id).order_by(CandidateSkill.canonical)).scalars())


def owned_skill(db: Session, user: User, skill_id: int) -> CandidateSkill:
    s = db.execute(select(CandidateSkill).where(CandidateSkill.id == skill_id, CandidateSkill.user_id == user.id)).scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill not found")
    return s


def add_skill(db: Session, settings: BackendSettings, user: User, name: str, proficiency: str | None, years: float | None) -> CandidateSkill:
    canonical = _canon(settings, name)
    row = db.execute(select(CandidateSkill).where(CandidateSkill.user_id == user.id, CandidateSkill.canonical == canonical)).scalar_one_or_none()
    if row is None:
        row = CandidateSkill(user_id=user.id, name=name.strip(), canonical=canonical, state="aware", source="manual")
        db.add(row)
    row.proficiency, row.years = proficiency, years
    db.commit()
    db.refresh(row)
    _refresh_gap_state(db, user, row)
    return row


def evidence_ceiling(skill: CandidateSkill) -> str:
    best = "aware"
    for ev in skill.evidence:
        cap = EVIDENCE_CEILING.get(ev.evidence_type, "learning")
        if STATE_RANK[cap] > STATE_RANK[best]:
            best = cap
    if skill.source == "resume_parse" and skill.state in ("project_evidence", "professional_experience"):
        best = skill.state if STATE_RANK[skill.state] > STATE_RANK[best] else best
    return best


def set_state(db: Session, user: User, skill: CandidateSkill, state: str) -> CandidateSkill:
    """Candidate affirms a state. It may not exceed what the evidence supports (interview_ready needs project or
    professional evidence underneath)."""
    if state not in SKILL_STATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown state")
    ceiling = evidence_ceiling(skill)
    if state == "interview_ready":
        if STATE_RANK[ceiling] < STATE_RANK["project_evidence"]:
            raise HTTPException(status.HTTP_409_CONFLICT, "Add project or work evidence before marking this skill interview-ready.")
    elif STATE_RANK[state] > STATE_RANK[ceiling] and STATE_RANK[state] > STATE_RANK["learning"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"'{STATE_LABELS[state]}' needs evidence. Your evidence supports up to '{STATE_LABELS[ceiling]}'.")
    skill.state = state
    db.commit()
    _refresh_gap_state(db, user, skill)
    return skill


def add_evidence(db: Session, user: User, skill: CandidateSkill, evidence_type: str, title: str, url: str | None,
                 description: str | None, occurred_on, learning_session_id: int | None = None) -> SkillEvidence:
    if evidence_type not in EVIDENCE_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown evidence type")
    ev = SkillEvidence(user_id=user.id, skill_id=skill.id, evidence_type=evidence_type, title=title.strip(), url=url,
                       description=description, occurred_on=occurred_on, learning_session_id=learning_session_id,
                       source="learning_session" if learning_session_id else "manual", verified=False)
    db.add(ev)
    db.flush()
    db.refresh(skill)
    cap = evidence_ceiling(skill)
    if STATE_RANK[cap] > STATE_RANK[skill.state]:  # evidence moves the state up automatically, never down
        skill.state = cap
    db.commit()
    _refresh_gap_state(db, user, skill)
    return ev


def evidenced_skills(db: Session, user_id: int) -> list[str]:
    """Skills the candidate has shown with project or professional evidence: these count in job scoring even when the
    confirmed resume profile doesn't list them. Course/practice evidence alone never does."""
    rows = db.execute(select(CandidateSkill).where(CandidateSkill.user_id == user_id)).scalars()
    return [s.canonical for s in rows if STATE_RANK.get(s.state, 0) >= STATE_RANK[CLOSING_STATE]]


def rescore_after_evidence(db: Session, settings: BackendSettings, user: User, canonical: str, reason: str) -> list[dict[str, Any]]:
    """Re-score the jobs that ask for this skill and record each before/after change (MatchHistory) with the reason."""
    from backend.services import matching_service
    try:
        um = matching_service.UserMatcher(db, settings, user, use_llm=False)
    except HTTPException:
        return []
    key = canonical.lower()
    rows = db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.status.in_(("new", "shortlisted")))).unique().scalars().all()
    changes = []
    for uj in rows:
        asked = {x.lower() for x in [*(uj.missing_skills or []), *(uj.matching_skills or []), *(uj.job.required_skills or []), *(uj.job.preferred_skills or [])]}
        if key not in asked:
            continue
        before = uj.match_score
        um.apply(uj)
        after = uj.match_score
        if before is not None and after is not None and abs(after - before) < 0.5:
            continue
        db.add(MatchHistory(user_id=user.id, user_job_id=uj.id, score_version=uj.score_version or "", old_score=before,
                            new_score=after, reason=reason[:300]))
        changes.append({"user_job_id": uj.id, "title": uj.job.title, "company": uj.job.company, "old_score": before, "new_score": after})
    db.commit()
    return changes


def match_history(db: Session, user: User, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(select(MatchHistory, UserJob).join(UserJob, UserJob.id == MatchHistory.user_job_id)
                      .where(MatchHistory.user_id == user.id).order_by(MatchHistory.created_at.desc(), MatchHistory.id.desc()).limit(limit)).all()
    return [{"id": h.id, "user_job_id": h.user_job_id, "title": uj.job.title, "company": uj.job.company, "old_score": h.old_score,
             "new_score": h.new_score, "reason": h.reason, "score_version": h.score_version, "created_at": h.created_at} for h, uj in rows]


def delete_evidence(db: Session, user: User, evidence_id: int) -> None:
    ev = db.execute(select(SkillEvidence).where(SkillEvidence.id == evidence_id, SkillEvidence.user_id == user.id)).scalar_one_or_none()
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evidence not found")
    skill = ev.skill
    db.delete(ev)
    db.flush()
    db.refresh(skill)
    cap = evidence_ceiling(skill)
    if STATE_RANK[skill.state] > max(STATE_RANK[cap], STATE_RANK["learning"]) and skill.state != "interview_ready":
        skill.state = cap
    if skill.state == "interview_ready" and STATE_RANK[cap] < STATE_RANK["project_evidence"]:
        skill.state = cap
    db.commit()
    _refresh_gap_state(db, user, skill)


# ---------------- job requirements ----------------

_YEARS = re.compile(r"(\d+)\s*\+?\s*(?:-|to)?\s*\d*\s*(?:years|yrs)", re.I)


def extract_requirements(db: Session, settings: BackendSettings, job: Job) -> list[JobRequirement]:
    """Structured requirements from the job record (rules-1 extractor). Idempotent per job."""
    existing = {(r.kind, r.canonical) for r in db.execute(select(JobRequirement).where(JobRequirement.job_id == job.id)).scalars()}
    tax = resume_service.taxonomy(settings)
    rows: list[tuple[str, str, str, str, bool, float | None]] = []
    for s in job.required_skills or []:
        rows.append(("skill", s, tax.canonical(s) or s, "required", False, None))
    for s in job.preferred_skills or []:
        if s not in (job.required_skills or []):
            rows.append(("skill", s, tax.canonical(s) or s, "preferred", False, None))
    for q in job.education_requirements or []:
        rows.append(("education", q, q, "required" if q in (job.mandatory_qualifications or []) else "preferred",
                     q in (job.mandatory_qualifications or []), None))
    if job.experience_min is not None:
        rows.append(("experience", job.experience_required or f"{job.experience_min:g}+ years", "years", "required", False, job.experience_min))
    out = []
    for kind, text, canonical, importance, hard, years in rows:
        if (kind, canonical) in existing:
            continue
        existing.add((kind, canonical))
        r = JobRequirement(job_id=job.id, kind=kind, text=text[:500], canonical=canonical[:120], importance=importance, hard=hard, years=years)
        db.add(r)
        out.append(r)
    db.commit()
    return list(db.execute(select(JobRequirement).where(JobRequirement.job_id == job.id).order_by(JobRequirement.id)).scalars())


# ---------------- gaps ----------------

def generate_gaps(db: Session, settings: BackendSettings, user: User) -> list[Gap]:
    """gap_generation: aggregate missing required skills over the candidate's relevant jobs. Idempotent."""
    sync_skills_from_profile(db, settings, user)
    tax = resume_service.taxonomy(settings)
    skills = {s.canonical.lower(): s for s in list_skills(db, user)}
    ujs = db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.status.in_(("new", "shortlisted", "applied")),
                                           UserJob.match_score.is_not(None)).order_by(UserJob.match_score.desc()).limit(60)).scalars().all()
    rejected = db.execute(select(Application.job_id).where(Application.user_id == user.id, Application.stage == "rejected")).scalars().all()
    rejected_jobs = set(rejected)
    weight: dict[str, float] = defaultdict(float)
    jobs_for: dict[str, list[int]] = defaultdict(list)
    names: dict[str, str] = {}
    rej_count: dict[str, int] = defaultdict(int)
    for uj in ujs:
        w = max(0.2, (uj.match_score or 0) / 100)
        for raw in uj.missing_skills or []:
            c = tax.canonical(raw) or raw
            key = c.lower()
            names.setdefault(key, c)
            weight[key] += w
            jobs_for[key].append(uj.id)
            if uj.job_id in rejected_jobs:
                rej_count[key] += 1
    existing = {g.canonical.lower(): g for g in db.execute(select(Gap).where(Gap.user_id == user.id)).scalars()}
    total = max(1, len(ujs))
    for key, w in weight.items():
        share = len(jobs_for[key]) / total
        score = round(w + 1.5 * rej_count[key], 3)
        sev = "high" if share >= 0.4 or rej_count[key] >= 2 else "medium" if share >= 0.15 else "low"
        skill = skills.get(key)
        g = existing.get(key)
        if g is None:
            g = Gap(user_id=user.id, skill=names[key], canonical=names[key])
            db.add(g)
            existing[key] = g
        g.severity, g.score, g.job_count, g.rejection_count = sev, score, len(jobs_for[key]), rej_count[key]
        g.job_ids = jobs_for[key][:50]
        g.evidence_state = skill.state if skill else None
        g.explanation = (f"Asked for by {len(jobs_for[key])} of your {total} most relevant jobs"
                         + (f", and missing in {rej_count[key]} application(s) that were rejected" if rej_count[key] else "")
                         + (f". Your current evidence: {STATE_LABELS[skill.state]}." if skill else ". You have no recorded evidence yet."))
        g.next_action = _next_action(skill)
        if skill and STATE_RANK[skill.state] >= STATE_RANK[CLOSING_STATE]:
            if g.status != "closed":
                g.status, g.closed_at = "closed", utcnow()
        elif g.status == "closed":
            g.status, g.closed_at = "open", None
    for key, g in existing.items():  # no longer asked for anywhere: keep history, mark low
        if key not in weight and g.status == "open":
            g.score, g.severity, g.job_count = 0.0, "low", 0
    db.commit()
    return list_gaps(db, user)


def _next_action(skill: CandidateSkill | None) -> str:
    if skill is None or skill.state == "aware":
        return "Start a short learning resource to cover the basics."
    if skill.state == "learning":
        return "Practise it: finish an exercise or small task and record it."
    if skill.state == "practising":
        return "Turn practice into evidence: build a small project and add its link."
    return "Prepare to talk about it: practise interview questions on this skill."


def _refresh_gap_state(db: Session, user: User, skill: CandidateSkill) -> None:
    g = db.execute(select(Gap).where(Gap.user_id == user.id, Gap.canonical == skill.canonical)).scalar_one_or_none()
    if g is None:
        return
    g.evidence_state = skill.state
    g.next_action = _next_action(skill)
    if STATE_RANK[skill.state] >= STATE_RANK[CLOSING_STATE]:
        if g.status != "closed":
            g.status, g.closed_at = "closed", utcnow()
    elif g.status == "closed":
        g.status, g.closed_at = "open", None
    elif g.status == "open" and skill.state in ("learning", "practising"):
        g.status = "in_progress"
    db.commit()


def list_gaps(db: Session, user: User, include_closed: bool = True) -> list[Gap]:
    q = select(Gap).where(Gap.user_id == user.id)
    if not include_closed:
        q = q.where(Gap.status.in_(("open", "in_progress")))
    return list(db.execute(q.order_by(Gap.score.desc(), Gap.id)).scalars())


def best_gap(db: Session, user: User) -> tuple[Gap | None, list[Gap]]:
    open_ = [g for g in list_gaps(db, user, include_closed=False) if g.job_count > 0]
    return (open_[0] if open_ else None), open_[1:4]


def mark_gap_viewed(db: Session, user: User, gap: Gap) -> None:
    if gap.first_viewed_at is None:
        gap.first_viewed_at = utcnow()
        platform_service.track(db, user.id, "gap_viewed", gap_id=gap.id, severity=gap.severity)
        db.commit()


def job_gaps(db: Session, settings: BackendSettings, user: User, uj: UserJob) -> list[dict[str, Any]]:
    tax = resume_service.taxonomy(settings)
    skills = {s.canonical.lower(): s for s in list_skills(db, user)}
    out = []
    reqs = {r.canonical.lower(): r for r in extract_requirements(db, settings, uj.job) if r.kind == "skill"}
    for raw in uj.missing_skills or []:
        c = tax.canonical(raw) or raw
        s = skills.get(c.lower())
        r = reqs.get(c.lower())
        out.append({"skill": c, "importance": r.importance if r else "required", "evidence_state": s.state if s else None,
                    "severity": "high" if (r is None or r.importance == "required") else "medium", "next_action": _next_action(s)})
    return out


# ---------------- snapshot & next step ----------------

def profile_completeness(db: Session, user: User) -> dict[str, Any]:
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    conf = (prof.confirmed_profile if prof else None) or {}
    prefs = db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none()
    checks = {
        "name": bool(conf.get("full_name")), "contact": bool(conf.get("email") or conf.get("phone")),
        "headline": bool(conf.get("headline")), "summary": bool(conf.get("summary")),
        "skills": len(conf.get("skills") or []) >= 5, "experience_or_projects": bool(conf.get("experience") or conf.get("projects")),
        "education": bool(conf.get("education")), "target_roles": bool(prefs and prefs.job_titles),
        "locations": bool(prefs and prefs.locations), "search_mode": bool(prefs and prefs.search_mode),
    }
    return {"percent": round(100 * sum(checks.values()) / len(checks)), "missing": [k for k, v in checks.items() if not v]}


def snapshot(db: Session, settings: BackendSettings, user: User) -> dict[str, Any]:
    comp = profile_completeness(db, user)
    top = db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.status.in_(("new", "shortlisted")),
                                           UserJob.match_score.is_not(None)).order_by(UserJob.match_score.desc()).limit(30)).scalars().all()
    top = sorted(top, key=lambda u: (u.eligibility == "fail", -(u.match_score or 0)))[:3]  # eligible jobs first
    gap, alternatives = best_gap(db, user)
    if gap is None:
        try:
            generate_gaps(db, settings, user)
            gap, alternatives = best_gap(db, user)
        except Exception:  # profile not confirmed yet etc.
            pass
    apps = db.execute(select(Application).where(Application.user_id == user.id)).scalars().all()
    submitted = [a for a in apps if a.status == "SUBMITTED"]
    upcoming = db.execute(select(Interview).where(Interview.user_id == user.id, Interview.scheduled_at >= utcnow(),
                                                  Interview.scheduled_at <= utcnow() + timedelta(days=14))).scalars().all()
    has_resume = db.execute(select(ResumeVersion.id).where(ResumeVersion.user_id == user.id)).first() is not None
    prefs = db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none()
    intl = bool(prefs and prefs.search_mode in ("international", "both"))
    watching = db.execute(select(VisaWatch.id).where(VisaWatch.user_id == user.id)).first() is not None
    stage = "interviewing" if upcoming or any(a.stage in ("interview", "offer") for a in submitted) else \
        "applying" if submitted else "exploring" if top else "starting"
    return {
        "stage": stage, "profile_completeness": comp,
        "top_matches": [{"user_job_id": u.id, "title": u.job.title, "company": u.job.company, "score": u.match_score,
                         "eligibility": u.eligibility, "score_version": u.score_version} for u in top],
        "top_gap": _gap_out(gap) if gap else None, "alternative_gaps": [_gap_out(g) for g in alternatives],
        "counts": {"applications_submitted": len(submitted), "applications_in_progress": len(apps) - len(submitted),
                   "upcoming_interviews": len(upcoming)},
        "show": {"tracker": bool(apps), "interview_prep": bool(upcoming) or any(a.stage == "interview" for a in submitted),
                 "learning": gap is not None, "international": intl, "reflection": bool(submitted)},
        "next_step": _next_step(comp, top, gap, submitted, upcoming, has_resume, intl, watching),
    }


def _gap_out(g: Gap) -> dict[str, Any]:
    return {"id": g.id, "skill": g.skill, "severity": g.severity, "explanation": g.explanation, "next_action": g.next_action,
            "evidence_state": g.evidence_state, "status": g.status, "job_count": g.job_count, "rejection_count": g.rejection_count}


MISSING_LABELS = {"name": "your name", "contact": "contact details", "headline": "a headline", "summary": "a summary",
                  "skills": "at least five skills", "experience_or_projects": "work experience or projects",
                  "education": "education", "target_roles": "target roles", "locations": "preferred locations",
                  "search_mode": "where you want to work"}


def _next_step(comp, top, gap, submitted, upcoming, has_resume, intl, watching) -> dict[str, str]:
    if comp["percent"] < 50:
        missing = [MISSING_LABELS.get(k, k) for k in comp["missing"][:3]]
        return {"kind": "profile", "label": "Finish your profile", "link": "/settings?tab=profile",
                "reason": "Matches and resumes are built from your profile. Still to add: " + ", ".join(missing) + "."}
    if upcoming:
        return {"kind": "interview_prep", "label": "Prepare for your interview", "link": "/interview-prep",
                "reason": f"You have {len(upcoming)} interview(s) in the next 14 days."}
    if not has_resume:
        return {"kind": "build_resume", "label": "Build your resume", "link": "/studio",
                "reason": "Create an editable resume from your profile so each application uses a tracked version."}
    good = [u for u in top if u.eligibility != "fail" and (u.match_score or 0) >= 60]
    if good:
        u = good[0]
        return {"kind": "apply", "label": f"Apply: {u.job.title} at {u.job.company}", "link": f"/discover?job={u.id}",
                "reason": f"Your strongest current match ({u.match_score:.0f}/100) with no application yet."}
    if gap is not None:
        return {"kind": "learn", "label": f"Close a gap: {gap.skill}", "link": "/career",
                "reason": gap.explanation}
    if intl and not watching:
        return {"kind": "international", "label": "Explore international options", "link": "/international",
                "reason": "You said you are open to working abroad; see which routes fit your profile."}
    return {"kind": "discover", "label": "Find more matching jobs", "link": "/discover",
            "reason": "Review new matches from today's discovery run."}


# ---------------- sponsorship signal ----------------

_SPONSOR_YES = re.compile(r"\b(visa sponsorship (is )?(available|provided|offered)|we (can|will|do) sponsor|sponsorship available|"
                          r"will sponsor (a |your )?(work )?visa)\b", re.I)
_SPONSOR_NO = re.compile(r"\b(no (visa )?sponsorship|(unable|not able) to sponsor|does not (offer|provide) (visa )?sponsorship|"
                         r"must (already )?(have|hold) (the )?right to work|without (the need for )?sponsorship)\b", re.I)
_RELOCATION = re.compile(r"\b(relocation (assistance|support|package)|we (help|support) (with )?relocation)\b", re.I)


SENIORITY_LEVELS = ("intern", "entry", "junior", "mid", "senior", "lead", "manager", "director")
_SENIORITY_TITLE = [  # first match wins; checked against the job title only
    ("director", r"\b(director|head of|vice president|vp|chief|cxo|cto|cfo|coo)\b"),
    ("intern", r"\b(intern|internship|trainee|apprentice)\b"),
    ("manager", r"\b(manager|mgr)\b"),
    ("lead", r"\b(lead|principal|staff|architect)\b"),
    ("senior", r"\b(senior|sr\.?|iii|iv)\b"),
    ("junior", r"\b(junior|jr\.?)\b"),
    ("entry", r"\b(entry[- ]level|graduate|fresher|new grad)\b"),
    ("mid", r"\b(mid[- ]level|ii)\b"),
]


def infer_seniority(title: str | None, experience_min: float | None) -> str | None:
    """Seniority from the title, else from a *stated* minimum experience. Unknown stays None (never guessed as entry)."""
    t = (title or "").lower()
    for level, rx in _SENIORITY_TITLE:
        if re.search(rx, t):
            return level
    if experience_min is None:
        return None
    if experience_min >= 8:
        return "lead"
    if experience_min >= 5:
        return "senior"
    if experience_min >= 2:
        return "mid"
    return "entry" if experience_min > 0 else None


def sponsorship_signal(text: str | None) -> tuple[str, str | None]:
    """verified (posting says sponsorship is offered) | none (posting says it isn't) | inferred | unknown."""
    if not text:
        return "unknown", None
    if m := _SPONSOR_NO.search(text):
        return "none", f'posting says: "{m.group(0)}"'
    if m := _SPONSOR_YES.search(text):
        return "verified", f'posting says: "{m.group(0)}"'
    if m := _RELOCATION.search(text):
        return "inferred", f'relocation mentioned ("{m.group(0)}"), sponsorship not stated'
    return "unknown", None
