"""V3.3 Portal Connections: admin setup of LinkedIn/Indeed sign-in, the admin's real-flow test, role separation, the
status model shown on the cards, Naukri hand-off rows, and the job-link preview used by guided import.

Providers are SIMULATED with httpx.MockTransport at the real LinkedIn/Indeed URLs (FakeProviders from the V3.2 tests).
No test reaches LinkedIn or Indeed, and none of this is a verified live connection.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from api_helpers import auth, import_job, onboard, register
from test_v32_portal_accounts import INDEED_ACCT, INDEED_ISS, FakeProviders, fake, rows  # noqa: F401 (fixture)

API = "/api/v1"
APP = "https://jobpilot.example.test"
NAUKRI_URL = "https://www.naukri.com/job-listings-accounts-receivable-analyst-acme-health-bengaluru-3-to-6-years-120325001234"


@pytest.fixture
def sclient(app_env, monkeypatch, fake):
    """A server that knows its public address but has no portal credentials in its environment."""
    from fastapi.testclient import TestClient

    from backend.config import get_settings
    from backend.main import create_app

    monkeypatch.setenv("PUBLIC_APP_URL", APP)
    for k in ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "INDEED_CLIENT_ID", "INDEED_CLIENT_SECRET", "OAUTH_DEV_ENDPOINTS"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    with TestClient(create_app(start_scheduler=False)) as c:
        yield c
    get_settings.cache_clear()


def make_admin(c, email="admin@example.com") -> dict:
    tokens = register(c, email)
    from backend.db import session_factory
    from backend.models import User

    with session_factory()() as db:
        db.query(User).filter(User.email == email).one().role = "admin"
        db.commit()
    return auth(tokens)


def setup_rows(c, h) -> dict:
    r = c.get(f"{API}/admin/portals", headers=h)
    assert r.status_code == 200, r.text
    return {p["provider"]: p for p in r.json()}


def save(c, h, provider, client_id, secret=None):
    return c.put(f"{API}/admin/portals/{provider}/credentials", headers=h,
                 json={"client_id": client_id, **({"client_secret": secret} if secret is not None else {})})


def run_test(c, h, fake, provider, account, **override):
    r = c.post(f"{API}/admin/portals/{provider}/test", headers=h)
    assert r.status_code == 200, r.text
    url = r.json()["authorization_url"]
    back = fake.consent(url, account)
    body = {"state": back["state"], "code": back["code"], **({"iss": INDEED_ISS} if provider == "indeed" else {}), **override}
    return url, c.post(f"{API}/portals/oauth/complete", headers=h, json={k: v for k, v in body.items() if v is not None})


def identities() -> int:
    from backend.db import session_factory
    from backend.models import ExternalIdentity

    with session_factory()() as db:
        return db.query(ExternalIdentity).count()


# ---- roles ------------------------------------------------------------------------------------------------------------

def test_only_admins_reach_setup(sclient):
    h = auth(register(sclient, "cand@example.com"))
    assert sclient.get(f"{API}/admin/portals", headers=h).status_code == 403
    assert save(sclient, h, "linkedin", "li-client", "li-secret").status_code == 403
    assert sclient.delete(f"{API}/admin/portals/linkedin/credentials", headers=h).status_code == 403
    assert sclient.post(f"{API}/admin/portals/linkedin/test", headers=h).status_code == 403
    assert sclient.get(f"{API}/admin/portals").status_code == 401
    r = rows(sclient, h)["linkedin"]
    assert "setup" not in r["actions"] and r["setup_state"] is None and "CLIENT" not in r["reason"]
    a = make_admin(sclient)
    ra = rows(sclient, a)["linkedin"]
    assert "setup" in ra["actions"] and ra["setup_state"] == "not_configured" and "Set it up" in ra["reason"]
    assert "setup" not in rows(sclient, a)["naukri"]["actions"]  # Naukri has nothing to set up


# ---- setup overview ---------------------------------------------------------------------------------------------------

def test_setup_shows_the_real_callback_from_configuration(sclient, monkeypatch):
    a = make_admin(sclient)
    li, ind = setup_rows(sclient, a)["linkedin"], setup_rows(sclient, a)["indeed"]
    assert li["redirect_uri"] == f"{APP}/oauth-callback.html" and li["redirect_from"] == "PUBLIC_APP_URL" and li["redirect_problem"] is None
    assert li["state"] == "not_configured" and li["configured"] is False and li["has_secret"] is False and li["client_id"] is None
    assert li["links"]["console"] == "https://www.linkedin.com/developers/apps" and li["product"] == "Sign In with LinkedIn using OpenID Connect"
    assert li["scopes"] == ["openid", "profile", "email"] and li["env_names"] == ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"]
    assert ind["links"]["console"] == "https://docs.indeed.com/getstarted/partner-console"
    assert ind["scopes"] == ["email", "offline_access"] and ind["pkce"] is True
    # An explicit redirect setting wins and is named as the source.
    from backend.config import get_settings

    monkeypatch.setenv("LINKEDIN_REDIRECT_URI", "https://app.example.test/cb/oauth-callback.html")
    get_settings.cache_clear()
    li = setup_rows(sclient, a)["linkedin"]
    assert li["redirect_uri"] == "https://app.example.test/cb/oauth-callback.html" and li["redirect_from"] == "LINKEDIN_REDIRECT_URI"
    # No public address known: no made-up localhost value, and it says what to set.
    monkeypatch.delenv("LINKEDIN_REDIRECT_URI")
    monkeypatch.delenv("PUBLIC_APP_URL")
    get_settings.cache_clear()
    li = setup_rows(sclient, a)["linkedin"]
    assert li["redirect_uri"] is None and "PUBLIC_APP_URL" in li["redirect_problem"]


# ---- credentials ------------------------------------------------------------------------------------------------------

def test_saved_credentials_are_encrypted_and_never_returned(sclient):
    a = make_admin(sclient)
    assert save(sclient, a, "linkedin", "li-client").status_code == 422          # a secret is needed the first time
    assert save(sclient, a, "linkedin", "bad id with spaces", "x").status_code == 422
    assert save(sclient, a, "linkedin", "li-client", "has space").status_code == 422
    r = save(sclient, a, "linkedin", "li-client", "li-secret")
    assert r.status_code == 200 and "li-secret" not in r.text
    out = r.json()
    assert out["configured"] and out["source"] == "admin" and out["has_secret"] and out["client_id"] == "li-client" and out["state"] == "ready_to_test"
    assert "li-secret" not in sclient.get(f"{API}/admin/portals", headers=a).text
    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import AuditLog, PortalProviderConfig
    from backend.security import CredentialCipher

    with session_factory()() as db:
        row = db.query(PortalProviderConfig).filter_by(provider="linkedin").one()
        assert row.client_secret_encrypted != "li-secret" and CredentialCipher(get_settings()).decrypt(row.client_secret_encrypted) == "li-secret"
        assert all("li-secret" not in str(e.details) for e in db.query(AuditLog).all())
    # Saving again without a secret keeps the saved one.
    assert save(sclient, a, "linkedin", "li-client").json()["has_secret"] is True
    # Candidates can now connect; the button goes to the real LinkedIn, never the simulator.
    c = auth(register(sclient, "cand@example.com"))
    li = rows(sclient, c)["linkedin"]
    assert li["status"] == "not_linked" and li["status_label"] == "Ready to connect" and "connect" in li["actions"] and not li["simulated"]
    url = sclient.post(f"{API}/portals/linkedin/connect", headers=c).json()["authorization_url"]
    assert urlsplit(url).hostname == "www.linkedin.com" and parse_qs(urlsplit(url).query)["client_id"] == ["li-client"]
    # Removing them turns sign-in off again.
    assert sclient.delete(f"{API}/admin/portals/linkedin/credentials", headers=a).json()["configured"] is False
    assert rows(sclient, c)["linkedin"]["status"] == "not_configured"


def test_server_environment_settings_take_precedence(sclient, monkeypatch):
    from backend.config import get_settings

    a = make_admin(sclient)
    monkeypatch.setenv("INDEED_CLIENT_ID", "in-client")
    monkeypatch.setenv("INDEED_CLIENT_SECRET", "in-secret")
    get_settings.cache_clear()
    ind = setup_rows(sclient, a)["indeed"]
    assert ind["source"] == "env" and ind["editable"] is False and ind["has_secret"] and "in-secret" not in str(ind)
    r = save(sclient, a, "indeed", "other-client", "other-secret")
    assert r.status_code == 409 and "environment" in r.json()["detail"]


def test_admin_saved_credentials_never_use_the_simulator(sclient, monkeypatch):
    from backend.config import get_settings

    a = make_admin(sclient)
    monkeypatch.setenv("OAUTH_DEV_ENDPOINTS", '{"linkedin": {"authorize": "http://127.0.0.1:9/a", "token": "http://127.0.0.1:9/t", '
                                              '"userinfo": "http://127.0.0.1:9/u", "jwks": "http://127.0.0.1:9/j", "issuer": "http://127.0.0.1:9"}}')
    get_settings.cache_clear()
    save(sclient, a, "linkedin", "li-client", "li-secret")
    li = setup_rows(sclient, a)["linkedin"]
    assert li["simulated"] is False and li["state"] == "ready_to_test"
    url = sclient.post(f"{API}/admin/portals/linkedin/test", headers=a).json()["authorization_url"]
    assert url.startswith("https://www.linkedin.com/oauth/v2/authorization?")


# ---- the admin's real-flow test --------------------------------------------------------------------------------------

def test_linkedin_test_connection_verifies_and_links_nothing(sclient, fake):
    a = make_admin(sclient)
    save(sclient, a, "linkedin", "li-client", "li-secret")
    url, r = run_test(sclient, a, fake, "linkedin", fake.accounts["li-sub-1"])
    assert url.startswith("https://www.linkedin.com/oauth/v2/authorization?")
    assert r.status_code == 200, r.text
    t = r.json()["setup_test"]
    assert t["status"] == "verified" and t["simulated"] is False and "Nothing was linked" in t["detail"]
    assert r.json()["identity"] is None and identities() == 0  # no account linked, no token kept
    assert setup_rows(sclient, a)["linkedin"]["state"] == "verified"
    assert "AT-li" not in r.text


def test_refused_app_shows_provider_authorization_required(sclient, fake):
    a = make_admin(sclient)
    c = auth(register(sclient, "cand@example.com"))
    save(sclient, a, "linkedin", "li-client", "wrong-secret")
    _, r = run_test(sclient, a, fake, "linkedin", fake.accounts["li-sub-1"])
    assert r.status_code == 502 and "refused JobPilot's app" in r.json()["detail"]
    s = setup_rows(sclient, a)["linkedin"]
    assert s["state"] == "authorization_required" and s["last_test"]["status"] == "authorization_required"
    li = rows(sclient, c)["linkedin"]
    assert li["status"] == "authorization_required" and li["status_label"] == "Provider authorization required"
    assert "connect" not in li["actions"] and "refused" in li["reason"]
    # The provider refusing at its own sign-in page counts the same.
    _, r = run_test(sclient, a, fake, "linkedin", fake.accounts["li-sub-1"], code=None, error="unauthorized_client")
    assert r.status_code == 502 and setup_rows(sclient, a)["linkedin"]["last_test"]["status"] == "authorization_required"
    # New credentials clear the old verdict.
    save(sclient, a, "linkedin", "li-client", "li-secret")
    assert setup_rows(sclient, a)["linkedin"]["last_test"] is None and rows(sclient, c)["linkedin"]["status"] == "not_linked"


def test_indeed_setup_test_uses_pkce_and_iss_and_records_cancel(sclient, fake):
    a = make_admin(sclient)
    save(sclient, a, "indeed", "in-client", "in-secret")
    url, r = run_test(sclient, a, fake, "indeed", INDEED_ACCT)
    q = parse_qs(urlsplit(url).query)
    assert urlsplit(url).hostname == "secure.indeed.com" and q["code_challenge_method"] == ["S256"] and q["scope"] == ["email offline_access"]
    assert r.status_code == 200 and r.json()["setup_test"]["status"] == "verified" and identities() == 0
    # A foreign issuer fails the test.
    _, r = run_test(sclient, a, fake, "indeed", INDEED_ACCT, iss="https://evil.example")
    assert r.status_code == 400 and setup_rows(sclient, a)["indeed"]["last_test"]["status"] == "failed"
    # Cancelling on Indeed is recorded as cancelled, not as a broken setup.
    _, r = run_test(sclient, a, fake, "indeed", INDEED_ACCT, code=None, error="access_denied")
    s = setup_rows(sclient, a)["indeed"]
    assert r.status_code == 400 and s["last_test"]["status"] == "cancelled" and s["state"] == "ready_to_test"


def test_a_candidate_cannot_finish_an_admins_test(sclient, fake):
    a = make_admin(sclient)
    save(sclient, a, "linkedin", "li-client", "li-secret")
    started = sclient.post(f"{API}/admin/portals/linkedin/test", headers=a).json()["authorization_url"]
    back = fake.consent(started, fake.accounts["li-sub-1"])
    c = auth(register(sclient, "cand@example.com"))
    r = sclient.post(f"{API}/portals/oauth/complete", headers=c, json={"state": back["state"], "code": back["code"]})
    assert r.status_code == 403 and identities() == 0


# ---- card states --------------------------------------------------------------------------------------------------------

def test_card_states_connected_limited_reconnect_and_naukri(sclient, fake):
    from test_v32_portal_accounts import connect

    a = make_admin(sclient)
    save(sclient, a, "linkedin", "li-client", "li-secret")
    c = auth(register(sclient, "cand@example.com"))
    assert connect(sclient, c, fake, "linkedin", fake.accounts["li-sub-1"]).status_code == 200
    li = rows(sclient, c)["linkedin"]
    assert li["status"] == "linked" and li["status_label"] == "Connected" and not li["limited"]
    assert li["actions"][:3] == ["check", "reconnect", "disconnect"]
    from backend.db import session_factory
    from backend.models import ExternalIdentity

    with session_factory()() as db:
        db.query(ExternalIdentity).one().scopes = ["openid", "email"]
        db.commit()
    li = rows(sclient, c)["linkedin"]
    assert li["limited"] and li["status_label"] == "Connected with limited permissions" and "Profile photo" not in li["capabilities"]["profile_access"]["fields"]
    with session_factory()() as db:
        db.query(ExternalIdentity).one().status = "reconnect_required"
        db.commit()
    li = rows(sclient, c)["linkedin"]
    assert li["status_label"] == "Reconnect required" and li["reason"] and "connect" not in li["actions"] and "reconnect" in li["actions"]
    nk = rows(sclient, c)["naukri"]
    assert nk["status"] == "native_only" and nk["status_label"] == "Opens in browser" and nk["identity"] is None
    assert nk["url"] == "https://www.naukri.com/" and not {"connect", "reconnect", "check", "setup"} & set(nk["actions"])
    assert {"open", "import", "prepare", "optimize"} <= set(nk["actions"])
    ind = rows(sclient, c)["indeed"]
    assert "optimize" not in ind["actions"] and ind["capabilities"]["profile_guidance"]["available"] is False


# ---- guided import --------------------------------------------------------------------------------------------------------

def test_job_link_preview_recognises_without_saving_then_counts_on_the_card(sclient, resume_bytes):
    h = onboard(sclient, "imp@example.com", resume_bytes)
    p = sclient.post(f"{API}/jobs/import/preview", headers=h, json={"url": NAUKRI_URL}).json()
    assert p["recognized"] and p["platform"] == "Naukri" and p["job_id"] == "120325001234" and p["existing"] is None
    assert "reads only the link" in p["detail"]
    assert sclient.get(f"{API}/jobs", headers=h, params={"view": "all"}).json()["total"] == 0  # nothing saved
    other = sclient.post(f"{API}/jobs/import/preview", headers=h, json={"url": "https://example.com/careers/123"}).json()
    assert other["recognized"] is False and "enter the job's details yourself" in other["detail"]
    assert sclient.post(f"{API}/jobs/import/preview", headers=h, json={"url": "not a url"}).status_code == 422
    assert rows(sclient, h)["naukri"]["capabilities"]["listings"] == {**rows(sclient, h)["naukri"]["capabilities"]["listings"], "available": False, "count": 0}
    out = import_job(sclient, h, url=NAUKRI_URL, title="Accounts Receivable Analyst", company="Acme Health")
    again = sclient.post(f"{API}/jobs/import/preview", headers=h, json={"url": NAUKRI_URL}).json()
    assert again["existing"]["user_job_id"] == out["user_job_ids"][0] and again["existing"]["company"] == "Acme Health"
    listings = rows(sclient, h)["naukri"]["capabilities"]["listings"]
    assert listings["available"] and listings["count"] == 1 and "1 Naukri job in" in listings["detail"]
    assert rows(sclient, h)["linkedin"]["capabilities"]["listings"]["count"] == 0
