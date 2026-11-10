"""Compliance fixes and the versioned scoring contract (MAT-02/03/04, DSC-13, NEG-02, ID-03, RES-15)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from api_helpers import auth, register

from backend.services import scoring_v2
from core.models import ComponentScore, EligibilityStatus, MatchResult


def _match(score: float = 80) -> MatchResult:
    names = ["core_skills", "experience", "responsibilities", "education", "location"]
    comps = [ComponentScore(name=n, score=score, weight=20, weighted=score / 5, evidence="e", method="rule_based") for n in names]
    return MatchResult(overall_score=score, category="good", components=comps)


def _job(**kw):
    base = dict(industry=None, salary_min_lpa=None, salary_max_lpa=None, country=None, location=None, sponsorship_signal="unknown",
                sponsorship_evidence=None)
    return SimpleNamespace(**{**base, **kw})


def _prefs(**kw):
    base = dict(industries=[], domains=[], salary_min=None, currency="INR", work_authorization=[], search_mode="india",
                needs_sponsorship=None)
    return SimpleNamespace(**{**base, **kw})


def test_weights_sum_to_100_and_are_versioned():
    assert sum(scoring_v2.WEIGHTS.values()) == 100
    assert scoring_v2.WEIGHTS == {"required_skills": 30, "experience": 20, "responsibilities": 15, "education_certifications": 10,
                                  "location_work_mode": 10, "industry_domain": 5, "salary": 5, "work_authorization": 5}
    out = scoring_v2.score(_match(), EligibilityStatus.ELIGIBLE, [], _job(), _prefs())
    assert out["score_version"] == scoring_v2.SCORE_VERSION and len(out["components"]) == 8
    assert abs(sum(c["weighted"] for c in out["components"]) - out["total"]) < 0.11


def test_unknown_salary_and_authorisation_stay_unknown():
    out = scoring_v2.score(_match(80), EligibilityStatus.ELIGIBLE, [], _job(), _prefs())
    dims = {c["name"]: c for c in out["components"]}
    for name in ("salary", "work_authorization", "industry_domain"):
        assert dims[name]["status"] == "unknown" and dims[name]["score"] is None and dims[name]["weighted"] == 0
    assert out["total"] == 80.0  # unknowns neither help nor hurt: remaining weights are re-normalised
    assert out["eligibility"] == "unknown"  # country unknown -> eligibility unknown, not pass


def test_eligibility_is_separate_from_suitability():
    strong = scoring_v2.score(_match(95), EligibilityStatus.INELIGIBLE, ["Needs 10 years"], _job(country="IN"), _prefs())
    assert strong["total"] > 90 and strong["eligibility"] == "fail"
    ok = scoring_v2.score(_match(60), EligibilityStatus.ELIGIBLE, [], _job(country="IN"), _prefs())
    assert ok["eligibility"] == "pass"
    abroad = scoring_v2.score(_match(60), EligibilityStatus.ELIGIBLE, [], _job(country="DE"), _prefs())
    assert abroad["eligibility"] == "unknown"  # no authorisation and sponsorship unknown: not assumed either way
    sponsored = scoring_v2.score(_match(60), EligibilityStatus.ELIGIBLE, [], _job(country="DE", sponsorship_signal="verified"), _prefs())
    assert sponsored["eligibility"] == "pass"


def test_salary_dimension_uses_candidate_minimum():
    low = scoring_v2.score(_match(), EligibilityStatus.ELIGIBLE, [], _job(salary_max_lpa=6), _prefs(salary_min=1_000_000))
    high = scoring_v2.score(_match(), EligibilityStatus.ELIGIBLE, [], _job(salary_max_lpa=14), _prefs(salary_min=1_000_000))
    sal = lambda o: next(c for c in o["components"] if c["name"] == "salary")  # noqa: E731
    assert sal(low)["score"] < 50 and sal(high)["score"] == 100


def test_score_is_not_presented_as_a_hiring_prediction():
    assert "not a prediction" in scoring_v2.DISCLAIMER


def test_fetcher_does_not_impersonate_a_browser():
    from backend.services import scrapling_client

    src = inspect.getsource(scrapling_client)
    assert "impersonate=" not in src and "StealthyFetcher.fetch" not in src and "Mozilla/5.0" not in src
    assert "JobPilot" in scrapling_client.USER_AGENT


def test_robots_failure_is_treated_as_disallowed(monkeypatch):
    from backend.services import scrapling_client
    from backend.services.ats import base as ats_base

    monkeypatch.setattr(ats_base, "transport_override", None)
    monkeypatch.setattr(scrapling_client, "mock_fetch_handler", None)
    c = scrapling_client.ScraplingClient()

    def boom(url):
        raise OSError("network down")

    monkeypatch.setattr(c, "validate_url", boom)
    with pytest.raises(scrapling_client.RobotsDisallowedError):
        c.check_robots("https://careers.example.com/jobs")


def test_global_maintenance_actions_are_admin_only(client):
    h = auth(register(client, "plain@example.com"))
    assert client.post("/api/v1/discovery/reap-expired", headers=h).status_code == 403
    assert client.post("/api/v1/discovery/connectors/remotive/test", headers=h).status_code == 403


def test_new_master_profile_contains_no_invented_facts(client):
    from backend.db import session_factory
    from backend.models import User
    from backend.services.profile_master_service import ProfileMasterService

    register(client, "fresh@example.com")
    with session_factory()() as db:
        uid = db.query(User).filter(User.email == "fresh@example.com").one().id
        p = ProfileMasterService.get_or_create_profile(db, uid)
        assert p.headline is None and p.summary is None and p.years_experience == 0
        assert p.skills == [] and p.experiences == [] and p.preferred_locations == []


def test_country_is_inferred_only_from_unambiguous_locations():
    assert scoring_v2.infer_country("Bengaluru, Karnataka") == "IN"
    assert scoring_v2.infer_country("Remote") is None
    assert scoring_v2.infer_country("London or Bengaluru") is None  # two countries: don't guess
    out = scoring_v2.score(_match(), EligibilityStatus.ELIGIBLE, [], _job(location="Pune, India"), _prefs())
    auth = next(c for c in out["components"] if c["name"] == "work_authorization")
    assert auth["status"] == "known" and "inferred" in auth["evidence"] and out["eligibility"] == "pass"
