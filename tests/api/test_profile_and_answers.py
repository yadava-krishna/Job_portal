"""Stage G: resume versions, the verified answer bank, and notification preferences."""

from __future__ import annotations

from api_helpers import onboard

API = "/api/v1"


def test_resume_versions_default_rename_preview_delete(client, resume_bytes):
    h = onboard(client, "rv@example.com", resume_bytes)
    first = client.get(f"{API}/profile/resumes", headers=h).json()
    assert len(first) == 1 and first[0]["is_active"]
    confirmed_before = client.get(f"{API}/profile", headers=h).json()["confirmed"]
    r = client.post(f"{API}/profile/resume", headers=h, params={"make_default": "false", "name": "Resume - FP&A roles"},
                    files={"file": ("x.pdf", resume_bytes, "application/pdf")})
    assert r.status_code == 201
    rs = client.get(f"{API}/profile/resumes", headers=h).json()
    assert len(rs) == 2 and rs[0]["id"] == first[0]["id"] and rs[1]["original_filename"] == "Resume - FP_A roles.pdf"
    second = rs[1]["id"]
    # Switching the default does not touch the confirmed profile.
    rs = client.post(f"{API}/profile/resumes/{second}/default", headers=h).json()
    assert rs[0]["id"] == second and rs[0]["is_active"]
    assert client.get(f"{API}/profile", headers=h).json()["confirmed"] == confirmed_before
    assert client.put(f"{API}/profile/resumes/{second}", headers=h, json={"name": "FPA roles"}).json()["original_filename"] == "FPA roles.pdf"
    f = client.get(f"{API}/profile/resumes/{second}/file", headers=h, params={"inline": "true"})
    assert f.status_code == 200 and f.content == resume_bytes and f.headers["content-disposition"].startswith("inline")
    assert client.delete(f"{API}/profile/resumes/{second}", headers=h).status_code == 409  # the default stays
    assert client.delete(f"{API}/profile/resumes/{first[0]['id']}", headers=h).status_code == 204
    assert [x["id"] for x in client.get(f"{API}/profile/resumes", headers=h).json()] == [second]
    # Another user can't see, use or delete it.
    hb = onboard(client, "rv-b@example.com", resume_bytes)
    assert client.get(f"{API}/profile/resumes/{second}/file", headers=hb).status_code == 404
    assert client.post(f"{API}/profile/resumes/{second}/default", headers=hb).status_code == 404
    assert client.delete(f"{API}/profile/resumes/{second}", headers=hb).status_code == 404


def test_answer_bank_answers_reworded_questions_and_never_sensitive_ones(client, resume_bytes):
    from test_extension import pair, xh

    h = onboard(client, "ab@example.com", resume_bytes)
    facts = {"custom_answers": [
        {"question": "Are you comfortable working from office five days a week?", "answer": "Yes, from our Bengaluru office"},
        {"question": "What is your gender?", "answer": "should never be used"},
    ]}
    assert client.put(f"{API}/profile/verified-facts", headers=h, json=facts).status_code == 200
    tok = pair(client, h)
    qs = ["Are you comfortable working from the office 5 days a week?", "Are you comfortable working from office five days a week",
          "What is your gender?", "Are you comfortable relocating?"]
    out = {a["question"]: a for a in client.post(f"{API}/extension/answers", headers=xh(tok), json={"questions": qs}).json()}
    assert out[qs[1]]["status"] == "VERIFIED" and out[qs[1]]["answer"] == "Yes, from our Bengaluru office"
    assert out[qs[0]]["status"] == "VERIFIED"
    assert out[qs[2]]["status"] == "NEEDS_INPUT"
    assert out[qs[3]]["status"] == "NEEDS_INPUT"


def test_notification_preferences(client, resume_bytes):
    h = onboard(client, "np@example.com", resume_bytes)
    assert client.get(f"{API}/notifications/preferences", headers=h).json() == {
        "new_matches": True, "delivery": "immediate", "min_score": None, "sources": [], "email": "off"}
    r = client.put(f"{API}/notifications/preferences", headers=h, json={"new_matches": True, "delivery": "daily_digest", "min_score": 75,
                                                                       "sources": ["greenhouse"]})
    assert r.json()["delivery"] == "daily_digest" and r.json()["min_score"] == 75
    assert client.put(f"{API}/notifications/preferences", headers=h, json={"email": "daily"}).status_code == 422


def test_notification_preferences_filter_and_digest(app_env, client, resume_bytes):
    from backend.db import session_factory
    from backend.models import Job, Notification, User, UserJob
    from backend.services import notification_service

    onboard(client, "nd@example.com", resume_bytes)
    with session_factory()() as db:
        user = db.query(User).filter(User.email == "nd@example.com").one()
        ujs = []
        for i, (score, source) in enumerate([(90, "greenhouse"), (80, "lever"), (60, "greenhouse"), (85, "greenhouse")]):
            job = Job(job_key=f"k{i}", platform="Greenhouse", source=source, company="C", title=f"T{i}", job_url=f"https://x/{i}")
            db.add(job); db.flush()
            uj = UserJob(user_id=user.id, job_id=job.id, source=source, match_score=score)
            db.add(uj); db.flush()
            ujs.append((uj, source))
        notification_service.save_prefs(db, user, {"new_matches": True, "delivery": "daily_digest", "min_score": 70, "sources": ["greenhouse"]})
        for uj, source in ujs:
            notification_service.notify_new_match(db, user, uj, source)
        db.commit()
        rows = db.query(Notification).filter(Notification.user_id == user.id).all()
        assert len(rows) == 1 and rows[0].kind == "digest" and rows[0].occurrences == 2  # 90 and 85 on Greenhouse
        notification_service.save_prefs(db, user, {"new_matches": False})
        assert notification_service.notify_new_match(db, user, ujs[0][0], "greenhouse") is None
