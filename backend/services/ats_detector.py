"""backend/services/ats_detector.py

Heuristic and content-based detector for employer career pages and job boards.
Identifies:
- ATS platforms (Greenhouse, Lever, Ashby, SmartRecruiters, Recruitee, Workday, iCIMS, Taleo, SuccessFactors, Workable, BambooHR)
- Public board tokens
- Schema.org JobPosting microdata / JSON-LD
- XML sitemaps
- RSS/Atom syndication feeds
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse, urlsplit

from backend.services.scrapling_client import ScraplingError, SSRFBlockedError, get_scrapling_client

log = logging.getLogger(__name__)

# URL Pattern Regexes for instantaneous zero-network detection
_GREENHOUSE_URL_RE = re.compile(
    r"(?:boards|job-boards|boards\.eu)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-zA-Z0-9_\-]+)",
    re.IGNORECASE,
)
_LEVER_URL_RE = re.compile(r"jobs\.lever\.co/([a-zA-Z0-9_\-]+)", re.IGNORECASE)
_ASHBY_URL_RE = re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_\-]+)", re.IGNORECASE)
_SMARTRECRUITERS_URL_RE = re.compile(
    r"(?:careers\.)?smartrecruiters\.com/([a-zA-Z0-9_\-]+)", re.IGNORECASE
)
_RECRUITEE_URL_RE = re.compile(
    r"(?:https?://)?([a-zA-Z0-9_\-]+)\.recruitee\.com", re.IGNORECASE
)
_WORKDAY_URL_RE = re.compile(
    r"(?:https?://)?([a-zA-Z0-9_\-]+)(?:\.wd\d+)?\.myworkdayjobs\.com", re.IGNORECASE
)
_WORKABLE_URL_RE = re.compile(
    r"apply\.workable\.com/([a-zA-Z0-9_\-]+)", re.IGNORECASE
)
_BAMBOOHR_URL_RE = re.compile(
    r"([a-zA-Z0-9_\-]+)\.bamboohr\.(?:com|co\.uk)/careers", re.IGNORECASE
)
_ICIMS_URL_RE = re.compile(r"([a-zA-Z0-9_\-]+)\.icims\.com", re.IGNORECASE)
_TALEO_URL_RE = re.compile(r"([a-zA-Z0-9_\-]+)\.taleo\.net", re.IGNORECASE)
_SUCCESSFACTORS_URL_RE = re.compile(
    r"(?:jobs\.sap\.com|career\d*\.successfactors\.(?:com|eu))", re.IGNORECASE
)

# HTML Content Embed Regexes
_EMBED_GH_IFRAME_RE = re.compile(
    r'<iframe[^>]+src=["\'](?:https?:)?//(?:boards|job-boards)\.greenhouse\.io/embed/job_board\?for=([a-zA-Z0-9_\-]+)',
    re.IGNORECASE,
)
_EMBED_GH_SCRIPT_RE = re.compile(
    r'grnh\.se/([a-zA-Z0-9_\-]+)|boards\.greenhouse\.io/([a-zA-Z0-9_\-]+)',
    re.IGNORECASE,
)
_EMBED_LEVER_RE = re.compile(
    r'lever-jobs-container|jobs\.lever\.co/([a-zA-Z0-9_\-]+)',
    re.IGNORECASE,
)
_EMBED_ASHBY_RE = re.compile(
    r'jobs\.ashbyhq\.com/([a-zA-Z0-9_\-]+)|ashby_embed',
    re.IGNORECASE,
)
_EMBED_SMART_RE = re.compile(
    r'smartrecruiters\.com/([a-zA-Z0-9_\-]+)|smart-widget',
    re.IGNORECASE,
)


def detect_from_url(url: str) -> dict[str, Any] | None:
    """Instant URL-based heuristic detection without performing network calls."""
    if not url:
        return None

    clean_url = url.strip()

    # Greenhouse
    m = _GREENHOUSE_URL_RE.search(clean_url)
    if m:
        token = m.group(1).split("?")[0].split("/")[0]
        return {
            "ats_platform": "greenhouse",
            "board_token": token,
            "api_endpoint": f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
            "confidence": 1.0,
        }

    # Lever
    m = _LEVER_URL_RE.search(clean_url)
    if m:
        token = m.group(1).split("?")[0].split("/")[0]
        return {
            "ats_platform": "lever",
            "board_token": token,
            "api_endpoint": f"https://api.lever.co/v0/postings/{token}",
            "confidence": 1.0,
        }

    # Ashby
    m = _ASHBY_URL_RE.search(clean_url)
    if m:
        token = m.group(1).split("?")[0].split("/")[0]
        return {
            "ats_platform": "ashby",
            "board_token": token,
            "api_endpoint": f"https://api.ashbyhq.com/posting-api/job-board/{token}",
            "confidence": 1.0,
        }

    # SmartRecruiters
    m = _SMARTRECRUITERS_URL_RE.search(clean_url)
    if m:
        token = m.group(1).split("?")[0].split("/")[0]
        return {
            "ats_platform": "smartrecruiters",
            "board_token": token,
            "api_endpoint": f"https://api.smartrecruiters.com/v1/companies/{token}/postings",
            "confidence": 0.95,
        }

    # Recruitee
    m = _RECRUITEE_URL_RE.search(clean_url)
    if m:
        token = m.group(1).split(".")[0]
        return {
            "ats_platform": "recruitee",
            "board_token": token,
            "api_endpoint": f"https://{token}.recruitee.com/api/offers/",
            "confidence": 0.95,
        }

    # Workable
    m = _WORKABLE_URL_RE.search(clean_url)
    if m:
        token = m.group(1).split("?")[0].split("/")[0]
        return {
            "ats_platform": "workable",
            "board_token": token,
            "api_endpoint": f"https://apply.workable.com/api/v1/widget/accounts/{token}",
            "confidence": 0.95,
        }

    # Workday
    m = _WORKDAY_URL_RE.search(clean_url)
    if m:
        return {
            "ats_platform": "workday",
            "board_token": m.group(1),
            "api_endpoint": None,
            "confidence": 0.90,
        }

    # BambooHR
    m = _BAMBOOHR_URL_RE.search(clean_url)
    if m:
        return {
            "ats_platform": "bamboohr",
            "board_token": m.group(1),
            "api_endpoint": None,
            "confidence": 0.90,
        }

    # iCIMS
    m = _ICIMS_URL_RE.search(clean_url)
    if m:
        return {
            "ats_platform": "icims",
            "board_token": m.group(1),
            "api_endpoint": None,
            "confidence": 0.85,
        }

    # Taleo
    m = _TALEO_URL_RE.search(clean_url)
    if m:
        return {
            "ats_platform": "taleo",
            "board_token": m.group(1),
            "api_endpoint": None,
            "confidence": 0.85,
        }

    # SuccessFactors
    m = _SUCCESSFACTORS_URL_RE.search(clean_url)
    if m:
        return {
            "ats_platform": "successfactors",
            "board_token": None,
            "api_endpoint": None,
            "confidence": 0.85,
        }

    return None


def detect_from_html(base_url: str, html: str) -> dict[str, Any]:
    """Inspects page HTML content for embedded ATS iframes, widgets, feeds, and JSON-LD."""
    results: dict[str, Any] = {
        "ats_platform": None,
        "board_token": None,
        "api_endpoint": None,
        "detected_sources": [],
        "has_json_ld": False,
        "sitemap_url": None,
        "feed_url": None,
        "confidence": 0.0,
    }

    if not html:
        return results

    # 1. Embedded Greenhouse
    m = _EMBED_GH_IFRAME_RE.search(html)
    if m:
        token = m.group(1)
        results["ats_platform"] = "greenhouse"
        results["board_token"] = token
        results["api_endpoint"] = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        results["detected_sources"].append("greenhouse")
        results["confidence"] = 0.95
    else:
        m2 = _EMBED_GH_SCRIPT_RE.search(html)
        if m2:
            token = m2.group(1) or m2.group(2)
            results["ats_platform"] = "greenhouse"
            results["board_token"] = token
            results["api_endpoint"] = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
            results["detected_sources"].append("greenhouse")
            results["confidence"] = 0.85

    # 2. Embedded Lever
    if not results["ats_platform"]:
        m = _EMBED_LEVER_RE.search(html)
        if m:
            token = m.group(1) if m.groups() and m.group(1) else None
            results["ats_platform"] = "lever"
            results["board_token"] = token
            if token:
                results["api_endpoint"] = f"https://api.lever.co/v0/postings/{token}"
            results["detected_sources"].append("lever")
            results["confidence"] = 0.85

    # 3. Embedded Ashby
    if not results["ats_platform"]:
        m = _EMBED_ASHBY_RE.search(html)
        if m:
            token = m.group(1) if m.groups() and m.group(1) else None
            results["ats_platform"] = "ashby"
            results["board_token"] = token
            if token:
                results["api_endpoint"] = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
            results["detected_sources"].append("ashby")
            results["confidence"] = 0.85

    # 4. Embedded SmartRecruiters
    if not results["ats_platform"]:
        m = _EMBED_SMART_RE.search(html)
        if m:
            token = m.group(1) if m.groups() and m.group(1) else None
            results["ats_platform"] = "smartrecruiters"
            results["board_token"] = token
            if token:
                results["api_endpoint"] = f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
            results["detected_sources"].append("smartrecruiters")
            results["confidence"] = 0.80

    # 5. Schema.org JobPosting JSON-LD Detection
    if 'application/ld+json' in html and 'JobPosting' in html:
        results["has_json_ld"] = True
        results["detected_sources"].append("json_ld")

    # 6. Feed Detection
    feed_match = re.search(
        r'<link[^>]+type=["\']application/(?:rss\+xml|atom\+xml)["\'][^>]+href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if feed_match:
        feed_href = feed_match.group(1)
        results["feed_url"] = urljoin(base_url, feed_href)
        results["detected_sources"].append("rss_feed")

    # 7. Sitemap link detection
    sitemap_match = re.search(
        r'<link[^>]+rel=["\']sitemap["\'][^>]+href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if sitemap_match:
        sitemap_href = sitemap_match.group(1)
        results["sitemap_url"] = urljoin(base_url, sitemap_href)
        results["detected_sources"].append("sitemap")

    return results


async def detect_career_url(url: str, fetch_if_needed: bool = True) -> dict[str, Any]:
    """Complete asynchronous detection inspecting URL first, then fetching page content safely if needed."""
    url = url.strip()
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Step 1: Instant URL heuristic check
    url_result = detect_from_url(url)
    if url_result:
        return {
            "url": url,
            "domain": domain,
            "ats_platform": url_result["ats_platform"],
            "board_token": url_result["board_token"],
            "api_endpoint": url_result["api_endpoint"],
            "detected_sources": [url_result["ats_platform"]],
            "has_json_ld": False,
            "sitemap_url": None,
            "feed_url": None,
            "confidence": url_result["confidence"],
            "method": "url_pattern",
        }

    # Default fallback
    base_res: dict[str, Any] = {
        "url": url,
        "domain": domain,
        "ats_platform": None,
        "board_token": None,
        "api_endpoint": None,
        "detected_sources": [],
        "has_json_ld": False,
        "sitemap_url": None,
        "feed_url": None,
        "confidence": 0.0,
        "method": "static_probe",
    }

    if not fetch_if_needed:
        return base_res

    # Step 2: Safe fetch page content with SSRF and size bounds
    client = get_scrapling_client()
    try:
        resp = await client.fetch_page_async(url, js_render=False)
        html_res = detect_from_html(url, resp.text)
        base_res.update(html_res)
        base_res["method"] = "html_inspection"
    except (SSRFBlockedError, ScraplingError) as exc:
        log.warning("ATS detection fetch halted for %s: %s", url, exc)
        base_res["error"] = str(exc)

    return base_res
