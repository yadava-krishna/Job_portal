"""Pagination of the job feed, the way the web app pages it (24 per page): nothing skipped, nothing repeated, accurate
totals, stable order across pages for every sort, filters paging consistently, and empty pages past the end."""

from __future__ import annotations

import math

import pytest
from api_helpers import import_job, onboard

API = "/api/v1"
PAGE = 24          # what the web app asks for
N_JOBS = 49        # full-time roles
N_INTERN = 12      # internships, listed separately under kind=internships


@pytest.fixture
def feed(client, resume_bytes):
    h = onboard(client, "pages@example.com", resume_bytes)
    for i in range(N_JOBS):
        # Distinct companies, so "one listing per role" grouping never merges two of them.
        import_job(client, h, url=f"https://www.linkedin.com/jobs/view/41{i:08d}/", company=f"Company {i:02d}",
                   title="Accounts Receivable Analyst" if i % 2 else "Accounts Receivable Specialist",
                   posted_date=f"{(i % 9) + 1} days ago")
    for i in range(N_INTERN):
        import_job(client, h, url=f"https://www.linkedin.com/jobs/view/42{i:08d}/", company=f"Intern Co {i:02d}",
                   title="Finance Intern", employment_type="Internship", posted_date="today")
    return h


def _page(client, h, page: int, **params) -> dict:
    r = client.get(f"{API}/jobs", headers=h, params={"view": "feed", "page": page, "page_size": PAGE, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _walk(client, h, **params) -> tuple[list[int], int]:
    """Every id across all pages, in order, plus the total the API reported."""
    first = _page(client, h, 1, **params)
    total = first["total"]
    pages = max(1, math.ceil(total / PAGE))
    ids = [i["user_job_id"] for i in first["items"]]
    for p in range(2, pages + 1):
        body = _page(client, h, p, **params)
        assert body["total"] == total, "the total must not change between pages"
        ids += [i["user_job_id"] for i in body["items"]]
    return ids, total


@pytest.mark.parametrize("sort", ["score", "posted", "discovered"])
def test_every_job_appears_exactly_once_across_pages(client, feed, sort):
    ids, total = _walk(client, feed, kind="all", sort=sort)
    assert total == N_JOBS + N_INTERN
    assert len(ids) == total, "pages together must hold every job"
    assert len(set(ids)) == len(ids), "no job may appear on two pages"
    # The same order as one big page: paging never reshuffles.
    one = client.get(f"{API}/jobs", headers=feed, params={"view": "feed", "kind": "all", "sort": sort, "page_size": 100}).json()
    assert ids == [i["user_job_id"] for i in one["items"]]


def test_page_sizes_last_page_and_past_the_end(client, feed):
    total = N_JOBS + N_INTERN                      # 61 → pages of 24, 24, 13
    p1, p3, p4 = (_page(client, feed, p, kind="all") for p in (1, 3, 4))
    assert len(p1["items"]) == PAGE and p1["page"] == 1 and p1["page_size"] == PAGE
    assert len(p3["items"]) == total - 2 * PAGE
    assert p4["items"] == [] and p4["total"] == total, "a page past the end is empty, with the true total"


def test_jobs_and_internships_page_separately_and_add_up(client, feed):
    jobs, jobs_total = _walk(client, feed, kind="jobs")
    interns, interns_total = _walk(client, feed, kind="internships")
    assert (jobs_total, interns_total) == (N_JOBS, N_INTERN)
    assert not set(jobs) & set(interns)
    everything, _ = _walk(client, feed, kind="all")
    assert set(jobs) | set(interns) == set(everything)


def test_a_search_pages_consistently_and_starts_from_its_own_first_page(client, feed):
    ids, total = _walk(client, feed, kind="all", q="Specialist")
    assert total == math.ceil(N_JOBS / 2) and len(ids) == total and len(set(ids)) == total
    titles = {i["job"]["title"] for p in range(1, math.ceil(total / PAGE) + 1) for i in _page(client, feed, p, kind="all", q="Specialist")["items"]}
    assert titles == {"Accounts Receivable Specialist"}


def test_page_size_is_bounded(client, feed):
    assert client.get(f"{API}/jobs", headers=feed, params={"page_size": 101}).status_code == 422
    assert client.get(f"{API}/jobs", headers=feed, params={"page": 0}).status_code == 422
