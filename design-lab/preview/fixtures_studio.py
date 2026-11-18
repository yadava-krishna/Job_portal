"""Sample responses for Resume Studio, Searches & companies and Onboarding (preview harness only).

Shapes mirror frontend/src/features/studio/api.ts and frontend/src/types/api.ts. Never touches the real backend.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_NOW = datetime.now(timezone.utc)


def _iso(days: float = 0, hours: float = 0) -> str:
    return (_NOW - timedelta(days=days, hours=hours)).isoformat()


# ---------------- Resume Studio ----------------

_FONTS = [{"key": "inter", "label": "Inter"}, {"key": "source_serif", "label": "Source Serif"}, {"key": "carlito", "label": "Carlito (Calibri-like)"}]


def _tpl(key, name, cat, ats, cols, desc, pages=2):
    return {"key": key, "name": name, "category": cat, "ats_safe": ats, "columns": cols, "description": desc, "max_pages": pages,
            "supports_docx": ats, "fonts": _FONTS, "heading_styles": ["caps_rule", "accent", "underline", "plain"],
            "date_formats": ["MMM YYYY", "MM/YYYY", "YYYY"],
            "defaults": {"font_family": "inter", "font_size": 10.5, "line_height": 1.3, "margin_mm": 16, "section_spacing": 1,
                         "heading_style": "caps_rule", "accent": "#1e3a5f", "date_format": "MMM YYYY", "page_size": "A4"}}


_TEMPLATES = [
    _tpl("ats_simple", "ATS Simple", "ats", True, 1, "One clean column that every applicant-tracking system reads correctly."),
    _tpl("modern_professional", "Modern Professional", "modern", False, 2, "Two columns with a coloured sidebar. Best when a person reads it first."),
    _tpl("technical", "Technical", "ats", True, 1, "Skills and projects up top, for engineering and data roles."),
    _tpl("finance", "Finance", "ats", True, 1, "Conservative serif layout that banks and audit firms expect."),
    _tpl("graduate", "Graduate", "ats", True, 1, "Education and projects first, for students and early-career roles.", 1),
    _tpl("executive", "Executive", "modern", False, 1, "Roomy summary and impact highlights for senior roles."),
    _tpl("international", "International", "ats", True, 1, "Adds a work-authorisation line for applications abroad."),
]


def _version(i, name, key, tname, ats, status, days, parent=None, job=None, rev=7):
    return {"id": i, "name": name, "template_key": key, "template_name": tname, "ats_safe": ats, "status": status,
            "locked_at": _iso(days) if status == "locked" else None, "revision": rev,
            "settings": {"font_size": 10.5, "page_size": "A4"}, "target_job_id": job, "parent_id": parent,
            "created_at": _iso(days + 3), "updated_at": _iso(days), "checksum": "9f2c1d"}


_VERSIONS = [
    _version(3, "Data analyst · fintech", "ats_simple", "ATS Simple", True, "draft", 0.08, parent=1, job=200),
    _version(4, "Product analyst · Swiggy", "technical", "Technical", True, "draft", 1.2, parent=3, job=202),
    _version(2, "Business analyst · Meesho", "ats_simple", "ATS Simple", True, "locked", 8, parent=1),
    _version(1, "Base resume", "modern_professional", "Modern Professional", False, "draft", 28),
]


def _b(text, source="profile", approved=True):
    return {"text": text, "evidence_refs": ["experience:0"] if source == "profile" else [], "source": source, "approved": approved}


_SECTIONS = [
    {"id": 1, "type": "header", "heading": "Contact", "visible": True, "blocks": [
        {"id": 11, "type": "contact", "source_profile_ref": "profile:contact", "visible": True, "bullets": [],
         "content": {"name": "Asha Rao", "headline": "Data analyst · SQL, Python and dashboards for payments teams",
                     "email": "asha.rao@example.com", "phone": "+91 98450 12345", "location": "Bengaluru, India",
                     "links": ["linkedin.com/in/asha-rao"]}}]},
    {"id": 2, "type": "summary", "heading": "Summary", "visible": True, "blocks": [
        {"id": 21, "type": "text", "source_profile_ref": "profile:summary", "visible": True, "bullets": [],
         "content": {"text": "Analyst with 3 years in fintech. I build the reporting that risk and growth teams decide with."}}]},
    {"id": 3, "type": "experience", "heading": "Experience", "visible": True, "blocks": [
        {"id": 31, "type": "entry", "source_profile_ref": "experience:0", "visible": True,
         "content": {"title": "Data Analyst", "organization": "Paytm", "start": "Apr 2023", "end": None, "current": True, "location": "Bengaluru"},
         "bullets": [_b("Built the merchant risk dashboard used by 40 analysts."),
                     _b("Cut weekly reporting time from 6 hours to 40 minutes by moving it to dbt and Tableau.", "suggestion")]},
        {"id": 32, "type": "entry", "source_profile_ref": "experience:1", "visible": True,
         "content": {"title": "Analytics Intern", "organization": "Zeta", "start": "Jun 2022", "end": "Mar 2023", "current": False, "location": "Bengaluru"},
         "bullets": [_b("Automated card-spend cohort reports in Python.")]}]},
    {"id": 4, "type": "education", "heading": "Education", "visible": True, "blocks": [
        {"id": 41, "type": "entry", "source_profile_ref": "education:0", "visible": True, "bullets": [],
         "content": {"title": "B.Com (Hons)", "organization": "Christ University", "start": "2019", "end": "2022", "current": False}}]},
    {"id": 5, "type": "skills", "heading": "Skills", "visible": True, "blocks": [
        {"id": 51, "type": "skill_group", "source_profile_ref": "profile:skills", "visible": True, "bullets": [],
         "content": {"label": "Analytics", "items": ["SQL", "Python", "Pandas", "Tableau", "Excel", "A/B testing", "Statistics"]}}]},
    {"id": 6, "type": "projects", "heading": "Projects", "visible": False, "blocks": [
        {"id": 61, "type": "entry", "source_profile_ref": "projects:0", "visible": True,
         "content": {"title": "UPI fraud explorer", "organization": "", "start": "2024", "end": "", "current": False},
         "bullets": [_b("Streamlit app over 2M public transactions.")]}]},
]

_V3 = {**_VERSIONS[0], "sections": _SECTIONS}

_LAYOUT = {"pages": 2, "page_fill": [0.96, 0.14], "settings": {},
           "warnings": [{"level": "warning", "message": "The last page is only about 14% full."},
                        {"level": "info", "message": "Projects is hidden, so it isn't on the page."}],
           "fit_suggestions": [{"label": "Slightly tighter spacing", "settings": {"section_spacing": 0.9, "line_height": 1.25}, "pages": 1}]}

_FEEDBACK = {"resume_version_id": 3, "job_id": None, "pages": 2, "readiness": 82, "ats_safe_template": True,
             "score_method": "18 of 22 layout and wording checks pass.",
             "note": "Checks run on the exported PDF, so they see what an employer's system sees.",
             "issues": [
                 {"level": "warning", "code": "last_page", "kind": "format", "message": "The second page is mostly empty.", "where": None},
                 {"level": "warning", "code": "figure", "kind": "accuracy", "message": "“6 hours to 40 minutes” isn't in your confirmed profile.", "where": {"section": "experience", "block": 0, "bullet": 1}},
                 {"level": "suggestion", "code": "verb", "kind": "writing", "message": "Start with a stronger verb than “Automated”.", "where": {"section": "experience", "block": 1, "bullet": 0}},
                 {"level": "info", "code": "job", "kind": "job", "message": "Covers 5 of 6 skills listed in the job.", "where": None},
             ]}

_SUGGESTIONS = [
    {"id": "w3-0-0", "kind": "rewrite", "where": {"section": 2, "block": 0, "bullet": 0},
     "before": "Built the merchant risk dashboard used by 40 analysts.",
     "after": "Built the merchant risk dashboard that 40 analysts use to approve payouts daily.",
     "evidence": "unknown", "reason": "Says what the dashboard is for. Check the detail is true before accepting."},
    {"id": "s4", "kind": "add_skill", "where": {"section": 4, "block": 0}, "before": None, "after": "dbt", "skill": "dbt",
     "evidence": "supported", "reason": "Listed in your profile and asked for in this job."},
]

# ---------------- Searches & companies ----------------

_CRIT = {"keywords": [], "exclude_keywords": [], "locations": [], "remote_ok": True, "industries": [], "experience_years": None,
         "employment_types": [], "work_modes": [], "company_ids": [], "use_watchlist": True, "include_suggested": True, "related_titles": True,
         "sources": ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "remote_feeds"], "max_age_days": None}


def _run(i, status, found, new, matched, summary, hours, results=None):
    return {"id": i, "trigger": "saved_search", "status": status, "sources": ["greenhouse", "lever"], "started_at": _iso(hours=hours + 0.1),
            "completed_at": _iso(hours=hours), "jobs_found": found, "jobs_new": new, "jobs_matched": matched, "duplicates": max(found - new, 0),
            "error_details": [], "platform_stats": {}, "source_results": results or {}, "summary": summary}


_SEARCHES = [
    {"id": 1, "name": "Your preferred roles", "origin": "starter", "criteria": _CRIT, "schedule": "daily", "min_match_score": None, "enabled": True,
     "created_at": _iso(29), "updated_at": _iso(29), "last_run_at": _iso(hours=3), "next_run_at": _iso(-0.8),
     "last_run": _run(40, "completed", 38, 12, 9, "Checked 64 company boards and 4 remote feeds. 38 matching jobs: 12 new.", 3)},
    {"id": 2, "name": "Product analyst · Bengaluru", "origin": "user",
     "criteria": {**_CRIT, "keywords": ["Product Analyst", "Growth Analyst"], "locations": ["Bengaluru"], "industries": ["Fintech", "E-commerce"]},
     "schedule": "daily", "min_match_score": 75, "enabled": True, "created_at": _iso(12), "updated_at": _iso(4), "last_run_at": _iso(hours=5),
     "next_run_at": _iso(-0.7),
     "last_run": _run(41, "partial", 9, 3, 2, "9 matching jobs: 3 new. 2 boards couldn't be read.", 5, {
         "greenhouse": {"label": "Greenhouse", "status": "ok", "message": None, "found": 7, "new": 3, "duplicates": 4, "failed_requests": 0, "boards_ok": 22, "listings_checked": 1840},
         "lever": {"label": "Lever", "status": "partial", "message": "2 boards could not be read: Dunzo (board not found), Slice (timed out).", "found": 2, "new": 0, "duplicates": 2, "failed_requests": 2, "boards_ok": 9, "boards_failed": 2},
     })},
    {"id": 3, "name": "Remote data roles", "origin": "user",
     "criteria": {**_CRIT, "keywords": ["Data Analyst"], "locations": ["Remote - India"], "work_modes": ["Remote"], "sources": ["remote_feeds", "greenhouse"], "include_suggested": False},
     "schedule": "weekly", "min_match_score": None, "enabled": False, "created_at": _iso(20), "updated_at": _iso(6), "last_run_at": _iso(6),
     "next_run_at": None, "last_run": _run(33, "completed", 4, 1, 1, "4 matching jobs: 1 new.", 6 * 24)},
]


def _co(i, name, ats, token, industry, status, jobs, hours, err=None):
    url = {"greenhouse": f"https://job-boards.greenhouse.io/{token}", "lever": f"https://jobs.lever.co/{token}",
           "ashby": f"https://jobs.ashbyhq.com/{token}"}.get(ats, f"https://careers.smartrecruiters.com/{token}")
    return {"id": i, "name": name, "ats": ats, "board_token": token, "region": "IN", "industry": industry, "domain": None, "origin": "curated",
            "board_url": url, "last_fetched_at": _iso(hours=hours) if status else None, "last_status": status, "last_error": err, "job_count": jobs}


_WATCHLIST = [
    _co(1, "PhonePe", "ashby", "phonepe", "Fintech", "ok", 42, 3),
    _co(2, "Razorpay", "lever", "razorpay", "Fintech", "ok", 57, 3),
    _co(3, "Swiggy", "greenhouse", "swiggy", "E-commerce", "ok", 31, 3),
    _co(4, "Zerodha", "greenhouse", "zerodha", "Fintech", "empty", 0, 3),
    _co(5, "Dunzo", "lever", "dunzo", "E-commerce", "not_found", None, 5, "The Lever board 'dunzo' returned 404."),
    _co(6, "Slice", "lever", "slice", "Fintech", "error", None, 5, "Timed out after 20 s."),
    _co(7, "Groww", "greenhouse", "groww", "Fintech", None, None, 0),
]


def _dir(name, ats, token, industry, watched=False):
    return {"name": name, "ats": ats, "token": token, "industry": industry, "domain": None, "curated": True, "company_id": None, "watched": watched}


_SUGGESTED = [
    _dir("PhonePe", "ashby", "phonepe", "Fintech", True), _dir("CRED", "lever", "cred", "Fintech"),
    _dir("Meesho", "greenhouse", "meesho", "E-commerce"), _dir("Postman", "greenhouse", "postman", "SaaS"),
    _dir("Freshworks", "smartrecruiters", "freshworks", "SaaS"), _dir("Zeta", "lever", "zeta", "Fintech"),
    _dir("Groww", "greenhouse", "groww", "Fintech", True),
]

_CONNECTORS = [
    {"source_id": "greenhouse", "name": "Greenhouse", "domain": "boards-api.greenhouse.io", "category": "ats_api", "access_method": "api",
     "permission_status": "public_api", "is_discoverable": True, "status": "ok", "rate_limit_rpm": 60, "last_success_at": _iso(hours=3), "last_error": None, "jobs_discovered": 512},
    {"source_id": "lever", "name": "Lever", "domain": "api.lever.co", "category": "ats_api", "access_method": "api",
     "permission_status": "public_api", "is_discoverable": True, "status": "degraded", "rate_limit_rpm": 60, "last_success_at": _iso(hours=5), "last_error": "2 boards failed", "jobs_discovered": 341},
    {"source_id": "remotive", "name": "Remotive", "domain": "remotive.com", "category": "remote_feed", "access_method": "rss",
     "permission_status": "public_feed", "is_discoverable": True, "status": "ok", "rate_limit_rpm": 10, "last_success_at": _iso(hours=3), "last_error": None, "jobs_discovered": 88},
    {"source_id": "adzuna", "name": "Adzuna", "domain": "api.adzuna.com", "category": "job_api", "access_method": "api",
     "permission_status": "needs_key", "is_discoverable": False, "status": "unknown", "rate_limit_rpm": 25, "last_success_at": None, "last_error": None, "jobs_discovered": 0},
]


def _health(key, label, kind, conn, jobs, hours=None, boards=None, missing=None, err=None, enabled=True, configured=True):
    return {"key": key, "label": label, "kind": kind, "enabled": enabled, "configured": configured, "missing": missing, "connection": conn,
            "last_attempt_at": _iso(hours=hours) if hours is not None else None, "last_success_at": _iso(hours=hours) if hours is not None and conn != "failing" else None,
            "last_error": err, "jobs_in_feed": jobs, "boards": boards, "last_run": None}


_SOURCES = {
    "saved_searches": 3, "enabled_searches": 2,
    "last_run": _run(40, "completed", 1284, 38, 46, "Checked 64 company boards and 4 remote feeds. 38 new jobs.", 3),
    "sources": [
        _health("greenhouse", "Greenhouse job boards", "ats", "ok", 512, 3, {"total": 28, "ok": 28, "failing": 0, "unchecked": 0}),
        _health("lever", "Lever job boards", "ats", "degraded", 341, 5, {"total": 14, "ok": 12, "failing": 2, "unchecked": 0}),
        _health("ashby", "Ashby job boards", "ats", "ok", 220, 3, {"total": 9, "ok": 9, "failing": 0, "unchecked": 0}),
        _health("remote_feeds", "Remote job feeds", "api", "ok", 88, 3),
        _health("adzuna_api", "Adzuna Jobs API", "api", "not_configured", 0, None, None,
                "Server credentials are missing: set ADZUNA_APP_ID and ADZUNA_APP_KEY in the backend's .env and restart it.", configured=False, enabled=False),
        _health("email_alerts", "Job alert e-mails", "email", "unknown", 14, None),
    ],
}

FIXTURES: dict[str, object] = {
    "/api/v1/studio/templates": _TEMPLATES,
    "/api/v1/studio/versions": _VERSIONS,
    "/api/v1/studio/versions/3": _V3,
    "/api/v1/studio/versions/3/layout": _LAYOUT,
    "/api/v1/studio/versions/3/feedback": _FEEDBACK,
    "/api/v1/studio/versions/3/suggestions": _SUGGESTIONS,
    "/api/v1/saved-searches": _SEARCHES,
    "/api/v1/companies/watchlist": _WATCHLIST,
    "/api/v1/companies/suggested": _SUGGESTED,
    "/api/v1/companies/directory": _SUGGESTED[:4],
    "/api/v1/discovery/connectors": _CONNECTORS,
    "/api/v1/discovery/sources": _SOURCES,
}
