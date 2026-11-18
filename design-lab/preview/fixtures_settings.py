"""Sample responses for the Settings page (preview harness only; never touches the real backend)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_NOW = datetime.now(timezone.utc)


def _iso(days: float = 0, hours: float = 0) -> str:
    return (_NOW - timedelta(days=days, hours=hours)).isoformat()


_PROFILE = {
    "full_name": "Asha Rao", "email": "asha.rao@example.com", "phone": "+91 98450 12345", "location": "Bengaluru, India",
    "headline": "Data analyst · SQL, Python and dashboards for payments teams",
    "summary": "Analyst with 3 years in fintech. I build the reporting that risk and growth teams decide with, and I like turning messy data into one clear chart.",
    "skills": ["SQL", "Python", "Pandas", "Tableau", "Excel", "A/B testing", "Statistics"],
    "experience": [
        {"title": "Data Analyst", "company": "Paytm", "start": "2023-04", "end": None, "is_current": True,
         "bullets": ["Built the merchant risk dashboard used by 40 analysts.", "Cut weekly reporting time from 6 hours to 40 minutes."]},
        {"title": "Analytics Intern", "company": "Zeta", "start": "2022-06", "end": "2023-03", "is_current": False,
         "bullets": ["Automated card-spend cohort reports in Python."]},
    ],
    "education": [{"degree": "B.Com (Hons)", "institution": "Christ University", "university": "Christ University", "year": 2022}],
    "certifications": ["Google Data Analytics"], "projects": [{"name": "UPI fraud explorer", "bullets": ["Streamlit app over 2M public transactions."]}],
    "achievements": ["Analyst of the quarter, Q2 2025"], "languages": ["English", "Hindi", "Kannada"],
    "linkedin_url": "https://www.linkedin.com/in/asha-rao", "github_url": None, "portfolio_url": None, "website_url": None,
}

_RESUME = {"id": 3, "original_filename": "asha_rao_data_analyst.pdf", "size_bytes": 184_320, "page_count": 2, "sha256": "",
           "uploaded_at": _iso(29), "is_active": True}

_PREFERENCES = {
    "domains": ["Analytics", "Finance"], "industries": ["BFSI", "E-commerce"], "job_titles": ["Data Analyst", "Business Analyst", "Product Analyst"],
    "title_keywords": ["MIS"], "locations": ["Bengaluru", "Remote - India"], "work_modes": ["Remote", "Hybrid"],
    "salary_min": 1_200_000, "salary_max": 2_000_000, "currency": "INR", "experience_min": 1, "experience_max": 4,
    "employment_types": ["Full-time"], "notice_period": "30 days", "preferred_companies": ["PhonePe", "Razorpay"],
    "excluded_companies": [], "min_match_score": 70,
    "weights": {"core_skills": 35, "experience": 25, "responsibilities": 20, "education": 10, "location": 10},
    "application_settings": {"approval_required": True, "cover_letter": "when_required", "max_prepared_per_day": 25},
    "is_configured": True,
}


def _platform(name: str, enabled: bool, sources: list[tuple[str, str]], chosen: list[str], api: bool, notes: str, method: str) -> dict:
    return {"platform": name, "enabled": enabled, "discovery_sources": chosen,
            "available_sources": [{"id": i, "label": l} for i, l in sources], "automated_search": api,
            "automated_apply": False, "application_method": method, "notes": notes}


_CLIP = [("browser_clipper", "Browser job clipper (pages you open yourself)"), ("user_job_url", "Paste a job link")]

FIXTURES: dict[str, object] = {
    "/api/v1/profile": {"has_resume": True, "resume": _RESUME, "parsed": _PROFILE, "confirmed": _PROFILE, "confirmed_at": _iso(28),
                        "experience": {"months": 43, "years": 3, "years_months": "3 years 7 months", "merged_periods": [], "method": "dates", "note": None},
                        "parse_warnings": [],
                        "verified_facts": {"expected_ctc": "16-18 LPA", "notice_period": "30 days", "earliest_start_date": "1 Jan 2027",
                                           "work_authorization": "Indian citizen", "requires_sponsorship": False, "willing_to_relocate": True,
                                           "relevant_experience": "3 years in fintech analytics",
                                           "custom_answers": [
                                               {"question": "Are you comfortable working from office three days a week?", "answer": "Yes, Bengaluru office works for me.", "applies_to": "any", "updated_at": _iso(6)},
                                               {"question": "Why do you want to join us?", "answer": "Your risk team's public talks on UPI fraud.", "applies_to": "one_job", "note": "PhonePe", "updated_at": _iso(2)},
                                           ]}},
    "/api/v1/profile/resumes": [
        _RESUME,
        {"id": 2, "original_filename": "asha_rao_business_analyst.pdf", "size_bytes": 172_032, "page_count": 1, "sha256": "", "uploaded_at": _iso(40), "is_active": False},
    ],
    "/api/v1/preferences": _PREFERENCES,
    "/api/v1/platforms": [
        _platform("Greenhouse", True, [("greenhouse", "Company job boards (official API)")], ["greenhouse"], True, "Public job boards of companies that use Greenhouse.", "employer form, filled by Smart Apply"),
        _platform("Lever", True, [("lever", "Company job boards (official API)")], ["lever"], True, "Public postings of companies that use Lever.", "employer form, filled by Smart Apply"),
        _platform("LinkedIn", True, _CLIP + [("alert_email", "Your LinkedIn job-alert e-mails")], ["browser_clipper", "alert_email"], False, "Only pages you open yourself, or your own alert e-mails.", "on LinkedIn, by you"),
        _platform("Naukri", False, _CLIP, ["browser_clipper", "user_job_url"], False, "Only pages you open yourself.", "on Naukri, by you"),
        _platform("Adzuna", False, [], [], True, "Needs an Adzuna API key on the server.", "on the employer's site"),
    ],
    "/api/v1/career-goals": {"search_mode": "both", "target_countries": ["GB", "AE"], "seniority": "mid", "open_to_relocation": True,
                             "work_authorization": ["IN"], "needs_sponsorship": True},
    "/api/v1/countries": [
        {"code": c, "name": n, "region": r, "currency": cur, "official_source_url": None, "routes": k}
        for c, n, r, cur, k in [("IN", "India", "Asia", "INR", 0), ("GB", "United Kingdom", "Europe", "GBP", 3), ("AE", "United Arab Emirates", "Middle East", "AED", 2),
                                ("DE", "Germany", "Europe", "EUR", 3), ("SG", "Singapore", "Asia", "SGD", 2)]
    ],
    "/api/v1/consents": [
        {"kind": "ai_processing", "granted": True, "text": "Use AI to suggest resume wording and answers. You review everything before it is used.", "granted_at": _iso(25), "revoked_at": None},
        {"kind": "learning_tracking", "granted": False, "text": "Record the time you spend on learning tasks so your plan can adapt.", "granted_at": None, "revoked_at": None},
        {"kind": "mentor_sharing", "granted": False, "text": "Let a mentor you invite see your applications and progress.", "granted_at": None, "revoked_at": _iso(10)},
        {"kind": "extension", "granted": True, "text": "Let the Smart Apply extension read application forms you open and fill them from your profile.", "granted_at": _iso(20), "revoked_at": None},
        {"kind": "email_notifications", "granted": False, "text": "Send reminders to your e-mail address.", "granted_at": None, "revoked_at": None},
    ],
    "/api/v1/notifications/preferences": {"new_matches": True, "delivery": "daily_digest", "min_score": 75, "sources": ["greenhouse", "lever"], "email": "off",
                                          "kinds": {"new_match": True, "follow_up_due": True, "interview_upcoming": True, "application_incomplete": False,
                                                    "listing_closed": True, "discovery_failed": True}},
    "/api/v1/integrations/email": {"enabled": True, "imap_host": "imap.gmail.com", "imap_port": 993, "username": "asha.rao@example.com", "has_password": True,
                                   "folder": "INBOX", "lookback_days": 2, "last_checked_at": _iso(hours=1), "last_error": None},
    "/api/v1/extension/devices": [
        {"id": 3, "name": "Chrome on laptop", "scopes": [], "created_at": _iso(12), "last_used_at": _iso(hours=5), "expires_at": _iso(-78)},
    ],
}
