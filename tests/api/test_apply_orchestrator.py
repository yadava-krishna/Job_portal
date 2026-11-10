"""Tests for Phase 12: Unified Apply Orchestration Service."""

import pytest
from backend.db import session_factory
from backend.models import Job
from backend.services.apply_orchestrator import ApplyOrchestrator
from tests.api.api_helpers import auth, register


def test_route_determination_logic():
    # Route A: Greenhouse / Lever
    job_gh = Job(
        job_key="stripe:gh_123", platform="Greenhouse", external_job_id="123", company="Stripe",
        title="Software Engineer", job_url="https://boards.greenhouse.io/stripe/jobs/123", source="greenhouse",
    )
    assert ApplyOrchestrator._determine_route(job_gh) == "ROUTE_A_DIRECT_API"

    # Route B: Workday
    job_wd = Job(
        job_key="adobe:wd_456", platform="Workday", external_job_id="456", company="Adobe",
        title="Senior Developer", job_url="https://adobe.myworkdayjobs.com/en-US/careers/job/456", source="workday",
    )
    assert ApplyOrchestrator._determine_route(job_wd) == "ROUTE_B_ATS_FORM"

    # Route C: Email
    job_email = Job(
        job_key="startup:mail_789", platform="Startup", external_job_id="789", company="Stealth",
        title="Founding Engineer", job_url="mailto:hiring@stealthstartup.io", source="startup",
    )
    assert ApplyOrchestrator._determine_route(job_email) == "ROUTE_C_EMAIL"

    # Route D: External Manual
    job_ext = Job(
        job_key="portal:ext_999", platform="Other", external_job_id="999", company="TechCorp",
        title="Platform Engineer", job_url="https://techcorp.com/careers/apply/999", source="portal",
    )
    assert ApplyOrchestrator._determine_route(job_ext) == "ROUTE_D_EXTERNAL_MANUAL"


def test_apply_orchestration_api_flow(client):
    headers = auth(register(client, "orchestrator_candidate@jobpilot.io"))

    job_id = None
    with session_factory()() as db:
        job = Job(
            job_key="greenhouse:canva_infra_lead",
            platform="Greenhouse",
            external_job_id="canva_555",
            company="Canva",
            title="Infrastructure Tech Lead",
            job_url="https://jobs.lever.co/canva/555",
            location="Remote",
            work_mode="Remote",
            description="Leading cloud infrastructure with Docker and Kubernetes.",
            required_skills=["Docker", "Kubernetes"],
            source="lever",
            is_expired=False,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
        from backend.models import User, UserJob
        uid = db.query(User).filter(User.email == "orchestrator_candidate@jobpilot.io").one().id
        db.add(UserJob(user_id=uid, job_id=job_id, source="import", status="new"))
        db.commit()

    # 1. Orchestrate Application
    res = client.post(f"/api/v1/applications/jobs/{job_id}/orchestrate", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["job"]["id"] == job_id
    assert data["application_route"] in ("ROUTE_A_DIRECT_API", "ROUTE_B_ATS_FORM", "ROUTE_D_EXTERNAL_MANUAL")
    assert data["tailored_resume_id"] is not None
    assert len(data["screening_answers"]) > 0
    assert len(data["checklist"]) > 0
    app_id = data["id"]

    # 2. Generate Recruiter Email Draft
    draft_res = client.post(
        f"/api/v1/applications/{app_id}/email-draft",
        json={"target_email": "recruiting@canva.com"},
        headers=headers,
    )
    assert draft_res.status_code == 200
    draft = draft_res.json()
    assert draft["recipient_email"] == "recruiting@canva.com"
    assert "Canva" in draft["body_text"] or "Infrastructure Tech Lead" in draft["subject"]
    assert draft["candidate_consent_required"] is True
    assert draft["attachment_name"].endswith(".pdf")
