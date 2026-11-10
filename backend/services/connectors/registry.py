"""backend/services/connectors/registry.py

Central connector registry managing connector instances and dispatching discovery runs.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.services.connectors.academic_connector import AcademicConnector
from backend.services.connectors.arbeitnow_connector import ArbeitnowConnector
from backend.services.connectors.base_connector import BaseConnector, SourceHealth
from backend.services.connectors.career_url_connector import CareerUrlConnector
from backend.services.connectors.government_connector import GovernmentConnector
from backend.services.connectors.himalayas_connector import HimalayasConnector
from backend.services.connectors.html_connector import HtmlConnector
from backend.services.connectors.jsonld_connector import JsonLdConnector
from backend.services.connectors.ncs_connector import NcsConnector
from backend.services.connectors.remoteok_connector import RemoteOkConnector
from backend.services.connectors.remotive_connector import RemotiveConnector
from backend.services.connectors.rss_connector import RssConnector
from backend.services.connectors.sitemap_connector import SitemapConnector
from backend.services.normalization import NormalizedJob
from backend.services.source_policies import SourceCategory, is_permitted

log = logging.getLogger(__name__)


class ConnectorRegistry:
    """Manages active connectors and executes compliant job discovery."""

    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            JsonLdConnector(),
            RssConnector(),
            SitemapConnector(),
            HtmlConnector(),
            CareerUrlConnector(),
            RemotiveConnector(),
            HimalayasConnector(),
            RemoteOkConnector(),
            ArbeitnowConnector(),
            NcsConnector(),
            GovernmentConnector(),
            AcademicConnector(),
        ]
        for conn in defaults:
            self.register(conn)

    def register(self, connector: BaseConnector) -> None:
        self._connectors[connector.source_id.lower()] = connector

    def get(self, source_id: str) -> BaseConnector | None:
        return self._connectors.get(source_id.lower())

    def list_all(self, category: SourceCategory | None = None) -> list[BaseConnector]:
        if category is None:
            return list(self._connectors.values())
        return [c for c in self._connectors.values() if c.category == category]

    def list_health(self) -> list[SourceHealth]:
        return [c.get_source_health() for c in self._connectors.values()]

    def run_connector(self, source_id: str, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        """Execute discovery via named connector, enforcing permission policies."""
        source_id = source_id.lower()
        if not is_permitted(source_id):
            log.warning("Attempted to execute unpermitted source: %s", source_id)
            return []

        conn = self.get(source_id)
        if not conn:
            log.warning("Connector not found for source: %s", source_id)
            return []

        try:
            jobs = conn.discover(criteria)
            log.info("Connector %s discovered %d valid jobs", source_id, len(jobs))
            return jobs
        except Exception as exc:
            log.error("Connector %s failed during discovery: %s", source_id, exc)
            conn.record_failure(str(exc))
            return []


# Global singleton connector registry
registry = ConnectorRegistry()
