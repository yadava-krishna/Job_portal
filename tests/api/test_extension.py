"""Phase 3: browser-extension pairing, device credentials, scoped data access, isolation and application tracking."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from api_helpers import auth, import_job, onboard, register
from ats_fixtures import Boards

API = "/api/v1"
GH_JOB = "https://job-boards.greenhouse.io/acmefintech/jobs/101"
SEARCH = {"name": "AR roles", "schedule": "daily", "min_match_score": 0,
          "criteria": {"keywords": ["Accounts Receivable"], "locations": ["Bengaluru", "Hyderabad"], "remote_ok": True}}


@pytest.fixture
def boards(app_env, monkeypatch):
    from backend.services.ats import base

    b = Boards()
    monkeypatch.setattr(base, "transport_override", b.transport())
    return b


def code_for(client, h) -> str:
    r = client.post(f"{API}/extension/pairing-codes", headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["code"]) == 9 and body["code"][4] == "-" and body["expires_in_seconds"] == 300
    return body["code"]


def pair(client, h, name="Chrome on laptop") -> dict:
    r = client.post(f"{API}/extension/pair", json={"code": code_for(client, h), "device_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def xh(tok: dict | str) -> dict:
    return {"Authorization": f"Bearer {tok['token'] if isinstance(tok, dict) else tok}"}


def with_board_job(client, h) -> dict:
    """Put the Greenhouse fixture job 101 into this user's feed through the normal discovery path."""
    assert client.post(f"{API}/companies/watchlist", headers=h, json={"url": "https://job-boards.greenhouse.io/acmefintech",
                                                                       "name": "Acme Fintech"}).status_code == 201
    sid = client.post(f"{API}/saved-searches", headers=h, json=SEARCH).json()["id"]
    assert client.post(f"{API}/saved-searches/{sid}/run", headers=h).status_code == 202
    items = client.get(f"{API}/jobs", headers=h, params={"page_size": 100}).json()["items"]
    return next(i for i in items if i["job"]["job_url"] == GH_JOB)


# ---- pairing ----------------------------------------------------------------------------------

def test_pairing_issues_a_scoped_device_credential_once(client, resume_bytes):
    h = onboard(client, "p@example.com", resume_bytes)
    code = code_for(client, h)
    r = client.post(f"{API}/extension/pair", json={"code": code.lower().replace("-", " "), "device_name": "Chrome"})
    assert r.status_code == 201, r.text
    tok = r.json()
    assert tok["token"].startswith("jpx_") and len(tok["token"]) > 40
    assert sorted(tok["scopes"]) == ["applications:track", "autofill:read"]
    # The code is single use.
    assert client.post(f"{API}/extension/pair", json={"code": code}).status_code == 400
    # The credential is stored hashed: nothing in the DB equals it.
    from backend.db import session_factory
    from backend.models import ExtensionToken

    with session_factory()() as db:
        hashes = [t.token_hash for t in db.query(ExtensionToken).all()]
    assert tok["token"] not in hashes and code.replace("-", "") not in hashes
    st = client.get(f"{API}/extension/status", headers=xh(tok)).json()
    assert st["connected"] and st["profile_ready"] and not st["rotate_recommended"]
    devices = client.get(f"{API}/extension/devices", headers=h).json()
    assert [d["name"] for d in devices] == ["Chrome"]


def test_pairing_code_expires_after_five_minutes(client, resume_bytes, monkeypatch):
    h = onboard(client, "e@example.com", resume_bytes)
    code = code_for(client, h)
    from backend.services import extension_service

    real = extension_service.utcnow
    monkeypatch.setattr(extension_service, "utcnow", lambda: real() + timedelta(minutes=5, seconds=1))
    assert client.post(f"{API}/extension/pair", json={"code": code}).status_code == 400


def test_wrong_codes_are_rejected_and_rate_limited(client, app_env, monkeypatch):
    from backend.config import get_settings

    h = auth(register(client, "b@example.com"))
    code_for(client, h)
    for _ in range(10):
        assert client.post(f"{API}/extension/pair", json={"code": "ZZZZ-ZZZZ"}).status_code == 400
    assert client.post(f"{API}/extension/pair", json={"code": "ZZZZ-ZZZZ"}).status_code == 429
    assert get_settings() is not None


def test_only_three_codes_are_live_at_once(client):
    h = auth(register(client, "c@example.com"))
    codes = [code_for(client, h) for _ in range(4)]
    assert client.post(f"{API}/extension/pair", json={"code": codes[0]}).status_code == 400  # oldest was retired
    assert client.post(f"{API}/extension/pair", json={"code": codes[3]}).status_code == 201


def test_pairing_requires_a_logged_in_user_and_codes_cannot_authenticate(client):
    assert client.post(f"{API}/extension/pairing-codes").status_code == 401
    h = auth(register(client, "k@example.com"))
    code = code_for(client, h)
    assert client.get(f"{API}/extension/status", headers=xh(code)).status_code == 401
    assert client.get(f"{API}/extension/status", headers=xh("jpx_" + code)).status_code == 401


# ---- credential boundaries --------------------------------------------------------------------

def test_device_credentials_work_only_on_extension_routes_and_jwts_not_on_them(client, resume_bytes):
    h = onboard(client, "s@example.com", resume_bytes)
    tok = pair(client, h)
    for path in ("/auth/me", "/profile", "/jobs", "/applications", "/profile/resume"):
        assert client.get(f"{API}{path}", headers=xh(tok)).status_code == 401, path
    for path in ("/extension/status", "/extension/autofill-profile", "/extension/resume"):
        assert client.get(f"{API}{path}", headers=h).status_code == 401, path
    # Device management needs the user's login, not the device credential.
    assert client.get(f"{API}/extension/devices", headers=xh(tok)).status_code == 401
    assert client.post(f"{API}/extension/pairing-codes", headers=xh(tok)).status_code == 401


def test_revocation_from_settings_and_from_the_extension(client, resume_bytes):
    h = onboard(client, "r@example.com", resume_bytes)
    a, b = pair(client, h, "laptop"), pair(client, h, "desktop")
    assert client.delete(f"{API}/extension/devices/{a['token_id']}", headers=h).status_code == 204
    assert client.get(f"{API}/extension/status", headers=xh(a)).status_code == 401
    assert client.get(f"{API}/extension/status", headers=xh(b)).status_code == 200
    assert client.post(f"{API}/extension/disconnect", headers=xh(b)).status_code == 204
    assert client.get(f"{API}/extension/autofill-profile", headers=xh(b)).status_code == 401
    assert client.get(f"{API}/extension/devices", headers=h).json() == []


def test_expired_credentials_are_rejected(client, resume_bytes, monkeypatch):
    h = onboard(client, "x@example.com", resume_bytes)
    tok = pair(client, h)
    from backend.services import extension_service

    real = extension_service.utcnow
    monkeypatch.setattr(extension_service, "utcnow", lambda: real() + timedelta(days=90, minutes=1))
    assert client.get(f"{API}/extension/status", headers=xh(tok)).status_code == 401


def test_rotation_issues_a_new_credential_and_retires_the_old_one(client, resume_bytes, monkeypatch):
    h = onboard(client, "rot@example.com", resume_bytes)
    old = pair(client, h)
    r = client.post(f"{API}/extension/rotate", headers=xh(old))
    assert r.status_code == 200
    new = r.json()
    assert new["token"] != old["token"]
    assert client.get(f"{API}/extension/status", headers=xh(new)).status_code == 200
    # The old one keeps working only for the short grace period.
    from backend.services import extension_service

    real = extension_service.utcnow
    monkeypatch.setattr(extension_service, "utcnow", lambda: real() + timedelta(minutes=3))
    assert client.get(f"{API}/extension/status", headers=xh(old)).status_code == 401
    assert client.get(f"{API}/extension/status", headers=xh(new)).status_code == 200


def test_users_can_only_see_and_revoke_their_own_devices(client, resume_bytes):
    ha = onboard(client, "a1@example.com", resume_bytes)
    hb = onboard(client, "b1@example.com", resume_bytes)
    ta = pair(client, ha)
    assert client.get(f"{API}/extension/devices", headers=hb).json() == []
    assert client.delete(f"{API}/extension/devices/{ta['token_id']}", headers=hb).status_code == 404
    assert client.get(f"{API}/extension/status", headers=xh(ta)).status_code == 200


# ---- what the extension can read --------------------------------------------------------------

def test_autofill_profile_is_minimal_and_lists_what_is_missing(client, resume_bytes):
    h = onboard(client, "m@example.com", resume_bytes)
    tok = pair(client, h)
    data = client.get(f"{API}/extension/autofill-profile", headers=xh(tok)).json()
    assert data["ready"] and data["has_resume"]
    f = data["fields"]
    assert f["email"] == "test.candidate@example.com" and f["first_name"] and f["full_name"]
    for leaked in ("summary", "skills", "experience", "headline", "achievements", "projects", "match_score"):
        assert leaked not in f
    missing = {m["key"] for m in data["missing"]}
    assert {"linkedin_url", "expected_ctc", "notice_period", "work_authorization"} <= missing
    # Add links and verified answers: they appear, and drop out of "missing".
    prof = client.get(f"{API}/profile", headers=h).json()["confirmed"]
    prof["linkedin_url"] = "linkedin.com/in/test-candidate"
    assert client.put(f"{API}/profile", headers=h, json=prof).status_code == 200
    assert client.put(f"{API}/profile/verified-facts", headers=h, json={"notice_period": "30 days", "requires_sponsorship": False}).status_code == 200
    data = client.get(f"{API}/extension/autofill-profile", headers=xh(tok)).json()
    assert data["fields"]["linkedin_url"] == "https://linkedin.com/in/test-candidate"
    assert data["facts"] == {"notice_period": "30 days", "requires_sponsorship": False}
    assert "notice_period" not in {m["key"] for m in data["missing"]}


def test_profile_links_reject_non_web_addresses(client, resume_bytes):
    h = onboard(client, "l@example.com", resume_bytes)
    prof = client.get(f"{API}/profile", headers=h).json()["confirmed"]
    for bad in ("javascript:alert(1)", "https://user:pw@example.com", "notaurl"):
        prof["portfolio_url"] = bad
        assert client.put(f"{API}/profile", headers=h, json=prof).status_code == 422, bad


def test_answers_are_classified_and_never_invented(client, resume_bytes):
    h = onboard(client, "q@example.com", resume_bytes)
    tok = pair(client, h)
    qs = ["What is your expected CTC?", "Notice period?", "Total years of experience", "Will you require visa sponsorship?",
          "What is your gender?"]
    out = {a["question"]: a for a in client.post(f"{API}/extension/answers", headers=xh(tok), json={"questions": qs}).json()}
    assert out["What is your expected CTC?"]["status"] == "NEEDS_INPUT" and out["What is your expected CTC?"]["answer"] is None
    assert out["Will you require visa sponsorship?"]["status"] == "NEEDS_INPUT"
    assert out["What is your gender?"]["status"] == "NEEDS_INPUT"
    assert out["Total years of experience"]["status"] == "SUGGESTED"
    client.put(f"{API}/profile/verified-facts", headers=h, json={"expected_ctc": "9 LPA", "notice_period": "30 days", "requires_sponsorship": False})
    out = {a["question"]: a for a in client.post(f"{API}/extension/answers", headers=xh(tok), json={"questions": qs}).json()}
    assert out["What is your expected CTC?"] == {**out["What is your expected CTC?"], "status": "VERIFIED", "answer": "9 LPA"}
    assert out["Will you require visa sponsorship?"]["answer"] == "No"


def test_resume_is_available_to_the_owner_only_and_never_cached(client, resume_bytes):
    ha = onboard(client, "ra@example.com", resume_bytes)
    ta = pair(client, ha)
    r = client.get(f"{API}/extension/resume", headers=xh(ta))
    assert r.status_code == 200 and r.content == resume_bytes and "no-store" in r.headers["cache-control"]
    hb = auth(register(client, "rb@example.com"))  # no resume
    tb = pair(client, hb)
    assert client.get(f"{API}/extension/resume", headers=xh(tb)).status_code == 404
    from backend.db import session_factory
    from backend.models import AuditLog

    with session_factory()() as db:
        assert db.query(AuditLog).filter(AuditLog.action == "extension.resume_downloaded").count() == 1


# ---- matching pages and tracking --------------------------------------------------------------

def test_match_recognises_own_jobs_only(client, boards, resume_bytes):
    ha = onboard(client, "ma@example.com", resume_bytes)
    hb = onboard(client, "mb@example.com", resume_bytes)
    item = with_board_job(client, ha)
    ta, tb = pair(client, ha), pair(client, hb)
    for url in (GH_JOB, "https://job-boards.greenhouse.io/embed/job_app?for=acmefintech&token=101",
                "https://boards.greenhouse.io/acmefintech/jobs/101?gh_src=x"):
        m = client.post(f"{API}/extension/match", headers=xh(ta), json={"url": url}).json()
        assert m["in_jobpilot"] and m["user_job_id"] == item["user_job_id"] and m["platform"] == "Greenhouse", url
    # User B has not got this job: B learns nothing about A's feed.
    m = client.post(f"{API}/extension/match", headers=xh(tb), json={"url": GH_JOB}).json()
    assert m == {**m, "supported": True, "in_jobpilot": False, "user_job_id": None, "title": None}
    for url in ("https://example.com/jobs/1", "http://job-boards.greenhouse.io/acmefintech/jobs/101", "javascript:alert(1)"):
        assert client.post(f"{API}/extension/match", headers=xh(ta), json={"url": url}).json()["supported"] is False


def test_extension_tracking_uses_the_existing_workflow_without_duplicates(client, boards, resume_bytes):
    h = onboard(client, "t@example.com", resume_bytes)
    item = with_board_job(client, h)
    tok = pair(client, h)
    s1 = client.post(f"{API}/extension/applications/start", headers=xh(tok), json={"user_job_id": item["user_job_id"]}).json()
    assert s1["status"] == "OPENED" and s1["submitted_at"] is None  # filling is never applying
    s2 = client.post(f"{API}/extension/applications/start", headers=xh(tok), json={"user_job_id": item["user_job_id"]}).json()
    assert s2["application_id"] == s1["application_id"]
    app_id = s1["application_id"]
    c1 = client.post(f"{API}/extension/applications/{app_id}/confirm", headers=xh(tok), json={"submitted": True, "reference_id": "GH-1"}).json()
    assert c1["status"] == "SUBMITTED" and c1["submitted_at"] and not c1["already_submitted"]
    c2 = client.post(f"{API}/extension/applications/{app_id}/confirm", headers=xh(tok), json={"submitted": True}).json()
    assert c2["already_submitted"] and c2["submitted_at"] == c1["submitted_at"]
    # The web app sees the same single application, confirmed once, from the extension.
    apps = client.get(f"{API}/applications", headers=h).json()
    assert len(apps) == 1
    detail = client.get(f"{API}/applications/{app_id}", headers=h).json()
    assert detail["confirmation_source"] == "extension_user_confirmed" and detail["reference_id"] == "GH-1"
    assert [e["event_type"] for e in detail["events"]].count("SUBMISSION_CONFIRMED") == 1
    # Confirming again from the web app does not create anything new either.
    assert client.post(f"{API}/applications/{app_id}/confirm", headers=h, json={"submitted": True}).status_code == 200
    assert len(client.get(f"{API}/applications", headers=h).json()) == 1
    m = client.post(f"{API}/extension/match", headers=xh(tok), json={"url": GH_JOB}).json()
    assert m["application_status"] == "SUBMITTED"


def test_extension_cannot_touch_another_users_jobs_or_applications(client, boards, resume_bytes):
    ha = onboard(client, "ia@example.com", resume_bytes)
    hb = onboard(client, "ib@example.com", resume_bytes)
    item = with_board_job(client, ha)
    app_id = client.post(f"{API}/applications/prepare", headers=ha, json={"user_job_id": item["user_job_id"]}).json()["id"]
    tb = pair(client, hb)
    assert client.post(f"{API}/extension/applications/start", headers=xh(tb), json={"user_job_id": item["user_job_id"]}).status_code == 404
    assert client.post(f"{API}/extension/applications/{app_id}/confirm", headers=xh(tb), json={"submitted": True}).status_code == 404
    assert client.get(f"{API}/applications/{app_id}", headers=ha).json()["status"] == "PREPARED"


def test_not_submitted_returns_the_application_to_prepared(client, boards, resume_bytes):
    h = onboard(client, "n@example.com", resume_bytes)
    item = with_board_job(client, h)
    tok = pair(client, h)
    app_id = client.post(f"{API}/extension/applications/start", headers=xh(tok), json={"user_job_id": item["user_job_id"]}).json()["application_id"]
    r = client.post(f"{API}/extension/applications/{app_id}/confirm", headers=xh(tok), json={"submitted": False}).json()
    assert r["status"] == "PREPARED" and r["submitted_at"] is None


# ---- Greenhouse-hosted application forms ------------------------------------------------------

def _employer_site_job(client, h, boards, *, form_status=200, form_body=None):
    """A Greenhouse job whose listing URL is on the employer's own site (like Stripe or Databricks)."""
    board = boards.payloads[("greenhouse", "acmefintech")]
    board["jobs"][0]["absolute_url"] = "https://careers.acmefintech.example/jobs?gh_jid=101"
    original = boards.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/embed/job_app":
            body = form_body if form_body is not None else '<form><input id="first_name"><input name="job" value="101"></form>'
            return httpx.Response(form_status, text=body, headers={"location": "https://x.example/"} if form_status == 302 else None)
        return original(request)

    from backend.services.ats import base

    base.transport_override = httpx.MockTransport(handler)
    client.post(f"{API}/companies/watchlist", headers=h, json={"url": "https://job-boards.greenhouse.io/acmefintech", "name": "Acme Fintech"})
    sid = client.post(f"{API}/saved-searches", headers=h, json=SEARCH).json()["id"]
    client.post(f"{API}/saved-searches/{sid}/run", headers=h)
    items = client.get(f"{API}/jobs", headers=h, params={"page_size": 100}).json()["items"]
    item = next(i for i in items if "careers.acmefintech.example" in (i["job"]["job_url"] or ""))
    return client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": item["user_job_id"]}).json()["id"]


def test_hosted_form_offered_only_when_greenhouse_serves_it(client, boards, resume_bytes):
    from backend.services import extension_service

    extension_service._hosted_cache.clear()
    h = onboard(client, "g@example.com", resume_bytes)
    app_id = _employer_site_job(client, h, boards)
    o = client.get(f"{API}/applications/{app_id}/apply-options", headers=h).json()
    assert o["hosted_form_url"] == "https://job-boards.greenhouse.io/embed/job_app?for=acmefintech&token=101"
    assert not o["original_supported"] and not o["direct_apply"]


@pytest.mark.parametrize("status_code,body", [(302, ""), (200, "<html>Job not found</html>"), (404, "")])
def test_hosted_form_not_offered_when_unverified(client, boards, resume_bytes, status_code, body):
    from backend.services import extension_service

    extension_service._hosted_cache.clear()
    h = onboard(client, f"g{status_code}{len(body)}@example.com", resume_bytes)
    app_id = _employer_site_job(client, h, boards, form_status=status_code, form_body=body)
    o = client.get(f"{API}/applications/{app_id}/apply-options", headers=h).json()
    assert o["hosted_form_url"] is None and "careers site" in o["message"]


def test_apply_options_for_hosted_and_clipped_jobs(client, boards, resume_bytes):
    h = onboard(client, "o@example.com", resume_bytes)
    item = with_board_job(client, h)
    app_id = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": item["user_job_id"]}).json()["id"]
    o = client.get(f"{API}/applications/{app_id}/apply-options", headers=h).json()
    assert o["original_supported"] and o["platform"] == "Greenhouse" and o["hosted_form_url"] is None
    clip = import_job(client, h)["user_job_ids"][0]
    app2 = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": clip}).json()["id"]
    o2 = client.get(f"{API}/applications/{app2}/apply-options", headers=h).json()
    assert not o2["original_supported"] and "LinkedIn" in o2["message"]


# ---- unified tracking --------------------------------------------------------------------------

def test_tracking_fields_stages_and_submission_method(client, boards, resume_bytes):
    h = onboard(client, "track@example.com", resume_bytes)
    item = with_board_job(client, h)
    app_id = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": item["user_job_id"]}).json()["id"]
    r = client.put(f"{API}/applications/{app_id}/tracking", headers=h, json={"notes": "Referred by a friend", "follow_up_at": "2026-11-20T10:00:00Z"})
    assert r.status_code == 200 and r.json()["notes"] == "Referred by a friend" and r.json()["follow_up_at"].startswith("2026-11-20")
    # Stages apply only after submission, and include assessment and archived.
    assert client.post(f"{API}/applications/{app_id}/stage", headers=h, json={"stage": "assessment"}).status_code == 409
    client.post(f"{API}/applications/{app_id}/confirm", headers=h, json={"submitted": True})
    for stage in ("assessment", "interview", "archived"):
        assert client.post(f"{API}/applications/{app_id}/stage", headers=h, json={"stage": stage}).json()["stage"] == stage
    a = client.get(f"{API}/applications", headers=h).json()[0]
    assert a["submission_method"] == "Employer website, confirmed in JobPilot"
    # Another user cannot change it.
    hb = onboard(client, "track-b@example.com", resume_bytes)
    assert client.put(f"{API}/applications/{app_id}/tracking", headers=hb, json={"notes": "x"}).status_code == 404
