"""Unit tests for the ATS Detector service."""

from __future__ import annotations

import pytest

from backend.services.ats_detector import detect_from_html, detect_from_url, detect_career_url
from backend.services.scrapling_client import mock_fetch_handler, ScraplingResponse


def test_detect_from_url_greenhouse():
    res = detect_from_url("https://boards.greenhouse.io/stripe")
    assert res is not None
    assert res["ats_platform"] == "greenhouse"
    assert res["board_token"] == "stripe"
    assert "stripe" in res["api_endpoint"]


def test_detect_from_url_lever():
    res = detect_from_url("https://jobs.lever.co/canva")
    assert res is not None
    assert res["ats_platform"] == "lever"
    assert res["board_token"] == "canva"
    assert "canva" in res["api_endpoint"]


def test_detect_from_url_ashby():
    res = detect_from_url("https://jobs.ashbyhq.com/notion")
    assert res is not None
    assert res["ats_platform"] == "ashby"
    assert res["board_token"] == "notion"


def test_detect_from_url_smartrecruiters():
    res = detect_from_url("https://careers.smartrecruiters.com/atlassian")
    assert res is not None
    assert res["ats_platform"] == "smartrecruiters"
    assert res["board_token"] == "atlassian"


def test_detect_from_url_recruitee():
    res = detect_from_url("https://tacitknowledge.recruitee.com")
    assert res is not None
    assert res["ats_platform"] == "recruitee"
    assert res["board_token"] == "tacitknowledge"


def test_detect_from_url_workday():
    res = detect_from_url("https://salesforce.wd1.myworkdayjobs.com/External_Career_Site")
    assert res is not None
    assert res["ats_platform"] == "workday"
    assert res["board_token"] == "salesforce"


def test_detect_from_html_embed_greenhouse():
    html = """
    <html>
      <head><title>Careers</title></head>
      <body>
        <h1>Work with us</h1>
        <iframe src="https://boards.greenhouse.io/embed/job_board?for=datadog"></iframe>
      </body>
    </html>
    """
    res = detect_from_html("https://datadog.com/careers", html)
    assert res["ats_platform"] == "greenhouse"
    assert res["board_token"] == "datadog"
    assert "greenhouse" in res["detected_sources"]


def test_detect_from_html_json_ld():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Backend Software Engineer",
          "hiringOrganization": { "@type": "Organization", "name": "Tech Corp" }
        }
        </script>
        <link rel="alternate" type="application/rss+xml" href="/jobs/feed.xml" />
        <link rel="sitemap" href="/job-sitemap.xml" />
      </head>
      <body><h1>Careers</h1></body>
    </html>
    """
    res = detect_from_html("https://techcorp.com/careers", html)
    assert res["has_json_ld"] is True
    assert "json_ld" in res["detected_sources"]
    assert "rss_feed" in res["detected_sources"]
    assert "sitemap" in res["detected_sources"]
    assert res["feed_url"] == "https://techcorp.com/jobs/feed.xml"
    assert res["sitemap_url"] == "https://techcorp.com/job-sitemap.xml"


def test_detect_career_url_mocked():
    import asyncio
    import backend.services.scrapling_client as sc

    sample_html = """
    <html>
      <body>
        <div id="lever-jobs-container"></div>
        <script src="https://jobs.lever.co/examplecorp"></script>
      </body>
    </html>
    """

    def mock_fetch(url, *args, **kwargs):
        return ScraplingResponse(
            url=url,
            status=200,
            text=sample_html,
        )

    sc.mock_fetch_handler = mock_fetch
    try:
        res = asyncio.run(detect_career_url("https://examplecorp.com/careers", fetch_if_needed=True))
        assert res["ats_platform"] == "lever"
        assert res["domain"] == "examplecorp.com"
        assert res["confidence"] > 0.5
    finally:
        sc.mock_fetch_handler = None


def test_detect_career_url_ssrf_blocked():
    import asyncio
    # Attempting to scan loopback/internal IP must return safe error instead of crashing
    res = asyncio.run(detect_career_url("http://127.0.0.1/admin", fetch_if_needed=True))
    assert "error" in res or res["confidence"] == 0.0
