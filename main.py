"""Command-line entry point.

    python main.py run                 # manual daily run now
    python main.py schedule            # start the daily scheduler (09:00 IST by default)
    python main.py profile [--refresh] # parse the resume and show the candidate profile
    python main.py add-job --url ...   # import a job you found
    python main.py add-jd <job> --file jd.txt
    python main.py approvals           # list applications awaiting approval / submission
    python main.py show <app_id>
    python main.py approve <app_id> | reject <app_id> | open <app_id>
    python main.py mark-submitted <app_id> --reference X --confirmation "..."
    python main.py mark-failed <app_id> --reason "..."
    python main.py search-links [--open] [--platform LinkedIn]
    python main.py report [--date YYYY-MM-DD]
    python main.py status
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import date
from pathlib import Path

from core import timeutil
from core.logging_setup import setup_logging
from core.models import Platform
from core.settings import ConfigError, Settings, load_settings


def _settings(args) -> Settings:
    s = load_settings(args.config)
    timeutil.set_timezone(s.timezone)
    s.ensure_directories()
    setup_logging(s.logs_dir, s.logging.level, console=not getattr(args, "quiet", False))
    return s


def _db(s: Settings):
    from database.db import Database

    return Database(s.db_path)


# ---- commands -------------------------------------------------------------------

def cmd_run(args) -> int:
    from runner import DailyRunner, RunAlreadyInProgress

    s = _settings(args)
    if args.mode:
        from core.settings import ApplicationMode

        s.applications.mode = ApplicationMode(args.mode)
    try:
        result = DailyRunner(s).run(trigger="manual")
    except RunAlreadyInProgress as exc:
        print(exc, file=sys.stderr)
        return 3
    print(result.summary_text)
    return 0 if result.status == "completed" else 1


def cmd_schedule(args) -> int:
    from scheduler import start_scheduler

    start_scheduler(_settings(args))
    return 0


def cmd_profile(args) -> int:
    from resume.profile_builder import ProfileBuilder

    s = _settings(args)
    p = ProfileBuilder(s).load_or_build(force=args.refresh)
    te = p["total_experience"]
    print(f"Name:        {p['name']}")
    print(f"Resume:      {p['resume']['path']}")
    print(f"Experience:  {te['years_months']} ({te['years']} years, from dates; as of {te['as_of']})")
    if te.get("discrepancy_note"):
        print(f"  Note:      {te['discrepancy_note']}")
    for r in p["experience"]:
        print(f"  - {r['title']} | {r['company']} | {r['start']} to {r['end'] or 'present'} ({r['months']} months)")
    print("Education:   " + "; ".join(filter(None, (e.get("degree") for e in p["education"]))))
    print("Training:    " + ", ".join(p["certifications"]))
    print("Skills:      " + ", ".join(s_["name"] for s_ in p["skills"]))
    print("Achievements:")
    for a in p["achievements"]:
        print(f"  - {a['text']}")
    unverified = [x["skill"] for x in p["seed_skill_verification"] if not x["found_in_resume"]]
    print("Seed skills: " + ("all found in resume" if not unverified else "NOT in resume: " + ", ".join(unverified)))
    for w in p["warnings"]:
        print(f"Warning:     {w}")
    print(f"Profile JSON: {s.cache_dir / 'candidate_profile.json'}")
    return 0


def cmd_add_job(args) -> int:
    s = _settings(args)
    record = {k: v for k, v in {
        "url": args.url, "title": args.title, "company": args.company, "location": args.location,
        "platform": args.platform, "posted_date": args.posted, "salary": args.salary, "experience": args.experience,
        "work_mode": args.work_mode, "employment_type": args.employment_type,
        "description": Path(args.jd_file).read_text(encoding="utf-8") if args.jd_file else None,
        "screening_questions": args.question or None,
    }.items() if v}
    from discovery.sources import record_from_mapping

    try:
        rec = record_from_mapping(record, source="manual")
    except ValueError as exc:
        print(f"Cannot add job: {exc}", file=sys.stderr)
        return 2
    name = f"manual_{timeutil.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    (s.inbox_dir / name).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Added {rec.platform} job to the inbox ({name}). It will be processed on the next run (python main.py run).")
    return 0


def cmd_add_jd(args) -> int:
    from core.skills import SkillTaxonomy
    from intelligence.jd_analyzer import JDAnalyzer

    s = _settings(args)
    db = _db(s)
    jobs = db.find_jobs(args.job)
    if len(jobs) != 1:
        print(f"Job '{args.job}' not found (use the job id, job key or URL shown in the report).", file=sys.stderr)
        return 2
    job = jobs[0]
    if db.get_application_by_job_key(job["job_key"]):
        print("This job already has an application; its description is kept as prepared.", file=sys.stderr)
        return 2
    text = Path(args.file).read_text(encoding="utf-8").strip()
    a = JDAnalyzer(SkillTaxonomy.from_file(s.taxonomy_path)).analyze(text, title=job["title"] or "")
    fields = {"required_skills": a.required_skills, "preferred_skills": a.preferred_skills, "education_requirements": a.education,
              "mandatory_qualifications": a.mandatory_qualifications}
    if job["exp_min_years"] is None and a.exp_min is not None:
        fields.update(exp_min_years=a.exp_min, exp_max_years=a.exp_max, experience_required=a.experience_text)
    db.set_job_description(job["id"], text, fields)
    db.add_event(event_type="DESCRIPTION_ADDED", job_id=job["id"], details=f"{len(text)} characters")
    print(f"Description saved for job {job['id']} ({job['company']} - {job['title']}); it will be re-scored on the next run.")
    return 0


def cmd_approvals(args) -> int:
    from applications.approval_manager import ApprovalManager

    s = _settings(args)
    am = ApprovalManager(s, _db(s))
    groups = [("Awaiting your approval", am.pending()), ("Ready for you to submit / verify", am.to_submit())]
    for title, rows in groups:
        print(f"\n{title} ({len(rows)})")
        for r in rows:
            print(f"  #{r['id']:<4} {r['match_score'] or 0:5.1f}  {r['platform']:<8} {r['company'][:28]:<28} {r['title'][:40]:<40} [{r['status']}]")
    print("\nCommands: show <id> | approve <id> | reject <id> | open <id> | mark-submitted <id> --reference .. --confirmation ..")
    return 0


def cmd_show(args) -> int:
    s = _settings(args)
    db = _db(s)
    app = db.get_application(args.app_id)
    if app is None:
        print(f"Application {args.app_id} not found.", file=sys.stderr)
        return 2
    txt = Path(app["package_path"]).with_suffix(".txt") if app["package_path"] else None
    if txt and txt.exists():
        print(txt.read_text(encoding="utf-8"))
    print(f"Current status: {app['status']}")
    for e in db.events_for(args.app_id):
        print(f"  {e['created_at']}  {e['event_type']:<30} {e['from_status'] or '':>18} -> {e['to_status'] or '':<18} {e['details'] or ''}")
    return 0


def _approval(args):
    from applications.application_manager import ApplicationManager
    from applications.approval_manager import ApprovalManager
    from core.llm import build_llm
    from core.skills import SkillTaxonomy
    from resume.profile_builder import ProfileBuilder

    s = _settings(args)
    db = _db(s)
    manager = None
    if args.command == "approve":
        profile = ProfileBuilder(s).load_or_build()
        cid = db.upsert_candidate(s.candidate.name, profile)
        manager = ApplicationManager(s, db, profile, cid, SkillTaxonomy.from_file(s.taxonomy_path), build_llm(s.llm)[0])
    return ApprovalManager(s, db, manager)


def cmd_approval_action(args) -> int:
    from applications.application_manager import TransitionError
    from applications.submission_verifier import VerificationError

    am = _approval(args)
    try:
        if args.command == "approve":
            print(f"#{args.app_id}: {am.approve(args.app_id, open_browser=False if args.no_open else None)}")
        elif args.command == "reject":
            am.reject(args.app_id, args.reason)
            print(f"#{args.app_id}: rejected.")
        elif args.command == "open":
            url = am.open(args.app_id)
            print(f"Opened {url} (this does not mark the application as submitted)." if url else "This job has no URL.")
        elif args.command == "mark-submitted":
            am.mark_submitted(args.app_id, args.reference, args.confirmation)
            print(f"#{args.app_id}: recorded as SUBMITTED with confirmation evidence.")
        elif args.command == "mark-failed":
            am.mark_failed(args.app_id, args.reason)
            print(f"#{args.app_id}: recorded as FAILED.")
        elif args.command == "retry":
            am.retry(args.app_id)
            print(f"#{args.app_id}: back to PENDING_MANUAL_SUBMISSION.")
    except (TransitionError, VerificationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_search_links(args) -> int:
    from platforms import enabled_platforms, get_adapter

    s = _settings(args)
    links = []
    for p in enabled_platforms(s):
        if args.platform and p != Platform.parse(args.platform):
            continue
        links += get_adapter(p, s).build_search_links(s.search)
    for link in links:
        print(f"{link.platform.value:<9} {link.title:<30} {link.location:<16} {link.url}")
    if args.open:
        if len(links) > 15 and not args.yes:
            print(f"\n{len(links)} links - add --yes to open them all, or filter with --platform.", file=sys.stderr)
            return 2
        for link in links:
            webbrowser.open(link.url, new=2)
    return 0


def cmd_report(args) -> int:
    from platforms import enabled_platforms, get_adapter
    from reports.excel_generator import ExcelReportGenerator

    s = _settings(args)
    db = _db(s)
    day = date.fromisoformat(args.date) if args.date else timeutil.today()
    cand = db.one("SELECT total_experience_months FROM candidates WHERE name=?", (s.candidate.name,))
    years = (cand["total_experience_months"] / 12) if cand else 0.0
    links = [l for p in enabled_platforms(s) for l in get_adapter(p, s).build_search_links(s.search)]
    path = ExcelReportGenerator(db, s.data_root, s.candidate.name, years, s.matching.min_match_score).generate(day, links)
    print(f"Report written: {path}")
    return 0


def cmd_status(args) -> int:
    s = _settings(args)
    db = _db(s)
    print("Recent runs:")
    for r in db.recent_runs(10):
        print(f"  #{r['id']:<4} {r['run_date']} {r['trigger']:<9} {r['status']:<11} {r['started_at'][11:19]}-{(r['finished_at'] or '')[11:19]:<8} {r['report_path'] or r['error'] or ''}")
    counts = db.query("SELECT status, COUNT(*) n FROM applications GROUP BY status ORDER BY status")
    print("Applications: " + (", ".join(f"{c['status']}={c['n']}" for c in counts) or "none"))
    jobs = db.query("SELECT pipeline_status, COUNT(*) n FROM jobs GROUP BY pipeline_status ORDER BY pipeline_status")
    print("Jobs:         " + (", ".join(f"{c['pipeline_status']}={c['n']}" for c in jobs) or "none"))
    print(f"Mode: {s.applications.mode}   Data: {s.data_root}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Daily job discovery, matching, application tracking and Excel reporting.")
    p.add_argument("--config", help="Path to settings.yaml (default: config/settings.yaml)")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="Run the daily workflow now")
    r.add_argument("--mode", choices=["DISCOVERY_ONLY", "ASSISTED", "APPROVAL_REQUIRED", "PERMITTED_AUTO_APPLY"], help="Override the application mode for this run")
    r.set_defaults(func=cmd_run)
    sub.add_parser("schedule", help="Start the daily scheduler").set_defaults(func=cmd_schedule)
    pr = sub.add_parser("profile", help="Parse the resume and show the candidate profile")
    pr.add_argument("--refresh", action="store_true", help="Rebuild even if the resume is unchanged")
    pr.set_defaults(func=cmd_profile)

    a = sub.add_parser("add-job", help="Add a job (by URL and details) to the import inbox")
    a.add_argument("--url")
    a.add_argument("--title")
    a.add_argument("--company")
    a.add_argument("--location")
    a.add_argument("--platform", help="LinkedIn, Indeed or Naukri (detected from the URL if omitted)")
    a.add_argument("--jd-file", help="Text file with the full job description")
    a.add_argument("--posted", help="Posting date (YYYY-MM-DD or '2 days ago')")
    a.add_argument("--salary")
    a.add_argument("--experience")
    a.add_argument("--work-mode")
    a.add_argument("--employment-type")
    a.add_argument("--question", action="append", help="A screening question shown on the application (repeatable)")
    a.set_defaults(func=cmd_add_job)

    d = sub.add_parser("add-jd", help="Attach a job description to a discovered job")
    d.add_argument("job", help="Job id, job key or URL")
    d.add_argument("--file", required=True)
    d.set_defaults(func=cmd_add_jd)

    sub.add_parser("approvals", help="List applications awaiting approval or submission").set_defaults(func=cmd_approvals)
    sh = sub.add_parser("show", help="Show an application package and its history")
    sh.add_argument("app_id", type=int)
    sh.set_defaults(func=cmd_show)

    for name, help_ in [("approve", "Approve an application"), ("reject", "Reject an application"), ("open", "Open the job page for manual submission"),
                        ("mark-submitted", "Record a confirmed submission"), ("mark-failed", "Record a failed submission"),
                        ("retry", "Move a failed/blocked application back to pending manual submission")]:
        c = sub.add_parser(name, help=help_)
        c.add_argument("app_id", type=int)
        if name == "approve":
            c.add_argument("--no-open", action="store_true", help="Do not open the job page")
        if name in ("reject", "mark-failed"):
            c.add_argument("--reason", required=name == "mark-failed")
        if name == "mark-submitted":
            c.add_argument("--reference", help="Application/reference ID shown by the platform")
            c.add_argument("--confirmation", help="Exact confirmation message shown by the platform")
        c.set_defaults(func=cmd_approval_action)

    sl = sub.add_parser("search-links", help="Print (or open) pre-filtered platform search links")
    sl.add_argument("--open", action="store_true")
    sl.add_argument("--yes", action="store_true")
    sl.add_argument("--platform")
    sl.set_defaults(func=cmd_search_links)

    rp = sub.add_parser("report", help="Generate a fresh Excel report (never overwrites)")
    rp.add_argument("--date", help="YYYY-MM-DD (default today)")
    rp.set_defaults(func=cmd_report)
    sub.add_parser("status", help="Show recent runs and counts").set_defaults(func=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        from resume.resume_parser import ResumeParseError

        if isinstance(exc, ResumeParseError):
            print(f"Resume error: {exc}", file=sys.stderr)
            return 2
        raise
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
