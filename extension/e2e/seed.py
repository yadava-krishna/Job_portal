"""Seed a throwaway local JobPilot database for the extension end-to-end test (fabricated data only).

Run with the project's virtualenv: python extension/e2e/seed.py <api_base> <out.json>
Creates a user through the public API, confirms a synthetic profile, then puts three ATS jobs (one per platform)
into that user's feed through the same upsert path discovery uses.
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
EMAIL, PASSWORD = "extension.e2e@example.com", "E2e-Test-Passw0rd"
JOBS = [
    ("greenhouse", "jobpilote2e", "101", "Accounts Receivable Analyst", "https://job-boards.greenhouse.io/jobpilote2e/jobs/101"),
    ("lever", "jobpilot-e2e", "0b6a3f6e-1111-4c1e-9b1e-000000000001", "Accounts Receivable Executive",
     "https://jobs.lever.co/jobpilot-e2e/0b6a3f6e-1111-4c1e-9b1e-000000000001"),
    ("ashby", "jobpilot-e2e", "7c1d2e3f-2222-4a5b-8c9d-000000000002", "Finance Associate",
     "https://jobs.ashbyhq.com/jobpilot-e2e/7c1d2e3f-2222-4a5b-8c9d-000000000002"),
]


def main() -> None:
    c = httpx.Client(timeout=60)
    r = c.post(f"{API}/auth/register", json={"email": EMAIL, "password": PASSWORD, "full_name": "Test Candidate"})
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    pdf = make_pdf(OUT.parent / "e2e-resume.pdf", SYNTHETIC_RESUME_LINES).read_bytes()
    r = c.post(f"{API}/profile/resume", headers=h, files={"file": ("Test_Candidate_Resume.pdf", pdf, "application/pdf")})
    r.raise_for_status()
    prof = r.json()["parsed"]
    prof["full_name"] = "Test Candidate"  # as a user would correct the all-caps resume header on review
    prof["linkedin_url"] = "https://www.linkedin.com/in/test-candidate-e2e"
    prof["github_url"] = "https://github.com/test-candidate-e2e"
    for e in prof["experience"][:1]:
        e["is_current"] = True
    c.put(f"{API}/profile", headers=h, json=prof).raise_for_status()
    c.put(f"{API}/profile/verified-facts", headers=h, json={"notice_period": "30 days", "expected_ctc": "9 LPA",
                                                            "requires_sponsorship": False, "willing_to_relocate": True}).raise_for_status()
    c.put(f"{API}/preferences", headers=h, json={"job_titles": ["Accounts Receivable Analyst"], "locations": ["Bengaluru"],
                                                 "min_match_score": 0}).raise_for_status()

    # Put the jobs in the feed exactly as discovery would (normalised job + source link + user job).
    from backend.config import get_settings
    from backend.db import init_engine, session_factory
    from backend.models import User, UserJob
    from backend.services import discovery_service
    from backend.services.normalization import NormalizedJob

    init_engine(get_settings().database_url)
    with session_factory()() as db:
        user = db.query(User).filter(User.email == EMAIL).one()
        ids = {}
        for ats, board, jid, title, url in JOBS:
            nj = NormalizedJob(source=ats, source_key=f"{ats}:{board}:{jid}", platform=ats.capitalize(), company="JobPilot E2E Co",
                               title=title, job_url=url, external_job_id=jid, location="Bengaluru", description="Synthetic test job.")
            job, _ = discovery_service.upsert_normalized(db, nj)
            db.flush()
            uj = UserJob(user_id=user.id, job_id=job.id, source=ats, status="new")
            db.add(uj)
            db.flush()
            ids[ats] = {"user_job_id": uj.id, "url": url}
        db.commit()
    OUT.write_text(json.dumps({"email": EMAIL, "password": PASSWORD, "jobs": ids, "resume_bytes": len(pdf)}))


if __name__ == "__main__":
    main()
