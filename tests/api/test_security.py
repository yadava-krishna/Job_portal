"""Security regression tests: client-IP resolution, rate-limit bypass attempts, per-account lockout, docs exposure."""

from __future__ import annotations

import pytest
from api_helpers import PASSWORD, register

from backend.api.deps import resolve_client_ip

TRUSTED = ["127.0.0.0/8", "::1/128", "172.16.0.0/12"]
LOGIN = "/api/v1/auth/login"


def _client(app_env, monkeypatch, peer: str, **env):
    from fastapi.testclient import TestClient

    from backend.config import get_settings
    from backend.main import create_app

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return TestClient(create_app(start_scheduler=False), client=(peer, 50000))


def _bad_login(c, email="victim@example.com", password="Wr0ngPassword!", xff=None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    return c.post(LOGIN, json={"email": email, "password": password}, headers=headers).status_code


# --- resolve_client_ip -------------------------------------------------------------------------

@pytest.mark.parametrize("peer, xff, expected", [
    ("203.0.113.9", "1.2.3.4", "203.0.113.9"),                      # untrusted peer: header ignored
    ("203.0.113.9", None, "203.0.113.9"),
    ("172.20.0.5", "198.51.100.7", "198.51.100.7"),                 # proxy appended the real client
    ("172.20.0.5", "6.6.6.6, 198.51.100.7", "198.51.100.7"),        # forged left part never wins
    ("172.20.0.5", "6.6.6.6, 198.51.100.7, 172.21.0.3", "198.51.100.7"),  # skip trusted hops
    ("172.20.0.5", "garbage, 198.51.100.7", "198.51.100.7"),
    ("172.20.0.5", "198.51.100.7, garbage", "172.20.0.5"),          # malformed hop: stop, fall back
    ("172.20.0.5", "127.0.0.1, 172.21.0.3", "127.0.0.1"),           # all trusted: origin hop
    ("172.20.0.5", "198.51.100.7:4711", "198.51.100.7"),            # IPv4 with port
    ("172.20.0.5", "[2001:db8::1]:443", "2001:db8::1"),             # IPv6 with port
    ("::1", "2001:db8::2", "2001:db8::2"),
    (None, "1.2.3.4", "unknown"),
])
def test_resolve_client_ip(peer, xff, expected):
    assert resolve_client_ip(peer, xff, TRUSTED) == expected


def test_resolve_client_ip_ignores_headers_when_disabled():
    assert resolve_client_ip("172.20.0.5", "198.51.100.7", TRUSTED, trust_headers=False) == "172.20.0.5"


# --- Rate-limit bypass attempts ------------------------------------------------------------------

def test_spoofed_forwarded_for_from_untrusted_peer_is_still_limited(app_env, monkeypatch):
    """A direct internet client rotating X-Forwarded-For values must share one bucket (its real address)."""
    with _client(app_env, monkeypatch, "203.0.113.9", AUTH_RATE_LIMIT_PER_MINUTE="3") as c:
        codes = [_bad_login(c, xff=f"10.9.8.{i}") for i in range(5)]
    assert codes == [401, 401, 401, 429, 429]


def test_forged_left_entries_behind_trusted_proxy_are_still_limited(app_env, monkeypatch):
    """Behind the tunnel the client controls the left of the chain; only the proxy-appended address counts."""
    with _client(app_env, monkeypatch, "172.20.0.5", AUTH_RATE_LIMIT_PER_MINUTE="3") as c:
        codes = [_bad_login(c, xff=f"10.9.8.{i}, 198.51.100.7") for i in range(5)]
    assert codes == [401, 401, 401, 429, 429]


def _split_xff(forged: str, real: str) -> list[tuple[str, str]]:
    """The client's header line followed by a second line appended by the proxy (ngrok's behaviour)."""
    return [("X-Forwarded-For", forged), ("X-Forwarded-For", real), ("Content-Type", "application/json")]


def test_forged_header_line_with_proxy_appended_line_is_still_limited(app_env, monkeypatch):
    with _client(app_env, monkeypatch, "172.20.0.5", AUTH_RATE_LIMIT_PER_MINUTE="3") as c:
        body = '{"email": "victim@example.com", "password": "Wr0ngPassword!"}'
        codes = [c.post(LOGIN, content=body, headers=_split_xff(f"10.9.8.{i}", "198.51.100.7")).status_code
                 for i in range(5)]
    assert codes == [401, 401, 401, 429, 429]


def test_distinct_clients_behind_proxy_get_separate_buckets(app_env, monkeypatch):
    with _client(app_env, monkeypatch, "172.20.0.5", AUTH_RATE_LIMIT_PER_MINUTE="2") as c:
        a = [_bad_login(c, xff="198.51.100.7") for _ in range(3)]
        b = [_bad_login(c, xff="198.51.100.8") for _ in range(2)]
    assert a == [401, 401, 429]
    assert b == [401, 401]


def test_rate_limit_response_has_retry_after(app_env, monkeypatch):
    with _client(app_env, monkeypatch, "203.0.113.9", AUTH_RATE_LIMIT_PER_MINUTE="1") as c:
        _bad_login(c)
        r = c.post(LOGIN, json={"email": "victim@example.com", "password": "x"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


# --- Per-account lockout -------------------------------------------------------------------------

def test_account_lock_across_rotating_real_addresses(app_env, monkeypatch):
    """Even an attacker with many real addresses gets a bounded number of guesses per account."""
    with _client(app_env, monkeypatch, "172.20.0.5", LOGIN_FAILURES_PER_ACCOUNT="3") as c:
        register(c, "victim@example.com")
        codes = [_bad_login(c, xff=f"198.51.100.{i}") for i in range(4)]
        # Locked: even the correct password is refused until the window passes.
        locked = _bad_login(c, password=PASSWORD, xff="198.51.100.200")
        other = c.post(LOGIN, json={"email": "someone@example.com", "password": "Wr0ngPassword!"},
                       headers={"X-Forwarded-For": "198.51.100.201"}).status_code
    assert codes == [401, 401, 401, 429]
    assert locked == 429
    assert other == 401  # the lock is per account, not global


def test_account_lock_key_is_case_insensitive(app_env, monkeypatch):
    with _client(app_env, monkeypatch, "203.0.113.9", LOGIN_FAILURES_PER_ACCOUNT="2") as c:
        codes = [_bad_login(c, email=e) for e in ("Victim@Example.com", "victim@example.com", "VICTIM@EXAMPLE.COM")]
    assert codes == [401, 401, 429]


def test_successful_login_clears_failures(app_env, monkeypatch):
    with _client(app_env, monkeypatch, "203.0.113.9", LOGIN_FAILURES_PER_ACCOUNT="3") as c:
        register(c, "victim@example.com")
        assert [_bad_login(c) for _ in range(2)] == [401, 401]
        assert _bad_login(c, password=PASSWORD) == 200
        assert [_bad_login(c) for _ in range(3)] == [401, 401, 401]


# --- API documentation exposure ------------------------------------------------------------------

DOC_PATHS = ("/api/v1/docs", "/api/v1/openapi.json")


def _doc_codes(c, xff=None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    return [c.get(p, headers=headers).status_code for p in (*DOC_PATHS, "/api/v1/redoc", "/redoc", "/docs", "/openapi.json")]


def test_docs_hidden_from_public_in_production(app_env, monkeypatch):
    with _client(app_env, monkeypatch, "203.0.113.9", ENVIRONMENT="production") as c:
        assert _doc_codes(c) == [404] * 6
        assert "docs" not in c.get("/").json()


def test_docs_hidden_from_tunnel_clients_even_with_forged_local_address(app_env, monkeypatch):
    """Through ngrok the peer is trusted, but the proxy-appended public address decides; a forged 127.0.0.1 doesn't help."""
    with _client(app_env, monkeypatch, "172.20.0.5", ENVIRONMENT="production") as c:
        assert _doc_codes(c, xff="198.51.100.7") == [404] * 6
        assert _doc_codes(c, xff="127.0.0.1, 198.51.100.7") == [404] * 6
        split = [c.get(p, headers=_split_xff("127.0.0.1", "198.51.100.7")).status_code for p in DOC_PATHS]
        assert split == [404, 404]


def test_docs_available_locally_in_production(app_env, monkeypatch):
    with _client(app_env, monkeypatch, "127.0.0.1", ENVIRONMENT="production") as c:
        assert _doc_codes(c) == [200, 200, 404, 404, 404, 404]
        assert c.get("/api/v1/openapi.json").json()["info"]["title"] == "JobPilot API"


def test_docs_off_everywhere(app_env, monkeypatch):
    with _client(app_env, monkeypatch, "127.0.0.1", DOCS_MODE="off") as c:
        assert _doc_codes(c) == [404] * 6


def test_docs_public_in_development(app_env, monkeypatch):
    with _client(app_env, monkeypatch, "203.0.113.9", ENVIRONMENT="development") as c:
        assert _doc_codes(c)[:2] == [200, 200]


def test_invalid_docs_mode_rejected(app_env, monkeypatch):
    from backend.config import get_settings

    monkeypatch.setenv("DOCS_MODE", "everyone")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_settings()
