"""Sample responses for the growth pages: career (gaps, skills, learning), interview prep, mentor, mentoring, international
and the admin console. Shapes follow frontend/src/features/career/types.ts and features/growth/types.ts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

NOW = datetime.now(timezone.utc)


def iso(days: float = 0, hours: float = 0) -> str:
    return (NOW - timedelta(days=days, hours=hours)).isoformat()


def day(days: float = 0) -> str:
    return (NOW - timedelta(days=days)).date().isoformat()


# ---------------------------------------------------------------- career

GAPS = [
    {"id": 1, "skill": "dbt", "severity": "high", "explanation": "Asked for in 9 of your top 20 matches, including PhonePe and Swiggy.",
     "next_action": "Build one small dbt project on a public dataset and link it.", "evidence_state": "aware", "status": "in_progress", "job_count": 9, "rejection_count": 1},
    {"id": 2, "skill": "Looker", "severity": "medium", "explanation": "Listed as required in 6 analyst roles you match.",
     "next_action": "Finish Google's free Looker fundamentals course.", "evidence_state": None, "status": "open", "job_count": 6, "rejection_count": 0},
    {"id": 3, "skill": "A/B testing", "severity": "medium", "explanation": "Growth and product analyst roles ask for experiment design.",
     "next_action": "Write up one experiment end to end: hypothesis, sample size, result.", "evidence_state": "learning", "status": "open", "job_count": 5, "rejection_count": 1},
    {"id": 4, "skill": "Airflow", "severity": "low", "explanation": "Mentioned as a nice-to-have in 3 data roles.",
     "next_action": "Read the Airflow concepts guide and schedule one DAG locally.", "evidence_state": None, "status": "open", "job_count": 3, "rejection_count": 0},
    {"id": 5, "skill": "Power BI", "severity": "low", "explanation": "Reporting roles in Chennai and Pune list it.",
     "next_action": "Rebuild one Tableau dashboard in Power BI.", "evidence_state": "project_evidence", "status": "closed", "job_count": 2, "rejection_count": 0},
]


def gap_detail(g: dict) -> dict:
    return {**g, "learning": {
        "skill": g["skill"], "level_suggested": "beginner", "enough": g["id"] != 4,
        "note": None if g["id"] != 4 else f"Only 1 checked resource(s) are catalogued for {g['skill']} so far.",
        "resources": [
            {"id": g["id"] * 10 + 1, "skill": g["skill"], "title": f"{g['skill']} Fundamentals", "url": "https://learn.getdbt.com/courses/dbt-fundamentals",
             "provider": "dbt Labs" if g["id"] == 1 else "Google", "type": "course", "level": "beginner", "duration_minutes": 300, "is_free": True,
             "source": "curated", "checked_at": iso(3), "link_status": "ok", "relevance": "Official course from the tool's maker"},
            {"id": g["id"] * 10 + 2, "skill": g["skill"], "title": f"Build a small {g['skill']} project", "url": "https://github.com/dbt-labs/jaffle-shop",
             "provider": "GitHub", "type": "project", "level": "beginner", "duration_minutes": 180, "is_free": True,
             "source": "curated", "checked_at": None, "link_status": "unverifiable", "relevance": "A starter project you can extend and link as evidence"},
            {"id": g["id"] * 10 + 3, "skill": g["skill"], "title": f"{g['skill']} for analysts: practical guide", "url": "https://www.coursera.org/",
             "provider": "Coursera", "type": "course", "level": "intermediate", "duration_minutes": 540, "is_free": False,
             "source": "curated", "checked_at": iso(10), "link_status": "ok", "relevance": "Covers testing and documentation, which job posts mention"},
        ],
    }}


SKILLS = {
    "states": [{"key": k, "label": v} for k, v in [("aware", "Aware"), ("learning", "Learning"), ("practising", "Practising"),
                                                    ("project_evidence", "Project evidence"), ("professional_experience", "Professional experience"),
                                                    ("interview_ready", "Interview ready")]],
    "skills": [
        {"id": 1, "name": "SQL", "canonical": "SQL", "state": "professional_experience", "state_label": "Professional experience", "proficiency": "advanced", "years": 2,
         "source": "resume_parse", "verified": True, "evidence_supports": "professional_experience",
         "evidence": [{"id": 11, "type": "employment", "title": "Analyst intern at Meesho: weekly cohort queries", "url": None, "description": None,
                       "source": "resume", "occurred_on": day(400), "created_at": iso(29)}]},
        {"id": 2, "name": "dbt", "canonical": "dbt", "state": "learning", "state_label": "Learning", "proficiency": "beginner", "years": None,
         "source": "manual", "verified": False, "evidence_supports": "learning",
         "evidence": [{"id": 21, "type": "course", "title": "dbt Fundamentals (half done)", "url": "https://learn.getdbt.com/courses/dbt-fundamentals",
                       "description": None, "source": "learning_session", "occurred_on": None, "created_at": iso(2)}]},
        {"id": 3, "name": "Power BI", "canonical": "Power BI", "state": "project_evidence", "state_label": "Project evidence", "proficiency": "intermediate", "years": 1,
         "source": "manual", "verified": False, "evidence_supports": "project_evidence",
         "evidence": [{"id": 31, "type": "project", "title": "Sales dashboard rebuilt from Tableau", "url": "https://github.com/asha/powerbi-sales",
                       "description": "Three pages, row-level security, scheduled refresh.", "source": "manual", "occurred_on": day(20), "created_at": iso(20)}]},
        {"id": 4, "name": "Python", "canonical": "Python", "state": "practising", "state_label": "Practising", "proficiency": "intermediate", "years": 1.5,
         "source": "resume_parse", "verified": False, "evidence_supports": "practising", "evidence": []},
    ],
}

MATCH_HISTORY = [
    {"id": 1, "user_job_id": 102, "title": "Product Analyst", "company": "Swiggy", "old_score": 78, "new_score": 84, "reason": "Power BI moved to project evidence",
     "score_version": "v3", "created_at": iso(20)},
    {"id": 2, "user_job_id": 105, "title": "Reporting Analyst", "company": "Freshworks", "old_score": 59, "new_score": 66, "reason": "Power BI moved to project evidence",
     "score_version": "v3", "created_at": iso(20)},
]

SESSIONS = {"sessions": [
    {"id": 3, "skill": "dbt", "resource_id": 11, "gap_id": 1, "status": "completed", "started_at": iso(2), "ended_at": iso(2, -1), "active_minutes": 52,
     "active_seconds": 3120, "idle_seconds": 480, "notes": "Models, refs, tests.", "helpful": True},
    {"id": 2, "skill": "Power BI", "resource_id": 51, "gap_id": 5, "status": "completed", "started_at": iso(21), "ended_at": iso(21, -2), "active_minutes": 95,
     "active_seconds": 5700, "idle_seconds": 900, "notes": None, "helpful": True},
], "stats": {"days": 30, "sessions": 2, "completed": 2, "active_minutes": 147, "idle_minutes": 23}}

# ---------------------------------------------------------------- international

COUNTRIES = [
    {"code": "GB", "name": "United Kingdom", "region": "Europe", "currency": "GBP", "official_source_url": "https://www.gov.uk/browse/visas-immigration", "routes": 2},
    {"code": "DE", "name": "Germany", "region": "Europe", "currency": "EUR", "official_source_url": "https://www.make-it-in-germany.com/en/", "routes": 2},
    {"code": "IE", "name": "Ireland", "region": "Europe", "currency": "EUR", "official_source_url": "https://enterprise.gov.ie/", "routes": 1},
    {"code": "AE", "name": "United Arab Emirates", "region": "Middle East", "currency": "AED", "official_source_url": "https://u.ae/", "routes": 1},
    {"code": "SG", "name": "Singapore", "region": "Asia", "currency": "SGD", "official_source_url": "https://www.mom.gov.sg/", "routes": 1},
    {"code": "CA", "name": "Canada", "region": "North America", "currency": "CAD", "official_source_url": "https://www.canada.ca/en/immigration-refugees-citizenship.html", "routes": 2},
]

ROUTE_SW = {"id": 2, "country_code": "GB", "code": "skilled_worker", "name": "Skilled Worker visa",
            "summary": "For a job offer from a UK employer approved by the Home Office, in an eligible occupation, above the salary threshold.",
            "requires_sponsorship": True, "source_url": "https://www.gov.uk/skilled-worker-visa", "confidence": "verified", "verified_at": iso(12),
            "last_checked_at": iso(3), "review_by": day(-80), "source_changed_at": None, "watching": True, "notice": "", "rules": []}
ROUTE_GT = {"id": 3, "country_code": "GB", "code": "graduate", "name": "Graduate visa",
            "summary": "For people who completed an eligible UK degree. You can't apply from outside the UK.",
            "requires_sponsorship": False, "source_url": "https://www.gov.uk/graduate-visa", "confidence": "unverified", "verified_at": None,
            "last_checked_at": iso(40), "review_by": None, "source_changed_at": iso(5), "watching": False, "notice": "", "rules": []}

COUNTRY_FIT = {
    "country": {"code": "GB", "name": "United Kingdom", "official_source_url": "https://www.gov.uk/browse/visas-immigration"},
    "already_authorised": False,
    "profile_used": {"years_experience": 2, "education": "bachelor", "languages": ["English", "Hindi", "Kannada"]},
    "notice": "General information only, not legal or immigration advice and not a prediction of approval. Rules change: always confirm on the official page before you act.",
    "routes": [
        {**ROUTE_SW, "fit": {"strengths": ["Your education (bachelor) meets the general level (bachelor).", "English is listed in your languages (B1 required)."],
                             "gaps": ["The general salary threshold is £38,700; your current salary is below it."],
                             "unknown": ["Whether the employer holds a sponsor licence.", "Whether the role's occupation code is eligible."],
                             "summary": "Possible with an offer above the salary threshold"}},
        {**ROUTE_GT, "fit": {"strengths": [], "gaps": ["Needs a UK degree; your profile lists a degree from India."], "unknown": [],
                             "summary": "Unlikely to apply to you"}},
    ],
    "relocation_tips": [
        "Ask recruiters early whether the role can be sponsored; many UK postings say so in the description.",
        "Check the employer on the official register of licensed sponsors before you apply.",
        "Budget for the Immigration Health Surcharge and visa fee; they are paid up front.",
    ],
}

# ---------------------------------------------------------------- interview prep

PREP_QUESTIONS = [
    {"id": "t1", "kind": "technical", "competency": "SQL", "question": "Write a query to find the 7-day rolling payment failure rate by merchant.",
     "why": "The posting asks for strong SQL on payments data."},
    {"id": "t2", "kind": "technical", "competency": "Statistics", "question": "How would you tell whether a rise in chargebacks is noise or a real change?",
     "why": "Risk analytics roles test basic statistical reasoning."},
    {"id": "t3", "kind": "technical", "competency": "Tableau", "question": "Walk us through a dashboard you built. Who used it and what changed because of it?",
     "why": "Tableau is listed as required."},
    {"id": "b1", "kind": "behavioural", "competency": "Ownership", "question": "Tell me about a time your analysis was wrong. What did you do?",
     "why": "Common at PhonePe for analyst roles; checks ownership."},
    {"id": "b2", "kind": "behavioural", "competency": "Stakeholders", "question": "Describe a time you pushed back on a stakeholder's request.",
     "why": "The role partners with product and risk teams."},
    {"id": "m1", "kind": "motivation", "competency": "Motivation", "question": "Why payments risk, and why PhonePe?",
     "why": "Almost every first round asks this."},
    {"id": "s1", "kind": "screening", "competency": "Logistics", "question": "What are your salary expectations and notice period?",
     "why": "Recruiter screens usually start here."},
]

PREP = {
    "job": {"user_job_id": 100, "title": "Data Analyst, Payments Risk", "company": "PhonePe"},
    "questions": PREP_QUESTIONS,
    "reference_links": [
        {"source": "glassdoor", "label": "PhonePe interviews on Glassdoor", "url": "https://www.glassdoor.co.in/Interview/PhonePe-Interview-Questions-E1094395.htm"},
        {"source": "ambitionbox", "label": "PhonePe on AmbitionBox", "url": "https://www.ambitionbox.com/interviews/phonepe-interview-questions"},
        {"source": "reddit", "label": "Search Reddit for PhonePe analyst", "url": "https://www.reddit.com/search/?q=phonepe+analyst+interview"},
        {"source": "company", "label": "PhonePe careers page", "url": "https://www.phonepe.com/careers/"},
    ],
    "reference_note": "Links open a search on each site. What people post there is unverified; use it as a hint, not a script.",
    "insights": [
        {"id": 1, "source": "glassdoor", "url": "https://www.glassdoor.co.in/", "question": "SQL round: window functions on a transactions table.",
         "note": "Three rounds: SQL, case study, hiring manager.", "created_at": iso(3)},
    ],
}

PRACTICES = [
    {"id": 7, "title": "Data Analyst, Payments Risk · PhonePe", "user_job_id": 100, "application_id": None, "status": "in_progress",
     "questions": PREP_QUESTIONS[:4], "answers": {"t1": {"answer": "Window over 7 days partitioned by merchant…", "self_rating": 3, "at": iso(1)}},
     "feedback": [{"question_id": "t1", "score": 3, "out_of": 5, "notes": ["Names the window frame", "Mention how you'd handle merchants with no traffic"], "method": "rule_based"}],
     "created_at": iso(1), "completed_at": None},
    {"id": 5, "title": "Business Analyst, Growth · Razorpay", "user_job_id": 101, "application_id": None, "status": "completed",
     "questions": PREP_QUESTIONS[:3], "answers": {q["id"]: {"answer": "…", "self_rating": 4, "at": iso(9)} for q in PREP_QUESTIONS[:3]},
     "feedback": [], "created_at": iso(9), "completed_at": iso(9)},
]

# ---------------------------------------------------------------- mentor

ACTIONS = [
    {"id": 1, "title": "Apply to 3 jobs scoring 80+ this week", "reason": "You've saved 4 strong matches but applied to none in 6 days.", "priority": "high",
     "due_on": day(-3), "source": "ai_mentor", "completed_at": None, "created_at": iso(2)},
    {"id": 2, "title": "Finish the dbt Fundamentals course", "reason": "dbt is your most-asked missing skill.", "priority": "medium",
     "due_on": day(-6), "source": "reflection", "completed_at": None, "created_at": iso(5)},
    {"id": 3, "title": "Ask Rohan for a referral at Swiggy", "reason": "Referrals convert far better than cold applications.", "priority": "medium",
     "due_on": None, "source": "human_mentor", "completed_at": None, "created_at": iso(4)},
    {"id": 4, "title": "Tailor resume for payments roles", "reason": "", "priority": "low", "due_on": None, "source": "self", "completed_at": iso(1), "created_at": iso(8)},
]

DIAGNOSES = [
    {"rule": "low_apply_rate", "title": "Saving more than applying", "confidence": "high",
     "observations": ["12 jobs saved in the last 14 days", "2 applications submitted in the same period"],
     "diagnosis": "You're finding good matches but not converting them into applications.", "limitations": "Doesn't count applications made outside JobPilot."},
    {"rule": "screen_dropoff", "title": "Few replies after applying", "confidence": "medium",
     "observations": ["18 applications, 3 screening calls", "Most rejections cite experience"],
     "diagnosis": "Your resume may be underselling project work for analyst roles.", "limitations": "Based on 18 applications; patterns may change with more data."},
]

REFLECTION = {"id": 3, "week_start": day(7), "outcome": "Applied to 2 roles, got a screening call from Groww.", "obstacle": "College exams took most of the week.",
              "next_action": "Apply to 3 jobs scoring 80+", "mood": 4, "created_at": iso(6)}

PLAN = {"diagnoses": DIAGNOSES, "actions": ACTIONS,
        "next_step": {"kind": "apply", "label": "Apply to PhonePe's Data Analyst role", "link": "/discover?job=100", "reason": "91% match, you meet every hard requirement, and it was posted today."},
        "reflection_due": True, "last_reflection": REFLECTION, "method": "rule_based",
        "note": "Built from your own activity in JobPilot. Rules, not guesses: each suggestion says what it's based on."}

MENTORS = {
    "mentors": [
        {"id": 11, "mentor_name": "Priya Menon", "mentor_email": "priya.menon@example.com", "status": "active", "scopes": ["funnel", "gaps", "actions"],
         "consented_at": iso(20), "revoked_at": None},
        {"id": 9, "mentor_name": "Karthik S", "mentor_email": "karthik@example.com", "status": "revoked", "scopes": ["profile"], "consented_at": iso(60), "revoked_at": iso(35)},
    ],
    "sessions": [
        {"id": 21, "scheduled_at": iso(-2), "duration_minutes": 30, "meeting_url": "https://meet.google.com/abc-defg-hij", "agenda": "Review my last three rejections",
         "status": "scheduled", "summary": None, "assignment_id": 11},
    ],
}

NOTES = [
    {"id": 1, "body": "Great progress on dbt. Try to finish the project before the PhonePe interview.", "visibility": "shared", "by_me": False, "created_at": iso(3)},
    {"id": 2, "body": "Thanks! Aiming for Sunday.", "visibility": "shared", "by_me": True, "created_at": iso(2.8)},
]

CANDIDATES = [
    {"assignment_id": 11, "candidate_name": "Asha Rao", "scopes": ["profile", "funnel", "gaps", "actions", "applications"], "since": iso(20)},
    {"assignment_id": 14, "candidate_name": "Vikram Nair", "scopes": ["funnel", "gaps"], "since": iso(9)},
]

FUNNEL = {"counts": {"prepared": 4, "opened": 3, "pending": 1, "applied": 18, "screening": 5, "assessment": 2, "interview": 3, "offer": 1, "rejected": 7},
          "conversion": {"application_to_screening": 27.8, "application_to_interview": 16.7, "interview_to_offer": 33.3},
          "rejection_reasons": [{"reason": "experience", "label": "Not enough experience", "count": 3}, {"reason": "skills", "label": "Missing skills", "count": 2}],
          "rejections_with_known_reason": 3, "by_resume_version": [{"version": "Data analyst · fintech", "applications": 11, "interviews": 3}], "note": None}

CANDIDATE = {
    "assignment_id": 11, "candidate_name": "Asha Rao", "scopes": ["profile", "funnel", "gaps", "actions", "applications"],
    "profile_completeness": {"percent": 86, "missing": ["portfolio_link"]},
    "funnel": FUNNEL, "diagnoses": DIAGNOSES,
    "gaps": [{k: v for k, v in g.items()} | {"evidence_state": g["evidence_state"] or "aware"} for g in GAPS[:3]],
    "actions": [a for a in ACTIONS if not a["completed_at"]],
    "applications": [{"id": 28, "title": "Business Analyst", "company": "Meesho", "status": "SUBMITTED", "stage": "applied"},
                     {"id": 25, "title": "Data Analyst", "company": "Groww", "status": "SUBMITTED", "stage": "interview"},
                     {"id": 22, "title": "Analyst", "company": "Zeta", "status": "SUBMITTED", "stage": "offer"}],
    "notes": [{**NOTES[0], "by_me": True}, {"id": 3, "body": "Seems anxious about case rounds. Suggest a mock next session.", "visibility": "private", "by_me": True, "created_at": iso(3)},
              {**NOTES[1], "by_me": False}],
    "sessions": [{**MENTORS["sessions"][0]},
                 {"id": 18, "scheduled_at": iso(12), "duration_minutes": 45, "meeting_url": None, "agenda": "Resume review", "status": "done",
                  "summary": "Move projects above education; quantify the Meesho cohort work.", "assignment_id": 11}],
}

# ---------------------------------------------------------------- admin

ADMIN_USERS = [
    {"id": 1, "email": "owner@example.com", "full_name": "Site Owner", "is_active": True, "role": "admin", "created_at": iso(120), "applications_count": 0, "jobs_count": 0},
    {"id": 7, "email": "asha.rao@example.com", "full_name": "Asha Rao", "is_active": True, "role": "user", "created_at": iso(30), "applications_count": 18, "jobs_count": 1284},
    {"id": 8, "email": "priya.menon@example.com", "full_name": "Priya Menon", "is_active": True, "role": "mentor", "created_at": iso(25), "applications_count": 0, "jobs_count": 0},
    {"id": 9, "email": "vikram.nair@example.com", "full_name": "Vikram Nair", "is_active": True, "role": "user", "created_at": iso(12), "applications_count": 6, "jobs_count": 840},
    {"id": 10, "email": "old.account@example.com", "full_name": "", "is_active": False, "role": "user", "created_at": iso(90), "applications_count": 2, "jobs_count": 120},
]

INVITES = [
    {"id": 4, "code": "JP-7KQ2-M9XA", "email": "neha@example.com", "role": "user", "max_uses": 1, "used_count": 0, "expires_at": iso(-5), "created_at": iso(2)},
    {"id": 3, "code": "JP-MENT-0R5", "email": None, "role": "mentor", "max_uses": 1, "used_count": 1, "expires_at": iso(-1), "created_at": iso(6)},
    {"id": 2, "code": "JP-2B8C-X1PL", "email": None, "role": "user", "max_uses": 1, "used_count": 0, "expires_at": iso(3), "created_at": iso(10)},
]

AUDIT = [
    {"id": 90, "actor_id": 1, "action": "user.role_changed", "target_type": "user", "target_id": "8", "ip": "192.168.1.20", "created_at": iso(hours=3)},
    {"id": 89, "actor_id": 1, "action": "invite.created", "target_type": "invite", "target_id": "4", "ip": "192.168.1.20", "created_at": iso(2)},
    {"id": 88, "actor_id": 7, "action": "auth.login", "target_type": None, "target_id": None, "ip": "10.0.0.14", "created_at": iso(2, 2)},
    {"id": 87, "actor_id": None, "action": "backup.completed", "target_type": "system", "target_id": None, "ip": None, "created_at": iso(2, 6)},
    {"id": 86, "actor_id": 8, "action": "mentor.viewed_candidate", "target_type": "assignment", "target_id": "11", "ip": "10.0.0.31", "created_at": iso(3)},
]

ADMIN_JOBS = [
    {"name": "job_discovery", "schedule": "Every 6 hours", "owner": "discovery", "description": "Searches every enabled source for new jobs.", "retries": 2,
     "last_status": "ok", "last_started_at": iso(hours=3), "last_error": None, "last_ok_at": iso(hours=3), "last_details": None, "last_trigger": "schedule"},
    {"name": "job_matching", "schedule": "After each discovery run", "owner": "matching", "description": "Scores new jobs against every candidate.", "retries": 3,
     "last_status": "failed", "last_started_at": iso(hours=2.9), "last_error": "OperationalError: could not connect to server: Connection refused (is the database running on port 5432?)",
     "last_ok_at": iso(1), "last_details": None, "last_trigger": "schedule", "runs_with": "job_discovery"},
    {"name": "freshness_check", "schedule": "Daily at 04:00", "owner": "discovery", "description": "Re-checks open listings and closes ones that were taken down.", "retries": 1,
     "last_status": "partial", "last_started_at": iso(hours=8), "last_error": None, "last_ok_at": iso(2), "last_details": None, "last_trigger": "catch_up"},
    {"name": "daily_digest", "schedule": "Daily at 08:00", "owner": "notifications", "description": "E-mails each candidate their new matches.", "retries": 2,
     "last_status": None, "last_started_at": None, "last_error": None, "last_ok_at": None, "last_details": None},
]

PRODUCT = {"days": 30, "note": "Counts only. No personal data leaves this server.",
           "north_star": {"applications_submitted": 26, "application_to_interview_pct": 15.4, "interview_to_offer_pct": 25, "offers": 1, "gap_closure_pct": 18,
                          "resume_reuse_pct": 72, "weekly_active_candidates": 7, "reflections_completed": 11, "onboarding_activation_pct": 83},
           "events": {"job_viewed": {"count": 1420, "users": 9, "failed": 0}, "application_submitted": {"count": 26, "users": 5, "failed": 1},
                      "resume_exported": {"count": 41, "users": 6, "failed": 0}, "learning_session_completed": {"count": 9, "users": 3, "failed": 0}},
           "ai_costs": [{"purpose": "resume_tailoring", "calls": 52, "cost_usd": 0.4132}, {"purpose": "job_analysis", "calls": 310, "cost_usd": 0.9411}],
           "feedback": [{"topic": "gap_usefulness", "responses": 6, "average_rating": 4.2}]}

SYSTEM = {"disk": {"used_percent": 62, "free_gb": 171, "level": "ok"},
          "backup": {"status": "ok", "at": NOW.strftime("%Y%m%dT031500Z"), "folder": "/backups/daily", "size_kb": 48210, "encrypted": True, "offhost": "no"}}

OPS = {
    "generated_at": iso(hours=0.1),
    "attention": [{"level": "warning", "text": "Sources not succeeding recently: Lever."}, {"level": "critical", "text": "Job matching failed 3 times in the last 24 hours."}],
    "disks": [{"label": "Data (resumes, exports, reports, logs)", "path": "/data", "available": True, "total_gb": 460, "used_gb": 289, "free_gb": 171, "used_percent": 62, "level": "ok"},
              {"label": "Backups", "path": "/backups", "available": True, "total_gb": 100, "used_gb": 74, "free_gb": 26, "used_percent": 74, "level": "warning",
               "note": "Over 70%: old daily backups will be pruned soon."}],
    "database": {"available": True, "dialect": "postgresql", "server_version": "16.4", "latency_ms": 1.4, "migration": "0011", "size_bytes": 52_428_800, "connections": 4,
                 "largest_tables": [{"table": "jobs", "bytes": 31_457_280, "rows_estimate": 12000}, {"table": "user_jobs", "bytes": 9_437_184, "rows_estimate": 41000}]},
    "backups": {"available": True, "level": "ok", "count": 9, "daily_count": 7, "stale_after_hours": 26, "last_status": "ok",
                "newest": {"name": "daily-20261118T031500Z", "at": iso(hours=6), "age_hours": 6, "size_bytes": 49_367_040}, "note": None},
    "background_jobs": {"failed_count": 3, "by_name": [{"name": "job_matching", "failures": 3, "last_failed_at": iso(hours=2.9)}],
                        "recent": [{"name": "job_matching", "status": "failed", "trigger": "schedule", "started_at": iso(hours=2.9), "attempts": 3, "error": "OperationalError: [redacted]"}],
                        "stuck": []},
    "discovery": {"by_status": {"completed": 27, "failed": 1}, "failed": 1, "stuck_running": 0, "failure_types": [{"type": "INTERRUPTED", "count": 1}]},
    "workflows": {"run_errors": [{"type": "HTTP_503", "platform": "Lever", "count": 2}], "apply_failed": 0, "apply_uncertain": 1, "apply_needs_information": 0},
    "sources": [
        {"key": "greenhouse", "name": "Greenhouse", "kind": "ats", "enabled": True, "health": "ok", "state": "ok", "last_run_at": iso(hours=3), "last_success_at": iso(hours=3),
         "hours_since_success": 3, "last_error": None, "runs_7d": 28, "failures_7d": 0, "last_failed_at": None, "last_failure": None},
        {"key": "lever", "name": "Lever", "kind": "ats", "enabled": True, "health": "degraded", "state": "failing", "last_run_at": iso(hours=3), "last_success_at": iso(4),
         "hours_since_success": 100, "last_error": None, "runs_7d": 5, "failures_7d": 2, "last_failed_at": iso(hours=3), "last_failure": "HTTP 503"},
        {"key": "ashby", "name": "Ashby", "kind": "ats", "enabled": True, "health": "ok", "state": "stale", "last_run_at": iso(1), "last_success_at": iso(2),
         "hours_since_success": 50, "last_error": None, "runs_7d": 12, "failures_7d": 0, "last_failed_at": None, "last_failure": None},
        {"key": "adzuna", "name": "Adzuna", "kind": "aggregator", "enabled": False, "health": "ok", "state": "disabled", "last_run_at": None, "last_success_at": None,
         "hours_since_success": None, "last_error": None, "runs_7d": 0, "failures_7d": 0, "last_failed_at": None, "last_failure": None},
    ],
    "source_freshness": [{"source": "greenhouse", "open_jobs": 420, "newest_discovered_at": iso(hours=3), "last_verified_at": iso(hours=6), "hours_since_verified": 6},
                         {"source": "lever", "open_jobs": 211, "newest_discovered_at": iso(4), "last_verified_at": iso(4), "hours_since_verified": 96}],
    "user_activity": {"accounts": 12, "active_accounts": 11, "logins_24h": 3, "logins_7d": 8, "logins_30d": 10, "active_users_7d": 7, "signups_7d": 1,
                      "discovery_runs_7d": 28, "applications_submitted_7d": 4},
    "extension": {"connected_devices": 2, "used_24h": 1, "used_7d": 2, "unused_30d": 0, "expired": 0, "bundled_version": "2.0.0", "version_reporting": False,
                  "note": "The extension doesn't send its version to the server yet."},
}

FIXTURES: dict[str, object] = {
    "/api/v1/gaps": {"best": GAPS[0], "alternatives": GAPS[1:3], "gaps": GAPS},
    **{f"/api/v1/gaps/{g['id']}": gap_detail(g) for g in GAPS},
    "/api/v1/skills": SKILLS,
    "/api/v1/matches/history": MATCH_HISTORY,
    "/api/v1/learning-sessions": SESSIONS,
    "/api/v1/consents": [{"kind": "learning_tracking", "granted": True, "text": "Track time on learning sessions you start.", "granted_at": iso(10), "revoked_at": None}],
    "/api/v1/countries": COUNTRIES,
    "/api/v1/career-goals": {"search_mode": "both", "target_countries": ["GB", "DE"], "seniority": "entry", "open_to_relocation": True,
                             "work_authorization": ["IN"], "needs_sponsorship": True},
    "/api/v1/country-fit": COUNTRY_FIT,
    "/api/v1/visa-routes": [ROUTE_SW, ROUTE_GT],
    "/api/v1/interview-prep/100": PREP,
    "/api/v1/interview-practice": PRACTICES,
    "/api/v1/interview-practice/7": PRACTICES[0],
    "/api/v1/interview-practice/5": PRACTICES[1],
    "/api/v1/mentor/plan": PLAN,
    "/api/v1/mentor/reflections": [REFLECTION, {**REFLECTION, "id": 2, "week_start": day(14), "outcome": "Finished Power BI project.", "obstacle": "None really.",
                                                 "next_action": "Start dbt course", "mood": 5, "created_at": iso(13)}],
    "/api/v1/mentoring/mentors": MENTORS,
    "/api/v1/mentoring/mentors/11/notes": NOTES,
    "/api/v1/mentor-workspace/candidates": CANDIDATES,
    "/api/v1/mentor-workspace/candidates/11": CANDIDATE,
    "/api/v1/admin/metrics": {"total_users": 12, "active_users": 11, "total_jobs": 12840, "total_applications": 64, "total_interviews": 9, "total_offers": 2,
                              "active_sources": 7, "server_time": iso()},
    "/api/v1/admin/users": ADMIN_USERS,
    "/api/v1/admin/invites": INVITES,
    "/api/v1/admin/audit-log": AUDIT,
    "/api/v1/admin/jobs": ADMIN_JOBS,
    "/api/v1/admin/product-metrics": PRODUCT,
    "/api/v1/admin/system": SYSTEM,
    "/api/v1/admin/ops-health": OPS,
}
