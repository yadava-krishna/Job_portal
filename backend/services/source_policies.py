"""backend/services/source_policies.py

Central source policy registry and legal/compliance permission controller.

Defines permitted access methods, compliance statuses, and rate limits for all
supported job sources. Enforces ethical data acquisition guidelines:
- Strictly prohibits automated scraping, session hijacking, or CAPTCHA bypass
  for protected portals (LinkedIn, Indeed, Naukri).
- Permits only official APIs, verified public feeds, open sitemaps, and public
  pages with Schema.org JobPosting or permitted HTML under robots.txt compliance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PermissionStatus(StrEnum):
    APPROVED_PUBLIC_API = "approved_public_api"
    APPROVED_PUBLIC_FEED = "approved_public_feed"
    APPROVED_PUBLIC_PAGE = "approved_public_page"
    PERMISSION_REQUIRED = "permission_required"
    MANUAL_USER_PROVIDED = "manual_user_provided"
    BLOCKED = "blocked"


class SourceCategory(StrEnum):
    ATS_API = "ats_api"
    RSS_FEED = "rss_feed"
    SITEMAP = "sitemap"
    CAREER_PAGE = "career_page"
    JSON_LD = "json_ld"
    AGGREGATOR_API = "aggregator_api"
    GOVERNMENT = "government"
    ACADEMIC = "academic"
    COMMERCIAL_PORTAL = "commercial_portal"


class AccessMethod(StrEnum):
    API = "api"
    FEED = "feed"
    SITEMAP = "sitemap"
    JSON_LD = "json_ld"
    HTML = "html"
    ASSISTED_ONLY = "assisted_only"


@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    name: str
    domain: str
    category: SourceCategory
    access_method: AccessMethod
    permission_status: PermissionStatus
    robots_txt_checked: bool = True
    rate_limit_rpm: int = 10
    requires_js: bool = False
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_discoverable(self) -> bool:
        """Indicates if JobPilot may automatically fetch jobs via this source."""
        return self.permission_status in (
            PermissionStatus.APPROVED_PUBLIC_API,
            PermissionStatus.APPROVED_PUBLIC_FEED,
            PermissionStatus.APPROVED_PUBLIC_PAGE,
        )


# Comprehensive registry of all known and configured source policies
_REGISTRY: dict[str, SourcePolicy] = {
    # ---------------- ATS Platforms (Official unauthenticated job boards) ----------------
    "greenhouse": SourcePolicy(
        source_id="greenhouse",
        name="Greenhouse Job Board API",
        domain="boards-api.greenhouse.io",
        category=SourceCategory.ATS_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=30,
        notes="Official public boards API for unauthenticated job retrieval.",
    ),
    "lever": SourcePolicy(
        source_id="lever",
        name="Lever Postings API",
        domain="api.lever.co",
        category=SourceCategory.ATS_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=30,
        notes="Official public postings API for unauthenticated job retrieval.",
    ),
    "ashby": SourcePolicy(
        source_id="ashby",
        name="Ashby Job Board API",
        domain="api.ashbyhq.com",
        category=SourceCategory.ATS_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=30,
        notes="Official public postings API for unauthenticated job retrieval.",
    ),
    "smartrecruiters": SourcePolicy(
        source_id="smartrecruiters",
        name="SmartRecruiters Postings API",
        domain="api.smartrecruiters.com",
        category=SourceCategory.ATS_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=20,
        notes="Official public postings API for unauthenticated job retrieval.",
    ),
    "recruitee": SourcePolicy(
        source_id="recruitee",
        name="Recruitee Careers Site API",
        domain="recruitee.com",
        category=SourceCategory.ATS_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=20,
        notes="Public career site offers endpoint.",
    ),
    "workable": SourcePolicy(
        source_id="workable",
        name="Workable Widget API",
        domain="apply.workable.com",
        category=SourceCategory.ATS_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.PERMISSION_REQUIRED,
        rate_limit_rpm=10,
        notes="Public widget API exists but third-party usage is undocumented. Permission required.",
    ),

    # ---------------- Aggregators (Official APIs or permitted public feeds) ----------------
    "adzuna": SourcePolicy(
        source_id="adzuna",
        name="Adzuna Jobs API",
        domain="api.adzuna.com",
        category=SourceCategory.AGGREGATOR_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=15,
        notes="Official developer key-based REST API.",
    ),
    "remotive": SourcePolicy(
        source_id="remotive",
        name="Remotive Remote Jobs API",
        domain="remotive.com",
        category=SourceCategory.AGGREGATOR_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=12,
        notes="Public API without authentication; requires attribution link-back.",
    ),
    "himalayas": SourcePolicy(
        source_id="himalayas",
        name="Himalayas Jobs API",
        domain="himalayas.app",
        category=SourceCategory.AGGREGATOR_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=10,
        notes="Public API; requires attribution link-back.",
    ),
    "remoteok": SourcePolicy(
        source_id="remoteok",
        name="Remote OK API & RSS",
        domain="remoteok.com",
        category=SourceCategory.AGGREGATOR_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=10,
        notes="Public JSON API and RSS feed.",
    ),
    "arbeitnow": SourcePolicy(
        source_id="arbeitnow",
        name="Arbeitnow Job Board API",
        domain="arbeitnow.com",
        category=SourceCategory.AGGREGATOR_API,
        access_method=AccessMethod.API,
        permission_status=PermissionStatus.APPROVED_PUBLIC_API,
        rate_limit_rpm=15,
        notes="Public API for European and international tech/remote roles.",
    ),

    # ---------------- Commercial Portals (Strict Assisted Mode Only) ----------------
    "linkedin": SourcePolicy(
        source_id="linkedin",
        name="LinkedIn",
        domain="linkedin.com",
        category=SourceCategory.COMMERCIAL_PORTAL,
        access_method=AccessMethod.ASSISTED_ONLY,
        permission_status=PermissionStatus.MANUAL_USER_PROVIDED,
        notes="Scraping prohibited by Terms of Service. Ingestion via read-only user email alerts and clipper only.",
    ),
    "indeed": SourcePolicy(
        source_id="indeed",
        name="Indeed",
        domain="indeed.com",
        category=SourceCategory.COMMERCIAL_PORTAL,
        access_method=AccessMethod.ASSISTED_ONLY,
        permission_status=PermissionStatus.MANUAL_USER_PROVIDED,
        notes="Scraping prohibited by Terms of Service. Ingestion via read-only user email alerts and clipper only.",
    ),
    "naukri": SourcePolicy(
        source_id="naukri",
        name="Naukri",
        domain="naukri.com",
        category=SourceCategory.COMMERCIAL_PORTAL,
        access_method=AccessMethod.ASSISTED_ONLY,
        permission_status=PermissionStatus.MANUAL_USER_PROVIDED,
        notes="Scraping prohibited by Terms of Service. Ingestion via read-only user email alerts and clipper only.",
    ),

    # ---------------- Indian Public Sector & Government ----------------
    "ncs_india": SourcePolicy(
        source_id="ncs_india",
        name="National Career Service (NCS)",
        domain="ncs.gov.in",
        category=SourceCategory.GOVERNMENT,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Official Government of India portal for public vacancies.",
    ),
    "upsc": SourcePolicy(
        source_id="upsc",
        name="Union Public Service Commission (UPSC)",
        domain="upsc.gov.in",
        category=SourceCategory.GOVERNMENT,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Public examination and recruitment notifications.",
    ),
    "ssc": SourcePolicy(
        source_id="ssc",
        name="Staff Selection Commission (SSC)",
        domain="ssc.gov.in",
        category=SourceCategory.GOVERNMENT,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Public vacancy circulars and notification feeds.",
    ),
    "isro": SourcePolicy(
        source_id="isro",
        name="ISRO Careers",
        domain="isro.gov.in",
        category=SourceCategory.GOVERNMENT,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Public recruitment notifications for research and engineering roles.",
    ),
    "drdo": SourcePolicy(
        source_id="drdo",
        name="DRDO Recruitment",
        domain="drdo.gov.in",
        category=SourceCategory.GOVERNMENT,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Public vacancy notices for defence research personnel.",
    ),

    # ---------------- Academic & Research Institutions ----------------
    "iit_bombay": SourcePolicy(
        source_id="iit_bombay",
        name="IIT Bombay Careers",
        domain="iitb.ac.in",
        category=SourceCategory.ACADEMIC,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Public staff and faculty appointment listings.",
    ),
    "iit_delhi": SourcePolicy(
        source_id="iit_delhi",
        name="IIT Delhi Careers",
        domain="iitd.ac.in",
        category=SourceCategory.ACADEMIC,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Public academic and technical job postings.",
    ),
    "iit_madras": SourcePolicy(
        source_id="iit_madras",
        name="IIT Madras Careers",
        domain="iitm.ac.in",
        category=SourceCategory.ACADEMIC,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Public vacancies and project staff openings.",
    ),
    "iisc_bangalore": SourcePolicy(
        source_id="iisc_bangalore",
        name="IISc Bangalore Positions",
        domain="iisc.ac.in",
        category=SourceCategory.ACADEMIC,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Public research associate and faculty notifications.",
    ),

    # ---------------- Generic User-Submitted Career Pages ----------------
    "user_career_url": SourcePolicy(
        source_id="user_career_url",
        name="User-Submitted Career Page",
        domain="*",
        category=SourceCategory.CAREER_PAGE,
        access_method=AccessMethod.HTML,
        permission_status=PermissionStatus.APPROVED_PUBLIC_PAGE,
        rate_limit_rpm=6,
        notes="Dynamic discovery from user-submitted company career URLs with SSRF guards and robots.txt check.",
    ),
}


def get_source_policy(source_id: str) -> SourcePolicy | None:
    """Retrieve policy definition for a source identifier."""
    return _REGISTRY.get(source_id.lower())


def is_permitted(source_id: str, access_method: str | None = None) -> bool:
    """Check whether a given source is permitted for automated job discovery."""
    policy = get_source_policy(source_id)
    if not policy:
        return False
    if not policy.is_discoverable:
        return False
    if access_method and policy.access_method != access_method:
        return False
    return True


def register_source_policy(policy: SourcePolicy) -> None:
    """Register or override a source policy in the global registry."""
    _REGISTRY[policy.source_id.lower()] = policy


def list_policies(category: SourceCategory | None = None) -> list[SourcePolicy]:
    """List all registered source policies, optionally filtered by category."""
    if category is None:
        return list(_REGISTRY.values())
    return [p for p in _REGISTRY.values() if p.category == category]
