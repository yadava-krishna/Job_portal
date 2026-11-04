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
    ("summary", ("SUMMARY", "PROFILE", "OBJECTIVE", "ABOUT ME")),
    ("certifications", ("CERTIFICATION", "CERTIFICATE", "LICENSE")),
    ("experience", ("EXPERIENCE", "EMPLOYMENT", "WORK HISTORY", "CAREER HISTORY")),
    ("education", ("EDUCATION", "ACADEMIC", "QUALIFICATION")),
    ("projects", ("PROJECT",)),
    ("achievements", ("ACHIEVEMENT", "ACCOMPLISHMENT", "AWARD")),
    ("skills", ("SKILLS", "COMPETENC", "EXPERTISE", "TOOLS")),
    ("languages", ("LANGUAGE",)),
]

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
_DATE_TOKEN = r"(?:[A-Za-z]{3,9}\.?\s*'?\d{2,4}|\d{1,2}[/\-.]\d{4}|\d{4})"
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
    import pymupdf

    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # pymupdf raises several exception types for corrupt files
        raise ResumeParseError(f"Could not open {path.name} as a PDF: {exc}") from exc
    try:
        if doc.needs_pass:
            raise ResumeParseError(f"{path.name} is password-protected; save an unprotected copy.")
        pages = [page.get_text("text") for page in doc]
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


def classify_heading(line: str) -> str | None:
    """Return the section name if `line` looks like a section heading."""
    s = line.strip()
    if not s or len(s) > 45 or _BULLET_RE.match(s):
        return None
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


def split_items(lines: list[str]) -> list[str]:
    """Split a skills-style block ('A • B • C', 'A, B | C') into items, joining wrapped lines."""
    joined = " ".join(ln.strip() for ln in lines)
    parts = re.split(r"\s*(?:•|●|▪|\||;|·|,(?![^()]*\)))\s*", joined)
    return [" ".join(p.split()).strip(" .") for p in parts if p and len(p.strip(" .")) > 1]


def parse_month(token: str, *, is_end: bool = False) -> date | None:
    t = re.sub(r"(?<=[a-z])\.", "", token.strip().lower()).replace("'", " ")
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
