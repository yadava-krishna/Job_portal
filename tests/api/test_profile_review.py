"""Resume extraction is reviewed, never auto-confirmed: field states (extracted / confirmed / missing / conflict / stale),
a newer resume only proposes changes, and existing confirmed profiles are not sent back through review."""

from __future__ import annotations

from datetime import timedelta

from api_helpers import auth, onboard, register
from support import SYNTHETIC_RESUME_LINES, make_pdf

API = "/api/v1"


def _states(review: dict) -> dict[str, str]:
    return {f["key"]: f["state"] for f in review["fields"]}


def test_parsed_values_are_extracted_not_confirmed_until_the_user_saves(client, resume_bytes):
    h = auth(register(client, "pr1@example.com"))
    r = client.post(f"{API}/profile/resume", headers=h, files={"file": ("cv.pdf", resume_bytes, "application/pdf")})
    body = r.json()
    assert body["confirmed"] is None and body["review"]["status"] == "unconfirmed"
    st = _states(body["review"])
    assert st["full_name"] == "extracted" and st["email"] == "extracted" and st["skills"] == "extracted" and st["experience"] == "extracted"
    assert st["linkedin_url"] == "empty"  # optional and not on the resume: not nagged about
    assert body["review"]["parsed_at"] and body["review"]["pending"] >= 4
    # Confirming makes them confirmed (and only then).
    assert client.put(f"{API}/profile", headers=h, json=body["parsed"]).status_code == 200
    review = client.get(f"{API}/profile", headers=h).json()["review"]
    assert review["status"] == "confirmed" and _states(review)["full_name"] == "confirmed"


def test_a_new_resume_proposes_changes_and_never_overwrites_the_confirmed_profile(client, resume_bytes, tmp_path):
    h = onboard(client, "pr2@example.com", resume_bytes)
    before = client.get(f"{API}/profile", headers=h).json()
    assert before["review"]["status"] == "confirmed"
    lines = [ln.replace("Bengaluru, Karnataka", "Hyderabad, Telangana") for ln in SYNTHETIC_RESUME_LINES]
    lines = lines[:-3] + ["Lead Analyst | Gamma Corp", "Apr 2024 - Present", "• Led a team of four."] + lines[-3:]
    new = make_pdf(tmp_path / "new.pdf", lines).read_bytes()
    after = client.post(f"{API}/profile/resume", headers=h, files={"file": ("cv2.pdf", new, "application/pdf")}).json()
    assert after["confirmed"] == before["confirmed"]  # nothing confirmed was changed by parsing
    review = after["review"]
    assert review["status"] == "needs_review"
    by = {f["key"]: f for f in review["fields"]}
    assert by["location"]["state"] == "conflict" and "Hyderabad" in by["location"]["extracted"]
    assert "Bengaluru" in by["location"]["confirmed"]
    assert by["experience"]["state"] == "conflict" and [x["company"] for x in by["experience"]["extracted"]] == ["Gamma Corp"]
    assert by["full_name"]["state"] == "confirmed"  # unchanged fields stay confirmed
    # The user keeps their own value: saving the confirmed profile again clears the review.
    assert client.put(f"{API}/profile", headers=h, json=after["confirmed"]).status_code == 200
    assert client.get(f"{API}/profile", headers=h).json()["review"]["status"] == "confirmed"


def test_existing_profiles_without_a_parse_time_are_not_flagged_and_old_confirmations_go_stale(client, resume_bytes):
    h = onboard(client, "pr3@example.com", resume_bytes)
    from backend.db import session_factory
    from backend.models import CandidateProfile, User, utcnow

    with session_factory()() as db:
        uid = db.query(User).filter_by(email="pr3@example.com").one().id
        prof = db.query(CandidateProfile).filter_by(user_id=uid).one()
        parsed = dict(prof.parsed_profile)
        parsed.pop("parsed_at", None)  # parsed before this release
        prof.parsed_profile = parsed
        db.commit()
    assert client.get(f"{API}/profile", headers=h).json()["review"]["status"] == "confirmed"
    with session_factory()() as db:
        prof = db.query(CandidateProfile).filter_by(user_id=uid).one()
        prof.confirmed_at = utcnow() - timedelta(days=400)
        db.commit()
    review = client.get(f"{API}/profile", headers=h).json()["review"]
    assert review["status"] == "needs_review" and _states(review)["location"] == "stale" and _states(review)["experience"] == "stale"


def test_review_is_private_to_each_user(client, resume_bytes):
    onboard(client, "pr4@example.com", resume_bytes)
    hb = auth(register(client, "pr4b@example.com"))
    assert client.get(f"{API}/profile", headers=hb).json()["review"] is None


def test_preference_changes_ask_for_new_scores_and_report_when_they_are_done(client, resume_bytes):
    h = onboard(client, "pr5@example.com", resume_bytes)
    st = client.get(f"{API}/preferences/rescore", headers=h).json()
    # TestClient runs background tasks before returning: the refresh asked for during onboarding is already done.
    assert st["requested_at"] and st["rescored_at"] and st["pending"] is False
    prefs = client.get(f"{API}/preferences", headers=h).json()
    assert client.put(f"{API}/preferences", headers=h, json={**prefs, "min_match_score": 55}).status_code == 200
    after = client.get(f"{API}/preferences/rescore", headers=h).json()
    assert after["requested_at"] > st["requested_at"] and after["pending"] is False
    r = client.post(f"{API}/preferences/rescore", headers=h)
    assert r.status_code == 202
    # Not signed in: refused.
    assert client.get(f"{API}/preferences/rescore").status_code == 401


def test_a_failed_refresh_stays_pending(client, resume_bytes, monkeypatch):
    h = onboard(client, "pr6@example.com", resume_bytes)
    from backend.services import matching_service

    def boom(*a, **k):
        raise RuntimeError("matcher down")
    monkeypatch.setattr(matching_service, "rescore_user", boom)
    prefs = client.get(f"{API}/preferences", headers=h).json()
    client.put(f"{API}/preferences", headers=h, json={**prefs, "min_match_score": 50})
    assert client.get(f"{API}/preferences/rescore", headers=h).json()["pending"] is True
