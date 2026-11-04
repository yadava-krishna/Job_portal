from datetime import date

import pytest

from conftest import AR_JD, FakeLLM, llm_response
from core.llm import LLMError
from core.models import EligibilityStatus, JobPosting, Platform
from intelligence.cover_letter import generate_cover_letter, template_cover_letter, verify_letter
from intelligence.eligibility import evaluate_eligibility
from intelligence.jd_analyzer import JDAnalyzer, parse_experience, parse_posted_date, parse_salary
from intelligence.job_matcher import JobMatcher
from applications.screening_answers import ScreeningAnswerer
from core.models import NEEDS_CANDIDATE_INPUT


def job(**kw) -> JobPosting:
    base = dict(job_key="linkedin:1", platform=Platform.LINKEDIN, company="Acme Health", title="Accounts Receivable Analyst",
                url="https://www.linkedin.com/jobs/view/1/", location="Bengaluru", work_mode="Hybrid", description=AR_JD,
                exp_min_years=3, exp_max_years=6, required_skills=["Accounts Receivable", "Payment Posting", "PivotTables"],
                preferred_skills=["Power BI"], education_requirements=["B.Com"])
    base.update(kw)
    return JobPosting(**base)


@pytest.mark.parametrize("text,expected", [("3-6 years of experience", (3, 6)), ("Minimum 4 years", (4, None)),
                                           ("5+ years in finance", (5, None)), ("2 to 4 yrs", (2, 4)), ("no requirement", (None, None))])
def test_parse_experience(text, expected):
    assert parse_experience(text)[:2] == expected


@pytest.mark.parametrize("text,expected", [("CTC: 6-9 LPA", (6, 9)), ("₹ 4,50,000 - 6,00,000 per annum", (4.5, 6.0)),
                                           ("Rs 40,000 - 50,000 per month", (4.8, 6.0)), ("Up to 12 Lakhs", (None, 12))])
def test_parse_salary(text, expected):
    assert parse_salary(text)[:2] == expected


def test_posted_date_relative():
    assert parse_posted_date("2 days ago", date(2026, 11, 4)) == date(2026, 11, 2)
    assert parse_posted_date("2026-11-01", date(2026, 11, 4)) == date(2026, 11, 1)


def test_jd_analyzer_required_vs_preferred(taxonomy):
    a = JDAnalyzer(taxonomy).analyze(AR_JD + "\nCA is mandatory for this role.")
    assert "Payment Posting" in a.required_skills and "Power BI" in a.preferred_skills
    assert "Power BI" not in a.required_skills
    assert (a.exp_min, a.exp_max) == (3, 6)
    assert a.employment_type == "Full-time"
    assert "CA" in a.mandatory_qualifications


def test_rule_based_scoring_is_explained(settings, profile, taxonomy):
    m = JobMatcher(settings.matching, settings.search, profile, taxonomy)
    r = m.score(job())
    assert r.scoring_method == "rule_based"
    assert [c.name for c in r.components] == ["core_skills", "experience", "responsibilities", "education", "location"]
    assert abs(sum(c.weighted for c in r.components) - r.overall_score) < 0.1
    assert abs(sum(c.weight for c in r.components) - 100) < 0.01
    assert "Accounts Receivable" in r.matching_skills
    assert "Power BI" in r.missing_optional_skills and "Power BI" not in r.missing_skills
    assert r.overall_score >= 70


def test_optional_skill_missing_does_not_sink_score(settings, profile, taxonomy):
    m = JobMatcher(settings.matching, settings.search, profile, taxonomy)
    with_opt = m.score(job(preferred_skills=["Power BI", "Tableau", "SQL"]))
    without = m.score(job(preferred_skills=[]))
    assert without.overall_score - with_opt.overall_score < 6


def test_categories(settings, profile, taxonomy):
    m = JobMatcher(settings.matching, settings.search, profile, taxonomy)
    assert [m.category(x) for x in (85, 84.9, 70, 55, 54.9)] == ["Excellent match", "Good match", "Good match", "Moderate match", "Low match"]


def test_llm_scoring_weights_computed_in_code_and_hallucinated_skills_dropped(settings, profile, taxonomy):
    llm = FakeLLM(llm_response(matching_skills=["Accounts Receivable", "Kubernetes"]))
    m = JobMatcher(settings.matching, settings.search, profile, taxonomy, llm, "fake")
    r = m.score(job())
    assert r.scoring_method.startswith("llm")
    assert r.matching_skills == ["Accounts Receivable"]
    assert any("Kubernetes" in n for n in r.notes)
    # experience = 50% deterministic years fit + 50% LLM relevance (80); others straight from the LLM
    years = m.years_fit(job())[0]
    expected = (90 * 35 + (years + 80) / 2 * 25 + 85 * 20 + 100 * 10 + 100 * 10) / 100
    assert r.overall_score == pytest.approx(expected, abs=0.1)


def test_llm_permanent_failure_falls_back_transient_raises(settings, profile, taxonomy):
    m = JobMatcher(settings.matching, settings.search, profile, taxonomy, FakeLLM(LLMError("refused")), "fake")
    r = m.score(job())
    assert r.scoring_method == "rule_based" and any("LLM scoring failed" in n for n in r.notes)
    m2 = JobMatcher(settings.matching, settings.search, profile, taxonomy, FakeLLM(LLMError("429", transient=True)), "fake")
    with pytest.raises(LLMError):
        m2.score(job())


def test_missing_description_low_confidence(settings, profile, taxonomy):
    llm = FakeLLM(llm_response())
    m = JobMatcher(settings.matching, settings.search, profile, taxonomy, llm, "fake")
    r = m.score(job(description=None, required_skills=[], preferred_skills=[]))
    assert r.confidence == "low" and llm.calls == 0


def test_location_scoring(settings, profile, taxonomy):
    m = JobMatcher(settings.matching, settings.search, profile, taxonomy)
    assert m.location_fit(job(location="Bangalore", work_mode="On-site"))[0] == 100
    assert m.location_fit(job(location="India", work_mode="Remote"))[0] == 100
    assert m.location_fit(job(location="Pune", work_mode="On-site"))[0] == 20


def test_eligibility_rules(settings):
    e = settings.eligibility
    today = date(2026, 11, 4)
    assert evaluate_eligibility(job(), e, settings.search, 5.9, today).status == EligibilityStatus.ELIGIBLE
    r = evaluate_eligibility(job(exp_min_years=10), e, settings.search, 5.9, today)
    assert r.status == EligibilityStatus.INELIGIBLE and "Requires 10+" in r.reasons[0]
    assert evaluate_eligibility(job(title="Director of Finance"), e, settings.search, 5.9, today).status == EligibilityStatus.INELIGIBLE
    assert evaluate_eligibility(job(location="Pune", work_mode="On-site"), e, settings.search, 5.9, today).status == EligibilityStatus.INELIGIBLE
    assert evaluate_eligibility(job(mandatory_qualifications=["CA"]), e, settings.search, 5.9, today).status == EligibilityStatus.NEEDS_REVIEW
    assert evaluate_eligibility(job(posted_date=date(2026, 9, 1)), e, settings.search, 5.9, today).status == EligibilityStatus.INELIGIBLE


def test_screening_never_guesses(profile, taxonomy):
    a = ScreeningAnswerer(profile, {}, taxonomy)
    for q in ["What is your current CTC?", "Expected salary?", "Notice period?", "Are you willing to relocate?",
              "Are you authorized to work in India?", "What is your date of birth?", "Rate your SQL skills 1-10",
              "Do you have experience with Kubernetes?"]:
        assert a.answer(q)["answer"] == NEEDS_CANDIDATE_INPUT, q
    assert "years" in a.answer("Total years of experience")["answer"]
    assert a.answer("Do you have experience with payment posting?")["answer"].startswith("Yes")
    assert "B.Com" in a.answer("Highest qualification")["answer"]


def test_screening_uses_verified_facts(profile, taxonomy):
    a = ScreeningAnswerer(profile, {"notice_period": "30 days", "expected_ctc": None, "willing_to_relocate": False}, taxonomy)
    assert a.answer("What is your notice period?")["answer"] == "30 days"
    assert a.answer("Expected CTC?")["answer"] == NEEDS_CANDIDATE_INPUT
    assert a.answer("Willing to relocate to Pune?")["answer"] == "No"


def test_cover_letter_verification(profile):
    j = job()
    assert verify_letter("Dear Acme Health, I processed 500 claims daily.", j, profile)  # 500 not on resume
    letter, method = generate_cover_letter(j, profile, None, FakeLLM({"cover_letter": "Dear Acme Health team, I improved accuracy by 99%."}))
    assert method.startswith("template")
    tpl = template_cover_letter(j, profile, None)
    assert "Acme Health" in tpl and not verify_letter(tpl, j, profile)
