"""Phase 4: the dashboard action centre is built from real rows and is private to each user."""

from __future__ import annotations

from api_helpers import import_job, onboard

API = "/api/v1"


def test_overview_sections_follow_real_state(client, resume_bytes):
    h = onboard(client, "ov1@example.com", resume_bytes)
    empty = client.get(f"{API}/dashboard/overview", headers=h)
    assert empty.status_code == 200, empty.text
    o = empty.json()
    assert o["new_jobs"]["count"] == 0 and o["saved"]["count"] == 0 and o["recent_submitted"] == []
    assert o["discovery"]["state"] == "never_run" and o["resume"]["state"] in ("missing", "not_exported", "ready")

    uj = import_job(client, h)["user_job_ids"][0]
    score = client.get(f"{API}/jobs", headers=h).json()["items"][0]["match_score"]
    o = client.get(f"{API}/dashboard/overview", headers=h).json()
    if score is not None and score >= o["new_jobs"]["min_score"]:
        assert [j["user_job_id"] for j in o["new_jobs"]["top"]] == [uj]
    else:
        assert o["new_jobs"]["count"] == 0  # below the user's own threshold: not shown as a relevant new job

    assert client.post(f"{API}/jobs/{uj}/save", headers=h).status_code in (200, 204)
    o = client.get(f"{API}/dashboard/overview", headers=h).json()
    assert o["saved"]["count"] == 1 and o["saved"]["top"][0]["user_job_id"] == uj

    app_id = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": uj}).json()["id"]
    assert client.post(f"{API}/applications/{app_id}/confirm", headers=h, json={"submitted": True}).status_code == 200
    o = client.get(f"{API}/dashboard/overview", headers=h).json()
    assert o["saved"]["count"] == 0  # applied jobs leave the saved list
    assert [a["application_id"] for a in o["recent_submitted"]] == [app_id] and o["recent_submitted"][0]["stage"] == "applied"


def test_overview_is_private(client, resume_bytes):
    ha = onboard(client, "ov2@example.com", resume_bytes)
    hb = onboard(client, "ov3@example.com", resume_bytes)
    uj = import_job(client, ha)["user_job_ids"][0]
    client.post(f"{API}/jobs/{uj}/save", headers=ha)
    b = client.get(f"{API}/dashboard/overview", headers=hb).json()
    assert b["saved"]["count"] == 0 and b["new_jobs"]["count"] == 0 and b["recent_submitted"] == []
    assert client.get(f"{API}/dashboard/overview").status_code == 401
