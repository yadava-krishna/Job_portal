"""Official job-board clients against mocked feeds, and the normalisation helpers."""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
from ats_fixtures import Boards, greenhouse_board

from backend.services import normalization as n
from backend.services.ats import AtsError, base, board_cache, fetch_board, parse_board_url


@pytest.fixture
def boards(app_env, monkeypatch):
    b = Boards()
    monkeypatch.setattr(base, "transport_override", b.transport())
    return b


# ---- clients ----------------------------------------------------------------------------------------

def test_greenhouse_parses_full_description_and_verified_date(boards):
    from core import timeutil

    r = fetch_board("greenhouse", "acmefintech", company_name="Acme Fintech")
    assert [j.external_job_id for j in r.jobs] == ["101", "102", "103", "104"]
    j = r.jobs[0]
    assert (j.source, j.platform, j.company, j.title, j.location) == ("greenhouse", "Greenhouse", "Acme Fintech", "Accounts Receivable Analyst", "Bengaluru")
    assert j.source_key == "greenhouse:acmefintech:101" and j.department == "Finance"
    assert j.job_url == "https://job-boards.greenhouse.io/acmefintech/jobs/101"
    assert j.posted_at == timeutil.today() - timedelta(days=1) and j.posted_at_source == "platform_api"
    assert "Perform payment posting" in j.description and "<" not in j.description and "alert(" not in j.description
    assert "content=true" in boards.calls[0]


def test_greenhouse_updated_at_is_never_a_posting_date(boards):
    j = {x.external_job_id: x for x in fetch_board("greenhouse", "acmefintech").jobs}["103"]
    assert j.posted_at is None and j.posted_at_source is None


def test_greenhouse_falls_back_to_api_company_name(boards):
    assert fetch_board("greenhouse", "acmefintech").jobs[0].company == "Acme Fintech Private Limited"


def test_lever_fields_salary_and_epoch_dates(boards):
    from core import timeutil

    r = fetch_board("lever", "betapay", company_name="Beta Pay")
    a, b = r.jobs
    assert (a.title, a.location, a.work_mode, a.employment_type, a.department) == (
        "Accounts Receivable Analyst", "Bangalore, Karnataka", "Hybrid", "Full-time", "Finance")
    assert a.posted_at == timeutil.today() - timedelta(days=4) and a.posted_at_source == "platform_api"
    assert (a.salary_min_lpa, a.salary_max_lpa) == (6.0, 9.0) and "INR" in a.salary_range
    assert "What you will do" in a.description and "Bachelor's degree" in a.description
    assert (b.work_mode, b.employment_type) == ("Remote", "Contract")
    assert "mode=json" in boards.calls[0]


def test_lever_eu_region_uses_eu_host(boards):
    fetch_board("lever", "betapay", region="eu")
    assert boards.calls[0].startswith("https://api.eu.lever.co/v0/postings/betapay")


def test_ashby_skips_unlisted_and_reads_locations(boards):
    r = fetch_board("ashby", "gammaco", company_name="Gamma Co")
    assert r.skipped == 1 and len(r.jobs) == 1
    j = r.jobs[0]
    assert (j.title, j.location, j.locations, j.work_mode, j.employment_type) == (
        "Accounts Receivable Analyst - Collections", "Hyderabad", ["Hyderabad", "Pune"], "On-site", "Full-time")
    assert j.salary_range == "₹8L – ₹12L" and j.posted_at_source == "platform_api"
    assert "includeCompensation=true" in boards.calls[0]


@pytest.mark.parametrize("status, kind", [(404, "not_found"), (500, "transient"), (503, "transient"), (429, "transient"), (403, "invalid")])
def test_http_errors_are_classified(boards, status, kind):
    boards.status[("greenhouse", "acmefintech")] = status
    with pytest.raises(AtsError) as e:
        fetch_board("greenhouse", "acmefintech")
    assert e.value.kind == kind


def test_unknown_board_is_not_found(boards):
    with pytest.raises(AtsError) as e:
        fetch_board("lever", "no-such-board")
    assert e.value.kind == "not_found"


def test_malformed_and_unexpected_bodies(app_env, monkeypatch):
    monkeypatch.setattr(base, "transport_override", httpx.MockTransport(lambda r: httpx.Response(200, text="<html>oops</html>")))
    with pytest.raises(AtsError) as e:
        fetch_board("ashby", "x")
    assert e.value.kind == "invalid"
    monkeypatch.setattr(base, "transport_override", httpx.MockTransport(lambda r: httpx.Response(200, json={"unexpected": True})))
    for ats in ("greenhouse", "lever", "ashby"):
        with pytest.raises(AtsError):
            fetch_board(ats, "x")


def test_timeouts_and_connection_errors_are_transient(app_env, monkeypatch):
    def boom(request):
        raise httpx.ConnectTimeout("slow", request=request)

    monkeypatch.setattr(base, "transport_override", httpx.MockTransport(boom))
    with pytest.raises(AtsError) as e:
        fetch_board("greenhouse", "acmefintech")
    assert e.value.kind == "transient"


def test_response_size_cap(boards, monkeypatch):
    monkeypatch.setattr(base, "MAX_BYTES", 500)
    with pytest.raises(AtsError, match="too large"):
        fetch_board("greenhouse", "acmefintech")


def test_bad_tokens_rejected_before_any_request(boards):
    for token in ("", "../etc", "a b", "x" * 200, "acme/../../"):
        with pytest.raises(AtsError):
            fetch_board("greenhouse", token)
    assert boards.calls == []


def test_board_cache_shares_fetches_and_remembers_missing_boards(boards):
    board_cache.get("greenhouse", "acmefintech")
    board_cache.get("greenhouse", "ACMEFINTECH")
    assert len(boards.calls) == 1
    for _ in range(2):
        with pytest.raises(AtsError):
            board_cache.get("lever", "missing")
    assert len(boards.calls) == 2  # the 404 is cached, not re-requested
    boards.status[("ashby", "gammaco")] = 503
    for _ in range(2):
        with pytest.raises(AtsError):
            board_cache.get("ashby", "gammaco")
    assert len(boards.calls) == 2 + 2 * 3  # transient errors are not cached: each lookup tries again (first try + 2 retries)


@pytest.mark.parametrize("url, expected", [
    ("https://job-boards.greenhouse.io/razorpay/jobs/123", ("greenhouse", "razorpay", None)),
    ("boards.greenhouse.io/acme", ("greenhouse", "acme", None)),
    ("https://boards.greenhouse.io/embed/job_board?for=acme&b=x", ("greenhouse", "acme", None)),
    ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", ("greenhouse", "acme", None)),
    ("https://jobs.lever.co/meesho/7d9a-uuid", ("lever", "meesho", None)),
    ("https://jobs.eu.lever.co/acme", ("lever", "acme", "eu")),
    ("https://jobs.ashbyhq.com/sarvam/c040-uuid/application", ("ashby", "sarvam", None)),
])
def test_parse_board_url(url, expected):
    assert parse_board_url(url) == expected


@pytest.mark.parametrize("url", ["https://www.linkedin.com/jobs/view/1", "https://evil.example/jobs.lever.co/x", "https://jobs.lever.co/", "not a url"])
def test_parse_board_url_rejects_other_sites(url):
    with pytest.raises(AtsError):
        parse_board_url(url)


# ---- normalisation ---------------------------------------------------------------------------------

def test_html_to_text_keeps_structure_and_drops_markup():
    text = n.html_to_text("&lt;h3&gt;Role&lt;/h3&gt;&lt;ul&gt;&lt;li&gt;One &amp;amp; two&lt;/li&gt;&lt;li&gt;Three&lt;/li&gt;&lt;/ul&gt;"
                          "&lt;script&gt;x()&lt;/script&gt;&lt;p&gt;End&amp;nbsp;here&lt;/p&gt;")
    assert text == "Role\n\n- One & two\n\n- Three\n\nEnd here"
    assert "x()" not in text and "<" not in text
    assert n.html_to_text(None) == "" and n.html_to_text("plain") == "plain"


def test_canonical_url():
    assert n.canonical_url("https://www.LinkedIn.com/jobs/view/42/?trk=abc&refId=x#top") == "linkedin.com/jobs/view/42"
    assert n.canonical_url("https://in.indeed.com/viewjob?jk=abc123&from=serp") == "in.indeed.com/viewjob?jk=abc123"
    assert n.canonical_url("https://boards.greenhouse.io/acme/jobs/1?gh_jid=1&utm_source=x") == "boards.greenhouse.io/acme/jobs/1?gh_jid=1"
    assert n.canonical_url(None) is None and n.canonical_url("not a url") is None


def test_dedup_keys_fold_legal_suffixes_and_seniority():
    assert n.dedup_key("Acme Fintech Private Limited", "Sr. Accounts Receivable Analyst") == \
        n.dedup_key("ACME FINTECH PVT LTD", "Senior Accounts-Receivable Analyst") == "acme fintech|senior accounts receivable analyst"
    assert n.dedup_key("Acme", "AR Analyst (Immediate Joiners)") == "acme|ar analyst"
    assert n.dedup_key("", "Analyst") is None and n.dedup_key("Acme", "") is None


def test_locations():
    assert n.location_tokens("Bangalore, Karnataka") == {"bengaluru"}
    assert n.location_tokens("Gurgaon / New Delhi") == {"gurugram", "delhi"}
    assert "noida" in n.location_tokens("Delhi NCR")
    assert n.locations_compatible("Bengaluru", "Bangalore, KA") is True
    assert n.locations_compatible("Mumbai", "Bengaluru") is False
    assert n.locations_compatible("Remote", "Bengaluru") is None
    assert n.split_locations("Bengaluru; Pune | Remote", ["Pune", "Hyderabad"]) == ["Bengaluru", "Pune", "Remote", "Hyderabad"]
    assert n.remote_ok_for_india("Remote - India") and n.remote_ok_for_india("Remote") and n.remote_ok_for_india("Remote, APAC")
    assert not n.remote_ok_for_india("Remote - US") and not n.remote_ok_for_india("San Francisco, CA")


@pytest.mark.parametrize("value, expected", [("FullTime", "Full-time"), ("Full Time Employee", "Full-time"), ("full_time", "Full-time"),
                                             ("PartTime", "Part-time"), ("Intern", "Internship"), ("Contract", "Contract"),
                                             ("Temporary", "Temporary"), ("", None), (None, None), ("Other", None)])
def test_employment_type(value, expected):
    assert n.employment_type(value) == expected


def test_work_mode():
    assert [n.work_mode(v) for v in ("onsite", "OnSite", "On-site", "hybrid", "Remote", None, "")] == \
        ["On-site", "On-site", "On-site", "Hybrid", "Remote", None, None]


def test_timestamps_become_local_calendar_dates():
    # 22:00 in New York on 3 Nov is already 4 Nov in India; "posted today" must use the user's calendar.
    assert n.local_date("2026-11-03T22:00:00-04:00") == date(2026, 11, 4)
    assert n.local_date(1762128000000) == date(2025, 11, 3)  # epoch ms (Lever)
    assert n.local_date("2026-10-29T16:56:07.691+00:00") == date(2026, 10, 29)
    assert n.local_date("garbage") is None and n.local_date(None) is None and n.local_date(True) is None


def test_posted_confidence():
    d = date(2026, 11, 1)
    assert [n.posted_confidence(d, s) for s in ("platform_api", "platform_page", "user_provided", "alert_email", "other", None)] == \
        ["verified", "verified", "verified", "estimated", "unknown", "unknown"]
    assert n.posted_confidence(None, "platform_api") == "unknown"


def test_enrich_fills_gaps_from_description(app_env):
    from backend.config import get_settings
    from backend.services import resume_service
    from intelligence.jd_analyzer import JDAnalyzer

    j = n.NormalizedJob(source="greenhouse", source_key="k", platform="Greenhouse", company="A", title="AR Analyst",
                        description=n.html_to_text(greenhouse_board()["jobs"][0]["content"]))
    n.enrich(j, JDAnalyzer(resume_service.taxonomy(get_settings())))
    assert (j.experience_min, j.experience_max) == (3, 6)
    assert any("receivable" in s.lower() for s in j.required_skills)
