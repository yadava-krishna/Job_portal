"""backend/services/achievement_service.py

Achievement rules engine and celebration milestone tracker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import User, UserAchievement

ACHIEVEMENTS = {
    "FIRST_RESUME": {
        "title": "Setting Sail",
        "description": "Uploaded your first resume and generated a candidate profile.",
        "icon": "scroll",
        "category": "onboarding",
    },
    "FIRST_SEARCH": {
        "title": "Charting the Course",
        "description": "Created your first automated saved search criteria.",
        "icon": "compass",
        "category": "discovery",
    },
    "FIRST_WATCH": {
        "title": "Harbor Watch",
        "description": "Added an employer career board to your company watchlist.",
        "icon": "binoculars",
        "category": "discovery",
    },
    "FIRST_CLIP": {
        "title": "Cargo Secured",
        "description": "Imported or clipped a vacancy using the browser tools.",
        "icon": "paperclip",
        "category": "discovery",
    },
    "FIRST_APP": {
        "title": "First Venture",
        "description": "Prepared your first tailored application package.",
        "icon": "send",
        "category": "applications",
    },
    "FIRST_INTERVIEW": {
        "title": "Meeting the Captain",
        "description": "Scheduled an interview round with an employer.",
        "icon": "calendar",
        "category": "pipeline",
    },
    "FIRST_OFFER": {
        "title": "Treasure in Port",
        "description": "Recorded an official employment offer.",
        "icon": "trophy",
        "category": "pipeline",
    },
    "APP_10": {
        "title": "Seasoned Mariner",
        "description": "Submitted 10 verified job applications.",
        "icon": "anchor",
        "category": "milestone",
    },
    "DISCOVERY_50": {
        "title": "Master of Charts",
        "description": "Discovered and evaluated 50 matched vacancies.",
        "icon": "map",
        "category": "discovery",
    },
}


@dataclass
class AchievementOut:
    code: str
    title: str
    description: str
    icon: str
    category: str
    earned: bool
    earned_at: datetime | None = None


def list_user_achievements(db: Session, user: User) -> list[AchievementOut]:
    """Retrieve all badges with earned state for this candidate."""
    earned_rows = db.execute(select(UserAchievement).where(UserAchievement.user_id == user.id)).scalars().all()
    earned_map = {r.code: r.earned_at for r in earned_rows}

    out: list[AchievementOut] = []
    for code, info in ACHIEVEMENTS.items():
        earned = code in earned_map
        out.append(
            AchievementOut(
                code=code,
                title=info["title"],
                description=info["description"],
                icon=info["icon"],
                category=info["category"],
                earned=earned,
                earned_at=earned_map.get(code),
            )
        )
    return out


def award_achievement(db: Session, user: User, code: str) -> bool:
    """Award an achievement badge if not already unlocked. Returns True if newly earned."""
    if code not in ACHIEVEMENTS:
        return False
    existing = db.execute(
        select(UserAchievement).where(UserAchievement.user_id == user.id, UserAchievement.code == code)
    ).scalar_one_or_none()
    if existing is not None:
        return False

    row = UserAchievement(
        user_id=user.id,
        code=code,
        earned_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return True
