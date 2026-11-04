"""Builds the structured candidate profile (JSON) from the parsed resume and caches it.

The cache is keyed by the resume's SHA-256, so editing or replacing the PDF
automatically triggers a rebuild on the next run.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from core import timeutil
from core.settings import Settings, validate_resume_path
from core.skills import SkillTaxonomy, normalize_text
from resume.resume_parser import (
    DATE_RANGE_RE,
    ResumeDocument,
    file_sha256,
    is_bullet,
    join_bullets,
    parse_date_range,
    parse_resume,
    split_items,
)

log = logging.getLogger(__name__)

PROFILE_SCHEMA_VERSION = 3

TITLE_NOUNS = (
    "Associate", "Analyst", "Executive", "Manager", "Specialist", "Consultant", "Officer",
    "Accountant", "Clerk", "Lead", "Coordinator", "Intern", "Assistant", "Engineer",
    "Representative", "Processor", "Trainee", "Supervisor", "Controller", "Auditor", "Developer",
)
_TITLE_NOUN_RE = re.compile(rf"\b({'|'.join(TITLE_NOUNS)})s?\b", re.IGNORECASE)
_HEADER_SEPARATORS = [r"\s+\|\s+", r"\s+I\s+", r"\s+@\s+", r"\s+at\s+", r"\s+—\s+", r"\s+–\s+", r",\s+"]
_METRIC_RE = re.compile(r"\d+(?:\.\d+)?\s*%|\b\d+(?:,\d{3})*(?:\.\d+)?\b(?!\s*(?:–|-)\s*\d{4})")
_DEGREE_RE = re.compile(
    r"\b(B\.?\s?Com|M\.?\s?Com|Bachelor[^,|\n]*|Master[^,|\n]*|MBA|PGDM|BBA|BBM|B\.?\s?Tech|B\.?\s?E\b|B\.?\s?Sc|M\.?\s?Sc|Ph\.?D|Diploma[^,|\n]*|CA\b|CFA\b|CPA\b)",
    re.IGNORECASE,
)


# ---- experience -------------------------------------------------------------


def months_between(start: date, end: date) -> int:
    """Inclusive month count: Jan 2020 - Jan 2020 is 1 month."""
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Merge overlapping or adjacent month intervals so overlapping jobs are not double-counted."""
    def idx(d: date) -> int:
        return d.year * 12 + d.month - 1

    ordered = sorted((idx(s), idx(e)) for s, e in intervals)
    merged: list[list[int]] = []
    for s, e in ordered:
        if merged and s <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(date(s // 12, s % 12 + 1, 1), date(e // 12, e % 12 + 1, 1)) for s, e in merged]


def total_experience_months(intervals: list[tuple[date, date]]) -> int:
    return sum(months_between(s, e) for s, e in merge_intervals(intervals))


def split_role_header(header: str) -> tuple[str, str, str]:
    """Split 'Title I Company' style headers. Returns (title, company, confidence)."""
    header = " ".join(header.split())
    for sep in _HEADER_SEPARATORS:
        parts = re.split(sep, header)
        if len(parts) >= 2:
            left, right = sep_join(parts[:-1], sep), parts[-1]
            if _TITLE_NOUN_RE.search(right) and not _TITLE_NOUN_RE.search(left):
                left, right = right, left  # "Company | Title" order
            return left.strip(" -"), right.strip(" -"), "high"
    # No separator: split after the last job-title noun ("Accounts Receivable Associate omega Healthcare").
    matches = list(_TITLE_NOUN_RE.finditer(header))
    if matches:
        cut = matches[-1].end()
        title, company = header[:cut].strip(), header[cut:].strip(" -,")
        if company:
            return title, company, "medium"
    return header, "", "low"


def sep_join(parts: list[str], sep: str) -> str:
    joiner = {r"\s+\|\s+": " | ", r"\s+I\s+": " I ", r",\s+": ", "}.get(sep, " - ")
    return joiner.join(parts)


def _header_block(lines: list[str], i: int, date_idx: set[int]) -> list[int]:
    """Indices of the title/company lines directly above the date line at `i` (at most 2).

    Header lines are not bullets and do not end with a full stop; walking back stops at
    the previous role's last bullet line, which does.
    """
    block: list[int] = []
    j = i - 1
    while j >= 0 and len(block) < 2:
        ln = lines[j].strip()
        if is_bullet(lines[j]) or j in date_idx or not ln or len(ln) > 90 or ln.endswith((".", ",", ";")):
            break
        block.insert(0, j)
        j -= 1
    return block


def parse_experience(lines: list[str], today: date) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    date_idx = [i for i, ln in enumerate(lines) if DATE_RANGE_RE.search(ln) and parse_date_range(ln, today)]
    date_set = set(date_idx)
    headers: dict[int, list[int]] = {}
    for i in date_idx:
        remainder = DATE_RANGE_RE.sub("", lines[i]).strip(" |,-–—")
        headers[i] = [] if (len(remainder) > 3 and not is_bullet(lines[i])) else _header_block(lines, i, date_set)

    roles: list[dict[str, Any]] = []
    for n, i in enumerate(date_idx):
        start, end, current = parse_date_range(lines[i], today)  # type: ignore[misc]
        block = headers[i]
        if block:
            header = " | ".join(lines[j].strip() for j in block)
        else:
            header = DATE_RANGE_RE.sub("", lines[i]).strip(" |,-–—")
        if not header:
            warnings.append(f"Could not find a title/company line for the role dated '{lines[i].strip()}'.")
        title, company, confidence = split_role_header(header)
        if confidence == "low":
            warnings.append(f"Title and company could not be separated in '{header}'.")
        # Bullets run until the next role's header block (or its date line).
        stop = len(lines)
        if n + 1 < len(date_idx):
            nxt = date_idx[n + 1]
            stop = headers[nxt][0] if headers[nxt] else nxt
        roles.append(
            {
                "title": title,
                "company": company,
                "header_raw": header,
                "parse_confidence": confidence,
                "start": start.strftime("%Y-%m"),
                "end": None if current else end.strftime("%Y-%m"),
                "is_current": current,
                "months": months_between(start, end),
                "date_text": DATE_RANGE_RE.search(lines[i]).group(0),  # type: ignore[union-attr]
                "bullets": join_bullets(lines[i + 1 : stop]),
            }
        )
    if not roles:
        warnings.append("No employment date ranges found; experience could not be calculated.")
    return roles, warnings


# ---- other sections -----------------------------------------------------------


def parse_education(lines: list[str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for ln in (l.strip() for l in lines):
        if _DEGREE_RE.search(ln) and not re.search(r"university|college|institute|school", ln, re.I):
            current = {"degree": ln, "institution": None, "university": None, "year": None, "raw": [ln]}
            entries.append(current)
            continue
        if current is None:
            current = {"degree": None, "institution": None, "university": None, "year": None, "raw": []}
            entries.append(current)
        current["raw"].append(ln)
        year = re.search(r"\b(19|20)\d{2}\b", ln)
        if year:
            current["year"] = int(year.group(0))
        parts = [p.strip() for p in re.split(r"\s*\|\s*", re.sub(r"\b(19|20)\d{2}\b", "", ln)) if p.strip()]
        for p in parts:
            if re.search(r"university", p, re.I):
                current["university"] = p
            elif re.search(r"college|institute|school|academy", p, re.I):
                current["institution"] = p.strip(", ")
    return entries


def parse_projects(lines: list[str]) -> list[dict[str, Any]]:
    """A non-bullet line opens a project when it follows a finished sentence and looks like a title."""
    projects: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    buffer: list[str] = []
    prev = ""
    for ln in lines:
        prev_is_marker = len(prev.strip()) <= 1
        opens = not is_bullet(ln) and (
            current is None or (not prev_is_marker and prev.rstrip().endswith(".") and _looks_like_title(ln))
        )
        if opens:
            if current is not None:
                current["bullets"] = join_bullets(buffer)
            current = {"name": ln.strip(), "bullets": []}
            projects.append(current)
            buffer = []
        else:
            buffer.append(ln)
        prev = ln
    if current is not None:
        current["bullets"] = join_bullets(buffer)
    return projects


def _looks_like_title(line: str) -> bool:
    s = line.strip()
    return (
        bool(s) and s[0].isupper() and len(s) < 90 and not s.endswith((".", ","))
        and (bool(re.search(r"\s[—–|-]\s", s)) or "project" in s.lower())
    )


def extract_achievements(roles: list[dict[str, Any]], projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for role in roles:
        for b in role["bullets"]:
            metrics = [m.group(0).strip() for m in _METRIC_RE.finditer(b)]
            if metrics:
                out.append({"text": b, "metrics": metrics, "context": f"{role['title']} at {role['company']}".strip()})
    for p in projects:
        for b in p["bullets"]:
            metrics = [m.group(0).strip() for m in _METRIC_RE.finditer(b)]
            if metrics:
                out.append({"text": b, "metrics": metrics, "context": p["name"]})
    return out


# ---- profile builder --------------------------------------------------------


class ProfileBuilder:
    def __init__(self, settings: Settings, taxonomy: SkillTaxonomy | None = None):
        self.settings = settings
        self.taxonomy = taxonomy or SkillTaxonomy.from_file(settings.taxonomy_path)

    @property
    def cache_path(self) -> Path:
        return self.settings.cache_dir / "candidate_profile.json"

    def load_or_build(self, *, force: bool = False, today: date | None = None) -> dict[str, Any]:
        resume = validate_resume_path(self.settings)
        sha = file_sha256(resume)
        facts = self.settings.load_verified_facts()
        overrides_sig = json.dumps(facts.get("profile_overrides", {}), sort_keys=True)
        if not force and self.cache_path.exists():
            try:
                cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if (
                    cached.get("resume", {}).get("sha256") == sha
                    and cached.get("schema_version") == PROFILE_SCHEMA_VERSION
                    and cached.get("_overrides_signature") == overrides_sig
                    and cached.get("resume", {}).get("path") == str(resume)
                ):
                    # Experience grows every month for a current role; refresh the arithmetic.
                    self._refresh_experience(cached, today or timeutil.today())
                    return cached
                log.info("Resume or profile overrides changed; rebuilding candidate profile.")
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Profile cache unreadable (%s); rebuilding.", exc)
        profile = self.build(resume, today=today)
        profile["_overrides_signature"] = overrides_sig
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.cache_path)
        return profile

    def _extractor(self) -> "ResumeProfileExtractor":
        c = self.settings.candidate
        return ResumeProfileExtractor(self.taxonomy, seed_skills=c.seed_skills, stated_years=c.stated_experience_years,
                                      default_name=c.name, default_location=c.location)

    def build(self, resume: Path, *, today: date | None = None) -> dict[str, Any]:
        profile = self._extractor().build(resume, today=today)
        self._apply_overrides(profile)
        return profile

    def _refresh_experience(self, profile: dict[str, Any], today: date, intervals: list[tuple[date, date]] | None = None) -> None:
        self._extractor().refresh_experience(profile, today, intervals)

    def _apply_overrides(self, profile: dict[str, Any]) -> None:
        overrides = self.settings.load_verified_facts().get("profile_overrides") or {}
        protected = {"schema_version", "resume", "total_experience", "resume_text"}
        for key, value in overrides.items():
            if key in protected:
                log.warning("profile_overrides.%s is not overridable and was ignored.", key)
                continue
            profile[key] = value
            profile.setdefault("overrides_applied", []).append(key)



class ResumeProfileExtractor:
    """Builds a structured profile from any resume PDF. Independent of the CLI settings,
    so the web portal can parse each user's own resume."""

    def __init__(self, taxonomy: SkillTaxonomy, *, seed_skills: list[str] | tuple[str, ...] = (), stated_years: float | None = None,
                 default_name: str | None = None, default_location: str | None = None):
        self.taxonomy = taxonomy
        self.seed_skills = list(seed_skills)
        self.stated_years = stated_years
        self.default_name = default_name
        self.default_location = default_location

    def build(self, resume: Path, *, today: date | None = None) -> dict[str, Any]:
        today = today or timeutil.today()
        doc = parse_resume(resume)
        warnings: list[str] = []

        roles, w = parse_experience(doc.sections.get("experience", []), today)
        warnings += w
        education = parse_education(doc.sections.get("education", []))
        projects = parse_projects(doc.sections.get("projects", []))

        # Certifications: in a combined "CERTIFICATIONS & TECHNICAL SKILLS" block the first
        # line is treated as certifications and the rest as technical skills.
        cert_lines = doc.sections.get("certifications", [])
        cert_heading = doc.section_headings.get("certifications", "")
        if cert_lines and "SKILL" in cert_heading.upper():
            certifications = split_items(cert_lines[:1])
            technical_skills = split_items(cert_lines[1:])
            warnings.append(
                f"'{cert_heading}' mixes certifications and skills; first line treated as certifications "
                f"({', '.join(certifications)}). Correct it in the profile review if needed."
            )
        else:
            certifications = split_items(cert_lines)
            technical_skills = []

        listed_skills = split_items(doc.sections.get("skills", []))
        languages = []
        for ln in doc.sections.get("languages", []):
            m = re.match(r"\s*languages?\s*:\s*(.+)", ln, re.I)
            if m:
                languages = [x.strip() for x in m.group(1).split(",") if x.strip()]

        skills = self._skills(doc, listed_skills, technical_skills, certifications)
        seed_report = self._verify_seed_skills(doc.text)
        for item in seed_report:
            if not item["found_in_resume"]:
                warnings.append(f"Configured seed skill '{item['skill']}' was not found in the resume and is not used for matching.")

        intervals = [(date.fromisoformat(r["start"] + "-01"), date.fromisoformat((r["end"] or today.strftime("%Y-%m")) + "-01")) for r in roles]
        header = doc.header_lines
        contact_line = header[1] if len(header) > 1 else ""
        email = re.search(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+", doc.text)
        phone = re.search(r"(?:\+?\d{1,3}[\s\-]?)?\d{10}\b|\+?\d[\d\s\-]{9,14}\d", contact_line)

        profile: dict[str, Any] = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "generated_at": timeutil.iso_now(),
            "resume": {"path": str(resume), "file_name": resume.name, "sha256": doc.sha256, "pages": doc.page_count, "parser": "pymupdf-rule-based"},
            "name": header[0].strip() if header else self.default_name,
            "configured_name": self.default_name,
            "contact": {
                "email": email.group(0) if email else None,
                "phone": phone.group(0).strip() if phone else None,
                "location": contact_line.split("|")[0].strip() if "|" in contact_line else self.default_location,
            },
            "headline": header[2].strip() if len(header) > 2 else None,
            "summary": " ".join(l.strip() for l in doc.sections.get("summary", [])),
            "skills": skills,
            "skills_listed_on_resume": listed_skills + technical_skills,
            "seed_skill_verification": seed_report,
            "experience": roles,
            "previous_companies": list(dict.fromkeys(r["company"] for r in roles if r["company"])),
            "total_experience": {},
            "education": education,
            "certifications": certifications,
            "projects": projects,
            "achievements": extract_achievements(roles, projects),
            "languages": languages,
            "warnings": warnings,
            "resume_text": doc.text,
        }
        self.refresh_experience(profile, today, intervals)
        log.info(
            "Candidate profile built: %d roles, %d skills, %.1f years experience.",
            len(roles), len(skills), profile["total_experience"]["years"],
        )
        return profile

    # -- helpers --
    def _skills(self, doc: ResumeDocument, listed: list[str], technical: list[str], certs: list[str]) -> list[dict[str, Any]]:
        skills: dict[str, dict[str, Any]] = {}
        for name in listed + technical + certs:
            canonical = self.taxonomy.canonical(name) or name
            skills.setdefault(canonical, {"name": canonical, "source": "resume_skills_section", "as_written": name, "evidence": name})
        for hit in self.taxonomy.find(doc.text):
            skills.setdefault(hit.skill, {"name": hit.skill, "source": "resume_text", "as_written": hit.alias, "evidence": hit.snippet})
        return list(skills.values())

    def _verify_seed_skills(self, text: str) -> list[dict[str, Any]]:
        report = []
        norm_text = normalize_text(text)
        for seed in self.seed_skills:
            canonical = self.taxonomy.canonical(seed)
            found = bool(canonical and canonical in self.taxonomy.skills_in(text)) or normalize_text(seed) in norm_text
            report.append({"skill": seed, "canonical": canonical or seed, "found_in_resume": found})
        return report

    def refresh_experience(self, profile: dict[str, Any], today: date, intervals: list[tuple[date, date]] | None = None) -> None:
        if intervals is None:
            intervals = []
            for r in profile.get("experience", []):
                start = date.fromisoformat(r["start"] + "-01")
                end = date(today.year, today.month, 1) if r.get("is_current") else date.fromisoformat(r["end"] + "-01")
                r["months"] = months_between(start, end)
                intervals.append((start, end))
        months = total_experience_months(intervals) if intervals else 0
        stated = self.stated_years
        years = round(months / 12, 1)
        note = None
        if stated is not None and months and abs(months / 12 - stated) >= 0.05 and months / 12 < stated:
            note = (
                f"Resume/config states {stated:g}+ years; employment dates add up to {months // 12} years "
                f"{months % 12} months ({years} years) as of {today.strftime('%b %Y')}. The date-based figure is used."
            )
        profile["total_experience"] = {
            "months": months,
            "years": years,
            "years_months": f"{months // 12} years {months % 12} months",
            "as_of": today.isoformat(),
            "method": "union of employment date ranges (overlaps counted once, months inclusive)",
            "merged_periods": [[s.strftime("%Y-%m"), e.strftime("%Y-%m")] for s, e in merge_intervals(intervals)],
            "stated_years": stated,
            "discrepancy_note": note,
        }


def profile_skill_names(profile: dict[str, Any]) -> list[str]:
    return [s["name"] for s in profile.get("skills", [])]


def current_role(profile: dict[str, Any]) -> dict[str, Any] | None:
    roles = profile.get("experience") or []
    current = [r for r in roles if r.get("is_current")]
    return current[0] if current else (roles[0] if roles else None)
