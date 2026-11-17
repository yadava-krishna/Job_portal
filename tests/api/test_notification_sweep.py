"""Phase 5 in-app alerts: the notification_sweep job (follow-ups, interviews, unfinished applications, closed listings,
failed discovery runs). Every kind is created once and never repeated by later sweeps."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from itertools import count

from sqlalchemy import select, update

from api_helpers import auth, register

API = "/api/v1"
_n = count(1)


def _user(client, email):
    from backend.db import session_factory
    from backend.models import User

    register(client, email)
    with session_factory()() as db:
        return db.execute(select(User.id).where(User.email == email)).scalar_one()


def _job(db, *, title="Data Analyst", company="Acme", **kw):
    from backend.models import Job

    i = next(_n)
    job = Job(job_key=f"test:{i}", platform="greenhouse", source="greenhouse", title=title, company=company,
              job_url=f"https://boards.greenhouse.io/acme/jobs/{i}", **kw)
    db.add(job)
    db.flush()
    return job


def _user_job(db, uid, job, **kw):
    from backend.models import UserJob

    uj = UserJob(user_id=uid, job_id=job.id, source=job.source, **kw)
    db.add(uj)
    db.flush()
    return uj


def _app(db, uid, job, status="SUBMITTED", **kw):
    from backend.models import Application

    a = Application(user_id=uid, job_id=job.id, status=status, **kw)
    db.add(a)
    db.flush()
    return a


def _sweep():
    from backend.db import session_factory
    from backend.services import notification_sweep

    with session_factory()() as db:
        return notification_sweep.run(db)


def _notes(uid, kind=None):
    from backend.db import session_factory
    from backend.models import Notification

    with session_factory()() as db:
        stmt = select(Notification).where(Notification.user_id == uid)
        if kind:
            stmt = stmt.where(Notification.kind == kind)
        return list(db.execute(stmt.order_by(Notification.id)).scalars())


def _now():
    return datetime.now(timezone.utc)


def test_follow_up_due_once_for_open_applications(client):
    from backend.db import session_factory
    from core import timeutil

    uid = _user(client, "followup@example.com")
    with session_factory()() as db:
        due = _app(db, uid, _job(db), follow_up_at=_now() - timedelta(hours=1))
        later_today = datetime.combine(timeutil.today(), time(23, 58), tzinfo=timeutil.tz())
        today = _app(db, uid, _job(db, company="Globex", title="BI Analyst"), follow_up_at=later_today)
        _app(db, uid, _job(db, company="Initech"), follow_up_at=_now() - timedelta(hours=2), stage="rejected")
        _app(db, uid, _job(db, company="Umbrella"), follow_up_at=_now() - timedelta(hours=2), status="WITHDRAWN")
        _app(db, uid, _job(db, company="Hooli"), follow_up_at=_now() + timedelta(days=3))
        db.commit()
        due_id, today_id = due.id, today.id

    first = _sweep()
    assert first["follow_up_due"] == 2
    notes = {n.link: n for n in _notes(uid, "follow_up_due")}
    assert set(notes) == {f"/applied?app={due_id}", f"/applied?app={today_id}"}
    assert notes[f"/applied?app={due_id}"].title == "Follow up with Acme about Data Analyst"
    assert notes[f"/applied?app={today_id}"].body == "Your follow-up date is today."
    assert _sweep()["follow_up_due"] == 0
    assert len(_notes(uid, "follow_up_due")) == 2


def test_upcoming_interview_within_24_hours(client):
    from backend.db import session_factory
    from backend.models import Interview

    uid = _user(client, "interview@example.com")
    with session_factory()() as db:
        job = _job(db, company="Acme", title="Data Analyst")
        uj = _user_job(db, uid, job)
        a = _app(db, uid, job, user_job_id=uj.id, stage="interview")
        soon = Interview(user_id=uid, application_id=a.id, round_name="Technical round", scheduled_at=_now() + timedelta(hours=3))
        db.add_all([soon, Interview(user_id=uid, application_id=a.id, scheduled_at=_now() + timedelta(hours=30)),
                    Interview(user_id=uid, application_id=a.id, scheduled_at=_now() + timedelta(hours=2), outcome="cancelled")])
        db.commit()
        soon_id, uj_id = soon.id, uj.id

    assert _sweep()["interview_upcoming"] == 1
    [n] = _notes(uid, "interview_upcoming")
    assert n.title.startswith("Interview with Acme ") and n.link == f"/interview-prep?job={uj_id}"
    assert "Technical round for Data Analyst" in n.body
    assert _sweep()["interview_upcoming"] == 0
    # Rescheduling gives a fresh reminder for the new time.
    with session_factory()() as db:
        db.get(Interview, soon_id).scheduled_at = _now() + timedelta(hours=5)
        db.commit()
    assert _sweep()["interview_upcoming"] == 1
    assert _sweep()["interview_upcoming"] == 0


def test_incomplete_applications(client):
    from backend.db import session_factory
    from backend.models import Application

    uid = _user(client, "incomplete@example.com")
    with session_factory()() as db:
        stale = _app(db, uid, _job(db, company="Acme", title="Data Analyst"), status="PREPARED")
        fresh = _app(db, uid, _job(db, company="Globex"), status="OPENED")
        opened = _app(db, uid, _job(db, company="Initech"), status="OPENED")
        uncertain = _app(db, uid, _job(db, company="Hooli"), status="CONFIRMATION_PENDING", apply_state="submission_uncertain")
        _app(db, uid, _job(db, company="Umbrella"), status="SUBMITTED")
        db.flush()
        old = _now() - timedelta(days=4)
        db.execute(update(Application).where(Application.id.in_([stale.id, opened.id])).values(updated_at=old))
        db.commit()
        ids = {"stale": stale.id, "fresh": fresh.id, "opened": opened.id, "uncertain": uncertain.id}

    assert _sweep()["application_incomplete"] == 3
    notes = {n.link: n for n in _notes(uid, "application_incomplete")}
    assert set(notes) == {f"/applied?app={ids[k]}" for k in ("stale", "opened", "uncertain")}
    assert notes[f"/applied?app={ids['stale']}"].title == "Finish your application to Acme for Data Analyst"
    assert notes[f"/applied?app={ids['uncertain']}"].title == "Check whether your application to Hooli went through"
    assert _sweep()["application_incomplete"] == 0
    assert len(_notes(uid, "application_incomplete")) == 3


def test_closed_or_expired_listings(client):
    from backend.db import session_factory

    uid = _user(client, "closed@example.com")
    with session_factory()() as db:
        saved_closed = _user_job(db, uid, _job(db, title="Data Analyst", company="Acme", closed_at=_now()), is_saved=True)
        draft_job = _job(db, title="BI Analyst", company="Globex", is_expired=True)
        draft = _app(db, uid, draft_job, status="PREPARED")
        db.flush()
        from backend.models import Application
        db.execute(update(Application).where(Application.id == draft.id).values(updated_at=_now() - timedelta(days=5)))
        _user_job(db, uid, _job(db, company="PastDeadline", expires_at=date.today() - timedelta(days=2)), is_saved=True)
        applied_job = _job(db, company="Initech", closed_at=_now())
        _user_job(db, uid, applied_job, is_saved=True)
        _app(db, uid, applied_job, status="SUBMITTED")
        _user_job(db, uid, _job(db, company="Dismissed", closed_at=_now()), is_saved=True, status="dismissed")
        _user_job(db, uid, _job(db, company="NotSaved", closed_at=_now()))
        _user_job(db, uid, _job(db, company="StillOpen"), is_saved=True)
        db.commit()
        saved_id, draft_id = saved_closed.id, draft.id

    first = _sweep()
    assert first["listing_closed"] == 3
    notes = {n.link: n for n in _notes(uid, "listing_closed")}
    assert notes[f"/discover?job={saved_id}"].title == "Data Analyst at Acme is no longer listed"
    assert "You saved this job." in notes[f"/discover?job={saved_id}"].body
    assert notes[f"/applied?app={draft_id}"].title == "BI Analyst at Globex has probably expired"
    assert any(n.title.startswith("Applications for ") and "PastDeadline" in n.title for n in notes.values())
    # The unsubmitted draft on an expired job is not nagged to be finished.
    assert first["application_incomplete"] == 0
    assert _sweep()["listing_closed"] == 0
    assert len(_notes(uid, "listing_closed")) == 3


def test_many_closed_listings_become_one_summary(client):
    from backend.db import session_factory

    uid = _user(client, "many-closed@example.com")
    with session_factory()() as db:
        for i in range(5):
            _user_job(db, uid, _job(db, company=f"Co{i}", closed_at=_now()), is_saved=True)
        db.commit()
    assert _sweep()["listing_closed"] == 1
    notes = _notes(uid, "listing_closed")
    unread = [n for n in notes if n.read_at is None]
    assert len(notes) == 6 and len(unread) == 1
    assert unread[0].title == "5 jobs you saved or started applying for are no longer open" and unread[0].link == "/saved"
    assert _sweep()["listing_closed"] == 0 and len(_notes(uid, "listing_closed")) == 6


def test_failed_discovery_runs_notify_once_per_run(client):
    from backend.db import session_factory
    from backend.models import DiscoveryRun

    uid = _user(client, "failedrun@example.com")
    with session_factory()() as db:
        failed = DiscoveryRun(user_id=uid, trigger="scheduled", status="failed", summary="Discovery could not run.",
                              error_details=[{"type": "INTERRUPTED", "message": "The server restarted before this run finished."}])
        interrupted = DiscoveryRun(user_id=uid, trigger="manual", status="failed",
                                   error_details=[{"type": "INTERRUPTED", "message": "The server restarted before this run finished."}])
        db.add_all([failed, interrupted,
                    DiscoveryRun(user_id=uid, trigger="scheduled", status="completed"),
                    DiscoveryRun(user_id=uid, trigger="scheduled", status="running"),
                    DiscoveryRun(user_id=uid, trigger="scheduled", status="failed", started_at=_now() - timedelta(days=10))])
        db.commit()

    assert _sweep()["discovery_failed"] == 2
    notes = _notes(uid, "discovery_failed")
    titles = sorted(n.title for n in notes)
    assert titles == ["A job search couldn't run", "Your scheduled job search couldn't run"]
    assert all(n.link == "/searches?tab=sources" for n in notes)
    assert any("The server restarted" in n.body for n in notes)
    assert _sweep()["discovery_failed"] == 0


def test_preferences_and_inactive_users_are_respected(client):
    from backend.db import session_factory
    from backend.models import NotificationPref, User

    off = _user(client, "prefs-off@example.com")
    gone = _user(client, "inactive@example.com")
    with session_factory()() as db:
        db.add(NotificationPref(user_id=off, kinds={"follow_up_due": {"in_app": False}}, email_digest="off"))
        _app(db, off, _job(db), follow_up_at=_now() - timedelta(hours=1))
        _user_job(db, off, _job(db, closed_at=_now()), is_saved=True)
        _app(db, gone, _job(db), follow_up_at=_now() - timedelta(hours=1))
        db.get(User, gone).is_active = False
        db.commit()
    _sweep()
    assert _notes(off, "follow_up_due") == [] and len(_notes(off, "listing_closed")) == 1
    assert _notes(gone) == []


def test_sweep_runs_as_a_named_job_and_shows_in_the_bell(client):
    from backend.db import session_factory
    from backend.models import User

    h = auth(register(client, "sweep-job@example.com"))
    a = auth(register(client, "sweep-admin@example.com"))
    with session_factory()() as db:
        uid = db.execute(select(User.id).where(User.email == "sweep-job@example.com")).scalar_one()
        db.execute(update(User).where(User.email == "sweep-admin@example.com").values(role="admin"))
        _app(db, uid, _job(db), follow_up_at=_now() - timedelta(hours=1))
        db.commit()
    assert client.post(f"{API}/admin/jobs/notification_sweep/run", headers=h).status_code == 403
    r1 = client.post(f"{API}/admin/jobs/notification_sweep/run", headers=a).json()
    r2 = client.post(f"{API}/admin/jobs/notification_sweep/run", headers=a).json()
    assert r1["status"] == "ok" and r1["details"]["created"] == 1 and r2["details"]["created"] == 0
    # notification_dispatch shares the dedupe key, so it doesn't repeat the sweep's reminder either.
    assert client.post(f"{API}/admin/jobs/notification_dispatch/run", headers=a).json()["details"]["in_app_created"] == 0
    bell = client.get(f"{API}/notifications", headers=h).json()
    assert bell["unread"] == 1 and bell["items"][0]["kind"] == "follow_up_due"
    jobs = {j["name"]: j for j in client.get(f"{API}/admin/jobs", headers=a).json()}
    assert jobs["notification_sweep"]["last_status"] == "ok" and jobs["notification_sweep"]["schedule"] == "hourly at :15"


def test_runs_with_nothing_configured_are_not_alerted_as_failures(client, resume_bytes):
    """The daily connected-sources run with no alert mailbox and no Adzuna key is a setup gap, not an outage."""
    from api_helpers import onboard
    from backend.db import session_factory
    from backend.models import DiscoveryRun, Notification, utcnow
    from backend.services import discovery_service, notification_sweep, overview_service

    h = onboard(client, "nc@example.com", resume_bytes)
    uid = client.get("/api/v1/auth/me", headers=h).json()["id"]
    db = session_factory()()
    try:
        unconfigured = DiscoveryRun(user_id=uid, trigger="scheduled", sources=["alert_email", "adzuna_api"], started_at=utcnow(),
                                    status="failed", jobs_found=0, jobs_new=0, jobs_matched=0, duplicates=0, platform_stats={},
                                    error_details=[{"type": "EMAIL_NOT_CONFIGURED", "message": "No mailbox"}],
                                    source_results={"alert_email": {"status": "not_configured", "label": "Job-alert emails"},
                                                    "adzuna_api": {"status": "not_configured", "label": "Adzuna"}})
        broken = DiscoveryRun(user_id=uid, trigger="manual", sources=["greenhouse"], started_at=utcnow(), status="failed",
                              jobs_found=0, jobs_new=0, jobs_matched=0, duplicates=0, platform_stats={},
                              error_details=[{"type": "INTERRUPTED", "message": "The server restarted before this run finished."}],
                              source_results={"greenhouse": {"status": "failed", "label": "Greenhouse"}})
        db.add_all([unconfigured, broken]); db.commit()
        assert discovery_service.nothing_configured(unconfigured) and not discovery_service.nothing_configured(broken)
        notification_sweep.run(db)
        keys = {n.dedupe_key for n in db.query(Notification).filter(Notification.user_id == uid, Notification.kind == "discovery_failed")}
        assert keys == {f"discovery_failed:{broken.id}"}
        broken.started_at = unconfigured.started_at  # make the unconfigured run the latest for the dashboard
        db.delete(broken); db.commit()
        from backend.models import User
        assert overview_service.discovery_health(db, db.get(User, uid))["state"] == "not_configured"
    finally:
        db.close()
