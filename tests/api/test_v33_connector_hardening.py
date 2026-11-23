"""V3.3 connector hardening: a dedicated ENCRYPTION_KEY for connector secrets (no JWT_SECRET fallback), key loss and
rotation, backend-enforced connection readiness, and real vs simulated separation.

Providers are SIMULATED with httpx.MockTransport at the real LinkedIn/Indeed URLs (FakeProviders from the V3.2 tests).
"""

from __future__ import annotations

import httpx
import pytest
from cryptography.fernet import Fernet

from api_helpers import auth, register
from test_v32_portal_accounts import FakeProviders, fake, rows  # noqa: F401 (fixture)
from test_v33_portal_setup import API, APP, make_admin, run_test, save, setup_rows

KEY_A, KEY_B = Fernet.generate_key().decode(), Fernet.generate_key().decode()


@pytest.fixture
def server(app_env, monkeypatch, fake):
    """Start a server with the given environment: server(ENCRYPTION_KEY=..., ...). Reconfigurable within a test."""
    from fastapi.testclient import TestClient

    from backend.config import get_settings
    from backend.main import create_app

    clients = []

    def make(**env):
        for k in ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET", "INDEED_CLIENT_ID", "INDEED_CLIENT_SECRET", "OAUTH_DEV_ENDPOINTS",
                  "ENCRYPTION_KEY", "ENCRYPTION_KEY_PREVIOUS"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("PUBLIC_APP_URL", APP)
        for k, v in env.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, v)
        get_settings.cache_clear()
        if not clients:
            clients.append(TestClient(create_app(start_scheduler=False)).__enter__())
        return clients[0]

    yield make
    for c in clients:
        c.__exit__(None, None, None)
    get_settings.cache_clear()


def db():
    from backend.db import session_factory

    return session_factory()()


def config_row(provider="linkedin"):
    from backend.models import PortalProviderConfig

    with db() as s:
        return s.query(PortalProviderConfig).filter_by(provider=provider).one_or_none()


# ---- 1. dedicated encryption key ----------------------------------------------------------------------------------------

def test_without_encryption_key_saving_secrets_is_off_and_nothing_else_breaks(server):
    c = server(ENCRYPTION_KEY=None)
    a = make_admin(c)
    s = setup_rows(c, a)["linkedin"]
    assert s["secret_storage"]["state"] == "missing" and s["secret_storage"]["can_save"] is False
    assert "ENCRYPTION_KEY" in s["secret_storage"]["detail"] and "JWT_SECRET" in s["secret_storage"]["detail"]
    r = save(c, a, "linkedin", "li-client", "li-secret")
    assert r.status_code == 409 and "ENCRYPTION_KEY" in r.json()["detail"] and "li-secret" not in r.text
    assert config_row() is None  # nothing stored, no key generated
    # Unrelated features keep working.
    assert c.get(f"{API}/portals", headers=a).status_code == 200
    assert c.get(f"{API}/jobs", headers=a).status_code == 200
    assert c.post(f"{API}/jobs/import/preview", headers=a, json={"url": "https://www.linkedin.com/jobs/view/4000000001/"}).json()["recognized"]


def test_an_invalid_encryption_key_is_refused_not_replaced(server):
    c = server(ENCRYPTION_KEY="not-a-fernet-key")
    a = make_admin(c)
    assert setup_rows(c, a)["linkedin"]["secret_storage"]["state"] == "invalid"
    assert save(c, a, "linkedin", "li-client", "li-secret").status_code == 409 and config_row() is None


def test_secrets_use_the_dedicated_key_never_the_jwt_secret(server):
    from backend.config import get_settings
    from backend.security import ConnectorSecretCipher, connector_key_id, legacy_jwt_derived_key

    c = server(ENCRYPTION_KEY=KEY_A)
    a = make_admin(c)
    assert save(c, a, "linkedin", "li-client", "li-secret").status_code == 200
    row = config_row()
    assert row.client_secret_key_id == connector_key_id(KEY_A)
    assert Fernet(KEY_A.encode()).decrypt(row.client_secret_encrypted.encode()) == b"li-secret"
    legacy = ConnectorSecretCipher(get_settings(), key=legacy_jwt_derived_key(get_settings()))
    assert legacy._fernet_try(row.client_secret_encrypted) is None
    assert KEY_A not in str(setup_rows(c, a))  # the key itself is never shown, only its id


# ---- key loss, rotation and recovery ---------------------------------------------------------------------------------

def test_a_lost_key_makes_saved_secrets_unusable_explicitly_and_they_are_never_silently_kept(server):
    c = server(ENCRYPTION_KEY=KEY_A)
    a = make_admin(c)
    save(c, a, "linkedin", "li-client", "li-secret")
    cand = auth(register(c, "cand@example.com"))
    server(ENCRYPTION_KEY=KEY_B)  # the key changed and the old one wasn't kept
    s = setup_rows(c, a)["linkedin"]
    assert s["secret_status"] == "unreadable" and s["configured"] is False and "can't be decrypted" in s["problem"]
    assert row_key_id_in(s["problem"])
    assert rows(c, cand)["linkedin"]["status"] == "not_configured"
    assert c.post(f"{API}/portals/linkedin/connect", headers=cand).status_code == 409
    kept = save(c, a, "linkedin", "li-client")  # keeping a secret nobody can read is refused
    assert kept.status_code == 409 and "can't be read" in kept.json()["detail"]
    assert config_row().client_secret_encrypted  # and it wasn't overwritten
    assert save(c, a, "linkedin", "li-client", "li-secret-2").status_code == 200  # re-entering it is the recovery
    assert rows(c, cand)["linkedin"]["status"] == "not_linked"


def row_key_id_in(text: str) -> bool:
    from backend.security import connector_key_id

    return connector_key_id(KEY_A) in text


def test_previous_key_keeps_working_during_rotation_and_the_tool_reencrypts(server, capsys):
    from backend.scripts import connector_secrets

    c = server(ENCRYPTION_KEY=KEY_A)
    a = make_admin(c)
    save(c, a, "linkedin", "li-client", "li-secret")
    before = config_row().client_secret_encrypted
    server(ENCRYPTION_KEY=KEY_B, ENCRYPTION_KEY_PREVIOUS=KEY_A)
    s = setup_rows(c, a)["linkedin"]
    assert s["configured"] and s["secret_status"] == "needs_rotation"
    assert connector_secrets.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "opens_with=['previous']" in out and "li-secret" not in out
    connector_secrets.main(["rotate", "--from", "previous"])  # dry run
    assert "would re-encrypt" in capsys.readouterr().out and config_row().client_secret_encrypted == before
    connector_secrets.main(["rotate", "--from", "previous", "--apply"])
    assert "re-encrypted" in capsys.readouterr().out
    server(ENCRYPTION_KEY=KEY_B)  # the old key can now go
    s = setup_rows(c, a)["linkedin"]
    assert s["configured"] and s["secret_status"] == "ok"


def test_recovering_a_secret_saved_under_the_old_jwt_derived_key(server, capsys):
    from backend.config import get_settings
    from backend.models import PortalProviderConfig
    from backend.scripts import connector_secrets
    from backend.security import legacy_jwt_derived_key

    c = server(ENCRYPTION_KEY=KEY_B)
    a = make_admin(c)
    legacy = Fernet(legacy_jwt_derived_key(get_settings()).encode())
    with db() as s:  # what a pre-hardening server would have stored without ENCRYPTION_KEY
        s.add(PortalProviderConfig(provider="indeed", client_id="in-client", client_secret_encrypted=legacy.encrypt(b"in-secret").decode()))
        s.commit()
    assert setup_rows(c, a)["indeed"]["secret_status"] == "unreadable"
    connector_secrets.main(["status"])
    assert "opens_with=['legacy-jwt']" in capsys.readouterr().out
    connector_secrets.main(["rotate", "--from", "legacy-jwt", "--apply"])
    assert "re-encrypted" in capsys.readouterr().out
    s = setup_rows(c, a)["indeed"]
    assert s["configured"] and s["secret_status"] == "ok"
    with pytest.raises(SystemExit):  # refuses without a dedicated key
        server(ENCRYPTION_KEY=None)
        connector_secrets.main(["rotate", "--from", "legacy-jwt", "--apply"])


# ---- 2. backend-enforced readiness -------------------------------------------------------------------------------------

@pytest.mark.parametrize("error,state,blocks", [
    ("redirect_uri_mismatch", "invalid_callback", True),
    ("invalid_client", "invalid_credentials", True),
    ("unauthorized_client", "authorization_required", True),
    ("invalid_scope", "authorization_required", True),
    ("temporarily_unavailable", "provider_unavailable", False),
    ("access_denied", "consent_declined", False),
])
def test_each_test_outcome_maps_to_its_readiness_and_only_definite_ones_block(server, fake, error, state, blocks):
    c = server(ENCRYPTION_KEY=KEY_A)
    a = make_admin(c)
    cand = auth(register(c, "cand@example.com"))
    save(c, a, "linkedin", "li-client", "li-secret")
    run_test(c, a, fake, "linkedin", fake.accounts["li-sub-1"], code=None, error=error)
    ready = setup_rows(c, a)["linkedin"]["readiness"]
    assert ready["state"] == state and ready["blocks_connect"] is blocks
    li = rows(c, cand)["linkedin"]
    assert ("connect" in li["actions"]) is (not blocks)
    assert (c.post(f"{API}/portals/linkedin/connect", headers=cand).status_code == 409) is blocks


def test_a_provider_outage_during_the_test_is_temporary(server, fake, monkeypatch):
    c = server(ENCRYPTION_KEY=KEY_A)
    a = make_admin(c)
    save(c, a, "linkedin", "li-client", "li-secret")
    real = fake.handler
    monkeypatch.setattr(fake, "handler", lambda req: httpx.Response(503) if "accessToken" in str(req.url) else real(req))
    from backend.services import identity_providers

    monkeypatch.setattr(identity_providers, "TRANSPORT", httpx.MockTransport(lambda req: fake.handler(req)))
    _, r = run_test(c, a, fake, "linkedin", fake.accounts["li-sub-1"])
    assert r.status_code == 502
    ready = setup_rows(c, a)["linkedin"]["readiness"]
    assert ready["state"] == "provider_unavailable" and ready["blocks_connect"] is False


def test_a_verified_test_and_a_missing_callback(server, fake):
    c = server(ENCRYPTION_KEY=KEY_A)
    a = make_admin(c)
    save(c, a, "linkedin", "li-client", "li-secret")
    run_test(c, a, fake, "linkedin", fake.accounts["li-sub-1"])
    assert setup_rows(c, a)["linkedin"]["readiness"]["state"] == "verified"
    server(ENCRYPTION_KEY=KEY_A, PUBLIC_APP_URL=None)  # the server forgot its public address
    ready = setup_rows(c, a)["linkedin"]["readiness"]
    assert ready["state"] == "invalid_callback" and ready["blocks_connect"]
    server(ENCRYPTION_KEY=KEY_A, PUBLIC_APP_URL="https://other.example.test")  # a different callback: the old result no longer applies
    assert setup_rows(c, a)["linkedin"]["readiness"]["state"] == "unverified"


def test_a_candidate_cannot_change_readiness_with_a_forged_error(server, fake):
    c = server(ENCRYPTION_KEY=KEY_A)
    a = make_admin(c)
    save(c, a, "linkedin", "li-client", "li-secret")
    cand = auth(register(c, "cand@example.com"))
    st = c.post(f"{API}/portals/linkedin/connect", headers=cand).json()["authorization_url"]
    state = httpx.URL(st).params["state"]
    r = c.post(f"{API}/portals/oauth/complete", headers=cand, json={"state": state, "error": "invalid_client"})
    assert r.status_code == 502
    assert setup_rows(c, a)["linkedin"]["readiness"]["state"] == "unverified"
    assert "connect" in rows(c, cand)["linkedin"]["actions"]


# ---- 3. real and simulated stay apart ----------------------------------------------------------------------------------

def test_a_simulated_test_never_changes_the_real_verification(server, fake):
    from backend.config import get_settings
    from backend.services import identity_providers, portal_setup_service

    c = server(ENCRYPTION_KEY=KEY_A)
    a = make_admin(c)
    save(c, a, "linkedin", "li-client", "li-secret")
    run_test(c, a, fake, "linkedin", fake.accounts["li-sub-1"])
    sim = identity_providers._replace(identity_providers.get(get_settings(), "linkedin"), simulated=True)
    with db() as s:
        portal_setup_service.record_test(s, sim, "authorization_required", "simulated refusal")
    row = setup_rows(c, a)["linkedin"]
    assert row["readiness"]["state"] == "verified" and row["last_test"]["status"] == "verified"
    assert row["simulated_test"]["status"] == "authorization_required" and row["simulated_test"]["simulated"] is True


def test_a_simulated_identity_never_shows_as_a_real_linked_account(server, fake):
    from backend.models import ExternalIdentity, User

    c = server(ENCRYPTION_KEY=KEY_A)
    a = make_admin(c)
    save(c, a, "linkedin", "li-client", "li-secret")
    cand = auth(register(c, "cand@example.com"))
    with db() as s:  # linked earlier while this server used the local simulator
        uid = s.query(User).filter_by(email="cand@example.com").one().id
        s.add(ExternalIdentity(user_id=uid, provider="linkedin", subject="sim-li-7Qx2", name="Test Candidate", scopes=["openid"],
                               access_token_encrypted="x", checks={"simulated": True}))
        s.commit()
    li = rows(c, cand)["linkedin"]
    assert li["status"] == "reconnect_required" and li["identity"]["simulated"] is True and "simulator" in li["reason"]
    assert li["capabilities"]["account_linked"]["available"] is False and "(simulated)" in li["status_label"]
    calls = len(fake.calls)
    out = c.post(f"{API}/portals/linkedin/check", headers=cand).json()
    assert out["status"] == "reconnect_required" and len(fake.calls) == calls  # its token never went to the real LinkedIn


def test_simulator_endpoints_are_ignored_in_production():
    from backend.config import get_settings
    from backend.services import identity_providers

    s = get_settings().model_copy(update={
        "environment": "production", "public_app_url": "https://jobs.example.test", "linkedin_client_id": "li", "linkedin_client_secret": "x",
        "oauth_dev_endpoints": {"linkedin": {"authorize": "http://127.0.0.1:9/a", "token": "http://127.0.0.1:9/t",
                                             "userinfo": "http://127.0.0.1:9/u", "jwks": "http://127.0.0.1:9/j", "issuer": "http://127.0.0.1:9"}}})
    p = identity_providers.get(s, "linkedin")
    assert p.simulated is False and p.authorize_url == "https://www.linkedin.com/oauth/v2/authorization" and p.issuers[0].startswith("https://www.linkedin.com")
