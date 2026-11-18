"""Sample data for the Applications, application detail, Apply dialog and Reports previews (no real data)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

NOW = datetime.now(timezone.utc)


def iso(days: float = 0, hours: float = 0) -> str:
    return (NOW - timedelta(days=days, hours=hours)).isoformat()


def job(i: int, company: str, title: str, platform: str, loc: str = "Bengaluru", url: str | None = "https://job-boards.greenhouse.io/x/jobs/1") -> dict:
    return {"id": 300 + i, "platform": platform, "external_job_id": str(i), "company": company, "title": title, "location": loc,
            "work_mode": "Hybrid", "employment_type": "Full-time", "experience_required": "0-2 years", "salary_range": None,
            "job_url": url, "posted_at": None, "posted_at_source": None, "posted_label": "", "description_preview": None,
            "has_full_description": True, "source": platform.lower(), "posted_at_confidence": "verified", "first_seen_at": iso(30),
            "last_verified_at": iso(1), "closed_at": None, "industry": "Fintech", "department": "Analytics", "sources": []}


# (id, company, title, platform, status, stage, days since submitted, score, follow-up offset days, apply_state, reference)
ROWS = [
    (25, "Groww", "Data Analyst", "Greenhouse", "SUBMITTED", "interview", 12, 86, None, "submitted_confirmed", "GRW-20419"),
    (28, "Meesho", "Business Analyst", "Lever", "SUBMITTED", "applied", 8, 81, -1, None, None),
    (22, "Zeta", "Analyst, Risk Platform", "Ashby", "SUBMITTED", "offer", 20, 78, None, None, "ZT-8812"),
    (29, "Juspay", "Data Analyst, Payments", "Lever", "SUBMITTED", "screening", 5, 83, 3, "submitted_confirmed", None),
    (30, "Slice", "Product Analyst", "Greenhouse", "SUBMITTED", "assessment", 9, 77, None, None, None),
    (27, "Paytm", "Reporting Analyst", "SmartRecruiters", "SUBMITTED", "rejected", 24, 69, None, None, None),
    (26, "Dream11", "Analytics Associate", "Greenhouse", "SUBMITTED", "applied", 3, 74, None, None, None),
    (24, "Navi", "Junior Data Analyst", "Ashby", "SUBMITTED", "screening", 15, 80, None, None, None),
    (31, "Swiggy", "Product Analyst", "Greenhouse", "CONFIRMATION_PENDING", None, None, 84, None, "submission_uncertain", None),
    (32, "PhonePe", "Data Analyst, Payments Risk", "Ashby", "OPENED", None, None, 91, None, "ready_for_review", None),
    (33, "Razorpay", "Business Analyst, Growth", "Lever", "PREPARED", None, None, 88, None, None, None),
    (21, "Ola", "MIS Analyst", "Greenhouse", "WITHDRAWN", "withdrawn", 40, 62, None, None, None),
]

STATE_LABELS = {"submitted_confirmed": "Submitted (confirmed)", "submission_uncertain": "Submission uncertain: please check",
                "ready_for_review": "Ready for review", "filling": "Filling"}


def app(r: tuple) -> dict:
    aid, company, title, platform, status, stage, days, score, fu, state, ref = r
    created = (days or 1) + 1
    return {
        "id": aid, "status": status, "stage": stage, "user_job_id": 100 + aid, "match_score": score,
        "match_category": "strong" if score >= 85 else "good", "resume_used": "Data analyst · fintech (v3)", "reference_id": ref,
        "confirmation_text": None, "confirmation_source": "extension" if state == "submitted_confirmed" else ("user_confirmed" if status == "SUBMITTED" else None),
        "created_at": iso(created), "opened_at": iso(created - 0.5) if status != "PREPARED" else None,
        "submitted_at": iso(days) if days is not None else None,
        "submission_method": "Smart Apply" if state == "submitted_confirmed" else ("By hand on the employer's site" if status == "SUBMITTED" else None),
        "follow_up_at": iso(-fu) if fu is not None else None,
        "apply_state": state, "apply_state_label": STATE_LABELS.get(state or ""), "apply_mode": "autofill_review" if state else None,
        "apply_state_at": iso(days or 0, 2) if state else None,
        "job": job(aid, company, title, platform),
        **({"rejection_reason": "experience", "rejection_reason_known": True} if stage == "rejected" else {}),
    }


APPS = [app(r) for r in ROWS]


def ev(i: int, t: str, days: float, to: str | None = None, details: str | None = None, frm: str | None = None) -> dict:
    return {"id": i, "event_type": t, "from_status": frm, "to_status": to, "details": details, "created_at": iso(days)}


DETAIL_25 = {
    **APPS[0],
    "cover_letter": "Dear Groww hiring team,\n\nI build dashboards that people actually open...",
    "screening_answers": [], "checklist": [], "needs_candidate_input": [],
    "notes": "Round 2 is a SQL case on payment funnels. Revise window functions.",
    "follow_up_at": None,
    "events": [
        ev(1, "PREPARED", 13.2, "PREPARED"),
        ev(2, "RESUME_SELECTED", 13.1, details="Data analyst · fintech (v3)"),
        ev(3, "OPENED_EXTERNAL", 12.2, "OPENED"),
        ev(4, "APPLY_STATE", 12.15, "filling"),
        ev(5, "APPLY_STATE", 12.1, "ready_for_review"),
        ev(6, "APPLY_STATE", 12.05, "submission_pending"),
        ev(7, "SUBMISSION_CONFIRMED", 12.0, "SUBMITTED", "source=extension; reference=GRW-20419"),
        ev(8, "STAGE_CHANGED", 7, "screening", frm="applied"),
        ev(9, "INTERVIEW_ADDED", 6),
        ev(10, "STAGE_CHANGED", 4, "interview", frm="screening"),
    ],
}

PENDING_31 = {**APPS[8], "cover_letter": None, "screening_answers": [], "checklist": [], "needs_candidate_input": [], "notes": None,
              "events": [ev(1, "PREPARED", 1.2, "PREPARED"), ev(2, "OPENED_EXTERNAL", 1.1, "OPENED"), ev(3, "APPLY_STATE", 1.05, "filling"),
                         ev(4, "APPLY_STATE", 1.0, "submission_uncertain"), ev(5, "RETURNED_UNDECIDED", 0.9, "CONFIRMATION_PENDING")]}

INTERVIEWS = [
    {"id": 4, "application_id": 25, "round_name": "Round 2 · SQL case", "interviewers": "Priya Menon (Analytics Lead)", "location": "https://meet.google.com/abc-defg-hij",
     "mode": "video", "scheduled_at": iso(-2, -3), "duration_minutes": 60, "notes": None, "outcome": "scheduled", "created_at": iso(6)},
    {"id": 3, "application_id": 25, "round_name": "Recruiter screen", "interviewers": "Karan S.", "location": None, "mode": "phone",
     "scheduled_at": iso(5), "duration_minutes": 30, "notes": None, "outcome": "passed", "created_at": iso(7), "feedback_at": iso(5)},
]

OFFERS = [{"id": 2, "application_id": 22, "base_salary": 1400000, "currency": "INR", "bonus": 150000, "equity": None, "decision_deadline": iso(-5)[:10],
           "status": "received", "notes": "Joining bonus negotiable.", "created_at": iso(3), "company": "Zeta", "title": "Analyst, Risk Platform"}]

CONTACTS = [
    {"id": 1, "application_id": 25, "name": "Priya Menon", "role": "Analytics Lead", "email": "priya@example.com", "phone": None,
     "linkedin_url": "https://www.linkedin.com/in/example", "notes": None, "created_at": iso(6)},
    {"id": 2, "application_id": 25, "name": "Karan S.", "role": "Talent partner", "email": "karan@example.com", "phone": "+91 98xxx xxx10",
     "linkedin_url": None, "notes": None, "created_at": iso(7)},
]

FUNNEL = {
    "counts": {"prepared": 14, "opened": 12, "pending": 2, "applied": 9, "screening": 6, "assessment": 3, "interview": 2, "offer": 1, "rejected": 1},
    "conversion": {"application_to_screening": 67, "application_to_interview": 22, "interview_to_offer": 50},
    "rejection_reasons": [{"reason": "experience", "label": "Not enough experience", "count": 1}],
    "rejections_with_known_reason": 1,
    "by_resume_version": [{"version": "Data analyst · fintech (v3)", "applications": 6, "interviews": 2}, {"version": "General (v1)", "applications": 3, "interviews": 0}],
    "note": None,
}

ANALYTICS = {
    # Same 30-day series as the base fixture (the dashboard reads this endpoint too); only platforms and outcomes are added.
    "days": 30,
    "series": [{"date": (NOW - timedelta(days=29 - d)).date().isoformat(), "discovered": [12, 30, 8, 44, 20, 26, 51, 18, 9, 33][d % 10],
                "applied": [0, 1, 0, 1, 0, 0, 1, 0, 0, 0][d % 10]} for d in range(30)],
    "funnel": [{"stage": "Discovered", "count": 1284}, {"stage": "Shortlisted", "count": 46}, {"stage": "Applied", "count": 18},
               {"stage": "Interview", "count": 3}, {"stage": "Offer", "count": 1}],
    "platforms": [
        {"platform": "Greenhouse", "applied": 4, "responses": 2, "rejected": 1, "response_rate": 50},
        {"platform": "Lever", "applied": 2, "responses": 1, "rejected": 0, "response_rate": 50},
        {"platform": "Ashby", "applied": 2, "responses": 2, "rejected": 0, "response_rate": 100},
        {"platform": "SmartRecruiters", "applied": 1, "responses": 0, "rejected": 1, "response_rate": 0},
    ],
    "status_counts": {"SUBMITTED": 9, "CONFIRMATION_PENDING": 1, "OPENED": 1, "PREPARED": 1, "WITHDRAWN": 1},
}

REPORTS = [
    {"id": 12, "kind": "daily", "report_date": (NOW - timedelta(days=0)).date().isoformat(), "file_name": f"jobpilot_daily_{NOW.date().isoformat()}.xlsx", "size_bytes": 48211, "created_at": iso(hours=3)},
    {"id": 11, "kind": "daily", "report_date": (NOW - timedelta(days=1)).date().isoformat(), "file_name": f"jobpilot_daily_{(NOW - timedelta(days=1)).date().isoformat()}.xlsx", "size_bytes": 46980, "created_at": iso(1, 3)},
    {"id": 9, "kind": "history", "report_date": (NOW - timedelta(days=6)).date().isoformat(), "file_name": "jobpilot_history.xlsx", "size_bytes": 131072, "created_at": iso(6)},
]

APPLY_OPTIONS = {"original_url": "https://job-boards.greenhouse.io/x/jobs/1", "original_supported": True, "platform": "Greenhouse",
                 "hosted_form_url": None, "direct_apply": False, "message": "This is a Greenhouse form. You submit it there yourself."}

FIXTURES: dict[str, object] = {
    "/api/v1/applications": APPS,
    "/api/v1/applications/25": DETAIL_25,
    "/api/v1/applications/31": PENDING_31,
    "/api/v1/interviews": INTERVIEWS,
    "/api/v1/offers": OFFERS,
    "/api/v1/applications/25/contacts": CONTACTS,
    "/api/v1/applications/31/contacts": [],
    "/api/v1/analytics/funnel": FUNNEL,
    "/api/v1/rejection-reasons": [{"key": "experience", "label": "Not enough experience"}, {"key": "salary", "label": "Salary expectations"},
                                  {"key": "no_reply", "label": "No reply"}],
    "/api/v1/dashboard/analytics": ANALYTICS,
    "/api/v1/reports": REPORTS,
    "/api/v1/applications/25/apply-options": APPLY_OPTIONS,
    "/api/v1/applications/5/apply-options": APPLY_OPTIONS,
}
