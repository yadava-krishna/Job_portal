"""Phase 3: discovery quality without AI.

Normalised locations, countries and remote scope; salaries in any currency (never converted); the Himalayas feed read
correctly; freshness that says how a job was confirmed; a polite dead-link check that never visits LinkedIn, Naukri or
Indeed; expiry that doesn't close jobs still listed on the employer's board; remote roles closed to the candidate's
country scored as such; and a match explanation grouped into matched / partial / not matched / not evaluated."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db import Base
from backend.models import Job, utcnow
from core.locations import normalize_location, remote_open_to
from core.salary import comparable, parse


@pytest.mark.parametrize("raw, display, country, scope", [
    ("bangalore, , India", "Bengaluru, India", "IN", None),
    ("Bengaluru, Karnataka, India", "Bengaluru, India", "IN", None),
    ("Hyderabad, , India", "Hyderabad, India", "IN", None),
    ("Gurgaon", "Gurugram, India", "IN", None),
    ("IN-Pune", "Pune, India", "IN", None),
    ("India (Hyderabad)", "Hyderabad, India", "IN", None),
    ("Hybrid - Bangalore", "Bengaluru, India", "IN", None),
    ("Bangalore, IN", "Bengaluru, India", "IN", None),     # IN next to an Indian city is India, not Indiana
    ("Anderson, IN", "Anderson, IN, United States", "US", None),
    ("Chennai, TN", "Chennai, India", "IN", None),
    ("Mountain View, CA", "Mountain View, CA, United States", "US", None),
    ("US-CA-Dublin", "Dublin, CA, United States", "US", None),
    ("Dublin", "Dublin, Ireland", "IE", None),
    ("Amsterdam, Netherlands; London, United Kingdom", "Amsterdam, Netherlands · London, United Kingdom", None, None),
    ("Remote - USA", "Remote (United States)", "US", ["US"]),
    ("India (Remote)", "Remote (India)", "IN", ["IN"]),
    ("Worldwide Remote", "Remote (worldwide)", None, ["*"]),
    ("Remote - Europe", "Remote (Europe)", None, ["EU"]),
    ("Remote", "Remote", None, None),
    ("Insert City, Country", "Insert City, Country", None, None),  # unknown text is kept, never given a guessed country
    (None, None, None, None),
])
def test_locations_are_normalised_consistently(raw, display, country, scope):
    p = normalize_location(raw)
    assert (p.display, p.country, p.remote_scope) == (display, country, scope)


def test_work_mode_hint_and_remote_scope_check():
    assert normalize_location("Hybrid - Bangalore").mode == "Hybrid"
    assert remote_open_to(["US"], ["IN"]) is False
    assert remote_open_to(["APAC"], ["IN"]) is True
    assert remote_open_to(["*"], ["IN"]) is True
    assert remote_open_to(None, ["IN"]) is None


@pytest.mark.parametrize("text, expected", [
    ("$130K – $150K • Offers Equity", ("USD", 130000, 150000, "year", True)),
    ("INR ?–3000000 per year salary", ("INR", None, 3000000, "year", False)),
    ("₹5 Lakh", ("INR", 500000, 500000, "year", False)),
    ("12-18 LPA", ("INR", 1200000, 1800000, "year", False)),
    ("Up to ₹15 LPA", ("INR", None, 1500000, "year", False)),
    ("₹25,000 - ₹40,000 per month", ("INR", 25000, 40000, "month", False)),
    ("USD 2000 - 2500", ("USD", 2000, 2500, None, False)),  # small figure, no period: never annualised
    ("PHP 50000–75000 per month salary", ("PHP", 50000, 75000, "month", False)),
    ("CZK 690000–720000 per year salary", ("CZK", 690000, 720000, "year", False)),
    ("USD 22–28 per hour wage", ("USD", 22, 28, "hour", False)),
    ("£35,000 - £45,000 pa", ("GBP", 35000, 45000, "year", False)),
    ("10L - 14L", ("INR", 1000000, 1400000, "year", True)),
])
def test_salaries_are_parsed_without_ai(text, expected):
    s = parse(text)
    assert (s.currency, s.min, s.max, s.period, s.period_assumed) == expected


@pytest.mark.parametrize("text", ["Benefits: 401(k) and 5 years", "Competitive pay", "", None, "Plus full benefits."])
def test_text_without_a_salary_is_not_a_salary(text):
    assert parse(text) is None


def test_salaries_are_never_compared_across_currencies():
    usd = parse("$80K – $110K")
    assert comparable(usd, 1_200_000, "INR")[0] is None and "does not convert" in comparable(usd, 1_200_000, "INR")[1]
    assert comparable(parse("USD 2000 - 2500"), 20_000, "USD")[0] is None  # period unknown: can't tell
    assert comparable(parse("12-18 LPA"), 1_500_000, "INR")[0] is True
    assert comparable(parse("₹25,000 - ₹40,000 per month"), 600_000, "INR")[0] is False  # 4.8 L a year < 6 L


# ---- connectors ------------------------------------------------------------------------------

def test_himalayas_reads_epoch_dates_expiry_currency_and_who_may_apply():
    from backend.services.connectors.himalayas_connector import HimalayasConnector

    payload = {"jobs": [
        {"title": "On-Chain Researcher", "companyName": "Hermeneutic", "employmentType": "Full Time", "minSalary": None, "maxSalary": None,
         "salaryPeriod": "annual", "seniority": ["Mid-level"], "currency": None, "description": "<p>" + "Research " * 30 + "</p>",
         "locationRestrictions": ["Hong Kong", "Singapore", "United Kingdom", "United States"], "pubDate": 1794823079,
         "expiryDate": "1800007078", "applicationLink": "https://himalayas.app/companies/h/jobs/r", "guid": "https://himalayas.app/companies/h/jobs/r"},
        {"title": "AR Analyst", "companyName": "Acme", "employmentType": "Full Time", "minSalary": 50000, "maxSalary": 60000,
         "salaryPeriod": "annual", "currency": "USD", "locationRestrictions": [], "description": "Collections " * 30,
         "pubDate": "1794823079", "applicationLink": "https://himalayas.app/companies/a/jobs/ar"},
    ]}
    client = SimpleNamespace(fetch_page=lambda url, source_id=None: SimpleNamespace(text=json.dumps(payload)))
    first, second = HimalayasConnector(client).discover()
    assert first.posted_at is not None and first.expires_at is not None and first.expires_at > first.posted_at
    assert first.location == "Remote - Hong Kong; Singapore; United Kingdom; United States" and first.seniority == "Mid-level"
    assert first.job_url == "https://himalayas.app/companies/h/jobs/r" and first.salary_range is None
    assert normalize_location(first.location).remote_scope == ["HK", "SG", "GB", "US"]
    assert second.location == "Worldwide Remote" and second.salary_range == "USD 50000 - 60000 per year"


# ---- stored jobs: normalisation, freshness, expiry, link check -----------------------------

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def _job(db, key: str, **kw) -> Job:
    base = dict(job_key=key, platform="Greenhouse", company="Acme", title="AR Analyst", source="greenhouse",
                job_url=f"https://example.com/jobs/{key}", is_expired=False, freshness_score=1.0)
    j = Job(**{**base, **kw})
    db.add(j)
    db.commit()
    return j


def test_normalise_facts_fills_new_columns_without_touching_raw_text(db):
    from backend.services.normalization import NORMALIZED_VERSION, normalize_facts, salary_label

    j = _job(db, "n1", location="Bangalore, Karnataka", salary_range="12-18 LPA")
    normalize_facts(j)
    assert (j.location, j.location_normalized, j.country) == ("Bangalore, Karnataka", "Bengaluru, India", "IN")
    assert (j.salary_currency, j.salary_min, j.salary_period, j.salary_min_lpa, j.salary_max_lpa) == ("INR", 1200000, "year", 12, 18)
    assert salary_label(j) == "INR 12 L–18 L a year" and j.normalized_version == NORMALIZED_VERSION
    r = _job(db, "n2", location="Remote - USA", salary_range="$80K – $110K")
    normalize_facts(r)
    assert (r.work_mode, r.remote_scope, r.salary_currency, r.salary_min_lpa) == ("Remote", ["US"], "USD", None)


def test_backfill_job_normalises_old_rows_once(db, monkeypatch):
    from backend.services import jobs_registry

    _job(db, "b1", location="hyderabad", description="x")
    _job(db, "b2", location="Remote - Canada")
    first = jobs_registry._normalise_and_dedupe(db, None)
    assert first["normalised"] == 2
    assert jobs_registry._normalise_and_dedupe(db, None)["normalised"] == 0  # version-stamped: no repeat work


def test_freshness_says_how_a_job_was_confirmed(db):
    from backend.services.freshness import status

    now = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    today = date(2026, 11, 16)
    j = _job(db, "f1", last_verified_at=now - timedelta(hours=2))
    assert status(j, now, today)["state"] == "open" and "Greenhouse board" in status(j, now, today)["detail"]
    j.last_verified_at = now - timedelta(days=6)
    assert status(j, now, today)["state"] == "unconfirmed"
    j.expires_at = today - timedelta(days=1)
    assert status(j, now, today)["state"] == "expired" and "closing date" in status(j, now, today)["detail"]
    j.closed_at, j.link_status = now, "gone"
    assert status(j, now, today) | {"checked_at": None} == {"state": "closed", "label": "No longer listed",
                                                            "detail": 'Closed: its page returned "not found" on 16 Nov 2026.', "checked_at": None}
    clip = _job(db, "f2", source="browser_clipper", platform="LinkedIn", job_url="https://www.linkedin.com/jobs/view/1/")
    assert status(clip, now, today)["label"] == "Check on the site"


def test_old_jobs_still_listed_on_the_board_are_not_expired(db):
    from backend.services.discovery_service import reap_expired_jobs

    old = date.today() - timedelta(days=80)
    listed = _job(db, "r1", posted_at=old, last_verified_at=utcnow())
    unlisted = _job(db, "r2", posted_at=old, last_verified_at=utcnow() - timedelta(days=10))
    past_close = _job(db, "r3", posted_at=date.today(), expires_at=date.today() - timedelta(days=1), last_verified_at=utcnow())
    assert reap_expired_jobs(db) == 2
    assert (listed.is_expired, unlisted.is_expired, past_close.is_expired) == (False, True, True)
    assert unlisted.closed_at is None  # expired is not "closed"


def test_link_check_classifies_conservatively():
    from backend.services.link_check import classify

    assert classify(404, "") == "gone" and classify(410, "") == "gone"
    assert classify(200, "<title>Job not found</title><body>…</body>") == "gone"
    assert classify(200, "<html><head><title>AR Analyst</title></head><body><h1>AR Analyst</h1><p>Apply now</p></body></html>") == "ok"
    # Template strings inside scripts never close an open job.
    assert classify(200, "<title>AR Analyst</title><script>var t='This job is no longer available'</script><p>Apply</p>") == "ok"
    assert classify(403, "") == "unreachable" and classify(None, "") == "unreachable" and classify(503, "") == "unreachable"


def test_link_check_skips_board_jobs_and_sites_that_forbid_automation(db):
    from backend.services import link_check

    feed = _job(db, "l1", source="himalayas", job_url="https://himalayas.app/companies/a/jobs/ar")
    gone = _job(db, "l2", source="user_job_url", job_url="https://careers.example.org/jobs/2")
    _job(db, "l3", source="browser_clipper", job_url="https://www.linkedin.com/jobs/view/3/")
    _job(db, "l4", source="browser_clipper", job_url="https://www.naukri.com/job-listings-4")
    _job(db, "l5", source="greenhouse", job_url="https://job-boards.greenhouse.io/acme/jobs/5")  # boards confirm these
    visited: list[str] = []

    def fake_fetch(url):
        visited.append(url)
        return (404, "") if "careers.example.org" in url else (200, "<title>AR Analyst</title><p>Apply</p>")

    out = link_check.check(db, fetch=fake_fetch)
    assert sorted(visited) == sorted([feed.job_url, gone.job_url])
    assert out == {"checked": 2, "ok": 1, "gone": 1, "unreachable": 0, "skipped": 0}
    assert gone.closed_at is not None and gone.link_status == "gone" and feed.closed_at is None and feed.link_status == "ok"
    assert link_check.check(db, fetch=fake_fetch)["checked"] == 0  # each job at most once every few days


# ---- matching ---------------------------------------------------------------------------------

def _matcher(countries):
    from core.settings import SearchConfig
    from intelligence.job_matcher import JobMatcher

    m = object.__new__(JobMatcher)
    m.search = SearchConfig.model_construct(locations=["Bengaluru", "Remote"], work_modes=["Remote", "Hybrid", "On-site"])
    m.work_countries, m.willing_to_relocate = countries, None
    return m


def test_remote_roles_closed_to_the_candidates_country_score_low():
    posting = lambda loc: SimpleNamespace(location=loc, work_mode="Remote")  # noqa: E731
    m = _matcher(["IN"])
    us_only, why = m.location_fit(posting("Remote - USA"))
    assert us_only == 10.0 and "only for candidates in United States" in why
    assert m.location_fit(posting("Remote - India"))[0] == 100.0
    assert m.location_fit(posting("Worldwide Remote"))[0] == 100.0
    unstated, why = m.location_fit(posting("Remote"))
    assert unstated == 85.0 and "doesn't say" in why
    assert _matcher([]).location_fit(posting("Remote - USA"))[0] == 100.0  # no stated authorisation: not judged


def test_salary_dimension_uses_normalised_pay_and_refuses_currency_guesses():
    from backend.services import scoring_v2

    prefs = SimpleNamespace(salary_min=1_000_000, currency="INR")
    usd = SimpleNamespace(salary_currency="USD", salary_min=80000, salary_max=110000, salary_period="year", salary_period_assumed=True,
                          salary_min_lpa=None, salary_max_lpa=None)
    score, why = scoring_v2._salary(usd, prefs)
    assert score is None and "does not convert" in why
    inr = SimpleNamespace(salary_currency="INR", salary_min=1_200_000, salary_max=1_800_000, salary_period="year",
                          salary_period_assumed=False, salary_min_lpa=12, salary_max_lpa=18)
    assert scoring_v2._salary(inr, prefs)[0] == 100.0
    legacy = SimpleNamespace(salary_min_lpa=6, salary_max_lpa=8)  # stored before normalisation: LPA columns still work
    assert scoring_v2._salary(legacy, prefs)[0] < 100


def test_explanation_groups_every_dimension():
    from backend.services.scoring_v2 import explain

    comps = [
        {"name": "required_skills", "label": "Required skills", "status": "known", "score": 90.0, "base_weight": 30, "evidence": "4 of 5"},
        {"name": "experience", "label": "Experience", "status": "known", "score": 60.0, "base_weight": 20, "evidence": "1 year short"},
        {"name": "location_work_mode", "label": "Location", "status": "known", "score": 10.0, "base_weight": 10, "evidence": "US only"},
        {"name": "salary", "label": "Salary", "status": "unknown", "score": None, "base_weight": 5, "evidence": "not stated"},
    ]
    match = SimpleNamespace(matching_skills=["SQL"], missing_skills=["SAP"], missing_optional_skills=[])
    e = explain(comps, match)
    assert [i["name"] for i in e["matched"]] == ["required_skills"] and [i["name"] for i in e["partial"]] == ["experience"]
    assert [i["name"] for i in e["not_matched"]] == ["location_work_mode"] and [i["name"] for i in e["not_evaluated"]] == ["salary"]
    assert e["summary"] == "1 of 3 checks match, 1 partly, 1 don't. 1 couldn't be checked, so they don't count either way."
    assert e["skills"] == {"matched": ["SQL"], "missing": ["SAP"], "missing_optional": []}


def test_new_synonyms_are_recognised():
    from pathlib import Path

    from core.skills import SkillTaxonomy

    tax = SkillTaxonomy.from_file(Path(__file__).resolve().parents[2] / "config" / "skills_taxonomy.yaml")
    found = set(tax.skills_in("Own O2C, cut DSO, review the ageing report, SAP S/4HANA, credit control, intercompany reconciliation"))
    assert {"Order to Cash", "DSO Reduction", "Aging Analysis", "SAP", "Credit Control", "Intercompany Accounting"} <= found
