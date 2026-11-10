"""ATS-Pure Vector PDF Resume Generator.

Produces clean, machine-readable PDF documents using ReportLab.
Employs a single-column linear layout, standard fonts (Helvetica),
and clean text streams for maximum ATS text extraction fidelity.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer


class PdfResumeGenerator:
    """Generates standard ATS-compliant PDF resumes."""

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
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "TitleStyle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=HexColor("#0f172a"),
            alignment=1,  # Center
        )

        contact_style = ParagraphStyle(
            "ContactStyle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=HexColor("#475569"),
            alignment=1,  # Center
        )

        heading_style = ParagraphStyle(
            "HeadingStyle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=HexColor("#0f172a"),
            spaceBefore=10,
            spaceAfter=4,
        )

        body_style = ParagraphStyle(
            "BodyStyle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=HexColor("#1e293b"),
        )

        role_style = ParagraphStyle(
            "RoleStyle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=HexColor("#1e293b"),
        )

        bullet_style = ParagraphStyle(
            "BulletStyle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=HexColor("#334155"),
            leftIndent=15,
            firstLineIndent=-10,
            spaceAfter=3,
        )

        story = []

        # 1. Header
        story.append(Paragraph(candidate_name, title_style))
        story.append(Spacer(1, 4))

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
            story.append(Paragraph(" | ".join(contact_parts), contact_style))
            story.append(Spacer(1, 10))

        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#cbd5e1"), spaceAfter=8))

        # 2. Professional Summary
        if summary:
            story.append(Paragraph("PROFESSIONAL SUMMARY", heading_style))
            story.append(Paragraph(summary, body_style))
            story.append(Spacer(1, 6))

        # 3. Technical Skills
        if skills:
            story.append(Paragraph("TECHNICAL SKILLS", heading_style))
            skills_text = " • ".join(skills)
            story.append(Paragraph(skills_text, body_style))
            story.append(Spacer(1, 6))

        # 4. Work Experience
        if experiences:
            story.append(Paragraph("PROFESSIONAL EXPERIENCE", heading_style))
            for exp in experiences:
                company = exp.get("company", "")
                title = exp.get("title", "")
                start = exp.get("start_date") or ""
                end = "Present" if exp.get("is_current") else (exp.get("end_date") or "")
                date_str = f"({start} - {end})".strip(" ()")
                if date_str:
                    date_str = f" ({date_str})"

                role_header = f"<b>{title}</b> — {company} <font color='#64748b' size='8.5'><i>{date_str}</i></font>"
                story.append(Paragraph(role_header, role_style))
                story.append(Spacer(1, 2))

                for b in exp.get("bullets", []):
                    story.append(Paragraph(f"• {b}", bullet_style))
                story.append(Spacer(1, 4))

        # 5. Education
        if education:
            story.append(Paragraph("EDUCATION", heading_style))
            story.append(Paragraph(education, body_style))

        doc.build(story)
        buffer.seek(0)
        return buffer
