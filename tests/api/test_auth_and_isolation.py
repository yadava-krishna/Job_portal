from api_helpers import PASSWORD, auth, import_job, onboard, register


def test_register_login_me(client):
    tokens = register(client, "a@example.com")
    assert tokens["token_type"] == "bearer" and tokens["refresh_token"]
    me = client.get("/api/v1/auth/me", headers=auth(tokens)).json()
    assert me["email"] == "a@example.com"
    r = client.post("/api/v1/auth/login", json={"email": "A@Example.com", "password": PASSWORD})
    assert r.status_code == 200


def test_duplicate_email_and_weak_password(client):
    register(client, "dup@example.com")
    assert client.post("/api/v1/auth/register", json={"email": "dup@example.com", "password": PASSWORD}).status_code == 409
    r = client.post("/api/v1/auth/register", json={"email": "weak@example.com", "password": "password"})
    assert r.status_code == 422 and "requirements" in r.json()["detail"]


def test_wrong_password_is_generic(client):
    register(client, "x@example.com")
    a = client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "WrongPass123"})
    b = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "WrongPass123"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_protected_endpoints_require_token(client):
    for path in ("/api/v1/auth/me", "/api/v1/profile", "/api/v1/jobs", "/api/v1/applications", "/api/v1/reports", "/api/v1/dashboard/summary"):
        assert client.get(path).status_code == 401, path
    assert client.get("/api/v1/jobs", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_refresh_rotation_and_reuse_detection(client):
    t = register(client, "r@example.com")
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]})
    assert r1.status_code == 200
    new = r1.json()
    # Replaying the old (rotated) token revokes the whole session family.
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_logout_revokes_refresh(client):
    t = register(client, "l@example.com")
    assert client.post("/api/v1/auth/logout", headers=auth(t), json={"refresh_token": t["refresh_token"]}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401


def test_invite_code_required_when_configured(app_env, monkeypatch):
    monkeypatch.setenv("REGISTRATION_INVITE_CODE", "letmein-2026")
    from backend.config import get_settings
    from fastapi.testclient import TestClient
    from backend.main import create_app

    get_settings.cache_clear()
    with TestClient(create_app(start_scheduler=False)) as c:
        assert c.get("/api/v1/auth/config").json()["registration_requires_invite"] is True
        assert c.post("/api/v1/auth/register", json={"email": "i@example.com", "password": PASSWORD}).status_code == 403
        assert c.post("/api/v1/auth/register", json={"email": "i@example.com", "password": PASSWORD, "invite_code": "letmein-2026"}).status_code == 201


def test_auth_rate_limit(app_env, monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_PER_MINUTE", "3")
    from backend.config import get_settings
    from backend.security import rate_limiter
    from fastapi.testclient import TestClient
    from backend.main import create_app

    get_settings.cache_clear()
    rate_limiter.reset()
    with TestClient(create_app(start_scheduler=False)) as c:
        codes = [c.post("/api/v1/auth/login", json={"email": "z@example.com", "password": "Whatever123"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3] == 429


def test_user_isolation_across_every_resource(client, resume_bytes):
    ha = onboard(client, "alice@example.com", resume_bytes)
    hb = onboard(client, "bob@example.com", resume_bytes)
    ja = import_job(client, ha)["user_job_ids"][0]
    app_a = client.post("/api/v1/applications/prepare", headers=ha, json={"user_job_id": ja}).json()["id"]
    rep_a = client.post("/api/v1/reports/history", headers=ha).json()["id"]

    # Bob cannot see or act on Alice's job, application or report: always 404.
    for method, path in [
        ("get", f"/api/v1/jobs/{ja}"), ("get", f"/api/v1/jobs/{ja}/analysis"), ("post", f"/api/v1/jobs/{ja}/save"),
        ("post", f"/api/v1/jobs/{ja}/dismiss"), ("get", f"/api/v1/applications/{app_a}"),
        ("post", f"/api/v1/applications/{app_a}/open"), ("get", f"/api/v1/reports/{rep_a}/download"),
    ]:
        assert getattr(client, method)(path, headers=hb).status_code == 404, path
    assert client.post("/api/v1/applications/prepare", headers=hb, json={"user_job_id": ja}).status_code == 404
    assert client.post(f"/api/v1/applications/{app_a}/confirm", headers=hb, json={"submitted": True}).status_code == 404

    # Bob's lists contain none of Alice's data.
    assert client.get("/api/v1/jobs?view=all", headers=hb).json()["total"] == 0
    assert client.get("/api/v1/applications", headers=hb).json() == []
    assert client.get("/api/v1/reports", headers=hb).json() == []
    assert client.get("/api/v1/dashboard/summary", headers=hb).json()["total_discovered"] == 0

    # Same public job imported by Bob: shared listing, separate private feed entry and application.
    jb = import_job(client, hb)["user_job_ids"][0]
    assert jb != ja
    assert client.get(f"/api/v1/jobs/{jb}", headers=hb).json()["job"]["id"] == client.get(f"/api/v1/jobs/{ja}", headers=ha).json()["job"]["id"]
    assert client.get(f"/api/v1/jobs/{jb}", headers=hb).json()["application_id"] is None
