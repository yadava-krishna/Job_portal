"""Smart Apply completion: answer memory, the application preflight package, destination resolution, the native
hand-off, evidence-graded submission states, recovery, and the extension's learn/prove endpoints."""

from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

import pytest
from api_helpers import import_job, onboard
from test_extension import GH_JOB, boards, pair, with_board_job, xh  # noqa: F401  (fixture re-export)

API = "/api/v1"
GH_QUESTIONS = {"id": 101, "title": "Accounts Receivable Analyst", "questions": [
    {"label": "First Name", "required": True, "fields": [{"name": "first_name", "type": "input_text", "values": []}]},
    {"label": "Resume/CV", "required": True, "fields": [{"name": "resume", "type": "input_file", "values": []}]},
    {"label": "What is your notice period?", "required": True, "fields": [{"name": "question_1", "type": "input_text", "values": []}]},
    {"label": "How many years of SAP experience do you have?", "required": True,
     "fields": [{"name": "question_2", "type": "input_text", "values": []}]},
    {"label": "Are you legally authorized to work in India?", "required": True,
     "fields": [{"name": "question_3", "type": "multi_value_single_select", "values": [{"label": "Yes", "value": 1}, {"label": "No", "value": 0}]}]},
    {"label": "Why do you want to work at Acme?", "required": False, "fields": [{"name": "question_4", "type": "textarea", "values": []}]},
]}


# ---- answer memory: pure classification and parsing -----------------------------------------

def test_equivalent_wordings_share_one_key_and_different_meanings_do_not():
    from backend.services.answer_memory import classify

    same = ["How many years of Python experience do you have?", "Total professional Python experience?",
            "Python development experience in years?", "Years working professionally with Python?"]
    assert {classify(q).key for q in same} == {"experience_years.python"}
    assert classify("Total software experience").key == "experience_years.software"
    assert classify("Total experience including internships").key == "experience_years.total.incl_internships"
    assert classify("Total years of experience").key == "experience_years.total"
    assert classify("Relevant experience in years").scope == "job"  # never reused across jobs
    assert classify("Are you authorized to work in the United States?").key == "work_authorization.us"
    assert classify("Are you authorised to work in the UK without sponsorship?").key == "work_authorization.uk"
    assert classify("Will you require visa sponsorship to work in the US?").key == "requires_sponsorship.us"
    assert classify("Have you worked for this company before?").scope == "company"


def test_sensitive_third_party_and_mixed_questions_are_never_auto_answered():
    from backend.services.answer_memory import classify

    for q in ("Gender", "Are you a protected veteran?", "Date of birth", "Disability status", "PAN number", "Are you at least 18 years of age?"):
        assert classify(q).never, q
    assert classify("Referrer's LinkedIn profile").key is None
    assert classify("Company website").key is None
    mixed = classify("Notice period and expected CTC")
    assert mixed.confidence < 0.75 and mixed.notes


def test_units_and_types_are_validated():
    from backend.services.answer_memory import InvalidAnswer, parse

    assert parse("days", "2 months") == (60, "60 days")
    assert parse("days", "Immediate") == (0, "Immediate")
    assert parse("number", "18 months")[0] == 1.5
    assert parse("money", "12 LPA")[0] == {"amount": 1_200_000, "currency": "INR", "period": "year"}
    assert parse("money", "$120k")[0]["currency"] == "USD"
    assert parse("boolean", "yes") == (True, "Yes")
    for t, v in (("number", "2-3"), ("number", "seventy"), ("days", "400 days"), ("boolean", "maybe"), ("money", "10-12 LPA")):
        with pytest.raises(InvalidAnswer):
            parse(t, v)


# ---- the package, answer reuse and learning --------------------------------------------------

def _prepare(client, h, user_job_id):
    r = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": user_job_id})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_first_application_asks_then_second_reuses_verified_answers(client, resume_bytes, boards):
    boards.payloads[("gh_questions", "acmefintech", "101")] = GH_QUESTIONS
    h = onboard(client, "aw1@example.com", resume_bytes)
    item = with_board_job(client, h)
    app_id = _prepare(client, h, item["user_job_id"])

    pkg = client.get(f"{API}/applications/{app_id}/package", headers=h).json()["package"]
    assert pkg["destination"]["kind"] == "ats" and pkg["destination"]["verified"] and pkg["capabilities"]["assisted_submit"]
    assert pkg["questions_source"] == "employer_api" and pkg["readiness"]["form_inspected"]
    labels = {a["question"]: a for a in pkg["answers"]}
    assert "First Name" not in labels and "Resume/CV" not in labels  # standard fields come from the profile
    assert labels["What is your notice period?"]["status"] == "NEEDS_INPUT"  # replaced the common wording, never guessed
    assert labels["How many years of SAP experience do you have?"]["status"] == "NEEDS_INPUT"
    assert pkg["readiness"]["level"] == "needs_input" and pkg["action"] == "review_autofill"

    # Answer in the workspace: SAP years remembered, the motivation text only for this job.
    r = client.post(f"{API}/applications/{app_id}/answers", headers=h, json={"items": [
        {"question": "What is your notice period?", "answer": "1 month", "remember": True},
        {"question": "How many years of SAP experience do you have?", "answer": "4", "remember": True},
        {"question": "Expected CTC", "answer": "14 LPA", "remember": True},
        {"question": "Why do you want to work at Acme?", "answer": "Payments at scale.", "remember": False},
        {"question": "Gender", "answer": "x", "remember": True}]})
    body = r.json()
    assert r.status_code == 200 and len(body["saved"]) == 3 and body["errors"][0]["question"] == "Gender"
    answers = {a["question"]: a for a in body["package"]["answers"]}
    assert answers["What is your notice period?"]["answer"] == "30 days"
    assert answers["Why do you want to work at Acme?"]["source"] == "this_application"

    # A second employer form, worded differently: reused from memory, verified.
    from backend.db import session_factory
    from backend.models import AnswerMemory, User
    from backend.services import answer_memory
    from backend.config import get_settings

    with session_factory()() as db:
        user = db.query(User).filter_by(email="aw1@example.com").one()
        res = {a["question"]: a for a in answer_memory.resolve(db, get_settings(), user, [
            "Notice period (days)", "Total SAP experience in years?", "Salary expectations", "How many years of Java experience?"])}
        assert res["Notice period (days)"]["status"] == "VERIFIED" and res["Notice period (days)"]["answer"] == "30 days"
        assert res["Total SAP experience in years?"]["answer"] == "4"
        assert res["Salary expectations"]["answer"] == "14 LPA" and res["Salary expectations"]["confirm"]
        assert res["How many years of Java experience?"]["status"] == "NEEDS_INPUT"  # never inferred from SAP
        row = db.query(AnswerMemory).filter_by(user_id=user.id, key="expected_ctc").one()
        assert row.value_encrypted and row.value_text is None and row.value_json is None  # private: encrypted at rest
        # Settings -> Verified answers kept in step.
        from backend.models import CandidateProfile
        assert db.query(CandidateProfile).filter_by(user_id=user.id).one().verified_facts["notice_period"] == "30 days"

    listed = {r["key"]: r for r in client.get(f"{API}/answers/memory", headers=h).json()}
    assert listed["expected_ctc"]["masked"] and listed["expected_ctc"]["answer"] is None
    assert client.get(f"{API}/answers/memory", headers=h, params={"reveal": True}).json()
    assert listed["notice_period"]["history"][0]["answer"] == "30 days"


def test_unreachable_employer_questions_fail_fast_and_are_not_refetched_on_every_open(client, resume_bytes, boards):
    h = onboard(client, "aw-fast@example.com", resume_bytes)
    item = with_board_job(client, h)
    app_id = _prepare(client, h, item["user_job_id"])
    boards.status[("greenhouse", "acmefintech")] = 503  # Greenhouse down: a transient failure
    question_calls = lambda: [u for u in boards.calls if "questions=true" in u]  # noqa: E731
    before = len(question_calls())

    pkg = client.get(f"{API}/applications/{app_id}/package", headers=h).json()["package"]
    assert pkg["questions_source"] == "not_inspected" and not pkg["readiness"]["form_inspected"]  # honest, not "ready"
    assert len(question_calls()) == before + 1  # one attempt: the person is waiting, no retries
    client.get(f"{API}/applications/{app_id}/package", headers=h)
    assert len(question_calls()) == before + 1  # a recent failure is not retried on every open
    boards.status.pop(("greenhouse", "acmefintech"))
    boards.payloads[("gh_questions", "acmefintech", "101")] = GH_QUESTIONS
    pkg = client.get(f"{API}/applications/{app_id}/package", headers=h, params={"refresh": True}).json()["package"]
    assert pkg["questions_source"] == "employer_api"  # an explicit refresh tries again


def test_stale_time_dependent_answers_are_offered_for_review_not_reused(client, resume_bytes):
    h = onboard(client, "aw2@example.com", resume_bytes)
    assert client.put(f"{API}/answers/memory", headers=h, json={"question": "Notice period", "answer": "15 days"}).status_code == 200
    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import AnswerMemory, User, utcnow
    from backend.services import answer_memory

    with session_factory()() as db:
        user = db.query(User).filter_by(email="aw2@example.com").one()
        row = db.query(AnswerMemory).filter_by(user_id=user.id, key="notice_period").one()
        row.last_confirmed_at = utcnow() - timedelta(days=45)
        db.commit()
        a = answer_memory.resolve(db, get_settings(), user, ["What is your notice period?"])[0]
        assert a["status"] == "SUGGESTED" and a["stale"] and "still right" in a["reason"]


def test_company_specific_answers_are_not_reused_for_another_employer(client, resume_bytes):
    h = onboard(client, "aw3@example.com", resume_bytes)
    a1 = import_job(client, h, company="Acme Health", url="https://www.linkedin.com/jobs/view/4000000011/")
    a2 = import_job(client, h, company="Other Corp", url="https://www.linkedin.com/jobs/view/4000000012/", title="AR Specialist")
    app1, _ = _prepare(client, h, a1["user_job_ids"][0]), _prepare(client, h, a2["user_job_ids"][0])
    q = "Have you previously worked for this company?"
    r = client.post(f"{API}/applications/{app1}/answers", headers=h, json={"items": [{"question": q, "answer": "Yes", "remember": True}]})
    assert r.status_code == 200 and r.json()["saved"] == [q]
    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import User
    from backend.services import answer_memory

    with session_factory()() as db:
        user = db.query(User).filter_by(email="aw3@example.com").one()
        assert answer_memory.resolve(db, get_settings(), user, [q], company="Acme Health")[0]["answer"] == "Yes"
        assert answer_memory.resolve(db, get_settings(), user, [q], company="Other Corp")[0]["status"] == "NEEDS_INPUT"


def test_resume_choice_is_kept_and_used_by_the_extension(client, resume_bytes, boards):
    h = onboard(client, "aw4@example.com", resume_bytes)
    r = client.post(f"{API}/profile/resume", headers=h, params={"make_default": False, "name": "FP&A version"},
                    files={"file": ("fpa.pdf", resume_bytes, "application/pdf")})
    assert r.status_code == 201
    other = [x for x in client.get(f"{API}/profile/resumes", headers=h).json() if not x["is_active"]][0]
    item = with_board_job(client, h)
    app_id = _prepare(client, h, item["user_job_id"])
    r = client.put(f"{API}/applications/{app_id}/resume", headers=h, json={"kind": "upload", "id": other["id"]})
    assert r.status_code == 200 and r.json()["package"]["resume"] == {**r.json()["package"]["resume"], "id": other["id"], "selected_by": "you"}
    tok = pair(client, h)
    ext = client.get(f"{API}/extension/applications/{app_id}/package", headers=xh(tok)).json()
    assert ext["resume"]["id"] == other["id"] and ext["resume"]["kind"] == "upload"


# ---- destination resolution and the native hand-off -----------------------------------------

def test_linkedin_job_gets_native_handoff_and_only_verified_employer_suggestions(client, resume_bytes):
    h = onboard(client, "aw5@example.com", resume_bytes)
    item = import_job(client, h, company="Acme Health", title="Accounts Receivable Analyst", location="Bengaluru")
    from backend.db import session_factory
    from backend.models import CataloguePosting

    with session_factory()() as db:
        for sk, title, loc in (("greenhouse:acmehealth:555", "Accounts Receivable Analyst", "Bengaluru, India"),
                               ("greenhouse:acmehealth:556", "Accounts Receivable Manager", "Bengaluru"),  # different job
                               ("lever:acmehealth:0d0e0f00-1111-2222-3333-444455556666", "Accounts Receivable Analyst", "London")):  # other city
            ats, board, jid = sk.split(":")
            url = f"https://job-boards.greenhouse.io/{board}/jobs/{jid}" if ats == "greenhouse" else f"https://jobs.lever.co/{board}/{jid}"
            db.add(CataloguePosting(source_key=sk, target_key=f"ats:{ats}:{board}", source=ats, title=title, company="Acme Health",
                                    location=loc, job_url=url, skills=[], payload={}, content_hash="x"))
        db.commit()
    app_id = _prepare(client, h, item["user_job_ids"][0])
    pkg = client.get(f"{API}/applications/{app_id}/package", headers=h).json()["package"]
    d = pkg["destination"]
    assert d["kind"] == "restricted" and d["platform_name"] == "LinkedIn" and pkg["action"] == "open_native"
    assert not pkg["capabilities"]["autofill"] and pkg["capabilities"]["native_handoff"]
    assert [s["url"] for s in d["suggestions"]] == ["https://job-boards.greenhouse.io/acmehealth/jobs/555"]  # never the manager role or London
    assert "linkedin.com" in d["url"]  # unchanged until the user confirms

    assert client.post(f"{API}/applications/{app_id}/destination", headers=h, json={"url": "https://job-boards.greenhouse.io/acmehealth/jobs/556"}).status_code == 409
    r = client.post(f"{API}/applications/{app_id}/destination", headers=h, json={"url": "https://job-boards.greenhouse.io/acmehealth/jobs/555"})
    d = r.json()["package"]["destination"]
    assert d["kind"] == "ats" and d["confirmed_by_user"] and not d["verified"] and r.json()["package"]["action"] == "review_autofill"
    d = client.delete(f"{API}/applications/{app_id}/destination", headers=h).json()["package"]["destination"]
    assert d["kind"] == "restricted"

    # Native hand-off: opened is not applied; the user's own report is recorded as such.
    r = client.post(f"{API}/applications/{app_id}/handoff", headers=h)
    a = r.json()["application"]
    assert r.status_code == 200 and a["status"] == "OPENED" and a["apply_state"] == "form_opened" and "linkedin.com" in r.json()["url"]
    a = client.post(f"{API}/applications/{app_id}/confirm", headers=h, json={"submitted": True, "reference_id": "LI-1"}).json()
    assert a["status"] == "SUBMITTED" and a["apply_state"] == "user_reported" and a["apply_state_label"] == "Applied (you told us)"
    assert client.post(f"{API}/applications/{app_id}/handoff", headers=h).status_code == 409  # never again
    consents = {c["kind"]: c["granted"] for c in client.get(f"{API}/consents", headers=h).json()}
    assert consents["apply_assist"]


# ---- evidence-graded outcomes and recovery --------------------------------------------------

def _state(client, tok, app_id, state, **body):
    return client.post(f"{API}/extension/applications/{app_id}/state", headers=xh(tok), json={"state": state, **body})


def test_user_report_is_upgraded_only_by_real_evidence_and_text_alone_is_not_proof(client, resume_bytes, boards):
    h = onboard(client, "aw6@example.com", resume_bytes)
    tok = pair(client, h)
    item = with_board_job(client, h)
    app_id = client.post(f"{API}/extension/applications/start", headers=xh(tok), json={"user_job_id": item["user_job_id"]}).json()["application_id"]
    assert _state(client, tok, app_id, "filling", session={"platform": "Workday"}).status_code == 200
    assert _state(client, tok, app_id, "submission_pending").status_code == 200
    # "Thank you" text on a site without an adapter: not proof.
    r = _state(client, tok, app_id, "submitted_confirmed", session={"signal": "Thank you for applying", "signal_kind": "text", "platform": "Workday"})
    assert r.status_code == 200 and r.json()["apply_state"] == "submission_uncertain" and r.json()["status"] == "CONFIRMATION_PENDING"
    # The user says they applied: recorded as their report, not as verified.
    a = client.post(f"{API}/applications/{app_id}/confirm", headers=h, json={"submitted": True}).json()
    assert a["status"] == "SUBMITTED" and a["apply_state"] == "user_reported"
    # The employer's confirmation page later seen by the adapter upgrades the evidence.
    r = _state(client, tok, app_id, "submitted_confirmed", session={"signal": "Application received (Greenhouse confirmation)", "signal_kind": "adapter"})
    assert r.status_code == 200 and r.json()["apply_state"] == "submitted_confirmed" and r.json()["confirmation"]["confidence"] == "high"


def test_abandoned_sessions_become_interrupted_and_resume_without_resubmitting(client, resume_bytes, boards):
    h = onboard(client, "aw7@example.com", resume_bytes)
    tok = pair(client, h)
    item = with_board_job(client, h)
    app_id = client.post(f"{API}/extension/applications/start", headers=xh(tok), json={"user_job_id": item["user_job_id"]}).json()["application_id"]
    assert _state(client, tok, app_id, "ready_for_review").status_code == 200
    # The extension reports a closed tab.
    r = _state(client, tok, app_id, "interrupted", session={"message": "Tab closed before submitting."})
    assert r.status_code == 200 and r.json()["apply_state"] == "interrupted" and r.json()["status"] == "OPENED"
    pkg = client.get(f"{API}/applications/{app_id}/package", headers=h).json()["package"]
    assert pkg["action"] == "resume" and pkg["action_label"] == "Resume application"
    # Resuming starts a fresh fill and review; authorising straight from "interrupted" is refused.
    assert _state(client, tok, app_id, "submission_authorized").status_code == 409
    assert _state(client, tok, app_id, "filling").status_code == 200

    # The background sweep: idle sessions -> interrupted; a submit click without outcome -> uncertain.
    from backend.db import session_factory
    from backend.models import Application, utcnow
    from backend.services import apply_state_service

    assert _state(client, tok, app_id, "reviewed").status_code == 200
    with session_factory()() as db:
        db.get(Application, app_id).apply_state_at = utcnow() - timedelta(hours=7)
        db.commit()
        assert apply_state_service.sweep_stale(db)["interrupted"] == 1
    for s in ("ready_for_review", "reviewed", "submission_authorized", "submission_pending"):
        assert _state(client, tok, app_id, s).status_code == 200, s
    with session_factory()() as db:
        db.get(Application, app_id).apply_state_at = utcnow() - timedelta(minutes=45)
        db.commit()
        assert apply_state_service.sweep_stale(db)["uncertain"] == 1
        app = db.get(Application, app_id)
        assert app.apply_state == "submission_uncertain" and app.status == "CONFIRMATION_PENDING"
    assert client.get(f"{API}/applications/{app_id}/package", headers=h).json()["package"]["action"] == "resolve_uncertain"


# ---- extension: answers in context, learning, proof of server identity ------------------------

def test_extension_answers_use_memory_and_learn_only_what_the_user_ticked(client, resume_bytes, boards):
    h = onboard(client, "aw8@example.com", resume_bytes)
    tok = pair(client, h)
    item = with_board_job(client, h)
    app_id = client.post(f"{API}/extension/applications/start", headers=xh(tok), json={"user_job_id": item["user_job_id"]}).json()["application_id"]
    qs = ["Years of experience with Excel", "Are you a protected veteran?", "What is your notice period?"]
    out = {a["question"]: a for a in client.post(f"{API}/extension/answers", headers=xh(tok), json={"questions": qs, "application_id": app_id}).json()}
    assert out["Are you a protected veteran?"]["sensitivity"] == "never" and out["Are you a protected veteran?"]["answer"] is None
    assert out["Years of experience with Excel"]["status"] == "NEEDS_INPUT" and out["Years of experience with Excel"]["key"] == "experience_years.excel"
    r = client.post(f"{API}/extension/answers/learn", headers=xh(tok), json={"application_id": app_id, "items": [
        {"question": "Years of experience with Excel", "answer": "5"}, {"question": "Are you a protected veteran?", "answer": "No"},
        {"question": "What is your notice period?", "answer": "sometime"}]})
    body = r.json()
    assert body["saved"] == ["Years of experience with Excel"] and len(body["errors"]) == 2
    out = client.post(f"{API}/extension/answers", headers=xh(tok), json={"questions": ["Excel experience (years)"]}).json()[0]
    assert out["status"] == "VERIFIED" and out["answer"] == "5"
    # The questions the extension saw are on the application for the workspace (labels only, never sensitive ones).
    pkg = client.get(f"{API}/applications/{app_id}/package", headers=h).json()["package"]
    from backend.db import session_factory
    from backend.models import Application
    with session_factory()() as db:
        seen = db.get(Application, app_id).package["form_questions"]["items"]
    assert "Are you a protected veteran?" not in seen and "Years of experience with Excel" in seen
    assert pkg["answers"]
    # A question read off the form (the form doesn't say whether it's required) is shown as unanswered, not blocking.
    client.post(f"{API}/extension/answers", headers=xh(tok), json={"questions": ["Preferred pronunciation of your name"], "application_id": app_id})
    pkg = client.get(f"{API}/applications/{app_id}/package", headers=h).json()["package"]
    row = next(a for a in pkg["answers"] if a["question"] == "Preferred pronunciation of your name")
    assert row["status"] == "NEEDS_INPUT" and not row["required"]
    needs = sum(1 for a in pkg["answers"] if a["status"] == "NEEDS_INPUT" and a["sensitivity"] != "never")
    assert pkg["readiness"]["other_unanswered"] >= 1 and pkg["readiness"]["needs_input"] + pkg["readiness"]["other_unanswered"] == needs


def test_prove_answers_only_with_the_issuing_servers_secret(client, resume_bytes):
    h = onboard(client, "aw9@example.com", resume_bytes)
    tok = pair(client, h)
    nonce = "ab" * 16
    r = client.post(f"{API}/extension/prove", json={"token_id": tok["token_id"], "nonce": nonce})
    key = bytes.fromhex(hashlib.sha256(tok["token"].encode()).hexdigest())
    assert r.status_code == 200 and r.json()["proof"] == hmac.new(key, f"jobpilot-prove:{nonce}".encode(), hashlib.sha256).hexdigest()
    assert client.post(f"{API}/extension/prove", json={"token_id": 99999, "nonce": nonce}).status_code == 404
    assert client.post(f"{API}/extension/prove", json={"token_id": tok["token_id"], "nonce": "short"}).status_code == 422
    assert client.post(f"{API}/extension/disconnect", headers=xh(tok)).status_code == 204
    assert client.post(f"{API}/extension/prove", json={"token_id": tok["token_id"], "nonce": nonce}).status_code == 404


def test_settings_facts_feed_answer_memory(client, resume_bytes):
    h = onboard(client, "aw10@example.com", resume_bytes)
    r = client.put(f"{API}/profile/verified-facts", headers=h, json={"notice_period": "2 months", "willing_to_relocate": True,
                                                                       "expected_ctc": "negotiable"})
    assert r.status_code == 200
    mem = {m["key"]: m for m in client.get(f"{API}/answers/memory", headers=h).json()}
    assert mem["notice_period"]["answer"] == "60 days" and mem["notice_period"]["source"] == "settings"
    assert mem["willing_to_relocate"]["answer"] == "Yes"
    assert "expected_ctc" not in mem  # "negotiable" isn't an amount: Settings keeps it as typed, nothing invented
