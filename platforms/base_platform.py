"""Common interface for job platforms.

No adapter scrapes, automates a browser, or calls private APIs. Jobs reach the
system only through permitted channels (the candidate's own alert emails, files
or URLs the candidate imports), and applications are submitted by the candidate
unless an adapter declares an authorised submission mechanism.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.models import ApplicationStatus, JobPosting, Platform, RawJobRecord
from core.settings import SearchConfig

if TYPE_CHECKING:
    from database.db import Database
    from discovery.sources import JobSource

log = logging.getLogger(__name__)


class PlatformError(Exception):
    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class SubmissionNotPermitted(PlatformError):
    """Raised when asked to submit through a platform with no authorised submission mechanism."""


class SecurityChallengeEncountered(PlatformError):
    """A CAPTCHA, OTP, login challenge or unexpected form appeared; processing must stop."""


@dataclass(frozen=True)
class AccessCapabilities:
    automated_search: bool
    automated_apply: bool
    discovery_channels: tuple[str, ...]
    application_method: str
    notes: str


@dataclass
class SearchLink:
    platform: Platform
    title: str
    location: str
    url: str


@dataclass
class SearchResult:
    platform: Platform
    jobs: list[JobPosting] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    records_seen: int = 0


TRACKING_PARAMS = re.compile(r"^(utm_.*|trk.*|refid|trackingid|lipi|midtoken|midsig|eid|otptoken|ssid|src|from|alertid|ref.*|cmp|tk|sjdu|acatk|pub|xkcb|sid)$", re.I)


def strip_tracking(url: str, keep: tuple[str, ...] = ()) -> str:
    """Remove tracking query parameters and fragments from a URL."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if k in keep or not TRACKING_PARAMS.match(k)]
    if keep:
        query = [(k, v) for k, v in query if k in keep]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower(), path, urlencode(query), ""))


class BasePlatform(ABC):
    platform: Platform
    official_domains: tuple[str, ...]
    capabilities: AccessCapabilities

    def __init__(self, sources: list["JobSource"] | None = None, settings: Any = None):
        self.sources = sources or []
        self.settings = settings

    # ---- required interface --------------------------------------------------
    def search_jobs(self, criteria: SearchConfig) -> SearchResult:
        """Collect this platform's jobs from every permitted source configured for it.

        Filtering by score/eligibility happens later so nothing is silently discarded.
        """
        from discovery.job_extractor import JobExtractor

        extractor = JobExtractor(self)
        result = SearchResult(platform=self.platform)
        for source in self.sources:
            try:
                records = source.fetch(self.platform)
            except PlatformError as exc:
                result.errors.append(f"{source.name}: {exc}")
                continue
            for record in records:
                result.records_seen += 1
                try:
                    result.jobs.append(extractor.to_posting(record))
                except ValueError as exc:
                    result.errors.append(f"{source.name}: skipped malformed record ({exc})")
        log.info("%s: %d job records from %d source(s).", self.platform, result.records_seen, len(self.sources))
        return result

    def extract_job_details(self, record: RawJobRecord) -> dict[str, Any]:
        """Platform-specific normalisation of the raw record's structured fields."""
        url = self.get_job_url(record)
        return {
            "platform_job_id": record.job_id or (self.identify_job_id(record.url) if record.url else None),
            "url": url,
            "title": (record.title or "").strip(),
            "company": (record.company or "").strip(),
            "location": (record.location or "").strip() or None,
            "application_method": record.application_method or self.capabilities.application_method,
        }

    def extract_job_description(self, record: RawJobRecord) -> str | None:
        """Return the description supplied with the record. Never fetched from the platform."""
        if not record.description:
            return None
        text = record.description.replace("\r\n", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() or None

    @abstractmethod
    def identify_job_id(self, url: str | None) -> str | None:
        ...

    @abstractmethod
    def canonical_url(self, job_id: str) -> str | None:
        ...

    def get_job_url(self, record: RawJobRecord) -> str | None:
        job_id = record.job_id or (self.identify_job_id(record.url) if record.url else None)
        if job_id:
            canonical = self.canonical_url(job_id)
            if canonical:
                return canonical
        return strip_tracking(record.url) if record.url else None

    def check_application_status(self, job_key: str, db: "Database") -> ApplicationStatus | None:
        """Return the locally tracked status.

        None of the supported platforms offers a job-seeker API for application
        status, so the source of truth is the local database, updated from
        candidate confirmations and confirmation emails.
        """
        app = db.get_application_by_job_key(job_key)
        return ApplicationStatus(app["status"]) if app else None

    def submit_application(self, job: JobPosting, package: dict[str, Any]) -> dict[str, Any]:
        """Submit through an authorised mechanism. No current platform provides one to this tool."""
        raise SubmissionNotPermitted(
            f"{self.platform} has no authorised automated submission mechanism available to this tool. "
            f"{self.capabilities.notes}"
        )

    @abstractmethod
    def build_search_links(self, criteria: SearchConfig) -> list[SearchLink]:
        """Pre-filtered search URLs for the candidate to open and review manually."""

    # ---- helpers ---------------------------------------------------------------
    def is_official_url(self, url: str | None) -> bool:
        if not url:
            return False
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        host = parts.netloc.lower().split(":")[0]
        return parts.scheme == "https" and any(host == d or host.endswith("." + d) for d in self.official_domains)

    @staticmethod
    def experience_band(criteria: SearchConfig) -> tuple[int, int]:
        return int(criteria.experience_min_years), int(criteria.experience_max_years)

    @staticmethod
    def is_remote_location(location: str) -> bool:
        return "remote" in location.lower()

    @staticmethod
    def city_of(location: str) -> str:
        return re.split(r"[,\-–]", location)[0].strip()
