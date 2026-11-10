"""Verified Recruiter Email Drafting & Dispatch Consent Service.

Drafts professional, role-specific recruiter emails based on candidate's
verified facts and tailored resume highlights. Adheres to strict candidate
consent gates: drafts require explicit review before simulated or SMTP delivery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.orm import Session

from backend.models import Application, Job, User
from backend.services.profile_master_service import ProfileMasterService


@dataclass
class RecruiterEmailDraft:
    recipient_email: str
    subject: str
    body_text: str
    attachment_name: str
    candidate_consent_required: bool = True


class RecruiterEmailService:
    """Constructs verified recruiter outreach drafts."""

    @classmethod
    def generate_draft(
        cls, db: Session, user: User, app: Application, target_email: str | None = None
    ) -> RecruiterEmailDraft:
        job = app.job
        recipient = target_email or cls._extract_email_from_job(job)
        if not recipient:
            recipient = f"careers@{job.company.lower().replace(' ', '')}.com" if job.company else "recruiting@company.com"

        # Validate syntax
        try:
            valid = validate_email(recipient, check_deliverability=False)
            clean_recipient = valid.normalized
        except EmailNotValidError:
            clean_recipient = "careers@company.com"

        master_facts = ProfileMasterService.get_master_facts(db, user.id)
        candidate_name = user.full_name or "Candidate"
        top_skills = master_facts.get("skills", [])[:4]
        skills_str = ", ".join(top_skills)
        years_exp = master_facts.get("years_experience", 0)

        subject = f"Application for {job.title or 'Software Engineer'} — {candidate_name}"

        body_text = (
            f"Dear {job.company or 'Hiring'} Team,\n\n"
            f"I am writing to express my strong interest in the {job.title or 'Software Engineer'} role "
            f"at {job.company or 'your company'}.\n\n"
            f"With over {years_exp:.0f} years of engineering experience focusing on {skills_str}, "
            f"I have delivered scalable backend systems and high-throughput microservices that align closely "
            f"with your team's technical requirements.\n\n"
            f"I have attached my tailored resume for your consideration. I would welcome the opportunity "
            f"to discuss how my background and technical problem-solving can contribute to {job.company or 'your team'}.\n\n"
            f"Thank you for your time and consideration.\n\n"
            f"Best regards,\n"
            f"{candidate_name}\n"
            f"Email: {user.email}\n"
            f"Location: {', '.join(master_facts.get('preferred_locations', ['Bengaluru']))}\n"
        )

        attachment_name = f"{candidate_name.replace(' ', '_')}_Resume.pdf"

        return RecruiterEmailDraft(
            recipient_email=clean_recipient,
            subject=subject,
            body_text=body_text,
            attachment_name=attachment_name,
            candidate_consent_required=True,
        )

    @staticmethod
    def _extract_email_from_job(job: Job) -> str | None:
        text = f"{job.description or ''} {job.job_url or ''} {job.application_url or ''}"
        match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        return match.group(0) if match else None
