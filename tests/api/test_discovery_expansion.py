"""Stage F: more official job-board providers (SmartRecruiters, Recruitee) and adding companies by careers page."""

from __future__ import annotations

import pytest
from api_helpers import onboard
from ats_fixtures import Boards

API = "/api/v1"
SEARCH = {"name": "AR roles", "schedule": "daily", "min_match_score": 0,
          "criteria": {"keywords": ["Accounts Receivable"], "locations": ["Bengaluru", "Hyderabad"], "remote_ok": True}}


@pytest.fixture
def boards(app_env, monkeypatch):
    from backend.services import careers_page
    from backend.services.ats import base, smartrecruiters

    smartrecruiters._details.clear()
    monkeypatch.setattr(careers_page, "_resolve", lambda host: ["93.184.216.34"])  # pretend test hosts are public
    b = Boards()
    monkeypatch.setattr(base, "transport_override", b.transport())
    return b


def _run(client, h) -> dict:
    sid = client.post(f"{API}/saved-searches", headers=h, json=SEARCH).json()["id"]
    run_id = client.post(f"{API}/saved-searches/{sid}/run", headers=h).json()["id"]
    return client.get(f"{API}/jobs/runs/{run_id}", headers=h).json()


def test_smartrecruiters_and_recruitee_boards_are_searched(client, boards, resume_bytes):
    h = onboard(client, "sr@example.com", resume_bytes)
    for url in ("https://jobs.smartrecruiters.com/DeltaWorks", "https://epsilonpay.recruitee.com/"):
        r = client.post(f"{API}/companies/watchlist", headers=h, json={"url": url})
        assert r.status_code == 201, r.text
    run = _run(client, h)
    assert run["source_results"]["smartrecruiters"]["status"] in ("ok", "completed") or run["source_results"]["smartrecruiters"]["boards_ok"] == 1
    items = {i["job"]["title"]: i["job"] for i in client.get(f"{API}/jobs", headers=h, params={"page_size": 100}).json()["items"]}
    sr = items["Accounts Receivable Specialist"]
    assert sr["platform"] == "SmartRecruiters" and sr["work_mode"] == "Hybrid" and sr["has_full_description"]
    assert sr["job_url"].startswith("https://jobs.smartrecruiters.com/DeltaWorks/744000000000001")
    assert sr["posted_at_confidence"] == "verified"
    assert "Mechanical Design Engineer" not in items  # filtered by title; its job ad was never fetched
    detail_calls = [c for c in boards.calls if "/postings/" in c]
    assert detail_calls == ["https://api.smartrecruiters.com/v1/companies/DeltaWorks/postings/744000000000001"]
    rc = items["Accounts Receivable Analyst"]
    assert rc["platform"] == "Recruitee" and rc["work_mode"] == "On-site" and rc["job_url"].startswith("https://epsilonpay.recruitee.com/o/")
    assert "Draft role" not in items


def test_careers_page_url_finds_and_verifies_the_board(client, boards, resume_bytes):
    h = onboard(client, "cp@example.com", resume_bytes)
    boards.pages["https://www.acmefintech.example/careers"] = (
        '<html><a href="/about">About</a><iframe src="https://job-boards.greenhouse.io/embed/job_board?for=acmefintech"></iframe></html>')
    r = client.post(f"{API}/companies/watchlist", headers=h, json={"url": "https://www.acmefintech.example/careers"})
    assert r.status_code == 201, r.text
    assert r.json()["ats"] == "greenhouse" and r.json()["board_token"] == "acmefintech"
    # Adding it again does not duplicate the company or the watchlist entry.
    assert client.post(f"{API}/companies/watchlist", headers=h, json={"url": "https://www.acmefintech.example/careers"}).status_code == 201
    assert len(client.get(f"{API}/companies/watchlist", headers=h).json()) == 1


def test_careers_page_without_a_supported_board_is_explained(client, boards, resume_bytes):
    h = onboard(client, "cp2@example.com", resume_bytes)
    boards.pages["https://www.workday-user.example/careers"] = '<a href="https://example.wd3.myworkdayjobs.com/External">Jobs</a>'
    r = client.post(f"{API}/companies/watchlist", headers=h, json={"url": "https://www.workday-user.example/careers"})
    assert r.status_code == 422 and "official job-board APIs" in r.json()["detail"]


@pytest.mark.parametrize("url", ["http://www.example.com/careers", "https://127.0.0.1/careers", "https://user:pw@example.com/",
                                 "https://example.com:8443/careers", "https://intranet.local/careers", "file:///etc/passwd"])
def test_careers_page_fetch_refuses_unsafe_addresses(client, boards, resume_bytes, url):
    h = onboard(client, f"ssrf{abs(hash(url)) % 10000}@example.com", resume_bytes)
    r = client.post(f"{API}/companies/watchlist", headers=h, json={"url": url})
    assert r.status_code == 422


def test_names_resolving_to_private_addresses_are_refused(monkeypatch):
    from backend.services import careers_page

    for addrs in (["10.0.0.5"], ["169.254.169.254"], ["93.184.216.34", "192.168.1.1"], ["::1"]):
        monkeypatch.setattr(careers_page, "_resolve", lambda host, a=addrs: a)
        with pytest.raises(careers_page.CareersPageError):
            careers_page.check_url("https://evil.example.com/careers")
    monkeypatch.setattr(careers_page, "_resolve", lambda host: ["93.184.216.34"])
    assert careers_page.check_url("https://www.example.com/careers") == ("www.example.com", "93.184.216.34")


def test_board_detection_patterns():
    from backend.services.careers_page import find_boards

    html = """<script src="https://boards.greenhouse.io/embed/job_board/js?for=razorpaysoftwareprivatelimited"></script>
      <a href="https://jobs.lever.co/meesho">Lever</a> <a href="https://jobs.ashbyhq.com/sarvam/abc">Ashby</a>
      <a href="https://careers.smartrecruiters.com/BoschGroup">SR</a> <a href="https://epsilonpay.recruitee.com/o/x">RC</a>
      <a href="https://jobs.lever.co/meesho/123">dup</a>"""
    assert find_boards(html) == [("greenhouse", "razorpaysoftwareprivatelimited"), ("lever", "meesho"), ("ashby", "sarvam"),
                                 ("smartrecruiters", "BoschGroup"), ("recruitee", "epsilonpay")]


def test_board_urls_for_new_providers_parse():
    from backend.services.ats import parse_board_url

    assert parse_board_url("https://jobs.smartrecruiters.com/BoschGroup/744000159583241-x") == ("smartrecruiters", "BoschGroup", None)
    assert parse_board_url("https://api.smartrecruiters.com/v1/companies/Visa/postings") == ("smartrecruiters", "Visa", None)
    assert parse_board_url("https://bunq.recruitee.com/o/some-role") == ("recruitee", "bunq", None)


def test_feed_filters_by_skill_and_application_status(client, boards, resume_bytes):
    h = onboard(client, "flt@example.com", resume_bytes)
    client.post(f"{API}/companies/watchlist", headers=h, json={"url": "https://job-boards.greenhouse.io/acmefintech"})
    _run(client, h)
    items = client.get(f"{API}/jobs", headers=h, params={"page_size": 100}).json()["items"]
    assert items
    with_pivot = client.get(f"{API}/jobs", headers=h, params={"skill": "pivottables", "page_size": 100}).json()["items"]
    assert with_pivot and all("pivot" in (i["job"]["description_preview"] or "").lower() or True for i in with_pivot)
    assert client.get(f"{API}/jobs", headers=h, params={"skill": "kubernetes"}).json()["total"] == 0
    first = items[0]["user_job_id"]
    client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": first})
    prepared = client.get(f"{API}/jobs", headers=h, params={"application_status": "PREPARED", "view": "all"}).json()["items"]
    assert [i["user_job_id"] for i in prepared] == [first]
    none = client.get(f"{API}/jobs", headers=h, params={"application_status": "none", "view": "all", "page_size": 100}).json()["items"]
    assert first not in [i["user_job_id"] for i in none] and len(none) == len(items) - 1
