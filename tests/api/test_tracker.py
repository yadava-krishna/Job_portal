"""Phase 4: interviews, offers, contacts, Today view, active time, data export and account deletion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api_helpers import PASSWORD, import_job, onboard

API = "/api/v1"


def _submitted_app(client, h, url="https://www.linkedin.com/jobs/view/4000000001/", company="Acme Health") -> int:
    uj = import_job(client, h, url=url, company=company)["user_job_ids"][0]
    app_id = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": uj}).json()["id"]
    assert client.post(f"{API}/applications/{app_id}/confirm", headers=h, json={"submitted": True}).status_code == 200
    return app_id


def test_interviews_offers_contacts_and_calendar(client, resume_bytes):
    h = onboard(client, "t1@example.com", resume_bytes)
    app_id = _submitted_app(client, h)
    when = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0).isoformat()
    r = client.post(f"{API}/applications/{app_id}/interviews", headers=h,
                    json={"round_name": "HR round", "scheduled_at": when, "duration_minutes": 45, "mode": "video", "location": "https://meet.example/abc"})
    assert r.status_code == 201, r.text
    iv = r.json()
    assert iv["company"] == "Acme Health"
    assert client.get(f"{API}/applications/{app_id}", headers=h).json()["stage"] == "interview"  # moved along automatically
    assert [i["id"] for i in client.get(f"{API}/interviews", headers=h, params={"upcoming": True}).json()] == [iv["id"]]
    ics = client.get(f"{API}/interviews/calendar.ics", headers=h)
    assert ics.status_code == 200 and "BEGIN:VEVENT" in ics.text and "HR round: Accounts Receivable Analyst at Acme Health" in ics.text
    assert client.put(f"{API}/interviews/{iv['id']}", headers=h, json={**iv, "outcome": "passed"}).json()["outcome"] == "passed"
    o = client.put(f"{API}/applications/{app_id}/offer", headers=h, json={"base_salary": 900000, "decision_deadline": "2026-12-01"}).json()
    assert o["status"] == "received" and client.get(f"{API}/applications/{app_id}", headers=h).json()["stage"] == "offer"
    o2 = client.put(f"{API}/applications/{app_id}/offer", headers=h, json={"base_salary": 950000, "status": "negotiating"}).json()
    assert o2["id"] == o["id"] and len(client.get(f"{API}/offers", headers=h).json()) == 1  # one offer per application
    c = client.post(f"{API}/applications/{app_id}/contacts", headers=h, json={"name": "Priya (recruiter)", "email": "recruiter@example.com"})
    assert c.status_code == 201 and len(client.get(f"{API}/applications/{app_id}/contacts", headers=h).json()) == 1
    events = [e["event_type"] for e in client.get(f"{API}/applications/{app_id}", headers=h).json()["events"]]
    assert "INTERVIEW_ADDED" in events and "OFFER_RECORDED" in events


def test_tracker_is_private_to_each_user(client, resume_bytes):
    ha = onboard(client, "ta@example.com", resume_bytes)
    hb = onboard(client, "tb@example.com", resume_bytes)
    app_id = _submitted_app(client, ha)
    iv = client.post(f"{API}/applications/{app_id}/interviews", headers=ha, json={"round_name": "R1"}).json()
    c = client.post(f"{API}/applications/{app_id}/contacts", headers=ha, json={"name": "X"}).json()
    assert client.post(f"{API}/applications/{app_id}/interviews", headers=hb, json={"round_name": "R1"}).status_code == 404
    assert client.put(f"{API}/applications/{app_id}/offer", headers=hb, json={}).status_code == 404
    assert client.get(f"{API}/applications/{app_id}/contacts", headers=hb).status_code == 404
    assert client.put(f"{API}/interviews/{iv['id']}", headers=hb, json={"round_name": "hijack"}).status_code == 404
    assert client.delete(f"{API}/interviews/{iv['id']}", headers=hb).status_code == 404
    assert client.delete(f"{API}/contacts/{c['id']}", headers=hb).status_code == 404
    assert client.get(f"{API}/interviews", headers=hb).json() == [] and client.get(f"{API}/offers", headers=hb).json() == []
    assert "BEGIN:VEVENT" not in client.get(f"{API}/interviews/calendar.ics", headers=hb).text


def test_interviews_and_offers_need_a_submitted_application(client, resume_bytes):
    h = onboard(client, "t2@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    app_id = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": uj}).json()["id"]
    assert client.post(f"{API}/applications/{app_id}/interviews", headers=h, json={}).status_code == 409
    assert client.put(f"{API}/applications/{app_id}/offer", headers=h, json={}).status_code == 409


def test_today_view_buckets(client, resume_bytes, monkeypatch):
    from backend.db import session_factory
    from backend.models import Application, ApplicationEvent

    h = onboard(client, "td@example.com", resume_bytes)
    quiet = _submitted_app(client, h, "https://www.linkedin.com/jobs/view/4000000002/", company="Acme Health")
    follow = _submitted_app(client, h, "https://www.linkedin.com/jobs/view/4000000003/", company="Beta Corp")
    soon = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    client.post(f"{API}/applications/{follow}/interviews", headers=h, json={"round_name": "Panel", "scheduled_at": soon})
    client.put(f"{API}/applications/{follow}/tracking", headers=h, json={"follow_up_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()})
    old = datetime.now(timezone.utc) - timedelta(days=20)
    with session_factory()() as db:  # nothing heard for 20 days on the first application
        db.query(ApplicationEvent).filter(ApplicationEvent.application_id == quiet).update({"created_at": old})
        db.query(Application).filter(Application.id == quiet).update({"submitted_at": old, "updated_at": old})
        db.commit()
    t = client.get(f"{API}/dashboard/today", headers=h).json()
    assert [i["application_id"] for i in t["waiting_on_them"]] == [quiet]
    assert any(i["kind"] == "interview" and i["application_id"] == follow for i in t["coming_up"])
    assert any(i["kind"] == "follow_up" and i["application_id"] == follow for i in t["your_move"])
    # Marking it ghosted takes it out of "waiting on them".
    assert client.post(f"{API}/applications/{quiet}/stage", headers=h, json={"stage": "ghosted"}).json()["stage"] == "ghosted"
    assert client.get(f"{API}/dashboard/today", headers=h).json()["waiting_on_them"] == []


def test_active_time_counts_only_visible_active_heartbeats(client, resume_bytes, monkeypatch):
    from backend.services import tracker_service

    h = onboard(client, "act@example.com", resume_bytes)
    base = datetime.now(timezone.utc)
    clock = {"t": base}
    monkeypatch.setattr(tracker_service, "utcnow", lambda: clock["t"])
    for i in range(5):  # 2.5 minutes of activity in one session
        clock["t"] = base + timedelta(seconds=30 * i)
        assert client.post(f"{API}/activity/heartbeat", headers=h, json={"visible": True, "active": True}).status_code == 204
    client.post(f"{API}/activity/heartbeat", headers=h, json={"visible": False, "active": True})  # hidden tab: ignored
    clock["t"] = base + timedelta(minutes=20)  # long gap: a new session
    client.post(f"{API}/activity/heartbeat", headers=h, json={"visible": True, "active": True})
    m = client.get(f"{API}/dashboard/activity-metrics", headers=h).json()
    assert m["sessions"] == 2 and m["active_minutes"] == 2
    uj = import_job(client, h)["user_job_ids"][0]
    client.get(f"{API}/jobs/{uj}", headers=h)
    client.get(f"{API}/jobs/{uj}", headers=h)
    assert client.get(f"{API}/dashboard/activity-metrics", headers=h).json()["jobs_viewed"] == 1


def test_export_contains_your_data_and_no_secrets(client, resume_bytes):
    h = onboard(client, "ex@example.com", resume_bytes)
    _submitted_app(client, h)
    r = client.get(f"{API}/account/export", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["account"]["email"] == "ex@example.com" and len(data["applications"]) == 1 and data["resumes"]
    text = r.text
    for secret in ("password_hash", "token_hash", "stored_path", "$argon2"):
        assert secret not in text


def test_account_deletion_requires_password_and_removes_everything(client, app_env, resume_bytes):
    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import Application, Resume, User

    h = onboard(client, "del@example.com", resume_bytes)
    _submitted_app(client, h)
    other = onboard(client, "keep@example.com", resume_bytes)
    with session_factory()() as db:
        uid = db.query(User).filter(User.email == "del@example.com").one().id
    folder = get_settings().user_dir(uid)
    assert folder.exists()
    assert client.post(f"{API}/account/delete", headers=h, json={"password": "wrong", "confirm": "DELETE"}).status_code == 403
    assert client.post(f"{API}/account/delete", headers=h, json={"password": PASSWORD, "confirm": "nope"}).status_code == 422
    assert client.post(f"{API}/account/delete", headers=h, json={"password": PASSWORD, "confirm": "DELETE"}).status_code == 204
    assert not folder.exists()
    with session_factory()() as db:
        assert db.query(User).filter(User.email == "del@example.com").count() == 0
        assert db.query(Application).filter(Application.user_id == uid).count() == 0
        assert db.query(Resume).filter(Resume.user_id == uid).count() == 0
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401
    assert client.get(f"{API}/auth/me", headers=other).status_code == 200  # nobody else affected
