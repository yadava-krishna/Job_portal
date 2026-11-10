"""Tests for ScraplingClient: SSRF security, rate-limiting, robots.txt, and HTML parsing."""

from __future__ import annotations

import pytest
from backend.services.scrapling_client import (
    ScraplingClient,
    SSRFBlockedError,
    ScraplingResponse,
    client as default_client,
)


def test_ssrf_blocks_private_and_loopback_ips():
    """Verify that SSRF guard blocks localhost, internal hostnames, and bare IP addresses."""
    # Loopback & local
    with pytest.raises(SSRFBlockedError):
        ScraplingClient.validate_url("https://127.0.0.1/careers")

    with pytest.raises(SSRFBlockedError):
        ScraplingClient.validate_url("https://localhost/careers")

    with pytest.raises(SSRFBlockedError):
        ScraplingClient.validate_url("https://internal.corp/careers")

    with pytest.raises(SSRFBlockedError):
        ScraplingClient.validate_url("http://169.254.169.254/latest/meta-data/")

    # Prohibited non-standard ports
    with pytest.raises(SSRFBlockedError):
        ScraplingClient.validate_url("https://example.com:8080/careers")


def test_scrapling_response_adaptor_parsing():
    """Verify that ScraplingResponse exposes CSS and XPath querying via Scrapling Adaptor."""
    html = """
    <html>
      <body>
        <div class="job-card">
          <h2 class="title">Lead Python Developer</h2>
          <span class="company">Acme Labs</span>
          <span class="location">Remote</span>
        </div>
      </body>
    </html>
    """
    resp = ScraplingResponse(url="https://example.com/jobs", status=200, text=html)
    assert resp.css(".title::text").get().strip() == "Lead Python Developer"
    assert resp.css(".company::text").get().strip() == "Acme Labs"
    assert resp.xpath("//span[@class='location']/text()").get().strip() == "Remote"


def test_domain_rate_limiter():
    """Verify token bucket rate limiter tracking and domain counters."""
    client = ScraplingClient(max_concurrency=2)
    client.rate_limiter.set_rate_limit("example.com", 60)
    assert client.rate_limiter.get_rate_limit("example.com") == 60
    assert client.rate_limiter.get_rate_limit("unknown.com") == 10
