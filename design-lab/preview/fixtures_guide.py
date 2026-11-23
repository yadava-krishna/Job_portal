"""Sample responses for the user-guide screenshots (Portal Connections, remembered answers). Preview harness only."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.services.portal_service import connections  # noqa: E402  (static text, no database)

_NOW = datetime.now(timezone.utc)


def _iso(days: float = 0) -> str:
    return (_NOW - timedelta(days=days)).isoformat()


def _ans(key, label, answer, group, *, scope="global", scope_name=None, source="you", days=10, stale=False, question=None):
    return {"key": key, "scope_ref": scope_name or "", "scope_kind": scope, "scope_name": scope_name, "reusable": scope == "global",
            "label": label, "answer": answer, "masked": False, "value_type": "text", "unit": None, "sensitivity": "personal",
            "source": source, "status": "confirmed", "stale": stale, "question": question, "last_confirmed_at": _iso(days),
            "revalidate_days": 90, "group": group, "history": []}


_REVIEW_ITEMS = [
    {"key": "headline", "label": "Headline", "state": "ok", "existing": "Data analyst · SQL, Python and dashboards for payments teams",
     "suggestion": None, "why": "Has your target role and fits LinkedIn's limit.", "copy": False, "done_at": None},
    {"key": "about", "label": "About section", "state": "ok",
     "existing": "Analyst with 3 years in fintech. I build the reporting that risk and growth teams decide with, and I like turning messy data into one clear chart.",
     "suggestion": "Analyst with 3 years in fintech. I build the reporting that risk and growth teams decide with, and I like turning messy data into one clear chart.",
     "why": "Your confirmed summary. Paste it into About if it isn't there yet.", "copy": True, "done_at": _iso(2)},
    {"key": "experience", "label": "Experience", "state": "ok", "existing": None, "suggestion": None, "why": "Every role has a description.", "copy": False, "done_at": None},
    {"key": "achievements", "label": "Quantified achievements", "state": "ok",
     "existing": "Built the merchant risk dashboard used by 40 analysts.\nCut weekly reporting time from 6 hours to 40 minutes.",
     "suggestion": "• Built the merchant risk dashboard used by 40 analysts.\n• Cut weekly reporting time from 6 hours to 40 minutes.",
     "why": "Results with numbers, from your confirmed profile. Use them in About or under each role.", "copy": True, "done_at": None},
    {"key": "skills", "label": "Skills", "state": "ok", "existing": "SQL, Python, Pandas, Tableau, Excel, A/B testing, Statistics",
     "suggestion": "SQL, Python, Pandas, Tableau, Excel, A/B testing, Statistics", "why": "Your confirmed skills. Add the ones you use most to LinkedIn's Skills section.",
     "copy": True, "done_at": None},
    {"key": "location", "label": "Location", "state": "ok", "existing": "Bengaluru, India", "suggestion": None, "why": "Matches where you're looking.", "copy": False, "done_at": None},
    {"key": "target_titles", "label": "Target job titles", "state": "ok", "existing": "Data Analyst, Business Analyst, Product Analyst",
     "suggestion": "Data Analyst, Business Analyst, Product Analyst", "why": "Add these to LinkedIn's 'Open to work' job titles.", "copy": True, "done_at": None},
]

FIXTURES = {
    "/api/v1/portals": connections(),
    "/api/v1/portals/linkedin/review": {"portal": "linkedin", "name": "LinkedIn", "items": _REVIEW_ITEMS, "completeness": 100,
                                        "source": "Built from your confirmed JobPilot profile and preferences. JobPilot never changes your profile on LinkedIn."},
    "/api/v1/answers/memory": [
        _ans("expected_ctc", "Expected CTC", "16–18 LPA", "preferences", days=12),
        _ans("notice_period", "Notice period", "30 days", "preferences", days=12),
        _ans("work_authorization_in", "Can you work in India?", "Yes, Indian citizen", "eligibility", days=40),
        _ans("relocate", "Willing to relocate?", "Yes, within India", "preferences", days=95, stale=True),
        _ans("why_company", "Why do you want to work at PhonePe?", "I've used UPI risk data every day for 3 years and want to work on it at the source.",
             "other", scope="company", scope_name="PhonePe", source="application", days=3, question="Why PhonePe?"),
        _ans("office_5_days", "Comfortable working from the office five days a week?", "Yes", "preferences", days=20),
    ],
    "/api/v1/answers/conflicts": [
        {"key": "current_company", "label": "Current company", "saved": "Zeta", "profile": "Paytm", "used": "ask"},
    ],
}


# ---- Apply Workspace (Discover -> Apply on the PhonePe card) ------------------------------------------------------
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location("_fx_apps", Path(__file__).parent / "fixtures_applications.py")
_fx = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_fx)  # type: ignore[union-attr]
APPLY_APP = dict(_fx.DETAIL_25, id=5, status="PREPARED", apply_state=None, apply_state_label=None,
                 job=dict(_fx.DETAIL_25.get("job") or {}, title="Data Analyst, Payments Risk", company="PhonePe"))


def _pa(question, *, key=None, status="NEEDS_INPUT", answer=None, source=None, sensitivity="personal", confirm=False, stale=False,
        reason=None, value_type="text", unit=None, remember=True):
    return {"question": question, "key": key, "label": question, "answer": answer, "status": status, "source": source, "confidence": 1,
            "sensitivity": sensitivity, "confirm": confirm, "stale": stale, "reason": reason, "value_type": value_type, "unit": unit,
            "scope": "global", "notes": [], "remember_default": remember, "origin": "common", "required": True, "options": [], "field_type": "text"}


_GH = "https://jobs.ashbyhq.com/phonepe/1"
FIXTURES["/api/v1/applications/5/package"] = {"application": APPLY_APP, "package": {
    "version": 1, "prepared_at": _iso(0),
    "job": {"title": "Data Analyst, Payments Risk", "company": "PhonePe", "source": "Ashby", "location": "Bengaluru", "match_score": 91, "job_url": _GH},
    "destination": {"original_url": _GH, "source_platform": "Ashby", "url": _GH, "kind": "ats", "ats": "ashby", "platform_name": "Ashby",
                    "verified": True, "evidence": ["Employer posting on PhonePe's own Ashby job board."], "suggestions": [], "confirmed_by_user": False},
    "capabilities": {"prepare": True, "autofill": True, "assisted_submit": True, "native_handoff": False, "verified_confirmation": True,
                     "summary": "JobPilot fills this Ashby form; you review it and confirm the submission."},
    "resume": {"kind": "studio", "id": 3, "name": "Data analyst · fintech", "format": "pdf", "selected_by": "you", "ready": True},
    "profile": {"personal": [{"key": "full_name", "label": "Full name", "value": "Asha Rao", "source": "profile"},
                             {"key": "email", "label": "E-mail", "value": "asha.rao@example.com", "source": "profile"},
                             {"key": "phone", "label": "Phone", "value": "+91 98450 12345", "source": "profile"}],
                "professional": [{"key": "current_title", "label": "Current title", "value": "Data Analyst", "source": "profile"},
                                 {"key": "current_company", "label": "Current company", "value": "Paytm", "source": "profile"}],
                "links": [{"key": "linkedin", "label": "LinkedIn", "value": "https://www.linkedin.com/in/asha-rao", "source": "profile"}]},
    "answers": [
        _pa("Total years of experience", key="experience_years.total", status="VERIFIED", answer="3", source="profile", value_type="number", unit="years"),
        _pa("Expected CTC", key="expected_ctc", status="SUGGESTED", answer="16–18 LPA", source="memory", sensitivity="private", confirm=True, value_type="money"),
        _pa("Notice period", key="notice_period", status="VERIFIED", answer="30 days", source="memory", confirm=True, value_type="days", unit="days"),
        _pa("Willing to relocate?", key="willing_to_relocate", status="SUGGESTED", answer="Yes, within India", source="memory", stale=True,
            reason="Saved a while ago. Check it's still right.", value_type="boolean"),
        _pa("Why do you want to work at PhonePe?", status="SUGGESTED", answer="I've used UPI risk data every day for 3 years and want to work on it at the source.",
            source="saved_for_one_job.PhonePe"),
        _pa("What is your gender?", sensitivity="never", remember=False, reason="Sensitive personal question: always yours to answer."),
    ],
    "questions_source": "employer_api", "missing": [], "conflicts": [],
    "eligibility": [{"label": "Work authorisation", "status": "ok", "detail": "Indian citizen; the job is in Bengaluru."},
                    {"label": "Experience", "status": "ok", "detail": "Asks for 0–2 years; you have 3."}],
    "readiness": {"profile": True, "resume": True, "known_questions": True, "form_inspected": False, "to_check": 2, "needs_input": 1,
                  "level": "needs_input", "summary": "1 answer needed before you apply."},
    "action": "review_autofill", "action_label": "Review and autofill"}}
