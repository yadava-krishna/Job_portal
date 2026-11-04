"""Deterministic job-description analysis: skills, experience, salary, mode, type, education."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from core.skills import SkillTaxonomy

_EXP_RANGE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*(?:\+\s*)?(?:-|–|to)\s*(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", re.I)
_EXP_PLUS = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+\s*(?:years?|yrs?)", re.I)
_EXP_MIN = re.compile(r"(?:minimum|min\.?|at\s+least|over|more\s+than)\s*(?:of\s*)?(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", re.I)
_EXP_PLAIN = re.compile(r"(\d{1,2}(?:\.\d)?)\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+|total\s+|overall\s+|professional\s+|work\s+)?experience", re.I)

_LPA_RANGE = re.compile(r"(?:₹|INR|Rs\.?)?\s*(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:LPA|L\.?P\.?A|lakhs?|lacs?|lac|L\b)", re.I)
_LPA_SINGLE = re.compile(r"(?:up\s*to|upto|max(?:imum)?)?\s*(?:₹|INR|Rs\.?)?\s*(\d+(?:\.\d+)?)\s*(?:LPA|L\.?P\.?A|lakhs?|lacs?)", re.I)
_RUPEE_RANGE = re.compile(r"(?:₹|INR|Rs\.?)\s*([\d,]{5,})\s*(?:-|–|to)\s*(?:₹|INR|Rs\.?)?\s*([\d,]{5,})\s*(?:(?:per|a|/)\s*(year|annum|month|yr|mo))?", re.I)

_PREFERRED_MARKERS = re.compile(r"\b(preferred|nice[\s-]to[\s-]have|good[\s-]to[\s-]have|desirable|added advantage|is a plus|bonus|optional|advantageous)\b", re.I)
_PREFERRED_HEADING = re.compile(r"^\s*(preferred|nice to have|good to have|desired|bonus|plus)\b.*:?\s*$", re.I)
_REQUIRED_HEADING = re.compile(r"^\s*(requirements?|required|must[\s-]have|qualifications?|what you('ll)? need|skills|key skills|who you are|responsibilities|job description|about the role|role)\b.*:?\s*$", re.I)

EDUCATION_PATTERNS = {
    "B.Com": r"\bB\.?\s?Com\b|bachelor'?s?\s+(?:degree\s+)?(?:of|in)\s+commerce",
    "M.Com": r"\bM\.?\s?Com\b|master'?s?\s+(?:degree\s+)?(?:of|in)\s+commerce",
    "MBA": r"\bMBA\b|\bPGDM\b|master'?s? of business administration",
    "CA": r"\bCA\b(?!\s*-?\s*inter)|chartered accountant",
    "CA Inter": r"\bCA\s*-?\s*inter(?:mediate)?\b",
    "CMA": r"\bCMA\b|\bICWA\b|cost and management accountant",
    "CFA": r"\bCFA\b",
    "CPA": r"\bCPA\b",
    "ACCA": r"\bACCA\b",
    "Bachelor's degree": r"bachelor'?s?\s+degree|\bgraduat(?:e|ion)\b|\bdegree in (?:finance|accounting|commerce|economics)",
    "Any graduate": r"any\s+graduate|graduate in any",
}

WORK_MODE_PATTERNS = [
    ("Hybrid", r"\bhybrid\b"),
    ("Remote", r"\bremote\b|work\s+from\s+home|\bwfh\b"),
    ("On-site", r"\bon[\s-]?site\b|work\s+from\s+office|\bwfo\b|in[\s-]office"),
]
EMPLOYMENT_TYPE_PATTERNS = [
    ("Internship", r"\bintern(ship)?\b"),
    ("Contract", r"\bcontract(ual)?\b|\btemporary\b|\bfixed[\s-]term\b|\bfreelance\b"),
    ("Part-time", r"\bpart[\s-]time\b"),
    ("Full-time", r"\bfull[\s-]time\b|\bpermanent\b"),
]


@dataclass
class JDAnalysis:
    exp_min: float | None = None
    exp_max: float | None = None
    experience_text: str | None = None
    salary_min_lpa: float | None = None
    salary_max_lpa: float | None = None
    salary_text: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    mandatory_qualifications: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    mentions_cover_letter: bool = False


def parse_experience(text: str | None) -> tuple[float | None, float | None, str | None]:
    if not text:
        return None, None, None
    for pattern, kind in ((_EXP_RANGE, "range"), (_EXP_MIN, "min"), (_EXP_PLUS, "plus"), (_EXP_PLAIN, "plain")):
        m = pattern.search(text)
        if m:
            if kind == "range":
                lo, hi = float(m.group(1)), float(m.group(2))
                if lo <= hi <= 40:
                    return lo, hi, m.group(0).strip()
                continue
            return float(m.group(1)), None, m.group(0).strip()
    return None, None, None


def parse_salary(text: str | None) -> tuple[float | None, float | None, str | None]:
    """Return (min, max) annual salary in lakhs (LPA)."""
    if not text:
        return None, None, None
    m = _LPA_RANGE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2)), m.group(0).strip()
    m = _RUPEE_RANGE.search(text)
    if m:
        lo, hi = (float(x.replace(",", "")) for x in (m.group(1), m.group(2)))
        monthly = (m.group(3) or "").lower().startswith("mo")
        factor = 12 if monthly else 1
        return round(lo * factor / 1e5, 2), round(hi * factor / 1e5, 2), m.group(0).strip()
    m = _LPA_SINGLE.search(text)
    if m:
        v = float(m.group(1))
        return (None, v, m.group(0).strip()) if re.search(r"up\s*to|upto|max", m.group(0), re.I) else (v, v, m.group(0).strip())
    return None, None, None


def detect_first(text: str | None, patterns: list[tuple[str, str]]) -> str | None:
    if not text:
        return None
    for label, pattern in patterns:
        if re.search(pattern, text, re.I):
            return label
    return None


def parse_posted_date(value: str | None, today: date) -> date | None:
    if not value:
        return None
    v = value.strip().lower()
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        pass
    if v in ("today", "just now", "just posted") or re.search(r"\b(minute|hour)s?\b", v):
        return today
    if v == "yesterday":
        return today - timedelta(days=1)
    m = re.search(r"(\d+)\s*\+?\s*(day|week|month)s?", v)
    if m:
        n = int(m.group(1))
        return today - timedelta(days=n * {"day": 1, "week": 7, "month": 30}[m.group(2)])
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


class JDAnalyzer:
    def __init__(self, taxonomy: SkillTaxonomy):
        self.taxonomy = taxonomy

    def analyze(self, description: str | None, *, title: str = "") -> JDAnalysis:
        a = JDAnalysis()
        text = description or ""
        a.exp_min, a.exp_max, a.experience_text = parse_experience(text)
        a.salary_min_lpa, a.salary_max_lpa, a.salary_text = parse_salary(text)
        a.work_mode = detect_first(text, WORK_MODE_PATTERNS)
        a.employment_type = detect_first(text, EMPLOYMENT_TYPE_PATTERNS)
        a.mentions_cover_letter = bool(re.search(r"cover\s+letter", text, re.I))

        required, preferred = self._split_skill_sections(text)
        a.required_skills = required or ([] if text else self.taxonomy.skills_in(title))
        a.preferred_skills = [s for s in preferred if s not in a.required_skills]

        for label, pattern in EDUCATION_PATTERNS.items():
            m = re.search(pattern, text, re.I)
            if m:
                a.education.append(label)
                # Judge "mandatory" vs "preferred" from the sentence/line that mentions the qualification.
                line_start = text.rfind("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.end())
                window = text[line_start : line_end if line_end != -1 else len(text)]
                if re.search(r"\b(mandatory|must|required|compulsory|essential|only)\b", window, re.I) and not _PREFERRED_MARKERS.search(window):
                    a.mandatory_qualifications.append(label)
        a.responsibilities = self._responsibilities(text)
        return a

    def _split_skill_sections(self, text: str) -> tuple[list[str], list[str]]:
        required: list[str] = []
        preferred: list[str] = []
        mode = "required"
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _PREFERRED_HEADING.match(stripped) and len(stripped) < 60:
                mode = "preferred"
                continue
            if _REQUIRED_HEADING.match(stripped) and len(stripped) < 60:
                mode = "required"
            line_mode = "preferred" if (mode == "preferred" or _PREFERRED_MARKERS.search(stripped)) else "required"
            target = preferred if line_mode == "preferred" else required
            for skill in self.taxonomy.skills_in(stripped):
                if skill not in required and skill not in preferred:
                    target.append(skill)
        return required, preferred

    @staticmethod
    def _responsibilities(text: str) -> list[str]:
        lines = []
        for line in text.splitlines():
            s = re.sub(r"^[\s•●▪◦*\-–.\d)]+", "", line).strip()
            if 25 <= len(s) <= 300 and re.match(r"^[A-Z]?[a-z]+(e|s|ing|ed)?\b", s):
                lines.append(s)
        return lines[:25]
