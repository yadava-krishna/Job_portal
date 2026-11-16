"""Central Apply Orchestrator Service.

Coordinates candidate applications across 4 routes:
- ROUTE_A_DIRECT_API: Authorized employer ATS public submission APIs.
- ROUTE_B_ATS_FORM: In-browser assisted form-fill with zero anti-bot tampering.
- ROUTE_C_EMAIL: Verified direct recruiter email drafting with explicit user consent.
- ROUTE_D_EXTERNAL_MANUAL: Guided external portal application with confirmation tracking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Application, Job, TailoredResume, User, UserJob
from backend.services.ats_detector import detect_from_url
from backend.services.profile_master_service import ProfileMasterService
from backend.services.resume_tailor_service import ResumeTailorService

log = logging.getLogger(__name__)


@dataclass
class OrchestrationPlan:
    route: str
    route_name: str
    target_url: str
    tailored_resume_id: int | None
    recommended_answers: list[dict[str, str]] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)
    instructions: str = ""


class ApplyOrchestrator:
    """Selects route, prepares tailored assets, and provisions verified answers."""

    @classmethod
    def orchestrate_job(cls, db: Session, user: User, job_id: int) -> Application:
        job = db.get(Job, job_id)
        if not job or db.execute(select(UserJob.id).where(UserJob.user_id == user.id, UserJob.job_id == job.id)).first() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")  # only jobs in the user's own feed

        # 1. Ensure Tailored Resume is generated for this job
        tailored = db.execute(
            select(TailoredResume).where(
                TailoredResume.user_id == user.id,
                TailoredResume.job_id == job.id,
            )
        ).scalar_one_or_none()

        if tailored is None:
            tailored = ResumeTailorService.tailor_resume(db, user, job.id)

        # 2. Determine Route
        route = cls._determine_route(job)

        # 3. Retrieve Candidate Facts for Q&A Pre-population
        master_facts = ProfileMasterService.get_master_facts(db, user.id)
        answers = cls._generate_screening_answers(master_facts, job)

        checklist = [
            "Review tailored resume highlights and summary",
            f"Verify work authorization ({master_facts.get('work_authorization') or 'not yet in your profile: add it in Settings'})",
            "Verify contact email and phone number",
        ]
        if route == "ROUTE_B_ATS_FORM":
            checklist.append("Open the form and click Fill in the JobPilot extension (Smart Apply)")
            checklist.append("Review every filled field before you submit")
        elif route == "ROUTE_C_EMAIL":
            checklist.append("Review recruiter email draft and tailored PDF attachment")
            checklist.append("Confirm send authorization")
        else:
            checklist.append("Complete submission on employer career portal")
            checklist.append("Record confirmation number in JobPilot tracker")

        route_metadata = {
            "route_description": cls._get_route_description(route),
            "tailored_title": tailored.title,
            "checklist": checklist,
        }

        # 4. Upsert Application Record
        app = db.execute(
            select(Application).where(
                Application.user_id == user.id,
                Application.job_id == job.id,
            )
        ).scalar_one_or_none()

        if app is None:
            app = Application(
                user_id=user.id,
                job_id=job.id,
                status="PREPARED",
                stage="applied",
                application_route=route,
                tailored_resume_id=tailored.id,
                route_metadata=route_metadata,
                screening_answers=answers,
                checklist=[{"item": c, "completed": False} for c in checklist],
            )
            db.add(app)
        else:
            app.application_route = route
            app.tailored_resume_id = tailored.id
            app.route_metadata = route_metadata
            app.screening_answers = answers
            app.checklist = [{"item": c, "completed": False} for c in checklist]

        db.commit()
        db.refresh(app)
        return app

    @classmethod
    def _determine_route(cls, job: Job) -> str:
        url = (job.job_url or "").lower()

        # Check for direct email application
        if "mailto:" in url or "@" in (job.application_url or ""):
            return "ROUTE_C_EMAIL"

        # Check for known ATS patterns
        ats_meta = detect_from_url(url)
        if ats_meta:
            platform = (ats_meta.get("ats_platform") or ats_meta.get("platform") or "").lower()
            if platform in ("greenhouse", "lever", "ashby"):
                return "ROUTE_A_DIRECT_API"
            if platform in ("workday", "smartrecruiters", "recruitee", "taleo", "icims", "workable"):
                return "ROUTE_B_ATS_FORM"

        return "ROUTE_D_EXTERNAL_MANUAL"

    @classmethod
    def _get_route_description(cls, route: str) -> str:
        # Honest labels: nothing is submitted without the user authorising that one application. The route codes stay unchanged for stored records.
        if route == "ROUTE_A_DIRECT_API":
            return "Greenhouse/Lever/Ashby form: Smart Apply fills it, you review and authorise the submission"
        if route == "ROUTE_B_ATS_FORM":
            return "Employer application system (Workday, SmartRecruiters and others): Smart Apply fills what it can, you finish and submit"
        if route == "ROUTE_C_EMAIL":
            return "Email application: JobPilot drafts the email, you send it"
        return "Employer career site: apply there yourself, then record it in JobPilot"

    NEEDS_INPUT = "NEEDS_INPUT"

    @classmethod
    def _generate_screening_answers(cls, facts: dict[str, Any], job: Job) -> list[dict[str, Any]]:
        """Only answers backed by a fact the candidate entered. Anything unknown stays unanswered (never a default)."""

        def item(question: str, value: Any, fmt) -> dict[str, Any]:
            if value in (None, "", []):
                return {"question": question, "answer": None, "status": cls.NEEDS_INPUT,
                        "reason": "Not in your confirmed profile. Answer it yourself."}
            return {"question": question, "answer": fmt(value), "status": "VERIFIED", "source": "profile"}

        years = facts.get("relevant_it_experience", facts.get("years_experience"))
        auth = facts.get("work_authorization")
        return [
            item("What is your total years of relevant IT experience?", years, lambda v: f"{float(v):.1f} years"),
            item("What is your work authorization?", auth, str),
            item("What is your current notice period?", facts.get("notice_period_days"), lambda v: f"{int(v)} days"),
            item("What are your preferred work locations?", facts.get("preferred_locations"), lambda v: ", ".join(v)),
        ]
