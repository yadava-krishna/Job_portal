"""AI mentor (rule-based action planner over the candidate's own career graph), weekly reflection, and the human
mentor workflow.

The planner explains every diagnosis with the observations behind it, a confidence level and its limitations.
It never shames, and with little data it says so instead of guessing. Human mentors see a candidate only through
an active, candidate-granted assignment, only the scopes granted, and every view is audited.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import (Application, AuditLog, Gap, LearningSession, MentorAction, MentorAssignment,
                            MentorNote, MentorSession, Reflection, ResumeVersion, User, utcnow)
from backend.services import career_service, interview_service, platform_service

SCOPES = ("profile", "funnel", "gaps", "actions", "applications")


def _week_start(d: date | None = None) -> date:
    d = d or utcnow().date()
    return d - timedelta(days=d.weekday())


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=utcnow().tzinfo)


def diagnose(db: Session, user: User) -> list[dict[str, Any]]:
    since = utcnow() - timedelta(days=60)
    apps = [a for a in db.execute(select(Application).where(Application.user_id == user.id, Application.status == "SUBMITTED")).scalars()
            if a.submitted_at and _aware(a.submitted_at) >= since]
    n = len(apps)
    interviews = sum(1 for a in apps if interview_service.reached_interview(db, a))
    offers = sum(1 for a in apps if a.stage == "offer")
    learning = [s for s in db.execute(select(LearningSession).where(LearningSession.user_id == user.id)).scalars()
                if _aware(s.started_at) >= utcnow() - timedelta(days=30)]
    learn_min = sum(s.active_seconds for s in learning) // 60
    recent_apps = sum(1 for a in apps if _aware(a.submitted_at) >= utcnow() - timedelta(days=30))
    repeated = db.execute(select(Gap).where(Gap.user_id == user.id, Gap.rejection_count >= 2, Gap.status != "closed")
                          .order_by(Gap.rejection_count.desc())).scalars().all()
    out: list[dict[str, Any]] = []

    def conf(sample: int) -> str:
        return "high" if sample >= 20 else "medium" if sample >= 8 else "low"

    if n >= 8 and interviews / n < 0.1:
        out.append({"rule": "many_apps_few_interviews", "title": "Many applications, few interviews",
                    "observations": [f"{n} applications in the last 60 days", f"{interviews} reached an interview ({100 * interviews / n:.0f}%)"],
                    "diagnosis": "The bottleneck is before the interview: targeting, eligibility or how your profile reads.",
                    "actions": [("Review the eligibility of your last 5 applications (location, years, authorisation)", "high", 3),
                                ("Run the resume check against your top job and fix every warning", "high", 5),
                                ("Apply only to jobs scoring 70+ with eligibility 'pass' for the next two weeks", "medium", 14)],
                    "confidence": conf(n), "limitations": "Employers rarely say why they don't reply; this is a pattern, not a verdict."})
    if interviews >= 3 and offers == 0:
        out.append({"rule": "interviews_no_offers", "title": "Interviews but no offers yet",
                    "observations": [f"{interviews} interview(s) in the last 60 days", "0 offers"],
                    "diagnosis": "Getting shortlisted works; interview readiness is where to focus.",
                    "actions": [("Do one practice session for your next interview and act on the feedback", "high", 3),
                                ("Write down what went well and badly after each interview (Applications > interview feedback)", "medium", 7)],
                    "confidence": conf(interviews), "limitations": "Offers also depend on competition and budgets you can't see."})
    for g in repeated[:2]:
        out.append({"rule": f"repeated_gap:{g.canonical}", "title": f"{g.skill} keeps coming up in rejections",
                    "observations": [f"Missing in {g.rejection_count} rejected application(s)", f"Asked for by {g.job_count} relevant jobs"],
                    "diagnosis": f"Evidence for {g.skill} is the most valuable thing to build next.",
                    "actions": [(f"Close the {g.skill} gap: {g.next_action}", "high", 14)],
                    "confidence": conf(g.rejection_count * 4), "limitations": "Based on job requirements, not on employers' stated reasons."})
    if learn_min >= 120 and recent_apps <= 1:
        out.append({"rule": "learning_without_applying", "title": "Lots of learning, few applications",
                    "observations": [f"{learn_min} active learning minutes in 30 days", f"{recent_apps} application(s) in 30 days"],
                    "diagnosis": "You're building skills; now put them to work. Applying is how you find out what matters.",
                    "actions": [("Apply to 3 jobs that match the skills you've been learning", "high", 7)],
                    "confidence": "medium", "limitations": "Fine to ignore if you are deliberately preparing before applying."})
    by_version: dict[int | None, list[Application]] = {}
    for a in apps:
        by_version.setdefault(a.resume_version_id, []).append(a)
    if len(by_version) >= 2:
        rates = {v: (sum(interview_service.reached_interview(db, a) for a in al) / len(al), len(al)) for v, al in by_version.items() if len(al) >= 3}
        if len(rates) >= 2:
            best = max(rates, key=lambda v: rates[v][0])
            worst = min(rates, key=lambda v: rates[v][0])
            if rates[best][0] - rates[worst][0] >= 0.2:
                name = db.get(ResumeVersion, best).name if best else "your uploaded resume"
                out.append({"rule": "resume_version_better", "title": f"'{name}' gets more interviews",
                            "observations": [f"{rates[best][0] * 100:.0f}% interview rate over {rates[best][1]} applications",
                                             f"vs {rates[worst][0] * 100:.0f}% for another version"],
                            "diagnosis": "Keep using the better-performing version and look at what's different about it.",
                            "actions": [(f"Use '{name}' as the base for your next applications", "medium", 7)],
                            "confidence": conf(min(r[1] for r in rates.values()) * 3),
                            "limitations": "Small samples: different jobs, not only the resume, differ between groups."})
    if not out:
        out.append({"rule": "not_enough_data" if n < 5 else "on_track", "title": "Not enough data for a diagnosis yet" if n < 5 else "No clear bottleneck",
                    "observations": [f"{n} application(s) and {interviews} interview(s) in the last 60 days"],
                    "diagnosis": "Keep going: patterns become visible after about 8 applications." if n < 5 else "Your funnel looks balanced; keep your weekly rhythm.",
                    "actions": [], "confidence": "low", "limitations": "Diagnoses need more outcomes to be meaningful."})
    return out


def plan(db: Session, settings: BackendSettings, user: User) -> dict[str, Any]:
    """GET /mentor/plan: diagnoses + open actions. New rule actions are added once (deduplicated by rule)."""
    diags = diagnose(db, user)
    # Don't re-suggest an action that is open, or that the candidate finished or dismissed in the last 30 days.
    recent = utcnow() - timedelta(days=30)
    open_rules = {a.rule for a in db.execute(select(MentorAction).where(MentorAction.user_id == user.id, MentorAction.rule.is_not(None)))
                  .scalars() if (a.completed_at is None and a.dismissed_at is None)
                  or (a.completed_at and _aware(a.completed_at) >= recent) or (a.dismissed_at and _aware(a.dismissed_at) >= recent)}
    for d in diags:
        for i, (title, prio, days) in enumerate(d["actions"]):
            rule = f"{d['rule']}#{i}"
            if rule not in open_rules:
                db.add(MentorAction(user_id=user.id, title=title[:300], reason=d["diagnosis"], priority=prio,
                                    due_on=utcnow().date() + timedelta(days=days), source="ai_mentor", rule=rule))
    db.commit()
    snap = career_service.snapshot(db, settings, user)
    last = db.execute(select(Reflection).where(Reflection.user_id == user.id).order_by(Reflection.week_start.desc())).scalars().first()
    return {"diagnoses": [{k: v for k, v in d.items() if k != "actions"} | {"suggested_actions": [a[0] for a in d["actions"]]} for d in diags],
            "actions": [action_out(a) for a in actions(db, user)], "next_step": snap["next_step"],
            "reflection_due": last is None or last.week_start < _week_start(),
            "last_reflection": reflection_out(last) if last else None,
            "method": "rule_based", "note": "Suggestions come from your own recorded activity. You decide what to do."}


def actions(db: Session, user: User, include_done: bool = False) -> list[MentorAction]:
    q = select(MentorAction).where(MentorAction.user_id == user.id, MentorAction.dismissed_at.is_(None))
    if not include_done:
        q = q.where(MentorAction.completed_at.is_(None))
    return list(db.execute(q.order_by(MentorAction.due_on.asc().nullslast(), MentorAction.id)).scalars())


def action_out(a: MentorAction) -> dict[str, Any]:
    return {"id": a.id, "title": a.title, "reason": a.reason, "priority": a.priority, "due_on": a.due_on, "source": a.source,
            "completed_at": a.completed_at, "created_at": a.created_at}


def owned_action(db: Session, user: User, action_id: int) -> MentorAction:
    a = db.execute(select(MentorAction).where(MentorAction.id == action_id, MentorAction.user_id == user.id)).scalar_one_or_none()
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Action not found")
    return a


def add_action(db: Session, user: User, title: str, reason: str, priority: str, due_on, source: str = "self",
               created_by_id: int | None = None) -> MentorAction:
    a = MentorAction(user_id=user.id, title=title.strip()[:300], reason=(reason or "").strip()[:2000],
                     priority=priority if priority in ("high", "medium", "low") else "medium", due_on=due_on, source=source,
                     created_by_id=created_by_id)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def reflection_out(r: Reflection) -> dict[str, Any]:
    return {"id": r.id, "week_start": r.week_start, "outcome": r.outcome, "obstacle": r.obstacle, "next_action": r.next_action,
            "mood": r.mood, "created_at": r.created_at}


def reflect(db: Session, user: User, outcome: str, obstacle: str, next_action: str, mood: int | None) -> Reflection:
    wk = _week_start()
    r = db.execute(select(Reflection).where(Reflection.user_id == user.id, Reflection.week_start == wk)).scalar_one_or_none()
    first = r is None
    if r is None:
        r = Reflection(user_id=user.id, week_start=wk, outcome="", obstacle="", next_action="")
        db.add(r)
    r.outcome, r.obstacle, r.next_action, r.mood = outcome.strip()[:3000], obstacle.strip()[:3000], next_action.strip()[:1000], mood
    if first:
        db.add(MentorAction(user_id=user.id, title=next_action.strip()[:300], reason="Your next action from this week's reflection",
                            priority="high", due_on=wk + timedelta(days=7), source="reflection"))
        platform_service.track(db, user.id, "reflection_completed", week=str(wk))
    db.commit()
    db.refresh(r)
    return r


def reflections(db: Session, user: User) -> list[Reflection]:
    return list(db.execute(select(Reflection).where(Reflection.user_id == user.id).order_by(Reflection.week_start.desc())).scalars())


# ---------------- human mentors ----------------

def _audit(db: Session, actor: User, action: str, target: str, details: dict | None = None) -> None:
    db.add(AuditLog(actor_id=actor.id, action=action, target_type="user", target_id=target, details=details or {}))


def invite_mentor(db: Session, candidate: User, mentor_email: str, scopes: list[str]) -> MentorAssignment:
    platform_service.require_consent(db, candidate, "mentor_sharing")
    mentor = db.execute(select(User).where(User.email == mentor_email.strip().lower(), User.is_active.is_(True))).scalar_one_or_none()
    if mentor is None or mentor.role != "mentor" or mentor.id == candidate.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No mentor account with that e-mail address.")
    scopes = [s for s in scopes if s in SCOPES] or ["funnel", "gaps", "actions"]
    a = db.execute(select(MentorAssignment).where(MentorAssignment.candidate_id == candidate.id, MentorAssignment.mentor_id == mentor.id)).scalar_one_or_none()
    if a is None:
        a = MentorAssignment(candidate_id=candidate.id, mentor_id=mentor.id)
        db.add(a)
    a.status, a.scopes, a.consented_at, a.revoked_at = "active", scopes, utcnow(), None
    _audit(db, candidate, "MENTOR_ACCESS_GRANTED", str(mentor.id), {"scopes": scopes})
    db.commit()
    db.refresh(a)
    return a


def candidate_assignments(db: Session, candidate: User) -> list[dict[str, Any]]:
    rows = db.execute(select(MentorAssignment).where(MentorAssignment.candidate_id == candidate.id)).scalars().all()
    return [{"id": a.id, "mentor_name": (db.get(User, a.mentor_id).full_name or "Mentor"), "mentor_email": db.get(User, a.mentor_id).email,
             "status": a.status, "scopes": a.scopes, "consented_at": a.consented_at, "revoked_at": a.revoked_at} for a in rows]


def revoke(db: Session, candidate: User, assignment_id: int) -> None:
    a = db.execute(select(MentorAssignment).where(MentorAssignment.id == assignment_id, MentorAssignment.candidate_id == candidate.id)).scalar_one_or_none()
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    a.status, a.revoked_at = "revoked", utcnow()
    _audit(db, candidate, "MENTOR_ACCESS_REVOKED", str(a.mentor_id))
    db.commit()


def require_mentor(user: User) -> User:
    if user.role != "mentor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Mentor role required.")
    return user


def _active(db: Session, mentor: User, assignment_id: int) -> MentorAssignment:
    a = db.execute(select(MentorAssignment).where(MentorAssignment.id == assignment_id, MentorAssignment.mentor_id == mentor.id,
                                                  MentorAssignment.status == "active")).scalar_one_or_none()
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return a


def mentor_candidates(db: Session, mentor: User) -> list[dict[str, Any]]:
    rows = db.execute(select(MentorAssignment).where(MentorAssignment.mentor_id == mentor.id, MentorAssignment.status == "active")).scalars().all()
    return [{"assignment_id": a.id, "candidate_name": db.get(User, a.candidate_id).full_name or f"Candidate {a.candidate_id}",
             "scopes": a.scopes, "since": a.consented_at} for a in rows]


def candidate_summary(db: Session, settings: BackendSettings, mentor: User, assignment_id: int) -> dict[str, Any]:
    a = _active(db, mentor, assignment_id)
    cand = db.get(User, a.candidate_id)
    _audit(db, mentor, "MENTOR_VIEWED_CANDIDATE", str(cand.id), {"assignment": a.id, "scopes": a.scopes})
    out: dict[str, Any] = {"assignment_id": a.id, "candidate_name": cand.full_name, "scopes": a.scopes}
    if "profile" in a.scopes:
        out["profile_completeness"] = career_service.profile_completeness(db, cand)
    if "funnel" in a.scopes:
        out["funnel"] = interview_service.funnel(db, cand)
        out["diagnoses"] = [{k: v for k, v in d.items() if k != "actions"} for d in diagnose(db, cand)]
    if "gaps" in a.scopes:
        out["gaps"] = [career_service._gap_out(g) for g in career_service.list_gaps(db, cand, include_closed=False)[:10]]
    if "actions" in a.scopes:
        out["actions"] = [action_out(x) for x in actions(db, cand)]
    if "applications" in a.scopes:
        out["applications"] = [{"id": x.id, "title": x.job.title, "company": x.job.company, "status": x.status, "stage": x.stage}
                               for x in db.execute(select(Application).where(Application.user_id == cand.id)).unique().scalars()]
    out["notes"] = notes(db, mentor, a)
    out["sessions"] = [session_out(s) for s in db.execute(select(MentorSession).where(MentorSession.assignment_id == a.id)
                                                          .order_by(MentorSession.scheduled_at.desc().nullslast())).scalars()]
    db.commit()
    return out


def notes(db: Session, viewer: User, a: MentorAssignment) -> list[dict[str, Any]]:
    rows = db.execute(select(MentorNote).where(MentorNote.assignment_id == a.id).order_by(MentorNote.created_at.desc())).scalars().all()
    return [{"id": n.id, "body": n.body, "visibility": n.visibility, "by_me": n.author_id == viewer.id, "created_at": n.created_at}
            for n in rows if n.visibility == "shared" or n.author_id == viewer.id]


def add_note(db: Session, author: User, assignment_id: int, body: str, visibility: str, as_mentor: bool) -> MentorNote:
    a = _active(db, author, assignment_id) if as_mentor else _candidate_assignment(db, author, assignment_id)
    n = MentorNote(assignment_id=a.id, author_id=author.id, body=body.strip()[:5000], visibility="private" if visibility == "private" else "shared")
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _candidate_assignment(db: Session, candidate: User, assignment_id: int) -> MentorAssignment:
    a = db.execute(select(MentorAssignment).where(MentorAssignment.id == assignment_id, MentorAssignment.candidate_id == candidate.id,
                                                  MentorAssignment.status == "active")).scalar_one_or_none()
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return a


def session_out(s: MentorSession) -> dict[str, Any]:
    return {"id": s.id, "scheduled_at": s.scheduled_at, "duration_minutes": s.duration_minutes, "meeting_url": s.meeting_url,
            "agenda": s.agenda, "status": s.status, "summary": s.summary}


def schedule_session(db: Session, user: User, assignment_id: int, data: dict[str, Any], as_mentor: bool) -> MentorSession:
    a = _active(db, user, assignment_id) if as_mentor else _candidate_assignment(db, user, assignment_id)
    url = (data.get("meeting_url") or "").strip() or None
    if url and not url.startswith("https://"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Meeting links must start with https://")
    s = MentorSession(assignment_id=a.id, scheduled_at=data.get("scheduled_at"), duration_minutes=int(data.get("duration_minutes") or 30),
                      meeting_url=url, agenda=(data.get("agenda") or "").strip()[:3000] or None)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def update_session(db: Session, user: User, session_id: int, data: dict[str, Any]) -> MentorSession:
    s = db.get(MentorSession, session_id)
    a = db.get(MentorAssignment, s.assignment_id) if s else None
    if s is None or a is None or a.status != "active" or user.id not in (a.mentor_id, a.candidate_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    for k in ("status", "summary", "agenda"):
        if data.get(k) is not None:
            setattr(s, k, str(data[k])[:5000])
    db.commit()
    return s


def candidate_sessions(db: Session, candidate: User) -> list[dict[str, Any]]:
    ids = [a.id for a in db.execute(select(MentorAssignment).where(MentorAssignment.candidate_id == candidate.id,
                                                                   MentorAssignment.status == "active")).scalars()]
    rows = db.execute(select(MentorSession).where(MentorSession.assignment_id.in_(ids or [-1]))).scalars().all()
    return [{**session_out(s), "assignment_id": s.assignment_id} for s in rows]


def mentor_recommend(db: Session, mentor: User, assignment_id: int, title: str, reason: str, priority: str, due_on) -> MentorAction:
    a = _active(db, mentor, assignment_id)
    if "actions" not in a.scopes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The candidate hasn't shared their action plan with you.")
    cand = db.get(User, a.candidate_id)
    _audit(db, mentor, "MENTOR_RECOMMENDED_ACTION", str(cand.id))
    return add_action(db, cand, title, reason, priority, due_on, source="human_mentor", created_by_id=mentor.id)
