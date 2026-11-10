"""Status changes made by this implementation pass, batch by batch (applied after audit_baseline.py).
Run:  python docs/requirements/audit_progress.py"""

from tracker import set_status, sync

D, P, M, B, F, N, X = "DONE_VERIFIED", "PARTIAL", "MISSING", "BLOCKED_EXTERNAL", "PLANNED_FUTURE", "NOT_APPLICABLE_JUSTIFIED", "BROKEN"
T = "tests/api/test_compliance_and_scoring.py"

BATCHES: dict[str, list[tuple]] = {
    "1 compliance, security, scoring": [
        ("MAT-02", D, "backend/services/scoring_v2.py WEIGHTS 30/20/15/10/10/5/5/5 (assert sum 100)", f"{T}::test_weights_sum_to_100_and_are_versioned", ""),
        ("MAT-03", D, "matching_service.apply stores user_jobs.score_version/match_components; GET /jobs/{id}/analysis dimensions", f"{T}; test_portal_workflow.py::test_import_scores_and_dedups", ""),
        ("MAT-04", D, "scoring_v2: unknown dimensions excluded + re-normalised; eligibility unknown", f"{T}::test_unknown_salary_and_authorisation_stay_unknown", ""),
        ("MAT-01", P, "scoring_v2 eligibility pass/fail/unknown separate from total", f"{T}::test_eligibility_is_separate_from_suitability", "UI and /jobs/{id}/intelligence still to align"),
        ("DSC-13", D, "scrapling_client._honest_get: JobPilot UA, no impersonation/stealth, robots failure = disallow, per-hop SSRF", f"{T}::test_fetcher_does_not_impersonate_a_browser; test_robots_failure_is_treated_as_disallowed", ""),
        ("NEG-02", D, "no browser impersonation; JS-only pages reported unsupported", f"{T}::test_fetcher_does_not_impersonate_a_browser", ""),
        ("ID-03", P, "reap-expired and connector test now CurrentAdmin; tailor/orchestrate check job is in user's feed", f"{T}::test_global_maintenance_actions_are_admin_only; test_resume_studio.py", "ownership tests for 0007 tables pending"),
        ("ID-04", P, "auth.forgot_password honest 503 without SMTP; single-use token bound to password hash; sessions revoked; rate limited", "test_achievements.py::test_password_reset_flow", "frontend forgot/reset screens pending"),
        ("SEC-06", P, "reset links no longer kept in memory (email_service.test_outbox None in production)", "test_achievements.py::test_password_reset_flow", ""),
        ("RES-15", P, "resume_tailor_service summary from own facts only; audit checks bullets/skills are the candidate's", f"{T}::test_new_master_profile_contains_no_invented_facts; test_resume_studio.py", "suggestion engine guard pending"),
        ("NEG-05", P, "fabricated tailored summary and seeded sample profile removed", f"{T}::test_new_master_profile_contains_no_invented_facts", ""),
        ("PRF-02", P, "ProfileSkill.is_verified now defaults False; v2 profile seeded only from confirmed facts", f"{T}::test_new_master_profile_contains_no_invented_facts", ""),
        ("NEG-03", P, "scoring_v2.DISCLAIMER returned by /jobs/{id}/analysis", f"{T}::test_score_is_not_presented_as_a_hiring_prediction", "UI wording pending"),
    ],
}

if __name__ == "__main__":
    for name, updates in BATCHES.items():
        set_status(updates)
    sync()
