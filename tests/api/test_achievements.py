"""Tests for Phase 6 & 7: Achievements, nicknames, and password reset workflow."""

from __future__ import annotations

from api_helpers import auth, onboard, register


def test_achievements_and_nickname(client, resume_bytes):
    h = onboard(client, "voyager@example.com", resume_bytes)

    # Nickname regenerate
    r = client.post("/api/v1/profile/nickname/regenerate", headers=h)
    assert r.status_code == 200
    nick = r.json()["nickname"]
    assert "_" in nick

    # Achievements
    ach = client.get("/api/v1/profile/achievements", headers=h).json()
    assert len(ach) >= 5
    assert any(a["code"] == "FIRST_RESUME" for a in ach)


def test_password_reset_flow(client, monkeypatch):
    from backend.services import email_service

    tokens = register(client, "resetme@example.com")
    # Without SMTP the server says so instead of pretending a link was sent.
    monkeypatch.setattr(email_service, "test_outbox", None)
    r = client.post("/api/v1/auth/forgot-password", json={"email": "resetme@example.com"})
    assert r.status_code == 503 and "not set up" in r.json()["detail"]

    outbox: list = []
    monkeypatch.setattr(email_service, "test_outbox", outbox)
    assert client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}).status_code == 200
    assert outbox == []  # unknown address: same answer, nothing sent
    r = client.post("/api/v1/auth/forgot-password", json={"email": "resetme@example.com"})
    assert r.status_code == 200 and len(outbox) == 1
    import re
    token = re.search(r"token=([A-Za-z0-9_\-\.]+)", outbox[0]["html"]).group(1)

    r2 = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "NewSecretPassword123!"})
    assert r2.status_code == 200
    # Single use: the same link no longer works, and the old session was signed out.
    again = client.post("/api/v1/auth/reset-password", json={"token": token, "new_password": "OtherSecretPass456!"})
    assert again.status_code == 400
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401

    r3 = client.post("/api/v1/auth/login", json={"email": "resetme@example.com", "password": "NewSecretPassword123!"})
    assert r3.status_code == 200
    assert "access_token" in r3.json()
