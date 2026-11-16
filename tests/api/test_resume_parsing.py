"""Resume parsing without AI: two-column PDFs with interleaved text order, Title-Case and Indian-style headings,
Word (.docx) files with page headers and tables, one-skill-per-line lists, contact details, and a round trip through
every Resume Studio template (the parser must read JobPilot's own PDFs back correctly)."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pytest

from api_helpers import auth, register

TODAY = date(2026, 11, 16)


def _extract(path: Path) -> dict:
    from core.skills import SkillTaxonomy
    from core.settings import PROJECT_ROOT
    from resume.profile_builder import ResumeProfileExtractor

    tax = SkillTaxonomy.from_file(PROJECT_ROOT / "config" / "skills_taxonomy.yaml")
    return ResumeProfileExtractor(tax).build(path, today=TODAY)


def _roles(p: dict) -> list[tuple]:
    return [(r["title"], r["company"], r["start"], r["is_current"]) for r in p["experience"]]


def two_column_pdf(path: Path) -> Path:
    """A sidebar layout whose text is written line by line across both columns (as many design tools do)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    left = ["CONTACT", "rahul.k@example.com", "+91 98860 11223", "Hyderabad, Telangana", "", "SKILLS", "SAP FI-AR", "Excel", "Power BI",
            "Tally ERP", "", "EDUCATION", "B.Com, Osmania University", "2015 - 2018", "", "LANGUAGES", "English, Telugu, Hindi"]
    right = ["Rahul Kumar", "Accounts Receivable Specialist", "", "PROFILE SUMMARY", "Accounts receivable specialist with five years in",
             "collections and cash application for US healthcare clients.", "", "WORK EXPERIENCE", "AR Specialist, Omega Healthcare",
             "June, 2021 - Present", "• Collected USD 1.2M monthly across 450 payer accounts.", "• Cut unapplied cash by 35% with daily lockbox review.",
             "AR Associate, Firstsource Solutions", "Jul 2018 - May 2021", "• Handled denials and appeals for 3 hospital clients.",
             "• Maintained 98% accuracy in payment posting audits."]
    c = canvas.Canvas(str(path), pagesize=A4)
    y = A4[1] - 60
    for i in range(max(len(left), len(right))):
        if i < len(left) and left[i]:
            c.setFont("Helvetica", 9.5)
            c.drawString(40, y, left[i])
        if i < len(right) and right[i]:
            c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 14 if i == 0 else 10)
            c.drawString(215, y, right[i])
        y -= 16
    c.save()
    return path


def titlecase_pdf(path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    lines = ["Sneha Patil", "sneha.patil@example.com | +91 99000 55443 | Pune", "", "Career Objective",
             "To work as a finance analyst in a growing organisation and contribute to accurate reporting.", "",
             "Work Experience:", "Junior Accountant, Kale & Co Chartered Accountants", "June, 2022 - Present",
             "• Prepared GST returns for 40 clients every month.", "• Reconciled bank statements and vendor ledgers in Tally.", "",
             "Technical Skills", "Tally Prime, GST, MS Excel, Bank Reconciliation", "", "Education", "M.Com, Savitribai Phule Pune University, 2022", "",
             "Personal Details", "Date of Birth: 01/01/2000", "Marital Status: Single", "Hobbies: Reading, Badminton", "",
             "Declaration", "I hereby declare that the above information is true to the best of my knowledge."]
    c = canvas.Canvas(str(path), pagesize=A4)
    y = A4[1] - 60
    for ln in lines:
        c.setFont("Helvetica", 10)
        c.drawString(50, y, ln)
        y -= 15
    c.save()
    return path


def resume_docx(path: Path | None = None) -> bytes:
    import docx

    d = docx.Document()
    d.sections[0].header.paragraphs[0].text = "Arjun Mehta | arjun.mehta@example.com | +91 98450 77665 | Chennai"
    for text, style in (("PROFESSIONAL SUMMARY", None), ("Credit and collections analyst with four years in B2B order-to-cash.", None),
                        ("PROFESSIONAL EXPERIENCE", None), ("Collections Analyst, Zeta Logistics", None), ("Aug 2020 - Present", None),
                        ("Reduced 90+ day overdue receivables by 28% in one year.", "List Bullet"),
                        ("Built a weekly ageing dashboard in Power BI.", "List Bullet"), ("KEY SKILLS", None)):
        d.add_paragraph(text, style=style) if style else d.add_paragraph(text)
    t = d.add_table(rows=2, cols=3)
    for i, s in enumerate(["Credit control", "SAP S/4HANA", "Power BI", "Dunning", "Excel", "Cash application"]):
        t.cell(i // 3, i % 3).text = s
    d.add_paragraph("EDUCATION")
    d.add_paragraph("MBA Finance, Loyola Institute of Business Administration, 2020")
    buf = io.BytesIO()
    d.save(buf)
    if path:
        path.write_bytes(buf.getvalue())
    return buf.getvalue()


def test_two_column_pdf_is_read_column_by_column(tmp_path):
    p = _extract(two_column_pdf(tmp_path / "two.pdf"))
    assert p["name"] == "Rahul Kumar"
    assert p["contact"] == {"email": "rahul.k@example.com", "phone": "+91 98860 11223", "location": "Hyderabad, Telangana"}
    assert _roles(p) == [("AR Specialist", "Omega Healthcare", "2021-06", True), ("AR Associate", "Firstsource Solutions", "2018-07", False)]
    assert {"SAP FI-AR", "Power BI"} <= set(p["skills_listed_on_resume"])  # one skill per line stays one item each
    assert not any("healthcare clients" in s for s in p["skills_listed_on_resume"])


def test_title_case_and_indian_headings(tmp_path):
    p = _extract(titlecase_pdf(tmp_path / "tc.pdf"))
    assert p["name"] == "Sneha Patil" and p["contact"]["location"] == "Pune" and p["contact"]["phone"] == "+91 99000 55443"
    assert _roles(p) == [("Junior Accountant", "Kale & Co Chartered Accountants", "2022-06", True)]
    assert p["summary"].startswith("To work as a finance analyst")
    listed = " ".join(p["skills_listed_on_resume"])
    assert "Tally Prime" in listed and "Marital" not in listed and "Badminton" not in listed and "declare" not in p["summary"]


def test_word_resume_with_header_and_skills_table(tmp_path):
    path = tmp_path / "cv.docx"
    resume_docx(path)
    p = _extract(path)
    assert p["name"] == "Arjun Mehta"
    assert p["contact"] == {"email": "arjun.mehta@example.com", "phone": "+91 98450 77665", "location": "Chennai"}
    assert _roles(p) == [("Collections Analyst", "Zeta Logistics", "2020-08", True)]
    assert {"Credit control", "SAP S/4HANA", "Power BI", "Dunning", "Excel", "Cash application"} <= set(p["skills_listed_on_resume"])


@pytest.mark.parametrize("template", ["ats_simple", "modern_professional", "technical", "finance", "graduate", "executive", "international"])
def test_resume_studio_pdfs_parse_back_to_the_same_roles(tmp_path, template):
    from backend.services.studio_render import render_pdf
    from backend.services.studio_service import _doc_from_profile

    prof = {"full_name": "Ananya Iyer", "headline": "Finance Operations Analyst", "email": "ananya.iyer@example.com",
            "phone": "+91 98450 12345", "location": "Pune, Maharashtra", "summary": "Order-to-cash and reconciliation specialist.",
            "experience": [{"title": "Senior AR Analyst", "company": "Example Health", "start": "Jan 2023", "end": None, "is_current": True,
                            "bullets": ["Reduced DSO from 62 to 41 days.", "Automated dunning for 300 accounts."]},
                           {"title": "AR Analyst", "company": "Acme Finance Services", "start": "Jun 2019", "end": "Dec 2022", "is_current": False,
                            "bullets": ["Reconciled 400 customer accounts monthly."]}],
            "education": [{"degree": "B.Com", "institution": "Symbiosis College", "year": "2019"}],
            "skills": ["SAP FI-AR", "Excel", "Power BI"]}
    pdf, _ = render_pdf({"sections": _doc_from_profile(prof)}, template, {})
    path = tmp_path / f"{template}.pdf"
    path.write_bytes(pdf)
    p = _extract(path)
    assert p["name"] == "Ananya Iyer" and p["contact"]["email"] == "ananya.iyer@example.com"
    assert [(r["title"], r["company"], r["start"]) for r in p["experience"]] == [
        ("Senior AR Analyst", "Example Health", "2023-01"), ("AR Analyst", "Acme Finance Services", "2019-06")], template


def test_word_upload_through_the_api_and_unsafe_files_are_refused(client):
    import zipfile

    h = auth(register(client, "docx@example.com"))
    data = resume_docx()
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    r = client.post("/api/v1/profile/resume", headers=h, files={"file": ("Arjun CV.docx", data, docx_mime)})
    assert r.status_code == 201, r.text
    parsed = r.json()["parsed"]
    assert parsed["full_name"] == "Arjun Mehta" and parsed["experience"][0]["company"] == "Zeta Logistics"
    files = client.get("/api/v1/profile/resumes", headers=h).json()
    assert files[0]["original_filename"] == "Arjun CV.docx"
    dl = client.get(f"/api/v1/profile/resumes/{files[0]['id']}/file", headers=h, params={"inline": True})
    assert dl.status_code == 200 and dl.content[:2] == b"PK" and "attachment" in dl.headers["content-disposition"]
    assert dl.headers["content-type"].startswith(docx_mime)
    # A macro-enabled document and a random zip are refused.
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w") as dst:
        for i in src.infolist():
            dst.writestr(i, src.read(i.filename))
        dst.writestr("word/vbaProject.bin", b"macro")
    bad = client.post("/api/v1/profile/resume", headers=h, files={"file": ("m.docx", buf.getvalue(), docx_mime)})
    assert bad.status_code == 415 and "macros" in bad.json()["detail"]
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zz:
        zz.writestr("hello.txt", "x" * 500)
    assert client.post("/api/v1/profile/resume", headers=h, files={"file": ("x.docx", z.getvalue(), docx_mime)}).status_code == 415
