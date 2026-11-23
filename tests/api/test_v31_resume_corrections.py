"""JobPilot V3.1: regression tests for the reported screenshot issues (resume export, checker, scores,
recommendations, explicit resume selection). Real WeasyPrint PDFs, read back with PyMuPDF; no mocks of the renderer."""

from __future__ import annotations

import copy
from datetime import date

import pytest
from api_helpers import import_job, onboard

API = "/api/v1"
from test_extension import boards  # noqa: E402,F401  (fixture)


# ---- fixtures: structured resumes with the characters that broke --------------------------------------------------

def entry(title, org, start, end=None, *, loc=None, bullets=(), current=False):
    return {"type": "entry", "visible": True, "source_profile_ref": None,
            "content": {"title": title, "organization": org, "start": start, "end": end, "current": current, "location": loc},
            "bullets": [{"text": b, "source": "user", "approved": True, "evidence_refs": []} for b in bullets]}


def unicode_doc(*, many_roles: int = 3, pua: bool = False):
    """Bullets, Unicode punctuation, a long title, dates, certifications, special characters; `many_roles` > 6 makes
    it run onto a second page."""
    lead = " " if pua else ""
    roles = [entry("Senior Data Analyst, Payments Risk & Fraud Strategy (Merchant Platforms)", "Paytm", "Jan 2022", current=True,
                   loc="Bangalore, India", bullets=[f"{lead}Built the merchant risk dashboard used by 40 analysts — cut review time by 35%.",
                                                     "Owned the “weekly KPI” pack; reconciled ₹12 Cr of settlements/month.",
                                                     "Automated SQL → Python pipelines (pandas, Airflow) for 3 teams."]),
             entry("Data Analyst", "Zeta", "Jun 2019", "Dec 2021", loc="Bangalore, India",
                   bullets=["Modelled card-spend cohorts; R² of 0.82 on the churn model.", "Partnered with café-chain clients on co-branded rewards."]),
             entry("Analyst Intern", "Flipkart", "Jan 2019", "May 2019", loc="Bangalore, India", bullets=["Cleaned catalogue data with SQL."])]
    for i in range(max(0, many_roles - 3)):
        roles.append(entry(f"Operations Associate {i + 1}", f"Example Co {i + 1}", f"Jan {2010 + i}", f"Dec {2010 + i}", loc="Bangalore, India",
                           bullets=[f"Handled the month-end close checklist for business unit {i + 1}, including accruals, "
                                    "reconciliations and variance commentary for the finance leadership review."] * 1
                           + [f"Trained {i + 3} new joiners on the ledger tools and the escalation process."]))
    return {"sections": [
        {"type": "header", "heading": "Contact", "visible": True, "blocks": [
            {"type": "contact", "visible": True, "source_profile_ref": None, "bullets": [],
             "content": {"name": "Asha Rao", "email": "asha.rao@example.com", "phone": "+91 98450 12345", "location": "Bengaluru, India", "links": []}}]},
        {"type": "summary", "heading": "Summary", "visible": True, "blocks": [
            {"type": "text", "visible": True, "source_profile_ref": None, "bullets": [], "content": {"text": "Data analyst — 5 years in fintech; SQL, Python & dashboards."}}]},
        {"type": "experience", "heading": "Experience", "visible": True, "blocks": roles},
        {"type": "education", "heading": "Education", "visible": True, "blocks": [entry("B.Tech, Computer Science", "RV College of Engineering", "2015", "2019")]},
        {"type": "certifications", "heading": "Certifications", "visible": True, "blocks": [entry("Google Data Analytics Certificate", "Coursera", "2023")]},
        {"type": "skills", "heading": "Skills", "visible": True, "blocks": [
            {"type": "skill_group", "visible": True, "source_profile_ref": None, "bullets": [], "content": {"label": None, "items": ["SQL", "Python", "Tableau", "A/B testing"]}}]},
    ]}


def make_version(client, h, doc):
    v = client.post(f"{API}/studio/versions", headers=h, json={"name": "V3.1", "template_key": "ats_simple"}).json()
    r = client.put(f"{API}/studio/versions/{v['id']}", headers=h, json={"revision": v["revision"], "sections": doc["sections"]})
    assert r.status_code == 200, r.text
    return r.json()


def check(client, h, vid, **params):
    r = client.get(f"{API}/studio/versions/{vid}/feedback", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ---- Task 3: corrupted characters --------------------------------------------------------------------------------

def test_text_normalisation_rules():
    from core.textclean import clean, fold, unreadable

    assert clean(" Built it", bullet=True) == "Built it"           # Symbol-font bullet at the start: dropped
    assert clean("A  B") == "A • B"                                 # elsewhere: a real bullet character
    assert clean("efﬁcient team​") == "efficient team"    # ligature, no-break space, zero-width
    assert unreadable("bad � char") == ["�"]
    assert fold("Jan 2022 – Present “KPI”") == fold("jan 2022 - present \"kpi\"")


def test_parser_turns_symbol_font_bullets_into_bullets_not_boxes():
    from resume.resume_parser import _clean_line, _join_lone_markers, is_bullet

    assert is_bullet(_clean_line(" Reconciled accounts"))
    assert is_bullet(_clean_line("� Reconciled accounts"))            # unmapped bullet glyph at line start
    assert "�" in _clean_line("Rec�onciled")                      # mid-word: kept, the checker reports it
    assert _join_lone_markers(["•", "Built X", "Title"]) == ["• Built X", "Title"]


def test_export_with_bullets_and_special_characters_is_visually_and_textually_correct(client, resume_bytes):
    import pymupdf

    h = onboard(client, "v31a@example.com", resume_bytes)
    v = make_version(client, h, unicode_doc(pua=True))
    # Saving normalised the Symbol-font bullet away; every other character is kept.
    exp = next(s for s in v["sections"] if s["type"] == "experience")
    assert exp["blocks"][0]["bullets"][0]["text"].startswith("Built the merchant risk dashboard")
    pdf = client.get(f"{API}/studio/versions/{v['id']}/preview.pdf", headers=h)
    doc = pymupdf.open(stream=pdf.content, filetype="pdf")
    text = " ".join(p.get_text() for p in doc)
    notdef = [chr(c[0]) for p in doc for sp in p.get_texttrace() for c in sp["chars"] if c[1] == 0]
    assert notdef == []                                                    # no box glyph anywhere
    for needle in ("₹12 Cr", "R² of 0.82", "café-chain", "“weekly KPI”", "SQL → Python", "Google Data Analytics Certificate"):
        assert needle in " ".join(text.split()), needle
    fb = check(client, h, v["id"])
    assert not [i for i in fb["issues"] if i["code"] in ("unreadable_chars", "dropped_chars", "export_readback", "render")], fb["issues"]


def test_unreadable_character_is_reported_at_its_field_and_fixing_it_clears_the_finding(client, resume_bytes):
    h = onboard(client, "v31b@example.com", resume_bytes)
    doc = unicode_doc()
    doc["sections"][2]["blocks"][1]["bullets"][0]["text"] = "Modelled card�spend cohorts."
    v = make_version(client, h, doc)
    fb = check(client, h, v["id"], revision=v["revision"])
    bad = [i for i in fb["issues"] if i["code"] == "unreadable_chars"]
    assert len(bad) == 1                                                   # once, not repeated by the read-back check
    i = bad[0]
    assert i["level"] == "error" and i["where"] == {"section": "experience", "block": 1, "bullet": 0, "field": "bullet"}
    assert i["entry"] == "Data Analyst — Zeta" and "U+FFFD" in i["evidence"] and i["why"] and i["fix"]
    before = fb["scores"]["resume_quality"]["score"]
    # The structural recommendation, accepted (the editor applies it and saves), then re-checked.
    sug = client.get(f"{API}/studio/versions/{v['id']}/suggestions", headers=h).json()
    fix = next(s for s in sug if s["category"] == "structure" and s["kind"] == "rewrite")
    assert fix["after"] == "Modelled card spend cohorts." and fix["where_label"].startswith("Experience · Data Analyst — Zeta")
    doc2 = {"sections": copy.deepcopy(v["sections"])}
    doc2["sections"][2]["blocks"][1]["bullets"][0]["text"] = fix["after"]
    v2 = client.put(f"{API}/studio/versions/{v['id']}", headers=h, json={"revision": v["revision"], "sections": doc2["sections"]}).json()
    fb2 = check(client, h, v["id"], revision=v2["revision"])
    assert not [i for i in fb2["issues"] if i["code"] == "unreadable_chars"]
    assert fb2["scores"]["resume_quality"]["score"] == before + 25
    assert fb2["revision"] == v2["revision"]


def test_rejecting_a_recommendation_changes_nothing(client, resume_bytes):
    h = onboard(client, "v31c@example.com", resume_bytes)
    doc = unicode_doc()
    doc["sections"][2]["blocks"][2]["bullets"][0]["text"] = "Responsible for cleaning catalogue data with SQL."
    v = make_version(client, h, doc)
    sug = client.get(f"{API}/studio/versions/{v['id']}/suggestions", headers=h).json()
    rw = next(s for s in sug if s["category"] == "writing")
    assert rw["before"].startswith("Responsible for") and rw["verified"] is True and "Resume Quality" in rw["effect"]
    again = client.get(f"{API}/studio/versions/{v['id']}", headers=h).json()
    assert again["revision"] == v["revision"]                              # asking for suggestions never edits
    assert again["sections"][2]["blocks"][2]["bullets"][0]["text"] == "Responsible for cleaning catalogue data with SQL."


# ---- Task 4: title vs location, entries kept apart ----------------------------------------------------------------

@pytest.mark.parametrize("lines", [
    ["Senior Data Analyst", "Paytm", "Bangalore, India", "Jan 2022 – Present", "• Built dashboards.",
     "Data Analyst", "Zeta", "Bangalore, India", "Jun 2019 – Dec 2021", "• Automated reconciliation."],
    ["Senior Data Analyst | Paytm", "Bangalore, India | Jan 2022 – Present", "• Built dashboards.",
     "Data Analyst | Zeta", "Bangalore, India | Jun 2019 – Dec 2021", "• Automated reconciliation."],
    ["Paytm", "Senior Data Analyst", "Jan 2022 – Present  Bangalore, India", "• Built dashboards.",
     "Zeta", "Data Analyst", "Jun 2019 – Dec 2021  Bangalore, India", "• Automated reconciliation."],
    ["Senior Data Analyst | Paytm, Bangalore, India", "Jan 2022 – Present", "• Built dashboards.",
     "Data Analyst | Zeta, Bangalore, India", "Jun 2019 – Dec 2021", "• Automated reconciliation."],
])
def test_location_is_never_read_as_the_job_title(lines):
    from resume.profile_builder import parse_experience

    roles, _ = parse_experience(lines, date(2026, 11, 23))
    assert [(r["title"], r["company"], r["location"]) for r in roles] == [
        ("Senior Data Analyst", "Paytm", "Bangalore, India"), ("Data Analyst", "Zeta", "Bangalore, India")]
    assert [r["start"] for r in roles] == ["2022-01", "2019-06"]


def test_entries_with_identical_locations_are_distinct_and_no_warning_is_duplicated(client, resume_bytes):
    h = onboard(client, "v31d@example.com", resume_bytes)
    v = make_version(client, h, unicode_doc())
    fb = check(client, h, v["id"])
    ids = [i["id"] for i in fb["issues"]]
    assert len(ids) == len(set(ids))                                        # every issue once
    assert not [i for i in fb["issues"] if "Bangalore" in i["message"]]     # the location is never a "missing role"
    assert not [i for i in fb["issues"] if i["code"].startswith("entry_")], fb["issues"]


def test_issue_ids_are_stable_and_refer_to_the_affected_entry(client, resume_bytes):
    h = onboard(client, "v31e@example.com", resume_bytes)
    doc = unicode_doc()
    doc["sections"][2]["blocks"][1]["content"]["start"] = None             # Zeta: no start date
    v = make_version(client, h, doc)
    first = {i["code"]: i for i in check(client, h, v["id"])["issues"]}["date_missing"]
    assert first["entry"] == "Data Analyst — Zeta" and first["where"]["block"] == 1 and first["where"]["field"] == "dates"
    # Move Zeta to the top: same issue id (it is about the entry, not its position), new position.
    secs = copy.deepcopy(v["sections"])
    secs[2]["blocks"] = [secs[2]["blocks"][1], secs[2]["blocks"][0], secs[2]["blocks"][2]]
    v2 = client.put(f"{API}/studio/versions/{v['id']}", headers=h, json={"revision": v["revision"], "sections": secs}).json()
    again = {i["code"]: i for i in check(client, h, v["id"])["issues"]}["date_missing"]
    assert again["id"] == first["id"] and again["where"]["block"] == 0 and v2["revision"] == v["revision"] + 1


# ---- Task 5: page count and stale analysis ------------------------------------------------------------------------

def test_page_count_agrees_between_check_preview_and_layout_for_a_multi_page_resume(client, resume_bytes):
    h = onboard(client, "v31f@example.com", resume_bytes)
    v = make_version(client, h, unicode_doc(many_roles=14))
    fb = check(client, h, v["id"])
    pv = client.get(f"{API}/studio/versions/{v['id']}/preview.pdf", headers=h)
    lay = client.get(f"{API}/studio/versions/{v['id']}/layout", headers=h).json()
    assert fb["pages"] >= 2
    assert fb["pages"] == int(pv.headers["X-Page-Count"]) == lay["pages"]
    assert pv.headers["X-Revision"] == str(v["revision"]) == str(fb["revision"]) == str(lay["revision"])
    assert fb["checksum"] == lay["checksum"] == pv.headers["X-Checksum"]


def test_a_check_for_an_older_revision_is_refused_so_it_cannot_overwrite_newer_results(client, resume_bytes):
    h = onboard(client, "v31g@example.com", resume_bytes)
    v = make_version(client, h, unicode_doc())
    secs = copy.deepcopy(v["sections"])
    secs[1]["blocks"][0]["content"]["text"] = "Data analyst with five years in fintech."
    v2 = client.put(f"{API}/studio/versions/{v['id']}", headers=h, json={"revision": v["revision"], "sections": secs}).json()
    old = client.get(f"{API}/studio/versions/{v['id']}/feedback", headers=h, params={"revision": v["revision"]})
    assert old.status_code == 409 and old.json()["detail"]["revision"] == v2["revision"]
    assert check(client, h, v["id"], revision=v2["revision"])["revision"] == v2["revision"]


def test_renderer_version_is_part_of_the_export_cache_key(client, resume_bytes, monkeypatch):
    from backend.services import resume_check

    h = onboard(client, "v31h@example.com", resume_bytes)
    v = make_version(client, h, unicode_doc())
    a = client.post(f"{API}/studio/versions/{v['id']}/export", headers=h, json={"format": "pdf"}).json()
    monkeypatch.setattr(resume_check, "RENDERER_VERSION", "test-next")
    b = client.post(f"{API}/studio/versions/{v['id']}/export", headers=h, json={"format": "pdf"}).json()
    assert a["checksum"] != b["checksum"]                                   # re-rendered, not the stale cached file


# ---- Task 6: three separate evaluations ----------------------------------------------------------------------------

def test_job_match_quality_and_alignment_are_reported_separately(client, resume_bytes):
    h = onboard(client, "v31i@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    v = make_version(client, h, unicode_doc())
    general = check(client, h, v["id"])
    assert set(general["scores"]) == {"resume_quality"}
    fb = check(client, h, v["id"], user_job_id=uj)
    s = fb["scores"]
    assert set(s) == {"resume_quality", "job_match", "alignment"}
    assert s["resume_quality"]["score"] == general["scores"]["resume_quality"]["score"]   # a job never changes Quality
    assert "not an ATS score" in s["resume_quality"]["method"] and "doesn't predict" in s["resume_quality"]["method"]
    assert 0 <= s["alignment"]["score"] <= 100 and "required count twice" in s["alignment"]["method"]
    assert s["job_match"]["method"]
    # Notes never lower Quality: only error/warning/suggestion points count.
    from backend.services.resume_check import quality_score
    assert quality_score([{"level": "info", "kind": "format"}] * 5) == 100
    assert quality_score([{"level": "warning", "kind": "job"}]) == 100


def test_job_recommendations_never_add_unevidenced_skills(client, resume_bytes):
    h = onboard(client, "v31j@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    v = make_version(client, h, unicode_doc())
    sug = client.get(f"{API}/studio/versions/{v['id']}/suggestions", headers=h, params={"user_job_id": uj}).json()
    gaps = [s for s in sug if s["category"] == "gap"]
    assert gaps and all(s["after"] is None and s["where"] is None and not s["verified"] for s in gaps)
    assert all(s["evidence"] == "supported" for s in sug if s["kind"] == "add_skill")


# ---- Task 2: explicit resume selection ------------------------------------------------------------------------------

def test_apply_package_requires_an_explicit_resume_choice_and_records_the_exact_file(client, resume_bytes, boards):
    from test_apply_workspace import _prepare
    from test_extension import pair, with_board_job, xh

    h = onboard(client, "v31k@example.com", resume_bytes)
    item = with_board_job(client, h)
    app_id = _prepare(client, h, item["user_job_id"])
    pkg = client.get(f"{API}/applications/{app_id}/package", headers=h).json()["package"]
    assert pkg["resume"]["selected_by"] is None and pkg["resume"]["ready"] is False
    assert pkg["resume"]["recommended"]["why"]                              # a suggestion, with its reason
    assert pkg["readiness"]["resume_choice_needed"] is True and pkg["readiness"]["level"] != "ready"
    assert "Choose the resume" in pkg["readiness"]["summary"]
    tok = pair(client, h)
    assert client.get(f"{API}/extension/applications/{app_id}/package", headers=xh(tok)).json()["resume"] is None  # nothing to attach yet
    rec = pkg["resume"]["recommended"]
    r = client.put(f"{API}/applications/{app_id}/resume", headers=h, json={"kind": rec["kind"], "id": rec["id"]})
    res = r.json()["package"]["resume"]
    assert res["selected_by"] == "you" and res["ready"] and res["checksum"]
    ext = client.get(f"{API}/extension/applications/{app_id}/package", headers=xh(tok)).json()["resume"]
    assert ext["selected_by"] == "you" and ext["id"] == rec["id"] and ext["checksum"] == res["checksum"]


def test_preview_and_check_exporting_the_same_revision_at_once_do_not_collide(client, resume_bytes):
    """The preview and the Check tab both ask for the export right after a save (found in the V3.1 walkthrough:
    a duplicate cache row and a lost temporary file made one of them fail with HTTP 500)."""
    import threading

    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import ResumeExport, User
    from backend.services import studio_service as ss

    h = onboard(client, "v31l@example.com", resume_bytes)
    v = make_version(client, h, unicode_doc())
    errors, ids = [], []

    def one():
        try:
            with session_factory()() as db:
                user = db.query(User).filter_by(email="v31l@example.com").one()
                ids.append(ss.export(db, get_settings(), user, ss.owned_version(db, user, v["id"]), "pdf").id)
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    ts = [threading.Thread(target=one) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errors == [] and len(set(ids)) == 1
    with session_factory()() as db:
        assert db.query(ResumeExport).filter_by(resume_version_id=v["id"], format="pdf").count() == 1
