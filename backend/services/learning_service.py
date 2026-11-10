"""Learning engine: curated, source-attributed resources per skill and opt-in learning sessions.

Resources come from backend/data/learning_resources.json (official documentation and established learning sites).
Each carries provider, type, level, duration, credibility and when its link was last checked. The resource_refresh
job re-checks links; broken ones are hidden. A session only measures time while the candidate has it open and
active (heartbeats), and only with the `learning_tracking` consent. Opening a link is never treated as learning.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import CandidateSkill, Gap, LearningResource, LearningSession, Notification, User, utcnow
from backend.services import career_service, platform_service

DATA = Path(__file__).resolve().parents[1] / "data" / "learning_resources.json"
LEVEL_FOR_STATE = {None: "beginner", "aware": "beginner", "learning": "beginner", "practising": "intermediate",
                   "project_evidence": "intermediate", "professional_experience": "advanced", "interview_ready": "advanced"}
HEARTBEAT_MAX_GAP = 90  # seconds; longer silences are idle time, not learning time
USER_AGENT = "JobPilot/2.0 (+private job-search assistant; link check)"


def seed_resources(db: Session) -> int:
    """Insert catalogue entries that aren't in the table yet (idempotent; keeps votes and check results)."""
    data = json.loads(DATA.read_text())["resources"]
    have = {(r.url, r.skill) for r in db.execute(select(LearningResource)).scalars()}
    n = 0
    for skill, items in data.items():
        for it in items:
            if (it["url"], skill) in have:
                continue
            db.add(LearningResource(skill=skill, title=it["title"], url=it["url"], provider=it["provider"],
                                    resource_type=it["resource_type"], level=it["level"], duration_minutes=it["duration_minutes"],
                                    credibility=it["credibility"], source="curated",
                                    check_status="ok" if it["link_check"] == "ok" else "unverifiable",
                                    checked_at=utcnow() if it["link_check"] == "ok" else None))
            n += 1
    db.commit()
    return n


def resources_for(db: Session, skill: str, state: str | None = None, limit: int = 5) -> dict[str, Any]:
    if db.execute(select(LearningResource.id).limit(1)).first() is None:
        seed_resources(db)
    rows = db.execute(select(LearningResource).where(LearningResource.skill.ilike(skill), LearningResource.active.is_(True),
                                                     LearningResource.check_status != "broken")).scalars().all()
    want = LEVEL_FOR_STATE.get(state, "beginner")

    def rank(r: LearningResource) -> float:
        votes = r.helpful_votes - r.unhelpful_votes
        return (r.credibility * 3 + (1.0 if r.level == want else 0.0) + (0.5 if r.check_status == "ok" else 0.0)
                + max(-1.0, min(1.0, votes / 5)))

    ranked = sorted(rows, key=rank, reverse=True)[:limit]
    return {"skill": skill, "level_suggested": want, "resources": [_res_out(r, want) for r in ranked],
            "enough": len(ranked) >= 3,
            "note": None if len(ranked) >= 3 else f"Only {len(ranked)} checked resource(s) are catalogued for {skill} so far."}


def _res_out(r: LearningResource, want: str) -> dict[str, Any]:
    why = [f"{r.provider} ({'official source' if r.credibility >= 1 else 'established learning site'})"]
    if r.level == want:
        why.append(f"{r.level} level fits your current evidence")
    if r.helpful_votes:
        why.append(f"{r.helpful_votes} candidate(s) found it helpful")
    return {"id": r.id, "skill": r.skill, "title": r.title, "url": r.url, "provider": r.provider, "type": r.resource_type,
            "level": r.level, "duration_minutes": r.duration_minutes, "is_free": r.is_free, "source": r.source,
            "checked_at": r.checked_at, "link_status": r.check_status, "relevance": "; ".join(why)}


# ---------------- sessions ----------------

def _owned_session(db: Session, user: User, session_id: int) -> LearningSession:
    s = db.execute(select(LearningSession).where(LearningSession.id == session_id, LearningSession.user_id == user.id)).scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Learning session not found")
    return s


def start(db: Session, user: User, resource_id: int | None, gap_id: int | None, skill: str | None) -> LearningSession:
    platform_service.require_consent(db, user, "learning_tracking")
    res = db.get(LearningResource, resource_id) if resource_id else None
    gap = db.execute(select(Gap).where(Gap.id == gap_id, Gap.user_id == user.id)).scalar_one_or_none() if gap_id else None
    name = (res.skill if res else None) or (gap.skill if gap else None) or (skill or "").strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a resource, a gap or a skill")
    for old in db.execute(select(LearningSession).where(LearningSession.user_id == user.id, LearningSession.status == "active")).scalars():
        old.status = "paused"  # one active session at a time
    s = LearningSession(user_id=user.id, resource_id=res.id if res else None, gap_id=gap.id if gap else None, skill=name,
                        status="active", started_at=utcnow(), last_heartbeat_at=utcnow())
    db.add(s)
    if gap and gap.status == "open":
        gap.status = "in_progress"
    db.flush()
    platform_service.track(db, user.id, "resource_started", session_id=s.id, resource_id=s.resource_id, skill=name)
    db.commit()
    return s


def heartbeat(db: Session, user: User, session_id: int, active: bool) -> LearningSession:
    s = _owned_session(db, user, session_id)
    if s.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, "This session is not running")
    now = utcnow()
    last = s.last_heartbeat_at or s.started_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=now.tzinfo)
    gap = max(0, int((now - last).total_seconds()))
    counted = min(gap, HEARTBEAT_MAX_GAP)
    if active:
        s.active_seconds += counted
        s.idle_seconds += gap - counted
    else:
        s.idle_seconds += gap
    s.last_heartbeat_at = now
    db.commit()
    return s


def pause(db: Session, user: User, session_id: int) -> LearningSession:
    s = _owned_session(db, user, session_id)
    if s.status == "active":
        s.status = "paused"
        db.commit()
    return s


def resume(db: Session, user: User, session_id: int) -> LearningSession:
    s = _owned_session(db, user, session_id)
    if s.status != "paused":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a paused session can be resumed")
    s.status, s.last_heartbeat_at = "active", utcnow()
    db.commit()
    return s


def complete(db: Session, settings, user: User, session_id: int, notes: str | None, knowledge_check: dict | None,
             helpful: bool | None, evidence_url: str | None, evidence_title: str | None) -> dict[str, Any]:
    s = _owned_session(db, user, session_id)
    if s.status == "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Already completed")
    s.status, s.ended_at = "completed", utcnow()
    s.notes = (notes or "").strip()[:5000] or None
    s.knowledge_check = {k: str(v)[:1000] for k, v in (knowledge_check or {}).items()}
    s.helpful = helpful
    res = db.get(LearningResource, s.resource_id) if s.resource_id else None
    if res is not None and helpful is not None:
        if helpful:
            res.helpful_votes += 1
        else:
            res.unhelpful_votes += 1
    canonical = career_service._canon(settings, s.skill)
    skill = db.execute(select(CandidateSkill).where(CandidateSkill.user_id == user.id, CandidateSkill.canonical == canonical)).scalar_one_or_none()
    if skill is None:
        skill = career_service.add_skill(db, settings, user, canonical, None, None)
    ev_type = "project" if evidence_url else ("practice" if (res and res.resource_type in ("exercise", "lab")) or s.knowledge_check else "course")
    title = evidence_title or (f"Project: {s.skill}" if evidence_url else f"Completed: {res.title}" if res else f"Studied {s.skill}")
    career_service.add_evidence(db, user, skill, ev_type, title, evidence_url or (res.url if res else None),
                                s.notes, utcnow().date(), learning_session_id=s.id)
    db.refresh(skill)
    platform_service.track(db, user.id, "resource_completed", session_id=s.id, resource_id=s.resource_id,
                           active_minutes=s.active_seconds // 60, evidence_type=ev_type)
    db.add(Notification(user_id=user.id, kind="learning_milestone", title=f"{s.skill}: now '{career_service.STATE_LABELS[skill.state]}'",
                        body=f"You finished a learning session ({s.active_seconds // 60} active minutes). Evidence recorded as {ev_type}.",
                        link="/career", dedupe_key=f"learning:{s.id}"))
    db.commit()
    return {"session": s, "skill_state": skill.state}


def sessions(db: Session, user: User, limit: int = 50) -> list[LearningSession]:
    return list(db.execute(select(LearningSession).where(LearningSession.user_id == user.id)
                           .order_by(LearningSession.started_at.desc()).limit(limit)).scalars())


def stats(db: Session, user: User, days: int = 30) -> dict[str, Any]:
    since = utcnow() - timedelta(days=days)
    rows = [s for s in sessions(db, user, 500) if (s.started_at.replace(tzinfo=since.tzinfo) if s.started_at.tzinfo is None else s.started_at) >= since]
    return {"days": days, "sessions": len(rows), "completed": sum(1 for s in rows if s.status == "completed"),
            "active_minutes": sum(s.active_seconds for s in rows) // 60, "idle_minutes": sum(s.idle_seconds for s in rows) // 60}


# ---------------- resource_refresh job ----------------

def refresh_links(db: Session, limit: int = 200) -> dict[str, int]:
    """Re-check resource links (honest user agent). 404/410 hides a resource; bot-blocked sites stay 'unverifiable'."""
    seed_resources(db)
    out = {"ok": 0, "broken": 0, "unverifiable": 0}
    rows = db.execute(select(LearningResource).order_by(LearningResource.checked_at.asc().nullsfirst()).limit(limit)).scalars().all()
    with httpx.Client(timeout=15, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for r in rows:
            try:
                code = client.get(r.url).status_code
            except httpx.HTTPError:
                code = 0
            r.check_status = "ok" if 200 <= code < 400 else "broken" if code in (404, 410) else "unverifiable"
            r.checked_at = utcnow()
            out[r.check_status] += 1
    db.commit()
    return out
