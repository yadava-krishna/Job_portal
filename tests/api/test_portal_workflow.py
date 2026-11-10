import io
from datetime import timedelta

import httpx
import openpyxl

from api_helpers import AR_JD, auth, import_job, onboard, register


# ---- resume upload & profile -------------------------------------------------------

def test_resume_upload_validation(client, resume_bytes):
    h = auth(register(client, "u@example.com"))
    up = lambda name, data, ctype="application/pdf": client.post("/api/v1/profile/resume", headers=h, files={"file": (name, data, ctype)})
    assert up("cv.txt", b"hello world " * 50, "text/plain").status_code == 415
    assert up("fake.pdf", b"not really a pdf" * 50).status_code == 415
    assert up("broken.pdf", b"%PDF-1.7\n" + b"garbage" * 100).status_code == 422
    assert up("big.pdf", b"%PDF-" + b"0" * (6 * 1024 * 1024)).status_code == 413
    r = up("../../etc/passwd.pdf", resume_bytes)
    assert r.status_code == 201
    body = r.json()
    assert body["resume"]["original_filename"] == "passwd.pdf"
    assert body["parsed"]["experience"][0]["company"] == "Alpha Finance Ltd"
    assert "resume" in body and "storage" not in str(body)  # no server paths leak


def test_resume_stored_per_user_and_downloadable(client, resume_bytes, app_env):
    h = auth(register(client, "s@example.com"))
    client.post("/api/v1/profile/resume", headers=h, files={"file": ("cv.pdf", resume_bytes, "application/pdf")})
    me = client.get("/api/v1/auth/me", headers=h).json()
    files = list((app_env / "storage" / "users" / str(me["id"]) / "resumes").glob("*.pdf"))
    assert len(files) == 1 and files[0].read_bytes() == resume_bytes
    r = client.get("/api/v1/profile/resume", headers=h)
    assert r.status_code == 200 and r.content == resume_bytes


def test_profile_edit_and_experience(client, resume_bytes):
    h = onboard(client, "p@example.com", resume_bytes)
    prof = client.get("/api/v1/profile", headers=h).json()
    edited = prof["confirmed"]
    edited["skills"].append("Power BI")
    edited["experience"] = [{"title": "Analyst", "company": "X", "start": "2020-01", "end": "2020-12", "is_current": False, "bullets": []},
                            {"title": "Analyst", "company": "Y", "start": "2020-07", "end": "2021-06", "is_current": False, "bullets": []}]
    out = client.put("/api/v1/profile", headers=h, json=edited).json()
    assert "Power BI" in out["confirmed"]["skills"]
    assert out["experience"]["months"] == 18  # overlap counted once
    bad = dict(edited, experience=[{"title": "x", "company": "y", "start": "2020/01"}])
    assert client.put("/api/v1/profile", headers=h, json=bad).status_code == 422


def test_onboarding_status(client, resume_bytes):
    h = auth(register(client, "o@example.com"))
    assert client.get("/api/v1/onboarding", headers=h).json()["completed"] is False
    h2 = onboard(client, "o2@example.com", resume_bytes)
    s = client.get("/api/v1/onboarding", headers=h2).json()
    assert s == {"resume_uploaded": True, "profile_confirmed": True, "preferences_saved": True, "platforms_selected": True, "completed": True}


def test_preferences_validation(client):
    h = auth(register(client, "pv@example.com"))
    assert client.put("/api/v1/preferences", headers=h, json={"salary_min": 10, "salary_max": 5}).status_code == 422
    assert client.put("/api/v1/preferences", headers=h, json={"work_modes": ["Moon"]}).status_code == 422
    ok = client.put("/api/v1/preferences", headers=h, json={"domains": ["Finance", "finance", "Healthcare"], "min_match_score": 75})
    assert ok.status_code == 200 and ok.json()["domains"] == ["Finance", "Healthcare"]


def test_platforms_listing_and_sources(client):
    h = auth(register(client, "pl@example.com"))
    plats = {p["platform"]: p for p in client.get("/api/v1/platforms", headers=h).json()}
    assert set(plats) == {"LinkedIn", "Indeed", "Naukri", "Adzuna"}
    assert all(not plats[p]["automated_apply"] for p in plats)
    r = client.put("/api/v1/platforms/preferences", headers=h, json={"platforms": [{"platform": "Naukri", "enabled": True, "discovery_sources": ["adzuna_api"]}]})
    assert r.status_code == 422
    r = client.put("/api/v1/platforms/preferences", headers=h, json={"platforms": [{"platform": "Adzuna", "enabled": True, "discovery_sources": ["adzuna_api"]}]})
    assert r.status_code == 422  # not configured on this server


# ---- discovery, matching, dedup ----------------------------------------------------------

def test_import_scores_and_dedups(client, resume_bytes):
    h = onboard(client, "d@example.com", resume_bytes)
    first = import_job(client, h)
    uj = first["user_job_ids"][0]
    again = import_job(client, h, url="https://www.linkedin.com/jobs/view/4000000001/?trackingId=xyz")
    assert again["user_job_ids"] == [uj] and again["run"]["duplicates"] == 1
    feed = client.get("/api/v1/jobs", headers=h).json()
    assert feed["total"] == 1
    item = feed["items"][0]
    assert item["match_score"] is not None and item["job"]["posted_label"].startswith("Today")
    assert "Accounts Receivable" in item["matching_skills"]
    analysis = client.get(f"/api/v1/jobs/{uj}/analysis", headers=h).json()
    assert [c["name"] for c in analysis["components"]] == ["core_skills", "experience", "responsibilities", "education", "location"]
    assert abs(sum(c["weighted"] for c in analysis["dimensions"]) - analysis["overall_score"]) < 0.2
    assert analysis["score_version"].startswith("v2") and len(analysis["dimensions"]) == 8
    assert sum(d["base_weight"] for d in analysis["dimensions"]) == 100
    assert analysis["eligibility"] in ("pass", "fail", "unknown")
    detail = client.get(f"/api/v1/jobs/{uj}", headers=h).json()
    assert detail["description"].startswith("About the role") and detail["responsibilities"]


def test_posted_today_requires_verified_date(client, resume_bytes):
    h = onboard(client, "t@example.com", resume_bytes)
    import_job(client, h)  # posted today (user-provided)
    import_job(client, h, url="https://in.indeed.com/viewjob?jk=0123456789abcdef", posted_date=None, company="NoDate Co")
    today = client.get("/api/v1/jobs?posted=today", headers=h).json()
    assert today["total"] == 1 and today["items"][0]["job"]["company"] == "Acme Health"
    all_jobs = {i["job"]["company"]: i["job"]["posted_label"] for i in client.get("/api/v1/jobs", headers=h).json()["items"]}
    assert all_jobs["NoDate Co"] == "Unknown"


def test_job_filters(client, resume_bytes):
    h = onboard(client, "f@example.com", resume_bytes)
    import_job(client, h)
    import_job(client, h, url="https://www.naukri.com/job-listings-x-031125011111", company="Other Co", location="Pune",
               title="MIS Analyst", work_mode="On-site")
    assert client.get("/api/v1/jobs?platform=Naukri", headers=h).json()["total"] == 1
    assert client.get("/api/v1/jobs?location=pune", headers=h).json()["total"] == 1
    assert client.get("/api/v1/jobs?q=acme", headers=h).json()["total"] == 1
    assert client.get("/api/v1/jobs?min_score=99.9", headers=h).json()["total"] == 0
    assert client.get("/api/v1/jobs?experience=4", headers=h).json()["total"] >= 1


def test_save_dismiss_restore(client, resume_bytes):
    h = onboard(client, "sv@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    client.post(f"/api/v1/jobs/{uj}/save", headers=h)
    assert client.get("/api/v1/jobs?view=saved", headers=h).json()["total"] == 1
    client.delete(f"/api/v1/jobs/{uj}/save", headers=h)
    assert client.get("/api/v1/jobs?view=saved", headers=h).json()["total"] == 0
    client.post(f"/api/v1/jobs/{uj}/dismiss", headers=h)
    assert client.get("/api/v1/jobs", headers=h).json()["total"] == 0
    assert client.get("/api/v1/jobs?view=dismissed", headers=h).json()["total"] == 1
    client.post(f"/api/v1/jobs/{uj}/restore", headers=h)
    assert client.get("/api/v1/jobs", headers=h).json()["total"] == 1


def test_add_description_upgrades_job(client, resume_bytes):
    h = onboard(client, "jd@example.com", resume_bytes)
    uj = import_job(client, h, description=None)["user_job_ids"][0]
    before = client.get(f"/api/v1/jobs/{uj}", headers=h).json()
    assert before["job"]["has_full_description"] is False
    r = client.put(f"/api/v1/jobs/{uj}/description", headers=h, json={"description": AR_JD})
    assert r.status_code == 200 and r.json()["job"]["has_full_description"] is True
    assert client.put(f"/api/v1/jobs/{uj}/description", headers=h, json={"description": AR_JD}).status_code == 409


# ---- apply workflow -----------------------------------------------------------------------

def test_apply_flow_open_is_not_applied(client, resume_bytes):
    h = onboard(client, "ap@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    app = client.post("/api/v1/applications/prepare", headers=h, json={"user_job_id": uj}).json()
    assert app["status"] == "PREPARED"
    answers = {a["question"]: a["answer"] for a in app["screening_answers"]}
    assert answers["What is your current CTC?"] == "NEEDS_CANDIDATE_INPUT"
    assert "years" in answers["Total years of experience?"]
    assert app["cover_letter"] and "Acme Health" in app["cover_letter"]  # JD asks for one
    assert any(c["check"].startswith("Posting is still open") for c in app["checklist"])
    assert client.post("/api/v1/applications/prepare", headers=h, json={"user_job_id": uj}).json()["id"] == app["id"]

    opened = client.post(f"/api/v1/applications/{app['id']}/open", headers=h).json()
    assert opened["url"] == "https://www.linkedin.com/jobs/view/4000000001/"
    assert opened["application"]["status"] == "OPENED"
    assert client.get("/api/v1/dashboard/summary", headers=h).json()["total_applied"] == 0
    assert client.get("/api/v1/jobs", headers=h).json()["total"] == 1  # still in the feed

    # Closed the tab without applying: back to prepared, still pending.
    r = client.post(f"/api/v1/applications/{app['id']}/confirm", headers=h, json={"submitted": False}).json()
    assert r["status"] == "PREPARED"
    client.post(f"/api/v1/applications/{app['id']}/open", headers=h)
    assert client.post(f"/api/v1/applications/{app['id']}/pending", headers=h).json()["status"] == "CONFIRMATION_PENDING"

    done = client.post(f"/api/v1/applications/{app['id']}/confirm", headers=h,
                       json={"submitted": True, "reference_id": "LI-123", "confirmation_text": "Your application was sent to Acme"}).json()
    assert done["status"] == "SUBMITTED" and done["reference_id"] == "LI-123" and done["stage"] == "applied"
    assert client.get("/api/v1/jobs", headers=h).json()["total"] == 0          # left the discovery feed
    assert client.get("/api/v1/jobs?view=applied", headers=h).json()["total"] == 1
    s = client.get("/api/v1/dashboard/summary", headers=h).json()
    assert s["total_applied"] == 1 and s["pending_applications"] == 0
    events = [e["event_type"] for e in client.get(f"/api/v1/applications/{app['id']}", headers=h).json()["events"]]
    assert events[0] == "PREPARED" and "OPENED_EXTERNAL" in events and events[-1] == "SUBMISSION_CONFIRMED"

    assert client.post(f"/api/v1/applications/{app['id']}/stage", headers=h, json={"stage": "interview"}).json()["stage"] == "interview"
    assert client.post(f"/api/v1/applications/{app['id']}/fail", headers=h, json={}).status_code == 409


def test_cross_platform_duplicate_application_blocked(client, resume_bytes):
    h = onboard(client, "cp@example.com", resume_bytes)
    a = import_job(client, h)["user_job_ids"][0]
    b = import_job(client, h, url="https://www.naukri.com/job-listings-ar-acme-031125099999", company="Acme Health Pvt Ltd")["user_job_ids"][0]
    assert client.post("/api/v1/applications/prepare", headers=h, json={"user_job_id": a}).status_code == 201
    r = client.post("/api/v1/applications/prepare", headers=h, json={"user_job_id": b})
    assert r.status_code == 409 and "already have an application" in r.json()["detail"]


def test_stage_requires_submission(client, resume_bytes):
    h = onboard(client, "st@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    app = client.post("/api/v1/applications/prepare", headers=h, json={"user_job_id": uj}).json()
    assert client.post(f"/api/v1/applications/{app['id']}/stage", headers=h, json={"stage": "offer"}).status_code == 409


# ---- reports --------------------------------------------------------------------------------

def test_reports_are_per_user(client, resume_bytes):
    ha = onboard(client, "ra@example.com", resume_bytes)
    hb = onboard(client, "rb@example.com", resume_bytes)
    import_job(client, ha)
    import_job(client, hb, url="https://in.indeed.com/viewjob?jk=00000000000000bb", company="Bob Only Corp")
    daily = client.get("/api/v1/reports/daily", headers=ha).json()
    assert client.get("/api/v1/reports/daily", headers=ha).json()["id"] == daily["id"]  # reused, not regenerated
    regen = client.post("/api/v1/reports/daily", headers=ha).json()
    assert regen["id"] != daily["id"] and regen["file_name"] != daily["file_name"]  # never overwritten
    xlsx = client.get(f"/api/v1/reports/{daily['id']}/download", headers=ha)
    assert xlsx.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(xlsx.content))
    assert wb.sheetnames[:4] == ["Application Details", "Daily Summary", "Job Analysis", "Errors and Logs"]
    companies = [r[5] for r in wb["Application Details"].iter_rows(min_row=2, values_only=True)]
    assert companies == ["Acme Health"]
    hist = client.post("/api/v1/reports/history", headers=hb).json()
    wb = openpyxl.load_workbook(io.BytesIO(client.get(f"/api/v1/reports/{hist['id']}/download", headers=hb).content))
    assert [r[5] for r in wb["Application Details"].iter_rows(min_row=2, values_only=True)] == ["Bob Only Corp"]


# ---- automated sources ------------------------------------------------------------------------

def test_adzuna_discovery_with_verified_dates(client, resume_bytes):
    from backend.db import session_factory
    from backend.models import PlatformPreference, User
    from backend.services import discovery_service
    from backend.services.adzuna import AdzunaClient
    from backend.config import get_settings
    from core import timeutil

    h = onboard(client, "az@example.com", resume_bytes)
    today = timeutil.today()
    payload = {"results": [
        {"id": 111, "title": "Accounts Receivable Analyst", "company": {"display_name": "Zeta Health"},
         "location": {"display_name": "Bengaluru, Karnataka"}, "description": AR_JD[:300], "redirect_url": "https://www.adzuna.in/land/ad/111",
         "created": f"{today.isoformat()}T05:00:00Z", "salary_min": 600000, "salary_max": 900000, "contract_time": "full_time"},
        {"id": 222, "title": "Financial Analyst", "company": {"display_name": "Old Co"}, "location": {"display_name": "Bengaluru"},
         "description": "Financial analysis and FP&A reporting.", "redirect_url": "https://www.adzuna.in/land/ad/222",
         "created": f"{(today - timedelta(days=3)).isoformat()}T05:00:00Z"},
    ]}
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, json=payload)

    db = session_factory()()
    user = db.query(User).filter_by(email="az@example.com").one()
    db.add(PlatformPreference(user_id=user.id, platform="Adzuna", enabled=True, discovery_sources=["adzuna_api"]))
    db.commit()
    client_ = AdzunaClient("id", "key", transport=httpx.MockTransport(handler))
    run = discovery_service.run_discovery(db, get_settings(), user, ["adzuna_api"], adzuna_client=client_)
    db.close()
    assert run.status == "completed" and run.jobs_new == 2 and "app_key" in str(calls[0])
    items = {i["job"]["company"]: i for i in client.get("/api/v1/jobs", headers=h).json()["items"]}
    assert items["Zeta Health"]["job"]["posted_label"] == "Today" and items["Zeta Health"]["job"]["platform"] == "Adzuna"
    assert items["Zeta Health"]["job"]["has_full_description"] is False  # snippet only
    assert client.get("/api/v1/jobs?posted=today", headers=h).json()["total"] == 1


def test_email_alert_discovery_and_confirmation(client, resume_bytes):
    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import User
    from backend.services import discovery_service
    from core.settings import EmailAlertsConfig
    from discovery.sources import EmailAlertSource
    from test_platforms_and_sources import LINKEDIN_ALERT, FakeIMAP

    h = onboard(client, "em@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    app = client.post("/api/v1/applications/prepare", headers=h, json={"user_job_id": uj}).json()
    client.post(f"/api/v1/applications/{app['id']}/open", headers=h)
    imap = FakeIMAP([("LinkedIn <jobalerts-noreply@linkedin.com>", "New jobs", LINKEDIN_ALERT),
                     ("LinkedIn <jobs-noreply@linkedin.com>", "Your application was sent to Acme Health", "<p>Accounts Receivable Analyst</p>")])
    src = EmailAlertSource(EmailAlertsConfig(enabled=True), imap_factory=lambda: imap, username="u", password="p")
    db = session_factory()()
    user = db.query(User).filter_by(email="em@example.com").one()
    run = discovery_service.run_discovery(db, get_settings(), user, ["alert_email"], email_factory=lambda d, u: (None, src))
    db.close()
    assert run.jobs_new == 2
    labels = [i["job"]["posted_label"] for i in client.get("/api/v1/jobs", headers=h).json()["items"]]
    assert all(l == "Unknown" or "alert" in l or "Today" in l for l in labels)
    detail = client.get(f"/api/v1/applications/{app['id']}", headers=h).json()
    assert detail["status"] == "SUBMITTED" and detail["confirmation_source"].startswith("email:")


def test_email_integration_password_encrypted(client, app_env):
    h = auth(register(client, "enc@example.com"))
    r = client.put("/api/v1/integrations/email", headers=h, json={"enabled": True, "username": "me@gmail.com", "password": "abcd efgh ijkl mnop"})
    assert r.status_code == 200 and r.json()["has_password"] and "password" not in r.json()
    from sqlalchemy import text

    from backend.db import get_engine

    with get_engine().connect() as conn:
        stored = conn.execute(text("select password_encrypted from email_integrations")).scalar_one()
    assert "abcd" not in stored


# ---- health ----------------------------------------------------------------------------------

def test_health_and_ready(client):
    h = client.get("/api/v1/health").json()
    assert h["status"] == "ok" and h["service"] == "jobpilot-backend" and h["database"]["connected"] is True
    assert {"enabled", "running", "next_run"} <= set(h["scheduler"])
    assert client.get("/api/v1/health/ready").status_code == 200


def test_health_reports_database_down(client, monkeypatch):
    import backend.api.routes.health as health

    monkeypatch.setattr(health, "check_database", lambda: (False, "OperationalError"))
    assert client.get("/api/v1/health").json()["status"] == "degraded"
    assert client.get("/api/v1/health/ready").status_code == 503


def test_cors_allows_configured_origin_only(client):
    ok = client.options("/api/v1/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
                                                    "Access-Control-Request-Headers": "authorization,ngrok-skip-browser-warning"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


# ---- SQLite (CLI) → portal import ---------------------------------------------------------------

def test_import_cli_sqlite_history(client, tmp_path, settings_factory):  # noqa: D103
    """Runs the real CLI pipeline into SQLite, then imports it into a portal user (idempotently)."""
    import json as _json

    from backend.scripts import import_sqlite
    from runner import DailyRunner

    s = settings_factory()
    (s.inbox_dir / "j.json").write_text(_json.dumps([{"url": "https://www.linkedin.com/jobs/view/4000000077/", "title": "Accounts Receivable Analyst",
                                                      "company": "Cli Corp", "location": "Bengaluru", "description": AR_JD}]))
    DailyRunner(s, llm=None, retry_base_delay=0).run()
    h = auth(register(client, "cli@example.com"))
    first = import_sqlite.run(s.db_path, "cli@example.com", dry_run=False)
    assert first["jobs"] == 1 and first["applications"] == 1 and first["profile"] == 1
    again = import_sqlite.run(s.db_path, "cli@example.com", dry_run=False)
    assert again["jobs"] == 0 and again["applications"] == 0
    apps = client.get("/api/v1/applications", headers=h).json()
    assert len(apps) == 1 and apps[0]["job"]["company"] == "Cli Corp" and apps[0]["status"] == "PREPARED"


def test_clipper_import_marks_page_date_verified(client, resume_bytes):
    h = onboard(client, "clip@example.com", resume_bytes)
    r = import_job(client, h, url="https://www.naukri.com/job-listings-fa-x-031125055555", company="Clip Co",
                   posted_date="today", posted_date_source="page", captured_via="clipper")
    assert r["run"]["sources"] == ["browser_clipper"]
    item = client.get("/api/v1/jobs?posted=today", headers=h).json()["items"][0]
    assert item["job"]["posted_label"] == "Today (per listing)" and item["job"]["posted_at_source"] == "platform_page"
