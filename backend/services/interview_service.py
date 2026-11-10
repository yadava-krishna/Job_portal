"""Interview preparation, practice, post-interview feedback and rejection intelligence.

Questions are generated from the job's own requirements and responsibilities (not a generic dump). Feedback on
practice answers is rule-based and explains itself (structure, specifics, length, relevance). Reference insights
are links the candidate opens themselves (Glassdoor, Reddit, AmbitionBox, Indeed search pages) plus notes they
save with attribution; JobPilot does not scrape those sites.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import quote_plus

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import Application, Interview, InterviewInsight, InterviewPractice, ResumeVersion, User, UserJob, utcnow
from backend.services import platform_service
from intelligence.jd_analyzer import JDAnalyzer

REJECTION_REASONS = {
    "skills_gap": "Missing skills or experience the role needed",
    "experience_level": "Seniority / years of experience",
    "eligibility": "Work authorisation, location or notice period",
    "salary": "Salary expectations",
    "interview_performance": "Interview performance",
    "position_filled": "Position filled or closed",
    "culture_fit": "Team / culture fit (as stated by employer)",
    "no_reason_given": "No reason given",
    "other": "Other",
}
INSIGHT_SOURCES = ("glassdoor", "reddit", "ambitionbox", "indeed", "other", "own")


def owned_user_job(db: Session, user: User, user_job_id: int) -> UserJob:
    uj = db.execute(select(UserJob).where(UserJob.id == user_job_id, UserJob.user_id == user.id)).scalar_one_or_none()
    if uj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return uj


def reference_links(company: str, role: str) -> list[dict[str, str]]:
    q = quote_plus(f"{company} {role} interview questions")
    c = quote_plus(company)
    return [
        {"source": "glassdoor", "label": f"Glassdoor: {company} interviews", "url": f"https://www.glassdoor.co.in/Search/results.htm?keyword={c}%20interview"},
        {"source": "ambitionbox", "label": f"AmbitionBox: {company} interviews", "url": f"https://www.ambitionbox.com/search?CompanySearch={c}"},
        {"source": "reddit", "label": "Reddit discussions", "url": f"https://www.reddit.com/search/?q={q}"},
        {"source": "indeed", "label": f"Indeed: {company} interviews", "url": f"https://in.indeed.com/cmp/{quote_plus(company.replace(' ', '-'))}/interviews"},
    ]


def generate_questions(settings: BackendSettings, db: Session, user: User, uj: UserJob) -> list[dict[str, Any]]:
    job = uj.job
    from backend.services import resume_service

    analysis = JDAnalyzer(resume_service.taxonomy(settings)).analyze(job.description or "")
    skills = list(dict.fromkeys([*(job.required_skills or []), *(job.preferred_skills or [])]))[:6]
    missing = set(uj.missing_skills or [])
    qs: list[dict[str, Any]] = []

    def add(kind: str, competency: str, text: str, why: str):
        qs.append({"id": f"q{len(qs) + 1}", "kind": kind, "competency": competency, "question": text, "why": why})

    for s in skills:
        if s in missing:
            add("technical", s, f"This role asks for {s}. How would you approach a typical {s} task here, and how are you building this skill?",
                f"{s} is required and not yet in your profile: expect a probing question.")
        else:
            add("technical", s, f"Walk me through a specific time you used {s}: the situation, what you did, and the result.",
                f"{s} is listed in the job and in your profile.")
    for line in (analysis.responsibilities or [])[:4]:
        duty = line.strip().rstrip(".")
        duty = duty[0].lower() + duty[1:] if duty else duty
        add("behavioural", "responsibility", f"Tell me about a time you had to {duty}.", "Taken from the job's responsibilities.")
    add("behavioural", "problem solving", "Describe a mistake or exception you found in your work. How did you find it and what did you change?",
        "Common for detail-oriented roles; prepare a STAR example.")
    add("motivation", "role fit", f"Why {job.company} and why this {job.title} role?", "Asked in almost every first round.")
    if job.experience_min:
        add("screening", "experience", f"The role asks for {job.experience_required or f'{job.experience_min:g}+ years'}. Summarise your relevant experience.",
            "Screening question from the stated requirement.")
    add("screening", "logistics", "What is your notice period and expected compensation?", "Standard screening question; answer from your settings.")
    return qs


def start_practice(settings: BackendSettings, db: Session, user: User, user_job_id: int) -> InterviewPractice:
    uj = owned_user_job(db, user, user_job_id)
    app = db.execute(select(Application).where(Application.user_id == user.id, Application.job_id == uj.job_id)).scalar_one_or_none()
    p = InterviewPractice(user_id=user.id, user_job_id=uj.id, application_id=app.id if app else None,
                          title=f"{uj.job.title} at {uj.job.company}", questions=generate_questions(settings, db, user, uj))
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def owned_practice(db: Session, user: User, practice_id: int) -> InterviewPractice:
    p = db.execute(select(InterviewPractice).where(InterviewPractice.id == practice_id, InterviewPractice.user_id == user.id)).scalar_one_or_none()
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Practice session not found")
    return p


_RESULT = re.compile(r"\b(result|outcome|reduced|increased|improved|saved|cut|grew|achieved|so that|which led)\b", re.I)
_ACTION = re.compile(r"\b(i (did|built|created|led|analysed|analyzed|reconciled|fixed|wrote|set up|handled|resolved|automated|prepared))\b", re.I)
_NUMBER = re.compile(r"\d")


def answer_feedback(question: dict[str, Any], answer: str) -> dict[str, Any]:
    words = len(answer.split())
    notes, score = [], 0
    if words < 40:
        notes.append("Short answer: aim for 60-180 words so there is room for situation, action and result.")
    elif words > 260:
        notes.append("Long answer: trim to the essentials; interviewers lose the thread after ~2 minutes.")
    else:
        score += 1
    if _ACTION.search(answer):
        score += 1
    else:
        notes.append("Say what *you* did (\"I reconciled…\", \"I built…\"), not only what the team did.")
    if _RESULT.search(answer):
        score += 1
    else:
        notes.append("End with the result: what changed because of your action?")
    if _NUMBER.search(answer):
        score += 1
    else:
        notes.append("Add a concrete detail you can stand behind (a volume, a time saved, a count). Only real numbers.")
    comp = question.get("competency", "")
    if comp and comp not in ("responsibility", "problem solving", "role fit", "experience", "logistics") and comp.lower() not in answer.lower():
        notes.append(f"Mention {comp} explicitly: the question is about it.")
    else:
        score += 1
    return {"question_id": question["id"], "score": score, "out_of": 5, "notes": notes or ["Clear, specific and structured."],
            "method": "rule_based"}


def save_answer(db: Session, user: User, practice_id: int, question_id: str, answer: str, self_rating: int | None) -> InterviewPractice:
    p = owned_practice(db, user, practice_id)
    q = next((q for q in p.questions if q["id"] == question_id), None)
    if q is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    answers = dict(p.answers or {})
    answers[question_id] = {"answer": answer.strip()[:6000], "self_rating": self_rating, "at": utcnow().isoformat()}
    fb = [f for f in (p.feedback or []) if f["question_id"] != question_id] + [answer_feedback(q, answer)]
    p.answers, p.feedback = answers, fb
    if len(answers) >= len(p.questions) and p.status != "completed":
        p.status, p.completed_at = "completed", utcnow()
    db.commit()
    db.refresh(p)
    return p


def add_insight(db: Session, user: User, data: dict[str, Any]) -> InterviewInsight:
    if data.get("source") not in INSIGHT_SOURCES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown source")
    ins = InterviewInsight(user_id=user.id, **{k: data.get(k) for k in ("company", "role", "source", "url", "question", "note")})
    db.add(ins)
    db.commit()
    db.refresh(ins)
    return ins


# ---------------- post-interview feedback ----------------

def record_feedback(db: Session, user: User, interview_id: int, data: dict[str, Any]) -> Interview:
    iv = db.execute(select(Interview).where(Interview.id == interview_id, Interview.user_id == user.id)).scalar_one_or_none()
    if iv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview not found")
    for k in ("interview_type", "strengths", "weaknesses", "candidate_feedback", "outcome"):
        if k in data and data[k] is not None:
            setattr(iv, k, data[k])
    if "topics" in data and data["topics"] is not None:
        iv.topics = [t.strip()[:80] for t in data["topics"] if t.strip()][:20]
    iv.feedback_at = utcnow()
    platform_service.track(db, user.id, "interview_recorded", interview_id=iv.id, kind="feedback", outcome=iv.outcome)
    db.commit()
    return iv


# ---------------- rejection intelligence ----------------

def record_rejection(db: Session, user: User, app: Application, reason: str, detail: str | None, known: bool) -> Application:
    from backend.services import application_service

    if reason not in REJECTION_REASONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown rejection reason")
    if app.status != "SUBMITTED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only submitted applications can be rejected")
    app.rejection_reason, app.rejection_detail, app.rejection_reason_known = reason, (detail or "").strip()[:2000] or None, known
    if app.stage != "rejected":
        application_service.set_stage(db, user, app, "rejected", f"Rejected: {REJECTION_REASONS[reason]}" + (" (employer said)" if known else " (your guess)"))
    db.commit()
    return app


def funnel(db: Session, user: User) -> dict[str, Any]:
    apps = db.execute(select(Application).where(Application.user_id == user.id)).scalars().all()
    sub = [a for a in apps if a.status == "SUBMITTED"]
    reached = Counter()
    order = ["applied", "screening", "assessment", "interview", "offer"]
    for a in sub:
        stage = a.stage or "applied"
        hist = {stage}
        # an application at a later stage has passed the earlier ones
        if stage in order:
            hist |= set(order[: order.index(stage) + 1])
        if stage == "rejected":
            iv = db.execute(select(Interview.id).where(Interview.application_id == a.id)).first()
            hist |= {"applied", "interview"} if iv else {"applied"}
        for s in hist:
            reached[s] += 1
    n = len(sub)
    rate = lambda a, b: round(100 * reached[a] / reached[b], 1) if reached[b] else None  # noqa: E731
    reasons = Counter(a.rejection_reason for a in sub if a.stage == "rejected" and a.rejection_reason)
    known = sum(1 for a in sub if a.stage == "rejected" and a.rejection_reason_known)
    by_version: dict[str, dict[str, int]] = defaultdict(lambda: {"applications": 0, "interviews": 0})
    for a in sub:
        key = f"v{a.resume_version_id}" if a.resume_version_id else "uploaded resume"
        by_version[key]["applications"] += 1
        by_version[key]["interviews"] += int(reached_interview(db, a))
    names = {f"v{v.id}": v.name for v in db.execute(select(ResumeVersion).where(ResumeVersion.user_id == user.id)).scalars()}
    return {
        "counts": {"prepared": sum(1 for a in apps if a.status == "PREPARED"), "opened": sum(1 for a in apps if a.status == "OPENED"),
                   "pending": sum(1 for a in apps if a.status == "CONFIRMATION_PENDING"), "applied": n,
                   **{s: reached[s] for s in order[1:]}, "rejected": sum(1 for a in sub if a.stage == "rejected")},
        "conversion": {"application_to_screening": rate("screening", "applied"), "application_to_interview": rate("interview", "applied"),
                       "interview_to_offer": rate("offer", "interview")},
        "rejection_reasons": [{"reason": r, "label": REJECTION_REASONS[r], "count": c} for r, c in reasons.most_common()],
        "rejections_with_known_reason": known,
        "by_resume_version": [{"version": names.get(k, k), **v} for k, v in by_version.items()],
        "note": "Rates use your own recorded outcomes; with few applications they are rough indicators only." if n < 10 else None,
    }


def reached_interview(db: Session, a: Application) -> bool:
    return a.stage in ("interview", "offer") or db.execute(select(Interview.id).where(Interview.application_id == a.id)).first() is not None
