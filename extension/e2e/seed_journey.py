"""Seed a throwaway local JobPilot database for the Smart Apply journey test (fabricated data only).

Run with the project's virtualenv: python extension/e2e/seed_journey.py <api_base> <out.json>

A brand-new user with a confirmed profile but NO saved answers (scenario A starts from scratch), and six jobs in the
feed through the same upsert path discovery uses:
  A greenhouse  first application: answers asked, then remembered
  B lever       returning user: remembered answers reused
  C ashby       complex form: radios, ranges, a required question, validation
  D greenhouse  interrupted application (tab closed), resumed safely
  E lever       ambiguous outcome after submitting (no confirmation page)
  F linkedin    unsupported platform: native hand-off and the user's own report
All employer pages are local fixtures served at the real ATS addresses by request interception; LinkedIn is a stub.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from support import SYNTHETIC_RESUME_LINES, make_pdf  # noqa: E402

API, OUT = sys.argv[1].rstrip("/") + "/api/v1", Path(sys.argv[2])
EMAIL, PASSWORD = "journey.e2e@example.com", "Journey-Test-Passw0rd"
JOBS = {
    "A": ("greenhouse", "jobpilote2e", "101", "Accounts Receivable Analyst", "https://job-boards.greenhouse.io/jobpilote2e/jobs/101"),
    "B": ("lever", "jobpilot-e2e", "0b6a3f6e-1111-4c1e-9b1e-000000000001", "Accounts Receivable Executive",
          "https://jobs.lever.co/jobpilot-e2e/0b6a3f6e-1111-4c1e-9b1e-000000000001"),
    "C": ("ashby", "jobpilot-e2e", "7c1d2e3f-2222-4a5b-8c9d-000000000002", "Finance Associate",
          "https://jobs.ashbyhq.com/jobpilot-e2e/7c1d2e3f-2222-4a5b-8c9d-000000000002"),
    "D": ("greenhouse", "jobpilote2e", "102", "Billing Specialist", "https://job-boards.greenhouse.io/jobpilote2e/jobs/102"),
    "E": ("lever", "jobpilot-e2e", "0b6a3f6e-1111-4c1e-9b1e-000000000005", "Collections Analyst",
          "https://jobs.lever.co/jobpilot-e2e/0b6a3f6e-1111-4c1e-9b1e-000000000005"),
}
COMPANIES = {"A": "Northwind Payments", "B": "Contoso Health", "C": "Fabrikam Finance", "D": "Northwind Payments", "E": "Tailspin Labs"}


def main() -> None:
    c = httpx.Client(timeout=60)
    r = c.post(f"{API}/auth/register", json={"email": EMAIL, "password": PASSWORD, "full_name": "Test Candidate"})
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pdf = make_pdf(OUT.parent / "journey-resume.pdf", SYNTHETIC_RESUME_LINES).read_bytes()
    r = c.post(f"{API}/profile/resume", headers=h, files={"file": ("Test_Candidate_Resume.pdf", pdf, "application/pdf")})
    r.raise_for_status()
    prof = r.json()["parsed"]
    prof["full_name"] = "Test Candidate"
    prof["linkedin_url"] = "https://www.linkedin.com/in/test-candidate-e2e"
    for e in prof["experience"][:1]:
        e["is_current"] = True
    c.put(f"{API}/profile", headers=h, json=prof).raise_for_status()
    # A second resume, so choosing a non-default resume can be shown.
    c.post(f"{API}/profile/resume", headers=h, params={"make_default": False, "name": "Resume - Finance roles"},
           files={"file": ("Test_Candidate_Finance.pdf", pdf, "application/pdf")}).raise_for_status()
    c.put(f"{API}/preferences", headers=h, json={"job_titles": ["Accounts Receivable Analyst"], "locations": ["Bengaluru"],
                                                 "min_match_score": 0}).raise_for_status()
    c.put(f"{API}/platforms/preferences", headers=h, json={"platforms": [
        {"platform": p, "enabled": True, "discovery_sources": ["user_job_url"]} for p in ("LinkedIn", "Indeed", "Naukri")]}).raise_for_status()

    from backend.config import get_settings
    from backend.db import init_engine, session_factory
    from backend.models import User, UserJob
    from backend.services import discovery_service
    from backend.services.normalization import NormalizedJob

    init_engine(get_settings().database_url)
    ids = {}
    with session_factory()() as db:
        user = db.query(User).filter(User.email == EMAIL).one()
        for key, (ats, board, jid, title, url) in JOBS.items():
            nj = NormalizedJob(source=ats, source_key=f"{ats}:{board}:{jid}", platform=ats.capitalize(), company=COMPANIES[key],
                               title=title, job_url=url, external_job_id=jid, location="Bengaluru",
                               description="Synthetic test job for the Smart Apply journey. Accounts receivable, billing and "
                                           "collections work with Excel reporting. 3+ years of experience.")
            job, _ = discovery_service.upsert_normalized(db, nj)
            db.flush()
            uj = UserJob(user_id=user.id, job_id=job.id, source=ats, status="new", match_score={"A": 86, "B": 81, "C": 74, "D": 78, "E": 69}[key])
            db.add(uj)
            db.flush()
            ids[key] = {"user_job_id": uj.id, "url": url, "ats": ats, "title": title, "company": COMPANIES[key]}
        db.commit()
    # F: a LinkedIn listing the user pasted in (never fetched; applying happens on LinkedIn itself).
    r = c.post(f"{API}/jobs/import", headers=h, json={
        "url": "https://www.linkedin.com/jobs/view/4999999999/", "title": "Accounts Receivable Lead", "company": "Wingtip Retail",
        "location": "Bengaluru", "posted_date": "today",
        "description": "Lead the accounts receivable team. Collections, cash application and month-end reporting. 5+ years.",
        "screening_questions": ["What is your notice period?", "How many years of accounts receivable experience do you have?"]})
    r.raise_for_status()
    ids["F"] = {"user_job_id": r.json()["user_job_ids"][0], "url": "https://www.linkedin.com/jobs/view/4999999999/", "ats": "linkedin",
                "title": "Accounts Receivable Lead", "company": "Wingtip Retail"}
    OUT.write_text(json.dumps({"email": EMAIL, "password": PASSWORD, "jobs": ids}))


if __name__ == "__main__":
    main()
