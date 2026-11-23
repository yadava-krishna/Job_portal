"""Resume Studio checks that work on the exported PDF itself (the exact revision the user sees and sends).

Three things are verified, each reported against the entry and field it concerns:

1. Characters. Text that can't be printed: the replacement character U+FFFD and Private Use code points (left by
   resumes made with Symbol/Wingdings bullets) print as boxes; characters no embedded font can draw (emoji) are
   silently dropped. Found in the source text and confirmed in the PDF's own glyph trace.
2. Read-back. Every visible field (title, employer, location, dates, each bullet, summary, skills) must be found in
   the PDF's extracted text. Comparison uses core.textclean.fold, so "–" vs "-" or curly vs straight quotes never
   count as a difference.
3. Association. JobPilot's own resume parser reads the PDF the way an applicant-tracking system might; each
   experience entry is matched to a parsed role by its dates (never by title), and the finding says when the title
   or employer came out attached to the wrong entry. Locations are never taken for titles (resume.profile_builder
   .is_location).

Issues carry a stable id (from what they are about, not list positions), the section/entry/field, a severity, an
explanation, the evidence and a suggested fix. Issues with the same cause on the same field are reported once.
No AI, no network.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Any

from core.textclean import fold, unreadable

# Part of every export's cache key: a renderer change re-renders cached previews instead of serving a stale PDF
# whose page count disagrees with a fresh check.
RENDERER_VERSION = "studio-render-2026.11.23b"  # b: inline bullets (extraction order)

_SYMBOLS = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF]")
LEVEL_POINTS = {"error": 25, "warning": 8, "suggestion": 3, "info": 0}  # notes never lower Resume Quality

FIELD_LABEL = {"title": "title", "organization": "employer", "location": "location", "dates": "dates", "text": "text",
               "items": "skills", "bullet": "bullet", "name": "name", "email": "e-mail", "phone": "phone", "detail": "detail"}


def entry_label(content: dict[str, Any]) -> str:
    parts = [str(content.get(k) or "").strip() for k in ("title", "organization")]
    return " — ".join(p for p in parts if p) or "(untitled entry)"


def issue(code: str, level: str, kind: str, message: str, *, section: str | None = None, block: int | None = None,
          bullet: int | None = None, field: str | None = None, entry: str | None = None, why: str = "", evidence: str = "",
          fix: str = "", key: str = "") -> dict[str, Any]:
    """One finding. `key` identifies what it is about (e.g. the entry's title+employer+start, the bullet text), so
    the id stays the same across re-checks and reorders."""
    ident = hashlib.sha1(f"{code}|{section}|{field}|{key or message}".encode()).hexdigest()[:10]
    where = {"section": section, "block": block, "bullet": bullet, "field": field} if section else None
    return {"id": f"{code}-{ident}", "code": code, "level": level, "kind": kind, "message": message, "where": where,
            "entry": entry, "why": why, "evidence": evidence, "fix": fix}


def dedupe(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One issue per id (same cause, same place). Different causes on the same field stay separate."""
    seen: dict[str, dict[str, Any]] = {}
    for i in issues:
        if i["id"] in seen:
            prev = seen[i["id"]]
            prev["count"] = prev.get("count", 1) + 1
        else:
            seen[i["id"]] = i
    return list(seen.values())


def quality_score(issues: list[dict[str, Any]]) -> int:
    """Resume Quality: 100 minus 25 per must-fix, 8 per worth-fixing, 3 per suggestion. Notes (info) and job-coverage
    findings don't count: job coverage is the separate Resume–Job Alignment."""
    return max(0, 100 - sum(LEVEL_POINTS[i["level"]] for i in issues if i["kind"] != "job"))


# ---- reading the PDF ---------------------------------------------------------------------------------------------

def inspect_pdf(pdf: bytes) -> dict[str, Any]:
    """Pages, extracted text, and which characters the PDF actually draws with a real glyph."""
    import pymupdf

    doc = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        texts, drawn, notdef = [], set(), set()
        for page in doc:
            texts.append(page.get_text())
            for span in page.get_texttrace():
                for ch in span.get("chars", ()):
                    (notdef if ch[1] == 0 else drawn).add(chr(ch[0]))
        return {"pages": doc.page_count, "text": "\n".join(texts), "drawn": drawn, "notdef": notdef}
    finally:
        doc.close()


def _fields(doc: dict[str, Any]):
    """(section type, block index, bullet index or None, field, text, entry label, stable key) for every visible
    printable value."""
    for s in doc["sections"]:
        if not s.get("visible", True):
            continue
        for bi, b in enumerate(s["blocks"]):
            if not b.get("visible", True):
                continue
            c = b.get("content") or {}
            label = entry_label(c) if b["type"] == "entry" else s.get("heading") or s["type"]
            base = f"{s['type']}|{c.get('title')}|{c.get('organization')}|{c.get('start')}"
            if b["type"] == "contact":
                for f in ("name", "email", "phone", "location"):
                    if c.get(f):
                        yield s["type"], bi, None, f, str(c[f]), "Contact", f"contact|{f}"
            elif b["type"] == "text":
                if c.get("text"):
                    yield s["type"], bi, None, "text", str(c["text"]), s.get("heading") or "Summary", f"{s['type']}|text"
            elif b["type"] == "skill_group":
                for it in c.get("items") or []:
                    if str(it).strip():
                        yield s["type"], bi, None, "items", str(it), s.get("heading") or "Skills", f"{base}|skill|{it}"
            elif b["type"] == "entry":
                for f in ("title", "organization", "location", "detail"):
                    if c.get(f):
                        yield s["type"], bi, None, f, str(c[f]), label, base
            for ui, u in enumerate(b.get("bullets") or []):
                if u.get("approved", True) and (u.get("text") or "").strip():
                    yield s["type"], bi, ui, "bullet", u["text"], label, f"{base}|bullet|{fold(u['text'])[:80]}"


def character_findings(doc: dict[str, Any], pdf_info: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    drawn = pdf_info["drawn"]
    for sec, bi, ui, field, text, label, key in _fields(doc):
        bad = unreadable(text)
        if bad:
            shown = " ".join(f"U+{ord(c):04X}" for c in bad)
            out.append(issue("unreadable_chars", "error", "format", f"{label}: {FIELD_LABEL.get(field, field)} has characters that print as boxes.",
                             section=sec, block=bi, bullet=ui, field=field, entry=label, key=key,
                             why="These code points (often bullets from a Word resume's Symbol font, or a character lost when "
                                 "a PDF was read) have no printable shape. The PDF shows a box, and application systems read garbage.",
                             evidence=f"{shown} in: “{text[:90]}”", fix="Retype the character, or delete it if it was a bullet mark."))
            continue
        dropped = sorted({ch for ch in text if ord(ch) > 0x2FF and not ch.isspace() and ch not in drawn and ch not in "•"})
        symbols = sorted(set(_SYMBOLS.findall(text)))
        if symbols and not dropped:
            out.append(issue("unsupported_chars", "warning", "format", f"{label}: emoji or symbols ({' '.join(symbols[:5])}) in the {FIELD_LABEL.get(field, field)}.",
                             section=sec, block=bi, bullet=ui, field=field, entry=label, key=key,
                             why="They print here, but many application systems drop them or show boxes.",
                             evidence=f"“{text[:90]}”", fix="Use words or plain punctuation instead."))
            continue
        if dropped and fold(text) not in fold(pdf_info["text"]):
            out.append(issue("dropped_chars", "warning", "format", f"{label}: {' '.join(dropped[:5])} doesn't appear in the PDF.",
                             section=sec, block=bi, bullet=ui, field=field, entry=label, key=key,
                             why="No font in the resume can draw these characters (usually emoji or rare symbols), so they are left out.",
                             evidence=f"In the editor: “{text[:90]}”", fix="Use words or plain punctuation instead."))
    return out


def readback_findings(doc: dict[str, Any], pdf_info: dict[str, Any], skip: set[tuple]) -> list[dict[str, Any]]:
    """Fields whose text isn't in the exported PDF's extracted text (`skip`: places already reported for characters)."""
    have = fold(pdf_info["text"])
    out = []
    for sec, bi, ui, field, text, label, key in _fields(doc):
        if (sec, bi, ui, field) in skip:
            continue
        want = fold(text)
        if field == "bullet" or field == "text":
            want = want[:60]  # long text wraps across lines; its start is enough to know it's there
        if want and want not in have:
            out.append(issue("export_readback", "error", "format", f"{label}: the {FIELD_LABEL.get(field, field)} can't be read back from the PDF.",
                             section=sec, block=bi, bullet=ui, field=field, entry=label, key=key,
                             why="Text that can't be extracted from the PDF is invisible to application systems.",
                             evidence=f"Looked for “{text[:80]}” in the exported PDF's text.",
                             fix="Check this field for unusual characters, then export again."))
    return out


def _ym(value: Any) -> str | None:
    from backend.services.studio_render import format_date

    t = format_date(value, "MM/YYYY") if value else ""
    m = re.fullmatch(r"(\d{2})/(\d{4})", t or "")
    return f"{m.group(2)}-{m.group(1)}" if m else None


def association_findings(doc: dict[str, Any], pdf: bytes) -> list[dict[str, Any]]:
    """How JobPilot's parser groups each experience entry's title, employer and dates when it reads the PDF."""
    from core.settings import PROJECT_ROOT
    from core.skills import SkillTaxonomy
    from resume.profile_builder import ResumeProfileExtractor

    exp = next((s for s in doc["sections"] if s["type"] == "experience" and s.get("visible", True)), None)
    entries = [(bi, b.get("content") or {}) for bi, b in enumerate((exp or {}).get("blocks") or [])
               if b.get("visible", True) and b["type"] == "entry" and (b.get("content") or {}).get("title")]
    if not entries:
        return []
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "resume.pdf"
        path.write_bytes(pdf)
        try:
            parsed = ResumeProfileExtractor(SkillTaxonomy.from_file(PROJECT_ROOT / "config" / "skills_taxonomy.yaml")).build(path)
        except Exception as exc:  # noqa: BLE001 - a parser failure is itself the finding
            return [issue("parse_failed", "warning", "format", "JobPilot's resume reader couldn't read the exported PDF.",
                          section="experience", why="If JobPilot can't read it, some application systems may not either.",
                          evidence=type(exc).__name__, fix="Try the Classic ATS template.", key="parse")]
    roles = parsed.get("experience") or []
    out = []
    for bi, c in entries:
        label = entry_label(c)
        start = _ym(c.get("start"))
        key = f"experience|{c.get('title')}|{c.get('organization')}|{c.get('start')}"
        end = _ym(c.get("end"))
        if not start or (end and not c.get("current") and end < start):
            continue  # no dates, or reversed ones: reported by the date checks, nothing to associate by
        same = [r for r in roles if r.get("start") == start]
        if not same:
            out.append(issue("entry_dates_unread", "warning", "format", f"{label}: its dates weren't recognised when the PDF was read.",
                             section="experience", block=bi, field="dates", entry=label, key=key,
                             why="Systems that can't find an entry's dates can't count your experience.",
                             evidence=f"No role starting {start} among {len(roles)} read from the PDF.",
                             fix="Use month and year (e.g. Jan 2022) for start and end."))
            continue
        r = min(same, key=lambda x: 0 if fold(x.get("title")) == fold(c.get("title")) else 1)
        title_ok = fold(c.get("title")) in fold(r.get("title")) or fold(c.get("title")) in fold(r.get("header_raw"))
        if not title_ok:
            got = r.get("title") or "nothing"
            out.append(issue("entry_title_unread", "warning", "format", f"{label}: read back with the title “{got}”.",
                             section="experience", block=bi, field="title", entry=label, key=key,
                             why="A system that pairs the wrong line with these dates files your experience under the wrong job title.",
                             evidence=f"Role dated {r.get('date_text') or start} came out as title “{got}”, employer “{r.get('company') or '—'}”.",
                             fix="Keep the title on its own line directly above the dates (all JobPilot templates do); "
                                 "avoid line breaks inside the title."))
        org = c.get("organization")
        if title_ok and org and fold(org) not in fold(f"{r.get('company')} {r.get('header_raw')}"):
            out.append(issue("entry_employer_unread", "info", "format", f"{label}: the employer was read as “{r.get('company') or '—'}”.",
                             section="experience", block=bi, field="organization", entry=label, key=key,
                             why="Some systems pair the employer with the wrong line.", evidence=f"Header read: “{r.get('header_raw')}”.",
                             fix="Usually fine to leave; check the employer field has nothing else in it."))
    return out


# ---- Resume–Job Alignment ---------------------------------------------------------------------------------------

ALIGNMENT_METHOD = ("Resume–Job Alignment: of the skills this job lists (required count twice, preferred once), the share "
                    "that appears on this resume version. Only what is printed on the resume counts. Skills that are in your "
                    "verified profile but not on this resume are shown as things you could add; skills you have no evidence "
                    "for are shown as gaps and are never added for you.")


def alignment(doc: dict[str, Any], job, profile_skills: set[str], profile_text: str, canon) -> dict[str, Any]:
    """{score, method, matched, addable, gaps} for one job. `canon(text)` -> canonical skill names in the text."""
    from core.textclean import fold as f

    resume_text = " ".join(x[4] for x in _fields(doc))
    on_resume = set(canon(resume_text))
    low_resume = f(resume_text)
    req = [s for s in (job.required_skills or []) if s]
    pref = [s for s in (job.preferred_skills or []) if s and s not in req]
    total = 2 * len(req) + len(pref)
    if not total:
        return {"score": None, "method": ALIGNMENT_METHOD, "matched": [], "addable": [], "gaps": [],
                "note": "This job lists no skills, so alignment can't be measured."}
    matched, addable, gaps, got = [], [], [], 0
    for weight, items in ((2, req), (1, pref)):
        for s in items:
            names = canon(s) | {s.lower()}
            if names & on_resume or f(s) in low_resume:
                matched.append({"skill": s, "required": weight == 2})
                got += weight
            elif names & {p.lower() for p in profile_skills} or f(s) in f(profile_text):
                addable.append({"skill": s, "required": weight == 2})
            else:
                gaps.append({"skill": s, "required": weight == 2})
    return {"score": round(100 * got / total), "method": ALIGNMENT_METHOD, "matched": matched, "addable": addable, "gaps": gaps}
