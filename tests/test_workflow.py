"""Database, application workflow, Excel, runner and scheduler tests."""

import json
import os
import threading
from datetime import datetime

import openpyxl
import pytest

from conftest import FakeLLM, inbox_job, llm_response
from applications.application_manager import TransitionError
from applications.approval_manager import ApprovalManager
from applications.submission_verifier import VerificationError
from core import timeutil
from core.models import ApplicationStatus
from database.db import Database, DuplicateApplicationError
from discovery.sources import EmailAlertSource, ImportInboxSource
from reports.excel_generator import _clean, report_path_for
from runner import DailyRunner, RunAlreadyInProgress, RunLock
from scheduler import should_catch_up
from test_platforms_and_sources import FakeIMAP


def put_inbox(settings, jobs, name="jobs.json"):
    (settings.inbox_dir / name).write_text(json.dumps(jobs))


def run(settings, **kw):
    return DailyRunner(settings, llm=kw.pop("llm", None), retry_base_delay=0, **kw).run()


def db_of(settings):
    return Database(settings.db_path)


# ---- end to end ----------------------------------------------------------------

def test_full_run_creates_report_and_approval_task(settings):
    put_inbox(settings, [
        inbox_job(),
        inbox_job(url="https://www.linkedin.com/jobs/view/4000000001/?trk=dup"),  # same job, tracking params
        inbox_job(url="https://in.indeed.com/viewjob?jk=0123456789abcdef", title="Director of Finance", company="Globex"),
        inbox_job(url="https://www.naukri.com/job-listings-mis-analyst-x-031125099999", title="MIS Analyst", company="Initech", description=None),
    ])
    result = run(settings)
    assert result.status == "completed"
    assert result.stats["platforms"]["LinkedIn"]["duplicates_skipped"] == 1
    assert os.path.exists(result.report_path)

    db = db_of(settings)
    statuses = {r["title"]: r["pipeline_status"] for r in db.query("SELECT title, pipeline_status FROM jobs")}
    assert statuses == {"Accounts Receivable Analyst": "APPLICATION_CREATED", "Director of Finance": "NOT_ELIGIBLE", "MIS Analyst": "NEEDS_DESCRIPTION"}
    apps = db.list_applications()
    assert len(apps) == 1 and apps[0]["status"] == "AWAITING_APPROVAL"
    assert apps[0]["submitted_at"] is None

    wb = openpyxl.load_workbook(result.report_path)
    assert wb.sheetnames == ["Application Details", "Daily Summary", "Job Analysis", "Errors and Logs", "Search Links"]
    ws = wb["Application Details"]
    assert ws.max_column == 35 and ws.max_row == 4
    assert ws.freeze_panes == "A2" and ws.auto_filter.ref
    assert ws["I2"].hyperlink is not None
    assert ws.conditional_formatting
    assert not list(settings.inbox_dir.glob("*.json"))  # archived


def test_second_run_never_duplicates_applications(settings):
    put_inbox(settings, [inbox_job()])
    run(settings)
    put_inbox(settings, [inbox_job(url="https://www.linkedin.com/jobs/view/4000000001/?refId=again")], name="again.json")
    r2 = run(settings)
    assert r2.stats["platforms"]["LinkedIn"]["duplicates_skipped"] == 1
    db = db_of(settings)
    assert db.one("SELECT COUNT(*) FROM applications")[0] == 1
    assert db.one("SELECT seen_count FROM jobs")[0] == 2
    reports = sorted(p.name for p in (settings.data_root / "2026").rglob("*.xlsx")) if (settings.data_root / "2026").exists() else \
        sorted(p.name for p in settings.data_root.rglob("*.xlsx"))
    assert len(reports) == 2 and reports[1].endswith("_run2.xlsx")


def test_zero_jobs_still_creates_report(settings):
    r = run(settings)
    assert r.status == "completed" and os.path.exists(r.report_path)
    ws = openpyxl.load_workbook(r.report_path)["Daily Summary"]
    assert ws["B5"].value == 0


def test_llm_scoring_used_when_available(settings):
    put_inbox(settings, [inbox_job()])
    llm = FakeLLM(llm_response())
    run(settings, llm=llm)
    assert llm.calls == 1
    db = db_of(settings)
    assert db.one("SELECT scoring_method FROM jobs")[0].startswith("llm")


def test_discovery_only_mode_prepares_nothing(settings_factory):
    s = settings_factory(applications__mode="DISCOVERY_ONLY")
    put_inbox(s, [inbox_job()])
    run(s)
    db = db_of(s)
    assert db.one("SELECT COUNT(*) FROM applications")[0] == 0
    assert db.one("SELECT pipeline_status FROM jobs")[0] == "SHORTLISTED"


def test_permitted_auto_apply_falls_back_to_assisted(settings_factory):
    s = settings_factory(applications__mode="PERMITTED_AUTO_APPLY")
    put_inbox(s, [inbox_job()])
    run(s)
    db = db_of(s)
    app = db.list_applications()[0]
    assert app["status"] == "PENDING_MANUAL_SUBMISSION"
    assert any(e["event_type"] == "AUTO_APPLY_UNAVAILABLE" for e in db.events_for(app["id"]))


def test_daily_limit_defers_jobs(settings_factory):
    s = settings_factory(applications__max_per_day=1)
    put_inbox(s, [inbox_job(), inbox_job(url="https://www.linkedin.com/jobs/view/4000000002/", company="Other Health")])
    r = run(s)
    assert r.stats["applications_created"] == 1 and r.stats["deferred"] == 1
    assert db_of(s).one("SELECT COUNT(*) FROM jobs WHERE pipeline_status='LIMIT_DEFERRED'")[0] == 1


def test_cross_platform_duplicate_blocked(settings):
    put_inbox(settings, [inbox_job(), inbox_job(url="https://www.naukri.com/job-listings-ar-analyst-acme-031125011111", company="Acme Health Pvt Ltd")])
    r = run(settings)
    assert r.stats["applications_created"] == 1 and r.stats["cross_platform_duplicates"] == 1


def test_disabled_platform_records_are_not_dropped(settings_factory):
    s = settings_factory(platforms__naukri__enabled=False)
    put_inbox(s, [inbox_job(url="https://www.naukri.com/job-listings-x-031125011111")], name="naukri.json")
    run(s)
    assert (s.inbox_dir / "naukri.json").exists()
    assert db_of(s).one("SELECT COUNT(*) FROM run_errors WHERE error_type='PLATFORM_DISABLED'")[0] == 1


def test_email_confirmation_marks_submitted(settings, monkeypatch):
    monkeypatch.setenv("IMAP_USERNAME", "u")
    monkeypatch.setenv("IMAP_PASSWORD", "p")
    put_inbox(settings, [inbox_job()])
    run(settings)
    imap = FakeIMAP([("LinkedIn <jobs-noreply@linkedin.com>", "Your application was sent to Acme Health", "<p>Accounts Receivable Analyst</p>")])
    sources = [ImportInboxSource(settings.inbox_dir), EmailAlertSource(settings.sources.email_alerts, imap_factory=lambda: imap)]
    r = run(settings, sources=sources)
    assert r.stats["confirmed_by_email"] == 1
    app = db_of(settings).list_applications()[0]
    assert app["status"] == "SUBMITTED" and app["confirmation_source"].startswith("email:")


# ---- approvals & state machine -------------------------------------------------------

def test_approval_flow_requires_evidence(settings):
    put_inbox(settings, [inbox_job()])
    run(settings)
    db = db_of(settings)
    am = ApprovalManager(settings, db)
    app_id = am.pending()[0]["id"]
    am.approve(app_id, open_browser=False)
    assert db.get_application(app_id)["status"] == "PENDING_MANUAL_SUBMISSION"
    with pytest.raises(VerificationError):
        am.mark_submitted(app_id, None, None)
    with pytest.raises(VerificationError):
        am.mark_submitted(app_id, None, "opened the page")
    assert db.get_application(app_id)["status"] == "PENDING_MANUAL_SUBMISSION"
    am.mark_submitted(app_id, "REF-1", None)
    assert db.get_application(app_id)["status"] == "SUBMITTED"
    with pytest.raises(TransitionError):
        am.reject(app_id)


def test_opening_job_is_not_applying(settings, monkeypatch):
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)
    put_inbox(settings, [inbox_job()])
    run(settings)
    db = db_of(settings)
    am = ApprovalManager(settings, db)
    app_id = am.pending()[0]["id"]
    am.open(app_id)
    assert db.get_application(app_id)["status"] == "AWAITING_APPROVAL"


def test_unique_constraint_blocks_second_application(settings):
    put_inbox(settings, [inbox_job()])
    run(settings)
    db = db_of(settings)
    app = db.list_applications()[0]
    with pytest.raises(DuplicateApplicationError):
        db.create_application(app["job_id"], app["candidate_id"], ApplicationStatus.AWAITING_APPROVAL, "APPROVAL_REQUIRED", None)


# ---- recovery, locking, scheduling ------------------------------------------------------

def test_lock_prevents_overlapping_runs(settings):
    lock = RunLock(settings.data_root / ".run.lock")
    lock.acquire()
    try:
        with pytest.raises(RunAlreadyInProgress):
            run(settings)
    finally:
        lock.release()


def test_stale_running_run_is_recovered(settings):
    db = db_of(settings)
    rid = db.start_run("scheduled")
    db.conn.execute("UPDATE daily_runs SET pid=999999 WHERE id=?", (rid,))
    db.close()
    run(settings)
    assert db_of(settings).one("SELECT status FROM daily_runs WHERE id=?", (rid,))[0] == "interrupted"


def test_stop_request_marks_run_interrupted(settings):
    put_inbox(settings, [inbox_job()])
    stop = threading.Event()
    stop.set()
    r = DailyRunner(settings, llm=None, stop_event=stop).run()
    assert r.status == "interrupted"
    assert list(settings.inbox_dir.glob("*.json"))  # nothing consumed; the next run picks it up


def test_catch_up_decision(settings):
    db = db_of(settings)
    tz = timeutil.tz()
    assert not should_catch_up(db, settings, datetime(2026, 11, 4, 8, 0, tzinfo=tz))
    assert should_catch_up(db, settings, datetime(2026, 11, 4, 10, 0, tzinfo=tz))
    db.conn.execute("INSERT INTO daily_runs (run_date, trigger, status, started_at) VALUES ('2026-11-04', 'scheduled', 'completed', 'x')")
    assert not should_catch_up(db, settings, datetime(2026, 11, 4, 10, 0, tzinfo=tz))


# ---- excel helpers -------------------------------------------------------------------

def test_report_never_overwrites(tmp_path):
    from datetime import date

    day = date(2026, 11, 3)
    p1 = report_path_for(tmp_path, day)
    assert p1 == tmp_path / "2026" / "November" / "2026-11-03_Applications.xlsx"
    p1.parent.mkdir(parents=True)
    p1.write_text("x")
    assert report_path_for(tmp_path, day).name == "2026-11-03_Applications_run2.xlsx"


def test_excel_cell_sanitising():
    assert not _clean("=HYPERLINK(\"http://x\")").startswith("=")
    assert _clean("-5 years") == "-5 years"
    assert _clean("bad\x07char") == "badchar"
    assert len(_clean("a" * 40000)) < 32_100


def test_log_redaction():
    from core.logging_setup import redact

    text = redact("user test.candidate@example.com phone +91 9876543210 key sk-ant-abcdef123456 password=hunter2")
    assert "@" not in text and "9876543210" not in text and "sk-ant-abc" not in text and "hunter2" not in text
