"""backend/services/connectors/base_connector.py

Abstract base connector interface for JobPilot multi-source job discovery.

Every connector adheres to a standard lifecycle:
- discover(criteria) -> list[NormalizedJob]
- fetch_job_details(job_ref) -> NormalizedJob | None
- normalize_job(raw) -> NormalizedJob
- validate_job(job) -> tuple[bool, list[str]]
- get_source_health() -> SourceHealth
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.services.normalization import NormalizedJob
from backend.services.source_policies import AccessMethod, SourceCategory, SourcePolicy, get_source_policy


@dataclass
class SourceHealth:
    source_id: str
    status: str  # ok | degraded | failing | not_configured | disabled | unknown
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    jobs_discovered: int = 0
    jobs_updated: int = 0
    jobs_rejected: int = 0
    details: dict[str, Any] = field(default_factory=dict)


class BaseConnector(ABC):
    """Abstract base class for all job source discovery connectors."""

    source_id: str
    name: str
    domain: str
    category: SourceCategory
    access_method: AccessMethod

    def __init__(self):
        self.health = SourceHealth(
            source_id=self.source_id,
            status="unknown",
        )

    @property
    def policy(self) -> SourcePolicy | None:
        """Fetch the compliance policy defined for this connector."""
        return get_source_policy(self.source_id)

    @abstractmethod
    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        """Discover jobs from this source matching optional search criteria."""
        ...

    def fetch_job_details(self, job_ref: str) -> NormalizedJob | None:
        """Fetch detailed information for a specific job posting if supported."""
        return None

    def validate_job(self, job: NormalizedJob) -> tuple[bool, list[str]]:
        """Validate candidate job against minimum quality thresholds."""
        errors: list[str] = []
        if not job.title or len(job.title.strip()) < 2:
            errors.append("Missing or invalid job title.")
        if not job.company or len(job.company.strip()) < 2:
            errors.append("Missing employer name.")
        if not job.job_url or not job.job_url.startswith(("http://", "https://")):
            errors.append("Missing or invalid job URL.")
        if not job.description or len(job.description.strip()) < 20:
            errors.append("Job description is missing or too brief.")
        return len(errors) == 0, errors

    def get_source_health(self) -> SourceHealth:
        """Return the current health state of this connector."""
        return self.health

    def record_success(self, count: int) -> None:
        self.health.status = "ok"
        self.health.last_success_at = datetime.utcnow()
        self.health.last_run_at = datetime.utcnow()
        self.health.last_error = None
        self.health.jobs_discovered += count

    def record_failure(self, error: str) -> None:
        self.health.status = "failing"
        self.health.last_run_at = datetime.utcnow()
        self.health.last_error = error
