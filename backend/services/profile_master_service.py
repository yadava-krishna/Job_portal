"""Master Candidate Profile (V2) Management Service.

Provides structured CRUD, verification, and fact aggregation for candidate
work experiences, skills, preferences, and verified career milestones.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import CandidateProfile, CandidateProfileV2, ProfileSkill, ProfileWorkExperience, utcnow

log = logging.getLogger(__name__)



def _parse_month(value: Any):
    """'2021-04' / '2021-04-01' / 'Apr 2021' -> date, or None when it can't be read reliably."""
    from datetime import date, datetime as _dt
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%b %Y", "%B %Y", "%m/%Y", "%Y"):
        try:
            d = _dt.strptime(value.strip(), fmt)
            return date(d.year, d.month, 1)
        except ValueError:
            continue
    return None


class ProfileMasterService:
    """Manages relational Master Candidate Profile V2."""

    @classmethod
    def get_or_create_profile(cls, db: Session, user_id: int) -> CandidateProfileV2:
        profile = db.execute(
            select(CandidateProfileV2).where(CandidateProfileV2.user_id == user_id)
        ).scalar_one_or_none()

        if profile is None:
            # Seed only from what the candidate confirmed (legacy confirmed profile). Nothing is invented: unknown
            # fields stay empty and skills are not marked verified until the candidate confirms them here.
            legacy = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user_id)).scalar_one_or_none()
            conf = (legacy.confirmed_profile if legacy else None) or {}
            exps = conf.get("experience") or []
            profile = CandidateProfileV2(
                user_id=user_id,
                headline=conf.get("headline") or (exps[0].get("title") if exps else None),
                summary=conf.get("summary"),
                years_experience=round((legacy.experience_months or 0) / 12, 1) if legacy else 0.0,
                relevant_it_experience=0.0,
                highest_education_level=None,
                preferred_locations=[],
                work_modes=[],
                work_authorization="",
                notice_period_days=0,
                verified_facts=dict(legacy.verified_facts or {}) if legacy else {},
                contact={k: conf.get(k) for k in ("full_name", "email", "phone", "location") if conf.get(k)},
                education=[{**e, "source": "confirmed_profile", "verified": True} for e in conf.get("education") or []],
                projects=[{**p, "source": "confirmed_profile", "verified": True} for p in conf.get("projects") or []],
                certifications=[{"name": c, "source": "confirmed_profile", "verified": True} for c in conf.get("certifications") or []],
                provenance={"seeded_from": "confirmed_profile" if conf else "empty", "seeded_at": utcnow().isoformat()},
            )
            db.add(profile)
            db.flush()
            for e in exps:
                db.add(ProfileWorkExperience(profile_id=profile.id, company=e.get("company") or "", title=e.get("title") or "",
                                             is_current=bool(e.get("is_current")), verified_bullets=list(e.get("bullets") or []),
                                             start_date=_parse_month(e.get("start")), end_date=_parse_month(e.get("end"))))
            for name in conf.get("skills") or []:
                db.add(ProfileSkill(profile_id=profile.id, name=name, category="technical", proficiency="UNSPECIFIED",
                                    years=0.0, is_verified=True))  # confirmed by the candidate in the profile review step
            db.commit()
            db.refresh(profile)

        return profile

    @classmethod
    def update_profile(cls, db: Session, user_id: int, data: dict[str, Any]) -> CandidateProfileV2:
        profile = cls.get_or_create_profile(db, user_id)
        allowed_fields = {
            "headline", "summary", "years_experience", "relevant_it_experience",
            "highest_education_level", "preferred_locations", "work_modes",
            "work_authorization", "expected_ctc_inr", "notice_period_days", "verified_facts"
        }
        for field, value in data.items():
            if field in allowed_fields and value is not None:
                setattr(profile, field, value)

        db.commit()
        db.refresh(profile)
        return profile

    @staticmethod
    def _parse_date(d: Any) -> Any:
        if isinstance(d, str) and d.strip():
            from datetime import date
            try:
                return date.fromisoformat(d.strip())
            except ValueError:
                return None
        return d

    @classmethod
    def add_work_experience(cls, db: Session, user_id: int, exp_data: dict[str, Any]) -> ProfileWorkExperience:
        profile = cls.get_or_create_profile(db, user_id)
        exp = ProfileWorkExperience(
            profile_id=profile.id,
            company=exp_data["company"],
            title=exp_data["title"],
            start_date=cls._parse_date(exp_data.get("start_date")),
            end_date=cls._parse_date(exp_data.get("end_date")),
            is_current=exp_data.get("is_current", False),
            description=exp_data.get("description", ""),
            technologies=exp_data.get("technologies", []),
            verified_bullets=exp_data.get("verified_bullets", []),
        )
        db.add(exp)
        db.commit()
        db.refresh(exp)
        return exp

    @classmethod
    def update_work_experience(cls, db: Session, user_id: int, exp_id: int, exp_data: dict[str, Any]) -> ProfileWorkExperience:
        profile = cls.get_or_create_profile(db, user_id)
        exp = db.execute(
            select(ProfileWorkExperience).where(
                ProfileWorkExperience.id == exp_id,
                ProfileWorkExperience.profile_id == profile.id
            )
        ).scalar_one_or_none()

        if exp is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Work experience not found")

        for key in ["company", "title", "start_date", "end_date", "is_current", "description", "technologies", "verified_bullets"]:
            if key in exp_data:
                val = exp_data[key]
                if key in ("start_date", "end_date"):
                    val = cls._parse_date(val)
                setattr(exp, key, val)

        db.commit()
        db.refresh(exp)
        return exp

    @classmethod
    def delete_work_experience(cls, db: Session, user_id: int, exp_id: int) -> bool:
        profile = cls.get_or_create_profile(db, user_id)
        exp = db.execute(
            select(ProfileWorkExperience).where(
                ProfileWorkExperience.id == exp_id,
                ProfileWorkExperience.profile_id == profile.id
            )
        ).scalar_one_or_none()
        if not exp:
            return False
        db.delete(exp)
        db.commit()
        return True

    @classmethod
    def add_or_update_skill(cls, db: Session, user_id: int, skill_data: dict[str, Any]) -> ProfileSkill:
        profile = cls.get_or_create_profile(db, user_id)
        name = skill_data["name"].strip()
        existing = db.execute(
            select(ProfileSkill).where(
                ProfileSkill.profile_id == profile.id,
                ProfileSkill.name.ilike(name)
            )
        ).scalar_one_or_none()

        if existing:
            if "proficiency" in skill_data:
                existing.proficiency = skill_data["proficiency"]
            if "years" in skill_data:
                existing.years = float(skill_data["years"])
            if "category" in skill_data:
                existing.category = skill_data["category"]
            if "is_verified" in skill_data:
                existing.is_verified = bool(skill_data["is_verified"])
            db.commit()
            db.refresh(existing)
            return existing

        skill = ProfileSkill(
            profile_id=profile.id,
            name=name,
            category=skill_data.get("category", "technical"),
            proficiency=skill_data.get("proficiency", "INTERMEDIATE"),
            years=float(skill_data.get("years", 1.0)),
            is_verified=bool(skill_data.get("is_verified", True)),
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)
        return skill

    @classmethod
    def delete_skill(cls, db: Session, user_id: int, skill_id: int) -> bool:
        profile = cls.get_or_create_profile(db, user_id)
        skill = db.execute(
            select(ProfileSkill).where(
                ProfileSkill.id == skill_id,
                ProfileSkill.profile_id == profile.id
            )
        ).scalar_one_or_none()
        if not skill:
            return False
        db.delete(skill)
        db.commit()
        return True

    @classmethod
    def get_master_facts(cls, db: Session, user_id: int) -> dict[str, Any]:
        profile = cls.get_or_create_profile(db, user_id)
        skills = [s.name for s in profile.skills]
        return {
            "headline": profile.headline,
            "summary": profile.summary,
            "years_experience": profile.years_experience,
            "relevant_it_experience": profile.relevant_it_experience,
            "education": profile.highest_education_level,
            "work_authorization": profile.work_authorization,
            "preferred_locations": profile.preferred_locations,
            "work_modes": profile.work_modes,
            "skills": skills,
            "experiences": [
                {
                    "id": exp.id,
                    "company": exp.company,
                    "title": exp.title,
                    "start_date": exp.start_date.isoformat() if exp.start_date else None,
                    "end_date": exp.end_date.isoformat() if exp.end_date else None,
                    "is_current": exp.is_current,
                    "description": exp.description,
                    "technologies": exp.technologies,
                    "verified_bullets": exp.verified_bullets,
                }
                for exp in profile.experiences
            ],
            "verified_facts": profile.verified_facts,
        }
