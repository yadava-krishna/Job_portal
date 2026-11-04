"""Naukri adapter (assisted mode).

Naukri has no public job-seeker API. Its own automation features (job alerts,
recruiter-visible profile, and Naukri's in-app AI job assistant where available)
are configured by the candidate inside their Naukri account; this tool cannot
and does not drive them. This adapter works from the candidate's own Naukri
alert emails and imported jobs, and the candidate applies on Naukri.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, quote, quote_plus, urlsplit

from core.models import Platform
from core.settings import SearchConfig
from platforms.base_platform import AccessCapabilities, BasePlatform, SearchLink

_LISTING_RE = re.compile(r"naukri\.com/job-listings-[^?#\s]*?-(\d{9,15})(?:[/?#]|$)", re.I)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class NaukriPlatform(BasePlatform):
    platform = Platform.NAUKRI
    official_domains = ("naukri.com",)
    capabilities = AccessCapabilities(
        automated_search=False,
        automated_apply=False,
        discovery_channels=("email_alert", "import_inbox"),
        application_method="Manual on Naukri (Apply / company site) by the candidate; Naukri's own assistant features are configured in the candidate's account",
        notes="Naukri provides no job-seeker API; automated access outside its own features is not permitted.",
    )

    def identify_job_id(self, url: str | None) -> str | None:
        if not url:
            return None
        m = _LISTING_RE.search(url)
        if m:
            return m.group(1)
        try:
            qs = parse_qs(urlsplit(url).query)
        except ValueError:
            return None
        for key in ("jobId", "jobid"):
            if qs.get(key) and qs[key][0].isdigit():
                return qs[key][0]
        return None

    def canonical_url(self, job_id: str) -> str | None:
        # Naukri job URLs need the title slug, which cannot be rebuilt from the ID alone.
        return None

    def build_search_links(self, criteria: SearchConfig) -> list[SearchLink]:
        lo, _ = self.experience_band(criteria)
        days = max(1, round(criteria.posted_within_hours / 24))
        links = []
        for location in criteria.locations:
            remote = self.is_remote_location(location)
            city = self.city_of(location)
            for title in criteria.job_titles:
                if remote:
                    # wfhType=2 is Naukri's work-from-home filter as used on naukri.com search pages.
                    url = f"https://www.naukri.com/{_slug(title)}-jobs?k={quote_plus(title)}&wfhType=2"
                else:
                    url = f"https://www.naukri.com/{_slug(title)}-jobs-in-{_slug(city)}?k={quote_plus(title)}&l={quote(city.lower())}"
                url += f"&experience={lo}&jobAge={days}"
                links.append(SearchLink(self.platform, title, location, url))
        return links
