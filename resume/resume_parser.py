"""PDF resume text extraction and section parsing.

Parsing is deterministic and only records what is written in the resume: every
extracted item comes from the PDF text, nothing is inferred or generated.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)


class ResumeParseError(Exception):
    pass


BULLET_CHARS = "•●▪◦‣∙·*-–.▪•"
_BULLET_RE = re.compile(rf"^\s*[{re.escape(BULLET_CHARS)}](?:\s+|$)")

SECTION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    # Sections that carry no profile facts (personal details, declarations, hobbies) are recognised so that their
    # lines never leak into skills or experience. "contact" holds sidebar contact blocks.
    ("other", ("PERSONAL DETAIL", "PERSONAL INFORMATION", "PERSONAL PROFILE", "DECLARATION", "HOBBIES", "INTERESTS", "REFERENCES",
               "EXTRA-CURRICULAR", "EXTRACURRICULAR", "EXTRA CURRICULAR", "STRENGTHS")),
    ("contact", ("CONTACT",)),
    ("summary", ("SUMMARY", "PROFILE", "OBJECTIVE", "ABOUT ME")),
    ("certifications", ("CERTIFICATION", "CERTIFICATE", "LICENSE", "TRAININGS", "COURSES")),
    ("experience", ("EXPERIENCE", "EMPLOYMENT", "WORK HISTORY", "CAREER HISTORY", "INTERNSHIP")),
    ("education", ("EDUCATION", "ACADEMIC", "QUALIFICATION")),
    ("projects", ("PROJECT",)),
    ("achievements", ("ACHIEVEMENT", "ACCOMPLISHMENT", "AWARD", "HONOURS", "HONORS")),
    ("skills", ("SKILLS", "COMPETENC", "EXPERTISE", "TOOLS", "PROFICIENC")),
    ("languages", ("LANGUAGE",)),
]
# Headings written in Title Case ("Work Experience:") are accepted only when the whole line is a known heading.
KNOWN_HEADINGS = {
    "summary": "summary", "professional summary": "summary", "profile summary": "summary", "career summary": "summary",
    "career objective": "summary", "objective": "summary", "profile": "summary", "about me": "summary",
    "experience": "experience", "work experience": "experience", "professional experience": "experience",
    "employment history": "experience", "work history": "experience", "internships": "experience", "internship": "experience",
    "relevant experience": "experience", "education": "education", "academic qualifications": "education",
    "educational qualifications": "education", "academic qualification": "education", "educational qualification": "education",
    "qualifications": "education", "projects": "projects", "academic projects": "projects", "key projects": "projects",
    "skills": "skills", "technical skills": "skills", "key skills": "skills", "core competencies": "skills", "it skills": "skills",
    "skills & tools": "skills", "skills and tools": "skills", "software skills": "skills",
    "certifications": "certifications", "certificates": "certifications", "courses": "certifications", "trainings": "certifications",
    "achievements": "achievements", "awards": "achievements", "awards & achievements": "achievements", "honours": "achievements",
    "languages": "languages", "languages known": "languages", "personal details": "other", "personal information": "other",
    "declaration": "other", "hobbies": "other", "interests": "other", "references": "other", "extra-curricular activities": "other",
    "extracurricular activities": "other", "strengths": "other", "contact": "contact", "contact details": "contact",
    "contact information": "contact",
}

_MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}
_DATE_TOKEN = r"(?:[A-Za-z]{3,9}\.?,?\s*[’']?\d{2,4}|\d{1,2}[/\-.]\d{4}|\d{4})"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:–|—|-|to|till|until)\s*(?P<end>present|current|current\s+date|till\s+date|to\s+date|now|ongoing|{_DATE_TOKEN})",
    re.IGNORECASE,
)


@dataclass
class ResumeDocument:
    path: Path
    sha256: str
    page_count: int
    text: str
    lines: list[str]
    sections: dict[str, list[str]] = field(default_factory=dict)
    section_headings: dict[str, str] = field(default_factory=dict)
    header_lines: list[str] = field(default_factory=list)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(path: Path) -> tuple[str, int]:
    """Text of a PDF (layout-aware: two-column pages are read one column at a time) or a Word .docx file."""
    if path.suffix.lower() == ".docx":
        return _docx_text(path)
    import pymupdf

    try:
        doc = pymupdf.open(path, filetype="pdf")
    except Exception as exc:  # pymupdf raises several exception types for corrupt files
        raise ResumeParseError(f"Could not open {path.name} as a PDF: {exc}") from exc
    try:
        if doc.needs_pass:
            raise ResumeParseError(f"{path.name} is password-protected; save an unprotected copy.")
        pages = [_page_text(page) for page in doc]
        count = doc.page_count
    finally:
        doc.close()
    text = "\n".join(pages)
    if len(text.strip()) < 100:
        raise ResumeParseError(
            f"{path.name} contains almost no extractable text. It may be a scanned image; "
            "export the resume as a text-based PDF."
        )
    return text, count


_DATEISH = re.compile(rf"^\s*({_DATE_TOKEN})(\s*(–|—|-|to)\s*(present|current|now|till date|{_DATE_TOKEN}))?\s*$", re.I)


def _page_text(page) -> str:
    """One page's text in reading order. A page laid out in two columns (e.g. a sidebar) is read column by column,
    starting with the column that holds the largest text (the name); everything else is read top to bottom."""
    lines = []
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            spans = [s for s in ln.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            x0, y0, x1, y1 = ln["bbox"]
            lines.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": "".join(s["text"] for s in ln["spans"]).strip(),
                          "size": max(s.get("size", 0) for s in spans)})
    if not lines:
        return ""
    order = _column_order(lines, page.rect.width)
    if order is None:
        order = _merge_rows(sorted(lines, key=lambda l: (round(l["y0"] / 3), l["x0"])))
    return "\n".join(l["text"] for l in order)


def _merge_rows(lines: list[dict]) -> list[dict]:
    """Keep left-to-right pieces of one visual row (title ... dates) as consecutive lines, top to bottom."""
    return lines


def _column_order(lines: list[dict], width: float) -> list[dict] | None:
    """Lines in column order if the page has two text columns, else None.

    Two columns need: a vertical gap no body line crosses; at least 5 lines on each side; the smaller side holding at
    least a quarter as many lines as the larger (so right-aligned dates, or headings in a left margin, don't count);
    and the smaller side not being mostly dates or short place names.
    """
    best = None
    edges = sorted({round(l["x1"]) for l in lines} | {round(l["x0"]) for l in lines})
    for g in edges:
        if not (0.2 * width <= g <= 0.8 * width):
            continue
        left = [l for l in lines if l["x1"] <= g + 1]
        right = [l for l in lines if l["x0"] >= g - 1]
        crossing = [l for l in lines if l["x0"] < g - 1 and l["x1"] > g + 1]
        if len(left) < 5 or len(right) < 5:
            continue
        body_top = min(min(l["y0"] for l in left), min(l["y0"] for l in right))
        if any(c["y0"] >= body_top - 1 for c in crossing):
            continue
        small, large = sorted((left, right), key=len)
        if len(small) / len(large) < 0.25:
            continue
        dates = sum(1 for l in small if _DATEISH.match(l["text"]))
        if dates / len(small) >= 0.3:  # right-aligned dates (and their locations) of a one-column resume
            continue
        score = min(len(left), len(right))
        if best is None or score > best[0]:
            best = (score, crossing, left, right)
    if best is None:
        return None
    _, crossing, left, right = best
    by_y = lambda ls: sorted(ls, key=lambda l: (round(l["y0"] / 3), l["x0"]))  # noqa: E731
    first, second = (left, right) if max(l["size"] for l in left) >= max(l["size"] for l in right) else (right, left)
    return by_y(crossing) + by_y(first) + by_y(second)


def _docx_text(path: Path) -> tuple[str, int]:
    """Text of a .docx: page-header lines first (contact details often live there), then the body in order.
    Bulleted paragraphs keep a bullet; table rows become "a | b | c" so cells stay separate items. A layout table
    (few rows, long cells: a two-column design made with a table) is read cell by cell instead."""
    import zipfile

    try:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        d = docx.Document(str(path))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ResumeParseError(f"Could not open {path.name} as a Word document: {exc}") from exc
    out: list[str] = []

    def para_text(p) -> str:
        t = " ".join(p.text.split())
        if not t:
            return ""
        style = (p.style.name if p.style is not None else "") or ""
        numbered = p._p.pPr is not None and p._p.pPr.numPr is not None
        return f"• {t}" if (style.lower().startswith("list") or numbered) and not is_bullet(t) else t

    def table_lines(t) -> list[str]:
        rows = [[c for c in r.cells] for r in t.rows]
        long_cells = sum(1 for r in rows for c in r if len(c.paragraphs) > 3)
        if len(rows) <= 3 and long_cells:
            seen, lines = set(), []
            for col in range(max(len(r) for r in rows)):
                for r in rows:
                    if col < len(r) and id(r[col]._tc) not in seen:
                        seen.add(id(r[col]._tc))
                        lines += [x for x in (para_text(p) for p in r[col].paragraphs) if x]
            return lines
        lines = []
        for r in rows:
            cells, seen = [], set()
            for c in r:
                if id(c._tc) in seen:
                    continue
                seen.add(id(c._tc))
                txt = " ".join(c.text.split())
                if txt:
                    cells.append(txt)
            if cells:
                lines.append(" | ".join(cells))
        return lines

    for section in d.sections:
        for p in section.header.paragraphs:
            if para_text(p):
                out.append(para_text(p))
    for child in d.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            t = para_text(Paragraph(child, d))
            if t:
                out.append(t)
        elif tag == "tbl":
            out += table_lines(Table(child, d))
    text = "\n".join(out)
    if len(text.strip()) < 100:
        raise ResumeParseError(f"{path.name} contains almost no text.")
    pages = 1
    try:
        with zipfile.ZipFile(path) as z:
            m = re.search(rb"<Pages>(\d+)</Pages>", z.read("docProps/app.xml"))
            pages = int(m.group(1)) if m else 1
    except (KeyError, zipfile.BadZipFile):
        pass
    return text, max(1, pages)


def classify_heading(line: str) -> str | None:
    """Return the section name if `line` looks like a section heading."""
    s = line.strip()
    if not s or len(s) > 45 or _BULLET_RE.match(s):
        return None
    known = KNOWN_HEADINGS.get(" ".join(s.rstrip(":").lower().split()))
    if known:
        return known
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 4 or sum(c.isupper() for c in letters) / len(letters) < 0.8:
        return None
    upper = s.upper()
    for name, keywords in SECTION_KEYWORDS:
        if any(k in upper for k in keywords):
            return name
    return None


def parse_resume(path: Path) -> ResumeDocument:
    text, pages = extract_text(path)
    lines = [ln.rstrip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    doc = ResumeDocument(path=path, sha256=file_sha256(path), page_count=pages, text=text, lines=lines)

    current: str | None = None
    for ln in lines:
        heading = classify_heading(ln)
        if heading:
            # A repeated heading (e.g. second "SKILLS" block) appends to the same section.
            current = heading
            doc.sections.setdefault(current, [])
            doc.section_headings.setdefault(current, ln.strip())
            continue
        if current is None:
            doc.header_lines.append(ln.strip())
        else:
            doc.sections[current].append(ln)
    if "experience" not in doc.sections:
        log.warning("No experience section heading found in the resume.")
    return doc


# ---- helpers used by the profile builder -------------------------------------


def join_bullets(lines: list[str]) -> list[str]:
    """Merge wrapped lines into bullets. A line starting with a bullet marker opens a new bullet."""
    bullets: list[str] = []
    current: list[str] = []
    for ln in lines:
        m = _BULLET_RE.match(ln)
        if m:
            if current:
                bullets.append(" ".join(current))
            rest = ln[m.end():].strip()
            current = [rest] if rest else []
        else:
            current.append(ln.strip())
    if current:
        bullets.append(" ".join(current))
    # Re-join words hyphenated across a line break ("patient- related" -> "patient-related").
    return [re.sub(r"(\w)- (\w)", r"\1-\2", " ".join(b.split())) for b in bullets if b.strip()]


def is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


_ITEM_SEP = re.compile(r"\s*(?:•|●|▪|\||;|·|,(?![^()]*\)))\s*")


def split_items(lines: list[str]) -> list[str]:
    """Split a skills-style block ('A • B • C', 'A, B | C') into items, joining wrapped lines.
    A list with one short item per line and no separators (common in sidebars) gives one item per line."""
    real = [ln.strip() for ln in lines if ln.strip()]
    if real and not any(_ITEM_SEP.search(_BULLET_RE.sub("", ln, count=1)) for ln in real) and all(len(ln.split()) <= 5 for ln in real):
        return [" ".join(_BULLET_RE.sub("", ln, count=1).split()).strip(" .") for ln in real if len(ln.strip(" .")) > 1]
    if real and all(_ITEM_SEP.search(ln) for ln in real):  # every line is itself a list ("a | b | c"): never join lines
        return [x for ln in real for x in split_items([ln + " "]) if x] if len(real) > 1 else _split_joined(real[0])
    return _split_joined(" ".join(_BULLET_RE.sub("", ln.strip(), count=1) if _BULLET_RE.match(ln) else ln.strip() for ln in lines))


def _split_joined(joined: str) -> list[str]:
    parts = re.split(r"\s*(?:•|●|▪|\||;|·|,(?![^()]*\)))\s*", joined)
    return [" ".join(p.split()).strip(" .") for p in parts if p and len(p.strip(" .")) > 1]


def parse_month(token: str, *, is_end: bool = False) -> date | None:
    t = re.sub(r"(?<=[a-z])\.", "", token.strip().lower()).replace("'", " ").replace("’", " ").replace(",", " ")
    m = re.fullmatch(r"([a-z]{3,9})\s*(\d{2,4})", t)
    if m and m.group(1) in _MONTHS:
        year = int(m.group(2))
        year = year + 2000 if year < 100 else year
        return date(year, _MONTHS[m.group(1)], 1)
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{4})", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return date(int(m.group(2)), int(m.group(1)), 1)
    m = re.fullmatch(r"(\d{4})", t)
    if m:
        # A bare year: assume the whole year (Jan for a start, Dec for an end).
        return date(int(m.group(1)), 12 if is_end else 1, 1)
    return None


def parse_date_range(text: str, today: date) -> tuple[date, date, bool] | None:
    m = DATE_RANGE_RE.search(text)
    if not m:
        return None
    start = parse_month(m.group("start"))
    end_token = m.group("end").strip().lower()
    is_current = bool(re.match(r"present|current|till|to\s+date|now|ongoing", end_token))
    end = date(today.year, today.month, 1) if is_current else parse_month(m.group("end"), is_end=True)
    if not start or not end or end < start:
        return None
    return start, end, is_current
