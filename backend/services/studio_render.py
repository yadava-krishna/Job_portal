"""Resume Studio rendering: six templates over one structured content model, to PDF (ReportLab, real selectable
text) and DOCX (python-docx). The live preview in the browser shows the actual PDF, so preview and export can't
drift apart. All user text is escaped before it reaches ReportLab's paragraph markup.
"""

from __future__ import annotations

import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, FrameBreak, HRFlowable, KeepTogether, ListFlowable, ListItem,
                                NextPageTemplate, PageTemplate, Paragraph, Spacer)

TEMPLATES: dict[str, dict[str, Any]] = {
    "ats_simple": {"name": "ATS Simple", "category": "ats", "ats_safe": True, "font": "Helvetica", "accent": "#000000",
                   "heading": "caps_rule", "columns": 1,
                   "order": ["header", "summary", "experience", "projects", "education", "skills", "certifications", "publications", "achievements"],
                   "description": "One column, standard headings, no colour. The safest choice for online application forms."},
    "modern_professional": {"name": "Modern Professional", "category": "modern", "ats_safe": False, "font": "Helvetica",
                            "accent": "#1f4e79", "heading": "accent", "columns": 2, "sidebar": ["skills", "education", "certifications"],
                            "order": ["header", "summary", "experience", "projects", "publications", "achievements"],
                            "description": "Two columns with a skills sidebar. Best for sending directly to people; use ATS Simple for portals."},
    "technical": {"name": "Technical", "category": "technical", "ats_safe": True, "font": "Helvetica", "accent": "#0b6e4f",
                  "heading": "accent", "columns": 1,
                  "order": ["header", "summary", "skills", "experience", "projects", "certifications", "education", "publications"],
                  "description": "Skills and projects up front for technical and analytics roles."},
    "finance": {"name": "Finance", "category": "finance", "ats_safe": True, "font": "Times-Roman", "accent": "#1b2a49",
                "heading": "caps_rule", "columns": 1,
                "order": ["header", "summary", "experience", "education", "certifications", "skills", "achievements"],
                "description": "Conservative serif layout; qualifications and certifications prominent."},
    "graduate": {"name": "Graduate", "category": "graduate", "ats_safe": True, "font": "Helvetica", "accent": "#5b2c83",
                 "heading": "accent", "columns": 1, "max_pages": 1,
                 "order": ["header", "summary", "education", "projects", "experience", "skills", "certifications", "achievements"],
                 "description": "Education and projects first, one page, for students and early-career candidates."},
    "international": {"name": "International", "category": "international", "ats_safe": True, "font": "Helvetica",
                      "accent": "#7a3e00", "heading": "caps_rule", "columns": 1, "page": "A4", "show_mobility": True,
                      "order": ["header", "summary", "experience", "education", "skills", "certifications", "projects", "publications"],
                      "description": "A4, with a line for work authorisation / relocation, for applications abroad."},
}
DENSITY = {"compact": 0.85, "normal": 1.0, "relaxed": 1.15}


def _bold(font: str) -> str:
    return {"Helvetica": "Helvetica-Bold", "Times-Roman": "Times-Bold"}.get(font, font)


def _styles(tpl: dict[str, Any], settings: dict[str, Any]) -> dict[str, ParagraphStyle]:
    size = float(min(12, max(9, settings.get("font_size", 10.5))))
    d = DENSITY.get(settings.get("density", "normal"), 1.0)
    font, bold, accent = tpl["font"], _bold(tpl["font"]), colors.HexColor(tpl["accent"])
    return {
        "name": ParagraphStyle("name", fontName=bold, fontSize=size + 8, leading=(size + 10), spaceAfter=2 * d),
        "headline": ParagraphStyle("headline", fontName=font, fontSize=size + 1, leading=size + 4, textColor=accent),
        "contact": ParagraphStyle("contact", fontName=font, fontSize=size - 1, leading=size + 2, spaceAfter=4 * d),
        "h": ParagraphStyle("h", fontName=bold, fontSize=size + 1, leading=size + 4, spaceBefore=8 * d, spaceAfter=2 * d,
                            textColor=accent if tpl["heading"] == "accent" else colors.black),
        "entry": ParagraphStyle("entry", fontName=bold, fontSize=size, leading=size + 3, spaceBefore=3 * d),
        "meta": ParagraphStyle("meta", fontName=font, fontSize=size - 1, leading=size + 2, textColor=colors.HexColor("#444444")),
        "body": ParagraphStyle("body", fontName=font, fontSize=size, leading=(size + 3) * d, alignment=TA_LEFT),
        "bullet": ParagraphStyle("bullet", fontName=font, fontSize=size, leading=(size + 3) * d),
    }


def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text or "")), style)


def _visible(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["type"]: s for s in doc["sections"] if s.get("visible", True)}


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _dates(c: dict[str, Any]) -> str:
    start, end = _s(c.get("start")), "Present" if c.get("current") else _s(c.get("end"))
    return f"{start} – {end}" if start and end else start or end


def _section_flow(section: dict[str, Any], st: dict[str, ParagraphStyle], tpl: dict[str, Any]) -> list:
    out: list = []
    heading = section.get("heading") or section["type"].title()
    out.append(_p(heading.upper() if tpl["heading"] == "caps_rule" else heading, st["h"]))
    if tpl["heading"] == "caps_rule":
        out.append(HRFlowable(width="100%", thickness=0.6, color=colors.black, spaceAfter=3))
    for block in section.get("blocks", []):
        if not block.get("visible", True):
            continue
        c = block.get("content") or {}
        if block["type"] == "text":
            out.append(_p(c.get("text"), st["body"]))
        elif block["type"] == "skill_group":
            label = c.get("label")
            items = ", ".join(_s(i) for i in c.get("items") or [] if _s(i))
            out.append(Paragraph((f"<b>{escape(label)}:</b> " if label else "") + escape(items), st["body"]))
        elif block["type"] == "entry":
            head = " — ".join(x for x in (_s(c.get("title")), _s(c.get("organization"))) if x)
            meta = " · ".join(x for x in (_dates(c), _s(c.get("location")), _s(c.get("link")), _s(c.get("detail"))) if x)
            parts = [_p(head, st["entry"])]
            if meta:
                parts.append(_p(meta, st["meta"]))
            bullets = [b for b in block.get("bullets", []) if b.get("approved", True) and (b.get("text") or "").strip()]
            if bullets:
                parts.append(ListFlowable([ListItem(_p(b["text"], st["bullet"]), leftIndent=10) for b in bullets],
                                          bulletType="bullet", start="•", leftIndent=10, bulletFontSize=8))
            out.append(KeepTogether(parts[:2]))
            out.extend(parts[2:])
    return out


def _header_flow(doc: dict[str, Any], st, tpl, settings) -> list:
    sec = _visible(doc).get("header")
    c = ((sec or {}).get("blocks") or [{}])[0].get("content", {}) if sec else {}
    out = [_p(c.get("name") or "Your name", st["name"])]
    if c.get("headline"):
        out.append(_p(c["headline"], st["headline"]))
    contact = " | ".join(_s(x) for x in (c.get("email"), c.get("phone"), c.get("location"), *(c.get("links") or [])) if _s(x))
    if contact:
        out.append(_p(contact, st["contact"]))
    if tpl.get("show_mobility") and settings.get("mobility_line"):
        out.append(_p(settings["mobility_line"], st["contact"]))
    out.append(Spacer(1, 2))
    return out


def render_pdf(doc: dict[str, Any], template_key: str, settings: dict[str, Any]) -> tuple[bytes, int]:
    tpl = TEMPLATES[template_key]
    st = _styles(tpl, settings)
    page = A4 if (settings.get("page_size") or tpl.get("page") or "A4") == "A4" else LETTER
    margin = 16 * mm * DENSITY.get(settings.get("density", "normal"), 1.0)
    buf = io.BytesIO()
    pdf = BaseDocTemplate(buf, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
                          title=_title(doc), author=_title(doc), subject="Resume", creator="JobPilot Resume Studio")
    w, h = page
    full = Frame(margin, margin, w - 2 * margin, h - 2 * margin, id="full")
    sections = _visible(doc)
    order = [t for t in tpl["order"] if t in sections and t != "header"] + \
            [t for t in sections if t not in tpl["order"] and t not in ("header",) and t not in tpl.get("sidebar", [])]
    story: list = []
    if tpl["columns"] == 2:
        head_h = 34 * mm
        side_w = (w - 2 * margin) * 0.32
        gap = 6 * mm
        header = Frame(margin, h - margin - head_h, w - 2 * margin, head_h, id="header")
        side = Frame(margin, margin, side_w, h - 2 * margin - head_h, id="side")
        main = Frame(margin + side_w + gap, margin, w - 2 * margin - side_w - gap, h - 2 * margin - head_h, id="main")
        pdf.addPageTemplates([PageTemplate(id="first", frames=[header, side, main]), PageTemplate(id="later", frames=[full])])
        story += [NextPageTemplate("later"), *_header_flow(doc, st, tpl, settings), FrameBreak()]
        for t in tpl["sidebar"]:
            if t in sections:
                story += _section_flow(sections[t], st, tpl)
        story.append(FrameBreak())
    else:
        pdf.addPageTemplates([PageTemplate(id="full", frames=[full])])
        story += _header_flow(doc, st, tpl, settings)
    for t in order:
        story += _section_flow(sections[t], st, tpl)
    pages = {"n": 0}

    def count(canvas, _doc):
        pages["n"] = canvas.getPageNumber()

    for pt in pdf.pageTemplates:
        pt.onPageEnd = count
    pdf.build(story)
    return buf.getvalue(), pages["n"]


def _title(doc: dict[str, Any]) -> str:
    sec = next((s for s in doc["sections"] if s["type"] == "header"), None)
    name = ((sec or {}).get("blocks") or [{}])[0].get("content", {}).get("name") if sec else None
    return f"{name} — Resume" if name else "Resume"


def render_docx(doc: dict[str, Any], template_key: str, settings: dict[str, Any]) -> tuple[bytes, str | None]:
    """DOCX export. Two-column templates fall back to one column in Word (stated in the returned note)."""
    from docx import Document
    from docx.shared import Pt, RGBColor

    tpl = TEMPLATES[template_key]
    d = Document()
    style = d.styles["Normal"]
    style.font.name = "Times New Roman" if tpl["font"].startswith("Times") else "Calibri"
    style.font.size = Pt(float(min(12, max(9, settings.get("font_size", 10.5)))))
    sections = _visible(doc)
    hc = ((sections.get("header") or {}).get("blocks") or [{}])[0].get("content", {}) if sections.get("header") else {}
    d.add_heading(hc.get("name") or "Your name", level=0)
    if hc.get("headline"):
        d.add_paragraph(hc["headline"])
    contact = " | ".join(_s(x) for x in (hc.get("email"), hc.get("phone"), hc.get("location"), *(hc.get("links") or [])) if _s(x))
    if contact:
        d.add_paragraph(contact)
    if tpl.get("show_mobility") and settings.get("mobility_line"):
        d.add_paragraph(settings["mobility_line"])
    order = [t for t in tpl["order"] if t in sections and t != "header"] + [t for t in tpl.get("sidebar", []) if t in sections]
    order += [t for t in sections if t not in order and t != "header"]
    accent = RGBColor.from_string(tpl["accent"].lstrip("#"))
    for t in order:
        s = sections[t]
        hp = d.add_heading(s.get("heading") or t.title(), level=1)
        for run in hp.runs:
            run.font.color.rgb = accent
        for block in s.get("blocks", []):
            if not block.get("visible", True):
                continue
            c = block.get("content") or {}
            if block["type"] == "text":
                d.add_paragraph(c.get("text") or "")
            elif block["type"] == "skill_group":
                p = d.add_paragraph()
                if c.get("label"):
                    p.add_run(f"{c['label']}: ").bold = True
                p.add_run(", ".join(_s(i) for i in c.get("items") or [] if _s(i)))
            elif block["type"] == "entry":
                p = d.add_paragraph()
                p.add_run(" — ".join(x for x in (_s(c.get("title")), _s(c.get("organization"))) if x)).bold = True
                meta = " · ".join(x for x in (_dates(c), _s(c.get("location")), _s(c.get("link")), _s(c.get("detail"))) if x)
                if meta:
                    d.add_paragraph(meta)
                for b in block.get("bullets", []):
                    if b.get("approved", True) and (b.get("text") or "").strip():
                        d.add_paragraph(b["text"], style="List Bullet")
    buf = io.BytesIO()
    d.save(buf)
    note = "Word export uses one column; the sidebar sections follow the main sections." if tpl["columns"] == 2 else None
    return buf.getvalue(), note
