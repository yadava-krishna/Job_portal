"""Builds docs/JobPilot_User_Guide.pdf and .docx from USER_GUIDE.md (screenshots in docs/guide/).

    PYTHONPATH=<dir with the `markdown` package> .venv/bin/python design-lab/preview/build_guide_docs.py

PDF: Markdown -> styled HTML -> printed by Chromium (Playwright). DOCX: a small converter for the Markdown this guide
uses (headings, paragraphs, lists, tables, quotes, images, bold, code, links) with python-docx.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import markdown
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "USER_GUIDE.md"
OUT_PDF = ROOT / "docs" / "JobPilot_User_Guide.pdf"
OUT_DOCX = ROOT / "docs" / "JobPilot_User_Guide.docx"
INK, ACCENT = RGBColor(0x1F, 0x1B, 0x5C), RGBColor(0x6D, 0x3C, 0xE8)

CSS = """
@page { size: A4; margin: 16mm 15mm 18mm; }
:root { --ink:#1f1b5c; --text:#2b2a33; --muted:#5d5b6b; --accent:#6d3ce8; --blue:#2f55e4; --line:#e4e2f0; --soft:#f5f3fe; }
body { font-family: "Inter", "Segoe UI", system-ui, sans-serif; color: var(--text); font-size: 10.5pt; line-height: 1.55; }
h1 { color: var(--ink); font-size: 26pt; letter-spacing: -0.02em; margin: 0 0 6pt; }
h2 { color: var(--ink); font-size: 17pt; margin: 22pt 0 6pt; padding-top: 6pt; border-top: 2px solid var(--line); break-after: avoid; }
h3 { color: var(--accent); font-size: 12.5pt; margin: 14pt 0 4pt; break-after: avoid; }
a { color: var(--blue); text-decoration: none; }
strong { color: var(--ink); }
code { font-family: "JetBrains Mono", Consolas, monospace; font-size: 9pt; background: var(--soft); padding: 1px 4px; border-radius: 4px; }
blockquote { margin: 10pt 0; padding: 8pt 12pt; background: var(--soft); border-left: 3px solid var(--accent); border-radius: 6px; color: var(--muted); }
blockquote p { margin: 2pt 0; }
img { display: block; width: 100%; border: 1px solid var(--line); border-radius: 8px; margin: 8pt 0 10pt; box-shadow: 0 2px 8px rgba(31,27,92,.08); break-inside: avoid; }
img[src*="phone"] { width: 42%; margin-left: auto; margin-right: auto; }
p:has(> img) { break-inside: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt; font-size: 9.5pt; break-inside: avoid; }
th { background: var(--soft); color: var(--ink); text-align: left; }
th, td { border: 1px solid var(--line); padding: 5pt 7pt; vertical-align: top; }
ul, ol { padding-left: 18pt; } li { margin: 2pt 0; }
hr { border: 0; height: 0; margin: 4pt 0; }
"""


def for_python_markdown(md_text: str) -> str:
    """GitHub-style lists -> what Python-Markdown expects: a blank line before a list, and 4-space nesting."""
    out: list[str] = []
    item = re.compile(r"^\s*([-*]|\d+\.)\s")
    for line in md_text.splitlines():
        n = len(line) - len(line.lstrip(" "))
        if n and line.strip():
            line = " " * (4 * -(-n // 3)) + line.lstrip(" ")
        prev = out[-1] if out else ""
        if item.match(line) and prev.strip() and not item.match(prev) and not prev.startswith(" "):
            out.append("")
        out.append(line)
    return "\n".join(out)


def build_pdf(md_text: str) -> None:
    body = markdown.markdown(for_python_markdown(md_text), extensions=["tables", "sane_lists", "attr_list"])
    html = f"<!doctype html><html><head><meta charset='utf-8'><title>JobPilot user guide</title><style>{CSS}</style></head><body>{body}</body></html>"
    tmp = ROOT / "_guide_print.html"  # at the root so docs/guide/... image paths resolve
    tmp.write_text(html, encoding="utf-8")

    async def go() -> None:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            page = await b.new_page()
            await page.goto(tmp.as_uri())
            await page.wait_for_load_state("networkidle")
            await page.pdf(path=str(OUT_PDF), format="A4", print_background=True, display_header_footer=True,
                           header_template="<span></span>",
                           footer_template="<div style='font-size:8px;color:#8a88a0;width:100%;text-align:center'>JobPilot user guide · "
                                           "<span class='pageNumber'></span> / <span class='totalPages'></span></div>",
                           margin={"top": "16mm", "bottom": "18mm", "left": "15mm", "right": "15mm"})
            await b.close()
    try:
        asyncio.run(go())
    finally:
        tmp.unlink(missing_ok=True)


# ---- DOCX ------------------------------------------------------------------------------------------------------------
INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*]+\*)")


def add_inline(par, text: str, bold: bool = False) -> None:
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            r = par.add_run(part[2:-2]); r.bold = True; r.font.color.rgb = INK
        elif part.startswith("`") and part.endswith("`"):
            r = par.add_run(part[1:-1]); r.font.name = "Consolas"; r.font.size = Pt(9.5)
        elif part.startswith("[") and "](" in part:
            label = part[1:part.index("](")]
            r = par.add_run(label); r.font.color.rgb = RGBColor(0x2F, 0x55, 0xE4); r.bold = bold
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            r = par.add_run(part[1:-1]); r.italic = True; r.bold = bold
        else:
            r = par.add_run(part); r.bold = bold


def shade(cell, hex_fill: str) -> None:
    tc = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_fill)
    tc.append(shd)


def build_docx(md_text: str) -> None:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    for side in ("left_margin", "right_margin"):
        setattr(sec, side, Cm(1.8))
    sec.top_margin = sec.bottom_margin = Cm(1.6)
    st = doc.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(10.5)
    for name, size, color in (("Title", 26, INK), ("Heading 1", 18, INK), ("Heading 2", 13, ACCENT)):
        s = doc.styles[name]; s.font.name = "Calibri"; s.font.size = Pt(size); s.font.color.rgb = color; s.font.bold = True
    width = sec.page_width - sec.left_margin - sec.right_margin

    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s or s == "---":
            i += 1; continue
        if s.startswith("# "):
            add_inline(doc.add_paragraph(style="Title"), s[2:]); i += 1; continue
        if s.startswith("## "):
            add_inline(doc.add_heading(level=1), s[3:]); i += 1; continue
        if s.startswith("### "):
            add_inline(doc.add_heading(level=2), s[4:]); i += 1; continue
        m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", s)
        if m:
            img = ROOT / m.group(2)
            w = width * 0.42 if "phone" in img.name else width
            doc.add_picture(str(img), width=int(w))
            cap = doc.add_paragraph(m.group(1)); cap.runs[0].italic = True; cap.runs[0].font.size = Pt(8.5)
            cap.runs[0].font.color.rgb = RGBColor(0x8A, 0x88, 0xA0)
            i += 1; continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            t = doc.add_table(rows=len(rows), cols=len(rows[0])); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
            for r, cells in enumerate(rows):
                for c, txt in enumerate(cells):
                    cell = t.cell(r, c); cell.text = ""
                    add_inline(cell.paragraphs[0], txt, bold=(r == 0))
                    if r == 0:
                        shade(cell, "F1EEFD")
            doc.add_paragraph()
            continue
        if s.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip()); i += 1
            p = doc.add_paragraph(); p.paragraph_format.left_indent = Cm(0.6)
            add_inline(p, " ".join(b for b in buf if b))
            for r in p.runs:
                r.font.color.rgb = RGBColor(0x5D, 0x5B, 0x6B)
            continue
        lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if lm:
            indent = len(lm.group(1)) // 2
            numbered = lm.group(2)[0].isdigit()
            text = lm.group(3)
            i += 1
            # continuation lines (indented, not a new list item, not blank)
            while i < len(lines) and lines[i].strip() and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]) \
                    and lines[i].startswith(" ") and not lines[i].strip().startswith(("|", "!", ">")):
                text += " " + lines[i].strip(); i += 1
            style = ("List Number" if numbered else "List Bullet") + (f" {min(indent + 1, 3)}" if indent else "")
            p = doc.add_paragraph(style=style)
            add_inline(p, text)
            continue
        buf = [s]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^\s*([-*]|\d+\.|#|\||!\[|>)", lines[i]) and lines[i].strip() != "---":
            buf.append(lines[i].strip()); i += 1
        add_inline(doc.add_paragraph(), " ".join(buf))
    doc.core_properties.title = "JobPilot user guide"
    doc.save(str(OUT_DOCX))


if __name__ == "__main__":
    text = SRC.read_text(encoding="utf-8")
    build_pdf(text)
    build_docx(text)
    print(OUT_PDF.relative_to(ROOT), OUT_DOCX.relative_to(ROOT))
