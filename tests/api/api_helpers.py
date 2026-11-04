"""Helpers shared by the API tests."""

from __future__ import annotations

PASSWORD = "Str0ngPassw0rd"

AR_JD = """About the role
We are hiring an Accounts Receivable Analyst for our US healthcare team.
Responsibilities:
- Perform payment posting using remittance information
- Follow up on unpaid claims with insurance companies
- Prepare Excel reports using PivotTables for management
Requirements:
- 3-6 years of experience in accounts receivable
- Bachelor's degree in Commerce
Good to have:
- Power BI
Full time role. Please attach a cover letter."""


def register(client, email: str, password: str = PASSWORD) -> dict:
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": email.split("@")[0]})
    assert r.status_code == 201, r.text
    return r.json()


def auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def onboard(client, email: str, resume: bytes, *, locations=("Bengaluru",), titles=("Accounts Receivable Analyst",)) -> dict:
    """Register and complete onboarding; returns auth headers."""
    h = auth(register(client, email))
    r = client.post("/api/v1/profile/resume", headers=h, files={"file": ("cv.pdf", resume, "application/pdf")})
    assert r.status_code == 201, r.text
    parsed = r.json()["parsed"]
    assert client.put("/api/v1/profile", headers=h, json=parsed).status_code == 200
    prefs = {"job_titles": list(titles), "locations": list(locations), "work_modes": ["Remote", "Hybrid", "On-site"],
             "employment_types": ["Full-time"], "min_match_score": 60}
    assert client.put("/api/v1/preferences", headers=h, json=prefs).status_code == 200
    plats = {"platforms": [{"platform": p, "enabled": True, "discovery_sources": ["user_job_url", "alert_email"]}
                           for p in ("LinkedIn", "Indeed", "Naukri")]}
    assert client.put("/api/v1/platforms/preferences", headers=h, json=plats).status_code == 200
    return h


def import_job(client, h, **kw) -> dict:
    body = {"url": "https://www.linkedin.com/jobs/view/4000000001/", "title": "Accounts Receivable Analyst",
            "company": "Acme Health", "location": "Bengaluru", "description": AR_JD, "posted_date": "today",
            "screening_questions": ["What is your current CTC?", "Total years of experience?"]}
    body.update(kw)
    r = client.post("/api/v1/jobs/import", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()
