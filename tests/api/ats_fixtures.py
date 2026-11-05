"""Synthetic job-board payloads with the same shape as the official Greenhouse, Lever and Ashby APIs.

Field names and value formats mirror live responses checked on 2026-11-04 (Greenhouse: entity-escaped HTML
`content`, `first_published` with an offset; Lever: `createdAt` in epoch ms, `categories`, `lists`; Ashby:
`isListed`, `publishedAt`, `secondaryLocations`). Companies and texts are fictitious.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

import httpx

AR_HTML = """<div class="content-intro"><p>Acme Fintech builds payments software.</p></div>
<h3>Responsibilities</h3><ul><li>Perform payment posting using remittance information</li>
<li>Follow up on unpaid claims with insurance companies</li><li>Prepare Excel reports using PivotTables for management</li></ul>
<h3>Requirements</h3><ul><li>3-6 years of experience in accounts receivable</li><li>Bachelor&#39;s degree in Commerce</li></ul>
<p>Good to have: Power BI. Full time role.</p><script>alert('never rendered')</script>"""

AR_PLAIN = ("Responsibilities\nPerform payment posting using remittance information\nFollow up on unpaid claims with insurance "
            "companies\nPrepare Excel reports using PivotTables for management\nRequirements\n3-6 years of experience in accounts "
            "receivable\nBachelor's degree in Commerce\nGood to have: Power BI.")


def iso(days_ago: int, offset_hours: int = -4) -> str:
    tz = timezone(timedelta(hours=offset_hours))
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).astimezone(tz).replace(microsecond=0).isoformat()


def epoch_ms(days_ago: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days_ago)).timestamp() * 1000)


def greenhouse_board(*, include_101: bool = True) -> dict:
    jobs = [
        {"id": 101, "title": "Accounts Receivable Analyst", "updated_at": iso(0), "first_published": iso(1),
         "absolute_url": "https://job-boards.greenhouse.io/acmefintech/jobs/101", "company_name": "Acme Fintech Private Limited",
         "location": {"name": "Bengaluru"}, "departments": [{"id": 1, "name": "Finance"}], "offices": [], "metadata": [],
         "content": html.escape(AR_HTML)},
        {"id": 102, "title": "Senior Software Engineer", "updated_at": iso(0), "first_published": iso(2),
         "absolute_url": "https://job-boards.greenhouse.io/acmefintech/jobs/102", "company_name": "Acme Fintech Private Limited",
         "location": {"name": "Bengaluru"}, "departments": [], "content": html.escape("<p>Build APIs in Go.</p>")},
        # Same title, different city, and no first_published: the posting date must stay unknown (updated_at is today!).
        {"id": 103, "title": "Accounts Receivable Analyst", "updated_at": iso(0),
         "absolute_url": "https://job-boards.greenhouse.io/acmefintech/jobs/103", "company_name": "Acme Fintech Private Limited",
         "location": {"name": "Mumbai"}, "departments": [{"id": 1, "name": "Finance"}], "content": html.escape(AR_HTML)},
        {"id": 104, "title": "Accounts Receivable Specialist", "updated_at": iso(0), "first_published": iso(3),
         "absolute_url": "https://job-boards.greenhouse.io/acmefintech/jobs/104", "company_name": "Acme Fintech Private Limited",
         "location": {"name": "Remote - US"}, "content": html.escape(AR_HTML)},
    ]
    if not include_101:
        jobs = jobs[1:]
    return {"jobs": jobs, "meta": {"total": len(jobs)}}


def lever_board() -> list:
    return [
        {"id": "aaaa-1111", "text": "Accounts Receivable Analyst", "createdAt": epoch_ms(4),
         "hostedUrl": "https://jobs.lever.co/betapay/aaaa-1111", "applyUrl": "https://jobs.lever.co/betapay/aaaa-1111/apply",
         "workplaceType": "hybrid", "country": "IN",
         "categories": {"commitment": "Full Time Employee", "department": "Finance", "location": "Bangalore, Karnataka",
                        "team": "Collections", "allLocations": ["Bangalore, Karnataka"]},
         "descriptionPlain": "Beta Pay is hiring.", "description": "<div>Beta Pay is hiring.</div>",
         "lists": [{"text": "What you will do", "content": "<li>Perform payment posting using remittance information</li>"
                                                            "<li>Follow up on unpaid claims with insurance companies</li>"},
                   {"text": "What you will need", "content": "<li>3-6 years of experience in accounts receivable</li>"
                                                             "<li>Excel reports using PivotTables</li>"}],
         "additionalPlain": "Bachelor's degree in Commerce.",
         "salaryRange": {"min": 600000, "max": 900000, "currency": "INR", "interval": "per-year-salary"}},
        {"id": "bbbb-2222", "text": "Accounts Receivable Executive", "createdAt": epoch_ms(10),
         "hostedUrl": "https://jobs.lever.co/betapay/bbbb-2222", "workplaceType": "remote",
         "categories": {"commitment": "Contract", "location": "Remote - India", "allLocations": ["Remote - India"]},
         "descriptionPlain": AR_PLAIN, "lists": []},
    ]


def ashby_board() -> dict:
    return {"apiVersion": "1", "jobs": [
        {"id": "u-1", "title": "Accounts Receivable Analyst", "isListed": False, "location": "Bengaluru",
         "publishedAt": iso(1, 0), "jobUrl": "https://jobs.ashbyhq.com/gammaco/u-1", "descriptionPlain": AR_PLAIN},
        {"id": "g-2", "title": "Accounts Receivable Analyst - Collections", "isListed": True, "location": "Hyderabad",
         "secondaryLocations": [{"location": "Pune", "address": {"postalAddress": {"addressCountry": "IN"}}}],
         "department": "Finance", "team": "AR", "isRemote": False, "workplaceType": "OnSite", "employmentType": "FullTime",
         "publishedAt": iso(2, 0), "jobUrl": "https://jobs.ashbyhq.com/gammaco/g-2",
         "applyUrl": "https://jobs.ashbyhq.com/gammaco/g-2/application", "descriptionPlain": AR_PLAIN,
         "descriptionHtml": "<p>ignored when plain text exists</p>", "shouldDisplayCompensationOnJobPostings": True,
         "compensation": {"compensationTierSummary": "₹8L – ₹12L", "scrapeableCompensationSalarySummary": None}},
    ]}


def smartrecruiters_list() -> dict:
    return {"offset": 0, "limit": 100, "totalFound": 2, "content": [
        {"id": "744000000000001", "name": "Accounts Receivable Specialist", "releasedDate": iso(1, 0),
         "location": {"city": "Bengaluru", "region": "KA", "country": "in", "remote": False, "hybrid": True, "fullLocation": "Bengaluru, KA, India"},
         "typeOfEmployment": {"id": "permanent", "label": "Full-time"}, "company": {"identifier": "DeltaWorks", "name": "Delta Works"},
         "department": {"label": "Finance"}},
        {"id": "744000000000002", "name": "Mechanical Design Engineer", "releasedDate": iso(2, 0),
         "location": {"city": "Pune", "country": "in", "remote": False, "fullLocation": "Pune, MH, India"},
         "typeOfEmployment": {"label": "Full-time"}, "company": {"name": "Delta Works"}},
    ]}


def smartrecruiters_detail(pid: str) -> dict:
    return {"id": pid, "postingUrl": f"https://jobs.smartrecruiters.com/DeltaWorks/{pid}-accounts-receivable-specialist",
            "jobAd": {"sections": {"jobDescription": {"text": AR_HTML}, "qualifications": {"text": "<ul><li>3-6 years of experience in accounts receivable</li></ul>"}}}}


def recruitee_offers() -> dict:
    return {"offers": [
        {"id": 901, "title": "Accounts Receivable Analyst", "status": "published", "location": "Hyderabad, Telangana, India", "remote": False,
         "hybrid": False, "on_site": True, "employment_type_code": "fulltime_permanent", "description": AR_HTML, "requirements": "<p>Excel</p>",
         "published_at": "2026-11-04 08:00:00 UTC".replace("2026-11-04", (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")),
         "careers_url": "https://epsilonpay.recruitee.com/o/accounts-receivable-analyst", "department": "Finance", "company_name": "Epsilon Pay"},
        {"id": 902, "title": "Draft role", "status": "draft"},
    ]}


class Boards:
    """A MockTransport standing in for the three official APIs. Mutate `.payloads` between runs to change a board."""

    def __init__(self) -> None:
        self.payloads: dict[tuple[str, str], object] = {
            ("greenhouse", "acmefintech"): greenhouse_board(),
            ("lever", "betapay"): lever_board(),
            ("ashby", "gammaco"): ashby_board(),
            ("smartrecruiters", "DeltaWorks"): smartrecruiters_list(),
            ("recruitee", "epsilonpay"): recruitee_offers(),
        }
        self.pages: dict[str, str] = {}  # careers pages: url -> html
        self.calls: list[str] = []
        self.status: dict[tuple[str, str], int] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(str(request.url))
        host, parts = request.url.host, [p for p in request.url.path.split("/") if p]
        if host == "boards-api.greenhouse.io":
            key = ("greenhouse", parts[2])
        elif host in ("api.lever.co", "api.eu.lever.co"):
            key = ("lever", parts[2])
        elif host == "api.ashbyhq.com":
            key = ("ashby", parts[2])
        elif host == "api.smartrecruiters.com":
            if len(parts) >= 5 and key_known(self, ("smartrecruiters", parts[2])):
                return httpx.Response(200, json=smartrecruiters_detail(parts[4]))
            key = ("smartrecruiters", parts[2])
            if key not in self.payloads:  # SmartRecruiters answers 200 with nothing for unknown companies
                return httpx.Response(200, json={"offset": 0, "limit": 100, "totalFound": 0, "content": []})
        elif host.endswith(".recruitee.com"):
            key = ("recruitee", host.split(".")[0])
        elif str(request.url).split("?")[0] in self.pages:
            return httpx.Response(200, text=self.pages[str(request.url).split("?")[0]], headers={"content-type": "text/html"})
        else:
            return httpx.Response(599)
        if key in self.status:
            return httpx.Response(self.status[key], text="error")
        if key not in self.payloads:
            return httpx.Response(404, text="Not Found")
        return httpx.Response(200, json=self.payloads[key])

    def transport(self) -> httpx.MockTransport:  # noqa: D102
        return httpx.MockTransport(self.handler)


def key_known(boards: "Boards", key: tuple[str, str]) -> bool:
    return key in boards.payloads
