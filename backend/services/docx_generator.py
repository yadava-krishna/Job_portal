"""Native Microsoft Word (.docx) Resume Generator.

Produces clean, standard OpenXML documents formatted with standard headings,
margins, fonts, and bullet points optimized for ATS systems and human recruiters.
"""

from __future__ import annotations

import io
from typing import Any

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH


class DocxResumeGenerator:
    """Generates standard ATS-compliant DOCX resumes."""

    @classmethod
    def generate(
        cls,
        candidate_name: str,
        contact_info: dict[str, str],
        summary: str,
        skills: list[str],
        experiences: list[dict[str, Any]],
        education: str | None = None,
    ) -> io.BytesIO:
        doc = docx.Document()

        # Set standard 0.75-inch margins
        for section in doc.sections:
            section.top_margin = Inches(0.75)
            section.bottom_margin = Inches(0.75)
            section.left_margin = Inches(0.75)
            section.right_margin = Inches(0.75)

        # 1. Candidate Header
        name_para = doc.add_paragraph()
        name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        name_run = name_para.add_run(candidate_name)
        name_run.bold = True
        name_run.font.size = Pt(20)
        name_run.font.name = "Calibri"
        name_run.font.color.rgb = RGBColor(30, 41, 59)

        # Contact Subheader
        contact_parts = []
        if contact_info.get("email"):
            contact_parts.append(contact_info["email"])
        if contact_info.get("phone"):
            contact_parts.append(contact_info["phone"])
        if contact_info.get("location"):
            contact_parts.append(contact_info["location"])
        if contact_info.get("linkedin"):
            contact_parts.append(contact_info["linkedin"])

        if contact_parts:
            contact_para = doc.add_paragraph()
            contact_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            contact_run = contact_para.add_run(" | ".join(contact_parts))
            contact_run.font.size = Pt(9.5)
            contact_run.font.name = "Calibri"
            contact_run.font.color.rgb = RGBColor(100, 116, 139)

        # Helper for adding styled section headers
        def add_section_heading(title: str):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(title.upper())
            run.bold = True
            run.font.size = Pt(11)
            run.font.name = "Calibri"
            run.font.color.rgb = RGBColor(15, 23, 42)

        # 2. Professional Summary
        if summary:
            add_section_heading("Professional Summary")
            sp = doc.add_paragraph()
            sp.paragraph_format.space_after = Pt(6)
            s_run = sp.add_run(summary)
            s_run.font.size = Pt(10)
            s_run.font.name = "Calibri"

        # 3. Technical Skills
        if skills:
            add_section_heading("Technical Skills")
            sk_p = doc.add_paragraph()
            sk_p.paragraph_format.space_after = Pt(6)
            sk_run = sk_p.add_run(" • ".join(skills))
            sk_run.font.size = Pt(10)
            sk_run.font.name = "Calibri"

        # 4. Work Experience
        if experiences:
            add_section_heading("Professional Experience")
            for exp in experiences:
                company = exp.get("company", "")
                title = exp.get("title", "")
                start = exp.get("start_date") or ""
                end = "Present" if exp.get("is_current") else (exp.get("end_date") or "")
                date_str = f"{start} - {end}".strip(" -")

                ep = doc.add_paragraph()
                ep.paragraph_format.space_before = Pt(6)
                ep.paragraph_format.space_after = Pt(2)

                t_run = ep.add_run(title)
                t_run.bold = True
                t_run.font.size = Pt(10.5)
                t_run.font.name = "Calibri"

                c_run = ep.add_run(f" | {company}")
                c_run.font.size = Pt(10.5)
                c_run.font.name = "Calibri"

                if date_str:
                    d_run = ep.add_run(f"  ({date_str})")
                    d_run.italic = True
                    d_run.font.size = Pt(9.5)
                    d_run.font.name = "Calibri"
                    d_run.font.color.rgb = RGBColor(100, 116, 139)

                bullets = exp.get("bullets", [])
                for b in bullets:
                    bp = doc.add_paragraph(style="List Bullet")
                    bp.paragraph_format.space_before = Pt(0)
                    bp.paragraph_format.space_after = Pt(2)
                    b_run = bp.add_run(b)
                    b_run.font.size = Pt(9.5)
                    b_run.font.name = "Calibri"

        # 5. Education
        if education:
            add_section_heading("Education")
            ed_p = doc.add_paragraph()
            ed_run = ed_p.add_run(education)
            ed_run.font.size = Pt(10)
            ed_run.font.name = "Calibri"

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
