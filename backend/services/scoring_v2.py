"""Versioned, explainable job scoring (spec 02 §11): eight weighted dimensions that add up to 100.

    required skills 30 | experience 20 | responsibilities 15 | education/certifications 10 |
    location/work mode 10 | industry/domain 5 | salary 5 | work authorisation/sponsorship 5

The first five dimensions reuse the existing JobMatcher component scores (rule-based or LLM-assisted, overall
always computed in code). The last three are deterministic from the job record and the candidate's goals.

Rules:
* A dimension with no data is `unknown`: it is left out and the remaining weights are re-normalised, so missing
  salary or authorisation information neither helps nor hurts. The UI shows it as unknown.
* Suitability (this score) is separate from hard eligibility (pass | fail | unknown). An ineligible job can still
  score well; it is just never shortlisted.
* The score is a relevance estimate for prioritising effort, not a prediction of being hired.
"""

from __future__ import annotations

from typing import Any

from backend.models import Job, JobPreference
from core.models import EligibilityStatus, MatchResult

SCORE_VERSION = "v2.2026-11"
WEIGHTS: dict[str, float] = {
    "required_skills": 30, "experience": 20, "responsibilities": 15, "education_certifications": 10,
    "location_work_mode": 10, "industry_domain": 5, "salary": 5, "work_authorization": 5,
}
LABELS = {
    "required_skills": "Required skills", "experience": "Experience", "responsibilities": "Responsibilities",
    "education_certifications": "Education & certifications", "location_work_mode": "Location & work mode",
    "industry_domain": "Industry / domain", "salary": "Salary", "work_authorization": "Work authorisation",
}
_FROM_V1 = {"core_skills": "required_skills", "experience": "experience", "responsibilities": "responsibilities",
            "education": "education_certifications", "location": "location_work_mode"}
DISCLAIMER = "A relevance estimate to help you prioritise. It is not a prediction that you will be hired."
assert sum(WEIGHTS.values()) == 100


def _industry(job: Job, prefs: JobPreference | None) -> tuple[float | None, str]:
    wanted = [w.lower() for w in ((prefs.industries if prefs else None) or []) + ((prefs.domains if prefs else None) or [])]
    if not job.industry:
        return None, "the posting does not state an industry"
    if not wanted:
        return None, "you have not chosen target industries"
    hit = any(w in job.industry.lower() or job.industry.lower() in w for w in wanted)
    return (100.0, f"{job.industry} is one of your target industries") if hit else (40.0, f"{job.industry} is not one of your target industries")


def _salary(job: Job, prefs: JobPreference | None) -> tuple[float | None, str]:
    want = prefs.salary_min / 100000 if prefs and prefs.salary_min and prefs.currency == "INR" else None
    top = job.salary_max_lpa or job.salary_min_lpa
    if top is None:
        return None, "the posting does not state a salary"
    if want is None:
        return None, "you have not set a minimum salary"
    if top >= want:
        return 100.0, f"up to {top:g} LPA meets your minimum of {want:g} LPA"
    return max(0.0, round(100 * top / want - 30, 1)), f"up to {top:g} LPA is below your minimum of {want:g} LPA"


def _authorization(job: Job, prefs: JobPreference | None) -> tuple[float | None, str, str]:
    """(score, evidence, eligibility) where eligibility is pass | fail | unknown for this dimension alone."""
    country = (job.country or "").upper() or None
    auth = [c.upper() for c in ((prefs.work_authorization if prefs else None) or [])]
    if not auth and prefs is not None and getattr(prefs, "search_mode", "india") == "india":
        auth = ["IN"]  # India-only search: the candidate has said they are looking where they can work
    if not country:
        return None, "the job's country is not known", "unknown"
    if not auth:
        return None, "you have not told us where you are authorised to work", "unknown"
    if country in auth:
        return 100.0, f"you are authorised to work in {country}", "pass"
    signal = job.sponsorship_signal or "unknown"
    needs = prefs.needs_sponsorship if prefs else None
    if signal == "none":
        if needs is True:
            return 0.0, f"needs authorisation for {country}; the posting says it does not sponsor ({job.sponsorship_evidence or ''})", "fail"
        return 30.0, f"job is in {country} and the posting says it does not sponsor visas", "unknown"
    if signal == "verified":
        return 80.0, f"needs authorisation for {country}; the posting says sponsorship is offered", "pass"
    if signal == "inferred":
        return 50.0, f"needs authorisation for {country}; sponsorship is inferred, not confirmed ({job.sponsorship_evidence or 'no detail'})", "unknown"
    if needs is False:
        return 70.0, f"job is in {country}; you said you do not need sponsorship", "pass"
    return 20.0, f"needs authorisation for {country}; sponsorship is unknown", "unknown"


def score(match: MatchResult, elig_status: EligibilityStatus, elig_reasons: list[str], job: Job,
          prefs: JobPreference | None) -> dict[str, Any]:
    raw: dict[str, tuple[float | None, str, str]] = {}
    for c in match.components:
        if c.name in _FROM_V1:
            raw[_FROM_V1[c.name]] = (c.score, c.evidence, c.method)
    s, ev = _industry(job, prefs)
    raw["industry_domain"] = (s, ev, "deterministic")
    s, ev = _salary(job, prefs)
    raw["salary"] = (s, ev, "deterministic")
    s, ev, auth_elig = _authorization(job, prefs)
    raw["work_authorization"] = (s, ev, "deterministic")

    known = {k: v for k, v in raw.items() if v[0] is not None}
    known_weight = sum(WEIGHTS[k] for k in known) or 1
    components = []
    for key, base in WEIGHTS.items():
        sc, evidence, method = raw.get(key, (None, "not assessed", "none"))
        eff = round(base * 100 / known_weight, 2) if sc is not None else 0.0
        components.append({"name": key, "label": LABELS[key], "status": "known" if sc is not None else "unknown",
                           "score": None if sc is None else round(sc, 1), "base_weight": base, "weight": eff,
                           "weighted": 0.0 if sc is None else round(sc * eff / 100, 2), "evidence": evidence, "method": method})
    total = round(sum(c["weighted"] for c in components), 1)

    if elig_status == EligibilityStatus.INELIGIBLE or auth_elig == "fail":
        eligibility = "fail"
    elif elig_status == EligibilityStatus.ELIGIBLE and auth_elig == "pass":
        eligibility = "pass"
    else:
        eligibility = "unknown"
    reasons = list(elig_reasons)
    if auth_elig != "pass":
        reasons.append(f"Work authorisation: {raw['work_authorization'][1]}")
    return {"score_version": SCORE_VERSION, "total": total, "components": components, "eligibility": eligibility,
            "eligibility_reasons": reasons, "unknown": [c["name"] for c in components if c["status"] == "unknown"],
            "disclaimer": DISCLAIMER}
