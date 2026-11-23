"""V3.2 portal accounts: LinkedIn OpenID Connect, Indeed OAuth, Naukri native hand-off, the shared capability model.

Every provider here is SIMULATED (httpx.MockTransport at the real provider URLs): an RSA key signs the ID tokens and is
published as a JWKS, the token endpoint checks client credentials, redirect URI and the PKCE verifier. No test reaches
LinkedIn or Indeed, and none of this is a verified live connection.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from api_helpers import auth, import_job, onboard, register

API = "/api/v1"
APP = "https://jobpilot.example.test"
LI_ISS = "https://www.linkedin.com/oauth"
INDEED_ISS = "https://secure.indeed.com"


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeProviders:
    """LinkedIn + Indeed at their real endpoint URLs, answering only through the test transport."""

    def __init__(self):
        self.key, self.kid = _key(), "k1"
        self.codes: dict[str, dict] = {}
        self.tokens: dict[str, dict] = {}       # access token -> account
        self.refresh_tokens: dict[str, dict] = {}
        self.revoked: set[str] = set()
        self.calls: list[str] = []
        self.id_token_override = None           # callable(claims) -> token, to forge bad tokens
        self.accounts = {"li-sub-1": {"sub": "li-sub-1", "name": "Test Candidate", "given_name": "Test", "family_name": "Candidate",
                                      "email": "test.candidate@example.com", "email_verified": True, "picture": "https://media.example/p.jpg"}}
        self.indeed_expires = 3600

    def jwks(self) -> dict:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def sign(self, claims: dict, key=None, kid=None, alg="RS256") -> str:
        return jwt.encode(claims, key or self.key, algorithm=alg, headers={"kid": kid or self.kid})

    # The user signs in on the provider and consents: the provider issues a code bound to this request.
    def consent(self, authorization_url: str, account: dict) -> dict:
        q = {k: v[0] for k, v in parse_qs(urlsplit(authorization_url).query).items()}
        code = "code-" + str(len(self.codes) + 1)
        self.codes[code] = {"q": q, "account": account, "host": urlsplit(authorization_url).hostname}
        return q | {"code": code}

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url).split("?")[0]
        self.calls.append(f"{request.method} {url}")
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()} if request.method == "POST" else {}
        if url == "https://www.linkedin.com/oauth/openid/jwks" or url == "https://secure.indeed.com/.well-known/keys":
            return httpx.Response(200, json=self.jwks())
        if url in ("https://www.linkedin.com/oauth/v2/accessToken", "https://apis.indeed.com/oauth/v2/tokens"):
            indeed = "indeed" in url
            if form.get("client_id") != ("in-client" if indeed else "li-client") or form.get("client_secret") != ("in-secret" if indeed else "li-secret"):
                return httpx.Response(401, json={"error": "invalid_client"})
            if form.get("grant_type") == "refresh_token":
                acct = self.refresh_tokens.pop(form.get("refresh_token"), None)
                if acct is None:
                    return httpx.Response(400, json={"error": "invalid_grant"})
                return httpx.Response(200, json=self._issue(acct, indeed=True))
            entry = self.codes.pop(form.get("code"), None)
            if entry is None or form.get("redirect_uri") != entry["q"]["redirect_uri"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            if "code_challenge" in entry["q"]:
                v = form.get("code_verifier") or ""
                if base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode() != entry["q"]["code_challenge"]:
                    return httpx.Response(400, json={"error": "invalid_grant"})
            out = self._issue(entry["account"], indeed=indeed)
            if not indeed:
                claims = {"iss": LI_ISS, "aud": "li-client", "sub": entry["account"]["sub"], "iat": int(time.time()), "exp": int(time.time()) + 3600,
                          **{k: v for k, v in entry["account"].items() if k != "sub"}}
                if entry["q"].get("nonce"):
                    claims["nonce"] = entry["q"]["nonce"]
                out["id_token"] = self.id_token_override(claims) if self.id_token_override else self.sign(claims)
            return httpx.Response(200, json=out)
        if url in ("https://api.linkedin.com/v2/userinfo", "https://secure.indeed.com/v2/api/userinfo"):
            tok = request.headers.get("Authorization", "").removeprefix("Bearer ")
            acct = self.tokens.get(tok)
            if acct is None or tok in self.revoked:
                return httpx.Response(401, json={"error": "invalid_token"})
            return httpx.Response(200, json=acct)
        return httpx.Response(404)

    def _issue(self, acct: dict, *, indeed: bool) -> dict:
        n = len(self.tokens) + 1
        tok = f"AT-{'in' if indeed else 'li'}-{n}-secretvalue"
        self.tokens[tok] = acct
        out = {"access_token": tok, "expires_in": self.indeed_expires if indeed else 5184000, "token_type": "Bearer"}
        if indeed:
            rt = f"RT-in-{n}-secretvalue"
            self.refresh_tokens[rt] = acct
            out.update(refresh_token=rt, scope="email offline_access")
        else:
            out["scope"] = "openid,profile,email"
        return out


@pytest.fixture
def fake(monkeypatch):
    from backend.services import identity_providers

    f = FakeProviders()
    monkeypatch.setattr(identity_providers, "TRANSPORT", httpx.MockTransport(f.handler))
    identity_providers.clear_key_cache()
    yield f
    identity_providers.clear_key_cache()


@pytest.fixture
def pclient(app_env, monkeypatch, fake):
    """API client on a server with LinkedIn and Indeed sign-in configured (simulated providers)."""
    from fastapi.testclient import TestClient

    from backend.config import get_settings
    from backend.main import create_app

    for k, v in {"PUBLIC_APP_URL": APP, "LINKEDIN_CLIENT_ID": "li-client", "LINKEDIN_CLIENT_SECRET": "li-secret",
                 "INDEED_CLIENT_ID": "in-client", "INDEED_CLIENT_SECRET": "in-secret"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    with TestClient(create_app(start_scheduler=False)) as c:
        yield c
    get_settings.cache_clear()


def rows(c, h) -> dict:
    r = c.get(f"{API}/portals", headers=h)
    assert r.status_code == 200, r.text
    return {p["portal"]: p for p in r.json()}


def connect(c, h, fake, portal: str, account: dict, **override) -> httpx.Response:
    r = c.post(f"{API}/portals/{portal}/connect", headers=h)
    assert r.status_code == 200, r.text
    back = fake.consent(r.json()["authorization_url"], account)
    body = {"state": back["state"], "code": back["code"], **({"iss": INDEED_ISS} if portal == "indeed" else {}), **override}
    return c.post(f"{API}/portals/oauth/complete", headers=h, json={k: v for k, v in body.items() if v is not None})


INDEED_ACCT = {"sub": "in-sub-9", "email": "test.candidate@example.com", "email_verified": True}


# ---- LinkedIn ---------------------------------------------------------------------------------------------------------

def test_linkedin_oidc_links_by_subject_with_every_check(pclient, fake):
    h = auth(register(pclient, "v32a@example.com"))
    before = rows(pclient, h)["linkedin"]
    assert before["status"] == "not_linked" and before["actions"][0] == "connect"
    assert before["capabilities"]["identity_auth"]["available"] is True and before["capabilities"]["account_linked"]["available"] is False

    r = pclient.post(f"{API}/portals/linkedin/connect", headers=h).json()
    q = {k: v[0] for k, v in parse_qs(urlsplit(r["authorization_url"]).query).items()}
    assert r["authorization_url"].startswith("https://www.linkedin.com/oauth/v2/authorization?")
    assert q["scope"] == "openid profile email" and q["response_type"] == "code" and q["client_id"] == "li-client"
    assert q["redirect_uri"] == f"{APP}/oauth-callback.html" and len(q["state"]) >= 32 and len(q["nonce"]) >= 24
    assert "code_challenge" not in q  # LinkedIn doesn't advertise PKCE for web apps (LINKEDIN_PKCE=true turns it on)

    back = fake.consent(r["authorization_url"], fake.accounts["li-sub-1"])
    row = pclient.post(f"{API}/portals/oauth/complete", headers=h, json={"state": back["state"], "code": back["code"]})
    assert row.status_code == 200, row.text
    li = row.json()
    assert li["status"] == "linked" and li["identity"]["name"] == "Test Candidate" and li["identity"]["email"] == "test.candidate@example.com"
    assert li["identity"]["checks"]["signature"] == "RS256" and li["identity"]["checks"]["nonce"] == "matched"
    assert li["identity"]["checks"]["issuer"] == LI_ISS and li["identity"]["checks"]["state"] == "bound_to_user"
    assert set(li["scopes"]["granted"]) == {"openid", "profile", "email"}
    caps = li["capabilities"]
    assert caps["account_linked"]["available"] and set(caps["profile_access"]["fields"]) == {"Account ID", "Name", "Profile photo", "E-mail address"}
    # Signing in grants identity only.
    assert caps["job_retrieval"]["available"] is False and caps["application_submission"]["available"] is False
    assert caps["native_handoff"]["available"] is True and li["actions"][:3] == ["check", "reconnect", "disconnect"]
    # Never copied into the verified JobPilot profile.
    prof = pclient.get(f"{API}/profile", headers=h)
    assert "Test Candidate" not in prof.text


@pytest.mark.parametrize("case", ["unknown", "reused", "expired", "other_user"])
def test_linkedin_rejects_bad_state(pclient, fake, case):
    from backend.db import session_factory
    from backend.models import OAuthState

    h = auth(register(pclient, f"v32s-{case}@example.com"))
    r = pclient.post(f"{API}/portals/linkedin/connect", headers=h).json()
    back = fake.consent(r["authorization_url"], fake.accounts["li-sub-1"])
    body = {"state": back["state"], "code": back["code"]}
    if case == "unknown":
        body["state"] = "forged-" + back["state"]
        expect = 400
    elif case == "reused":
        assert pclient.post(f"{API}/portals/oauth/complete", headers=h, json=body).status_code == 200
        expect = 400
    elif case == "expired":
        with session_factory()() as db:
            st = db.query(OAuthState).one()
            st.expires_at = st.created_at - timedelta(seconds=1)
            db.commit()
        expect = 400
    else:  # an attacker's sign-in completed in the victim's session (or the reverse): never linked
        h = auth(register(pclient, "v32s-victim@example.com"))
        expect = 403
    res = pclient.post(f"{API}/portals/oauth/complete", headers=h, json=body)
    assert res.status_code == expect, res.text
    if case != "reused":
        assert rows(pclient, h)["linkedin"]["status"] == "not_linked"
    if case == "other_user":  # burned: the rightful user can't replay it either
        assert fake.codes  # the code was never exchanged


@pytest.mark.parametrize("forge", ["wrong_nonce", "bad_signature", "wrong_audience", "wrong_issuer", "expired", "hs256", "no_id_token"])
def test_linkedin_rejects_invalid_id_tokens(pclient, fake, forge):
    other_key = _key()

    def make(claims):
        if forge == "wrong_nonce":
            return fake.sign({**claims, "nonce": "not-the-nonce"})
        if forge == "bad_signature":
            return fake.sign(claims, key=other_key)
        if forge == "wrong_audience":
            return fake.sign({**claims, "aud": "someone-else"})
        if forge == "wrong_issuer":
            return fake.sign({**claims, "iss": "https://evil.example"})
        if forge == "expired":
            return fake.sign({**claims, "iat": int(time.time()) - 7200, "exp": int(time.time()) - 3600})
        if forge == "hs256":
            return jwt.encode(claims, "li-secret", algorithm="HS256", headers={"kid": fake.kid})
        return None

    fake.id_token_override = make
    h = auth(register(pclient, f"v32t-{forge}@example.com"))
    res = connect(pclient, h, fake, "linkedin", fake.accounts["li-sub-1"])
    assert res.status_code == 400, res.text
    assert "Nothing was linked" in res.json()["detail"] or "expired" in res.json()["detail"]
    assert rows(pclient, h)["linkedin"]["status"] == "not_linked"


def test_linkedin_without_optional_email_and_cancel(pclient, fake):
    h = auth(register(pclient, "v32e@example.com"))
    acct = {"sub": "li-sub-2", "name": "No Mail"}
    fake.accounts["li-sub-2"] = acct
    li = connect(pclient, h, fake, "linkedin", acct).json()
    assert li["status"] == "linked" and li["identity"]["email"] is None and li["identity"]["email_verified"] is None
    assert "E-mail address" in li["capabilities"]["profile_access"]["fields"]  # granted, just not shared by LinkedIn
    # Cancelled on LinkedIn: nothing changes.
    h2 = auth(register(pclient, "v32e2@example.com"))
    r = pclient.post(f"{API}/portals/linkedin/connect", headers=h2).json()
    state = parse_qs(urlsplit(r["authorization_url"]).query)["state"][0]
    res = pclient.post(f"{API}/portals/oauth/complete", headers=h2, json={"state": state, "error": "user_cancelled_authorize",
                                                                          "error_description": "The user cancelled"})
    assert res.status_code == 400 and "cancelled" in res.json()["detail"]
    assert rows(pclient, h2)["linkedin"]["status"] == "not_linked"


def test_one_linkedin_account_cannot_be_linked_to_two_users_and_disconnect(pclient, fake):
    ha = auth(register(pclient, "v32d-a@example.com"))
    hb = auth(register(pclient, "v32d-b@example.com"))
    assert connect(pclient, ha, fake, "linkedin", fake.accounts["li-sub-1"]).status_code == 200
    dup = connect(pclient, hb, fake, "linkedin", fake.accounts["li-sub-1"])
    assert dup.status_code == 409 and "another JobPilot account" in dup.json()["detail"]
    # Cross-user isolation: B sees nothing of A's account and can't act on it.
    b = rows(pclient, hb)["linkedin"]
    assert b["status"] == "not_linked" and b["identity"] is None
    assert pclient.post(f"{API}/portals/linkedin/check", headers=hb).status_code == 404
    assert pclient.delete(f"{API}/portals/linkedin/connection", headers=hb).json()["disconnected"] is False
    assert rows(pclient, ha)["linkedin"]["status"] == "linked"
    # A checks (LinkedIn still accepts the token), then disconnects: tokens deleted, B can now link it.
    assert pclient.post(f"{API}/portals/linkedin/check", headers=ha).json()["status"] == "linked"
    out = pclient.delete(f"{API}/portals/linkedin/connection", headers=ha).json()
    assert out["disconnected"] and "deleted its access tokens" in out["detail"] and out["portal"]["status"] == "not_linked"
    from backend.db import session_factory
    from backend.models import ExternalIdentity
    with session_factory()() as db:
        assert db.query(ExternalIdentity).count() == 0
    assert connect(pclient, hb, fake, "linkedin", fake.accounts["li-sub-1"]).json()["status"] == "linked"


def test_revoked_linkedin_access_asks_to_reconnect_and_reconnect_works(pclient, fake):
    h = auth(register(pclient, "v32r@example.com"))
    connect(pclient, h, fake, "linkedin", fake.accounts["li-sub-1"])
    fake.revoked.update(fake.tokens)  # the member removed JobPilot on LinkedIn
    li = pclient.post(f"{API}/portals/linkedin/check", headers=h).json()
    assert li["status"] == "reconnect_required" and li["capabilities"]["reconnect_required"]["available"]
    assert li["actions"][:2] == ["reconnect", "disconnect"] and li["capabilities"]["account_linked"]["available"] is False
    again = connect(pclient, h, fake, "linkedin", fake.accounts["li-sub-1"]).json()
    assert again["status"] == "linked"


def test_expired_linkedin_token_needs_reconnect(pclient, fake):
    from backend.db import session_factory
    from backend.models import ExternalIdentity, utcnow

    h = auth(register(pclient, "v32x@example.com"))
    connect(pclient, h, fake, "linkedin", fake.accounts["li-sub-1"])
    with session_factory()() as db:
        row = db.query(ExternalIdentity).one()
        row.access_expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    li = rows(pclient, h)["linkedin"]
    assert li["status"] == "reconnect_required" and "expired" in li["identity"]["status_detail"]  # LinkedIn gives no refresh token


# ---- Indeed -----------------------------------------------------------------------------------------------------------

def test_indeed_oauth_with_pkce_iss_refresh_and_unlink(pclient, fake):
    from backend.db import session_factory
    from backend.models import ExternalIdentity, utcnow

    h = auth(register(pclient, "v32i@example.com"))
    r = pclient.post(f"{API}/portals/indeed/connect", headers=h).json()
    q = {k: v[0] for k, v in parse_qs(urlsplit(r["authorization_url"]).query).items()}
    assert r["authorization_url"].startswith("https://secure.indeed.com/oauth/v2/authorize?")
    assert q["code_challenge_method"] == "S256" and q["scope"] == "email offline_access" and "employer_access" not in q["scope"]
    back = fake.consent(r["authorization_url"], INDEED_ACCT)
    # RFC 9207: Indeed sends iss on the redirect; a missing or foreign issuer is refused.
    bad = pclient.post(f"{API}/portals/oauth/complete", headers=h, json={"state": back["state"], "code": back["code"], "iss": "https://evil.example"})
    assert bad.status_code == 400
    ind = connect(pclient, h, fake, "indeed", INDEED_ACCT).json()
    assert ind["status"] == "linked" and ind["identity"]["email"] == INDEED_ACCT["email"] and ind["identity"]["can_refresh"]
    assert ind["identity"]["checks"]["pkce"] is True and ind["capabilities"]["profile_access"]["fields"] == ["E-mail address"]
    assert ind["capabilities"]["job_retrieval"]["available"] is False and "undocumented" in ind["capabilities"]["job_retrieval"]["detail"]
    # The hour-long access token expires: Check refreshes it (Indeed rotates the refresh token).
    with session_factory()() as db:
        row = db.query(ExternalIdentity).one()
        old_rt = row.refresh_token_encrypted
        row.access_expires_at = utcnow() - timedelta(minutes=5)
        db.commit()
    assert rows(pclient, h)["indeed"]["status"] == "linked"  # refreshable, so not "reconnect" yet
    assert pclient.post(f"{API}/portals/indeed/check", headers=h).json()["status"] == "linked"
    assert any("oauth/v2/tokens" in c for c in fake.calls[-3:])
    with session_factory()() as db:
        row = db.query(ExternalIdentity).one()
        assert row.refresh_token_encrypted != old_rt and row.access_expires_at.replace(tzinfo=None) > utcnow().replace(tzinfo=None)
        row.access_expires_at = utcnow() - timedelta(minutes=5)
        db.commit()
    # Indeed refuses the refresh token (permission withdrawn): reconnect required, then unlink.
    fake.refresh_tokens.clear()
    assert pclient.post(f"{API}/portals/indeed/check", headers=h).json()["status"] == "reconnect_required"
    assert pclient.delete(f"{API}/portals/indeed/connection", headers=h).json()["disconnected"]
    assert rows(pclient, h)["indeed"]["status"] == "not_linked"


def test_indeed_permission_denied(pclient, fake):
    h = auth(register(pclient, "v32p@example.com"))
    r = pclient.post(f"{API}/portals/indeed/connect", headers=h).json()
    state = parse_qs(urlsplit(r["authorization_url"]).query)["state"][0]
    res = pclient.post(f"{API}/portals/oauth/complete", headers=h, json={"state": state, "error": "access_denied", "iss": INDEED_ISS})
    assert res.status_code == 400 and "Nothing was linked" in res.json()["detail"]
    assert rows(pclient, h)["indeed"]["status"] == "not_linked"


def test_without_partner_credentials_nothing_pretends_to_connect(client):
    h = auth(register(client, "v32n@example.com"))
    r = rows(client, h)
    for p in ("linkedin", "indeed"):
        assert r[p]["status"] == "not_configured" and r[p]["status_label"] == "Not configured"
        assert r[p]["capabilities"]["identity_auth"] == {**r[p]["capabilities"]["identity_auth"], "available": False, "state": "not_configured"}
        # One plain reason for a candidate (no setting names), said once; no setup action for a non-admin.
        assert "admin needs to add" in r[p]["reason"] and r[p]["capabilities"]["identity_auth"]["detail"] == "Not set up on this JobPilot server yet."
        assert "CLIENT_ID" not in r[p]["reason"] and "setup" not in r[p]["actions"] and r[p]["setup_state"] is None
        assert not {"connect", "reconnect", "check"} & set(r[p]["actions"])  # no button that can't work
        assert client.post(f"{API}/portals/{p}/connect", headers=h).status_code == 409


def test_indeed_employer_access_is_never_requested(app_env, monkeypatch):
    from backend.config import get_settings
    from backend.services import identity_providers

    for k, v in {"PUBLIC_APP_URL": APP, "INDEED_CLIENT_ID": "x", "INDEED_CLIENT_SECRET": "y", "INDEED_SCOPES": "email employer_access"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    p = identity_providers.get(get_settings(), "indeed")
    assert not p.configured and "employer" in p.problem
    monkeypatch.setenv("INDEED_SCOPES", "email job_seeker.jobs.search")
    get_settings.cache_clear()
    assert not identity_providers.get(get_settings(), "indeed").configured  # least privilege: only what JobPilot uses
    monkeypatch.setenv("INDEED_SCOPES", "email offline_access")
    monkeypatch.setenv("INDEED_REDIRECT_URI", "https://app.example/cb#frag")
    get_settings.cache_clear()
    assert "exact" in identity_providers.get(get_settings(), "indeed").problem
    monkeypatch.setenv("INDEED_REDIRECT_URI", "http://app.example/cb")
    get_settings.cache_clear()
    assert "HTTPS" in identity_providers.get(get_settings(), "indeed").problem
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("OAUTH_DEV_ENDPOINTS", json.dumps({"indeed": {"authorize": "http://127.0.0.1:1/a", "token": "http://127.0.0.1:1/t",
                                                                     "userinfo": "http://127.0.0.1:1/u", "jwks": "http://127.0.0.1:1/k", "issuer": "x"}}))
    monkeypatch.setenv("INDEED_REDIRECT_URI", "https://app.example/cb")
    get_settings.cache_clear()
    assert identity_providers.get(get_settings(), "indeed").token_url == "https://apis.indeed.com/oauth/v2/tokens"  # dev endpoints refused
    get_settings.cache_clear()


# ---- Naukri ---------------------------------------------------------------------------------------------------------

def test_naukri_native_handoff_preserves_preparation_and_records_a_user_reported_outcome(pclient, fake, resume_bytes):
    h = onboard(pclient, "v32k@example.com", resume_bytes)
    nk = rows(pclient, h)["naukri"]
    assert nk["status"] == "native_only" and nk["kind"] == "native" and nk["identity"] is None
    assert nk["capabilities"]["identity_auth"]["available"] is False and nk["capabilities"]["account_linked"]["available"] is False
    assert nk["capabilities"]["native_handoff"]["available"] and "connect" not in nk["actions"] and "open" in nk["actions"]
    assert "password" in nk["capabilities"]["identity_auth"]["detail"]
    assert pclient.post(f"{API}/portals/naukri/connect", headers=h).status_code == 404

    url = "https://www.naukri.com/job-listings-accounts-receivable-analyst-acme-health-bengaluru-3-to-5-years-231125000001"
    uj = import_job(pclient, h, url=url)["user_job_ids"][0]
    app = pclient.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": uj}).json()
    pkg = pclient.get(f"{API}/applications/{app['id']}/package", headers=h).json()["package"]
    dest = pkg["destination"]
    assert dest["kind"] == "restricted" and dest["platform_name"] == "Naukri" and dest["url"] == url
    assert pkg["capabilities"]["native_handoff"] and not pkg["capabilities"]["autofill"] and not pkg["capabilities"]["assisted_submit"]
    assert pkg["resume"]["selected_by"] is None and pkg["readiness"]["resume_choice_needed"]  # explicit choice, never a default
    rec = pkg["resume"]["recommended"]
    chosen = pclient.put(f"{API}/applications/{app['id']}/resume", headers=h, json={"kind": rec["kind"], "id": rec["id"]}).json()["package"]["resume"]
    assert chosen["selected_by"] == "you"

    out = pclient.post(f"{API}/applications/{app['id']}/handoff", headers=h).json()
    assert out["url"] == url  # the original Naukri listing, opened in the user's own browser
    detail = out["application"]
    assert detail["status"] != "SUBMITTED"  # opening the page is not applying
    after = pclient.get(f"{API}/applications/{app['id']}/package", headers=h).json()["package"]
    assert after["resume"]["selected_by"] == "you" and after["resume"]["checksum"] == chosen["checksum"]  # preparation kept

    done = pclient.post(f"{API}/applications/{app['id']}/confirm", headers=h, json={"submitted": True}).json()
    assert done["status"] == "SUBMITTED"
    from backend.db import session_factory
    from backend.models import Application
    with session_factory()() as db:
        a = db.get(Application, app["id"])
        assert a.apply_state == "user_reported" and a.apply_session["confirmation"]["confidence"] == "self_reported"
    assert not any("naukri" in c for c in fake.calls)  # JobPilot never talked to Naukri


# ---- shared -----------------------------------------------------------------------------------------------------------

def test_tokens_never_leave_the_backend_and_are_encrypted_at_rest(pclient, fake, caplog):
    import logging

    caplog.set_level(logging.INFO)
    h = auth(register(pclient, "v32sec@example.com"))
    res = connect(pclient, h, fake, "indeed", INDEED_ACCT)
    all_text = res.text + pclient.get(f"{API}/portals", headers=h).text + pclient.post(f"{API}/portals/indeed/check", headers=h).text
    for secret in [*fake.tokens, *fake.refresh_tokens, "in-secret", "li-secret"]:
        assert secret not in all_text
    from backend.db import session_factory
    from backend.models import AuditLog, ExternalIdentity
    with session_factory()() as db:
        row = db.query(ExternalIdentity).one()
        assert "secretvalue" not in (row.access_token_encrypted or "") + (row.refresh_token_encrypted or "")
        audit = " ".join(json.dumps(a.details) for a in db.query(AuditLog).all())
        assert "secretvalue" not in audit and "@" not in audit
    exported = pclient.get(f"{API}/account/export", headers=h)
    assert exported.status_code == 200 and exported.json()["linked_portal_accounts"][0]["provider"] == "indeed"
    assert "secretvalue" not in exported.text and "token_encrypted" not in exported.text
    assert "secretvalue" not in caplog.text and "code-" not in caplog.text


def test_existing_user_auth_is_unchanged_and_account_deletion_removes_links(pclient, fake):
    from api_helpers import PASSWORD

    h = auth(register(pclient, "v32del@example.com"))
    connect(pclient, h, fake, "linkedin", fake.accounts["li-sub-1"])
    # Login still works only with the JobPilot password; a portal account is never a way in.
    assert pclient.post(f"{API}/auth/login", json={"email": "v32del@example.com", "password": PASSWORD}).status_code == 200
    r = pclient.post(f"{API}/account/delete", headers=h, json={"password": PASSWORD, "confirm": "DELETE"})
    assert r.status_code in (200, 204), r.text
    from backend.db import session_factory
    from backend.models import ExternalIdentity, OAuthState
    with session_factory()() as db:
        assert db.query(ExternalIdentity).count() == 0 and db.query(OAuthState).count() == 0


def test_provider_job_records_map_with_provenance_but_no_portal_is_approved(client):
    from backend.models import utcnow
    from backend.services import provider_jobs

    now = utcnow()
    nj = provider_jobs.to_normalized("indeed", {"id": "abc123", "title": "AR Analyst", "company": "Acme", "location": "Bengaluru, India",
                                                "description": "<p>Cash <b>posting</b></p>", "url": "https://in.indeed.com/viewjob?jk=abc123",
                                                "apply_url": "https://acme.example/careers/1", "posted_at": "2026-11-20"}, verified_at=now)
    assert (nj.source, nj.source_key, nj.external_job_id, nj.platform) == ("indeed_api", "indeed_api:abc123", "abc123", "Indeed")
    assert nj.job_url.endswith("jk=abc123") and nj.application_url == "https://acme.example/careers/1"
    assert nj.posted_at_source == "platform_api" and nj.observed_at == now and nj.description == "Cash posting"
    assert provider_jobs.to_normalized("linkedin", {"id": "1", "title": "T", "company": "C", "url": "https://x"}, verified_at=now).posted_at is None
    with pytest.raises(ValueError):
        provider_jobs.to_normalized("naukri", {"id": "1", "title": "T"}, verified_at=now)
    h = auth(register(client, "v32j@example.com"))
    from fastapi import HTTPException
    from backend.db import session_factory
    from backend.models import User
    with session_factory()() as db:
        u = db.query(User).filter_by(email="v32j@example.com").one()
        for p in ("linkedin", "indeed", "naukri"):
            with pytest.raises(HTTPException) as e:
                provider_jobs.ingest(db, u, p, [], verified_at=now)
            assert e.value.status_code == 403
    assert h


def test_a_transient_indeed_outage_keeps_the_link_and_rotation_updates_refresh_expiry(pclient, fake):
    from backend.db import session_factory
    from backend.models import ExternalIdentity, utcnow

    h = auth(register(pclient, "v32o@example.com"))
    connect(pclient, h, fake, "indeed", INDEED_ACCT)

    def expire(refresh_in_minutes=None):
        with session_factory()() as db:
            row = db.query(ExternalIdentity).one()
            row.access_expires_at = utcnow() - timedelta(minutes=5)
            if refresh_in_minutes is not None:
                row.refresh_expires_at = utcnow() + timedelta(minutes=refresh_in_minutes)
            db.commit()

    expire()
    real = fake.handler
    fake.handler = lambda r: httpx.Response(503, text="down") if "oauth/v2/tokens" in str(r.url) else real(r)
    from backend.services import identity_providers
    identity_providers.TRANSPORT = httpx.MockTransport(lambda r: fake.handler(r))
    res = pclient.post(f"{API}/portals/indeed/check", headers=h)
    assert res.status_code == 502  # Indeed hiccup: said so, link untouched
    assert rows(pclient, h)["indeed"]["status"] == "linked"
    fake.handler = real
    # The rotated refresh token's expiry is recorded, so a stale earlier expiry can't force a reconnect later.
    expire(refresh_in_minutes=1)
    real_issue = fake._issue
    fake._issue = lambda acct, indeed: {**real_issue(acct, indeed=indeed), "refresh_token_expires_in": 86400 * 30}
    assert pclient.post(f"{API}/portals/indeed/check", headers=h).json()["status"] == "linked"
    with session_factory()() as db:
        assert db.query(ExternalIdentity).one().refresh_expires_at.replace(tzinfo=None) > (utcnow() + timedelta(days=29)).replace(tzinfo=None)


def test_a_long_provider_error_description_still_reports_the_cancel(pclient, fake):
    h = auth(register(pclient, "v32l@example.com"))
    r = pclient.post(f"{API}/portals/linkedin/connect", headers=h).json()
    state = parse_qs(urlsplit(r["authorization_url"]).query)["state"][0]
    res = pclient.post(f"{API}/portals/oauth/complete", headers=h, json={"state": state, "error": "user_cancelled_login", "error_description": "x" * 3000})
    assert res.status_code == 400 and "cancelled" in res.json()["detail"]


def test_a_local_simulated_sign_in_server_is_labelled_everywhere(app_env, monkeypatch, fake):
    """OAUTH_DEV_ENDPOINTS (local demos only): the card and the linked identity say SIMULATED, never 'verified by LinkedIn'."""
    from fastapi.testclient import TestClient

    from backend.config import get_settings
    from backend.main import create_app

    li = {"authorize": "https://www.linkedin.com/oauth/v2/authorization", "token": "https://www.linkedin.com/oauth/v2/accessToken",
          "userinfo": "https://api.linkedin.com/v2/userinfo", "jwks": "https://www.linkedin.com/oauth/openid/jwks", "issuer": LI_ISS}
    for k, v in {"PUBLIC_APP_URL": APP, "LINKEDIN_CLIENT_ID": "li-client", "LINKEDIN_CLIENT_SECRET": "li-secret",
                 "OAUTH_DEV_ENDPOINTS": json.dumps({"linkedin": li})}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    with TestClient(create_app(start_scheduler=False)) as c:
        h = auth(register(c, "v32sim@example.com"))
        row = rows(c, h)["linkedin"]
        assert row["simulated"] is True and row["capabilities"]["identity_auth"]["detail"].startswith("SIMULATED")
        assert rows(c, h)["indeed"]["simulated"] is False
        linked = connect(c, h, fake, "linkedin", fake.accounts["li-sub-1"]).json()
        assert linked["identity"]["simulated"] is True and linked["status_label"] == "Connected (simulated)"
    get_settings.cache_clear()
