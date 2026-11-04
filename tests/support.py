"""Test fixtures shared by the CLI tests (tests/) and the API tests (tests/api/)."""

from __future__ import annotations

from pathlib import Path


SYNTHETIC_RESUME_LINES = [
    "TEST CANDIDATE",
    "Bengaluru, Karnataka | +91 9000000000 | test.candidate@example.com",
    "FINANCE ANALYST",
    "PROFESSIONAL SUMMARY",
    "Finance professional with experience in accounts receivable and Excel reporting.",
    "CORE SKILLS",
    "Accounts Receivable • Payment Posting • Excel Reporting • Pivot",
    "Tables • Data Validation",
    "PROFESSIONAL EXPERIENCE",
    "Senior Analyst | Alpha Finance Ltd",
    "Jan 2022 - Present",
    "• Prepared monthly MIS reports in Excel for 12 business units.",
    "• Reduced reconciliation errors by 30% through data validation checks.",
    "Analyst | Beta Services",
    "Jun 2020 - Mar 2022",
    "• Posted insurance payments and handled accounts receivable follow-up.",
    "EDUCATION",
    "Bachelor of Commerce (B.Com)",
    "Example College, Bengaluru | Bangalore University | 2019",
]


def make_pdf(path: Path, lines: list[str]) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 50
    for line in lines:
        page.insert_text((40, y), line, fontsize=9)
        y += 14
    doc.save(path)
    doc.close()
    return path
