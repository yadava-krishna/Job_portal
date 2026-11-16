"""Smart Apply: the application state machine the extension reports into, duplicate prevention, recovery after a
browser restart, resume choice (uploads and Resume Studio exports) and matching employer-hosted pages by URL."""

from __future__ import annotations

from api_helpers import import_job, onboard
from test_extension import boards, pair, with_board_job, xh  # noqa: F401  (fixture re-export)

API = "/api/v1"


def _start(client, h, tok, boards_fixture=None) -> tuple[int, int]:
    item = with_board_job(client, h)
    r = client.post(f"{API}/extension/applications/start", headers=xh(tok), json={"user_job_id": item["user_job_id"]})
    assert r.status_code == 200, r.text
    return r.json()["application_id"], item["user_job_id"]


def _state(client, tok, app_id, state, **body):
    return client.post(f"{API}/extension/applications/{app_id}/state", headers=xh(tok), json={"state": state, **body})


def test_states_move_in_order_and_a_click_is_never_a_submission(client, resume_bytes, boards):
    h = onboard(client, "sa1@example.com", resume_bytes)
    tok = pair(client, h)
    app_id, _ = _start(client, h, tok)

    # Authorising without a review is refused.
    assert _state(client, tok, app_id, "filling", mode="assisted_submit").status_code == 200
    assert _state(client, tok, app_id, "submission_authorized").status_code == 409
    r = _state(client, tok, app_id, "ready_for_review", session={"counts": {"filled": 9, "needs": 1}, "page": "https://job-boards.greenhouse.io/x/jobs/1?token=secret"})
    assert r.status_code == 200 and r.json()["apply_counts"] == {"filled": 9, "needs": 1}
    assert _state(client, tok, app_id, "reviewed", session={"fingerprint": "abc123"}).status_code == 200
    assert _state(client, tok, app_id, "submission_authorized").status_code == 200
    r = _state(client, tok, app_id, "submission_pending")
    assert r.status_code == 200 and r.json()["status"] == "OPENED"  # clicked, not submitted

    # Confirmed only with a signal from the employer's page.
    assert _state(client, tok, app_id, "submitted_confirmed").status_code == 422
    r = _state(client, tok, app_id, "submitted_confirmed", session={"signal": "Thank you for applying (confirmation page)"}, reference_id="GH-77")
    body = r.json()
    assert r.status_code == 200 and body["status"] == "SUBMITTED" and body["apply_state"] == "submitted_confirmed" and body["submitted_at"]

    # Duplicate prevention: a submitted application can never be authorised or submitted again.
    for s in ("reviewed", "submission_authorized", "submission_pending"):
        r = _state(client, tok, app_id, s)
        assert r.status_code == 409 and "already submitted" in r.json()["detail"]

    from backend.db import session_factory
    from backend.models import Application, ApplicationEvent

    with session_factory()() as db:
        app = db.get(Application, app_id)
        assert app.reference_id == "GH-77" and app.confirmation_source == "smart_apply_assisted"
        assert app.apply_session["page"] == "https://job-boards.greenhouse.io/x/jobs/1"  # query string never stored
        steps = [e.to_status for e in db.query(ApplicationEvent).filter_by(application_id=app_id, event_type="APPLY_STATE").order_by(ApplicationEvent.id)]
    assert steps == ["filling", "ready_for_review", "reviewed", "submission_authorized", "submission_pending", "submitted_confirmed"]


def test_uncertain_outcome_waits_for_the_user_and_survives_a_restart(client, resume_bytes, boards):
    h = onboard(client, "sa2@example.com", resume_bytes)
    tok = pair(client, h)
    app_id, _ = _start(client, h, tok)
    assert _state(client, tok, app_id, "submission_pending", mode="autofill_review").status_code == 200  # user clicked the site's own submit
    r = _state(client, tok, app_id, "submission_uncertain", session={"message": "No confirmation seen within 30 s"})
    assert r.status_code == 200 and r.json()["status"] == "CONFIRMATION_PENDING"

    # After a browser restart the extension reads the state back.
    r = client.get(f"{API}/extension/applications/{app_id}", headers=xh(tok)).json()
    assert r["apply_state"] == "submission_uncertain" and r["apply_mode"] == "autofill_review"
    assert r["apply_state_label"].startswith("Submission uncertain")

    # The user says what happened.
    r = client.post(f"{API}/extension/applications/{app_id}/confirm", headers=xh(tok), json={"submitted": False}).json()
    assert r["status"] == "PREPARED" and r["apply_state"] == "cancelled"
    # A new attempt can start again after a cancellation.
    assert _state(client, tok, app_id, "ready_to_fill").status_code == 200


def test_other_users_cannot_touch_my_application_state(client, resume_bytes, boards):
    ha = onboard(client, "sa3a@example.com", resume_bytes)
    hb = onboard(client, "sa3b@example.com", resume_bytes)
    ta, tb = pair(client, ha), pair(client, hb)
    app_id, _ = _start(client, ha, ta)
    assert _state(client, tb, app_id, "filling").status_code == 404
    assert client.get(f"{API}/extension/applications/{app_id}", headers=xh(tb)).status_code == 404
    assert _state(client, ta, app_id, "not-a-state").status_code == 422


def test_resume_choice_lists_uploads_and_studio_versions_and_serves_each(client, resume_bytes):
    h = onboard(client, "sa4@example.com", resume_bytes)
    tok = pair(client, h)
    v = client.post(f"{API}/studio/versions", headers=h, json={"name": "Product CV", "template_key": "ats_simple"})
    assert v.status_code in (200, 201), v.text
    choices = client.get(f"{API}/extension/resumes", headers=xh(tok)).json()
    kinds = {(c["kind"], tuple(c["formats"])) for c in choices}
    assert ("upload", ("pdf",)) in kinds and ("studio", ("pdf", "docx")) in kinds
    up = next(c for c in choices if c["kind"] == "upload")
    assert up["active"]

    r = client.get(f"{API}/extension/resume", headers=xh(tok))  # default: the active upload
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.headers["x-resume-sha256"]) == 64
    sid = next(c["id"] for c in choices if c["kind"] == "studio")
    pdf = client.get(f"{API}/extension/resume", headers=xh(tok), params={"kind": "studio", "id": sid, "format": "pdf"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and "Product_CV.pdf" in pdf.headers["content-disposition"]
    docx = client.get(f"{API}/extension/resume", headers=xh(tok), params={"kind": "studio", "id": sid, "format": "docx"})
    assert docx.status_code == 200 and docx.content[:2] == b"PK" and "wordprocessingml" in docx.headers["content-type"]
    assert client.get(f"{API}/extension/resume", headers=xh(tok), params={"kind": "studio", "id": sid, "format": "exe"}).status_code == 422

    # Someone else's resumes are invisible.
    hb = onboard(client, "sa4b@example.com", resume_bytes)
    tb = pair(client, hb)
    assert client.get(f"{API}/extension/resume", headers=xh(tb), params={"kind": "studio", "id": sid}).status_code == 404
    assert client.get(f"{API}/extension/resume", headers=xh(tb), params={"kind": "upload", "id": up["id"]}).status_code == 404


def test_autofill_profile_splits_location_and_phone_and_marks_them_derived(client, resume_bytes):
    from backend.db import session_factory
    from backend.models import CandidateProfile, User

    h = onboard(client, "sa5@example.com", resume_bytes)
    with session_factory()() as db:
        u = db.query(User).filter_by(email="sa5@example.com").one()
        p = db.query(CandidateProfile).filter_by(user_id=u.id).one()
        p.confirmed_profile = {**p.confirmed_profile, "location": "Bengaluru, Karnataka, India", "phone": "+91 90000 12345"}
        db.commit()
    f = client.get(f"{API}/extension/autofill-profile", headers=xh(pair(client, h))).json()["fields"]
    assert (f["city"], f["state"], f["country"]) == ("Bengaluru", "Karnataka", "India")
    assert (f["phone_country_code"], f["phone_national"]) == ("+91", "9000012345")
    assert {"city", "state", "country", "phone_country_code"} <= set(f["_derived"]) and "email" not in f["_derived"]


def test_employer_hosted_page_matches_one_of_my_jobs_by_its_link(client, resume_bytes):
    h = onboard(client, "sa6@example.com", resume_bytes)
    tok = pair(client, h)
    job = import_job(client, h)
    from backend.db import session_factory
    from backend.models import Job, UserJob

    with session_factory()() as db:  # a job whose listing lives on the employer's Workday site
        j = db.get(Job, db.get(UserJob, job["user_job_ids"][0]).job_id)
        j.application_url = "https://acme.wd3.myworkdayjobs.com/en-US/careers/job/Bengaluru/AR-Analyst_R123"
        db.commit()
    m = client.post(f"{API}/extension/match", headers=xh(tok),
                    json={"url": "https://acme.wd3.myworkdayjobs.com/en-US/careers/job/Bengaluru/AR-Analyst_R123/apply/applyManually?x=1"}).json()
    assert m["in_jobpilot"] and m["user_job_id"] == job["user_job_ids"][0], m
    # A different page on the same site is not guessed to be this job.
    m = client.post(f"{API}/extension/match", headers=xh(tok), json={"url": "https://acme.wd3.myworkdayjobs.com/en-US/careers"}).json()
    assert not m["in_jobpilot"]


def test_saved_answers_keep_provenance_and_one_job_answers_are_only_suggestions(client, resume_bytes):
    h = onboard(client, "sa7@example.com", resume_bytes)
    tok = pair(client, h)
    body = {"notice_period": "30 days", "custom_answers": [
        {"question": "Are you comfortable working from office five days a week?", "answer": "Yes"},
        {"question": "Why do you want to work at Acme Health?", "answer": "Their AR automation work.", "applies_to": "one_job",
         "note": "Acme Health", "created_at": "2001-01-01T00:00:00Z"}]}
    f1 = client.put(f"{API}/profile/verified-facts", headers=h, json=body).json()["verified_facts"]
    a1 = f1["custom_answers"]
    assert all(a["created_at"] and a["updated_at"] for a in a1)
    assert not a1[1]["created_at"].startswith("2001")  # the client cannot set provenance
    assert f1["_updated"]["notice_period"]

    # Saving again without changes keeps the timestamps; changing one answer moves only its updated_at.
    body["custom_answers"][0]["answer"] = "Yes, from Bengaluru"
    f2 = client.put(f"{API}/profile/verified-facts", headers=h, json=body).json()["verified_facts"]
    a2 = f2["custom_answers"]
    assert a2[0]["created_at"] == a1[0]["created_at"] and a2[0]["updated_at"] >= a1[0]["updated_at"]
    assert a2[1]["updated_at"] == a1[1]["updated_at"] and f2["_updated"]["notice_period"] == f1["_updated"]["notice_period"]

    got = {a["question"]: a for a in client.post(f"{API}/extension/answers", headers=xh(tok), json={"questions": [
        "Are you comfortable working from office five days a week?", "Why do you want to work at Acme Health?"]}).json()}
    assert got["Are you comfortable working from office five days a week?"]["status"] == "VERIFIED"
    one = got["Why do you want to work at Acme Health?"]
    assert one["status"] == "SUGGESTED" and "specific job" in one["reason"]
