"""Stage G: resume versions, the verified answer bank, and notification preferences."""

from __future__ import annotations

from api_helpers import onboard

API = "/api/v1"
KINDS = ("new_match", "follow_up_due", "interview_upcoming", "application_incomplete", "listing_closed", "discovery_failed")
ALL_ON = dict.fromkeys(KINDS, True)


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
        "new_matches": True, "delivery": "immediate", "min_score": None, "sources": [], "email": "off", "kinds": ALL_ON}
    r = client.put(f"{API}/notifications/preferences", headers=h, json={"new_matches": True, "delivery": "daily_digest", "min_score": 75,
                                                                       "sources": ["greenhouse"]})
    assert r.json()["delivery"] == "daily_digest" and r.json()["min_score"] == 75
    assert client.put(f"{API}/notifications/preferences", headers=h, json={"email": "daily"}).status_code == 422


def test_notification_kind_switches_round_trip(client, resume_bytes):
    h = onboard(client, "nk@example.com", resume_bytes)
    url = f"{API}/notifications/preferences"
    client.put(url, headers=h, json={"delivery": "daily_digest", "min_score": 70, "sources": ["lever"]})

    # PATCH changes only what it names: the new-match settings and the other switches are untouched.
    r = client.patch(url, headers=h, json={"kinds": {"listing_closed": False, "discovery_failed": False}})
    assert r.status_code == 200
    body = r.json()
    assert body["kinds"] == {**ALL_ON, "listing_closed": False, "discovery_failed": False}
    assert (body["delivery"], body["min_score"], body["sources"], body["new_matches"]) == ("daily_digest", 70, ["lever"], True)
    assert client.get(url, headers=h).json() == body

    # kinds.new_match and new_matches are one switch, whichever way it is set.
    r = client.patch(url, headers=h, json={"kinds": {"new_match": False, "listing_closed": True}})
    assert r.json()["new_matches"] is False and r.json()["kinds"] == {**ALL_ON, "new_match": False, "discovery_failed": False}
    r = client.patch(url, headers=h, json={"new_matches": True})
    assert r.json()["kinds"]["new_match"] is True and r.json()["kinds"]["discovery_failed"] is False

    # An older client's PUT (no kinds) replaces the new-match settings and leaves the switches alone.
    r = client.put(url, headers=h, json={"new_matches": True, "delivery": "immediate", "min_score": None, "sources": [], "email": "off"})
    assert r.json()["kinds"]["discovery_failed"] is False and r.json()["delivery"] == "immediate"
    # A PUT that echoes back a GET (kinds included) works too.
    echoed = {**r.json(), "kinds": {**r.json()["kinds"], "follow_up_due": False}}
    assert client.put(url, headers=h, json=echoed).json()["kinds"]["follow_up_due"] is False

    # Unknown kinds and nulls for required fields are rejected; nothing is half-saved.
    assert client.patch(url, headers=h, json={"kinds": {"not_a_kind": False}}).status_code == 422
    assert client.patch(url, headers=h, json={"delivery": None}).status_code == 422
    assert client.patch(url, headers=h, json={"min_score": None}).json()["min_score"] is None  # null = use each search's threshold


def test_notification_prefs_read_older_stored_shapes(client, resume_bytes):
    from backend.db import session_factory
    from backend.models import NotificationPref, User

    h = onboard(client, "nold@example.com", resume_bytes)
    with session_factory()() as db:
        uid = db.query(User.id).filter(User.email == "nold@example.com").scalar()
        # Shapes written before per-type switches: the API's new_match dict, the sweep's {"in_app": false}, a bare false.
        db.add(NotificationPref(user_id=uid, email_digest="off", kinds={
            "new_match": {"new_matches": True, "delivery": "daily_digest", "min_score": None, "sources": []},
            "follow_up_due": {"in_app": False}, "listing_closed": False, "interview_upcoming": {"email": True}}))
        db.commit()
    body = client.get(f"{API}/notifications/preferences", headers=h).json()
    assert body["delivery"] == "daily_digest"
    assert body["kinds"] == {**ALL_ON, "follow_up_due": False, "listing_closed": False}
    # Switching one back on keeps the other keys stored for that type.
    client.patch(f"{API}/notifications/preferences", headers=h, json={"kinds": {"listing_closed": True, "interview_upcoming": False}})
    with session_factory()() as db:
        kinds = db.query(NotificationPref).filter(NotificationPref.user_id == uid).one().kinds
    assert kinds["listing_closed"] == {"in_app": True} and kinds["interview_upcoming"] == {"email": True, "in_app": False}
    assert kinds["new_match"]["delivery"] == "daily_digest"


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
