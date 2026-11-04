"""Indeed adapter (assisted mode).

Indeed's public Job Search (Publisher) API is closed to new users, and Indeed
Apply / Job Sync APIs are available only to employers and ATS partners. Indeed
prohibits scraping and automated applying. This adapter therefore works from the
candidate's own Indeed job-alert emails and imported jobs, and the candidate
applies on Indeed (Indeed Apply) themselves.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, quote_plus, urlsplit

from core.models import Platform
from core.settings import SearchConfig
from platforms.base_platform import AccessCapabilities, BasePlatform, SearchLink

_JK_RE = re.compile(r"[?&](?:jk|vjk)=([0-9a-f]{16})", re.I)
_PATH_ID_RE = re.compile(r"indeed\.[a-z.]+/(?:m/)?(?:viewjob|rc/clk|pagead/clk|job)/?[^\s]*?[-/]([0-9a-f]{16})(?:[/?#]|$)", re.I)


class IndeedPlatform(BasePlatform):
    platform = Platform.INDEED
    official_domains = ("indeed.com", "indeed.co.in")
    capabilities = AccessCapabilities(
        automated_search=False,
        automated_apply=False,
        discovery_channels=("email_alert", "import_inbox"),
        application_method="Manual via Indeed Apply or the employer site, by the candidate",
        notes="Indeed's job search and apply APIs are restricted to approved partners; scraping and auto-apply are not permitted.",
    )

    @property
    def domain(self) -> str:
        if self.settings is not None and self.settings.platforms.indeed.domain:
            return self.settings.platforms.indeed.domain
        return "in.indeed.com"

    def identify_job_id(self, url: str | None) -> str | None:
        if not url:
            return None
        m = _JK_RE.search(url)
        if m:
            return m.group(1).lower()
        try:
            qs = parse_qs(urlsplit(url).query)
        except ValueError:
            return None
        for key in ("jk", "vjk"):
            if qs.get(key) and re.fullmatch(r"[0-9a-fA-F]{16}", qs[key][0]):
                return qs[key][0].lower()
        m = _PATH_ID_RE.search(url)
        return m.group(1).lower() if m else None

    def canonical_url(self, job_id: str) -> str | None:
        return f"https://{self.domain}/viewjob?jk={job_id}" if re.fullmatch(r"[0-9a-f]{16}", job_id) else None

    def build_search_links(self, criteria: SearchConfig) -> list[SearchLink]:
        days = max(1, round(criteria.posted_within_hours / 24))
        jt = None
        if criteria.employment_types == ["Full-time"]:
            jt = "fulltime"
        elif criteria.employment_types == ["Contract"]:
            jt = "contract"
        links = []
        for location in criteria.locations:
            loc = "Remote" if self.is_remote_location(location) else self.city_of(location)
            for title in criteria.job_titles:
                url = f"https://{self.domain}/jobs?q={quote_plus(title)}&l={quote_plus(loc)}&fromage={days}&sort=date"
                if jt:
                    url += f"&jt={jt}"
                links.append(SearchLink(self.platform, title, location, url))
        return links
