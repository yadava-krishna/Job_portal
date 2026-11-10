"""Tests for Phase 11: Resume Studio & ATS Optimization (PDF & DOCX)."""

import pytest
from backend.models import Job
from backend.services.docx_generator import DocxResumeGenerator
from backend.services.pdf_generator import PdfResumeGenerator
from tests.api.api_helpers import auth, register


def test_docx_generator_output():
    buffer = DocxResumeGenerator.generate(
        candidate_name="Arjun Verma",
        contact_info={"email": "arjun@example.com", "location": "Bengaluru, India"},
        summary="Experienced backend engineer building scalable distributed architectures.",
        skills=["Python", "FastAPI", "Docker", "PostgreSQL"],
        experiences=[
            {
                "company": "Swiggy Tech",
                "title": "Senior Software Engineer",
                "start_date": "2021",
                "end_date": "Present",
                "is_current": True,
                "bullets": ["Engineered order streaming microservice processing 50k rpm."],
            }
        ],
        education="B.Tech in Computer Science",
    )
    data = buffer.getvalue()
    assert len(data) > 1000
    # DOCX is a zip archive starting with PK\x03\x04
    assert data.startswith(b"PK\x03\x04")


def test_pdf_generator_output():
    buffer = PdfResumeGenerator.generate(
        candidate_name="Arjun Verma",
        contact_info={"email": "arjun@example.com", "location": "Bengaluru, India"},
        summary="Experienced backend engineer building scalable distributed architectures.",
        skills=["Python", "FastAPI", "Docker", "PostgreSQL"],
        experiences=[
            {
                "company": "Swiggy Tech",
                "title": "Senior Software Engineer",
                "start_date": "2021",
                "end_date": "Present",
                "is_current": True,
                "bullets": ["Engineered order streaming microservice processing 50k rpm."],
            }
        ],
        education="B.Tech in Computer Science",
    )
    data = buffer.getvalue()
    assert len(data) > 1000
    # Valid PDF starts with %PDF-
    assert data.startswith(b"%PDF-")


def test_resume_studio_api_flow(client):
    from backend.db import session_factory
    headers = auth(register(client, "resume_studio_user@jobpilot.io"))

    job_id = None
    with session_factory()() as db:
        job = Job(
            job_key="linkedin:swiggy_backend_lead",
            platform="LinkedIn",
            external_job_id="swiggy_lead_123",
            company="Swiggy",
            title="Lead Backend Engineer",
            job_url="https://swiggy.careers/jobs/123",
            location="Bengaluru, Karnataka",
            work_mode="Hybrid",
            description="Looking for Lead Backend Engineer with Python, FastAPI, and PostgreSQL expertise.",
            required_skills=["Python", "FastAPI", "PostgreSQL"],
            source="linkedin",
            is_expired=False,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
        from backend.models import User, UserJob
        uid = db.query(User).filter(User.email == "resume_studio_user@jobpilot.io").one().id
        db.add(UserJob(user_id=uid, job_id=job_id, source="import", status="new"))
        db.commit()

    # Someone else's feed: a job that isn't in yours can't be tailored.
    other = auth(register(client, "resume_studio_other@jobpilot.io"))
    assert client.post("/api/v1/resumes/tailor", json={"job_id": job_id}, headers=other).status_code == 404

    # 1. Tailor Resume for Job
    res = client.post("/api/v1/resumes/tailor", json={"job_id": job_id}, headers=headers)
    assert res.status_code == 200, res.text
    tailored = res.json()
    assert tailored["job_id"] == job.id
    assert tailored["is_truthful_audited"] is True
    tailored_id = tailored["id"]

    # 2. Export as PDF
    pdf_res = client.get(f"/api/v1/resumes/tailored/{tailored_id}/export/pdf", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")

    # 3. Export as DOCX
    docx_res = client.get(f"/api/v1/resumes/tailored/{tailored_id}/export/docx", headers=headers)
    assert docx_res.status_code == 200
    assert "openxmlformats" in docx_res.headers["content-type"]
    assert docx_res.content.startswith(b"PK\x03\x04")

    # 4. Run 3-Tier ATS Compatibility Diagnostic
    ats_res = client.post(f"/api/v1/resumes/tailored/{tailored_id}/ats-compatibility", headers=headers)
    assert ats_res.status_code == 200
    ats_data = ats_res.json()
    assert ats_data["tier1_structure_score"] > 0
    assert ats_data["tier2_content_score"] > 0
    assert ats_data["tier3_parsing_score"] > 0
    assert 0 < ats_data["overall_score"] <= 100  # an empty (honest) profile scores low; no seeded fake facts
    assert len(ats_data["findings"]) > 0
