"""Hard eligibility rules, evaluated separately from the match score."""

from __future__ import annotations

import re
from datetime import date

from core.models import EligibilityResult, EligibilityStatus, JobPosting
from core.settings import EligibilityConfig, SearchConfig
from discovery.deduplication import normalize_company


def evaluate_eligibility(job: JobPosting, cfg: EligibilityConfig, search: SearchConfig, candidate_years: float, today: date) -> EligibilityResult:
    ineligible: list[str] = []
    review: list[str] = []

    company = normalize_company(job.company)
    for excluded in cfg.excluded_companies:
        if normalize_company(excluded) and normalize_company(excluded) == company:
            ineligible.append(f"Company '{job.company}' is in the excluded list")

    for kw in cfg.excluded_title_keywords:
        if re.search(rf"(?<![A-Za-z]){re.escape(kw)}(?![A-Za-z])", job.title or "", re.I):
            ineligible.append(f"Title contains excluded keyword '{kw}'")

    if job.exp_min_years is not None and job.exp_min_years - candidate_years > cfg.max_experience_gap_years:
        ineligible.append(
            f"Requires {job.exp_min_years:g}+ years; candidate has {candidate_years:.1f} "
            f"(gap above the allowed {cfg.max_experience_gap_years:g} years)"
        )

    if job.work_mode and job.work_mode in ("Remote", "Hybrid", "On-site") and job.work_mode not in cfg.allowed_work_modes:
        ineligible.append(f"Work mode {job.work_mode} is not allowed")

    if job.employment_type and job.employment_type in ("Full-time", "Contract", "Part-time", "Internship") and job.employment_type not in cfg.allowed_employment_types:
        ineligible.append(f"Employment type {job.employment_type} is not allowed")

    if cfg.allowed_locations and job.work_mode != "Remote" and job.location:
        loc = job.location.lower()
        if "remote" not in loc and not any(a.lower() in loc for a in cfg.allowed_locations):
            ineligible.append(f"Location '{job.location}' is outside the allowed locations")

    if cfg.enforce_min_salary and search.min_salary_lpa is not None:
        top = job.salary_max_lpa or job.salary_min_lpa
        if top is not None and top < search.min_salary_lpa:
            ineligible.append(f"Salary up to {top:g} LPA is below the minimum {search.min_salary_lpa:g} LPA")

    if job.posted_date and (today - job.posted_date).days > cfg.max_job_age_days:
        ineligible.append(f"Posted {(today - job.posted_date).days} days ago (limit {cfg.max_job_age_days})")

    lacking = {q.lower() for q in cfg.qualifications_candidate_lacks}
    for q in job.mandatory_qualifications:
        if q.lower() in lacking or (q == "CA" and "chartered accountant" in lacking):
            review.append(f"Description says {q} is mandatory; the candidate's resume does not list it")

    for flag in job.verification_flags:
        review.append(f"Verification: {flag}")

    if ineligible:
        return EligibilityResult(status=EligibilityStatus.INELIGIBLE, reasons=ineligible + review)
    if review:
        return EligibilityResult(status=EligibilityStatus.NEEDS_REVIEW, reasons=review)
    return EligibilityResult(status=EligibilityStatus.ELIGIBLE, reasons=["All hard requirements met"])
