"""Truthful Resume Tailoring Engine & Anti-Fabrication Audit.

Re-orders and emphasizes candidate's verified experiences and bullet points
for a specific Job Description without fabricating achievements, inflating
metrics, or adding unverified technologies.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import UserJob, Job, TailoredResume, User
from backend.services.jd_intelligence_service import JDIntelligenceService
from backend.services.profile_master_service import ProfileMasterService

log = logging.getLogger(__name__)


class ResumeTailorService:
    """Produces job-specific tailored resumes strictly bounded by verified candidate facts."""

    @classmethod
    def tailor_resume(cls, db: Session, user: User, job_id: int) -> TailoredResume:
        job = db.get(Job, job_id)
        in_feed = job is not None and db.execute(
            select(UserJob.id).where(UserJob.user_id == user.id, UserJob.job_id == job.id)).first() is not None
        if not in_feed:  # only jobs in this user's own feed
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")

        master_facts = ProfileMasterService.get_master_facts(db, user.id)
        jd_analysis = JDIntelligenceService.analyze_jd(job.title or "", job.description or "", job.location or "")

        target_skills = [s.lower() for s in (jd_analysis.required_skills + jd_analysis.preferred_skills)]
        verified_skills = [s.lower() for s in master_facts["skills"]]
        matching_skills = [s for s in master_facts["skills"] if s.lower() in target_skills]

        # 1. Tailor Work Experience Bullets
        selected_experiences: list[dict[str, Any]] = []
        for exp in master_facts["experiences"]:
            bullets = exp.get("verified_bullets", [])
            technologies = [t.lower() for t in exp.get("technologies", [])]

            # Score each bullet by keyword match density
            scored_bullets: list[tuple[float, str]] = []
            for b in bullets:
                score = 1.0
                b_lower = b.lower()
                for skill in target_skills:
                    if skill in b_lower:
                        score += 3.0
                for tech in technologies:
                    if tech in target_skills:
                        score += 1.5
                scored_bullets.append((score, b))

            # Sort bullets by relevance (highest first) while keeping original text
            scored_bullets.sort(key=lambda x: x[0], reverse=True)
            sorted_bullets = [b for _, b in scored_bullets]

            selected_experiences.append({
                "company": exp["company"],
                "title": exp["title"],
                "start_date": exp["start_date"],
                "end_date": exp["end_date"],
                "is_current": exp["is_current"],
                "description": exp.get("description", ""),
                "technologies": exp.get("technologies", []),
                "bullets": sorted_bullets,
            })

        # 2. Summary built only from the candidate's own facts: their headline (or latest verified title), verified
        # years and verified skills that the job asks for. No invented titles, claims or adjectives.
        years_exp = master_facts.get("years_experience", 0) or 0
        top_skills = matching_skills[:5] or master_facts["skills"][:5]
        role = (master_facts.get("headline") or "").strip() or next((e["title"] for e in master_facts["experiences"] if e.get("title")), "")
        parts = []
        if role:
            parts.append(role + (f" with {years_exp:g} years of experience" if years_exp else ""))
        if top_skills:
            parts.append("skills relevant to this role: " + ", ".join(top_skills))
        tailored_summary = ("; ".join(parts) + ".") if parts else ""

        # 3. Anti-fabrication gate: every bullet must be one of the candidate's own verified bullets, and every
        # skill named in the summary must be a verified skill.
        is_truthful = cls._anti_fabrication_audit(master_facts, selected_experiences, top_skills, verified_skills)
        if not is_truthful:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Resume failed anti-fabrication truthfulness verification.")

        # 4. Upsert Tailored Resume in DB
        title = f"{user.full_name or 'Candidate'} - {job.company or 'Target'} ({job.title or 'Role'})"
        tailored = db.execute(
            select(TailoredResume).where(
                TailoredResume.user_id == user.id,
                TailoredResume.job_id == job.id,
            )
        ).scalar_one_or_none()

        if tailored is None:
            tailored = TailoredResume(
                user_id=user.id,
                job_id=job.id,
                title=title,
                selected_bullets=selected_experiences,
                tailored_summary=tailored_summary,
                is_truthful_audited=True,
            )
            db.add(tailored)
        else:
            tailored.title = title
            tailored.selected_bullets = selected_experiences
            tailored.tailored_summary = tailored_summary
            tailored.is_truthful_audited = True

        db.commit()
        db.refresh(tailored)
        return tailored

    @staticmethod
    def _anti_fabrication_audit(master_facts: dict[str, Any], experiences: list[dict[str, Any]], summary_skills: list[str],
                                verified_skills: list[str]) -> bool:
        """True only if nothing was introduced that the candidate's verified facts don't contain."""
        own = {b.strip() for e in master_facts["experiences"] for b in e.get("verified_bullets", [])}
        for exp in experiences:
            if not isinstance(exp.get("bullets"), list) or any(b.strip() not in own for b in exp["bullets"]):
                return False
        return all(s.lower() in verified_skills for s in summary_skills)
