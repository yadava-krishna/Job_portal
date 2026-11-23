"""Resume Studio rendering: the generated PDFs and DOCX files themselves are inspected.

Representative resumes (fresher, one page, two pages, very long, unusual dates, long names and URLs, long skill
lists, non-ASCII text) are rendered with every template and checked for: complete content, text inside the margins,
no overlapping text, no section heading stranded at the bottom of a page, no blank trailing page, clickable links,
document metadata, page size, PDF/DOCX parity and the layout report.
"""

from __future__ import annotations

import io
import re

import pymupdf
import pytest

from backend.services.studio_render import (TEMPLATES, format_date, layout_report, normalize_settings, render_docx,
                                            render_model, render_pdf)
from backend.services.studio_service import _doc_from_profile

LONG_ORG = "Bharat Heavy Electricals and Engineering Services International Private Limited, Corporate Finance Shared Services"


def profile(*, roles=2, bullets=3, projects=1, skills=12, fresher=False, dates=("Jan 2023", "Present"), unicode=False) -> dict:
    exp = [] if fresher else [
        {"title": f"Senior Accounts Receivable Analyst {i}", "company": LONG_ORG if i == 1 else f"Example Health {i}",
         "start": dates[0] if i == 0 else f"0{(i % 9) + 1}/20{20 - i}", "end": dates[1] if i == 0 else f"20{21 - i}-06",
         "is_current": i == 0,
         "bullets": [f"Role {i} bullet {j}: reduced DSO from 62 to 41 days across 300 enterprise accounts by redesigning the dunning workflow."
                     for j in range(bullets)]}
        for i in range(roles)]
    return {
        "full_name": "Ananya Iyer" + (" Müller" if unicode else ""), "headline": "Finance Operations Analyst",
        "email": "ananya.iyer@example.com", "phone": "+91 98450 12345", "location": "Pune, Maharashtra",
        "linkedin_url": "https://www.linkedin.com/in/ananya-iyer-finance-operations-analyst-with-a-very-long-profile-slug",
        "summary": ("Expected compensation discussed in ₹ lakh; café-style résumé test. " if unicode else "") +
                   "Finance operations analyst focused on order-to-cash and reconciliations.",
        "experience": exp,
        "projects": [{"name": f"Project {k}: cash application rules", "bullets": [f"Project {k} raised auto-match from 55% to 88%."]}
                     for k in range(projects)],
        "education": [{"degree": "B.Com (Honours)", "institution": "Symbiosis College of Arts and Commerce", "year": "2019"}],
        "skills": [f"Skill{n}" for n in range(skills)], "certifications": ["SAP FI Certified Associate"],
        "achievements": ["Finance team award 2023"] if not fresher else [],
    }


def doc_for(p: dict) -> dict:
    return {"sections": _doc_from_profile(p)}


def text_blocks(pdf: bytes):
    d = pymupdf.open(stream=pdf, filetype="pdf")
    return d, [[b for b in page.get_text("blocks") if b[4].strip()] for page in d]


CASES = {
    "fresher": profile(fresher=True, projects=3),
    "one_page": profile(roles=1, bullets=3),
    "two_pages": profile(roles=4, bullets=5, projects=2),
    "long": profile(roles=8, bullets=7, projects=3, skills=60),
    "unusual_dates": profile(roles=3, dates=("sept '21", "till date")),
    "unicode": profile(roles=1, unicode=True),
}


@pytest.mark.parametrize("key", list(TEMPLATES))
@pytest.mark.parametrize("case", list(CASES))
def test_every_template_renders_complete_content_inside_the_page(key, case):
    doc = doc_for(CASES[case])
    st, _ = normalize_settings(key, {})
    pdf, pages = render_pdf(doc, key, st)
    d, blocks = text_blocks(pdf)
    assert pages == len(d) >= 1
    text = re.sub(r"\s+", " ", " ".join(p.get_text() for p in d))
    # Every piece of content is in the PDF as selectable text (never silently dropped).
    model = render_model(doc, key, st)
    for sec in model["sections"]:
        for it in sec["items"]:
            for b in it.get("bullets", []):
                assert b in text, (key, case, b[:40])
            if it["kind"] == "entry" and it["title"]:
                assert it["title"] in text
    assert model["name"] in text
    margin = st["margin_mm"] * 72 / 25.4
    for pno, (page, bl) in enumerate(zip(d, blocks)):
        assert bl, f"{key}/{case}: page {pno + 1} is blank"
        w = page.rect.width
        for b in bl:
            assert b[0] >= margin - 2 and b[2] <= w - margin + 2, (key, case, pno, b[4][:40])  # inside the side margins
        lines = sorted((b for b in bl), key=lambda b: b[1])
        for a, b in zip(lines, lines[1:]):  # no overlapping text blocks
            overlap_x = min(a[2], b[2]) - max(a[0], b[0])
            overlap_y = a[3] - b[1]
            assert not (overlap_x > 2 and overlap_y > 2), (key, case, pno, a[4][:30], b[4][:30])
        if pno < len(d) - 1:  # a section heading is never the last thing on a page
            last = max((b for b in bl if b[1] < page.rect.height - margin), key=lambda b: b[3])
            assert last[4].strip().upper() not in {s["heading"].upper() for s in model["sections"]}, (key, case, pno)


def test_dates_are_normalised_but_unknown_text_is_kept():
    assert format_date("sept '21", "MMM YYYY") == "Sep 2021"
    assert format_date("01/2020", "MMM YYYY") == "Jan 2020"
    assert format_date("2019-06", "MM/YYYY") == "06/2019"
    assert format_date("March 2018", "YYYY") == "2018"
    assert format_date("till date", "MMM YYYY") == "Present"
    assert format_date("Summer internship", "MMM YYYY") == "Summer internship"  # never invented
    assert format_date("13/2020", "MMM YYYY") == "13/2020"


def test_links_metadata_page_size_and_fonts():
    doc = doc_for(CASES["one_page"])
    pdf, _ = render_pdf(doc, "ats_simple", {"page_size": "LETTER"})
    d = pymupdf.open(stream=pdf, filetype="pdf")
    assert round(d[0].rect.width) == 612 and round(d[0].rect.height) == 792
    uris = [l.get("uri") for l in d[0].get_links()]
    assert "mailto:ananya.iyer@example.com" in uris and "tel:+919845012345" in uris
    assert any(u and u.startswith("https://www.linkedin.com/in/ananya-iyer") for u in uris)
    assert d.metadata["title"] == "Ananya Iyer – Resume" and d.metadata["author"] == "Ananya Iyer"
    assert all(f[1] in ("ttf", "cff", "TrueType", "Type1C", "OpenType") or f[3] for p in d for f in p.get_fonts())  # embedded fonts
    a4, _ = render_pdf(doc, "ats_simple", {})
    assert round(pymupdf.open(stream=a4, filetype="pdf")[0].rect.width) == 595


def test_unicode_survives_in_pdf_and_docx():
    import docx

    doc = doc_for(CASES["unicode"])
    pdf, _ = render_pdf(doc, "technical", {})
    text = "".join(p.get_text() for p in pymupdf.open(stream=pdf, filetype="pdf"))
    assert "₹" in text and "résumé" in text and "Müller" in text
    dx, _ = render_docx(doc, "technical", {})
    assert "₹" in " ".join(p.text for p in docx.Document(io.BytesIO(dx)).paragraphs)


@pytest.mark.parametrize("key", list(TEMPLATES))
def test_pdf_and_docx_carry_the_same_content(key):
    import docx

    doc = doc_for(CASES["two_pages"])
    pdf, _ = render_pdf(doc, key, {})
    ptxt = " ".join(p.get_text() for p in pymupdf.open(stream=pdf, filetype="pdf"))
    ptxt = re.sub(r"-\s*\n\s*", "-", ptxt)  # a long URL wrapped at a hyphen is still one word
    dx, _ = render_docx(doc, key, {})
    dd = docx.Document(io.BytesIO(dx))
    dtxt = " ".join(p.text for p in dd.paragraphs)
    words = lambda t: set(re.findall(r"[A-Za-z0-9@.%&-]{3,}", t)) - {"page"}  # noqa: E731
    assert words(ptxt) - words(dtxt) == set() and words(dtxt) - words(ptxt) == set()
    assert dd.core_properties.title == "Ananya Iyer – Resume"
    # Dates are right-aligned with a tab stop, and headings stay with what follows.
    entry = next(p for p in dd.paragraphs if p.text.startswith("Senior Accounts Receivable Analyst 0"))
    assert "\t" in entry.text and entry.paragraph_format.keep_with_next


def test_layout_settings_have_guard_rails():
    st, notes = normalize_settings("ats_simple", {"font_size": 7, "accent": "#ffff00", "heading_style": "label_left",
                                                  "font_family": "comic", "margin_mm": 2, "line_height": 3})
    assert st["font_size"] == 9.5 and st["accent"] == TEMPLATES["ats_simple"]["accent"]
    assert st["heading_style"] == "caps_rule" and st["font_family"] == "liberation_sans"
    assert st["margin_mm"] == 10 and st["line_height"] == 1.6
    assert any("too light" in n for n in notes) and any("readable" in n for n in notes)
    st2, _ = normalize_settings("modern_professional", {"heading_style": "label_left", "accent": "#0f766e"})
    assert st2["heading_style"] == "label_left" and st2["accent"] == "#0f766e"


def test_layout_report_warns_and_only_suggests():
    long_doc = doc_for(CASES["long"])
    before = repr(long_doc)
    rep = layout_report(long_doc, "graduate", {})
    assert rep["pages"] > 1 and any("designed for 1 page" in w["message"] for w in rep["warnings"])
    assert repr(long_doc) == before  # nothing removed or changed
    assert len(rep["page_fill"]) == rep["pages"] and all(0 <= f <= 1 for f in rep["page_fill"])
    short = layout_report(doc_for(CASES["fresher"]), "graduate", {})
    assert short["pages"] == 1 and not any(w["level"] == "warning" for w in short["warnings"])


def test_layout_endpoint_and_template_catalogue(client, resume_bytes):
    from api_helpers import onboard

    h = onboard(client, "layout@example.com", resume_bytes)
    tpls = {t["key"]: t for t in client.get("/api/v1/studio/templates", headers=h).json()}
    assert tpls["ats_simple"]["name"] == "Classic ATS" and "label_left" not in tpls["ats_simple"]["heading_styles"]
    assert "label_left" in tpls["modern_professional"]["heading_styles"] and tpls["executive"]["fonts"]
    v = client.post("/api/v1/studio/versions", headers=h, json={"name": "Layout", "template_key": "executive"}).json()
    rep = client.get(f"/api/v1/studio/versions/{v['id']}/layout", headers=h).json()
    assert rep["pages"] >= 1 and rep["settings"]["font_family"] == "palatino"
    # Saving settings goes through the same guard rails.
    r = client.put(f"/api/v1/studio/versions/{v['id']}", headers=h, json={"settings": {"accent": "#fafafa", "font_size": 11.5}}).json()
    assert r["settings"]["accent"] == TEMPLATES["executive"]["accent"] and r["settings"]["font_size"] == 11.5


def test_quality_checker_separates_objective_checks_and_reads_the_export_back(client, resume_bytes):
    from api_helpers import onboard

    h = onboard(client, "checker@example.com", resume_bytes)
    v = client.post("/api/v1/studio/versions", headers=h, json={"name": "Check", "template_key": "ats_simple"}).json()
    fb = client.get(f"/api/v1/studio/versions/{v['id']}/feedback", headers=h).json()
    assert "not an ATS score" in fb["score_method"]
    assert not [i for i in fb["issues"] if i["code"] in ("export_readback", "render")], fb["issues"]  # a clean resume reads back fully
    assert all(i["kind"] in ("format", "accuracy", "writing", "job") for i in fb["issues"])

    exp = next(s for s in v["sections"] if s["type"] == "experience")
    first = exp["blocks"][0]
    first["content"] = {**first["content"], "start": "Jan 2024", "end": "Mar 2020", "current": False}  # ends before it starts
    first["bullets"] = [{"text": "Closed the books on time 🚀", "source": "user", "approved": True, "evidence_refs": []}]
    import copy
    exp["blocks"].append({**copy.deepcopy(first), "id": None})  # the same entry twice
    saved = client.put(f"/api/v1/studio/versions/{v['id']}", headers=h, json={"revision": v["revision"], "sections": v["sections"]})
    assert saved.status_code == 200, saved.text
    codes = {i["code"]: i for i in client.get(f"/api/v1/studio/versions/{v['id']}/feedback", headers=h).json()["issues"]}
    assert codes["date_order"]["level"] == "error" and codes["date_order"]["kind"] == "format"
    # The emoji: printed but risky for application systems (unsupported_chars), or missing from the PDF where no
    # installed font draws it (dropped_chars, as on the production image).
    chars = codes.get("unsupported_chars") or codes.get("dropped_chars")
    assert "duplicate_entry" in codes and chars and "🚀" in chars["message"] + chars["evidence"]
    assert chars["where"]["section"] == "experience" and chars["where"]["field"] == "bullet" and chars["fix"]
    assert "entry_dates_unread" not in codes  # reversed dates are one finding (date_order), not two


def test_job_tailoring_reorders_skills_and_projects_without_adding_anything(client, resume_bytes):
    from api_helpers import import_job, onboard

    h = onboard(client, "tailor@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    v = client.post("/api/v1/studio/versions", headers=h, json={"name": "Tailor", "template_key": "ats_simple"}).json()
    skills = next(s for s in v["sections"] if s["type"] == "skills")
    skills["blocks"][0]["content"]["items"] = ["Tableau", "Python", "Accounts Receivable", "Collections", "Excel"]
    proj = next(s for s in v["sections"] if s["type"] == "projects")
    proj["visible"] = True
    proj["blocks"] = [
        {"type": "entry", "visible": True, "content": {"title": "Photography club website"}, "source_profile_ref": None,
         "bullets": [{"text": "Built a gallery site for the club.", "source": "user", "approved": True, "evidence_refs": []}]},
        {"type": "entry", "visible": True, "content": {"title": "Collections dashboard"}, "source_profile_ref": None,
         "bullets": [{"text": "Tracked accounts receivable ageing and collections follow-ups.", "source": "user", "approved": True, "evidence_refs": []}]}]
    client.put(f"/api/v1/studio/versions/{v['id']}", headers=h, json={"revision": v["revision"], "sections": v["sections"]})
    sug = client.get(f"/api/v1/studio/versions/{v['id']}/suggestions", headers=h, params={"user_job_id": uj}).json()
    kinds = {s["kind"]: s for s in sug}
    rs = kinds["reorder_skills"]
    items = ["Tableau", "Python", "Accounts Receivable", "Collections", "Excel"]
    reordered = [items[i] for i in rs["order"]]
    assert sorted(reordered) == sorted(items) and reordered.index("Accounts Receivable") < reordered.index("Tableau")
    assert kinds["reorder_entries"]["order"] == [1, 0]
    # Every change JobPilot can apply is backed by verified data; gaps and confirmations change nothing.
    assert all(s["evidence"] == "supported" for s in sug if s["kind"] not in ("gap", "confirm"))
    assert all(s["after"] is None and s.get("order") is None for s in sug if s["kind"] in ("gap", "confirm"))
    assert all(s["category"] and s["why"] and s["effect"] for s in sug)
