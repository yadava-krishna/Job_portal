"""Per-user matching with the existing JobMatcher and eligibility rules."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import CandidateProfile, Job, JobMatchReport, JobPreference, User, UserJob, utcnow
from backend.services import resume_service, scoring_v2
from core import timeutil
from core.llm import LLMClient, build_llm
from core.models import EligibilityStatus, JobPosting, MatchResult, Platform
from core.settings import EligibilityConfig, LLMConfig, MatchCategories, MatchingConfig, MatchWeights, SearchConfig
from core.skills import SkillTaxonomy
from intelligence.eligibility import evaluate_eligibility
from intelligence.job_matcher import JobMatcher

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _llm_cached(provider: str, model: str, effort: str, base_url: str | None, key_env: str, key_present: bool) -> tuple[LLMClient | None, str]:
    cfg = LLMConfig(provider=provider, model=model, effort=effort, base_url=base_url, api_key_env=key_env, fallback_to_rule_based=True)
    return build_llm(cfg)


def get_llm(settings: BackendSettings) -> tuple[LLMClient | None, str]:
    return _llm_cached(settings.llm_provider, settings.llm_model, settings.llm_effort, settings.llm_base_url,
                       settings.llm_api_key_env, bool(os.environ.get(settings.llm_api_key_env)))


def configs_for(prefs: JobPreference | None) -> tuple[MatchingConfig, SearchConfig, EligibilityConfig]:
    p = prefs
    weights = MatchWeights(**{k: v for k, v in ((p.weights if p else None) or {}).items() if k in MatchWeights.model_fields})
    matching = MatchingConfig(min_match_score=p.min_match_score if p else 70, weights=weights, categories=MatchCategories(),
                              require_description_for_shortlist=True)
    work_modes = (p.work_modes if p and p.work_modes else ["Remote", "Hybrid", "On-site"])
    locations = (p.locations if p and p.locations else [])
    if "Remote" in work_modes and not any("remote" in l.lower() for l in locations):
        locations = [*locations, "Remote"]
    # model_construct: preferences were validated by the API schema; the CLI's "at least one" rules don't apply here.
    search = SearchConfig.model_construct(
        job_titles=(p.job_titles if p else []) or [], locations=locations or ["Remote"], posted_within_hours=24,
        experience_min_years=(p.experience_min if p and p.experience_min is not None else 0),
        experience_max_years=(p.experience_max if p and p.experience_max is not None else 50),
        min_salary_lpa=(p.salary_min / 100000 if p and p.salary_min and p.currency == "INR" else None),
        employment_types=(p.employment_types if p and p.employment_types else ["Full-time", "Contract"]), work_modes=work_modes,
    )
    city_prefs = [l for l in (p.locations if p else []) if "remote" not in l.lower()]
    if any(c.lower() in ("bengaluru", "bangalore") for c in city_prefs):
        city_prefs = list(dict.fromkeys([*city_prefs, "Bengaluru", "Bangalore"]))
    eligibility = EligibilityConfig.model_construct(
        max_experience_gap_years=2.0, allowed_work_modes=work_modes,
        allowed_employment_types=list(dict.fromkeys([*search.employment_types, "Full-time", "Contract"])) if not p or not p.employment_types else p.employment_types,
        allowed_locations=city_prefs, enforce_min_salary=bool(p and p.salary_min), excluded_companies=(p.excluded_companies if p else []),
        excluded_title_keywords=[], qualifications_candidate_lacks=[], max_job_age_days=45,
    )
    return matching, search, eligibility


def job_to_posting(job: Job) -> JobPosting:
    platform = Platform(job.platform) if job.platform in {p.value for p in Platform} else Platform.LINKEDIN
    return JobPosting(
        job_key=job.job_key, platform=platform, platform_job_id=job.external_job_id, company=job.company or "",
        title=job.title or "", url=job.job_url, location=job.location, work_mode=job.work_mode, employment_type=job.employment_type,
        experience_required=job.experience_required, exp_min_years=job.experience_min, exp_max_years=job.experience_max,
        salary_range=job.salary_range, salary_min_lpa=job.salary_min_lpa, salary_max_lpa=job.salary_max_lpa, posted_date=job.posted_at,
        description=job.description, required_skills=job.required_skills or [], preferred_skills=job.preferred_skills or [],
        education_requirements=job.education_requirements or [], mandatory_qualifications=job.mandatory_qualifications or [],
        application_method=job.application_method, source=job.source, screening_questions=job.screening_questions or [],
        fingerprint=job.fingerprint or "", verification_flags=job.verification_flags or [],
    )


class UserMatcher:
    """Scores jobs for one user. Built once per request/run."""

    def __init__(self, db: Session, settings: BackendSettings, user: User, *, use_llm: bool = True):
        self.user = user
        prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
        if prof is None or not prof.confirmed_profile:
            raise HTTPException(status.HTTP_409_CONFLICT, "Confirm your profile before matching jobs.")
        self.taxonomy: SkillTaxonomy = resume_service.taxonomy(settings)
        self.profile = resume_service.matcher_profile(prof, self.taxonomy)
        from backend.services.career_service import evidenced_skills
        have = {x["name"].lower() for x in self.profile["skills"]}
        for name in evidenced_skills(db, user.id):  # project/employment evidence added in JobPilot counts too
            canon = self.taxonomy.canonical(name) or name
            if canon.lower() not in have:
                self.profile["skills"].append({"name": canon, "source": "skill_evidence"})
                have.add(canon.lower())
        self.verified_facts = prof.verified_facts or {}
        self.prefs = db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none()
        self.matching, self.search, self.eligibility = configs_for(self.prefs)
        llm, desc = get_llm(settings) if use_llm else (None, "rule_based (configured)")
        self.llm, self.llm_desc = llm, desc
        self.matcher = JobMatcher(self.matching, self.search, self.profile, self.taxonomy, llm, desc,
                                  willing_to_relocate=self.verified_facts.get("willing_to_relocate"))

    @property
    def candidate_years(self) -> float:
        return self.matcher.candidate_years

    def score(self, job: Job) -> tuple[MatchResult, Any]:
        posting = job_to_posting(job)
        match = self.matcher.score(posting)
        if job.description_is_snippet:
            match.notes.append("Only a description snippet is available; paste the full description for a more reliable score.")
            match.confidence = "low"
        elig = evaluate_eligibility(posting, self.eligibility, self.search, self.candidate_years, timeutil.today())
        return match, elig

    def apply(self, uj: UserJob, *, min_score: float | None = None) -> UserJob:
        """Score and (re)classify. min_score overrides the preference threshold (a saved search's own threshold)."""
        match, elig = self.score(uj.job)
        v2 = scoring_v2.score(match, elig.status, elig.reasons, uj.job, self.prefs)
        old_score = uj.match_score
        # The stored score is the versioned 8-dimension total; the v1 breakdown stays inside `match` for reference.
        match.category = self.matcher.category(v2["total"])
        uj.match_score = v2["total"]
        uj.match_category = match.category
        uj.match = {**match.model_dump(mode="json"), "v1_overall_score": match.overall_score, "overall_score": v2["total"],
                    "disclaimer": v2["disclaimer"], "unknown_dimensions": v2["unknown"]}
        uj.score_version = v2["score_version"]
        uj.match_components = v2["components"]
        uj.eligibility = v2["eligibility"]
        self.last_change = (old_score, v2["total"])
        uj.matching_skills = match.matching_skills
        uj.missing_skills = match.missing_skills
        uj.eligibility_status = elig.status.value
        uj.eligibility_reasons = elig.reasons
        uj.scoring_method = match.scoring_method
        uj.scored_at = utcnow()
        if uj.status in ("new", "shortlisted"):
            threshold = self.matching.min_match_score if min_score is None else min_score
            shortlisted = (uj.match_score >= threshold and elig.status != EligibilityStatus.INELIGIBLE
                           and bool(uj.job.description) and len(uj.job.description.strip()) >= 80)
            uj.status = "shortlisted" if shortlisted else "new"
        return uj


def rescore_user(db: Session, settings: BackendSettings, user: User) -> int:
    """Re-score every non-applied job in the user's feed (after profile or preference changes)."""
    try:
        um = UserMatcher(db, settings, user, use_llm=False)
    except Exception:
        return 0
    rows = db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.status.in_(["new", "shortlisted"]))).unique().scalars().all()
    for uj in rows:
        um.apply(uj)
    db.commit()
    return len(rows)


def compute_career_intelligence(db: Session, user: User, job: Job) -> JobMatchReport:
    """Evaluates a job against the Master Candidate Profile V2 using explainable 4-factor scoring:

    Composite = (0.25 * Eligibility) + (0.45 * Skills) + (0.20 * Experience) + (0.10 * Preferences)
    """
    from backend.models import JobMatchReport
    from backend.services.jd_intelligence_service import JDIntelligenceService
    from backend.services.profile_master_service import ProfileMasterService
    from backend.services.skill_gap_service import SkillGapService

    profile = ProfileMasterService.get_or_create_profile(db, user.id)
    candidate_skills = [s.name for s in profile.skills]
    jd_analysis = JDIntelligenceService.analyze_jd(job.title or "", job.description or "", job.location or "")
    gap_report = SkillGapService.analyze_skill_gaps(candidate_skills, jd_analysis.required_skills, jd_analysis.preferred_skills)

    # 1. Eligibility (25% weight)
    eligibility_score = 100.0
    disqualifiers = list(jd_analysis.hard_disqualifiers)
    if jd_analysis.work_authorization and "Clearance" in jd_analysis.work_authorization:
        if profile.work_authorization != "US Citizen":
            eligibility_score = 20.0
            disqualifiers.append("Candidate does not hold required security clearance")

    # 2. Skills (45% weight)
    skill_score = gap_report.match_percentage

    # 3. Experience (20% weight)
    exp_req = jd_analysis.min_years_exp
    candidate_exp = profile.years_experience
    if exp_req <= 0:
        experience_score = 100.0
    elif candidate_exp >= exp_req:
        experience_score = 100.0
    else:
        gap = exp_req - candidate_exp
        experience_score = max(15.0, round(100.0 - (gap * 20.0), 1))
        if candidate_exp < (exp_req * 0.5) and exp_req >= 4.0:
            disqualifiers.append(f"Substantial experience gap: requires {exp_req} yrs, candidate has {candidate_exp} yrs")

    # 4. Preferences (10% weight)
    pref_score = 100.0
    if job.work_mode and profile.work_modes:
        if job.work_mode not in profile.work_modes and not any(m.lower() == job.work_mode.lower() for m in profile.work_modes):
            pref_score -= 30.0
    if job.location and profile.preferred_locations:
        loc_matched = any(p_loc.lower() in job.location.lower() for p_loc in profile.preferred_locations)
        if not loc_matched and not (job.work_mode and "remote" in job.work_mode.lower()):
            pref_score -= 30.0
    pref_score = max(20.0, pref_score)

    # Composite calculation
    composite = round((0.25 * eligibility_score) + (0.45 * skill_score) + (0.20 * experience_score) + (0.10 * pref_score), 1)

    # Hard Disqualifiers Cap: Cap <= 30.0
    if disqualifiers:
        composite = min(composite, 30.0)

    explanation = (
        f"4-Factor Score Breakdown: Eligibility {eligibility_score:.1f}% (wt 0.25), "
        f"Skills {skill_score:.1f}% (wt 0.45), Experience {experience_score:.1f}% (wt 0.20), "
        f"Preferences {pref_score:.1f}% (wt 0.10)."
    )
    if disqualifiers:
        explanation += f" Capped at {composite:.1f}% due to disqualifier(s): {', '.join(disqualifiers)}."

    # Persist or update match report
    report = db.execute(
        select(JobMatchReport).where(
            JobMatchReport.user_id == user.id,
            JobMatchReport.job_id == job.id,
        )
    ).scalar_one_or_none()

    if report is None:
        report = JobMatchReport(
            user_id=user.id,
            job_id=job.id,
            composite_score=composite,
            eligibility_score=eligibility_score,
            skill_score=skill_score,
            experience_score=experience_score,
            preference_score=pref_score,
            matched_skills=gap_report.proven_skills,
            missing_skills=gap_report.missing_required_skills + gap_report.missing_preferred_skills,
            disqualifiers=disqualifiers,
            explanation=explanation,
        )
        db.add(report)
    else:
        report.composite_score = composite
        report.eligibility_score = eligibility_score
        report.skill_score = skill_score
        report.experience_score = experience_score
        report.preference_score = pref_score
        report.matched_skills = gap_report.proven_skills
        report.missing_skills = gap_report.missing_required_skills + gap_report.missing_preferred_skills
        report.disqualifiers = disqualifiers
        report.explanation = explanation

    db.commit()
    db.refresh(report)
    return report

