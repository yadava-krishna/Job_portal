"""Tests for all multi-source connectors with fixture data and mock fetchers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from backend.services.connectors import registry
from backend.services.connectors.career_url_connector import CareerUrlConnector
from backend.services.connectors.jsonld_connector import extract_jsonld_from_html
from backend.services.connectors.rss_connector import parse_feed_xml
from backend.services.connectors.sitemap_connector import parse_sitemap_urls
from backend.services.scrapling_client import ScraplingResponse


SAMPLE_JSONLD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <script type="application/ld+json">
  {
    "@context": "https://schema.org/",
    "@type": "JobPosting",
    "title": "Staff Backend Engineer",
    "description": "<p>We are seeking a Staff Backend Engineer with Python and distributed systems experience.</p>",
    "datePosted": "2026-11-01",
    "employmentType": "FULL_TIME",
    "hiringOrganization": {
      "@type": "Organization",
      "name": "Stripe"
    },
    "jobLocation": {
      "@type": "Place",
      "address": {
        "@type": "PostalAddress",
        "addressLocality": "Bengaluru",
        "addressCountry": "IN"
      }
    },
    "baseSalary": {
      "@type": "MonetaryAmount",
      "currency": "INR",
      "value": {
        "@type": "QuantitativeValue",
        "minValue": 4500000,
        "maxValue": 6500000,
        "unitText": "YEAR"
      }
    },
    "url": "https://stripe.com/jobs/staff-backend-101"
  }
  </script>
</head>
<body><h1>Careers</h1></body>
</html>
"""

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Tech Remote Openings</title>
    <link>https://example.com/rss</link>
    <item>
      <title>Full Stack React Engineer</title>
      <link>https://example.com/jobs/react-101</link>
      <description>Join our remote-first team building web applications.</description>
      <pubDate>Mon, 03 Nov 2026 10:00:00 GMT</pubDate>
      <author>talent@example.com (Alpha Corp)</author>
    </item>
  </channel>
</rss>
"""

SAMPLE_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://example.com/about</loc>
  </url>
  <url>
    <loc>https://example.com/careers/senior-python-dev</loc>
  </url>
</urlset>
"""


def test_jsonld_extraction():
    jobs = extract_jsonld_from_html(SAMPLE_JSONLD_HTML, "https://stripe.com/jobs")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Staff Backend Engineer"
    assert job.company == "Stripe"
    assert "Bengaluru" in (job.location or "")
    assert job.employment_type == "Full-time"
    assert job.salary_min_lpa == 45.0
    assert job.salary_max_lpa == 65.0
    assert job.posted_at_source == "platform_page"
    assert job.extraction_method == "json_ld"


def test_rss_feed_parsing():
    jobs = parse_feed_xml(SAMPLE_RSS_XML, "https://example.com/rss.xml")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Full Stack React Engineer"
    assert job.company == "Alpha Corp"
    assert job.job_url == "https://example.com/jobs/react-101"
    assert job.posted_at is not None
    assert job.extraction_method == "rss_feed"


def test_sitemap_url_parsing():
    subs, urls = parse_sitemap_urls(SAMPLE_SITEMAP_XML, "https://example.com/sitemap.xml")
    assert len(subs) == 0
    assert len(urls) == 2
    assert "https://example.com/careers/senior-python-dev" in urls


def test_remotive_connector_parsing(monkeypatch):
    from backend.services.connectors.remotive_connector import RemotiveConnector

    mock_resp = ScraplingResponse(
        url="https://remotive.com/api/remote-jobs",
        status=200,
        text=json.dumps({
            "jobs": [{
                "id": 9991,
                "url": "https://remotive.com/job/9991",
                "title": "Principal Architect",
                "company_name": "Acme Global",
                "candidate_required_location": "Worldwide",
                "salary": "$180,000 - $220,000",
                "description": "<p>Deep distributed systems knowledge required.</p>",
                "publication_date": "2026-11-02T12:00:00",
                "job_type": "full_time",
                "tags": ["Python", "Kubernetes"],
            }]
        }),
    )

    connector = RemotiveConnector()
    monkeypatch.setattr(connector.client, "fetch_page", lambda *a, **kw: mock_resp)
    jobs = connector.discover()

    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Principal Architect"
    assert j.company == "Acme Global"
    assert j.work_mode == "Remote"
    assert j.source == "remotive"
    assert "Python" in j.required_skills


def test_career_url_connector_ats_detection(monkeypatch):
    """Verify that career_url_connector detects ATS embed from careers page HTML."""
    html_with_greenhouse = """
    <html>
      <body>
        <h1>Work with us</h1>
        <script src="https://boards.greenhouse.io/embed/job_board/js?for=razorpay"></script>
      </body>
    </html>
    """
    mock_resp = ScraplingResponse(url="https://razorpay.com/careers", status=200, text=html_with_greenhouse)
    conn = CareerUrlConnector()
    monkeypatch.setattr(conn.client, "fetch_page", lambda *a, **kw: mock_resp)

    # Mock official board fetcher
    from backend.services.ats.base import BoardResult
    from backend.services.normalization import NormalizedJob
    dummy_job = NormalizedJob(
        source="greenhouse",
        source_key="greenhouse:razorpay:1",
        platform="Greenhouse",
        company="Razorpay",
        title="Software Engineer",
        job_url="https://boards.greenhouse.io/razorpay/jobs/1",
        description="Engineering role at Razorpay.",
    )
    monkeypatch.setattr("backend.services.ats.base.fetch_board", lambda ats, token, **kw: BoardResult(ats=ats, token=token, company_name="Razorpay", jobs=[dummy_job]))

    res = conn.analyze_career_url("https://razorpay.com/careers", company_hint="Razorpay")
    assert res.detected_ats == "greenhouse"
    assert res.ats_token == "razorpay"
    assert len(res.jobs) == 1
    assert res.jobs[0].title == "Software Engineer"
