"""Copy the CLI's SQLite history into one portal user's account.

    DATABASE_URL=... python -m backend.scripts.import_sqlite --sqlite ~/Job_Applications/database/job_applications.db \
        --email you@example.com [--dry-run]

The SQLite file is opened read-only and never modified. Re-running is safe: jobs and
applications are matched by job key / (user, job) and not duplicated.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select

from backend.config import get_settings
from backend.db import init_engine, session_factory
from backend.models import Application, ApplicationEvent, CandidateProfile, Job, User, UserJob

STATUS_MAP = {
    "SUBMITTED": "SUBMITTED", "FAILED": "FAILED", "BLOCKED": "FAILED", "REJECTED_BY_CANDIDATE": "WITHDRAWN",
    "AWAITING_APPROVAL": "PREPARED", "APPROVED": "PREPARED", "PENDING_MANUAL_SUBMISSION": "PREPARED",
    "SUBMITTING": "CONFIRMATION_PENDING", "NEEDS_VERIFICATION": "CONFIRMATION_PENDING",
}
FEED_STATUS = {"SHORTLISTED": "shortlisted", "LIMIT_DEFERRED": "shortlisted", "APPLICATION_CREATED": "applied"}


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _list(value: str | None) -> list:
    try:
        return json.loads(value or "[]")
    except json.JSONDecodeError:
        return []


def run(sqlite_path: Path, email: str, dry_run: bool) -> dict[str, int]:
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    init_engine(get_settings().database_url)
    db = session_factory()()
    counts = {"jobs": 0, "feed": 0, "applications": 0, "events": 0, "profile": 0}
    try:
        user = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
        if user is None:
            raise SystemExit(f"No portal user with email {email}. Register in the portal first.")

        cand = src.execute("SELECT * FROM candidates ORDER BY id LIMIT 1").fetchone()
        prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
        if cand and (prof is None or prof.parsed_profile is None):
            prof = prof or CandidateProfile(user_id=user.id, verified_facts={})
            prof.parsed_profile = json.loads(cand["profile_json"])
            prof.experience_months = cand["total_experience_months"]
            db.add(prof)
            counts["profile"] = 1

        job_ids: dict[int, int] = {}
        uj_ids: dict[int, int] = {}
        for r in src.execute("SELECT * FROM jobs ORDER BY id"):
            job = db.execute(select(Job).where(Job.job_key == r["job_key"])).scalar_one_or_none()
            if job is None:
                job = Job(job_key=r["job_key"], platform=r["platform"], external_job_id=r["platform_job_id"], fingerprint=r["fingerprint"],
                          company=r["company"] or "", title=r["title"] or "", location=r["location"], work_mode=r["work_mode"],
                          employment_type=r["employment_type"], experience_required=r["experience_required"],
                          experience_min=r["exp_min_years"], experience_max=r["exp_max_years"], salary_range=r["salary_range"],
                          salary_min_lpa=r["salary_min_lpa"], salary_max_lpa=r["salary_max_lpa"], description=r["description"],
                          required_skills=_list(r["required_skills"]), preferred_skills=_list(r["preferred_skills"]),
                          education_requirements=_list(r["education_requirements"]), mandatory_qualifications=_list(r["mandatory_qualifications"]),
                          screening_questions=_list(r["screening_questions"]), verification_flags=_list(r["verification_flags"]),
                          job_url=r["url"], posted_at=date.fromisoformat(r["posted_date"]) if r["posted_date"] else None,
                          posted_at_source="user_provided" if r["posted_date"] else None, source=r["source"] or "import_inbox",
                          application_method=r["application_method"])
                db.add(job)
                db.flush()
                counts["jobs"] += 1
            job_ids[r["id"]] = job.id
            uj = db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == job.id)).unique().scalar_one_or_none()
            if uj is None:
                match = json.loads(r["match_json"]) if r["match_json"] else None
                elig = json.loads(r["eligibility_json"]) if r["eligibility_json"] else {}
                uj = UserJob(user_id=user.id, job_id=job.id, source=r["source"] or "import_inbox",
                             status=FEED_STATUS.get(r["pipeline_status"], "new"), match_score=r["match_score"],
                             match_category=r["match_category"], match=match,
                             matching_skills=(match or {}).get("matching_skills", []), missing_skills=(match or {}).get("missing_skills", []),
                             eligibility_status=r["eligibility_status"], eligibility_reasons=elig.get("reasons", []),
                             scoring_method=r["scoring_method"], scored_at=_dt(r["scored_at"]),
                             discovered_at=_dt(r["first_seen_at"]) or datetime.now(timezone.utc), seen_count=r["seen_count"], notes=r["notes"])
                db.add(uj)
                db.flush()
                counts["feed"] += 1
            uj_ids[r["id"]] = uj.id

        for a in src.execute("SELECT * FROM applications ORDER BY id"):
            job_id = job_ids.get(a["job_id"])
            if job_id is None:
                continue
            existing = db.execute(select(Application).where(Application.user_id == user.id, Application.job_id == job_id)).unique().scalar_one_or_none()
            if existing is not None:
                continue
            status = STATUS_MAP.get(a["status"], "PREPARED")
            app = Application(user_id=user.id, job_id=job_id, user_job_id=uj_ids.get(a["job_id"]), status=status,
                              stage="applied" if status == "SUBMITTED" else None, resume_used=Path(a["resume_path"] or "").name or None,
                              cover_letter=a["cover_letter"], screening_answers=_list(a["screening_json"]), checklist=[],
                              reference_id=a["reference_id"], confirmation_text=a["confirmation_text"],
                              confirmation_source=f"cli:{a['confirmation_source']}" if a["confirmation_source"] else None,
                              submitted_at=_dt(a["submitted_at"]), created_at=_dt(a["created_at"]), notes=a["notes"])
            db.add(app)
            db.flush()
            counts["applications"] += 1
            if status == "SUBMITTED" and app.user_job_id:
                db.get(UserJob, app.user_job_id).status = "applied"
            for e in src.execute("SELECT * FROM application_events WHERE application_id=? ORDER BY id", (a["id"],)):
                db.add(ApplicationEvent(application_id=app.id, user_id=user.id, event_type=f"CLI_{e['event_type']}",
                                        from_status=e["from_status"], to_status=e["to_status"], details=e["details"], created_at=_dt(e["created_at"])))
                counts["events"] += 1
        if dry_run:
            db.rollback()
        else:
            db.commit()
        return counts
    finally:
        db.close()
        src.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sqlite", required=True, type=Path)
    p.add_argument("--email", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    if not args.sqlite.exists():
        print(f"{args.sqlite} not found", file=sys.stderr)
        return 2
    counts = run(args.sqlite.expanduser(), args.email, args.dry_run)
    print(("DRY RUN - nothing written. " if args.dry_run else "") + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
