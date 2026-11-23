"""Portal Connections: honest capabilities (no account linked without a configured sign-in, no automation on the portals), and LinkedIn/Naukri
checklists built only from the confirmed profile, per user."""

from __future__ import annotations

from api_helpers import auth, onboard, register

API = "/api/v1"


def test_capabilities_are_honest(client, resume_bytes):
    h = auth(register(client, "po1@example.com"))
    rows = {p["portal"]: p for p in client.get(f"{API}/portals", headers=h).json()}
    assert set(rows) == {"linkedin", "naukri", "indeed"}
    for p in rows.values():
        c = p["capabilities"]
        # No sign-in is configured on this server, so nothing is linked and no Connect action is offered.
        assert c["identity_auth"]["available"] is False and c["account_linked"]["available"] is False
        assert c["job_retrieval"]["available"] is False and c["application_submission"]["available"] is False
        assert c["assisted_submission"]["available"] is False and c["native_handoff"]["available"]
        assert c["source"]["available"] and c["application_handoff"]["available"]
        assert "connect" not in p["actions"]
    assert rows["indeed"]["capabilities"]["profile_guidance"]["available"] is False and "optimize" not in rows["indeed"]["actions"]
    assert client.get(f"{API}/portals").status_code == 401


def test_checklists_use_only_confirmed_facts_and_remember_what_was_ticked(client, resume_bytes):
    h = auth(register(client, "po2@example.com"))
    assert client.get(f"{API}/portals/linkedin/review", headers=h).status_code == 409  # no confirmed profile yet
    h = onboard(client, "po2b@example.com", resume_bytes)
    li = client.get(f"{API}/portals/linkedin/review", headers=h).json()
    items = {i["key"]: i for i in li["items"]}
    assert {"headline", "about", "experience", "achievements", "skills", "location", "target_titles"} <= set(items)
    profile = client.get(f"{API}/profile", headers=h).json()["confirmed"]
    known = " ".join([profile["headline"] or "", profile["summary"] or "", *profile["skills"], *[b for r in profile["experience"] for b in r["bullets"]],
                      *[f"{r['title']} {r['company']}" for r in profile["experience"]], "Accounts Receivable Analyst", "Seeking roles at"]).lower()
    # Every suggested achievement is one of the user's own confirmed bullets.
    for line in (items["achievements"]["suggestion"] or "").splitlines():
        assert line.lstrip("• ").lower() in known
    assert len(items["headline"]["suggestion"] or "") <= 220
    nk = client.get(f"{API}/portals/naukri/review", headers=h).json()
    nitems = {i["key"]: i for i in nk["items"]}
    assert {"resume_headline", "key_skills", "employment", "desired_titles", "preferred_location", "expected_salary", "notice_period",
            "resume_fresh"} <= set(nitems)
    assert len(nitems["resume_headline"]["suggestion"] or "") <= 250
    assert nitems["expected_salary"]["existing"] is None  # private: never shown back
    assert client.get(f"{API}/portals/indeed/review", headers=h).status_code == 404
    before = nk["completeness"]
    r = client.put(f"{API}/portals/naukri/review/notice_period", headers=h, json={"done": True}).json()
    assert next(i for i in r["items"] if i["key"] == "notice_period")["done_at"]
    assert r["completeness"] >= before
    assert client.put(f"{API}/portals/naukri/review/nope", headers=h, json={"done": True}).status_code == 404
    assert client.put(f"{API}/portals/indeed/review/x", headers=h, json={"done": True}).status_code == 404
    # Another user sees their own checklist, untouched.
    hb = onboard(client, "po2c@example.com", resume_bytes)
    other = client.get(f"{API}/portals/naukri/review", headers=hb).json()
    assert not next(i for i in other["items"] if i["key"] == "notice_period")["done_at"]
