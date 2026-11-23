"""Resume Studio rendering (v2): one structured content model, one layout specification, two outputs.

* PDF: semantic HTML + print CSS rendered by WeasyPrint. Real, selectable text with embedded (subset) fonts,
  clickable e-mail/phone/web links, document metadata, and CSS fragmentation rules for deterministic pagination:
  headings never end a page, an entry's title/date lines stay with its first bullet, short entries are not split,
  bullets are not split, and long entries may continue on the next page instead of leaving a hole.
* DOCX: python-docx built from the same layout spec (fonts, sizes, margins, spacing, accent, section order,
  right-aligned dates via a tab stop, keep-with-next on headings), so both files carry the same content.
* layout_report(): page count, how full the last page is, and plain warnings. Nothing is ever removed or shrunk
  automatically to fit; the user decides.
All user text is HTML-escaped before it reaches the renderer. No AI, no network access (WeasyPrint is given no base
URL and a fetcher that refuses everything).
"""

from __future__ import annotations

import html
import io
import re
from typing import Any

# ---------------------------------------------------------------------------------------------------------------
# Fonts: CSS stack for the PDF, the font name written into the DOCX, and whether it is safe for ATS templates.
# All are open fonts installed in the backend image (fonts-liberation, fonts-lato, fonts-urw-base35, fonts-dejavu).
FONTS: dict[str, dict[str, Any]] = {
    "liberation_sans": {"label": "Arial-style sans (Liberation Sans)", "css": "'Liberation Sans', Arial, Helvetica, 'DejaVu Sans', sans-serif", "docx": "Arial", "ats": True},
    "lato": {"label": "Lato", "css": "Lato, 'Liberation Sans', 'DejaVu Sans', sans-serif", "docx": "Calibri", "ats": True},
    "liberation_serif": {"label": "Times-style serif (Liberation Serif)", "css": "'Liberation Serif', 'Times New Roman', 'DejaVu Serif', serif", "docx": "Times New Roman", "ats": True},
    "palatino": {"label": "Palatino-style serif (P052)", "css": "P052, 'Palatino Linotype', 'Book Antiqua', 'Liberation Serif', serif", "docx": "Palatino Linotype", "ats": True},
    "dejavu_sans": {"label": "DejaVu Sans (wide Unicode coverage)", "css": "'DejaVu Sans', 'Liberation Sans', sans-serif", "docx": "Arial", "ats": True},
}

HEADING_STYLES = ("caps_rule", "accent", "underline", "plain", "label_left")

TEMPLATES: dict[str, dict[str, Any]] = {
    "ats_simple": {
        "name": "Classic ATS", "category": "ats", "ats_safe": True, "columns": 1, "font": "liberation_sans", "accent": "#111827",
        "heading": "caps_rule", "name_align": "left", "fonts": ["liberation_sans", "liberation_serif", "lato", "dejavu_sans"],
        "order": ["header", "summary", "experience", "projects", "education", "skills", "certifications", "publications", "achievements", "custom"],
        "description": "One column, standard headings, black text. The safest choice for online application forms.",
    },
    "modern_professional": {
        "name": "Modern Professional", "category": "modern", "ats_safe": False, "columns": 1, "font": "lato", "accent": "#1d4ed8",
        "heading": "label_left", "name_align": "left", "fonts": ["lato", "liberation_sans", "dejavu_sans"],
        "order": ["header", "summary", "experience", "projects", "skills", "education", "certifications", "publications", "achievements", "custom"],
        "description": "Section names in a left margin and a blue accent. Made for reading by people; for online forms prefer Classic ATS.",
    },
    "technical": {
        "name": "Technical Engineer", "category": "technical", "ats_safe": True, "columns": 1, "font": "liberation_sans", "accent": "#0f766e",
        "heading": "accent", "name_align": "left", "fonts": ["liberation_sans", "lato", "dejavu_sans"], "skills_grid": True,
        "order": ["header", "summary", "skills", "experience", "projects", "certifications", "education", "publications", "achievements", "custom"],
        "description": "Skills and projects up front, grouped skill rows. For engineering, data and analytics roles.",
    },
    "finance": {
        "name": "Experienced Professional", "category": "experienced", "ats_safe": True, "columns": 1, "font": "liberation_serif", "accent": "#1e3a5f",
        "heading": "caps_rule", "name_align": "left", "fonts": ["liberation_serif", "palatino", "liberation_sans"],
        "order": ["header", "summary", "experience", "achievements", "education", "certifications", "skills", "projects", "publications", "custom"],
        "description": "Conservative serif layout for long careers: experience first, then achievements and qualifications.",
    },
    "graduate": {
        "name": "Fresher / Graduate", "category": "graduate", "ats_safe": True, "columns": 1, "font": "lato", "accent": "#6d28d9",
        "heading": "accent", "name_align": "left", "max_pages": 1, "fonts": ["lato", "liberation_sans", "dejavu_sans"],
        "order": ["header", "summary", "education", "projects", "experience", "skills", "certifications", "achievements", "publications", "custom"],
        "description": "Education and projects first, aimed at one page. For students and early-career candidates.",
    },
    "executive": {
        "name": "Executive", "category": "executive", "ats_safe": True, "columns": 1, "font": "palatino", "accent": "#7f1d1d",
        "heading": "underline", "name_align": "center", "fonts": ["palatino", "liberation_serif", "lato"],
        "order": ["header", "summary", "achievements", "experience", "education", "certifications", "skills", "projects", "publications", "custom"],
        "description": "Centred name, refined serif and selected achievements before experience. For senior leadership roles.",
    },
    "international": {
        "name": "International (A4)", "category": "international", "ats_safe": True, "columns": 1, "font": "liberation_sans", "accent": "#7c2d12",
        "heading": "caps_rule", "name_align": "left", "page": "A4", "show_mobility": True, "fonts": ["liberation_sans", "lato", "liberation_serif"],
        "order": ["header", "summary", "experience", "education", "skills", "certifications", "projects", "publications", "achievements", "custom"],
        "description": "A4 with a line for work authorisation and relocation, for applications abroad.",
    },
}

SPACING = {"compact": 0.75, "normal": 1.0, "relaxed": 1.25}
DATE_FORMATS = ("MMM YYYY", "MM/YYYY", "YYYY")
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MONTH_IDX = {m.lower(): i for i, m in enumerate(_MONTHS)} | {
    "january": 0, "february": 1, "march": 2, "april": 3, "june": 5, "july": 6, "august": 7, "september": 8, "sept": 8,
    "october": 9, "november": 10, "december": 11}


# ---------------------------------------------------------------------------------------------------------------
# Settings: validated with guard rails. Returns (settings, notes about anything that was adjusted).

def _luminance(hexcolor: str) -> float:
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast_on_white(hexcolor: str) -> float:
    return 1.05 / (_luminance(hexcolor) + 0.05)


def normalize_settings(template_key: str, raw: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    tpl = TEMPLATES[template_key]
    raw = dict(raw or {})
    notes: list[str] = []

    def num(key, default, lo, hi):
        try:
            v = float(raw.get(key, default))
        except (TypeError, ValueError):
            v = default
        return round(min(hi, max(lo, v)), 2)

    min_size = 9.5 if tpl["ats_safe"] else 9.0
    font_size = num("font_size", 10.5, min_size, 12)
    if raw.get("font_size") is not None and float(raw.get("font_size") or 0) < min_size:
        notes.append(f"Text size kept at {min_size} pt or larger so the resume stays readable.")
    font = raw.get("font_family") if raw.get("font_family") in tpl["fonts"] else tpl["font"]
    if raw.get("font_family") and raw.get("font_family") not in tpl["fonts"]:
        notes.append(f"{tpl['name']} uses one of: {', '.join(FONTS[f]['label'] for f in tpl['fonts'])}.")
    accent = str(raw.get("accent") or tpl["accent"])
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        accent = tpl["accent"]
    if contrast_on_white(accent) < 4.5:
        notes.append("That colour is too light to read on white; the template colour is used instead.")
        accent = tpl["accent"]
    heading = raw.get("heading_style") if raw.get("heading_style") in HEADING_STYLES else tpl["heading"]
    if heading == "label_left" and tpl["ats_safe"]:
        heading = tpl["heading"]  # side labels can scramble the reading order for applicant-tracking systems
    spacing = raw.get("section_spacing")
    if spacing is None:
        spacing = SPACING.get(raw.get("density", "normal"), 1.0)
    try:
        spacing = round(min(1.6, max(0.6, float(spacing))), 2)
    except (TypeError, ValueError):
        spacing = 1.0
    page = raw.get("page_size") or tpl.get("page") or "A4"
    page = "LETTER" if str(page).upper() == "LETTER" else "A4"
    out = {
        "font_family": font, "font_size": font_size, "line_height": num("line_height", 1.3, 1.1, 1.6),
        "margin_mm": num("margin_mm", 16, 10, 25), "section_spacing": spacing, "heading_style": heading, "accent": accent.lower(),
        "page_size": page, "date_format": raw.get("date_format") if raw.get("date_format") in DATE_FORMATS else "MMM YYYY",
        "mobility_line": " ".join(str(raw.get("mobility_line") or "").split())[:200],
        "density": raw.get("density") if raw.get("density") in SPACING else "normal",
    }
    return out, notes


# ---------------------------------------------------------------------------------------------------------------
# Content model -> render model (shared by PDF and DOCX).

def _s(v: Any, *, bullet: bool = False) -> str:
    """Printable text: normalised (core.textclean: invisible characters, odd spaces, ligatures, Symbol-font bullets)
    and whitespace collapsed. Unreadable characters (U+FFFD, other private-use code points) are kept: the checker
    reports where they are rather than the renderer silently guessing."""
    from core.textclean import clean

    return "" if v is None else " ".join(clean(str(v), bullet=bullet).split())


def format_date(value: Any, fmt: str) -> str:
    """Normalise a written date to the chosen format. Text that is not a recognisable date is kept as written."""
    t = _s(value)
    if not t:
        return ""
    if re.fullmatch(r"(?i)present|current|now|till date|to date|ongoing", t):
        return "Present"
    m = re.fullmatch(r"([A-Za-z]{3,9})\.?,?\s*'?(\d{2}|\d{4})", t)
    if m and m.group(1).lower() in _MONTH_IDX:
        mon, year = _MONTH_IDX[m.group(1).lower()], m.group(2)
    else:
        m = re.fullmatch(r"(\d{1,2})[/.-](\d{4})|(\d{4})[/.-](\d{1,2})", t)
        if m and 1 <= int(m.group(1) or m.group(4)) <= 12:
            mon, year = int(m.group(1) or m.group(4)) - 1, m.group(2) or m.group(3)
        elif re.fullmatch(r"\d{4}", t):
            return t
        else:
            return t
    if len(year) == 2:
        year = ("20" if int(year) <= 40 else "19") + year
    if fmt == "YYYY":
        return year
    if fmt == "MM/YYYY":
        return f"{mon + 1:02d}/{year}"
    return f"{_MONTHS[mon]} {year}"


def _dates(c: dict[str, Any], fmt: str) -> str:
    start = format_date(c.get("start"), fmt)
    end = "Present" if c.get("current") else format_date(c.get("end"), fmt)
    return f"{start} – {end}" if start and end else start or end


def _url_label(u: str) -> str:
    return re.sub(r"^(https?://)?(www\.)?", "", u).rstrip("/")


def _href(u: str) -> str | None:
    u = u.strip()
    if re.match(r"^https?://", u):
        return u
    if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", u, re.I):
        return "https://" + u
    return None


def render_model(doc: dict[str, Any], template_key: str, settings: dict[str, Any]) -> dict[str, Any]:
    tpl = TEMPLATES[template_key]
    fmt = settings["date_format"]
    visible = {s["type"]: s for s in doc.get("sections", []) if s.get("visible", True)}
    hc = {}
    if visible.get("header"):
        hc = ((visible["header"].get("blocks") or [{}])[0] or {}).get("content", {}) or {}
    contact = []
    if _s(hc.get("email")):
        contact.append({"text": _s(hc["email"]), "href": "mailto:" + _s(hc["email"])})
    if _s(hc.get("phone")):
        contact.append({"text": _s(hc["phone"]), "href": "tel:" + re.sub(r"[^\d+]", "", _s(hc["phone"]))})
    if _s(hc.get("location")):
        contact.append({"text": _s(hc["location"]), "href": None})
    for link in hc.get("links") or []:
        if _s(link):
            contact.append({"text": _url_label(_s(link)), "href": _href(_s(link))})
    order = [t for t in tpl["order"] if t in visible and t != "header"]
    order += [t for t in visible if t not in order and t != "header"]
    sections = []
    for t in order:
        sec = visible[t]
        items = []
        for b in sec.get("blocks") or []:
            if not b.get("visible", True):
                continue
            c = b.get("content") or {}
            if b["type"] == "text":
                paras = [p for p in re.split(r"\n\s*\n", str(c.get("text") or "")) if p.strip()]
                if paras:
                    items.append({"kind": "text", "paragraphs": [_s(p) for p in paras]})
            elif b["type"] == "skill_group":
                skills = [_s(i) for i in c.get("items") or [] if _s(i)]
                if skills:
                    items.append({"kind": "skills", "label": _s(c.get("label")), "items": skills})
            elif b["type"] == "entry":
                bullets = [_s(u.get("text"), bullet=True) for u in b.get("bullets") or [] if u.get("approved", True) and _s(u.get("text"), bullet=True)]
                title, org = _s(c.get("title")), _s(c.get("organization"))
                if not (title or org or bullets):
                    continue
                link = _s(c.get("link"))
                items.append({"kind": "entry", "title": title, "org": org, "dates": _dates(c, fmt), "location": _s(c.get("location")),
                              "detail": _s(c.get("detail")), "link": link, "link_href": _href(link) if link else None, "bullets": bullets})
        if items:
            sections.append({"type": t, "heading": _s(sec.get("heading")) or t.title(), "items": items})
    mobility = settings.get("mobility_line") if tpl.get("show_mobility") else ""
    return {"name": _s(hc.get("name")) or "Your name", "headline": _s(hc.get("headline")), "contact": contact,
            "mobility": mobility, "sections": sections}


# ---------------------------------------------------------------------------------------------------------------
# HTML / CSS

def _e(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _link(text: str, href: str | None) -> str:
    return f'<a href="{_e(href)}">{_e(text)}</a>' if href else _e(text)


def _css(tpl: dict[str, Any], st: dict[str, Any], page_name: str) -> str:
    font = FONTS[st["font_family"]]["css"]
    size, lh, sp, m = st["font_size"], st["line_height"], st["section_spacing"], st["margin_mm"]
    accent = st["accent"]
    head_color = accent if st["heading_style"] in ("accent", "label_left", "underline") else "#111827"
    name_color = accent if tpl["category"] in ("modern", "graduate", "technical") else "#111827"
    page = "A4" if st["page_size"] == "A4" else "letter"
    heading_css = {
        "caps_rule": "text-transform: uppercase; letter-spacing: .06em; border-bottom: .8pt solid #111827; padding-bottom: 1.5pt;",
        "accent": f"color: {head_color};",
        "underline": f"color: {head_color}; border-bottom: .6pt solid {head_color}; padding-bottom: 1.5pt; text-transform: uppercase; letter-spacing: .08em; font-size: {size:.1f}pt;",
        "plain": "",
        "label_left": f"color: {head_color}; text-transform: uppercase; letter-spacing: .05em; font-size: {size - 1:.1f}pt;",
    }[st["heading_style"]]
    label_left = st["heading_style"] == "label_left"
    gutter = 34 if label_left else 0
    return f"""
@page {{ size: {page}; margin: {m}mm {m}mm {m}mm {m}mm;
  @bottom-right {{ content: "{_e(page_name)} · page " counter(page) " of " counter(pages); font: {max(7, size - 3):.1f}pt {font}; color: #6b7280; }} }}
@page :first {{ @bottom-right {{ content: none; }} }}
html {{ font-family: {font}; font-size: {size}pt; line-height: {lh}; color: #111827; }}
body {{ margin: 0; }}
a {{ color: inherit; text-decoration: none; }}
.hdr {{ text-align: {tpl['name_align']}; margin-bottom: {8 * sp:.1f}pt; {'border-bottom: 1.2pt solid ' + accent + '; padding-bottom: 6pt;' if tpl['category'] == 'modern' else ''} }}
.name {{ font-size: {size + 11:.1f}pt; line-height: 1.1; font-weight: 700; margin: 0; color: {name_color}; letter-spacing: {'.04em' if tpl['category'] == 'executive' else '0'}; }}
.headline {{ font-size: {size + 1:.1f}pt; color: {accent if tpl['category'] != 'ats' else '#374151'}; margin-top: 2pt; }}
.contact {{ font-size: {size - 0.5:.1f}pt; color: #374151; margin-top: 3pt; overflow-wrap: anywhere; }}
.contact .sep {{ color: #9ca3af; padding: 0 4pt; }}
.mobility {{ font-size: {size - 0.5:.1f}pt; color: #374151; margin-top: 2pt; }}
.sec {{ margin-top: {9 * sp:.1f}pt; position: relative; {f'padding-left: {gutter}mm;' if label_left else ''} }}
.sec > h2 {{ font-size: {size + 1:.1f}pt; font-weight: 700; margin: 0 0 {4 * sp:.1f}pt 0; break-after: avoid; {heading_css}
  {f'position: absolute; left: 0; top: 1pt; width: {gutter - 4}mm; margin: 0;' if label_left else ''} }}
.entry {{ margin-top: {5 * sp:.1f}pt; }}
.entry:first-of-type {{ margin-top: 0; }}
.entry.short {{ break-inside: avoid; }}
.eh {{ break-inside: avoid; }}
.eh.keep {{ break-after: avoid; }}
.row {{ display: flex; justify-content: space-between; align-items: baseline; gap: 10pt; }}
.row > .l {{ flex: 1 1 auto; min-width: 0; }}
.row > .r {{ flex: 0 0 auto; white-space: nowrap; text-align: right; color: #374151; font-size: {size - 0.5:.1f}pt; }}
.t {{ font-weight: 700; }}
.o {{ font-style: italic; color: #1f2937; }}
.meta {{ font-size: {size - 0.5:.1f}pt; color: #4b5563; overflow-wrap: anywhere; }}
ul {{ margin: {2 * sp:.1f}pt 0 0 0; padding-left: 0; list-style: none; }}
/* The bullet is inline text with a hanging indent (not a list marker): text extraction then reads "• Built …" in
   order, instead of the markers coming out as stray lines at the end of the page. */
li {{ margin: 0 0 {1.5 * sp:.1f}pt 0; padding-left: 9pt; text-indent: -7pt; break-inside: avoid; orphans: 2; widows: 2; }}
li::before {{ content: "• "; white-space: pre; color: {accent if tpl['category'] != 'ats' else '#111827'}; }}
p {{ margin: 0 0 {3 * sp:.1f}pt 0; orphans: 2; widows: 2; }}
.skills {{ margin: 0 0 {2 * sp:.1f}pt 0; }}
.skills .k {{ font-weight: 700; }}
.skills.grid {{ display: grid; grid-template-columns: 34mm 1fr; column-gap: 6pt; }}
"""


def build_html(doc: dict[str, Any], template_key: str, settings: dict[str, Any]) -> str:
    tpl = TEMPLATES[template_key]
    st, _ = normalize_settings(template_key, settings)
    m = render_model(doc, template_key, st)
    parts = [f'<header class="hdr"><h1 class="name">{_e(m["name"])}</h1>']
    if m["headline"]:
        parts.append(f'<div class="headline">{_e(m["headline"])}</div>')
    if m["contact"]:
        sep = '<span class="sep">|</span>' if tpl["category"] == "ats" else '<span class="sep">·</span>'
        parts.append('<div class="contact">' + sep.join(f"<span>{_link(c['text'], c['href'])}</span>" for c in m["contact"]) + "</div>")
    if m["mobility"]:
        parts.append(f'<div class="mobility">{_e(m["mobility"])}</div>')
    parts.append("</header>")
    for sec in m["sections"]:
        parts.append(f'<section class="sec sec-{_e(sec["type"])}"><h2>{_e(sec["heading"])}</h2>')
        for it in sec["items"]:
            if it["kind"] == "text":
                parts.extend(f"<p>{_e(p)}</p>" for p in it["paragraphs"])
            elif it["kind"] == "skills":
                grid = tpl.get("skills_grid") and it["label"]
                label = f'<span class="k">{_e(it["label"])}{"" if grid else ":"}</span> ' if it["label"] else ""
                items = _e(", ".join(it["items"]))
                parts.append(f'<div class="skills{" grid" if grid else ""}">{label}<span>{items}</span></div>' if grid
                             else f'<div class="skills">{label}{items}</div>')
            else:
                short = len(it["bullets"]) <= 3
                head = []
                if it["title"] or it["dates"]:
                    head.append(f'<div class="row"><span class="l t">{_e(it["title"] or it["org"])}</span><span class="r">{_e(it["dates"])}</span></div>')
                if it["title"] and (it["org"] or it["location"]):
                    head.append(f'<div class="row"><span class="l o">{_e(it["org"])}</span><span class="r">{_e(it["location"])}</span></div>')
                meta = " · ".join(x for x in (it["detail"],) if x)
                if it["link"]:
                    meta = (meta + " · " if meta else "") + _link(_url_label(it["link"]), it["link_href"])
                    head.append(f'<div class="meta">{meta}</div>')
                elif meta:
                    head.append(f'<div class="meta">{_e(meta)}</div>')
                bullets = "".join(f"<li>{_e(b)}</li>" for b in it["bullets"])
                parts.append(f'<div class="entry{" short" if short else ""}">' + (f'<div class="eh{" keep" if it["bullets"] else ""}">{"".join(head)}</div>' if head else "")
                             + (f"<ul>{bullets}</ul>" if bullets else "") + "</div>")
        parts.append("</section>")
    title = f"{m['name']} – Resume" if m["name"] != "Your name" else "Resume"
    meta = (f'<meta name="author" content="{_e(m["name"])}"><meta name="description" content="Resume">'
            f'<meta name="generator" content="JobPilot Resume Studio">')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{_e(title)}</title>{meta}'
            f"<style>{_css(tpl, st, m['name'])}</style></head><body>{''.join(parts)}</body></html>")


def _no_fetch(url: str, *a, **kw):
    raise ValueError("JobPilot resumes never load external resources")


def _render(doc: dict[str, Any], template_key: str, settings: dict[str, Any]):
    from weasyprint import HTML

    return HTML(string=build_html(doc, template_key, settings), url_fetcher=_no_fetch).render()


def _fill(document) -> list[float]:
    """For each page, how far down the content reaches (0..1 of the printable height)."""
    from weasyprint.formatting_structure.boxes import LineBox, MarginBox

    out = []
    for page in document.pages:
        box = page._page_box
        top = box.content_box_y()
        height = box.height
        bottom = top
        for child in box.children:
            if isinstance(child, MarginBox):  # the "page X of Y" footer is not content
                continue
            for b in child.descendants():
                if isinstance(b, LineBox):
                    bottom = max(bottom, b.position_y + b.height)
        out.append(round(max(0.0, min(1.0, (bottom - top) / height)) if height else 0.0, 3))
    return out


def render_pdf(doc: dict[str, Any], template_key: str, settings: dict[str, Any]) -> tuple[bytes, int]:
    rendered = _render(doc, template_key, settings)
    return rendered.write_pdf(), len(rendered.pages)


def layout_report(doc: dict[str, Any], template_key: str, settings: dict[str, Any], *, suggest: bool = True) -> dict[str, Any]:
    """Pages, fill of each page, and warnings. Suggests (never applies) settings that would save a nearly empty page."""
    tpl = TEMPLATES[template_key]
    st, notes = normalize_settings(template_key, settings)
    rendered = _render(doc, template_key, st)
    fills = _fill(rendered)
    pages = len(fills)
    warnings: list[dict[str, str]] = [{"level": "info", "message": n} for n in notes]
    target = tpl.get("max_pages", 2)
    if pages > target:
        warnings.append({"level": "warning", "message": f"{tpl['name']} is designed for {target} page{'s' if target > 1 else ''}; this resume is {pages}. "
                                                         "Shorten older roles or remove less relevant bullets (JobPilot never removes content for you)."})
    elif pages >= 3:
        warnings.append({"level": "warning", "message": f"{pages} pages is long for most roles; two is the usual maximum."})
    if pages > 1 and fills[-1] < 0.2:
        warnings.append({"level": "warning", "message": f"The last page is only about {round(fills[-1] * 100)}% full. "
                                                         "Trim a few bullets or tighten spacing to save a page."})
    if pages == 1 and fills[0] < 0.5:
        warnings.append({"level": "info", "message": "The page is about half full. That is fine for early careers; projects or achievements can add substance."})
    suggestions: list[dict[str, Any]] = []
    if suggest and pages > 1 and fills[-1] < 0.35:
        for label, change in (("Tighter spacing", {"section_spacing": 0.8, "line_height": min(st["line_height"], 1.2)}),
                              ("Narrower margins", {"margin_mm": 13}),
                              ("Spacing, margins and 10 pt text", {"section_spacing": 0.8, "line_height": 1.2, "margin_mm": 13,
                                                                     "font_size": max(10.0, 9.5 if tpl["ats_safe"] else 9.0)})):
            trial = {**st, **change}
            n = len(_render(doc, template_key, trial).pages)
            if n < pages:
                suggestions.append({"label": label, "settings": change, "pages": n})
                break
    return {"pages": pages, "page_fill": fills, "warnings": warnings, "fit_suggestions": suggestions, "settings": st}


# ---------------------------------------------------------------------------------------------------------------
# DOCX from the same render model and layout spec.

def _set_cell_border_bottom(paragraph, color_hex: str, size_eighths: int = 6) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    p_pr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", str(size_eighths)), ("w:space", "1"), ("w:color", color_hex.lstrip("#"))):
        bottom.set(qn(k), v)
    bdr.append(bottom)
    p_pr.append(bdr)


def _add_hyperlink(paragraph, text: str, url: str, color: str | None = None) -> None:
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    r_id = paragraph.part.relate_to(url, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    if color:
        c = OxmlElement("w:color")
        c.set(qn("w:val"), color.lstrip("#"))
        rpr.append(c)
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def render_docx(doc: dict[str, Any], template_key: str, settings: dict[str, Any]) -> tuple[bytes, str | None]:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.shared import Mm, Pt, RGBColor

    tpl = TEMPLATES[template_key]
    st, _ = normalize_settings(template_key, settings)
    m = render_model(doc, template_key, st)
    size, sp = st["font_size"], st["section_spacing"]
    accent = RGBColor.from_string(st["accent"].lstrip("#"))
    dark = RGBColor(0x37, 0x41, 0x51)

    d = Document()
    sec = d.sections[0]
    _ = WD_SECTION  # (one section)
    if st["page_size"] == "A4":
        sec.page_width, sec.page_height = Mm(210), Mm(297)
    else:
        sec.page_width, sec.page_height = Mm(215.9), Mm(279.4)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Mm(st["margin_mm"]))
    text_width = sec.page_width - sec.left_margin - sec.right_margin

    normal = d.styles["Normal"]
    normal.font.name = FONTS[st["font_family"]]["docx"]
    normal.font.size = Pt(size)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.line_spacing = st["line_height"] * 0.95
    props = d.core_properties
    props.title = f"{m['name']} – Resume" if m["name"] != "Your name" else "Resume"
    props.author = m["name"]
    props.subject = "Resume"
    props.comments = "Created with JobPilot Resume Studio"

    def para(space_before=0.0, space_after=0.0, keep_next=False, align=None):
        p = d.add_paragraph()
        pf = p.paragraph_format
        pf.space_before, pf.space_after, pf.keep_with_next = Pt(space_before), Pt(space_after), keep_next
        if align == "center":
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return p

    align = tpl["name_align"]
    p = para(0, 1, align=align)
    r = p.add_run(m["name"])
    r.bold, r.font.size = True, Pt(size + 11)
    if tpl["category"] in ("modern", "graduate", "technical"):
        r.font.color.rgb = accent
    if m["headline"]:
        r = para(0, 1, align=align).add_run(m["headline"])
        r.font.size = Pt(size + 1)
        r.font.color.rgb = accent if tpl["category"] != "ats" else dark
    if m["contact"]:
        p = para(1, 0, align=align)
        for i, c in enumerate(m["contact"]):
            if i:
                p.add_run("  |  " if tpl["category"] == "ats" else "  ·  ").font.color.rgb = RGBColor(0x9C, 0xA3, 0xAF)
            if c["href"]:
                _add_hyperlink(p, c["text"], c["href"])
            else:
                p.add_run(c["text"])
    if m["mobility"]:
        para(1, 0, align=align).add_run(m["mobility"])
    heading = "accent" if st["heading_style"] == "label_left" else st["heading_style"]
    upper = st["heading_style"] in ("caps_rule", "underline", "label_left")  # same capitals as the PDF
    for s in m["sections"]:
        h = para(9 * sp, 3 * sp, keep_next=True)
        text = s["heading"].upper() if upper else s["heading"]
        r = h.add_run(text)
        r.bold, r.font.size = True, Pt(size + 1)
        if heading in ("accent", "underline"):
            r.font.color.rgb = accent
        if heading == "caps_rule":
            _set_cell_border_bottom(h, "111827")
        elif heading == "underline":
            _set_cell_border_bottom(h, st["accent"], 4)
        for it in s["items"]:
            if it["kind"] == "text":
                for ptxt in it["paragraphs"]:
                    para(0, 3 * sp).add_run(ptxt)
            elif it["kind"] == "skills":
                p = para(0, 2 * sp)
                if it["label"]:
                    p.add_run(f"{it['label']}: ").bold = True
                p.add_run(", ".join(it["items"]))
            else:
                first = True
                for left, right, style in ((it["title"] or it["org"], it["dates"], "t"),
                                           (it["org"] if it["title"] else "", it["location"], "o")):
                    if not (left or right):
                        continue
                    p = para(5 * sp if first else 0, 0, keep_next=True)
                    p.paragraph_format.tab_stops.add_tab_stop(text_width, WD_TAB_ALIGNMENT.RIGHT)
                    r = p.add_run(left)
                    r.bold, r.italic = style == "t", style == "o"
                    if right:
                        rr = p.add_run("\t" + right)
                        rr.font.size, rr.font.color.rgb = Pt(size - 0.5), dark
                    first = False
                if it["detail"] or it["link"]:
                    p = para(0, 0, keep_next=bool(it["bullets"]))
                    if it["detail"]:
                        p.add_run(it["detail"]).font.size = Pt(size - 0.5)
                    if it["link"]:
                        if it["detail"]:
                            p.add_run(" · ")
                        if it["link_href"]:
                            _add_hyperlink(p, _url_label(it["link"]), it["link_href"])
                        else:
                            p.add_run(it["link"])
                for i, b in enumerate(it["bullets"]):
                    p = d.add_paragraph(style="List Bullet")
                    pf = p.paragraph_format
                    pf.space_before, pf.space_after = Pt(2 * sp if i == 0 else 0), Pt(1.5 * sp)
                    pf.left_indent, pf.first_line_indent = Mm(5), Mm(-3.5)
                    pf.keep_together = True
                    p.add_run(b)
    buf = io.BytesIO()
    d.save(buf)
    note = "In Word the section names sit above each section instead of in the left margin." if st["heading_style"] == "label_left" else None
    return buf.getvalue(), note
