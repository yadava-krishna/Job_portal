"""backend/services/connectors/rss_connector.py

Generic RSS and Atom feed connector using Scrapling for high-speed XML parsing.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from backend.services.connectors.base_connector import BaseConnector
from backend.services.normalization import (
    NormalizedJob,
    canonical_url,
    html_to_text,
    local_date,
    work_mode as normalize_work_mode,
)
from backend.services.scrapling_client import ScraplingClient, client as default_client
from backend.services.source_policies import AccessMethod, SourceCategory

log = logging.getLogger(__name__)


def parse_feed_xml(xml_content: str, feed_url: str, default_company: str | None = None) -> list[NormalizedJob]:
    """Parse RSS 2.0 or Atom XML content into NormalizedJob objects."""
    jobs: list[NormalizedJob] = []
    try:
        root = ET.fromstring(xml_content.encode("utf-8", errors="replace"))
    except Exception as exc:
        log.warning("XML parsing failed for feed %s: %s", feed_url, exc)
        return []

    domain = urlparse(feed_url).netloc.lower()

    # Detect Atom vs RSS
    # Atom: namespace usually http://www.w3.org/2005/Atom or tag == 'feed'
    is_atom = root.tag.endswith("feed") or "http://www.w3.org/2005/Atom" in root.tag

    if is_atom:
        ns = {"atom": "http://www.w3.org/2005/Atom"} if "http://www.w3.org/2005/Atom" in root.tag else {}
        entries = root.findall(".//atom:entry", ns) if ns else root.findall(".//entry")
        for entry in entries:
            title_node = entry.find("atom:title", ns) if ns else entry.find("title")
            title = (title_node.text or "").strip() if title_node is not None else ""
            if not title:
                continue

            # Link
            link = ""
            link_node = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns) if ns else entry.find("link")
            if link_node is not None:
                link = link_node.attrib.get("href") or link_node.text or ""

            # Content / Summary
            desc_node = entry.find("atom:content", ns) or entry.find("atom:summary", ns) if ns else (entry.find("content") or entry.find("summary"))
            raw_desc = (desc_node.text or "").strip() if desc_node is not None else ""
            clean_desc = html_to_text(raw_desc) if "<" in raw_desc else raw_desc

            # Published Date
            date_node = entry.find("atom:published", ns) or entry.find("atom:updated", ns) if ns else (entry.find("published") or entry.find("updated"))
            posted_at: date | None = None
            if date_node is not None and date_node.text:
                try:
                    posted_at = local_date(date_node.text[:10])
                except Exception:
                    posted_at = None

            # Author / Company
            author_node = entry.find("atom:author/atom:name", ns) if ns else entry.find("author/name")
            company = (author_node.text or "").strip() if author_node is not None else (default_company or domain)

            job = NormalizedJob(
                source="rss_feed",
                source_key=f"feed:{domain}:{canonical_url(link) or link}",
                platform="Feed",
                company=company,
                title=title,
                job_url=link,
                application_url=link,
                description=clean_desc,
                posted_at=posted_at,
                posted_at_source="platform_feed",
                work_mode=normalize_work_mode("", title),
                extraction_method="atom_feed",
                extraction_confidence=0.90,
                parser_version="1.0.0",
            )
            jobs.append(job)

    else:
        # RSS 2.0 (<rss><channel><item>)
        channel = root.find("channel")
        channel_title = (channel.findtext("title") or "") if channel is not None else ""
        items = root.findall(".//item")

        for item in items:
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            link = (item.findtext("link") or "").strip()
            raw_desc = (item.findtext("description") or "").strip()
            clean_desc = html_to_text(raw_desc) if "<" in raw_desc else raw_desc

            # pubDate
            pub_date_str = item.findtext("pubDate")
            posted_at = None
            if pub_date_str:
                try:
                    import email.utils
                    parsed_tuple = email.utils.parsedate_to_datetime(pub_date_str)
                    posted_at = parsed_tuple.date()
                except Exception:
                    posted_at = None

            # Company: check author, dc:creator or default
            company = (item.findtext("author") or default_company or channel_title or domain).strip()
            # Clean "user@example.com (Company Name)"
            if "(" in company and ")" in company:
                company = company.split("(", 1)[1].split(")", 1)[0].strip()

            job = NormalizedJob(
                source="rss_feed",
                source_key=f"feed:{domain}:{canonical_url(link) or link}",
                platform="RSS",
                company=company,
                title=title,
                job_url=link,
                application_url=link,
                description=clean_desc,
                posted_at=posted_at,
                posted_at_source="platform_feed",
                work_mode=normalize_work_mode("", title),
                extraction_method="rss_feed",
                extraction_confidence=0.90,
                parser_version="1.0.0",
            )
            jobs.append(job)

    return jobs


class RssConnector(BaseConnector):
    """Connector discovering jobs from RSS/Atom vacancy feeds."""

    source_id = "rss_feed"
    name = "RSS/Atom Vacancy Feeds"
    domain = "*"
    category = SourceCategory.RSS_FEED
    access_method = AccessMethod.FEED

    def __init__(self, scrapling_client: ScraplingClient | None = None):
        super().__init__()
        self.client = scrapling_client or default_client

    def discover(self, criteria: dict[str, Any] | None = None) -> list[NormalizedJob]:
        feed_urls = (criteria or {}).get("feed_urls", [])
        company_name = (criteria or {}).get("company")
        results: list[NormalizedJob] = []

        for f_url in feed_urls:
            try:
                resp = self.client.fetch_feed(f_url)
                jobs = parse_feed_xml(resp.text, resp.url, default_company=company_name)
                for j in jobs:
                    valid, _ = self.validate_job(j)
                    if valid:
                        results.append(j)
            except Exception as exc:
                log.warning("RSS fetch failed for %s: %s", f_url, exc)

        self.record_success(len(results))
        return results
