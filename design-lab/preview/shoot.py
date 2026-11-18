"""Local preview harness for the redesign (never touches the real backend or database).

Runs the frontend dev server's pages in headless Chromium and answers every API call with sample data, so each
redesigned page can be screenshotted in light and dark, desktop and phone.

    python design-lab/preview/shoot.py dashboard discover applied --theme both
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.async_api import async_playwright

APP = "http://127.0.0.1:5199"
API = "http://127.0.0.1:59999"
OUT = Path(__file__).parent / "shots"
FULL = False
NOW = datetime.now(timezone.utc)


def iso(days: float = 0, hours: float = 0) -> str:
    return (NOW - timedelta(days=days, hours=hours)).isoformat()


USER = {"id": 7, "email": "asha.rao@example.com", "full_name": "Asha Rao", "role": "user", "is_active": True,
        "created_at": iso(30), "onboarding_completed_at": iso(29)}

JOBS = [
    ("PhonePe", "Data Analyst, Payments Risk", "Bengaluru", "Hybrid", "₹14–20 LPA", 91, ["SQL", "Python", "Tableau", "Statistics"], ["dbt"], "Ashby", "https://jobs.ashbyhq.com/phonepe/1"),
    ("Razorpay", "Business Analyst, Growth", "Bengaluru", "On-site", "₹12–16 LPA", 88, ["SQL", "Excel", "A/B testing"], ["Looker"], "Lever", "https://jobs.lever.co/razorpay/2"),
    ("Swiggy", "Product Analyst", "Bengaluru", "Hybrid", "₹15–22 LPA", 84, ["SQL", "Python", "Product sense"], ["Amplitude"], "Greenhouse", "https://job-boards.greenhouse.io/swiggy/jobs/3"),
    ("Zerodha", "Analytics Intern", "Remote", "Remote", "₹40k / month", 79, ["Python", "Pandas"], ["Spark"], "Greenhouse", "https://job-boards.greenhouse.io/zerodha/jobs/4"),
    ("CRED", "Junior Data Scientist", "Bengaluru", "On-site", None, 72, ["Python", "ML"], ["PyTorch", "Airflow"], "Lever", "https://jobs.lever.co/cred/5"),
    ("Freshworks", "Reporting Analyst", "Chennai", "Hybrid", "₹9–12 LPA", 66, ["Excel", "SQL"], ["Power BI"], "SmartRecruiters", None),
    ("Postman", "Senior Data Engineer", "Bengaluru", "Hybrid", None, 48, ["SQL"], ["Scala", "Kafka", "6+ years"], "Greenhouse", None),
]


def user_job(i: int, j: tuple) -> dict:
    company, title, loc, mode, sal, score, have, miss, platform, url = j
    return {
        "user_job_id": 100 + i, "status": "new", "is_saved": i == 1, "match_score": score,
        "match_category": "strong" if score >= 85 else "good" if score >= 70 else "fair",
        "matching_skills": have, "missing_skills": miss, "eligibility_status": "INELIGIBLE" if score < 50 else "ELIGIBLE",
        "scoring_method": "rule_based", "discovered_at": iso(hours=2 + i * 5), "saved_at": None, "dismissed_at": None,
        "application_id": None, "application_status": None,
        "job": {"id": 200 + i, "platform": platform, "external_job_id": str(i), "company": company, "title": title,
                "location": loc, "work_mode": mode, "employment_type": "Internship" if "Intern" in title else "Full-time",
                "experience_required": "0-2 years" if score > 70 else "3-5 years", "salary_range": sal, "job_url": url,
                "posted_at": (NOW - timedelta(days=i)).date().isoformat(), "posted_at_source": "platform_api",
                "posted_label": "Today" if i == 0 else f"{i} days ago",
                "description_preview": f"Join {company} to turn data into decisions. You'll own dashboards, run experiments and partner with product and risk teams.",
                "has_full_description": True, "source": platform.lower(), "posted_at_confidence": "verified",
                "first_seen_at": iso(hours=2 + i * 5), "last_verified_at": iso(hours=1), "closed_at": None,
                "industry": "Fintech", "department": "Analytics",
                "sources": [{"source": platform.lower(), "platform": platform, "url": url, "first_seen_at": iso(1)}]},
    }


ITEMS = [user_job(i, j) for i, j in enumerate(JOBS)]
# A longer feed so pagination can be exercised: variations of the base jobs with lower scores.
_EXTRA_CO = ["Meesho", "Groww", "Zeta", "Paytm", "Ola", "Dunzo", "Urban Company", "Unacademy", "Nykaa", "Lenskart", "Myntra", "ShareChat"]
FEED = ITEMS + [user_job(10 + k, (_EXTRA_CO[k % len(_EXTRA_CO)], JOBS[k % 6][1], JOBS[k % 6][2], JOBS[k % 6][3], JOBS[k % 6][4],
                                   max(35, 78 - k), JOBS[k % 6][6][:2], JOBS[k % 6][7], JOBS[k % 6][8], JOBS[k % 6][9])) for k in range(55)]


def overview_job(u: dict) -> dict:
    j = u["job"]
    return {"user_job_id": u["user_job_id"], "title": j["title"], "company": j["company"], "match_score": u["match_score"],
            "location": f'{j["location"]} · {j["work_mode"]}', "salary": j["salary_range"], "discovered_at": u["discovered_at"],
            "freshness": "open", "eligibility_status": u["eligibility_status"]}


FIXTURES: dict[str, object] = {
    "/api/v1/health": {"status": "ok", "service": "jobpilot-backend", "version": "2.6.0", "timestamp": iso(),
                       "database": {"connected": True, "error": None},
                       "scheduler": {"enabled": True, "running": True, "next_run": iso(-0.3), "last_run": None}},
    "/api/v1/auth/me": USER,
    "/api/v1/auth/config": {"registration": "invite"},
    "/api/v1/onboarding": {"resume_uploaded": True, "profile_confirmed": True, "preferences_saved": True, "platforms_selected": True, "completed": True},
    "/api/v1/dashboard/overview": {
        "new_jobs": {"count": 12, "min_score": 70, "days": 7, "top": [overview_job(u) for u in ITEMS[:5]]},
        "attention": [
            {"kind": "confirm", "title": "Did you submit: Product Analyst at Swiggy?", "detail": "Opened 2 hours ago", "due": None, "application_id": 31, "user_job_id": None, "interview_id": None},
            {"kind": "follow_up", "title": "Follow up: Business Analyst at Meesho", "detail": "Applied 8 days ago, no reply", "due": None, "application_id": 28, "user_job_id": None, "interview_id": None},
        ],
        "upcoming": [
            {"kind": "interview", "title": "Interview: Data Analyst at Groww", "detail": "Round 2 · Video call", "due": iso(-2), "application_id": 25, "user_job_id": None, "interview_id": 4},
            {"kind": "offer_deadline", "title": "Offer decision: Analyst at Zeta", "detail": "Respond by Friday", "due": iso(-5), "application_id": 22, "user_job_id": None, "interview_id": None},
        ],
        "waiting": [],
        "saved": {"count": 4, "no_longer_open": 1, "top": [overview_job(ITEMS[1]), overview_job(ITEMS[3])]},
        "recent_submitted": [
            {"application_id": 28, "title": "Business Analyst", "company": "Meesho", "submitted_at": iso(8), "stage": "applied"},
            {"application_id": 25, "title": "Data Analyst", "company": "Groww", "submitted_at": iso(12), "stage": "interview"},
            {"application_id": 22, "title": "Analyst", "company": "Zeta", "submitted_at": iso(20), "stage": "offer"},
        ],
        "resume": {"state": "ready", "message": None, "uploaded": {"filename": "asha_rao.pdf", "uploaded_at": iso(29)}, "profile_confirmed": True,
                   "versions": 3, "latest": {"id": 3, "name": "Data analyst · fintech", "updated_at": iso(2), "status": "exported"}, "last_export_at": iso(2)},
        "discovery": {"state": "ok", "problems": [], "last_run": {"id": 40, "status": "completed", "started_at": iso(hours=3), "completed_at": iso(hours=2.9), "jobs_found": 1284, "jobs_new": 38}},
    },
    "/api/v1/dashboard/summary": {"total_discovered": 1284, "total_shortlisted": 46, "total_applied": 18, "total_saved": 4, "pending_applications": 2,
                                  "average_match_score": 74, "discovered_today": 38, "applied_today": 1, "posted_today_verified": 9, "interviews": 3, "offers": 1,
                                  "platforms": [{"platform": p, "discovered": d, "shortlisted": s, "applied": a, "average_score": sc} for p, d, s, a, sc in
                                                [("Greenhouse", 512, 18, 7, 76), ("Lever", 341, 12, 5, 73), ("Ashby", 220, 9, 4, 78), ("SmartRecruiters", 211, 7, 2, 66)]],
                                  "last_discovery_run": {"id": 40, "status": "completed", "started_at": iso(hours=3), "completed_at": iso(hours=2.9), "jobs_found": 1284, "jobs_new": 38, "jobs_matched": 46, "errors": 0}},
    "/api/v1/dashboard/activity": [{"kind": "discovery", "at": iso(hours=3), "details": "38 new jobs from 4 sources"},
                                   {"kind": "event", "at": iso(8), "title": "Business Analyst", "company": "Meesho", "event_type": "STATUS", "to_status": "SUBMITTED"}],
    "/api/v1/dashboard/analytics": {"days": 30, "series": [{"date": (NOW - timedelta(days=29 - d)).date().isoformat(), "discovered": [12, 30, 8, 44, 20, 26, 51, 18, 9, 33][d % 10], "applied": [0, 1, 0, 2, 1, 0, 1, 0, 0, 1][d % 10]} for d in range(30)],
                                    "funnel": [{"stage": "Discovered", "count": 1284}, {"stage": "Shortlisted", "count": 46}, {"stage": "Applied", "count": 18}, {"stage": "Interview", "count": 3}, {"stage": "Offer", "count": 1}],
                                    "platforms": [], "status_counts": {}},
    "/api/v1/career/snapshot": {"stage": "applying", "profile_completeness": {"percent": 86, "missing": ["Portfolio link"]}, "top_matches": [{"user_job_id": 100, "title": "Data Analyst, Payments Risk", "company": "PhonePe", "score": 91, "eligibility": "pass", "score_version": "v3"}],
                                "top_gap": {"id": 1, "skill": "dbt", "severity": "medium", "explanation": "Asked for in 9 of your top 20 matches.", "next_action": "Build one small dbt project", "evidence_state": None, "status": "open", "job_count": 9, "rejection_count": 0},
                                "alternative_gaps": [], "counts": {"applications_submitted": 18, "applications_in_progress": 2, "upcoming_interviews": 1},
                                "show": {"tracker": True, "interview_prep": True, "learning": True, "international": False, "reflection": True},
                                "next_step": {"kind": "apply", "label": "Apply to your best match", "link": "/discover", "reason": "PhonePe's Data Analyst role is a 91% match and closes soon."}},
    "/api/v1/jobs": {"items": ITEMS, "total": 38, "hidden_unknown_dates": 0, "page": 1, "page_size": 25},
    "/api/v1/jobs/runs": [{"id": 40, "trigger": "scheduled", "status": "completed", "sources": ["all"], "started_at": iso(hours=3), "completed_at": iso(hours=2.9),
                           "jobs_found": 1284, "jobs_new": 38, "jobs_matched": 46, "duplicates": 210, "error_details": [], "platform_stats": {}, "source_results": {}, "summary": "All sources answered."}],
    "/api/v1/notifications": {"items": [{"id": 1, "kind": "new_match", "title": "12 new matches", "body": "PhonePe, Razorpay and 10 more", "link": "/discover", "occurrences": 1, "read_at": None, "created_at": iso(hours=3)}], "unread": 1},
    "/api/v1/jobs/search-links": [],
    "/api/v1/discovery/sources": {"sources": [], "saved_searches": 3, "enabled_searches": 3,
                                   "last_run": {"id": 40, "trigger": "scheduled", "status": "completed", "sources": ["all"], "started_at": iso(hours=3), "completed_at": iso(hours=2.9),
                                                "jobs_found": 1284, "jobs_new": 38, "jobs_matched": 46, "duplicates": 210, "error_details": [], "platform_stats": {}, "source_results": {}, "summary": "All sources answered."}},
    "/api/v1/saved-searches": [],
    "/api/v1/preferences": {"titles": ["Data Analyst"], "locations": ["Bengaluru"], "min_match_score": 70},
}


def _load_extra_fixtures() -> None:
    """fixtures_*.py files next to this script add or override sample responses (one file per area, no merge conflicts)."""
    import importlib.util
    for f in sorted(Path(__file__).parent.glob("fixtures_*.py")):
        spec = importlib.util.spec_from_file_location(f.stem, f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        FIXTURES.update(getattr(mod, "FIXTURES", {}))


_load_extra_fixtures()


def answer(path: str, method: str, query: dict | None = None):
    if method == "POST" and path.endswith("/auth/refresh"):
        return {"access_token": "preview-access", "refresh_token": "preview-refresh", "token_type": "bearer", "expires_in": 3600, "user": USER}
    if method != "GET":
        return {}
    if path == "/api/v1/jobs" and query is not None and "page_size" in query and query.get("page_size") != ["1"]:
        page, size = int(query.get("page", ["1"])[0]), int(query["page_size"][0])
        return {"items": FEED[(page - 1) * size: page * size], "total": len(FEED), "hidden_unknown_dates": 0, "page": page, "page_size": size}
    if path in FIXTURES:
        return FIXTURES[path]
    if re.fullmatch(r"/api/v1/jobs/\d+/analysis", path):
        uid = int(path.split("/")[-2]); u = next((x for x in ITEMS if x["user_job_id"] == uid), ITEMS[0])
        return {"user_job_id": uid, "overall_score": u["match_score"], "category": u["match_category"], "components": [],
                "matching_skills": u["matching_skills"], "missing_skills": u["missing_skills"], "missing_optional_skills": [],
                "relevant_experience": "", "experience_gap": "", "education_match": None, "location_match": None, "responsibilities_match": [],
                "reasons_for": ["Strong overlap with your SQL and Python work", "Location and work mode fit your preferences"],
                "reasons_against": [f"Asks for {m}" for m in u["missing_skills"]], "recommendation": "Worth applying: tailor your resume around dashboards and experiments.",
                "explanation": "", "eligibility_status": "ELIGIBLE", "eligibility_reasons": [], "scoring_method": "rule_based", "confidence": "medium", "notes": [],
                "score_version": "v3", "eligibility": "pass", "unknown_dimensions": [], "disclaimer": "A relevance estimate to help you prioritise. It is not a prediction that you will be hired.",
                "dimensions": [dict(name=n, label=l, status="known", score=sc, base_weight=w, weight=w, weighted=round(sc * w / 100, 1), evidence=ev, method="rule")
                               for n, l, sc, w, ev in [("skills", "Skills", u["match_score"], 40, "Matched " + ", ".join(u["matching_skills"])),
                                                       ("experience", "Experience", 90, 25, "0–2 years fits"), ("location", "Location", 100, 15, "Bengaluru, hybrid")]]}
    if re.fullmatch(r"/api/v1/jobs/\d+", path):
        uid = int(path.rsplit("/", 1)[1])
        u = dict(next((x for x in ITEMS if x["user_job_id"] == uid), ITEMS[0]))
        u.update({"description": u["job"]["description_preview"] + "\n\nWhat you'll do\n- Build and own risk dashboards used by 40+ people\n- Run A/B tests with product\n- Turn findings into rules with the fraud team\n\nWhat you bring\n- Strong SQL and Python\n- Clear written communication\n\nBenefits\n- Health cover for you and family\n- Learning budget",
                  "description_is_snippet": False, "responsibilities": ["Build and own risk dashboards used by 40+ people", "Run A/B tests with product", "Turn findings into rules with the fraud team"],
                  "required_skills": u["matching_skills"] + u["missing_skills"], "preferred_skills": ["dbt", "Airflow"], "education_requirements": ["Bachelor's degree"],
                  "mandatory_qualifications": [], "verification_flags": [], "similar": []})
        return u
    return None


async def shoot(pages: list[str], themes: list[str], phone: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    missing: set[str] = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for theme in themes:
            for vp_name, vp in ([("desktop", {"width": 1440, "height": 900})] + ([("phone", {"width": 390, "height": 844})] if phone else [])):
                ctx = await browser.new_context(viewport=vp, device_scale_factor=2 if vp_name == "phone" else 1.5,
                                                color_scheme="dark" if theme == "dark" else "light")
                await ctx.add_init_script(f"localStorage.setItem('jobpilot.refreshToken','preview-refresh');"
                                          f"localStorage.setItem('jobpilot.theme','{theme}');"
                                          f"localStorage.setItem('jobpilot.apiBaseUrl','{API}');")

                async def route(r):
                    url = r.request.url
                    path = url.split("://", 1)[1].split("/", 1)[1]
                    path = "/" + path.split("?", 1)[0]
                    if r.request.method == "OPTIONS":
                        return await r.fulfill(status=204, headers={"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*"})
                    from urllib.parse import parse_qs, urlparse
                    body = answer(path, r.request.method, parse_qs(urlparse(url).query))
                    if body is None:
                        missing.add(path)
                        body = []
                    await r.fulfill(status=200, content_type="application/json", body=json.dumps(body),
                                    headers={"access-control-allow-origin": "*"})

                await ctx.route(f"{API}/**", route)
                page = await ctx.new_page()
                for name in pages:
                    await page.goto(f"{APP}/#/{name}")
                    await page.wait_for_timeout(2600)
                    out = OUT / f"{name.replace('/', '_').replace('?', '_')}-{theme}-{vp_name}.png"
                    await page.screenshot(path=str(out), full_page=FULL)
                    print(out)
                await ctx.close()
        await browser.close()
    if missing:
        print("unmocked:", sorted(missing))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="+")
    ap.add_argument("--theme", choices=["light", "dark", "both"], default="light")
    ap.add_argument("--phone", action="store_true")
    ap.add_argument("--full", action="store_true", help="full-page capture (fixed elements may render mid-animation)")
    a = ap.parse_args()
    FULL = a.full
    asyncio.run(shoot(a.pages, ["light", "dark"] if a.theme == "both" else [a.theme], a.phone))
