"""API routes for Resume Studio: Tailoring, PDF/DOCX Export, and ATS Diagnostics."""

from __future__ import annotations

import io
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from backend.api.deps import CurrentUser, DbSession
from backend.models import Job, TailoredResume
from backend.schemas.resumes import ATSDiagnosticReportOut, TailoredResumeOut, TailorResumeRequest
from backend.services.ats_diagnostic_service import ATSDiagnosticService
from backend.services.docx_generator import DocxResumeGenerator
from backend.services.pdf_generator import PdfResumeGenerator
from backend.services.profile_master_service import ProfileMasterService
from backend.services.resume_tailor_service import ResumeTailorService

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("/tailor", response_model=TailoredResumeOut)
def tailor_resume(body: TailorResumeRequest, user: CurrentUser, db: DbSession) -> TailoredResumeOut:
    """Tailor candidate's resume for a specific job description without fabrication."""
    tailored = ResumeTailorService.tailor_resume(db, user, body.job_id)
    return TailoredResumeOut.model_validate(tailored)


@router.get("/tailored/{tailored_id}", response_model=TailoredResumeOut)
def get_tailored_resume(tailored_id: int, user: CurrentUser, db: DbSession) -> TailoredResumeOut:
    """Retrieve tailored resume details."""
    tailored = db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tailored_id,
            TailoredResume.user_id == user.id,
        )
    ).scalar_one_or_none()

    if not tailored:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tailored resume not found")

    return TailoredResumeOut.model_validate(tailored)


@router.get("/tailored/{tailored_id}/export/pdf")
def export_pdf(tailored_id: int, user: CurrentUser, db: DbSession) -> Response:
    """Stream pristine, machine-readable ATS vector PDF."""
    tailored = db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tailored_id,
            TailoredResume.user_id == user.id,
        )
    ).scalar_one_or_none()

    if not tailored:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tailored resume not found")

    master_facts = ProfileMasterService.get_master_facts(db, user.id)
    contact_info = {
        "email": user.email,
        "location": ", ".join(master_facts.get("preferred_locations", [])[:2]),
    }

    pdf_buffer = PdfResumeGenerator.generate(
        candidate_name=user.full_name or "Candidate",
        contact_info=contact_info,
        summary=tailored.tailored_summary or "",
        skills=master_facts.get("skills", []),
        experiences=tailored.selected_bullets or [],
        education=master_facts.get("education"),
    )

    filename = f"{user.full_name or 'Resume'}_Tailored.pdf".replace(" ", "_")
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tailored/{tailored_id}/export/docx")
def export_docx(tailored_id: int, user: CurrentUser, db: DbSession) -> Response:
    """Stream standard native Microsoft Word .docx document."""
    tailored = db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tailored_id,
            TailoredResume.user_id == user.id,
        )
    ).scalar_one_or_none()

    if not tailored:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tailored resume not found")

    master_facts = ProfileMasterService.get_master_facts(db, user.id)
    contact_info = {
        "email": user.email,
        "location": ", ".join(master_facts.get("preferred_locations", [])[:2]),
    }

    docx_buffer = DocxResumeGenerator.generate(
        candidate_name=user.full_name or "Candidate",
        contact_info=contact_info,
        summary=tailored.tailored_summary or "",
        skills=master_facts.get("skills", []),
        experiences=tailored.selected_bullets or [],
        education=master_facts.get("education"),
    )

    filename = f"{user.full_name or 'Resume'}_Tailored.docx".replace(" ", "_")
    return Response(
        content=docx_buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/tailored/{tailored_id}/ats-compatibility", response_model=ATSDiagnosticReportOut)
def run_ats_diagnostic(tailored_id: int, user: CurrentUser, db: DbSession) -> ATSDiagnosticReportOut:
    """Run 3-tier ATS compatibility diagnostic audit."""
    tailored = db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tailored_id,
            TailoredResume.user_id == user.id,
        )
    ).scalar_one_or_none()

    if not tailored:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tailored resume not found")

    job = db.get(Job, tailored.job_id)
    report = ATSDiagnosticService.evaluate_tailored_resume(db, user, tailored, job)
    return ATSDiagnosticReportOut.model_validate(report)
