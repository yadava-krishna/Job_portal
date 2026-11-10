"""End-to-end API coverage for the career graph features: snapshot/goals/consent, skills & evidence, gaps, learning,
Resume Studio (versions, immutability, cached exports, feedback), interview prep, rejections & funnel, AI mentor &
reflection, human mentoring with isolation, international routes and source-change detection, analytics events."""

from __future__ import annotations

import fitz  # PyMuPDF
from api_helpers import auth, import_job, onboard, register

API = "/api/v1"


def _submit(client, h, uj: int) -> int:
    app_id = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": uj}).json()["id"]
    assert client.post(f"{API}/applications/{app_id}/confirm", headers=h, json={"submitted": True}).status_code == 200
    return app_id


def test_snapshot_goals_consent_and_next_step(client, resume_bytes):
    h = onboard(client, "snap@example.com", resume_bytes)
    import_job(client, h)
    snap = client.get(f"{API}/career/snapshot", headers=h).json()
    assert 0 <= snap["profile_completeness"]["percent"] <= 100 and snap["top_matches"]
    assert snap["next_step"]["kind"] in ("profile", "build_resume", "apply", "learn", "interview_prep", "international", "discover")
    g = client.put(f"{API}/career-goals", headers=h, json={"search_mode": "both", "target_countries": ["gb", "DE"],
                                                         "work_authorization": ["IN"], "needs_sponsorship": True, "seniority": "mid"}).json()
    assert g["target_countries"] == ["GB", "DE"] and g["search_mode"] == "both"
    assert client.put(f"{API}/career-goals", headers=h, json={"target_countries": ["Germany"]}).status_code == 422
    assert client.get(f"{API}/career/snapshot", headers=h).json()["show"]["international"] is True
    kinds = {c["kind"]: c["granted"] for c in client.get(f"{API}/consents", headers=h).json()}
    assert kinds["learning_tracking"] is False and kinds["mentor_sharing"] is False
    client.put(f"{API}/consents/learning_tracking", headers=h, json={"granted": True})
    assert {c["kind"]: c["granted"] for c in client.get(f"{API}/consents", headers=h).json()}["learning_tracking"] is True
    assert client.post(f"{API}/feedback", headers=h, json={"topic": "job_relevance", "rating": 4}).status_code == 201
    assert client.post(f"{API}/feedback", headers=h, json={"topic": "nope"}).status_code == 422


def test_skills_evidence_states_gaps_and_learning(client, resume_bytes):
    h = onboard(client, "skills@example.com", resume_bytes)
    import_job(client, h)
    skills = client.get(f"{API}/skills", headers=h).json()
    assert [s["key"] for s in skills["states"]] == ["aware", "learning", "practising", "project_evidence", "professional_experience", "interview_ready"]
    s = client.post(f"{API}/skills", headers=h, json={"name": "Tableau"}).json()
    assert s["state"] == "aware"
    # A course alone can't make a skill "project evidence" or "interview ready".
    assert client.put(f"{API}/skills/{s['id']}/state", headers=h, json={"state": "project_evidence"}).status_code == 409
    assert client.put(f"{API}/skills/{s['id']}/state", headers=h, json={"state": "interview_ready"}).status_code == 409
    s = client.post(f"{API}/skills/{s['id']}/evidence", headers=h, json={"evidence_type": "course", "title": "Tableau basics"}).json()
    assert s["state"] == "learning"
    s = client.post(f"{API}/skills/{s['id']}/evidence", headers=h,
                    json={"evidence_type": "project", "title": "AR dashboard", "url": "https://github.com/example/ar-dashboard"}).json()
    assert s["state"] == "project_evidence"  # never professional_experience from a project
    assert client.put(f"{API}/skills/{s['id']}/state", headers=h, json={"state": "professional_experience"}).status_code == 409
    assert client.put(f"{API}/skills/{s['id']}/state", headers=h, json={"state": "interview_ready"}).json()["state"] == "interview_ready"

    gaps = client.get(f"{API}/gaps", headers=h, params={"refresh": True}).json()
    assert gaps["gaps"], gaps
    best = gaps["best"]
    assert best and best["explanation"] and best["next_action"]
    detail = client.get(f"{API}/gaps/{best['id']}", headers=h).json()
    res = detail["learning"]["resources"]
    if res:  # catalogued skill: resources carry provider, link status and why they're relevant
        assert {"provider", "url", "link_status", "relevance", "level"} <= set(res[0])
    # Learning sessions need explicit consent.
    assert client.post(f"{API}/learning-sessions", headers=h, json={"skill": "Power BI"}).status_code == 403
    client.put(f"{API}/consents/learning_tracking", headers=h, json={"granted": True})
    sess = client.post(f"{API}/learning-sessions", headers=h, json={"skill": "Power BI"}).json()
    assert sess["status"] == "active"
    client.post(f"{API}/learning-sessions/{sess['id']}/heartbeat", headers=h, json={"active": True})
    done = client.post(f"{API}/learning-sessions/{sess['id']}/complete", headers=h,
                       json={"notes": "Built a first report", "helpful": True, "knowledge_check": {"q1": "measures vs columns"}}).json()
    assert done["skill_state"] in ("learning", "practising")
    assert client.post(f"{API}/learning-sessions/{sess['id']}/complete", headers=h, json={}).status_code == 409
    other = auth(register(client, "skills-other@example.com"))
    assert client.post(f"{API}/learning-sessions/{sess['id']}/heartbeat", headers=other, json={"active": True}).status_code == 404
    assert client.put(f"{API}/skills/{s['id']}/state", headers=other, json={"state": "aware"}).status_code == 404


def test_resume_studio_versions_exports_and_immutability(client, resume_bytes):
    h = onboard(client, "studio@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    tpls = client.get(f"{API}/studio/templates", headers=h).json()
    assert [t["key"] for t in tpls] == ["ats_simple", "modern_professional", "technical", "finance", "graduate", "international"]
    v = client.post(f"{API}/studio/versions", headers=h, json={"name": "Base", "template_key": "ats_simple"}).json()
    types = [s["type"] for s in v["sections"]]
    assert types[0] == "header" and "experience" in types and "skills" in types
    exp = next(s for s in v["sections"] if s["type"] == "experience")
    assert exp["blocks"] and all(b["source"] == "profile" for b in exp["blocks"][0]["bullets"])
    # Autosave with optimistic concurrency.
    v["sections"][0]["blocks"][0]["content"]["headline"] = "AR & Collections Analyst <b>"
    saved = client.put(f"{API}/studio/versions/{v['id']}", headers=h, json={"revision": v["revision"], "sections": v["sections"]}).json()
    assert saved["revision"] == v["revision"] + 1
    assert client.put(f"{API}/studio/versions/{v['id']}", headers=h, json={"revision": v["revision"], "name": "stale"}).status_code == 409
    # Every template renders a real, text-searchable PDF (escaped markup included).
    for t in tpls:
        r = client.put(f"{API}/studio/versions/{v['id']}", headers=h, json={"template_key": t["key"]})
        assert r.status_code == 200, r.text
        pdf = client.get(f"{API}/studio/versions/{v['id']}/preview.pdf", headers=h)
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
        text = "".join(p.get_text() for p in fitz.open(stream=pdf.content, filetype="pdf"))
        assert "AR & Collections Analyst <b>" in text, t["key"]
    # Exports are cached per content checksum.
    e1 = client.post(f"{API}/studio/versions/{v['id']}/export", headers=h, json={"format": "pdf"}).json()
    e2 = client.post(f"{API}/studio/versions/{v['id']}/export", headers=h, json={"format": "pdf"}).json()
    assert e1["id"] == e2["id"] and e1["file_sha256"] == e2["file_sha256"]
    docx = client.post(f"{API}/studio/versions/{v['id']}/export", headers=h, json={"format": "docx"}).json()
    dl = client.get(f"{API}{docx['download_url']}", headers=h)
    assert dl.status_code == 200 and dl.content[:2] == b"PK"
    fb = client.get(f"{API}/studio/versions/{v['id']}/feedback", headers=h, params={"user_job_id": uj}).json()
    assert "issues" in fb and "does not guarantee" in fb["note"]
    assert isinstance(client.get(f"{API}/studio/versions/{v['id']}/suggestions", headers=h, params={"user_job_id": uj}).json(), list)
    # Using it for an application records the exact file; submitting locks the version.
    app_id = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": uj}).json()["id"]
    att = client.put(f"{API}/applications/{app_id}/resume-version", headers=h, json={"resume_version_id": v["id"]}).json()
    assert att["resume_version_id"] == v["id"] and len(att["resume_checksum"]) == 64
    assert client.post(f"{API}/applications/{app_id}/confirm", headers=h, json={"submitted": True}).status_code == 200
    locked = client.get(f"{API}/studio/versions/{v['id']}", headers=h).json()
    assert locked["status"] == "locked"
    assert client.put(f"{API}/studio/versions/{v['id']}", headers=h, json={"name": "edit"}).status_code == 409
    assert client.delete(f"{API}/studio/versions/{v['id']}", headers=h).status_code == 409
    copy = client.post(f"{API}/studio/versions/{v['id']}/clone", headers=h, json={"name": "Base v2"}).json()
    assert copy["status"] == "draft" and copy["parent_id"] == v["id"]
    # Other users can't see or download any of it.
    other = auth(register(client, "studio-other@example.com"))
    assert client.get(f"{API}/studio/versions/{v['id']}", headers=other).status_code == 404
    assert client.get(f"{API}{docx['download_url']}", headers=other).status_code == 404


def test_interview_prep_rejection_funnel_and_stage_rules(client, resume_bytes):
    h = onboard(client, "prep@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    prep = client.get(f"{API}/interview-prep/{uj}", headers=h).json()
    assert len(prep["questions"]) >= 5 and {l["source"] for l in prep["reference_links"]} == {"glassdoor", "ambitionbox", "reddit", "indeed"}
    p = client.post(f"{API}/interview-practice", headers=h, json={"user_job_id": uj}).json()
    q = p["questions"][0]
    p2 = client.post(f"{API}/interview-practice/{p['id']}/answers", headers=h, json={"question_id": q["id"], "answer": "We did reconciliation."}).json()
    fb = p2["feedback"][0]
    assert fb["score"] < 5 and fb["notes"]
    assert client.post(f"{API}/interview-insights", headers=h, json={"company": "Acme Health", "source": "glassdoor",
                                                                      "question": "Tell me about DSO"}).status_code == 201
    app_id = _submit(client, h, uj)
    r = client.post(f"{API}/applications/{app_id}/rejection", headers=h, json={"reason": "skills_gap", "known": False}).json()
    assert r["stage"] == "rejected" and r["rejection_reason_known"] is False
    assert client.post(f"{API}/applications/{app_id}/stage", headers=h, json={"stage": "interview"}).status_code == 409
    f = client.get(f"{API}/analytics/funnel", headers=h).json()
    assert f["counts"]["applied"] == 1 and f["counts"]["rejected"] == 1 and f["rejection_reasons"][0]["reason"] == "skills_gap"


def test_ai_mentor_reflection_and_human_mentor_isolation(client, resume_bytes):
    from backend.db import session_factory
    from backend.models import AuditLog, User

    h = onboard(client, "mentee@example.com", resume_bytes)
    plan = client.get(f"{API}/mentor/plan", headers=h).json()
    assert plan["diagnoses"] and plan["diagnoses"][0]["confidence"] in ("low", "medium", "high")
    r = client.post(f"{API}/mentor/reflection", headers=h, json={"outcome": "Sent 3 applications", "obstacle": "No replies",
                                                                  "next_action": "Fix resume warnings"}).json()
    assert r["next_action"] == "Fix resume warnings"
    acts = client.get(f"{API}/mentor/actions", headers=h).json()
    assert any(a["source"] == "reflection" for a in acts)
    a = next(a for a in acts if a["source"] == "reflection")
    assert client.patch(f"{API}/mentor/actions/{a['id']}", headers=h, json={"done": True}).json()["completed_at"]

    mh = auth(register(client, "mentor1@example.com"))
    m2 = auth(register(client, "mentor2@example.com"))
    with session_factory()() as db:
        for e in ("mentor1@example.com", "mentor2@example.com"):
            db.query(User).filter(User.email == e).one().role = "mentor"
        db.commit()
    assert client.get(f"{API}/mentor-workspace/candidates", headers=h).status_code == 403  # candidates aren't mentors
    # Sharing needs consent first.
    assert client.post(f"{API}/mentoring/mentors", headers=h, json={"mentor_email": "mentor1@example.com"}).status_code == 403
    client.put(f"{API}/consents/mentor_sharing", headers=h, json={"granted": True})
    asg = client.post(f"{API}/mentoring/mentors", headers=h, json={"mentor_email": "mentor1@example.com", "scopes": ["gaps", "actions"]}).json()
    cands = client.get(f"{API}/mentor-workspace/candidates", headers=mh).json()
    assert [c["assignment_id"] for c in cands] == [asg["id"]]
    summary = client.get(f"{API}/mentor-workspace/candidates/{asg['id']}", headers=mh).json()
    assert "gaps" in summary and "funnel" not in summary and "applications" not in summary  # only granted scopes
    assert client.get(f"{API}/mentor-workspace/candidates/{asg['id']}", headers=m2).status_code == 404  # another mentor
    client.post(f"{API}/mentor-workspace/candidates/{asg['id']}/notes", headers=mh, json={"body": "private thought", "visibility": "private"})
    client.post(f"{API}/mentor-workspace/candidates/{asg['id']}/notes", headers=mh, json={"body": "Shared plan"})
    seen = client.get(f"{API}/mentoring/mentors/{asg['id']}/notes", headers=h).json()
    assert [n["body"] for n in seen] == ["Shared plan"]
    s = client.post(f"{API}/mentor-workspace/candidates/{asg['id']}/sessions", headers=mh,
                    json={"meeting_url": "https://meet.example.com/abc", "agenda": "Review gaps"})
    assert s.status_code == 201
    assert client.post(f"{API}/mentor-workspace/candidates/{asg['id']}/sessions", headers=mh, json={"meeting_url": "javascript:alert(1)"}).status_code == 422
    assert client.post(f"{API}/mentor-workspace/candidates/{asg['id']}/actions", headers=mh, json={"title": "Do a mock interview"}).status_code == 201
    assert any(a["source"] == "human_mentor" for a in client.get(f"{API}/mentor/actions", headers=h).json())
    with session_factory()() as db:
        assert db.query(AuditLog).filter(AuditLog.action == "MENTOR_VIEWED_CANDIDATE").count() == 1
    assert client.delete(f"{API}/mentoring/mentors/{asg['id']}", headers=h).status_code == 204
    assert client.get(f"{API}/mentor-workspace/candidates/{asg['id']}", headers=mh).status_code == 404  # access ends at once


def test_international_routes_fit_watch_and_source_changes(client, resume_bytes):
    from backend.db import session_factory
    from backend.models import Notification
    from backend.services import international_service

    h = onboard(client, "intl@example.com", resume_bytes)
    countries = client.get(f"{API}/countries", headers=h).json()
    assert len(countries) >= 10 and all(c["official_source_url"].startswith("https://") for c in countries)
    routes = client.get(f"{API}/visa-routes", headers=h, params={"country": "GB"}).json()
    assert routes and routes[0]["confidence"] == "unverified" and "not legal" in routes[0]["notice"]
    fit = client.get(f"{API}/country-fit", headers=h, params={"country": "DE"}).json()
    assert fit["routes"] and {"strengths", "gaps", "unknown"} <= set(fit["routes"][0]["fit"])
    client.put(f"{API}/visa-routes/{routes[0]['id']}/watch", headers=h, json={"watching": True})
    with session_factory()() as db:
        first = international_service.check_sources(db, fetch=lambda url: "<p>version one</p>")
        assert first["checked"] >= 9 and first["changed"] == 0
        second = international_service.check_sources(db, fetch=lambda url: "<p>version two</p>")
        assert second["changed"] >= 9
        assert db.query(Notification).filter(Notification.kind == "source_change").count() == 1  # only the watched route


def test_prd_events_are_recorded_without_personal_data(client, resume_bytes):
    from backend.db import session_factory
    from backend.models import AnalyticsEvent

    h = onboard(client, "events@example.com", resume_bytes)
    assert client.get(f"{API}/onboarding", headers=h).json()["completed"] is True  # what the UI calls after the last step
    uj = import_job(client, h)["user_job_ids"][0]
    client.get(f"{API}/jobs/{uj}", headers=h)
    client.post(f"{API}/jobs/{uj}/save", headers=h)
    v = client.post(f"{API}/studio/versions", headers=h, json={"name": "E"}).json()
    client.post(f"{API}/studio/versions/{v['id']}/export", headers=h, json={"format": "pdf"})
    _submit(client, h, uj)
    with session_factory()() as db:
        names = {e.name for e in db.query(AnalyticsEvent).all()}
        props = " ".join(str(e.properties) for e in db.query(AnalyticsEvent).all())
    for n in ("onboarding_completed", "job_viewed", "job_saved", "resume_created", "resume_exported", "application_prepared", "application_submitted"):
        assert n in names, n
    assert "events@example.com" not in props


def test_student_can_onboard_without_a_resume(client):
    h = auth(register(client, "student@example.com"))
    assert client.put(f"{API}/profile", headers=h, json={"full_name": "S"}).status_code == 422  # needs something real
    prof = {"full_name": "Student Example", "email": "student@example.com", "skills": ["Microsoft Excel", "SQL"],
            "education": [{"degree": "B.Com", "institution": "Example College", "year": "2026"}],
            "projects": [{"name": "Sales dashboard", "bullets": ["Built a sales dashboard in Excel for a college fest"]}]}
    assert client.put(f"{API}/profile", headers=h, json=prof).status_code == 200
    assert client.put(f"{API}/preferences", headers=h, json={"job_titles": ["Accounts Trainee"], "locations": ["Pune"],
                                                              "work_modes": ["On-site"], "employment_types": ["Full-time"]}).status_code == 200
    plats = {"platforms": [{"platform": "LinkedIn", "enabled": True, "discovery_sources": ["user_job_url"]}]}
    assert client.put(f"{API}/platforms/preferences", headers=h, json=plats).status_code == 200
    st = client.get(f"{API}/onboarding", headers=h).json()
    assert st["completed"] is True and st["resume_uploaded"] is True
    v = client.post(f"{API}/studio/versions", headers=h, json={"name": "First resume", "template_key": "graduate"}).json()
    assert any(s["type"] == "projects" and s["visible"] for s in v["sections"])  # a student's first resume comes from the manual profile
    skills = {s["canonical"]: s["state"] for s in client.get(f"{API}/skills", headers=h).json()["skills"]}
    assert "professional_experience" not in skills.values()  # no employment, so nothing is shown as work experience


def test_export_includes_career_data_without_storage_keys(client, resume_bytes):
    h = onboard(client, "exp2@example.com", resume_bytes)
    v = client.post(f"{API}/studio/versions", headers=h, json={"name": "Exported"}).json()
    client.post(f"{API}/studio/versions/{v['id']}/export", headers=h, json={"format": "pdf"})
    client.post(f"{API}/skills", headers=h, json={"name": "Tableau"})
    data = client.get(f"{API}/account/export", headers=h).json()
    assert data["resume_versions"][0]["name"] == "Exported" and data["resume_versions"][0]["sections"]
    assert any(s["canonical"] == "Tableau" for s in data["skills"]) and data["resume_exports"]
    assert "file_key" not in str(data["resume_exports"]) and "users/" not in str(data["resume_exports"])


def test_job_filters_for_country_sponsorship_and_eligibility(client, resume_bytes):
    h = onboard(client, "filters@example.com", resume_bytes)
    import_job(client, h)  # Bengaluru
    import_job(client, h, url="https://www.linkedin.com/jobs/view/4000000077/", title="AR Specialist", company="Far Away Ltd",
               location="London, United Kingdom", description="We offer visa sponsorship is available for this role. " * 3)
    titles = lambda **p: sorted(i["job"]["title"] for i in client.get(f"{API}/jobs", headers=h, params={"view": "all", **p}).json()["items"])  # noqa: E731
    assert titles(country="IN") == ["Accounts Receivable Analyst"]
    assert titles(country="GB") == ["AR Specialist"]
    assert titles(sponsorship=["verified"]) == ["AR Specialist"]
    assert set(titles(eligibility=["pass", "fail", "unknown"])) == {"AR Specialist", "Accounts Receivable Analyst"}
    import_job(client, h, url="https://www.linkedin.com/jobs/view/4000000078/", title="Senior Accounts Executive", company="Ledger Co",
               location="Pune, India", description="Own month-end close and receivables reporting for the region. " * 3)
    assert titles(seniority="senior") == ["Senior Accounts Executive"]
    assert titles(seniority="entry") == []  # no title cue and no stated experience: unknown, not guessed


def test_infer_seniority_never_guesses():
    from backend.services.career_service import infer_seniority
    assert infer_seniority("Finance Intern", None) == "intern"
    assert infer_seniority("Head of Finance", None) == "director"
    assert infer_seniority("Accounts Manager", None) == "manager"
    assert infer_seniority("Principal Engineer", None) == "lead"
    assert infer_seniority("Sr. Analyst", None) == "senior"
    assert infer_seniority("Software Engineer II", None) == "mid"
    assert infer_seniority("Analyst", 6) == "senior"
    assert infer_seniority("Analyst", None) is None
    assert infer_seniority("Analyst", 0) is None


def test_normalisation_job_backfills_signals(client):
    from backend.db import session_factory
    from backend.models import Job
    from backend.services import jobs_registry
    with session_factory()() as db:
        db.add(Job(job_key="bf-1", platform="manual", source="manual", title="Senior Payroll Specialist", company="Old Co", location="Dubai",
                   description="Visa sponsorship is available for the right candidate.", seniority=None, sponsorship_signal="unknown"))
        db.commit()
        out = jobs_registry._normalise_and_dedupe(db, None)
        job = db.query(Job).filter_by(job_key="bf-1").one()
        assert (job.seniority, job.sponsorship_signal) == ("senior", "verified")
        assert out["seniority"] >= 1 and out["sponsorship"] >= 1


def test_closing_a_gap_rescores_with_before_after_reasoning(client, resume_bytes):
    h = onboard(client, "beforeafter@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    job = client.get(f"{API}/jobs/{uj}", headers=h).json()
    missing = job["missing_skills"]
    assert missing, job
    skill = client.post(f"{API}/skills", headers=h, json={"name": missing[0]}).json()
    before = job["match_score"]
    # A course doesn't reach project evidence, so the score must not move.
    r = client.post(f"{API}/skills/{skill['id']}/evidence", headers=h, json={"evidence_type": "course", "title": "Intro"}).json()
    assert r["score_changes"] == []
    r = client.post(f"{API}/skills/{skill['id']}/evidence", headers=h,
                    json={"evidence_type": "project", "title": "Portfolio piece", "url": "https://github.com/example/p"}).json()
    assert r["state"] == "project_evidence"
    ch = [c for c in r["score_changes"] if c["user_job_id"] == uj]
    assert ch and ch[0]["old_score"] == before and ch[0]["new_score"] > before, r["score_changes"]
    hist = client.get(f"{API}/matches/history", headers=h).json()
    assert hist[0]["user_job_id"] == uj and "Project evidence" in hist[0]["reason"]
    assert client.get(f"{API}/matches/history", headers=auth(register(client, "ba-other@example.com"))).json() == []
