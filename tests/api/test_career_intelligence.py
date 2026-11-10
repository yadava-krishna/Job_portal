"""Tests for Phase 10: Career Intelligence Engine (Deterministic Matching & Skill Gaps)."""

import pytest
from backend.services.jd_intelligence_service import JDIntelligenceService
from backend.services.skill_gap_service import SkillGapService
from tests.api.api_helpers import auth, register


def test_jd_intelligence_extraction():
    title = "Senior Backend Engineer (Python / FastAPI)"
    desc = """
    We are seeking a Senior Backend Engineer to design scalable cloud services.
    Requirements:
    - 5+ years of software engineering experience in Python.
    - Deep knowledge of FastAPI, PostgreSQL, Docker, and REST APIs.
    - Bachelor's degree in Computer Science or related field.
    
    Nice to have:
    - Experience with Kubernetes and Redis.
    - Familiarity with AWS.
    """
    res = JDIntelligenceService.analyze_jd(title, desc)
    assert res.seniority == "SENIOR"
    assert res.min_years_exp == 5.0
    assert res.education_level == "Bachelor's"
    assert any("fastapi" in s.lower() for s in res.required_skills)
    assert any("python" in s.lower() for s in res.required_skills)
    assert res.hard_disqualifiers == []


def test_jd_intelligence_disqualifiers():
    title = "Cleared Systems Engineer"
    desc = "Must be a US Citizen. Active US Security Clearance required. 8+ years exp."
    res = JDIntelligenceService.analyze_jd(title, desc)
    assert len(res.hard_disqualifiers) > 0
    assert "US Security Clearance" in res.hard_disqualifiers[0]


def test_skill_gap_analysis_exact_and_transferable():
    candidate_skills = ["FastAPI", "PostgreSQL", "Git"]
    required_skills = ["FastAPI", "Django", "PostgreSQL", "Rust"]
    preferred_skills = ["Redis", "AWS"]

    gap = SkillGapService.analyze_skill_gaps(candidate_skills, required_skills, preferred_skills)

    # FastAPI and PostgreSQL should be proven
    assert any("fastapi" in s.lower() for s in gap.proven_skills)
    assert any("postgresql" in s.lower() for s in gap.proven_skills)

    # Django should be transferable because candidate has FastAPI
    assert any("django" in t["requested"].lower() for t in gap.transferable_skills)

    # Rust should be missing required
    assert any("rust" in s.lower() for s in gap.missing_required_skills)

    # Check learning roadmap includes resources
    assert len(gap.learning_roadmap) > 0


def test_master_profile_and_matching_flow(client):
    headers = auth(register(client, "career_intel_user@jobpilot.io"))

    # 1. Retrieve Master Profile
    res = client.get("/api/v1/profile/master", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "headline" in data
    assert "years_experience" in data

    # 2. Update Master Profile
    update_payload = {
        "headline": "Lead Platform Architect",
        "years_experience": 6.0,
        "relevant_it_experience": 6.0,
        "notice_period_days": 15,
        "preferred_locations": ["Bengaluru", "Remote"],
    }
    res = client.put("/api/v1/profile/master", json=update_payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["headline"] == "Lead Platform Architect"
    assert res.json()["years_experience"] == 6.0

    # 3. Add Work Experience
    exp_payload = {
        "company": "Infosys Tech",
        "title": "Senior Systems Engineer",
        "start_date": "2021-01-01",
        "end_date": "2024-01-01",
        "technologies": ["Python", "FastAPI", "PostgreSQL"],
        "verified_bullets": ["Engineered high-throughput API endpoints reducing latency by 40%."],
    }
    res = client.post("/api/v1/profile/experiences", json=exp_payload, headers=headers)
    assert res.status_code == 200
    exp_id = res.json()["id"]

    # 4. Add Skill
    skill_payload = {
        "name": "Rust",
        "category": "technical",
        "proficiency": "ADVANCED",
        "years": 2.0,
        "is_verified": True,
    }
    res = client.post("/api/v1/profile/skills", json=skill_payload, headers=headers)
    assert res.status_code == 200
    skill_id = res.json()["id"]

    # 5. Verify Master Profile reflects added skill and experience
    res = client.get("/api/v1/profile/master", headers=headers)
    assert res.status_code == 200
    profile_data = res.json()
    assert any(e["id"] == exp_id for e in profile_data["experiences"])
    assert any(s["id"] == skill_id for s in profile_data["skills"])

    # 6. Clean up skill and experience
    res = client.delete(f"/api/v1/profile/skills/{skill_id}", headers=headers)
    assert res.status_code == 200
    res = client.delete(f"/api/v1/profile/experiences/{exp_id}", headers=headers)
    assert res.status_code == 200
